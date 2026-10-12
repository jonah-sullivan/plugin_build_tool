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

__author__ = "jonah-sullivan"

import configparser
import errno
import fnmatch
import glob
import http.client
import json
import os
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from string import Template

import click
from packaging.version import Version


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
    install_files = python_files + main_dialog + compiled_ui(cfg) + compiled_resource(cfg) + extras
    exclusions = cfg.get("files", "excluded_files", fallback="").split()
    if exclusions:
        install_files = [f for f in install_files if not any(fnmatch.fnmatch(f, pat) for pat in exclusions)]
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
    deploy_files(
        config_file,
        plugin_path,
        quick=quick,
        confirm=not no_confirm,
        build_help=not no_docs,
    )


def resolve_plugin_path(cfg, plugin_path=None):
    """Resolve the plugin deployment directory.

    Precedence: explicit plugin_path (--plugin_path/-p) > plugin_path in the
    [plugin] section of the config file > the default QGIS plugin directory.
    Returns an absolute path.
    """
    if not plugin_path:
        plugin_path = cfg.get("plugin", "plugin_path", fallback=None)
        if plugin_path:
            click.secho("Using plugin directory from pb_tool.cfg", fg="green")

    if not plugin_path:
        plugin_path = get_plugin_directory()

    return Path(plugin_path).absolute()


def deploy_files(config_file, plugin_path, confirm=True, quick=False, build_help=True):
    """Deploy the plugin using parameters in pb_tool.cfg"""
    # check for the config file
    if not Path(config_file).exists():
        click.secho(f"Configuration file {config_file} is missing.", fg="red")
        sys.exit(1)
    else:
        cfg = get_config(config_file)

        plugin_path = resolve_plugin_path(cfg, plugin_path)

        plugin_dir = plugin_path / cfg.get("plugin", "name")

        if quick:
            click.secho("Doing quick deployment", fg="green")
            install_files(plugin_dir, cfg, copy_help=build_help)
            click.secho(
                "Quick deployment complete---if you have problems with your plugin, try doing a full deploy.",
                fg="green",
            )

        else:
            if confirm:
                docs_line = "                * Build the help docs\n" if build_help else ""
                print(
                    f"""Deploying will:
                * Remove your currently deployed version
                * Compile the ui and resource files
{docs_line}                * Copy everything to your {plugin_dir} directory
                """
                )

                proceed = click.confirm("Proceed?")
            else:
                proceed = True

            if proceed:
                # clean the deployment
                clean_deployment(False, config_file, plugin_dir)
                click.secho(f"Deploying to {plugin_dir}", fg="green")
                # compile to make sure everything is fresh
                click.secho("Compiling to make sure install is clean", fg="green")
                compile_files(cfg)
                if build_help:
                    build_docs()
                install_files(plugin_dir, cfg, copy_help=build_help)


def install_files(plugin_dir, cfg, copy_help=True):
    errors = []
    install_files = get_install_files(cfg)
    plugin_dir.mkdir(parents=True, exist_ok=True)

    fail = False
    extra_dirs = cfg.get("files", "extra_dirs", fallback="").split()
    for file in install_files:
        click.secho(f"Copying {file}", fg="magenta")
        try:
            dest = plugin_dir / file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(file, dest)
            print()
        except Exception as oops:
            errors.append(f"Error copying files: {file}, {oops.strerror}")
            click.echo(click.style(" ----> ERROR", fg="red"))
            fail = True
    for xdir in extra_dirs:
        click.secho(
            f"Copying contents of {xdir} to {plugin_dir}",
            fg="magenta",
        )
        try:
            shutil.copytree(xdir, plugin_dir / xdir, dirs_exist_ok=True)
        except Exception as oops:
            errors.append(f"Error copying directory: {xdir}, {oops}")
            click.echo(click.style(" ----> ERROR", fg="red"))
            fail = True
    if copy_help:
        help_src = cfg.get("help", "dir", fallback=None)
        help_target_name = cfg.get("help", "target", fallback=None)
        if not help_src or not help_target_name:
            click.secho("No [help] section in config, skipping help files", fg="yellow")
        elif Path(help_src).exists():
            help_target = plugin_dir / help_target_name
            click.secho(f"Copying {help_src} to {help_target}", fg="magenta")
            try:
                shutil.copytree(help_src, help_target, dirs_exist_ok=True)
            except Exception as oops:
                errors.append(f"Error copying help files: {help_src}, {oops}")
                click.echo(click.style(" ----> ERROR", fg="red"))
                fail = True
        else:
            click.secho(f"No help found at {help_src}, skipping", fg="yellow")
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
        cfg = get_config(config)
        plugin_dir = resolve_plugin_path(cfg) / cfg.get("plugin", "name")
    if ask_first:
        proceed = click.confirm(f"Delete the deployed plugin from {plugin_dir}?")
    else:
        proceed = True

    if proceed:
        click.echo(f"Removing plugin from {plugin_dir}")
        try:
            shutil.rmtree(plugin_dir)
            return True
        except OSError as oops:
            print(f"Plugin was not deleted: {oops.strerror}")
    else:
        click.echo("Plugin was not deleted")
    return False


@cli.command()
def clean_docs():
    """
    Remove the built HTML help files from the build directory
    """
    if Path("help").exists():
        click.echo("Removing built HTML from the help documentation")
        if sys.platform == "win32":
            makeprg = "make.bat"
        else:
            makeprg = "make"
        subprocess.check_call([makeprg, "clean"], cwd=Path("help"))

    else:
        print("No help directory exists in the current directory")


@cli.command()
@click.option(
    "--config",
    default="pb_tool.cfg",
    help="Name of the config file to use if other than pb_tool.cfg",
)
@click.option(
    "--plugin_path",
    "-p",
    default=None,
    help="Specify the directory where your plugin is deployed if not using the standard location",
)
def dclean(config, plugin_path):
    """Remove the deployed plugin from the QGIS plugin directory,
    --plugin_path, or plugin_path in the config file"""
    cfg = get_config(config)
    plugin_dir = resolve_plugin_path(cfg, plugin_path) / cfg.get("plugin", "name")
    clean_deployment(True, config, plugin_dir)


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
            Path(file).unlink()
            print(f"Deleted: {file}")
        except OSError as oops:
            print(f"Couldn't delete {file}: {oops.strerror}")


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
    if Path("help").exists():
        click.echo("Building the help documentation")
        if sys.platform == "win32":
            makeprg = "make.bat"
        else:
            makeprg = "make"
        env = os.environ.copy()
        env["PYTHON"] = sys.executable
        subprocess.check_call([makeprg, "html"], env=env, cwd=Path("help"))
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
        print("Unable to find the lrelease command. Make sure it is installed and in your path.")
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
                    locale = Path(locale).with_suffix(".ts")
                    subprocess.check_call([cmd, Path("i18n") / locale])
            else:
                print(f"No translations are specified in {config}")


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
@click.option(
    "--plugin_path",
    "-p",
    default=None,
    help="Specify the directory where your plugin is deployed if not using the standard location",
)
@click.option(
    "--no-docs",
    "-n",
    is_flag=True,
    help="Skip building the Sphinx help documentation",
)
@click.option(
    "--release-version",
    default=None,
    help="Stamp this version string into metadata.txt before packaging (e.g. 1.2.0)",
)
def zip(config_file, quick, plugin_path, no_docs, release_version):
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
            sys.exit(1)
        else:
            use_7z = True
    click.secho("Found zip: %s" % zip, fg="green")

    cfg = get_config(config_file)
    name = cfg.get("plugin", "name", fallback=None)
    if not name:
        click.secho("Your config file is missing the plugin name (name=parameter)", fg="red")
        sys.exit(1)
    plugin_path = resolve_plugin_path(cfg, plugin_path)
    if not quick:
        proceed = click.confirm("This requires a dclean and deploy first. Proceed?")
        if proceed:
            # clean_deployment(False, config)
            deploy_files(config_file, plugin_path=plugin_path, build_help=not no_docs, confirm=False)
    else:
        # Check to see if the plugin directory exists, otherwise we can't
        # do a quick zip
        if not Path(plugin_path).joinpath(name).exists():
            deploy_files(config_file, plugin_path=plugin_path, build_help=not no_docs, confirm=False)
        proceed = True

    if proceed:
        # inject version/git info into the deployed metadata.txt before zipping
        metadata_path = Path(plugin_path) / name / "metadata.txt"
        if metadata_path.exists():
            patch_metadata(metadata_path, release_version)
            click.secho("Patched metadata.txt with build info", fg="green")
        elif release_version:
            click.secho(
                "Warning: metadata.txt not found in deployed plugin, skipping version injection",
                fg="yellow",
            )

        # delete the zip if it exists
        zip_path = Path(f"{name}.zip").absolute()
        if zip_path.exists():
            zip_path.unlink()
        if use_7z:
            subprocess.check_call(
                [
                    zip,
                    "a",
                    "-r",
                    str(zip_path),
                    name,
                    "-xr!__pycache__",
                    "-xr!*.pyc",
                    "-xr!.buildinfo",
                    "-xr!.buildinfo.bak",
                ],
                cwd=plugin_path,
            )
        else:
            subprocess.check_call(
                [
                    zip,
                    "-r",
                    str(zip_path),
                    name,
                    "-x",
                    "*/__pycache__/*",
                    "-x",
                    "*/*.pyc",
                    "-x",
                    "*/.buildinfo",
                    "-x",
                    "*/.buildinfo.bak",
                ],
                cwd=plugin_path,
            )
        print(f"The {name}.zip archive has been created in the current directory")


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

    click.secho(f"Using Python {sys.version}", fg="green")
    if valid:
        click.secho(
            f"Your {config_file} file is valid and contains all mandatory items",
            fg="green",
        )
    else:
        click.secho(f"Your {config_file} file is invalid", fg="red")
    try:
        plugin_path = get_plugin_directory()
        click.secho(f"Plugin path: {plugin_path}", fg="green")
    except Exception:
        click.secho(
            """Unable to determine location of your QGIS Plugin directory.
            Make sure your QGIS environment is setup properly for development
            and Python has access to the qgis.PyQt.QtCore module.""",
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
        click.secho(f"Found suitable zip utility: {zip_utility}", fg="green")

    if not valid:
        sys.exit(1)


@cli.command()
@click.option(
    "--config_file",
    default="pb_tool.cfg",
    help="Name of the config file to use if other than pb_tool.cfg",
)
def list(config_file):
    """List the contents of the configuration file"""
    if Path(config_file).exists():
        for line in Path(config_file).read_text().splitlines():
            print(line)
    else:
        click.secho(
            f"There is no {config_file} file in the current directory",
            fg="red",
        )
        click.secho("We can't do anything without it", fg="red")
        sys.exit(1)


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
        cfg_name = click.prompt("Name of package (lower case). This will be used as the directory name for deployment")

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
        locales.append(Path(locale).name)

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
    if Path(fname).exists():
        confirm = click.confirm(f"{name} exists. Overwrite?")
        if not confirm:
            fname = click.prompt("Enter a name for the config file:")

    Path(fname).write_text(cfg)

    print(f"Created new config file in {fname}")


@cli.command()
@click.option(
    "--type",
    "plugin_type",
    type=click.Choice(["processing", "dialog", "dockwidget"], case_sensitive=False),
    default="processing",
    help="Type of plugin skeleton to create",
)
@click.option("--name", default=None, help="Plugin module name (snake_case)")
@click.option("--class_name", default=None, help="Plugin class name (CamelCase)")
@click.option("--title", default=None, help="Human-readable plugin title (used in menus)")
@click.option("--description", default=None, help="Short plugin description")
@click.option("--author", default=None, help="Author name")
@click.option("--email", default=None, help="Author email")
def create(plugin_type, name, class_name, title, description, author, email):
    """Create a new plugin skeleton from a template"""
    import shutil
    from datetime import date

    name = name or click.prompt("Module name (snake_case, used as directory name)")
    class_name = class_name or click.prompt("Class name (CamelCase)")
    title = title or click.prompt("Plugin title (shown in menus)", default=class_name)
    description = description or click.prompt("Description")
    author = author or click.prompt("Author")
    email = email or click.prompt("Email")

    # Per-type substitution variables for pb_tool.cfg template
    type_cfg = {
        "dialog": {
            "TemplatePyFiles": f"{name}_dialog.py",
            "TemplateUiFiles": f"{name}_dialog_base.ui",
            "TemplateExtraFiles": "icon.png",
        },
        "dockwidget": {
            "TemplatePyFiles": f"{name}_dockwidget.py",
            "TemplateUiFiles": f"{name}_dockwidget_base.ui",
            "TemplateExtraFiles": "icon.png",
        },
        "processing": {
            "TemplatePyFiles": f"{name}_provider.py {name}_algorithm.py",
            "TemplateUiFiles": "",
            "TemplateExtraFiles": "icon.png",
        },
    }

    subs = {
        "TemplateModuleName": name,
        "TemplateClass": class_name,
        "TemplateTitle": title,
        "TemplateMenuText": title,
        "TemplateDescription": description,
        "TemplateAuthor": author,
        "TemplateEmail": email,
        "TemplateYear": str(date.today().year),
        "TemplateBuildDate": date.today().isoformat(),
        "TemplateVCSFormat": "$Format:%H$",
        # dialog / dockwidget menu wiring
        "TemplateMenuAddMethod": "addPluginToMenu",
        "TemplateMenuRemoveMethod": "removePluginMenu",
        # dockwidget dock area
        "TemplateDockWidgetArea": "Qt.RightDockWidgetArea",
        # processing provider / algorithm identifiers
        "TemplateAlgoName": name,
        "TemplateAlgoGroup": name,
        "TemplateProviderName": name,
        # pb_tool.cfg placeholders
        **type_cfg[plugin_type],
    }

    tmpl_dir = Path(__file__).parent / "templates" / plugin_type
    if not tmpl_dir.exists():
        click.secho(f"No templates found for type '{plugin_type}'", fg="red")
        sys.exit(1)

    out_dir = Path(name)
    if out_dir.exists():
        if not click.confirm(f"Directory '{out_dir}' exists. Overwrite?"):
            return
    out_dir.mkdir(parents=True, exist_ok=True)

    file_map = {
        "__init__.tmpl": "__init__.py",
        "module_name.tmpl": f"{name}.py",
        "module_name_provider.tmpl": f"{name}_provider.py",
        "module_name_algorithm.tmpl": f"{name}_algorithm.py",
        "module_name_dialog.tmpl": f"{name}_dialog.py",
        "module_name_dialog_base.ui.tmpl": f"{name}_dialog_base.ui",
        "module_name_dockwidget.tmpl": f"{name}_dockwidget.py",
        "module_name_dockwidget_base.ui.tmpl": f"{name}_dockwidget_base.ui",
        "readme.tmpl": "README.md",
    }

    for tmpl_file, out_file in file_map.items():
        tmpl_path = tmpl_dir / tmpl_file
        if not tmpl_path.exists():
            continue
        content = tmpl_path.read_text()
        content = Template(content).safe_substitute(subs)
        out_path = out_dir / out_file
        out_path.write_text(content)
        click.secho(f"Created {out_path}", fg="green")

    # copy icon.png from templates root into the output directory
    icon_src = Path(__file__).parent / "templates" / "icon.png"
    if icon_src.exists():
        icon_dst = out_dir / "icon.png"
        shutil.copy2(icon_src, icon_dst)
        click.secho(f"Created {icon_dst}", fg="green")

    # generate pb_tool.cfg
    pb_tool_tmpl_path = Path(__file__).parent / "templates" / "pb_tool.tmpl"
    if pb_tool_tmpl_path.exists():
        cfg_content = Template(pb_tool_tmpl_path.read_text()).safe_substitute(subs)
        cfg_path = out_dir / "pb_tool.cfg"
        cfg_path.write_text(cfg_content)
        click.secho(f"Created {cfg_path}", fg="green")

    click.secho(
        f"\nPlugin skeleton created in '{out_dir}/'. Add a metadata.txt and run pb_tool deploy to get started.",
        fg="green",
    )


@cli.command()
def update():
    """Check for update to pb_tool"""
    try:
        conn = http.client.HTTPSConnection("pypi.org")
        conn.request("GET", "/pypi/pb_tool/json")
        version = json.loads(conn.getresponse().read())["info"]["version"]
        click.secho(f"Latest version is {version}", fg="green")
        if __version() == "unknown":
            click.secho("Unable to determine your installed version", fg="yellow")
            return

        # convert versions
        this_version = Version(__version())  # this is the installed one
        current_version = Version(version)  # 'current_version' is the PyPI latest
        if this_version == current_version:
            click.secho("Your version is up to date", fg="green")
        elif current_version > this_version:
            click.secho(f"You have Version {__version()}", fg="green")
            click.secho("You can upgrade by running this command:")
            cmd = "pip install --upgrade pb_tool"
            print(f"   {cmd}")
        elif this_version > current_version:
            click.secho(f"You have development Version {__version()}", fg="green")

    except (http.client.HTTPException, OSError) as uoops:
        click.secho("Unable to check for update.")
        click.secho(f"{uoops}")
    finally:
        conn.close()


def check_cfg(cfg, section, name):
    try:
        cfg.get(section, name)
        return True
    except configparser.NoOptionError as oops:
        print(str(oops))
    except configparser.NoSectionError:
        print(f"Missing section '{section}' when looking for option '{name}'")
    return False


def get_config(config="pb_tool.cfg"):
    """
    Read the config file pb_tools.cfg and return it
    """
    if Path(config).exists():
        cfg = configparser.ConfigParser()
        cfg.read(config)
        # click.echo(cfg.sections())
        return cfg
    else:
        print(f"There is no {config} file in the current directory")
        print("We can't do anything without it")
        sys.exit(1)


def compiled_ui(cfg):
    try:
        uis = cfg.get("files", "compiled_ui_files").split()
        compiled = []
        for ui in uis:
            compiled.append(str(Path(ui).with_suffix(".py")))
        return compiled
    except configparser.NoSectionError as oops:
        print(str(oops))
        sys.exit(1)


def compiled_resource(cfg):
    try:
        res_files = cfg.get("files", "resource_files").split()
        compiled = []
        for res in res_files:
            compiled.append(str(Path(res).with_suffix(".py")))
        return compiled
    except configparser.NoSectionError as oops:
        print(str(oops))
        sys.exit(1)


def compile_files(cfg):
    # Compile all ui and resource files
    # TODO add changed detection
    # cfg = get_config(config)

    ui_files = cfg.get("files", "compiled_ui_files").split()
    res_files = cfg.get("files", "resource_files").split()

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

    if not ui_files:
        print("Compiled 0 UI files")
    elif not pyuic:
        print("pyuic5/pyuic6 is not in your path---unable to compile your ui files")
        if sys.platform == "win32":
            print("On Windows, run pb_tool from the OSGeo4W shell, or add the OSGeo4W bin directory to your PATH.")
    else:
        print(f"Using Qt{qt_version} ({pyuic})")
        ui_count = 0
        for ui in ui_files:
            if Path(ui).exists():
                output = str(Path(ui).with_suffix(".py"))
                if file_changed(ui, output):
                    print(f"Compiling {ui} to {output}")
                    subprocess.check_call([pyuic, "-o", output, ui])
                    ui_count += 1
                else:
                    print(f"Skipping {ui} (unchanged)")
            else:
                print(f"{ui} does not exist---skipped")
        print(f"Compiled {ui_count} UI files")

    if not res_files:
        print("Compiled 0 resource files")
        return

    # rcc is only needed for the Qt6 pipeline; Qt5 uses pyrcc5 (or the
    # PyQt5.pyrcc_main fallback) instead.
    rcc = None
    if qt_version == 6:
        rcc = check_path("rcc")
        if not rcc:
            click.secho(
                "rcc is not in your path---unable to compile your resource file(s)",
                fg="red",
            )
            if sys.platform == "win32":
                click.secho(
                    "On Windows, run pb_tool from the OSGeo4W shell, or add the OSGeo4W bin directory to your PATH.",
                    fg="red",
                )
            return
    elif qt_version is None:
        print("Unable to determine Qt version---skipping resource compilation")
        return

    res_count = 0
    for res in res_files:
        if Path(res).exists():
            output = str(Path(res).with_suffix(".py"))
            if file_changed(res, output):
                print(f"Compiling {res} to {output}")
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
                content = Path(output).read_text()
                content = content.replace("from PySide6 import QtCore", "from qgis.PyQt import QtCore")
                Path(output).write_text(content)
                res_count += 1
            else:
                print(f"Skipping {res} (unchanged)")
        else:
            print(f"{res} does not exist---skipped")
    print(f"Compiled {res_count} resource files")


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
    home = Path.home()
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home))
        candidates = [
            Path(appdata, "QGIS", "QGIS4", "profiles", "default", "python", "plugins"),
            Path(appdata, "QGIS", "QGIS3", "profiles", "default", "python", "plugins"),
        ]
        default = candidates[0]
    else:
        qgis4 = Path(
            home,
            ".local",
            "share",
            "QGIS",
            "QGIS4",
            "profiles",
            "default",
            "python",
            "plugins",
        )
        qgis3 = Path(
            home,
            ".local",
            "share",
            "QGIS",
            "QGIS3",
            "profiles",
            "default",
            "python",
            "plugins",
        )
        candidates = [qgis4, qgis3]
        default = qgis4
    for path in candidates:
        if Path(path).exists():
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
    return shutil.which(app)


def file_changed(infile, outfile):
    try:
        infile_s = Path(infile).stat()
        outfile_s = Path(outfile).stat()
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


def get_git_info():
    """Return (sha1, commit_count) from git, or (None, None) if not in a git repo."""
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        count = subprocess.check_output(["git", "rev-list", "--count", "HEAD"], text=True).strip()
        return sha, int(count)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, None


def patch_metadata(metadata_path, release_version=None):
    """Inject version, git SHA, commit count, and datetime into a deployed metadata.txt.

    Edits are surgical: only the touched keys change. Comments, blank lines and
    key order in the rest of the file are left untouched. Parsing follows the
    same rules QGIS and the plugin repository use (configparser semantics via
    ConfigUpdater), so ``=`` and ``:`` separators and leading whitespace around
    them are all handled consistently.
    """
    import re
    from datetime import datetime, timezone

    from configupdater import ConfigUpdater

    updater = ConfigUpdater()
    updater.optionxform = str  # preserve camelCase keys (commitSha1, dateTime)
    cfg_content = Path(metadata_path).read_text(encoding="utf-8")
    updater.read_string(cfg_content)

    if not updater.has_section("general"):
        updater.add_section("general")
    general = updater["general"]

    def set_key(key, value):
        value = str(value)
        if key in general:
            general[key].value = value
        else:
            general[key] = value

    if release_version:
        set_key("version", release_version)
        is_prerelease = bool(re.search(r"[-.](?:rc|alpha|beta|dev)\d*", release_version, re.I))
        if is_prerelease:
            set_key("experimental", "True")

    sha, count = get_git_info()
    if sha:
        set_key("commitSha1", sha)
    if count is not None:
        set_key("commitNumber", count)

    set_key("dateTime", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    Path(metadata_path).write_text(str(updater), encoding="utf-8")
