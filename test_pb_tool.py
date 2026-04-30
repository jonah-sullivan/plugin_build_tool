import os

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
                "--name", "my_plugin",
                "--class_name", "MyPlugin",
                "--title", "My Plugin",
                "--description", "A test plugin",
                "--author", "Test Author",
                "--email", "test@example.com",
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
                "--type", "processing",
                "--name", "my_plugin",
                "--class_name", "MyPlugin",
                "--title", "My Plugin",
                "--description", "A test plugin",
                "--author", "Test Author",
                "--email", "test@example.com",
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
                "--type", "dialog",
                "--name", "my_plugin",
                "--class_name", "MyPlugin",
                "--title", "My Plugin",
                "--description", "A test plugin",
                "--author", "Test Author",
                "--email", "test@example.com",
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
                "--type", "dockwidget",
                "--name", "my_plugin",
                "--class_name", "MyPlugin",
                "--title", "My Plugin",
                "--description", "A test plugin",
                "--author", "Test Author",
                "--email", "test@example.com",
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


def test_dclean():
    with runner.isolated_filesystem():
        with open("pb_tool.cfg", "w") as f:
            f.write(MINIMAL_CFG)
        result = runner.invoke(pb_tool.cli, ["dclean"], input="y\n")
        assert result.exit_code == 0


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
