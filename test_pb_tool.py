import ast
import builtins
import configparser
import json
import os
import re
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pb_tool import pb_tool

runner = CliRunner()

_real_get_plugin_directory = pb_tool.get_plugin_directory


@pytest.fixture(autouse=True)
def _isolated_qgis_plugin_dir(tmp_path, monkeypatch):
    # never let a test deploy to (or dclean) the real QGIS plugins folder
    monkeypatch.setattr(pb_tool, "get_plugin_directory", lambda: tmp_path / "qgis_plugins")


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
locales:
"""


def _read_cfg(text):
    cfg = configparser.ConfigParser()
    cfg.read_string(text)
    return cfg


def test_validate():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["validate"])
        assert result.exit_code == 0


def test_clean():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["clean"])
        assert result.exit_code == 0


CLEAN_CFG = MINIMAL_CFG.replace("compiled_ui_files:", "compiled_ui_files: settings.ui forms/extra.ui").replace(
    "resource_files:", "resource_files: resources.qrc"
)


def test_clean_deletes_compiled_files():
    with runner.isolated_filesystem():
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


def test_clean_reports_missing_compiled_files():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(CLEAN_CFG)
        Path("resources.py").write_text("")

        result = runner.invoke(pb_tool.cli, ["clean"])
        # a missing file is reported, not fatal, and the rest still get deleted
        assert result.exit_code == 0
        assert "Couldn't delete settings.py" in result.output
        assert not Path("resources.py").exists()


def test_cleandocs():
    result = runner.invoke(pb_tool.cli, ["clean-docs"])
    assert result.exit_code == 0


def test_config():
    with runner.isolated_filesystem():
        result = runner.invoke(
            pb_tool.cli,
            ["config", "--name", "test_from_pytest.cfg", "--package", "testname"],
            input="y\n",
        )
        assert result.exit_code == 0
        assert Path("test_from_pytest.cfg").exists()


def _write_plugin_sources():
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


def test_config_discovers_source_files():
    with runner.isolated_filesystem():
        _write_plugin_sources()
        result = runner.invoke(pb_tool.cli, ["config", "--name", "discovered.cfg", "--package", "foo"])
        assert result.exit_code == 0
        cfg = _read_cfg(Path("discovered.cfg").read_text())

        def files(option):
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


def test_config_empty_directory():
    with runner.isolated_filesystem():
        result = runner.invoke(pb_tool.cli, ["config", "--name", "empty.cfg", "--package", "foo"])
        assert result.exit_code == 0
        cfg = _read_cfg(Path("empty.cfg").read_text())
        for option in ["python_files", "main_dialog", "compiled_ui_files", "resource_files", "extras", "locales"]:
            assert cfg.get("files", option) == ""


def test_config_default_name_declined_does_not_write():
    with runner.isolated_filesystem():
        result = runner.invoke(pb_tool.cli, ["config", "--package", "foo"], input="n\n")
        assert result.exit_code == 0
        assert "This will overwrite any existing pb_tool.cfg" in result.output
        assert not Path("pb_tool.cfg").exists()


def test_create():
    with runner.isolated_filesystem():
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


def test_create_processing_files():
    """create --type processing produces the expected files with substituted content."""
    with runner.isolated_filesystem():
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


def test_create_dialog_files():
    """create --type dialog produces the expected files with substituted content."""
    with runner.isolated_filesystem():
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


def test_create_dockwidget_files():
    """create --type dockwidget produces the expected files with substituted content."""
    with runner.isolated_filesystem():
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


def _undefined_names(tree):
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
def test_create_generates_valid_python(plugin_type):
    """Every generated .py file compiles and references no undefined names."""
    with runner.isolated_filesystem():
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


def test_doc():
    result = runner.invoke(pb_tool.cli, ["doc"])
    assert result.exit_code == 0


def test_deploy():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["deploy"], input="y\n")
        assert result.exit_code == 0


def _write_legacy_plugin_files():
    Path("pb_tool.cfg").write_text(LEGACY_CFG_NO_HELP)
    Path("__init__.py").write_text("")
    Path("bar").mkdir(parents=True, exist_ok=True)
    (Path("bar") / "baz.txt").write_text("baz")


def test_deploy_quick_no_docs_without_help_section():
    with runner.isolated_filesystem():
        _write_legacy_plugin_files()
        result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--no-docs", "--quick"])
        assert result.exit_code == 0
        assert (Path("deploy_build") / "TestPlugin" / "__init__.py").exists()
        assert (Path("deploy_build") / "TestPlugin" / "bar" / "baz.txt").exists()


def test_deploy_full_without_help_section():
    with runner.isolated_filesystem():
        _write_legacy_plugin_files()
        result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--no-docs"])
        assert result.exit_code == 0
        assert (Path("deploy_build") / "TestPlugin" / "__init__.py").exists()


def test_deploy_missing_python_file_fails():
    with runner.isolated_filesystem():
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


def test_deploy_missing_extra_dir_fails():
    with runner.isolated_filesystem():
        _write_legacy_plugin_files()
        Path("pb_tool.cfg").write_text(LEGACY_CFG_NO_HELP.replace("extra_dirs: bar", "extra_dirs: bar nodir"))
        result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--no-docs", "--quick"])
        assert result.exit_code == 1
        assert "ERRORS:" in result.output
        assert "Error copying directory: nodir" in result.output
        assert (Path("deploy_build") / "TestPlugin" / "bar" / "baz.txt").exists()


LEGACY_CFG_WITH_HELP = (
    LEGACY_CFG_NO_HELP
    + """
[help]
dir: help/build/html
target: help
"""
)


def _write_help_build():
    html_dir = Path("help") / "build" / "html"
    (html_dir / "_static").mkdir(parents=True)
    (html_dir / "index.html").write_text("<html>index</html>")
    (html_dir / "_static" / "style.css").write_text("body {}")


def test_deploy_copies_help_files():
    with runner.isolated_filesystem():
        _write_legacy_plugin_files()
        Path("pb_tool.cfg").write_text(LEGACY_CFG_WITH_HELP)
        _write_help_build()
        result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--quick"])
        assert result.exit_code == 0
        help_target = Path("deploy_build") / "TestPlugin" / "help"
        assert (help_target / "index.html").read_text() == "<html>index</html>"
        assert (help_target / "_static" / "style.css").exists()


def test_deploy_no_docs_skips_help_files():
    with runner.isolated_filesystem():
        _write_legacy_plugin_files()
        Path("pb_tool.cfg").write_text(LEGACY_CFG_WITH_HELP)
        _write_help_build()
        result = runner.invoke(pb_tool.cli, ["deploy", "-y", "--quick", "--no-docs"])
        assert result.exit_code == 0
        assert not (Path("deploy_build") / "TestPlugin" / "help").exists()


def test_deploy_missing_help_build_is_skipped():
    with runner.isolated_filesystem():
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


def test_get_install_files_without_exclusions():
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
def test_get_install_files_exclusions(excluded, removed):
    cfg = _read_cfg(INSTALL_FILES_CFG.replace("locales:", f"locales:\nexcluded_files: {excluded}"))
    all_files = pb_tool.get_install_files(_read_cfg(INSTALL_FILES_CFG))
    expected = [f for f in all_files if f not in removed]
    assert pb_tool.get_install_files(cfg) == expected


def test_zip_full_without_help_section():
    with runner.isolated_filesystem():
        _write_legacy_plugin_files()
        with (
            patch.object(pb_tool, "check_path", return_value="zip"),
            patch.object(pb_tool.subprocess, "check_call"),
        ):
            result = runner.invoke(pb_tool.cli, ["zip", "--no-docs"], input="y\n")
        assert result.exit_code == 0
        assert (Path("deploy_build") / "TestPlugin" / "__init__.py").exists()


def test_zip():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        with (
            patch.object(pb_tool, "check_path", return_value="zip"),
            patch.object(pb_tool.subprocess, "check_call"),
        ):
            result = runner.invoke(pb_tool.cli, ["zip"], input="y\n")
        assert result.exit_code == 0


def test_zip_no_zip_binary():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        with patch.object(pb_tool, "check_path", return_value=None):
            result = runner.invoke(pb_tool.cli, ["zip"], input="y\n")
        assert result.exit_code != 0
        assert "zip or 7z not found" in result.output


def test_zip_missing_plugin_name():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG.replace("name: TestPlugin", "name:"))
        with patch.object(pb_tool, "check_path", return_value="zip"):
            result = runner.invoke(pb_tool.cli, ["zip"], input="y\n")
        assert result.exit_code != 0
        assert "missing the plugin name" in result.output


def test_deploy_missing_config():
    with runner.isolated_filesystem():
        result = runner.invoke(pb_tool.cli, ["deploy", "-y"])
        assert result.exit_code != 0


def test_validate_invalid_config():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG.replace("main_dialog:\n", ""))
        result = runner.invoke(pb_tool.cli, ["validate"])
        assert result.exit_code != 0
        assert "invalid" in result.output


def _meta_value(text, key):
    """Return the value of ``key`` in a metadata.txt string, or None.

    Accepts either ``=`` or ``:`` as the separator and any whitespace around it,
    so tests don't have to care how patch_metadata formats the line.
    """
    m = re.search(rf"^\s*{re.escape(key)}\s*[:=]\s*(.*?)\s*$", text, re.M)
    return m.group(1) if m else None


def test_patch_metadata_version_injection():
    """patch_metadata stamps the release version into an existing version field."""
    with runner.isolated_filesystem():
        Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion=0.1\nauthor=Test\n")
        with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
            pb_tool.patch_metadata("metadata.txt", release_version="1.2.3")
        result = Path("metadata.txt").read_text()
    assert _meta_value(result, "version") == "1.2.3"
    assert _meta_value(result, "dateTime")
    # untouched keys are left exactly as they were
    assert "name=TestPlugin" in result
    assert "author=Test" in result


def test_patch_metadata_prerelease_sets_experimental():
    """patch_metadata sets experimental=True when the version is a pre-release."""
    with runner.isolated_filesystem():
        Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion=0.1\nexperimental=False\n")
        with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
            pb_tool.patch_metadata("metadata.txt", release_version="1.2.0-rc1")
        result = Path("metadata.txt").read_text()
    assert _meta_value(result, "version") == "1.2.0-rc1"
    assert _meta_value(result, "experimental") == "True"


def test_patch_metadata_git_info():
    """patch_metadata injects commitSha1 and commitNumber returned by get_git_info."""
    with runner.isolated_filesystem():
        Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion=0.1\n")
        with patch.object(pb_tool, "get_git_info", return_value=("abc123def456", 42)):
            pb_tool.patch_metadata("metadata.txt")
        result = Path("metadata.txt").read_text()
    assert _meta_value(result, "commitSha1") == "abc123def456"
    assert _meta_value(result, "commitNumber") == "42"
    assert _meta_value(result, "dateTime")


def test_patch_metadata_appends_missing_fields():
    """patch_metadata appends fields that don't already exist in the file."""
    with runner.isolated_filesystem():
        Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion=0.1\n")
        with patch.object(pb_tool, "get_git_info", return_value=("deadbeef", 99)):
            pb_tool.patch_metadata("metadata.txt", release_version="2.0.0")
        result = Path("metadata.txt").read_text()
    assert _meta_value(result, "version") == "2.0.0"
    assert _meta_value(result, "commitSha1") == "deadbeef"
    assert _meta_value(result, "commitNumber") == "99"
    assert _meta_value(result, "dateTime")


def test_patch_metadata_with_whitespace():
    """patch_metadata tolerates whitespace around the key/value separator."""
    with runner.isolated_filesystem():
        Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion = 0.1\nexperimental =False\n")
        with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
            pb_tool.patch_metadata("metadata.txt", release_version="1.2.0-rc1")
        result = Path("metadata.txt").read_text()
    assert _meta_value(result, "version") == "1.2.0-rc1"
    assert _meta_value(result, "experimental") == "True"


def test_patch_metadata_colon_separator():
    """patch_metadata patches keys that use a colon separator (QGIS accepts both)."""
    with runner.isolated_filesystem():
        Path("metadata.txt").write_text("[general]\nname=TestPlugin\nversion: 0.1\n")
        with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
            pb_tool.patch_metadata("metadata.txt", release_version="1.2.3")
        result = Path("metadata.txt").read_text()
    assert _meta_value(result, "version") == "1.2.3"
    assert "0.1" not in result


def test_patch_metadata_preserves_comments_and_order():
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
    with runner.isolated_filesystem():
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


def test_patch_metadata_creates_general_section_if_missing():
    """patch_metadata adds a [general] section instead of crashing when absent."""
    with runner.isolated_filesystem():
        Path("metadata.txt").write_text("[help]\nfoo=bar\n")
        with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
            pb_tool.patch_metadata("metadata.txt", release_version="1.0.0")
        result = Path("metadata.txt").read_text()
    assert "[general]" in result
    assert _meta_value(result, "version") == "1.0.0"
    assert "[help]\nfoo=bar" in result


def test_dclean():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["dclean"], input="y\n")
        assert result.exit_code == 0


def test_resolve_plugin_path_cli_wins_over_config():
    cfg = _read_cfg(CFG_WITH_PLUGIN_PATH)
    result = pb_tool.resolve_plugin_path(cfg, "cli_path")
    assert result == Path("cli_path").absolute()


def test_resolve_plugin_path_config_wins_over_default():
    cfg = _read_cfg(CFG_WITH_PLUGIN_PATH)
    with patch.object(pb_tool, "get_plugin_directory") as mock_default:
        result = pb_tool.resolve_plugin_path(cfg)
    mock_default.assert_not_called()
    assert result == Path("./zip_build").absolute()


def test_resolve_plugin_path_falls_back_to_default():
    cfg = _read_cfg(MINIMAL_CFG)
    with patch.object(pb_tool, "get_plugin_directory", return_value="qgis_default"):
        result = pb_tool.resolve_plugin_path(cfg)
    assert result == Path("qgis_default").absolute()


def test_dclean_plugin_path_option():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        (Path("zip_build") / "TestPlugin").mkdir(parents=True, exist_ok=True)
        (Path("zip_build") / "TestPlugin" / "x.txt").write_text("x")
        sentinel = Path("default_qgis").absolute()
        with patch.object(pb_tool, "get_plugin_directory", return_value=sentinel):
            result = runner.invoke(pb_tool.cli, ["dclean", "-p", "zip_build"], input="y\n")
        assert result.exit_code == 0
        assert not (Path("zip_build") / "TestPlugin").exists()
        assert not sentinel.exists()


def test_dclean_config_plugin_path():
    with runner.isolated_filesystem():
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


def test_zip_plugin_path_option():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        sentinel = Path("default_qgis").absolute()
        with (
            patch.object(pb_tool, "check_path", return_value="zip"),
            patch.object(pb_tool.subprocess, "check_call"),
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
def test_zip_config_plugin_path_end_to_end():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(CFG_WITH_PLUGIN_PATH)
        sentinel = Path("default_qgis").absolute()
        with patch.object(pb_tool, "get_plugin_directory", return_value=sentinel):
            result = runner.invoke(pb_tool.cli, ["zip"], input="y\n")
        assert result.exit_code == 0
        assert "Using plugin directory from pb_tool.cfg" in result.output
        assert (Path("zip_build") / "TestPlugin").is_dir()
        assert (Path("TestPlugin.zip")).exists()
        assert not sentinel.exists()


def test_list():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["list"])
        assert result.exit_code == 0
        assert "TestPlugin" in result.output


def test_list_missing_config():
    with runner.isolated_filesystem():
        result = runner.invoke(pb_tool.cli, ["list"])
        assert result.exit_code != 0


def test_version():
    result = runner.invoke(pb_tool.cli, ["version"])
    assert result.exit_code == 0


def test_compile():
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["compile"])
        assert result.exit_code == 0


def test_compile_no_files_no_tool_warnings(monkeypatch):
    # See issue #44: an empty compiled_ui_files/resource_files config should
    # never trigger "not in your path" warnings, even if no Qt tools exist.
    monkeypatch.setattr(pb_tool, "check_path", lambda app: None)
    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["compile"])
        assert result.exit_code == 0
        assert "pyuic5/pyuic6 is not in your path" not in result.output
        assert "rcc is not in your path" not in result.output
        assert "Compiled 0 UI files" in result.output
        assert "Compiled 0 resource files" in result.output


def test_compile_qt5_resources_without_rcc(monkeypatch):
    # Qt5 resource compilation uses pyrcc5, not rcc, so a missing rcc binary
    # should not block it.
    cfg = MINIMAL_CFG.replace("resource_files:", "resource_files: resources.qrc")

    def fake_check_path(app):
        return {"pyuic5": "/fake/pyuic5", "pyrcc5": "/fake/pyrcc5"}.get(app)

    def fake_check_call(cmd):
        output = cmd[cmd.index("-o") + 1]
        Path(output).write_text("# compiled\n")

    monkeypatch.setattr(pb_tool, "check_path", fake_check_path)
    monkeypatch.setattr(pb_tool.subprocess, "check_call", fake_check_call)

    with runner.isolated_filesystem():
        Path("pb_tool.cfg").write_text(cfg)
        Path("resources.qrc").write_text("<RCC></RCC>\n")
        result = runner.invoke(pb_tool.cli, ["compile"])
        assert result.exit_code == 0
        assert "rcc is not in your path" not in result.output
        assert "Compiled 1 resource files" in result.output


@pytest.mark.parametrize(
    "installed, latest, expected",
    [
        ("3.5.3", "3.5.3", "up to date"),
        ("3.5.10", "3.6.0", "pip install --upgrade"),
        ("3.6.0", "3.5.10", "development Version"),
    ],
)
def test_update_version_compare(installed, latest, expected):
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


def _touch(path, mtime):
    Path(path).write_text("")
    os.utime(path, (mtime, mtime))


def test_file_changed_source_newer(tmp_path):
    _touch(tmp_path / "a.ui", 2000)
    _touch(tmp_path / "a.py", 1000)
    assert pb_tool.file_changed(tmp_path / "a.ui", tmp_path / "a.py") is True


def test_file_changed_output_up_to_date(tmp_path):
    _touch(tmp_path / "a.ui", 1000)
    _touch(tmp_path / "a.py", 2000)
    assert pb_tool.file_changed(tmp_path / "a.ui", tmp_path / "a.py") is False


def test_file_changed_same_mtime_is_unchanged(tmp_path):
    _touch(tmp_path / "a.ui", 1000)
    _touch(tmp_path / "a.py", 1000)
    assert pb_tool.file_changed(tmp_path / "a.ui", tmp_path / "a.py") is False


def test_file_changed_missing_output(tmp_path):
    _touch(tmp_path / "a.ui", 1000)
    assert pb_tool.file_changed(tmp_path / "a.ui", tmp_path / "a.py") is True


# --- get_plugin_directory -------------------------------------------------

PLUGINS = ("profiles", "default", "python", "plugins")


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr(pb_tool.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(pb_tool.sys, "platform", "linux")
    return tmp_path


def test_get_plugin_directory_defaults_to_qgis4(fake_home):
    # neither profile exists yet
    expected = fake_home.joinpath(".local", "share", "QGIS", "QGIS4", *PLUGINS)
    assert _real_get_plugin_directory() == expected


def test_get_plugin_directory_prefers_existing_qgis4(fake_home):
    for version in ("QGIS3", "QGIS4"):
        fake_home.joinpath(".local", "share", "QGIS", version, *PLUGINS).mkdir(parents=True)
    expected = fake_home.joinpath(".local", "share", "QGIS", "QGIS4", *PLUGINS)
    assert _real_get_plugin_directory() == expected


def test_get_plugin_directory_falls_back_to_qgis3(fake_home):
    qgis3 = fake_home.joinpath(".local", "share", "QGIS", "QGIS3", *PLUGINS)
    qgis3.mkdir(parents=True)
    assert _real_get_plugin_directory() == qgis3


def test_get_plugin_directory_windows_uses_appdata(fake_home, monkeypatch):
    monkeypatch.setattr(pb_tool.sys, "platform", "win32")
    appdata = fake_home / "AppData" / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))
    qgis3 = appdata.joinpath("QGIS", "QGIS3", *PLUGINS)
    qgis3.mkdir(parents=True)
    assert _real_get_plugin_directory() == qgis3


# --- AliasedGroup (command prefixes) --------------------------------------


@pytest.mark.parametrize("prefix", ["vers", "versi"])
def test_command_prefix_resolves_unique_match(prefix):
    result = runner.invoke(pb_tool.cli, [prefix])
    assert result.exit_code == 0
    assert result.output == runner.invoke(pb_tool.cli, ["version"]).output


def test_exact_command_name_wins_over_longer_matches():
    # "clean" is also a prefix of "clean-docs", but the exact name must win
    with runner.isolated_filesystem():
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
def test_ambiguous_command_prefix_fails(prefix, matches):
    result = runner.invoke(pb_tool.cli, [prefix])
    assert result.exit_code == 2
    assert f"Too many matches: {matches}" in result.output


def test_unknown_command_fails():
    result = runner.invoke(pb_tool.cli, ["nosuchcommand"])
    assert result.exit_code == 2
    assert "No such command" in result.output
