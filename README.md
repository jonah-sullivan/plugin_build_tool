# pb_tool

[![PyPI](https://img.shields.io/pypi/v/pb-tool)](https://pypi.org/project/pb-tool/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pb-tool)](https://pypi.org/project/pb-tool/)
[![Downloads](https://img.shields.io/pypi/dm/pb-tool)](https://pypistats.org/packages/pb-tool)
![Tests](https://github.com/jonah-sullivan/plugin_build_tool/workflows/Tests/badge.svg)
[![License: GPL v2](https://img.shields.io/badge/License-GPL_v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

A command-line tool for building and deploying QGIS Python plugins. pb_tool handles compiling UI and resource files, building Sphinx documentation, managing translations, deploying to your local QGIS plugin directory, and packaging for the QGIS Plugin Repository.

Supports **QGIS 3 and QGIS 4**, **Qt5 and Qt6**, and runs on **Linux, macOS, and Windows**.

---

## Features

- Compile `.ui` and `.qrc` files (auto-detects `pyuic5`/`pyuic6` and `rcc`)
- Deploy to your QGIS plugin directory for live testing
- Package into a `.zip` for upload to the Plugin Repository
- Build and clean Sphinx HTML documentation
- Compile translation files with `lrelease`
- Clean compiled and deployed files
- Validate your config file and environment

---

## Installation

```bash
pip install pb_tool
```

To upgrade:

```bash
pip install --upgrade pb_tool
```

pb_tool is also available as the shorter alias `pbt`:

```bash
pbt deploy
```

### Runtime dependencies

| Tool | Purpose |
|---|---|
| `pyuic5` or `pyuic6` | Compile `.ui` files to Python |
| `rcc` | Compile `.qrc` resource files |
| `lrelease` | Build `.qm` translation files from `.ts` sources |
| `zip` or `7z` | Package the plugin for upload |
| `sphinx` + `make` | Build HTML help documentation |

---

## Configuration

pb_tool requires a `pb_tool.cfg` file in your plugin's root directory. [Plugin Builder](https://plugins.qgis.org/plugins/pluginbuilder4/) generates this automatically. You can also create one by hand using the template below.

```ini
[plugin]
# Directory name used when deploying to the QGIS plugins folder
name: MyPlugin

# Override the deploy path (leave empty to use the QGIS default location)
plugin_path:

[files]
# Python source files to deploy
python_files: __init__.py my_plugin.py my_plugin_dialog.py

# Main dialog .ui file — loaded at runtime, not compiled
main_dialog: my_plugin_dialog_base.ui

# Additional .ui files to compile to Python
compiled_ui_files: settings_dialog.ui

# Qt resource files (.qrc) to compile
resource_files: resources.qrc

# Other files to include (e.g. metadata.txt, icon.png)
extras: metadata.txt icon.png

# Subdirectories to deploy alongside the plugin
extra_dirs: i18n

# Locales to build — .ts files must exist in the i18n/ directory
locales: en.ts fr.ts

[help]
# Sphinx build output directory
dir: help/build/html
# Directory name inside the deployed plugin
target: help
```

All paths are relative to the directory where you run pb_tool. The `name` value must match the folder name used in the QGIS plugins directory.

---

## Commands

Run `pb_tool --help` for the full command list. Commands support unique-prefix abbreviation — `pb_tool dep` is the same as `pb_tool deploy`.

---

### `deploy`

Compile files, build docs, and copy everything to the QGIS plugin directory.

```bash
pb_tool deploy [OPTIONS]
```

| Option | Description |
|---|---|
| `--config_file FILE` | Config file to use (default: `pb_tool.cfg`) |
| `-p, --plugin_path PATH` | Override the deploy destination |
| `-q, --quick` | Skip compiling and doc building; copy files only |
| `-y, --no-confirm` | Skip the confirmation prompt |

A full deploy will:

1. Remove the currently deployed version (`dclean`)
2. Compile all UI and resource files
3. Build Sphinx HTML documentation
4. Copy all declared files and directories to the plugin folder

Use `-q` for fast iteration when you only changed Python files.

**Example output:**

```
Deploying will:
    * Remove your currently deployed version
    * Compile the ui and resource files
    * Build the help docs
    * Copy everything to your ~/.local/share/QGIS/QGIS4/.../plugins/MyPlugin directory

Proceed? [y/N]: y
Removing plugin from ...
Compiling to make sure install is clean
Skipping resources.qrc (unchanged)
Building the help documentation
...
Copying __init__.py
Copying my_plugin.py
...
```

---

### `compile`

Compile `.ui` and `.qrc` files without deploying.

```bash
pb_tool compile [--config pb_tool.cfg]
```

- Detects `pyuic6` first, falls back to `pyuic5`
- Uses `rcc` for resource files; automatically rewrites `PySide6` imports to `qgis.PyQt`
- Skips files that have not changed since the last compile

---

### `doc`

Build Sphinx HTML documentation.

```bash
pb_tool doc
```

Runs `make html` inside the `help/` directory. Requires a Sphinx project set up there (Plugin Builder creates this automatically).

---

### `translate`

Compile `.ts` translation files to `.qm` using `lrelease`.

```bash
pb_tool translate [--config pb_tool.cfg]
```

Locales must be listed under `[files] > locales` in your config, and the `.ts` files must exist in the `i18n/` directory.

---

### `zip`

Package the deployed plugin into a `.zip` suitable for the QGIS Plugin Repository.

```bash
pb_tool zip [--config_file pb_tool.cfg] [-q]
```

By default triggers a full `dclean` + `deploy` first. Use `-q` to skip that step if the plugin is already deployed and current.

Requires `zip` or `7z` on your `PATH`.

---

### `validate`

Check `pb_tool.cfg` for required fields and report the environment status.

```bash
pb_tool validate [--config_file pb_tool.cfg]
```

Reports:

- Whether all mandatory config keys are present
- Resolved QGIS plugin directory path
- Python version in use
- Whether a suitable zip utility was found

---

### `clean`

Delete compiled UI and resource `.py` files.

```bash
pb_tool clean [--config pb_tool.cfg]
```

---

### `clean_docs`

Remove the built Sphinx HTML output.

```bash
pb_tool clean_docs
```

---

### `dclean`

Remove the deployed plugin from the QGIS plugins directory (prompts for confirmation).

```bash
pb_tool dclean [--config pb_tool.cfg]
```

---

### `list`

Print the contents of the config file.

```bash
pb_tool list [--config_file pb_tool.cfg]
```

---

### `update`

Check whether a newer version of pb_tool is available.

```bash
pb_tool update
```

---

### `version`

Print the current pb_tool version and exit.

```bash
pb_tool version
```

---

## Plugin directory detection

pb_tool automatically resolves the QGIS plugin directory in this order:

1. `~/.local/share/QGIS/QGIS4/profiles/default/python/plugins`
2. `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins`

If neither exists, the QGIS 4 path is used as the default. Override at any time with `deploy -p /your/path`.

---

## Typical workflow

```bash
# First deploy — full compile + copy
pb_tool deploy

# Iterate quickly on Python changes only
pb_tool deploy -q

# Validate your config and environment
pb_tool validate

# Package for the Plugin Repository
pb_tool zip

# Clean up compiled artefacts
pb_tool clean
```

---

## Troubleshooting

**`pyuic5`/`pyuic6` not found** — install Qt development tools. On Ubuntu/Debian: `sudo apt install pyqt5-dev-tools` or `sudo apt install pyqt6-dev-tools`. On Windows, install via OSGeo4W.

**`rcc` not found** — install the Qt resource compiler. On Ubuntu/Debian: `sudo apt install qtbase5-dev-tools` or `sudo apt install qt6-base-dev-tools`.

**Pygments uninstall error on pip install** — run:

```bash
pip install --ignore-installed Pygments pb_tool
```

**Windows setup** — see [A Quick Guide to Getting Started with PyQGIS on Windows](http://spatialgalaxy.net/2014/10/09/a-quick-guide-to-getting-started-with-pyqgis-on-windows/).

---

## Contributing

Issues and pull requests: <https://github.com/g-sherman/plugin_build_tool>

---

## License

GNU General Public License v2 or later (GPLv2+).
