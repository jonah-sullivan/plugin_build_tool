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
                "--description", "A test plugin",
                "--author", "Test Author",
                "--email", "test@example.com",
            ],
        )
        assert result.exit_code == 0


def test_doc():
    result = runner.invoke(pb_tool.cli, ["doc"])
    assert result.exit_code == 0


def test_deploy():
    result = runner.invoke(pb_tool.cli, ["deploy"], input="y\n")
    assert result.exit_code == 0


def test_zip():
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
