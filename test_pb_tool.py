import os

import click
from click.testing import CliRunner
from pb_tool import pb_tool

runner = CliRunner()


def test_validate():
    result = runner.invoke(pb_tool.cli, ["validate"])
    assert result.exit_code == 0


def test_clean():
    result = runner.invoke(pb_tool.cli, ["clean"])
    assert result.exit_code == 0


def test_cleandocs():
    result = runner.invoke(pb_tool.cli, ["clean_docs"])
    assert result.exit_code == 0


def test_config():
    result = runner.invoke(
        pb_tool.cli,
        ["config", "--name", "test_from_pytest.cfg", "--package", "testname"],
        input="y\n",
    )
    assert result.exit_code == 0
    assert os.path.exists("test_from_pytest.cfg") == 1


def test_create():
    result = runner.invoke(pb_tool.cli, ["create"])
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
    # assert os.path.exists(os.path.join(os.getcwd(), 'whereami.zip'))


def test_dclean():
    result = runner.invoke(pb_tool.cli, ["dclean"], input="y\n")
    assert result.exit_code == 0


# def test_help():
#     result = runner.invoke(pb_tool.cli, ['help'])
#     assert result.exit_code == 0


def test_list():
    result = runner.invoke(pb_tool.cli, ["list"])
    assert result.exit_code == 0


def test_validate():
    result = runner.invoke(pb_tool.cli, ["validate"])
    assert result.exit_code == 0


def test_update():
    result = runner.invoke(pb_tool.cli, ["update"])
    assert result.exit_code == 0


def test_version():
    result = runner.invoke(pb_tool.cli, ["version"])
    assert result.exit_code == 0


def test_compile():
    result = runner.invoke(pb_tool.cli, ["compile"])
    assert result.exit_code == 0


#    results.append("Command validate failed: {}".format(result.output))
# print("testing validate: {}".format(result))
# result = runner.invoke(pb_tool.cli, ['zip', '-q'])
# print("testing zip: {}".format(result))
# print results
