# Changelog

## 0.0.20 (2024-03-24)

* Add "version" command to pi_base script.
* Add missing msg arg for journal.log() in Loggr.log().

## 0.0.19 (2024-03-24)

* Fix Loggr color_code= args

## 0.0.18 (2024-03-24)

* Breaking change: rename pi_base.lib.app_utils.get_conf class to GetConf
* Breaking change: remove get_conf/GetConf methods get_list() and get_subkey_list()
* Implement GetConf.get_sub() with arbitrary number of nested keys
* Add typings to GetConf methods get() and get_subkey()
* Add __setitem__() to GetConf - makes overrides of conf files possible
* Change pi_base.lib.app_utls.AtDict class to lint cleanly
* Add pi_base.lib.app_utils._fix_aiohttp() to fix stray RuntimeError from aiohttp v 3.9 on Windows (supposedly fixed by aiohttp>=v4.0, but no versions available yet)
* Add run_maybe_async() and run_async() helpers to pi_base.lib.app_utils
* Move translate_config_paths() from pi_base.lib.remoteiot to pi_base.lib.app_utils
* Add file presence checks to pi_base/lib/manager.py
* Change pi_base.lib.loggr.Loggr class to be subclass of logging.Logger, adjust method signatures
* Clean rewrite of strftimedelta() in pi_base.lib.app_utils
* Add pi_base.lib.db_file.DbFile generic database file service, with GoogleDrive and local file backend

## 0.0.17 (2024-03-20)

* Bump version in common_requirements.txt

## 0.0.16 (2024-03-20)

* Fix missing arg to _get_developer_setup() in modpath.py.

## 0.0.15 (2024-03-20)

* Fix INST_REMOTEIOT not working in install.sh.

## 0.0.14 (2024-03-19)

* Enable remote control during install.sh.
* Show more information in install.sh/common_install.sh.
* Add INST_DEBUG setting and -D/--debug parameter to install.sh/common_install.sh.

## 0.0.13 (2024-03-19)

* Fix broken Audio sink logic for HDMI name in raspi-config.

## 0.0.12 (2024-03-18)

* Add "site" and "device" commands to pi_base CLI.
* Fix DeploySite issues.

## 0.0.11 (2024-03-18)

* Fix common_install.sh failing to change RPI networking type (raspi-config dropped do_netconfig())
* More typings

## 0.0.10 (2024-03-15)

* Fix modpath on RPI.

## 0.0.9 (2024-03-15)

* Fix modpath on Windows.

## 0.0.8 (2024-03-15)

* Bugfixes in pi_base/modpath.py.

## 0.0.7 (2024-03-14)

* Redo heuristics logic in pi_base/modpath.py.

## 0.0.6 (2024-03-14)

* Bump version in pi_base/common/common_requirements.txt.

## 0.0.5 (2024-03-14)

* Fix bugs left from move to package.

## 0.0.4 (2024-03-05)

* Add empty section [zest.releaser] to .pypirc

* Add zest-releaser dependency for tox:docs

* Remove setuptools_scm (not using git-based version)

* Move zest-releaser settings to pyproject.toml

## 0.0.3 (2024-03-05)

* Pull version from pi_base/_version.py into pyproject.toml

* Add missing EXAMPLE files

## 0.0.2 (2024-03-04)

* Set up PyPI 1st time registration

## 0.0.1 (2024-03-04)

* Development and fixes of the toolchain

## 0.0.0 (2024-03-04)

* First tagged version
