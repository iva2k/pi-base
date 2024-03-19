# Changelog

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
