#!/usr/bin/env python3

"""This module figures out paths for all other modules and adds them to sys.path, so python import will work.

It also has some utility functions helping to understand the environment it works in.

Exports:
    app_dir        (str): Location of the app script files and its configuration file
    modules_dir    (str): Location of installed modules
    pibase_lib_dir (str): Location of pi_base.lib
    running_on     (str): Detected environment
    testscript_dir (str): Location of tester scripts files
    results_dir    (str): Location to write results files to
    base_path      (str): Location of workspace (for dev) or the app user home folder (on target)
    script_dir     (str): Location of this script
    caller_dir     (str): CWD (current working directory)
    site_id        (str): What site ID to use (for dev)
    project        (str): What project name to use (for dev)

Functions:
    is_raspberrypi()
    is_posix()
    is_mac()
    is_win()
    get_workspace_dir()
    get_script_dir()

"""

from __future__ import annotations

import inspect
import os
import sys

DEBUG = False
# DEBUG = True

# TODO: (when needed) Implement dev vs. prod, instead of posix vs. non-posix.
# General idea:
#  - define few global constants with directory locations:
#    | app_dir        | path where to look for app_conf.yaml #TODO: (now) Rename to app_conf_dir to reflect it's real contents and intended use
#    | modules_dir    | path where to look for modules
#    | pibase_lib_dir | path where to look for pi-base modules
#    | running_on     | one of ['target', 'sources', 'build']
#    | testscript_dir | path where to look for test script .csv files
#    | results_dir    | path where to save result files
# - detect running_on condition and assign constants for
# - adds to sys.path (so import will work):
#   - modules_dir
#   - pibase_lib_dir (pi_base/lib/) folder for 'sources' and 'build' (?)
#

# in IDE:
# {workspace}/  | repo folder
# + blank/      | pi-base project template
# + projectN/   | user projects
# + modules/    | place for user common modules, shared between projects
# + pi_base/    | pi-base stuff
#   + common/   | #TODO: (now) maybe better name, or reorg the pieces differently
#   + lib/      | pi-base modules
#   + scripts/  | pi-base helper scripts #TODO: (now) dissolve into other places
#

# in build and on target:
# {workspace}/build/{SITE}/{project}/    |
# + common_install.sh                    |
# + common_requirements.txt              |
# + install.sh                           |
# + requirements.txt                     |
# + pkg/                                 | (and `/` on target)
#   + /home/pi/                          |
#     + app/                             |
#     + modules/                         |
#     + app_conf.yaml                    |


def is_raspberrypi() -> bool:
    try:
        with open("/sys/firmware/devicetree/base/model", encoding="utf-8") as m:
            if "raspberry pi" in m.read().lower():
                return True
    except Exception:  # noqa: S110
        pass
    return False


def is_posix() -> bool:
    return os.name == "posix"


def is_mac() -> bool:
    return sys.platform == "darwin"


def is_win() -> bool:
    return os.name == "nt"


# def get_workspace_dir(file_or_object_or_func=None):
#     if not file_or_object_or_func:
#         raise ValueError("Please provide file_or_object_or_func argument (can be __file__).")
def get_workspace_dir() -> str:
    return os.getcwd()


def get_script_dir(file_or_object_or_func: str | inspect._SourceObjectType, follow_symlinks: bool = True) -> str:
    if not file_or_object_or_func:
        raise ValueError("Please provide file_or_object_or_func argument (can be __file__).")
    if getattr(sys, "frozen", False):  # py2exe, PyInstaller, cx_Freeze
        path = os.path.abspath(sys.executable)
    elif isinstance(file_or_object_or_func, str):
        path = file_or_object_or_func
    else:
        path = inspect.getabsfile(file_or_object_or_func)
    if follow_symlinks:
        path = os.path.realpath(path)
    return os.path.dirname(path)


def get_developer_setup(filename: str, default_site_id: str, default_project: str) -> tuple[str, str, list[str]]:
    """Read a developer config file.

    Lines starting with '#' are comments and are ignored.

    A last not-comment line with 2 or more strings separated by commas will be used to fill in returned site_id and project, and the rest.

    The rest is a list of paths to add to sys.path.

    Args:
        filename (str): File to read
        default_site_id (str): Default value for site_id
        default_project (str): Default value for project

    Returns:
        tuple[str, str, list[str]]: site_id, project, rest
    """
    rest = []
    if os.path.isfile(filename):
        my_site_id, my_project, line = None, None, None
        try:
            with open(filename, encoding="utf-8") as fd:
                for line_in in fd:
                    line = line_in.strip()
                    if not line or line.startswith("#"):
                        continue
                    my_site_id, my_project, *rest = (part.strip() for part in line.split(","))
                    # Keep going, so we will use the last line and ignore all the others
        except Exception as err:
            print(f'Error "{err}" reading develop file "{filename}"' + f', parsing line "{line}"' if line else "", file=sys.stderr)
        if my_site_id and my_project:
            default_site_id, default_project = my_site_id, my_project
            if DEBUG:
                print(f'DEBUG Read develop file "{filename}", site_id={default_site_id}, project={default_project}')
        # else: Ignore the data if either of the 2 fields is missing
    return default_site_id, default_project, rest


# When:                                     __file__     # {workspace}/pi_base/modpath.py # /home/pi/modules/modpath.py # /home/pi/app/modpath.py  # {site_packages}/pi_base-X.X.X/pi_base/modpath.py
file_path = os.path.dirname(os.path.realpath(__file__))  # {workspace}/pi_base            # /home/pi/modules            # /home/pi/app             # {site_packages}/pi_base-X.X.X/pi_base
file_dir = os.path.basename(file_path)  #                # pi_base                        # pi_base                     # app                      # pi_base
base_path = os.path.dirname(file_path)  #                # {workspace}                    # /home/pi                    # /home/pi                 # {site_packages}/pi_base-X.X.X
script_dir = get_script_dir(__file__)  #                 # {workspace}/pi_base            # /home/pi/modules            # /home/pi/app             # {site_packages}/pi_base-X.X.X/pi_base
caller_dir = get_workspace_dir()

# Detect developer setup

# If present, 'develop.txt' file (see 'develop.SAMPLE.txt') defines which app is running and choose where to find .yaml file
develop_filename = os.path.realpath(os.path.join(base_path, "develop.txt"))
site_id, project, additional_paths = get_developer_setup(develop_filename, "BASE", "blank")
project_dir = os.path.join(base_path, f"build/{site_id}/{project}/pkg/home/pi")

if file_dir == "pi_base":
    # Running sources or dev in IDE
    DEBUG = True
    running_on: str = "sources"
    app_dir = project_dir
    modules_dir = os.path.join(base_path, "common")
    pibase_lib_dir = os.path.join(base_path, "pi_base", "lib")
    scripts_dir = os.path.join(project_dir, "modules")  # scripts is not copied to the Pi, but build modules directory has required files from scripts/
    testscript_dir = os.path.join(os.path.dirname(base_path), "scripts")
    results_dir: str = base_path
elif file_dir == "app" and not is_raspberrypi():
    # Running build but not on target
    DEBUG = True
    running_on = "build"
    project_dir = base_path
    app_dir = project_dir
    modules_dir = os.path.join(base_path, "modules")
    pibase_lib_dir = os.path.join(base_path, "modules")
    scripts_dir = modules_dir  # scripts is not copied to the Pi, but build modules directory has required files from scripts/
    testscript_dir = modules_dir
    results_dir = ""
else:
    # Defaults for 'target'
    running_on = "target"
    app_dir = "/home/pi"  # path where to look for app_conf.yaml
    modules_dir = "/home/pi/modules"  # path where to look for modules (from pi_base/lib, only when using build with legacy pi_base source code)
    pibase_lib_dir = "/home/pi/modules"  # path where to look for modules
    scripts_dir = modules_dir  # scripts is not copied to the Pi, but build directory has required files from scripts/
    testscript_dir = modules_dir  # path where to look for modules
    results_dir = app_dir

if DEBUG:
    my_vars = [
        "__file__",
        "__name__",
        "running_on",
        "base_path",
        "file_path",
        "file_dir",
        "project_dir",
        "script_dir",
        "caller_dir",
        "app_dir",
        "modules_dir",
        "pibase_lib_dir",
        "scripts_dir",
        "testscript_dir",
        "results_dir",
    ]

    def format_var(var: str) -> str:
        val = globals()[var]
        if isinstance(val, str):
            val = f'"{val}"'
        return f"  {var}={val}"

    lines = [format_var(var) for var in my_vars]
    vars_str = "\n  ".join(lines)
    print(f"DEBUG modpath.py\n  {vars_str}\n  is_raspberrypi={is_raspberrypi()}\n  is_posix={is_posix()}\n  is_mac={is_mac()}\n  is_win={is_win()}")

# Path where to look for modules:
my_paths = [modules_dir]
if running_on != "target":
    # For development, add relative paths:
    my_paths += [scripts_dir, pibase_lib_dir]
my_paths += additional_paths
for my_path in my_paths:
    if my_path in sys.path:
        continue
    sys.path.append(my_path)
    if DEBUG:
        print(f'DEBUG: sys.path appended with path "{my_path}"')
