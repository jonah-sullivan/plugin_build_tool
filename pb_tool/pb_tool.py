"""
/***************************************************************************
                                    pb_tool
                 A tool for building and deploying QGIS plugins
                              -------------------
        begin                : 2014-09-24
        copyright            : (C) 2014-2026 by Gary Sherman, 2026 Jonah Sullivan
        email                : gsherman@geoapt.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = "gsherman"

import os
import sys
import subprocess
import shutil
import errno
import fnmatch
import glob
import json
import http.client
import configparser
from string import Template

import click
from importlib.metadata import version as _pkg_version, PackageNotFoundError


class AliasedGroup(click.Group):
    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        matches = [x for x in self.list_commands(ctx) if x.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail("Too many matches: %s" % ", ".join(sorted(matches)))


# @click.group()
@click.command(cls=AliasedGroup)
def cli():
    """Simple Python tool to compile and deploy a QGIS plugin.
    For help on a command use --help after the command:
    pb_tool deploy --help.

    pb_tool requires a configuration file (default: pb_tool.cfg) that
    declares the files and resources used in your plugin. Plugin Builder
    2.6.0 creates a config file when you generate a new plugin template.

    See http://g-sherman.github.io/plugin_build_tool for for an example config
    file. You can also use the create command to generate a best-guess config
    file for an existing project, then tweak as needed.

    Bugs and enhancement requests, see:
        https://github.com/g-sherman/plugin_build_tool
    """
    pass


def __version():
    """return the current version"""
    try:
        return _pkg_version("pb_tool")
    except PackageNotFoundError:
        return "unknown"


def get_install_files(cfg):
    python_files = cfg.get("files", "python_files").split()
    main_dialog = cfg.get("files", "main_dialog").split()
    extras = cfg.get("files", "extras").split()
    install_files = (
        python_files + main_dialog + compiled_ui(cfg) + compiled_resource(cfg) + extras
    )
    exclusions = cfg.get("files", "excluded_files", fallback="").split()
    if exclusions:
        install_files = [
            f for f in install_files
            if not any(fnmatch.fnmatch(f, pat) for pat in exclusions)
        ]
    return install_files


@cli.command()
def version():
    """Return the version of pb_tool and exit"""
    click.echo(__version())


@cli.command()
@click.option(
    "--config_file",
    default="pb_tool.cfg",
    help="Name of the config file to use if other than pb_tool.cfg",
)
@click.option(
    "--plugin_path",
    "-p",
    default=None,
    help="Specify the directory where to deploy your plugin if not using the standard location",
)
@click.option(
    "--quick",
    "-q",
    is_flag=True,
    help="Do a quick install without compiling ui, resource, docs, \
              and translation files",
)
@click.option(
    "--no-confirm",
    "-y",
    is_flag=True,
    help="Don't ask for confirmation to overwrite existing files",
)
@click.option(
    "--no-docs",
    "-n",
    is_flag=True,
    help="Skip building the Sphinx help documentation",
)
def deploy(config_file, plugin_path, quick, no_confirm, no_docs):
    """Deploy the plugin to QGIS plugin directory using parameters in pb_tool.cfg"""
    deploy_files(config_file, plugin_path, quick=quick, confirm=not no_confirm, build_help=not no_docs)


def deploy_files(config_file, plugin_path, confirm=True, quick=False, build_help=True):
    """Deploy the plugin using parameters in pb_tool.cfg"""
    # check for the config file
    if not os.path.exists(config_file):
        click.secho("Configuration file {0} is missing.".format(config_file), fg="red")
    else:
        cfg = get_config(config_file)
        if not plugin_path:
            plugin_path = get_plugin_directory()
            if not plugin_path:
                click.secho("Unable to determine where to deploy your plugin", fg="red")
                return

        plugin_dir = os.path.join(plugin_path, cfg.get("plugin", "name"))

        if quick:
            click.secho("Doing quick deployment", fg="green")
            install_files(plugin_dir, cfg)
            click.secho(
                "Quick deployment complete---if you have problems with your"
                " plugin, try doing a full deploy.",
                fg="green",
            )

        else:
            if confirm:
                docs_line = "                * Build the help docs\n" if build_help else ""
                print("""Deploying will:
                * Remove your currently deployed version
                * Compile the ui and resource files
{0}                * Copy everything to your {1} directory
                """.format(docs_line, plugin_dir))

                proceed = click.confirm("Proceed?")
            else:
                proceed = True

            if proceed:
                # clean the deployment
                clean_deployment(False, config_file, plugin_dir)
                click.secho("Deploying to {0}".format(plugin_dir), fg="green")
                # compile to make sure everything is fresh
                click.secho("Compiling to make sure install is clean", fg="green")
                compile_files(cfg)
                if build_help:
                    build_docs()
                install_files(plugin_dir, cfg)


def install_files(plugin_dir, cfg):
    errors = []
    install_files = get_install_files(cfg)
    os.makedirs(plugin_dir, exist_ok=True)

    fail = False
    extra_dirs = cfg.get("files", "extra_dirs").split()
    for file in install_files:
        click.secho("Copying {0}".format(file), fg="magenta", nl=False)
        try:
            dest = os.path.join(plugin_dir, file)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(file, dest)
            print()
        except Exception as oops:
            errors.append("Error copying files: {0}, {1}".format(file, oops.strerror))
            click.echo(click.style(" ----> ERROR", fg="red"))
            fail = True
    for xdir in extra_dirs:
        click.secho(
            "Copying contents of {0} to {1}".format(xdir, plugin_dir),
            fg="magenta",
            nl=False,
        )
        try:
            shutil.copytree(
                xdir, os.path.join(plugin_dir, xdir), dirs_exist_ok=True
            )
            print()
        except Exception as oops:
            errors.append("Error copying directory: {0}, {1}".format(xdir, str(oops)))
            click.echo(click.style(" ----> ERROR", fg="red"))
            fail = True
    help_src = cfg.get("help", "dir")
    if os.path.exists(help_src):
        help_target = os.path.join(plugin_dir, cfg.get("help", "target"))
        click.secho(
            "Copying {0} to {1}".format(help_src, help_target), fg="magenta", nl=False
        )
        try:
            shutil.copytree(help_src, help_target, dirs_exist_ok=True)
            print()
        except Exception as oops:
            errors.append("Error copying help files: {0}, {1}".format(help_src, str(oops)))
            click.echo(click.style(" ----> ERROR", fg="red"))
            fail = True
    else:
        click.secho(
            "No help found at {0}, skipping".format(help_src), fg="yellow"
        )
    if fail:
        print("\nERRORS:")
        for error in errors:
            print(error)
        print()
        print(
            "One or more files/directories specified in your config file\n"
            "failed to deploy---make sure they exist or if not needed remove\n"
            "them from the config. To ensure proper deployment, make sure your\n"
            "UI and resource files are compiled. Using dclean to delete the\n"
            "plugin before deploying may also help."
        )
        sys.exit(1)


def clean_deployment(ask_first=True, config="pb_tool.cfg", plugin_dir=None):
    """Remove the deployed plugin from the .local/share/QGIS/QGIS4/profiles/default/python/plugins directory"""
    if not plugin_dir:
        name = get_config(config).get("plugin", "name")
        plugin_dir = os.path.join(get_plugin_directory(), name)
    if ask_first:
        proceed = click.confirm(
            "Delete the deployed plugin from {0}?".format(plugin_dir)
        )
    else:
        proceed = True

    if proceed:
        click.echo("Removing plugin from {0}".format(plugin_dir))
        try:
            shutil.rmtree(plugin_dir)
            return True
        except OSError as oops:
            print("Plugin was not deleted: {0}".format(oops.strerror))
    else:
        click.echo("Plugin was not deleted")
    return False


@cli.command()
def clean_docs():
    """
    Remove the built HTML help files from the build directory
    """
    if os.path.exists("help"):
        click.echo("Removing built HTML from the help documentation")
        if sys.platform == "win32":
            makeprg = "make.bat"
        else:
            makeprg = "make"
        cwd = os.getcwd()
        os.chdir("help")
        subprocess.check_call([makeprg, "clean"])
        os.chdir(cwd)
    else:
        print("No help directory exists in the current directory")


@cli.command()
@click.option(
    "--config",
    default="pb_tool.cfg",
    help="Name of the config file to use if other than pb_tool.cfg",
)
def dclean(config):
    """Remove the deployed plugin from the .local/share/QGIS/QGIS4/profiles/default/python/plugins directory"""
    clean_deployment(True, config)


@cli.command()
@click.option(
    "--config",
    default="pb_tool.cfg",
    help="Name of the config file to use if other than pb_tool.cfg",
)
def clean(config):
    """Remove compiled resource and ui files"""
    cfg = get_config(config)
    files = compiled_ui(cfg) + compiled_resource(cfg)
    click.echo("Cleaning resource and ui files")
    for file in files:
        try:
            os.unlink(file)
            print("Deleted: {0}".format(file))
        except OSError as oops:
            print("Couldn't delete {0}: {1}".format(file, oops.strerror))


@cli.command()
@click.option(
    "--config",
    default="pb_tool.cfg",
    help="Name of the config file to use if other than pb_tool.cfg",
)
def compile(config):
    """
    Compile the resource and ui files
    """
    compile_files(get_config(config))


@cli.command()
def doc():
    """Build HTML version of the help files using sphinx"""
    build_docs()


def build_docs():
    """Build the docs using sphinx"""
    if os.path.exists("help"):
        click.echo("Building the help documentation")
        if sys.platform == "win32":
            makeprg = "make.bat"
        else:
            makeprg = "make"
        env = os.environ.copy()
        env["PYTHON"] = sys.executable
        cwd = os.getcwd()
        os.chdir("help")
        subprocess.check_call([makeprg, "html"], env=env)
        os.chdir(cwd)
    else:
        print("No help directory exists in the current directory")


@cli.command()
@click.option(
    "--config",
    default="pb_tool.cfg",
    help="Name of the config file to use if other than pb_tool.cfg",
)
def translate(config):
    """Build translations using lrelease. Locales must be specified
    in the config file and the corresponding .ts file must exist in
    the i18n directory of your plugin."""
    cmd = check_path("lrelease")
    if not cmd:
        print(
            "Unable to find the lrelease command. Make sure it is installed"
            " and in your path."
        )
        if sys.platform == "win32":
            print(
                "You can get lrelease by installing"
                " the qt6-devel package in the Libs"
                "\nsection of the OSGeo4W Advanced Install."
            )
    else:
        cfg = get_config(config)
        if check_cfg(cfg, "files", "locales"):
            locales = cfg.get("files", "locales").split()
            if locales:
                for locale in locales:
                    name, ext = os.path.splitext(locale)
                    if ext != ".ts":
                        locale = name + ".ts"
                    subprocess.check_call([cmd, os.path.join("i18n", locale)])
            else:
                print("No translations are specified in {0}".format(config))


@cli.command()
@click.option(
    "--config_file",
    default="pb_tool.cfg",
    help="Name of the config file to use if other than pb_tool.cfg",
)
@click.option(
    "--quick",
    "-q",
    is_flag=True,
    help="Do a quick packaging without dclean and deploy (plugin must have been previously deployed)",
)
def zip(config_file, quick):
    """Package the plugin into a zip file
    suitable for uploading to the QGIS
    plugin repository"""

    # check to see if we can find zip or 7z
    use_7z = False
    zip = check_path("zip")
    if not zip:
        # check for 7z
        zip = check_path("7z")
        if not zip:
            click.secho("zip or 7z not found. Unable to package the plugin", fg="red")
            if sys.platform == "win32":
                click.secho(
                    "Install 7-Zip (https://www.7-zip.org) or ensure Git for Windows is in your PATH.",
                    fg="red",
                )
            else:
                click.secho("Install zip (e.g. apt install zip) or 7-Zip.", fg="red")
            return
        else:
            use_7z = True
    click.secho("Found zip: %s" % zip, fg="green")

    name = get_config(config_file).get("plugin", "name", fallback=None)
    if not quick:
        proceed = click.confirm("This requires a dclean and deploy first. Proceed?")
        if proceed:
            # clean_deployment(False, config)
            deploy_files(config_file, plugin_path=None, confirm=False)
    else:
        # Check to see if the plugin directory exists, otherwise we can't
        # do a quick zip
        if not os.path.exists(os.path.join(get_plugin_directory(), name)):
            # click.secho(
            #     "You must deploy the plugin before you can package it using -q",
            #     fg='red')
            # proceed = click.confirm(
            #     'Do you want to deploy and proceed with packaging?')
            # if proceed:
            deploy_files(config_file, plugin_path=None, confirm=False)
        proceed = True

    # confirm = click.confirm(
    #    'Create a packaged plugin ({0}.zip) from the deployed files?'.format(name))
    # confirm = True
    if proceed:
        # delete the zip if it exists
        if os.path.exists("{0}.zip".format(name)):
            os.unlink("{0}.zip".format(name))
        if name:
            cwd = os.getcwd()
            os.chdir(get_plugin_directory())
            # click.secho("Current directory is {}".format(os.getcwd()), fg='magenta')
            if use_7z:
                subprocess.check_call(
                    [zip, "a", "-r", os.path.join(cwd, "{0}.zip".format(name)), name,
                     "-xr!__pycache__", "-xr!*.pyc", "-xr!.buildinfo", "-xr!.buildinfo.bak"]
                )
            else:
                subprocess.check_call(
                    [zip, "-r", os.path.join(cwd, "{0}.zip".format(name)), name,
                     "-x", "*/__pycache__/*", "-x", "*/*.pyc",
                     "-x", "*/.buildinfo", "-x", "*/.buildinfo.bak"]
                )

            print(
                "The {0}.zip archive has been created in the current directory".format(
                    name
                )
            )
        else:
            click.echo("Your config file is missing the plugin name (name=parameter)")


@cli.command()
@click.option(
    "--config_file",
    default="pb_tool.cfg",
    help="Name of the config file to use if other than pb_tool.cfg",
)
def validate(config_file):
    """
    Check the pb_tool.cfg file for mandatory sections/files
    """
    valid = True
    cfg = get_config(config_file)
    if not check_cfg(cfg, "plugin", "name"):
        valid = False
    if not check_cfg(cfg, "files", "python_files"):
        valid = False
    if not check_cfg(cfg, "files", "main_dialog"):
        valid = False
    if not check_cfg(cfg, "files", "resource_files"):
        valid = False
    if not check_cfg(cfg, "files", "extras"):
        valid = False
    if not check_cfg(cfg, "help", "dir"):
        valid = False
    if not check_cfg(cfg, "help", "target"):
        valid = False

    click.secho("Using Python {}".format(sys.version), fg="green")
    if valid:
        click.secho(
            "Your {0} file is valid and contains all mandatory items".format(
                config_file
            ),
            fg="green",
        )
    else:
        click.secho("Your {0} file is invalid".format(config_file), fg="red")
    try:
        plugin_path = get_plugin_directory()
        click.secho("Plugin path: {}".format(plugin_path), fg="green")
    except Exception:
        click.secho(
            """Unable to determine location of your QGIS Plugin directory.
        Make sure your QGIS environment is setup properly for development and Python
        has access to the qgis.PyQt.QtCore module.""",
            fg="red",
        )

    zipbin = find_zip()
    a7z = find_7z()
    if zipbin:
        zip_utility = zipbin
    elif a7z:
        zip_utility = a7z
    else:
        zip_utility = None
    if not zip_utility:
        click.secho("zip or 7z not found. Unable to package the plugin", fg="red")
        click.secho("Check your path or install a zip program", fg="red")
    else:
        click.secho("Found suitable zip utility: {}".format(zip_utility), fg="green")
    # check for templates - uncomment next 4 after create function is done
    # print(__file__)
    # print("Module: {}".format (sys.modules['pb_tool']))
    # basic_tmpl = pkgutil.get_data('pb_tool', 'templates/basic.tmpl')
    # print("Read basic template: {}".format(str(basic_tmpl, 'utf-8')))

    # f = open('pb_tool/templates/basic.tmpl')
    # if f:
    #     print("opened basic.tmpl")
    # else:
    #     print("unable to find basic.tmpl")


@cli.command()
@click.option(
    "--config_file",
    default="pb_tool.cfg",
    help="Name of the config file to use if other than pb_tool.cfg",
)
def list(config_file):
    """List the contents of the configuration file"""
    if os.path.exists(config_file):
        with open(config_file) as cfg:
            for line in cfg:
                print(line[:-1])
    else:
        click.secho(
            "There is no {0} file in the current directory".format(config_file),
            fg="red",
        )
        click.secho("We can't do anything without it", fg="red")


@cli.command()
@click.option(
    "--name",
    default="pb_tool.cfg",
    help="Name of the config file to create if other than pb_tool.cfg",
)
@click.option(
    "--package",
    default=None,
    help="Name of package (lower case). This will be used as the directory name for deployment",
)
def config(name, package):
    """
    Create a config file based on source files in the current directory
    """
    click.secho(
        "Create a config file based on source files in the current directory",
        fg="green",
    )
    if name == "pb_tool.cfg":
        click.secho(
            "This will overwrite any existing pb_tool.cfg in the current directory",
            fg="red",
        )
        proceed = click.confirm("Proceed?")
        if not proceed:
            return
    template = Template(config_template())

    # get the plugin package name
    if package:
        cfg_name = package
    else:
        cfg_name = click.prompt(
            "Name of package (lower case). This will be used as the directory name for deployment"
        )

    # get the list of python files
    py_files = glob.glob("*.py")

    # guess the main dialog ui file
    main_dlg = glob.glob("*_dialog_base.ui")

    # get the other ui files
    other_ui = glob.glob("*.ui")
    # remove the main dialog file
    try:
        for ui in main_dlg:
            other_ui.remove(ui)
    except ValueError:
        # don't care if we didn't find it
        pass

    # get the resource files (.qrc)
    resources = glob.glob("*.qrc")

    extras = glob.glob("*.png") + glob.glob("metadata.txt")

    locale_list = glob.glob("i18n/*.ts")
    locales = []
    for locale in locale_list:
        locales.append(os.path.basename(locale))

    cfg = template.substitute(
        Name=cfg_name,
        PythonFiles=" ".join(py_files),
        MainDialog=" ".join(main_dlg),
        CompiledUiFiles=" ".join(other_ui),
        Resources=" ".join(resources),
        Extras=" ".join(extras),
        Locales=" ".join(locales),
    )

    fname = name
    if os.path.exists(fname):
        confirm = click.confirm("{0} exists. Overwrite?".format(name))
        if not confirm:
            fname = click.prompt("Enter a name for the config file:")

    with open(fname, "w") as f:
        f.write(cfg)

    print("Created new config file in {0}".format(fname))


@cli.command()
@click.option(
    "--type",
    "plugin_type",
    type=click.Choice(["processing", "dialog"], case_sensitive=False),
    default="processing",
    help="Type of plugin skeleton to create",
)
@click.option("--name", default=None, help="Plugin module name (snake_case)")
@click.option("--class_name", default=None, help="Plugin class name (CamelCase)")
@click.option("--description", default=None, help="Short plugin description")
@click.option("--author", default=None, help="Author name")
@click.option("--email", default=None, help="Author email")
def create(plugin_type, name, class_name, description, author, email):
    """Create a new plugin skeleton from a template"""
    from datetime import date

    name = name or click.prompt("Module name (snake_case, used as directory name)")
    class_name = class_name or click.prompt("Class name (CamelCase)")
    description = description or click.prompt("Description")
    author = author or click.prompt("Author")
    email = email or click.prompt("Email")

    subs = {
        "TemplateModuleName": name,
        "TemplateClass": class_name,
        "TemplateDescription": description,
        "TemplateAuthor": author,
        "TemplateEmail": email,
        "TemplateYear": str(date.today().year),
        "TemplateBuildDate": date.today().isoformat(),
        "TemplateVCSFormat": "$Format:%H$",
    }

    tmpl_dir = os.path.join(os.path.dirname(__file__), "templates", plugin_type)
    if not os.path.exists(tmpl_dir):
        click.secho("No templates found for type '{0}'".format(plugin_type), fg="red")
        return

    out_dir = name
    if os.path.exists(out_dir):
        if not click.confirm("Directory '{0}' exists. Overwrite?".format(out_dir)):
            return
    os.makedirs(out_dir, exist_ok=True)

    file_map = {
        "__init__.tmpl": "__init__.py",
        "module_name.tmpl": "{0}.py".format(name),
        "module_name_provider.tmpl": "{0}_provider.py".format(name),
        "module_name_algorithm.tmpl": "{0}_algorithm.py".format(name),
        "module_name_dialog.tmpl": "{0}_dialog.py".format(name),
        "module_name_dialog_base.ui.tmpl": "{0}_dialog_base.ui".format(name),
        "resources.tmpl": "resources.qrc",
        "readme.tmpl": "README.md",
        "results.tmpl": "results.py",
    }

    created_py = []
    for tmpl_file, out_file in file_map.items():
        tmpl_path = os.path.join(tmpl_dir, tmpl_file)
        if not os.path.exists(tmpl_path):
            continue
        with open(tmpl_path) as f:
            content = Template(f.read()).safe_substitute(subs)
        out_path = os.path.join(out_dir, out_file)
        with open(out_path, "w") as f:
            f.write(content)
        click.secho("Created {0}".format(out_path), fg="green")
        if out_file.endswith(".py"):
            created_py.append(out_file)

    # generate pb_tool.cfg with the correct python_files already populated
    pb_tool_tmpl_path = os.path.join(os.path.dirname(__file__), "templates", "pb_tool.tmpl")
    if os.path.exists(pb_tool_tmpl_path):
        with open(pb_tool_tmpl_path) as f:
            cfg_content = Template(f.read()).safe_substitute(dict(
                subs,
                TemplateModuleName=name,
            ))
        # replace the stub python_files line with the actual generated files
        py_files_line = "python_files: {0}".format(" ".join(created_py))
        cfg_content = cfg_content.replace(
            "python_files: __init__.py {0}.py".format(name),
            py_files_line,
        )
        cfg_path = os.path.join(out_dir, "pb_tool.cfg")
        with open(cfg_path, "w") as f:
            f.write(cfg_content)
        click.secho("Created {0}".format(cfg_path), fg="green")

    click.secho(
        "\nPlugin skeleton created in '{0}/'. "
        "Add a metadata.txt and run pb_tool deploy to get started.".format(out_dir),
        fg="green",
    )


@cli.command()
def update():
    """Check for update to pb_tool"""
    try:
        conn = http.client.HTTPSConnection("pypi.org")
        conn.request("GET", "/pypi/pb_tool/json")
        version = json.loads(conn.getresponse().read())["info"]["version"]
        click.secho("Latest version is %s" % version, fg="green")
        # convert version numbers to int
        this_version = int(__version().replace(".", ""))
        current_version = int(version.replace(".", ""))

        if this_version == current_version:
            click.secho("Your version is up to date", fg="green")
        elif current_version > this_version:
            click.secho("You have Version %s" % __version(), fg="green")
            click.secho("You can upgrade by running this command:")
            cmd = "pip install --upgrade pb_tool"
            print("   %s" % cmd)
        elif this_version > current_version:
            click.secho("You have development Version %s" % __version(), fg="green")

    except (http.client.HTTPException, OSError) as uoops:
        click.secho("Unable to check for update.")
        click.secho("%s" % uoops)


def check_cfg(cfg, section, name):
    try:
        cfg.get(section, name)
        return True
    except configparser.NoOptionError as oops:
        print(str(oops))
    except configparser.NoSectionError:
        print(
            "Missing section '{0}' when looking for option '{1}'".format(section, name)
        )
    return False


def get_config(config="pb_tool.cfg"):
    """
    Read the config file pb_tools.cfg and return it
    """
    if os.path.exists(config):
        cfg = configparser.ConfigParser()
        cfg.read(config)
        # click.echo(cfg.sections())
        return cfg
    else:
        print("There is no {0} file in the current directory".format(config))
        print("We can't do anything without it")
        sys.exit(1)


def compiled_ui(cfg):
    # cfg = get_config(config)
    try:
        uis = cfg.get("files", "compiled_ui_files").split()
        compiled = []
        for ui in uis:
            base, ext = os.path.splitext(ui)
            compiled.append("{0}.py".format(base))
            # print("Compiled UI files: {}".format(compiled))
        return compiled
    except configparser.NoSectionError as oops:
        print(str(oops))
        sys.exit(1)


def compiled_resource(cfg):
    # cfg = get_config(config)
    try:
        res_files = cfg.get("files", "resource_files").split()
        compiled = []
        for res in res_files:
            base, ext = os.path.splitext(res)
            compiled.append("{0}.py".format(base))
            # print("Compiled resource files: {}".format(compiled))
        return compiled
    except configparser.NoSectionError as oops:
        print(str(oops))
        sys.exit(1)


def compile_files(cfg):
    # Compile all ui and resource files
    # TODO add changed detection
    # cfg = get_config(config)

    # determine Qt version and select appropriate uic tool
    if check_path("pyuic6"):
        pyuic = check_path("pyuic6")
        qt_version = 6
    elif check_path("pyuic5"):
        pyuic = check_path("pyuic5")
        qt_version = 5
    else:
        pyuic = None
        qt_version = None

    if not pyuic:
        print("pyuic5/pyuic6 is not in your path---unable to compile your ui files")
        if sys.platform == "win32":
            print(
                "On Windows, run pb_tool from the OSGeo4W shell, or add the OSGeo4W "
                "bin directory to your PATH."
            )
    else:
        print("Using Qt{0} ({1})".format(qt_version, pyuic))
        ui_files = cfg.get("files", "compiled_ui_files").split()
        ui_count = 0
        for ui in ui_files:
            if os.path.exists(ui):
                base, ext = os.path.splitext(ui)
                output = "{0}.py".format(base)
                if file_changed(ui, output):
                    print("Compiling {0} to {1}".format(ui, output))
                    subprocess.check_call([pyuic, "-o", output, ui])
                    ui_count += 1
                else:
                    print("Skipping {0} (unchanged)".format(ui))
            else:
                print("{0} does not exist---skipped".format(ui))
        print("Compiled {0} UI files".format(ui_count))

    # check to see if we have rcc
    rcc = check_path("rcc")

    if not rcc:
        click.secho(
            "rcc is not in your path---unable to compile your resource file(s)",
            fg="red",
        )
        if sys.platform == "win32":
            click.secho(
                "On Windows, run pb_tool from the OSGeo4W shell, or add the OSGeo4W "
                "bin directory to your PATH.",
                fg="red",
            )
    else:
        res_files = cfg.get("files", "resource_files").split()
        res_count = 0
        for res in res_files:
            if os.path.exists(res):
                base, ext = os.path.splitext(res)
                output = "{0}.py".format(base)
                if file_changed(res, output):
                    print("Compiling {0} to {1}".format(res, output))
                    cmd = []
                    if qt_version == 6:
                        cmd += [rcc, "-g", "python"]
                    if qt_version == 5:
                        pyrcc5 = check_path("pyrcc5")
                        if pyrcc5:
                            cmd += [pyrcc5]
                        else:
                            cmd += [sys.executable, "-m", "PyQt5.pyrcc_main"]
                    cmd += ["-o", output, res]
                    subprocess.check_call(cmd)
                    with open(output, "r") as f:
                        content = f.read()
                    content = content.replace(
                        "from PySide6 import QtCore", "from qgis.PyQt import QtCore"
                    )
                    with open(output, "w") as f:
                        f.write(content)
                    res_count += 1
                else:
                    print("Skipping {0} (unchanged)".format(res))
            else:
                print("{0} does not exist---skipped".format(res))
        print("Compiled {0} resource files".format(res_count))


def copy(source, destination):
    """Copy files recursively.

    Taken from: http://www.pythoncentral.io/
                how-to-recursively-copy-a-directory-folder-in-python/

    :param source: Source directory.
    :type source: str

    :param destination: Destination directory.
    :type destination: str

    """
    try:
        shutil.copytree(source, destination, dirs_exist_ok=True)
    except OSError as e:
        # If the error was caused because the source wasn't a directory
        if e.errno == errno.ENOTDIR:
            shutil.copy(source, destination)
        else:
            print("Directory not copied. Error: %s" % e)


def get_plugin_directory():
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", home)
        candidates = [
            os.path.join(appdata, "QGIS", "QGIS4", "profiles", "default", "python", "plugins"),
            os.path.join(appdata, "QGIS", "QGIS3", "profiles", "default", "python", "plugins"),
        ]
        default = candidates[0]
    else:
        qgis4 = os.path.join(home, ".local", "share", "QGIS", "QGIS4", "profiles", "default", "python", "plugins")
        qgis3 = os.path.join(home, ".local", "share", "QGIS", "QGIS3", "profiles", "default", "python", "plugins")
        candidates = [qgis4, qgis3]
        default = qgis4
    for path in candidates:
        if os.path.exists(path):
            return path
    return default


def config_template():
    """
    :return: the template for a pb_tool.cfg file
    """
    template = """# Configuration file for plugin builder tool
# Sane defaults for your plugin generated by the Plugin Builder are
# already set below.
#
# As you add Python source files and UI files to your plugin, add
# them to the appropriate [files] section below.

[plugin]
# Name of the plugin. This is the name of the directory that will
# be created in the QGIS3/QGIS4 python/plugins directory
name: $Name

# Full path to where you want your plugin directory copied. If empty,
# the QGIS default path will be used. Don't include the plugin name in
# the path.
plugin_path:

[files]
# Python  files that should be deployed with the plugin
python_files: $PythonFiles

# The main dialog file that is loaded (not compiled)
main_dialog: $MainDialog

# Other ui files for your dialogs (these will be compiled)
compiled_ui_files: $CompiledUiFiles

# Resource file(s) that will be compiled
resource_files: $Resources

# Other files required for the plugin
extras: $Extras

# Files to exclude from deployment (glob patterns, space-separated)
excluded_files:

# Other directories to be deployed with the plugin.
# These must be subdirectories under the plugin directory
extra_dirs:

# ISO code(s) for any locales (translations), separated by spaces.
# Corresponding .ts files must exist in the i18n directory
locales: $Locales

[help]
# the built help directory that should be deployed with the plugin
dir: help/build/html
# the name of the directory to target in the deployed plugin
target: help
"""

    return template


def check_path(app):
    """Adapted from StackExchange:
    http://stackoverflow.com/questions/377017
    """
    import os

    def is_exe(fpath):
        return os.path.exists(fpath) and os.access(fpath, os.X_OK)

    def ext_candidates(fpath):
        yield fpath
        for ext in os.environ.get("PATHEXT", "").split(os.pathsep):
            yield fpath + ext

    fpath, fname = os.path.split(app)
    if fpath:
        if is_exe(app):
            return app
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, app)
            for candidate in ext_candidates(exe_file):
                if is_exe(candidate):
                    return candidate

    return None


def file_changed(infile, outfile):
    try:
        infile_s = os.stat(infile)
        outfile_s = os.stat(outfile)
        return infile_s.st_mtime > outfile_s.st_mtime
    except OSError:
        return True


def find_zip():
    # check to see if we can find zip
    zip = check_path("zip")
    return zip


def find_7z():
    # check for 7z
    zip = check_path("7z")
    return zip