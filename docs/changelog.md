# Changelog

## [Unreleased]

### Added
- `--release-version` option for `pb_tool zip`: stamps `version`, `commitSha1`, `commitNumber`, and `dateTime` into the deployed `metadata.txt` before creating the archive. Pre-release version strings (containing `rc`, `alpha`, `beta`, or `dev`) also set `experimental=True`. Fields that don't already exist in `metadata.txt` are appended automatically. The source `metadata.txt` is never modified.

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
