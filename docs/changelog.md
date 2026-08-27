# Changelog
## [3.5.3] - 2026-08-28

### Added
- `--no-docs` flag for `pb_tool zip` to skip building/copying the Sphinx help

### Fixed
- Ignore whitespace around keys when patching `metadata.txt`

### Changed
- Patch `metadata.txt` with configparser (`=`/`:` separators) and
  edit it in place via ConfigUpdater, so comments, blank lines, and key order
  in the packaged file are preserved and adds the `configupdater` dependency

## [3.5.2] - 2026-08-07
- Only warn about missing pyuic/rcc when there are files to compile

## [3.5.1] - 2026-07-18

### Added
- fallback to fix when deploy crashing with NoSectionError when pb_tool.cfg had no [help] section. Read help dir/target with fallbacks and skip the copy step when they are absent
- pass --no-docs through to install_files so it also skips copying help (including in --quick mode), and tolerate a missing extra_dirs option with a fallback.
- Added tests using a legacy-style config without a [help] section.


## [3.5.0] - 2026-07-17

### Added
- `--release-version` option for `pb_tool zip`: stamps `version`, `commitSha1`, `commitNumber`, and `dateTime` into the deployed `metadata.txt` before creating the archive. Pre-release version strings (containing `rc`, `alpha`, `beta`, or `dev`) also set `experimental=True`. Fields that don't already exist in `metadata.txt` are appended automatically. The source `metadata.txt` is never modified.
- `-p/--plugin_path` option for `pb_tool zip` and `pb_tool dclean`. All deploy-related commands now resolve the plugin directory the same way: `-p` option > `plugin_path` in `pb_tool.cfg` > default QGIS profile directory (#41)

### Fixed
- Fatal errors now exit with a non-zero code so scripts and CI can detect failures (#42): missing config file (`deploy`, `zip`, `list`), no zip/7z utility found (`zip`), missing plugin `name` in the config (`zip`), invalid config (`validate`), and missing templates (`create`)
- `zip` and `dclean` no longer ignore a custom plugin path and zip the wrong (often empty) directory (#41)
- `zip` restores the original working directory after packaging
- `update` no longer crashes when the installed version cannot be determined

---

## [3.4.0] - 2026-05-24

### Added
- New `dockwidget` plugin type: `pb_tool create --type dockwidget` generates a toolbar button plugin with a dock widget panel
- `--title` option to `pb_tool create` for the human-readable plugin name shown in QGIS menus (distinct from the Python class name)
- `icon.png` is now copied into the generated plugin directory automatically

### Changed
- Generated plugin templates updated to match [QGIS Plugin Builder](https://github.com/jonah-sullivan/Qgis-Plugin-Builder):
    - **Dialog plugins:** replaced `QSettings`/`qVersion`/own toolbar with `QgsSettings`/`QLocale`/`iface.addToolBarIcon`; icon loaded from the filesystem instead of a Qt resource alias; dialog creation deferred to first `run()` call (`first_start` pattern)
    - **Processing plugins:** main class renamed to `*Plugin` and no longer takes `iface`; added `__author__`/`__date__`/`__copyright__`/`__revision__` module attributes; algorithm uses `self.tr()`, `QgsFeatureSink.FastInsert`, and correct `100.0 / featureCount` progress tracking; provider gains `__init__`, `unload`, `icon()`, and `longName()`
    - **`pb_tool.cfg`:** updated with `plugin_path:` field, `LICENSE` in extras, and correct `python_files`/`main_dialog` values populated per plugin type
- `resources.qrc` is no longer generated (Qt resource system not needed now that the icon uses a filesystem path)
- `sphinx` moved to optional `docs` dependency group

### Fixed
- Dialog template uses `exec()` instead of deprecated `exec_()` for Qt6/QGIS 4 compatibility

### Removed
- `test_plugin` directory removed from the repository; tests now generate a temporary plugin in an isolated filesystem

---

## [3.3.1] - 2026-04-30

### Fixed
- Windows compatibility issues in path handling
- `get_plugin_directory()` now used consistently in the `validate` command
- `urlopen` replaced with `http.client` to fix Bandit B310 security warning
- `xmlrpc.client` replaced with `urllib` and `defusedxml` in `plugin_upload.py`
- `__pycache__` directories and cache files excluded from `zip` output

---

## [3.3.0] - 2026-04-29

### Added
- MkDocs documentation site
- GitHub Actions publishing workflow
- Badges in README

### Changed
- Version now read from package metadata via `importlib.metadata` instead of being hardcoded
- `translate` command updated for Qt6

### Fixed
- Windows compatibility and failing tests
- Debug print statements removed from `translate` command
- PyQt5 import paths updated

---

## [3.2.0] - 2026-04-25

### Added
- Processing plugin skeleton template and `pb_tool create` command
- `--no-docs` flag to skip Sphinx build during deploy
- `excluded_files` option to filter files from deployment
- Plugin directory detection for QGIS 3 and 4 profiles
- Qt5/Qt6 fallback for resource compilation

### Fixed
- `TemplatePyFiles` not substituted in generated `pb_tool.cfg`
- Sphinx build failure on OSGeo4W
- `pyrcc5` compile failure on Windows/OSGeo4W
- Deploy failure for UI files in subdirectories
- Create full plugin directory path on fresh profiles (`os.makedirs` with `exist_ok=True`)
- Exit with non-zero error code when deployment fails

### Changed
- Ported from Python 2 to Python 3
- Updated for QGIS 4 and Qt6
- Modernised packaging (`pyproject.toml`)
- QGIS 3/4 plugin directory paths updated

---

## [1.9.1] - 2015-10-13

Last release of the original Gary Sherman version.
