import configparser
import os
import shutil
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pb_tool import pb_tool

runner = CliRunner()

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


def _read_cfg(text):
    cfg = configparser.ConfigParser()
    cfg.read_string(text)
    return cfg


def test_validate():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["validate"])
        assert result.exit_code == 0


def test_clean():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["clean"])
        assert result.exit_code == 0


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
        assert os.path.exists("test_from_pytest.cfg") == 1


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
            os.path.join("my_plugin", "__init__.py"),
            os.path.join("my_plugin", "my_plugin.py"),
            os.path.join("my_plugin", "my_plugin_algorithm.py"),
            os.path.join("my_plugin", "my_plugin_provider.py"),
            os.path.join("my_plugin", "README.md"),
            os.path.join("my_plugin", "pb_tool.cfg"),
        ]:
            assert os.path.exists(expected), f"{expected} was not created"
        with open(os.path.join("my_plugin", "my_plugin.py")) as f:
            content = f.read()
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
            os.path.join("my_plugin", "__init__.py"),
            os.path.join("my_plugin", "my_plugin.py"),
            os.path.join("my_plugin", "my_plugin_dialog.py"),
            os.path.join("my_plugin", "my_plugin_dialog_base.ui"),
            os.path.join("my_plugin", "icon.png"),
            os.path.join("my_plugin", "README.md"),
            os.path.join("my_plugin", "pb_tool.cfg"),
        ]:
            assert os.path.exists(expected), f"{expected} was not created"
        with open(os.path.join("my_plugin", "my_plugin_dialog.py")) as f:
            content = f.read()
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
            os.path.join("my_plugin", "__init__.py"),
            os.path.join("my_plugin", "my_plugin.py"),
            os.path.join("my_plugin", "my_plugin_dockwidget.py"),
            os.path.join("my_plugin", "my_plugin_dockwidget_base.ui"),
            os.path.join("my_plugin", "icon.png"),
            os.path.join("my_plugin", "README.md"),
            os.path.join("my_plugin", "pb_tool.cfg"),
        ]:
            assert os.path.exists(expected), f"{expected} was not created"
        with open(os.path.join("my_plugin", "my_plugin_dockwidget.py")) as f:
            content = f.read()
        assert "MyPlugin" in content
        assert "$Template" not in content


def test_doc():
    result = runner.invoke(pb_tool.cli, ["doc"])
    assert result.exit_code == 0


def test_deploy():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["deploy"], input="y\n")
        assert result.exit_code == 0


def test_zip():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["zip"], input="y\n")
        assert result.exit_code == 0


def test_patch_metadata_version_injection():
    """patch_metadata stamps the release version into an existing version= field."""
    with runner.isolated_filesystem():
        with open("metadata.txt", "w") as f:
            f.write("[general]\nname=TestPlugin\nversion=0.1\nauthor=Test\n")
        with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
            pb_tool.patch_metadata("metadata.txt", release_version="1.2.3")
        with open("metadata.txt") as f:
            result = f.read()
    assert "version=1.2.3" in result
    assert "version=0.1" not in result
    assert "dateTime=" in result


def test_patch_metadata_prerelease_sets_experimental():
    """patch_metadata sets experimental=True when the version is a pre-release."""
    with runner.isolated_filesystem():
        with open("metadata.txt", "w") as f:
            f.write("[general]\nname=TestPlugin\nversion=0.1\nexperimental=False\n")
        with patch.object(pb_tool, "get_git_info", return_value=(None, None)):
            pb_tool.patch_metadata("metadata.txt", release_version="1.2.0-rc1")
        with open("metadata.txt") as f:
            result = f.read()
    assert "version=1.2.0-rc1" in result
    assert "experimental=True" in result
    assert "experimental=False" not in result


def test_patch_metadata_git_info():
    """patch_metadata injects commitSha1 and commitNumber returned by get_git_info."""
    with runner.isolated_filesystem():
        with open("metadata.txt", "w") as f:
            f.write("[general]\nname=TestPlugin\nversion=0.1\n")
        with patch.object(pb_tool, "get_git_info", return_value=("abc123def456", 42)):
            pb_tool.patch_metadata("metadata.txt")
        with open("metadata.txt") as f:
            result = f.read()
    assert "commitSha1=abc123def456" in result
    assert "commitNumber=42" in result
    assert "dateTime=" in result


def test_patch_metadata_appends_missing_fields():
    """patch_metadata appends fields that don't already exist in the file."""
    with runner.isolated_filesystem():
        with open("metadata.txt", "w") as f:
            f.write("[general]\nname=TestPlugin\nversion=0.1\n")
        with patch.object(pb_tool, "get_git_info", return_value=("deadbeef", 99)):
            pb_tool.patch_metadata("metadata.txt", release_version="2.0.0")
        with open("metadata.txt") as f:
            result = f.read()
    assert "version=2.0.0" in result
    assert "commitSha1=deadbeef" in result
    assert "commitNumber=99" in result
    assert "dateTime=" in result


def test_dclean():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["dclean"], input="y\n")
        assert result.exit_code == 0


def test_resolve_plugin_path_cli_wins_over_config():
    cfg = _read_cfg(CFG_WITH_PLUGIN_PATH)
    result = pb_tool.resolve_plugin_path(cfg, "cli_path")
    assert result == os.path.abspath("cli_path")


def test_resolve_plugin_path_config_wins_over_default():
    cfg = _read_cfg(CFG_WITH_PLUGIN_PATH)
    with patch.object(pb_tool, "get_plugin_directory") as mock_default:
        result = pb_tool.resolve_plugin_path(cfg)
    mock_default.assert_not_called()
    assert result == os.path.abspath("./zip_build")


def test_resolve_plugin_path_falls_back_to_default():
    cfg = _read_cfg(MINIMAL_CFG)
    with patch.object(pb_tool, "get_plugin_directory", return_value="qgis_default"):
        result = pb_tool.resolve_plugin_path(cfg)
    assert result == os.path.abspath("qgis_default")


def test_dclean_plugin_path_option():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(MINIMAL_CFG)
        os.makedirs(os.path.join("zip_build", "TestPlugin"))
        with open(os.path.join("zip_build", "TestPlugin", "x.txt"), "w") as f:
            f.write("x")
        sentinel = os.path.abspath("default_qgis")
        with patch.object(pb_tool, "get_plugin_directory", return_value=sentinel):
            result = runner.invoke(pb_tool.cli, ["dclean", "-p", "zip_build"], input="y\n")
        assert result.exit_code == 0
        assert not os.path.exists(os.path.join("zip_build", "TestPlugin"))
        assert not os.path.exists(sentinel)


def test_dclean_config_plugin_path():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(CFG_WITH_PLUGIN_PATH)
        os.makedirs(os.path.join("zip_build", "TestPlugin"))
        with open(os.path.join("zip_build", "TestPlugin", "x.txt"), "w") as f:
            f.write("x")
        sentinel = os.path.abspath("default_qgis")
        with patch.object(pb_tool, "get_plugin_directory", return_value=sentinel):
            result = runner.invoke(pb_tool.cli, ["dclean"], input="y\n")
        assert result.exit_code == 0
        assert "Using plugin directory from pb_tool.cfg" in result.output
        assert not os.path.exists(os.path.join("zip_build", "TestPlugin"))
        assert not os.path.exists(sentinel)


def test_zip_plugin_path_option():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(MINIMAL_CFG)
        sentinel = os.path.abspath("default_qgis")
        with (
            patch.object(pb_tool, "check_path", return_value="zip"),
            patch.object(pb_tool.subprocess, "check_call"),
            patch.object(pb_tool, "get_plugin_directory", return_value=sentinel),
        ):
            result = runner.invoke(pb_tool.cli, ["zip", "-p", "zip_build"], input="y\n")
        assert result.exit_code == 0
        assert os.path.isdir(os.path.join("zip_build", "TestPlugin"))
        assert not os.path.exists(sentinel)


@pytest.mark.skipif(
    shutil.which("zip") is None and shutil.which("7z") is None,
    reason="zip/7z binary not available",
)
def test_zip_config_plugin_path_end_to_end():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(CFG_WITH_PLUGIN_PATH)
        sentinel = os.path.abspath("default_qgis")
        with patch.object(pb_tool, "get_plugin_directory", return_value=sentinel):
            result = runner.invoke(pb_tool.cli, ["zip"], input="y\n")
        assert result.exit_code == 0
        assert "Using plugin directory from pb_tool.cfg" in result.output
        assert os.path.isdir(os.path.join("zip_build", "TestPlugin"))
        assert os.path.exists("TestPlugin.zip")
        assert not os.path.exists(sentinel)


def test_list():
    result = runner.invoke(pb_tool.cli, ["list"])
    assert result.exit_code == 0


def test_update():
    result = runner.invoke(pb_tool.cli, ["update"])
    assert result.exit_code == 0


def test_version():
    result = runner.invoke(pb_tool.cli, ["version"])
    assert result.exit_code == 0


def test_compile():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["compile"])
        assert result.exit_code == 0
