import ast
import builtins
import configparser
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pb_tool import pb_tool

runner = CliRunner()

_real_get_plugin_directory = pb_tool.get_plugin_directory


@pytest.fixture(autouse=True)
def _isolated_qgis_plugin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # never let a test deploy to (or dclean) the real QGIS plugins folder
    monkeypatch.setattr(pb_tool, "get_plugin_directory", lambda: tmp_path / "qgis_plugins")


@pytest.fixture
def in_tmp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run the test from an empty working directory; pb_tool resolves its config
    and source files relative to the cwd.

    Uses a subdirectory so the cwd stays separate from tmp_path / "qgis_plugins",
    the default deploy target set by _isolated_qgis_plugin_dir.
    """
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


MINIMAL_CFG = """
[plugin]
name: TestPlugin

[files]
python_files:
main_dialog:
compiled_ui_files:
resource_files:
extras:
extra_dirs:
locales:

[help]
dir: help/build/html
target: help
"""

CFG_WITH_PLUGIN_PATH = MINIMAL_CFG.replace("name: TestPlugin", "name: TestPlugin\nplugin_path: ./zip_build")

# Legacy-style config without a [help] section (see issue #43)
LEGACY_CFG_NO_HELP = """
[plugin]
name: TestPlugin
plugin_path: ./deploy_build

[files]
python_files: __init__.py
main_dialog:
compiled_ui_files:
resource_files:
extras:
extra_dirs: bar
excluded_files:
locales:
"""


def _read_cfg(text: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read_string(text)
    return cfg


@pytest.mark.usefixtures("in_tmp_dir")
def test_validate() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    result = runner.invoke(pb_tool.cli, ["validate"])
    assert result.exit_code == 0


@pytest.mark.usefixtures("in_tmp_dir")
def test_clean() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    result = runner.invoke(pb_tool.cli, ["clean"])
    assert result.exit_code == 0


CLEAN_CFG = MINIMAL_CFG.replace("compiled_ui_files:", "compiled_ui_files: settings.ui forms/extra.ui").replace(
    "resource_files:", "resource_files: resources.qrc"
)


@pytest.mark.usefixtures("in_tmp_dir")
def test_clean_deletes_compiled_files() -> None:
    Path("pb_tool.cfg").write_text(CLEAN_CFG)
    Path("forms").mkdir()
    sources = ["settings.ui", "forms/extra.ui", "resources.qrc", "my_plugin.py"]
    compiled = ["settings.py", "forms/extra.py", "resources.py"]
    for name in sources + compiled:
        Path(name).write_text("")

    result = runner.invoke(pb_tool.cli, ["clean"])
    assert result.exit_code == 0
    for name in compiled:
        assert not Path(name).exists()
        assert f"Deleted: {Path(name)}" in result.output
    # the .ui/.qrc sources and unrelated .py files are left alone
    for name in sources:
        assert Path(name).exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_clean_reports_missing_compiled_files() -> None:
    Path("pb_tool.cfg").write_text(CLEAN_CFG)
    Path("resources.py").write_text("")

    result = runner.invoke(pb_tool.cli, ["clean"])
    # a missing file is reported, not fatal, and the rest still get deleted
    assert result.exit_code == 0
    assert "Couldn't delete settings.py" in result.output
    assert not Path("resources.py").exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_cleandocs() -> None:
    result = runner.invoke(pb_tool.cli, ["clean-docs"])
    assert result.exit_code == 0


@pytest.mark.usefixtures("in_tmp_dir")
def test_config() -> None:
    result = runner.invoke(
        pb_tool.cli,
        ["config", "--name", "test_from_pytest.cfg", "--package", "testname"],
        input="y\n",
    )
    assert result.exit_code == 0
    assert Path("test_from_pytest.cfg").exists()


def _write_plugin_sources() -> None:
    for name in [
        "__init__.py",
        "foo.py",
        "foo_dialog.py",
        "foo_dialog_base.ui",
        "settings.ui",
        "resources.qrc",
        "icon.png",
        "metadata.txt",
        "README.md",
    ]:
        Path(name).write_text("")
    Path("i18n").mkdir()
    Path("i18n", "foo_de.ts").write_text("")
    Path("i18n", "foo_fr.ts").write_text("")


@pytest.mark.usefixtures("in_tmp_dir")
def test_config_discovers_source_files() -> None:
    _write_plugin_sources()
    result = runner.invoke(pb_tool.cli, ["config", "--name", "discovered.cfg", "--package", "foo"])
    assert result.exit_code == 0
    cfg = _read_cfg(Path("discovered.cfg").read_text())

    def files(option: str) -> set[str]:
        # glob order depends on the filesystem, so compare as sets
        return set(cfg.get("files", option).split())

    assert cfg.get("plugin", "name") == "foo"
    assert files("python_files") == {"__init__.py", "foo.py", "foo_dialog.py"}
    assert files("main_dialog") == {"foo_dialog_base.ui"}
    # the main dialog is not repeated in compiled_ui_files
    assert files("compiled_ui_files") == {"settings.ui"}
    assert files("resource_files") == {"resources.qrc"}
    # only *.png and metadata.txt are picked up as extras
    assert files("extras") == {"icon.png", "metadata.txt"}
    # locales are stored by file name only, without the i18n/ prefix
    assert files("locales") == {"foo_de.ts", "foo_fr.ts"}


@pytest.mark.usefixtures("in_tmp_dir")
def test_config_empty_directory() -> None:
    result = runner.invoke(pb_tool.cli, ["config", "--name", "empty.cfg", "--package", "foo"])
    assert result.exit_code == 0
    cfg = _read_cfg(Path("empty.cfg").read_text())
    for option in ["python_files", "main_dialog", "compiled_ui_files", "resource_files", "extras", "locales"]:
        assert cfg.get("files", option) == ""


@pytest.mark.usefixtures("in_tmp_dir")
def test_config_default_name_declined_does_not_write() -> None:
    result = runner.invoke(pb_tool.cli, ["config", "--package", "foo"], input="n\n")
    assert result.exit_code == 0
    assert "This will overwrite any existing pb_tool.cfg" in result.output
    assert not Path("pb_tool.cfg").exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_create() -> None:
    result = runner.invoke(
        pb_tool.cli,
        [
            "create",
            "--name",
            "my_plugin",
            "--class_name",
            "MyPlugin",
            "--title",
            "My Plugin",
            "--description",
            "A test plugin",
            "--author",
            "Test Author",
            "--email",
            "test@example.com",
        ],
    )
    assert result.exit_code == 0


@pytest.mark.usefixtures("in_tmp_dir")
def test_create_processing_files() -> None:
    """create --type processing produces the expected files with substituted content."""
    result = runner.invoke(
        pb_tool.cli,
        [
            "create",
            "--type",
            "processing",
            "--name",
            "my_plugin",
            "--class_name",
            "MyPlugin",
            "--title",
            "My Plugin",
            "--description",
            "A test plugin",
            "--author",
            "Test Author",
            "--email",
            "test@example.com",
        ],
    )
    assert result.exit_code == 0
    for expected in [
        Path("my_plugin") / "__init__.py",
        Path("my_plugin") / "my_plugin.py",
        Path("my_plugin") / "my_plugin_algorithm.py",
        Path("my_plugin") / "my_plugin_provider.py",
        Path("my_plugin") / "README.md",
        Path("my_plugin") / "pb_tool.cfg",
    ]:
        assert expected.exists(), f"{expected} was not created"
    content = (Path("my_plugin") / "my_plugin.py").read_text()
    assert "MyPlugin" in content
    assert "Test Author" in content
    assert "$Template" not in content


@pytest.mark.usefixtures("in_tmp_dir")
def test_create_dialog_files() -> None:
    """create --type dialog produces the expected files with substituted content."""
    result = runner.invoke(
        pb_tool.cli,
        [
            "create",
            "--type",
            "dialog",
            "--name",
            "my_plugin",
            "--class_name",
            "MyPlugin",
            "--title",
            "My Plugin",
            "--description",
            "A test plugin",
            "--author",
            "Test Author",
            "--email",
            "test@example.com",
        ],
    )
    assert result.exit_code == 0
    for expected in [
        Path("my_plugin") / "__init__.py",
        Path("my_plugin") / "my_plugin.py",
        Path("my_plugin") / "my_plugin_dialog.py",
        Path("my_plugin") / "my_plugin_dialog_base.ui",
        Path("my_plugin") / "icon.png",
        Path("my_plugin") / "README.md",
        Path("my_plugin") / "pb_tool.cfg",
    ]:
        assert expected.exists(), f"{expected} was not created"
    content = (Path("my_plugin") / "my_plugin_dialog.py").read_text()
    assert "MyPlugin" in content
    assert "$Template" not in content


@pytest.mark.usefixtures("in_tmp_dir")
def test_create_dockwidget_files() -> None:
    """create --type dockwidget produces the expected files with substituted content."""
    result = runner.invoke(
        pb_tool.cli,
        [
            "create",
            "--type",
            "dockwidget",
            "--name",
            "my_plugin",
            "--class_name",
            "MyPlugin",
            "--title",
            "My Plugin",
            "--description",
            "A test plugin",
            "--author",
            "Test Author",
            "--email",
            "test@example.com",
        ],
    )
    assert result.exit_code == 0
    for expected in [
        Path("my_plugin") / "__init__.py",
        Path("my_plugin") / "my_plugin.py",
        Path("my_plugin") / "my_plugin_dockwidget.py",
        Path("my_plugin") / "my_plugin_dockwidget_base.ui",
        Path("my_plugin") / "icon.png",
        Path("my_plugin") / "README.md",
        Path("my_plugin") / "pb_tool.cfg",
    ]:
        assert expected.exists(), f"{expected} was not created"
    content = (Path("my_plugin") / "my_plugin_dockwidget.py").read_text()
    assert "MyPlugin" in content
    assert "$Template" not in content


def _undefined_names(tree: ast.AST) -> set[str]:
    """Names that are read somewhere in the module but never bound or imported."""
    bound = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__", "__spec__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)} - bound


@pytest.mark.parametrize("plugin_type", ["processing", "dialog", "dockwidget"])
@pytest.mark.usefixtures("in_tmp_dir")
def test_create_generates_valid_python(plugin_type: str) -> None:
    """Every generated .py file compiles and references no undefined names."""
    result = runner.invoke(
        pb_tool.cli,
        [
            "create",
            "--type",
            plugin_type,
            "--name",
            "my_plugin",
            "--class_name",
            "MyPlugin",
            "--title",
            "My Plugin",
            "--description",
            "A test plugin",
            "--author",
            "Test Author",
            "--email",
            "test@example.com",
        ],
    )
    assert result.exit_code == 0, result.output
    py_files = list(Path("my_plugin").glob("*.py"))
    assert py_files
    for py_file in py_files:
        source = py_file.read_text()
        tree = ast.parse(source, filename=str(py_file))
        compile(tree, str(py_file), "exec")
        assert not _undefined_names(tree), f"{py_file}: undefined {_undefined_names(tree)}"


@pytest.mark.usefixtures("in_tmp_dir")
def test_doc() -> None:
    result = runner.invoke(pb_tool.cli, ["doc"])
    assert result.exit_code == 0


@pytest.mark.usefixtures("in_tmp_dir")
def test_deploy() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    result = runner.invoke(pb_tool.cli, ["deploy"], input="y\n")
    assert result.exit_code == 0


def _write_legacy_plugin_files(search: str = "", replace: str = "") -> None:
    Path("pb_tool.cfg").write_text(LEGACY_CFG_NO_HELP.replace(search, replace))
    Path("__init__.py").write_text("")
    Path("bar").mkdir(parents=True, exist_ok=True)
    (Path("bar") / "baz.txt").write_text("baz")
    (Path("bar") / "foo.txt").write_text("foo")


@pytest.mark.usefixtures("in_tmp_dir")
def test_deploy_quick_no_docs_without_help_section() -> None:
    _write_legacy_plugin_files()
    result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--no-docs", "--quick"])
    assert result.exit_code == 0
    assert (Path("deploy_build") / "TestPlugin" / "__init__.py").exists()
    assert (Path("deploy_build") / "TestPlugin" / "bar" / "baz.txt").exists()
    assert (Path("deploy_build") / "TestPlugin" / "bar" / "foo.txt").exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_deploy_full_without_help_section() -> None:
    _write_legacy_plugin_files()
    result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--no-docs"])
    assert result.exit_code == 0
    assert (Path("deploy_build") / "TestPlugin" / "__init__.py").exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_deploy_missing_python_file_fails() -> None:
    _write_legacy_plugin_files()
    Path("pb_tool.cfg").write_text(
        LEGACY_CFG_NO_HELP.replace("python_files: __init__.py", "python_files: __init__.py missing.py")
    )
    result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--no-docs", "--quick"])
    assert result.exit_code == 1
    assert "ERRORS:" in result.output
    assert "Error copying files: missing.py" in result.output
    # files that do exist are still copied
    assert (Path("deploy_build") / "TestPlugin" / "__init__.py").exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_deploy_missing_extra_dir_fails() -> None:
    _write_legacy_plugin_files()
    Path("pb_tool.cfg").write_text(LEGACY_CFG_NO_HELP.replace("extra_dirs: bar", "extra_dirs: bar nodir"))
    result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--no-docs", "--quick"])
    assert result.exit_code == 1
    assert "ERRORS:" in result.output
    assert "Error copying directory: nodir" in result.output
    assert (Path("deploy_build") / "TestPlugin" / "bar" / "baz.txt").exists()
    assert (Path("deploy_build") / "TestPlugin" / "bar" / "foo.txt").exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_deploy_skips_excluded_files() -> None:
    _write_legacy_plugin_files("excluded_files:", "excluded_files: foo.*")
    result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--no-docs", "--quick"])
    assert result.exit_code == 0
    assert (Path("deploy_build") / "TestPlugin" / "__init__.py").exists()
    assert (Path("deploy_build") / "TestPlugin" / "bar" / "baz.txt").exists()
    assert not (Path("deploy_build") / "TestPlugin" / "bar" / "foo.txt").exists()


LEGACY_CFG_WITH_HELP = (
    LEGACY_CFG_NO_HELP
    + """
[help]
dir: help/build/html
target: help
"""
)


def _write_help_build() -> None:
    html_dir = Path("help") / "build" / "html"
    (html_dir / "_static").mkdir(parents=True)
    (html_dir / "index.html").write_text("<html>index</html>")
    (html_dir / "_static" / "style.css").write_text("body {}")


@pytest.mark.usefixtures("in_tmp_dir")
def test_deploy_copies_help_files() -> None:
    _write_legacy_plugin_files()
    Path("pb_tool.cfg").write_text(LEGACY_CFG_WITH_HELP)
    _write_help_build()
    result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--quick"])
    assert result.exit_code == 0
    help_target = Path("deploy_build") / "TestPlugin" / "help"
    assert (help_target / "index.html").read_text() == "<html>index</html>"
    assert (help_target / "_static" / "style.css").exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_deploy_no_docs_skips_help_files() -> None:
    _write_legacy_plugin_files()
    Path("pb_tool.cfg").write_text(LEGACY_CFG_WITH_HELP)
    _write_help_build()
    result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--quick", "--no-docs"])
    assert result.exit_code == 0
    assert not (Path("deploy_build") / "TestPlugin" / "help").exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_deploy_missing_help_build_is_skipped() -> None:
    _write_legacy_plugin_files()
    Path("pb_tool.cfg").write_text(LEGACY_CFG_WITH_HELP)
    result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--quick"])
    assert result.exit_code == 0
    assert "No help found at help/build/html, skipping" in result.output
    assert not (Path("deploy_build") / "TestPlugin" / "help").exists()


INSTALL_FILES_CFG = """
[plugin]
name: TestPlugin

[files]
python_files: __init__.py my_plugin.py my_plugin_test.py test_utils.py
main_dialog: my_plugin_dialog_base.ui
compiled_ui_files: settings.ui
resource_files: resources.qrc
extras: icon.png metadata.txt notes.md
extra_dirs:
locales:
"""


def test_get_install_files_without_exclusions() -> None:
    cfg = _read_cfg(INSTALL_FILES_CFG)
    assert pb_tool.get_install_files(cfg) == [
        "__init__.py",
        "my_plugin.py",
        "my_plugin_test.py",
        "test_utils.py",
        "my_plugin_dialog_base.ui",
        "settings.py",
        "resources.py",
        "icon.png",
        "metadata.txt",
        "notes.md",
    ]


@pytest.mark.parametrize(
    "excluded, removed",
    [
        ("notes.md", {"notes.md"}),
        ("*_test.py", {"my_plugin_test.py"}),
        ("*_test.py test_*.py", {"my_plugin_test.py", "test_utils.py"}),
        ("*.md *.png", {"notes.md", "icon.png"}),
        # compiled .ui/.qrc outputs go through the same filter
        ("resources.py", {"resources.py"}),
        ("nomatch.*", set()),
    ],
)
def test_get_install_files_exclusions(excluded: str, removed: set[str]) -> None:
    cfg = _read_cfg(INSTALL_FILES_CFG.replace("locales:", f"locales:\nexcluded_files: {excluded}"))
    all_files = pb_tool.get_install_files(_read_cfg(INSTALL_FILES_CFG))
    expected = [f for f in all_files if f not in removed]
    assert pb_tool.get_install_files(cfg) == expected


@pytest.mark.usefixtures("in_tmp_dir")
def test_zip_full_without_help_section() -> None:
    _write_legacy_plugin_files()
    with (
        patch.object(pb_tool, "check_path", return_value="zip"),
        patch.object(subprocess, "check_call"),
    ):
        result = runner.invoke(pb_tool.cli, ["zip", "--no-docs"], input="y\n")
    assert result.exit_code == 0
    assert (Path("deploy_build") / "TestPlugin" / "__init__.py").exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_zip() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    with (
        patch.object(pb_tool, "check_path", return_value="zip"),
        patch.object(subprocess, "check_call"),
    ):
        result = runner.invoke(pb_tool.cli, ["zip"], input="y\n")
    assert result.exit_code == 0


@pytest.mark.usefixtures("in_tmp_dir")
def test_zip_no_zip_binary() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    with patch.object(pb_tool, "check_path", return_value=None):
        result = runner.invoke(pb_tool.cli, ["zip"], input="y\n")
    assert result.exit_code != 0
    assert "zip or 7z not found" in result.output


@pytest.mark.usefixtures("in_tmp_dir")
def test_zip_missing_plugin_name() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG.replace("name: TestPlugin", "name:"))
    with patch.object(pb_tool, "check_path", return_value="zip"):
        result = runner.invoke(pb_tool.cli, ["zip"], input="y\n")
    assert result.exit_code != 0
    assert "missing the plugin name" in result.output


@pytest.mark.usefixtures("in_tmp_dir")
def test_deploy_missing_config() -> None:
    result = runner.invoke(pb_tool.cli, ["deploy", "-y"])
    assert result.exit_code != 0


@pytest.mark.usefixtures("in_tmp_dir")
def test_validate_invalid_config() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG.replace("main_dialog:\n", ""))
    result = runner.invoke(pb_tool.cli, ["validate"])
    assert result.exit_code != 0
    assert "invalid" in result.output


def _meta_value(text: str, key: str) -> str | None:
    """Return the value of ``key`` in a metadata.txt string, or None.

    Accepts either ``=`` or ``:`` as the separator and any whitespace around it,
    so tests don't have to care how patch_metadata formats the line.
    """
    m = re.search(rf"^\s*{re.escape(key)}\s*[:=]\s*(.*?)\s*$", text, re.M)
    return m.group(1) if m else None


@pytest.mark.usefixtures("in_tmp_dir")
def test_patch_metadata_version_injection() -> None:
    """patch_metadata stamps the release version into an existing version field."""
    Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion=0.1\nauthor=Test\n")
    with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
        pb_tool.patch_metadata("metadata.txt", release_version="1.2.3")
    result = Path("metadata.txt").read_text()
    assert _meta_value(result, "version") == "1.2.3"
    assert _meta_value(result, "dateTime")
    # untouched keys are left exactly as they were
    assert "name=TestPlugin" in result
    assert "author=Test" in result


@pytest.mark.usefixtures("in_tmp_dir")
def test_patch_metadata_prerelease_sets_experimental() -> None:
    """patch_metadata sets experimental=True when the version is a pre-release."""
    Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion=0.1\nexperimental=False\n")
    with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
        pb_tool.patch_metadata("metadata.txt", release_version="1.2.0-rc1")
    result = Path("metadata.txt").read_text()
    assert _meta_value(result, "version") == "1.2.0-rc1"
    assert _meta_value(result, "experimental") == "True"


@pytest.mark.usefixtures("in_tmp_dir")
def test_patch_metadata_git_info() -> None:
    """patch_metadata injects commitSha1 and commitNumber returned by get_git_info."""
    Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion=0.1\n")
    with patch.object(pb_tool, "get_git_info", return_value=("abc123def456", 42)):
        pb_tool.patch_metadata("metadata.txt")
    result = Path("metadata.txt").read_text()
    assert _meta_value(result, "commitSha1") == "abc123def456"
    assert _meta_value(result, "commitNumber") == "42"
    assert _meta_value(result, "dateTime")


@pytest.mark.usefixtures("in_tmp_dir")
def test_patch_metadata_appends_missing_fields() -> None:
    """patch_metadata appends fields that don't already exist in the file."""
    Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion=0.1\n")
    with patch.object(pb_tool, "get_git_info", return_value=("deadbeef", 99)):
        pb_tool.patch_metadata("metadata.txt", release_version="2.0.0")
    result = Path("metadata.txt").read_text()
    assert _meta_value(result, "version") == "2.0.0"
    assert _meta_value(result, "commitSha1") == "deadbeef"
    assert _meta_value(result, "commitNumber") == "99"
    assert _meta_value(result, "dateTime")


@pytest.mark.usefixtures("in_tmp_dir")
def test_patch_metadata_with_whitespace() -> None:
    """patch_metadata tolerates whitespace around the key/value separator."""
    Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion = 0.1\nexperimental =False\n")
    with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
        pb_tool.patch_metadata("metadata.txt", release_version="1.2.0-rc1")
    result = Path("metadata.txt").read_text()
    assert _meta_value(result, "version") == "1.2.0-rc1"
    assert _meta_value(result, "experimental") == "True"


@pytest.mark.usefixtures("in_tmp_dir")
def test_patch_metadata_colon_separator() -> None:
    """patch_metadata patches keys that use a colon separator (QGIS accepts both)."""
    Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion: 0.1\n")
    with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
        pb_tool.patch_metadata("metadata.txt", release_version="1.2.3")
    result = Path("metadata.txt").read_text()
    assert _meta_value(result, "version") == "1.2.3"
    assert "0.1" not in result


@pytest.mark.usefixtures("in_tmp_dir")
def test_patch_metadata_preserves_comments_and_order() -> None:
    """patch_metadata only rewrites the keys it touches, leaving the rest intact."""
    original = (
        "[general]\n"
        "name=TestPlugin\n"
        "# release notes below - keep this comment\n"
        "changelog=\n"
        "    1.0 first release\n"
        "\n"
        "version=0.1\n"
        "about=Handles 50% of the cases\n"
        "\n"
        "[extra]\n"
        "foo=bar\n"
    )
    Path("metadata.txt").write_text(original)
    with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
        pb_tool.patch_metadata("metadata.txt", release_version="1.2.3")
    result = Path("metadata.txt").read_text()
    assert "# release notes below - keep this comment" in result
    assert "    1.0 first release" in result
    assert "about=Handles 50% of the cases" in result  # '%' left untouched
    assert "[extra]\nfoo=bar" in result
    assert result.index("name=TestPlugin") < result.index("changelog=") < result.index("about=")
    assert _meta_value(result, "version") == "1.2.3"


@pytest.mark.usefixtures("in_tmp_dir")
def test_patch_metadata_creates_general_section_if_missing() -> None:
    """patch_metadata adds a [general] section instead of crashing when absent."""
    Path("metadata.txt").write_text("[help]\nfoo=bar\n")
    with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
        pb_tool.patch_metadata("metadata.txt", release_version="1.0.0")
    result = Path("metadata.txt").read_text()
    assert "[general]" in result
    assert _meta_value(result, "version") == "1.0.0"
    assert "[help]\nfoo=bar" in result


@pytest.mark.usefixtures("in_tmp_dir")
def test_dclean() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    result = runner.invoke(pb_tool.cli, ["dclean"], input="y\n")
    assert result.exit_code == 0


def test_resolve_plugin_path_cli_wins_over_config() -> None:
    cfg = _read_cfg(CFG_WITH_PLUGIN_PATH)
    result = pb_tool.resolve_plugin_path(cfg, "cli_path")
    assert result == Path("cli_path").absolute()


def test_resolve_plugin_path_config_wins_over_default() -> None:
    cfg = _read_cfg(CFG_WITH_PLUGIN_PATH)
    with patch.object(pb_tool, "get_plugin_directory") as mock_default:
        result = pb_tool.resolve_plugin_path(cfg)
    mock_default.assert_not_called()
    assert result == Path("./zip_build").absolute()


def test_resolve_plugin_path_falls_back_to_default() -> None:
    cfg = _read_cfg(MINIMAL_CFG)
    with patch.object(pb_tool, "get_plugin_directory", return_value=Path("qgis_default")):
        result = pb_tool.resolve_plugin_path(cfg)
    assert result == Path("qgis_default").absolute()


@pytest.mark.usefixtures("in_tmp_dir")
def test_dclean_plugin_path_option() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    (Path("zip_build") / "TestPlugin").mkdir(parents=True, exist_ok=True)
    (Path("zip_build") / "TestPlugin" / "x.txt").write_text("x")
    sentinel = Path("default_qgis").absolute()
    with patch.object(pb_tool, "get_plugin_directory", return_value=sentinel):
        result = runner.invoke(pb_tool.cli, ["dclean", "-p", "zip_build"], input="y\n")
    assert result.exit_code == 0
    assert not (Path("zip_build") / "TestPlugin").exists()
    assert not sentinel.exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_dclean_config_plugin_path() -> None:
    Path("pb_tool.cfg").write_text(CFG_WITH_PLUGIN_PATH)
    (Path("zip_build") / "TestPlugin").mkdir(parents=True, exist_ok=True)
    (Path("zip_build") / "TestPlugin" / "x.txt").write_text("x")
    sentinel = Path("default_qgis").absolute()
    with patch.object(pb_tool, "get_plugin_directory", return_value=sentinel):
        result = runner.invoke(pb_tool.cli, ["dclean"], input="y\n")
    assert result.exit_code == 0
    assert "Using plugin directory from pb_tool.cfg" in result.output
    assert not (Path("zip_build") / "TestPlugin").exists()
    assert not sentinel.exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_zip_plugin_path_option() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    sentinel = Path("default_qgis").absolute()
    with (
        patch.object(pb_tool, "check_path", return_value="zip"),
        patch.object(subprocess, "check_call"),
        patch.object(pb_tool, "get_plugin_directory", return_value=sentinel),
    ):
        result = runner.invoke(pb_tool.cli, ["zip", "-p", "zip_build"], input="y\n")
    assert result.exit_code == 0
    assert (Path("zip_build") / "TestPlugin").is_dir()
    assert not sentinel.exists()


@pytest.mark.skipif(
    shutil.which("zip") is None and shutil.which("7z") is None,
    reason="zip/7z binary not available",
)
@pytest.mark.usefixtures("in_tmp_dir")
def test_zip_config_plugin_path_end_to_end() -> None:
    Path("pb_tool.cfg").write_text(CFG_WITH_PLUGIN_PATH)
    sentinel = Path("default_qgis").absolute()
    with patch.object(pb_tool, "get_plugin_directory", return_value=sentinel):
        result = runner.invoke(pb_tool.cli, ["zip"], input="y\n")
    assert result.exit_code == 0
    assert "Using plugin directory from pb_tool.cfg" in result.output
    assert (Path("zip_build") / "TestPlugin").is_dir()
    assert (Path("TestPlugin.zip")).exists()
    assert not sentinel.exists()


@pytest.mark.usefixtures("in_tmp_dir")
def test_list() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    result = runner.invoke(pb_tool.cli, ["list"])
    assert result.exit_code == 0
    assert "TestPlugin" in result.output


@pytest.mark.usefixtures("in_tmp_dir")
def test_list_missing_config() -> None:
    result = runner.invoke(pb_tool.cli, ["list"])
    assert result.exit_code != 0


@pytest.mark.usefixtures("in_tmp_dir")
def test_version() -> None:
    result = runner.invoke(pb_tool.cli, ["version"])
    assert result.exit_code == 0


@pytest.mark.usefixtures("in_tmp_dir")
def test_compile() -> None:
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    result = runner.invoke(pb_tool.cli, ["compile"])
    assert result.exit_code == 0


@pytest.mark.usefixtures("in_tmp_dir")
def test_compile_no_files_no_tool_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    # See issue #44: an empty compiled_ui_files/resource_files config should
    # never trigger "not in your path" warnings, even if no Qt tools exist.
    monkeypatch.setattr(pb_tool, "check_path", lambda app: None)
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    result = runner.invoke(pb_tool.cli, ["compile"])
    assert result.exit_code == 0
    assert "pyuic5/pyuic6 is not in your path" not in result.output
    assert "rcc is not in your path" not in result.output
    assert "Compiled 0 UI files" in result.output
    assert "Compiled 0 resource files" in result.output


@pytest.mark.usefixtures("in_tmp_dir")
def test_compile_qt5_resources_without_rcc(monkeypatch: pytest.MonkeyPatch) -> None:
    # Qt5 resource compilation uses pyrcc5, not rcc, so a missing rcc binary
    # should not block it.
    cfg = MINIMAL_CFG.replace("resource_files:", "resource_files: resources.qrc")

    def fake_check_path(app: str) -> str | None:
        return {"pyuic5": "/fake/pyuic5", "pyrcc5": "/fake/pyrcc5"}.get(app)

    def fake_check_call(cmd: list[str]) -> None:
        output = cmd[cmd.index("-o") + 1]
        Path(output).write_text("# compiled\n")

    monkeypatch.setattr(pb_tool, "check_path", fake_check_path)
    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    Path("pb_tool.cfg").write_text(cfg)
    Path("resources.qrc").write_text("<RCC></RCC>\n")
    result = runner.invoke(pb_tool.cli, ["compile"])
    assert result.exit_code == 0
    assert "rcc is not in your path" not in result.output
    assert "Compiled 1 resource files" in result.output


@pytest.mark.parametrize(
    "tools, expected_prefix",
    [
        ({"pyuic6": "/fake/pyuic6", "rcc": "/fake/rcc"}, ["/fake/rcc", "-g", "python"]),
        ({"pyuic5": "/fake/pyuic5", "pyrcc5": "/fake/pyrcc5"}, ["/fake/pyrcc5"]),
        ({"pyuic5": "/fake/pyuic5"}, [sys.executable, "-m", "PyQt5.pyrcc_main"]),
    ],
    ids=["qt6-rcc", "qt5-pyrcc5", "qt5-pyrcc_main-fallback"],
)
@pytest.mark.usefixtures("in_tmp_dir")
def test_compile_resource_command(
    monkeypatch: pytest.MonkeyPatch, tools: dict[str, str], expected_prefix: list[str]
) -> None:
    cfg = MINIMAL_CFG.replace("resource_files:", "resource_files: resources.qrc")
    calls: list[list[str]] = []

    def fake_check_call(cmd: list[str]) -> None:
        calls.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_text("# compiled\n")

    monkeypatch.setattr(pb_tool, "check_path", tools.get)
    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    Path("pb_tool.cfg").write_text(cfg)
    Path("resources.qrc").write_text("<RCC></RCC>\n")
    result = runner.invoke(pb_tool.cli, ["compile"])
    assert result.exit_code == 0
    assert calls == [[*expected_prefix, "-o", "resources.py", "resources.qrc"]]


@pytest.mark.usefixtures("in_tmp_dir")
def test_compile_qt6_resources_without_rcc(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = MINIMAL_CFG.replace("resource_files:", "resource_files: resources.qrc")
    calls: list[list[str]] = []
    monkeypatch.setattr(pb_tool, "check_path", {"pyuic6": "/fake/pyuic6"}.get)
    monkeypatch.setattr(subprocess, "check_call", calls.append)

    Path("pb_tool.cfg").write_text(cfg)
    Path("resources.qrc").write_text("<RCC></RCC>\n")
    result = runner.invoke(pb_tool.cli, ["compile"])
    assert result.exit_code == 0
    assert "rcc is not in your path" in result.output
    assert calls == []


@pytest.mark.parametrize(
    "installed, latest, expected",
    [
        ("3.5.3", "3.5.3", "up to date"),
        ("3.5.10", "3.6.0", "pip install --upgrade"),
        ("3.6.0", "3.5.10", "development Version"),
    ],
)
@pytest.mark.usefixtures("in_tmp_dir")
def test_update_version_compare(installed: str, latest: str, expected: str) -> None:
    resp = json.dumps({"info": {"version": latest}}).encode()
    with (
        patch("pb_tool.pb_tool.http.client.HTTPSConnection") as conn,
        patch("pb_tool.pb_tool.__version", return_value=installed),
    ):
        conn.return_value.getresponse.return_value.read.return_value = resp
        result = runner.invoke(pb_tool.cli, ["update"])
    assert result.exit_code == 0
    assert expected in result.output


# --- file_changed ---------------------------------------------------------


def _touch(path: Path, mtime: int) -> None:
    Path(path).write_text("")
    os.utime(path, (mtime, mtime))


def test_file_changed_source_newer(tmp_path: Path) -> None:
    _touch(tmp_path / "a.ui", 2000)
    _touch(tmp_path / "a.py", 1000)
    assert pb_tool.file_changed(tmp_path / "a.ui", tmp_path / "a.py") is True


def test_file_changed_output_up_to_date(tmp_path: Path) -> None:
    _touch(tmp_path / "a.ui", 1000)
    _touch(tmp_path / "a.py", 2000)
    assert pb_tool.file_changed(tmp_path / "a.ui", tmp_path / "a.py") is False


def test_file_changed_same_mtime_is_unchanged(tmp_path: Path) -> None:
    _touch(tmp_path / "a.ui", 1000)
    _touch(tmp_path / "a.py", 1000)
    assert pb_tool.file_changed(tmp_path / "a.ui", tmp_path / "a.py") is False


def test_file_changed_missing_output(tmp_path: Path) -> None:
    _touch(tmp_path / "a.ui", 1000)
    assert pb_tool.file_changed(tmp_path / "a.ui", tmp_path / "a.py") is True


# --- get_plugin_directory -------------------------------------------------

PLUGINS = ("profiles", "default", "python", "plugins")


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    return tmp_path


def test_get_plugin_directory_defaults_to_qgis4(fake_home: Path) -> None:
    # neither profile exists yet
    expected = fake_home.joinpath(".local", "share", "QGIS", "QGIS4", *PLUGINS)
    assert _real_get_plugin_directory() == expected


def test_get_plugin_directory_prefers_existing_qgis4(fake_home: Path) -> None:
    for version in ("QGIS3", "QGIS4"):
        fake_home.joinpath(".local", "share", "QGIS", version, *PLUGINS).mkdir(parents=True)
    expected = fake_home.joinpath(".local", "share", "QGIS", "QGIS4", *PLUGINS)
    assert _real_get_plugin_directory() == expected


def test_get_plugin_directory_falls_back_to_qgis3(fake_home: Path) -> None:
    qgis3 = fake_home.joinpath(".local", "share", "QGIS", "QGIS3", *PLUGINS)
    qgis3.mkdir(parents=True)
    assert _real_get_plugin_directory() == qgis3


def test_get_plugin_directory_windows_uses_appdata(fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    appdata = fake_home / "AppData" / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))
    qgis3 = appdata.joinpath("QGIS", "QGIS3", *PLUGINS)
    qgis3.mkdir(parents=True)
    assert _real_get_plugin_directory() == qgis3


# --- AliasedGroup (command prefixes) --------------------------------------


@pytest.mark.parametrize("prefix", ["vers", "versi"])
def test_command_prefix_resolves_unique_match(prefix: str) -> None:
    result = runner.invoke(pb_tool.cli, [prefix])
    assert result.exit_code == 0
    assert result.output == runner.invoke(pb_tool.cli, ["version"]).output


@pytest.mark.usefixtures("in_tmp_dir")
def test_exact_command_name_wins_over_longer_matches() -> None:
    # "clean" is also a prefix of "clean-docs", but the exact name must win
    Path("pb_tool.cfg").write_text(MINIMAL_CFG)
    result = runner.invoke(pb_tool.cli, ["clean"])
    assert result.exit_code == 0
    assert "Cleaning resource and ui files" in result.output


@pytest.mark.parametrize(
    "prefix, matches",
    [
        ("v", "validate, version"),
        ("cl", "clean, clean-docs"),
        ("d", "dclean, deploy, doc"),
    ],
)
def test_ambiguous_command_prefix_fails(prefix: str, matches: str) -> None:
    result = runner.invoke(pb_tool.cli, [prefix])
    assert result.exit_code == 2
    assert f"Too many matches: {matches}" in result.output


def test_unknown_command_fails() -> None:
    result = runner.invoke(pb_tool.cli, ["nosuchcommand"])
    assert result.exit_code == 2
    assert "No such command" in result.output
