#!/usr/bin/env python3

"""This module figures out paths for all other modules and adds them to sys.path, so python import will work.

See a proxy modpath.py, which supplements this module to bootstrap any top-level module in environment with modules spread in different locations.

Return:
    app_dir: str
    modules_dir: str
    pibase_lib_dir: str
    running_on: str
"""

import inspect
import os
import sys


# TODO: (when needed) Implement dev vs. prod, instead of posix vs. non-posix.
# General idea:
#  - define few global constants with directory locations:
#    | app_dir        | path where to look for app_conf.yaml #TODO: (now) Rename to app_conf_dir to reflect it's real contents and intended use
#    | modules_dir    | path where to look for modules
#    | pibase_lib_dir | path where to look for pi-base modules
#    | running_on     | one of ['target', 'sources', 'build']
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


debug = False
# debug = True


def is_raspberrypi():
    try:
        with open("/sys/firmware/devicetree/base/model", encoding="utf-8") as m:
            if "raspberry pi" in m.read().lower():
                return True
    except Exception:  # noqa: S110
        pass
    return False


def is_posix():
    return os.name == "posix"


def is_mac():
    return sys.platform == "darwin"


def is_win():
    return os.name == "nt"


# def get_workspace_dir(file_or_object_or_func=None):
#     if not file_or_object_or_func:
#         raise ValueError("Please provide file_or_object_or_func argument (can be __file__).")
def get_workspace_dir() -> str:
    return os.getcwd()


def get_script_dir(file_or_object_or_func, follow_symlinks=True):
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


def get_developer_setup(filename, default_site_id, default_project):
    if os.path.isfile(filename):
        my_site_id, my_project, line = None, None, None
        try:
            with open(filename, encoding="utf-8") as fd:
                for line_in in fd:
                    line = line_in.strip()
                    if not line or line.startswith("#"):
                        continue
                    my_site_id, my_project = line.split(",")[:2]
        except Exception as err:
            print(f'Error "{err}" reading develop file "{filename}"' + f', parsing line "{line}"' if line else "")
        if my_site_id and my_project:
            default_site_id, default_project = my_site_id.strip(), my_project.strip()
            print(f'DEBUG Read develop file "{filename}", site_id={default_site_id}, project={default_project}')
    return default_site_id, default_project


# When:                                     __file__     # {workspace}/pi_base/modpath.py # /home/pi/pi_base/ # /home/pi/app/modpath.py  #
file_path = os.path.dirname(os.path.realpath(__file__))  # {workspace}/pi_base            # /home/pi/pi_base/ # /home/pi/app             #
file_dir = os.path.basename(file_path)  # pi_base                        # /home/pi/pi_base/ # app                      #
base_path = os.path.dirname(file_path)  # {workspace}                    # /home/pi/pi_base/ # /home/pi                 #
script_dir = get_script_dir(__file__)
caller_dir = get_workspace_dir()

# Detect developer setup

# If present, 'develop.txt' file (see 'develop.SAMPLE.txt') defines which app is running and choose where to find .yaml file
develop_filename = os.path.realpath(os.path.join(base_path, "develop.txt"))
site_id, project = get_developer_setup(develop_filename, "BASE", "blank")
project_dir = os.path.join(base_path, f"build/{site_id}/{project}/pkg/home/pi")

if file_dir == "pi_base":
    # Running sources or dev in IDE
    debug = True
    running_on = "sources"
    app_dir = project_dir
    modules_dir = os.path.join(base_path, "common")
    pibase_lib_dir = os.path.join(base_path, "pi_base", "lib")
    scripts_dir = os.path.join(project_dir, "modules")  # scripts is not copied to the Pi, but build modules directory has required files from scripts/
elif file_dir == "app" and not is_raspberrypi():
    # Running build but not on target
    debug = True
    running_on = "build"
    project_dir = base_path
    app_dir = project_dir
    modules_dir = os.path.join(base_path, "modules")
    pibase_lib_dir = os.path.join(base_path, "modules")
    scripts_dir = modules_dir  # scripts is not copied to the Pi, but build modules directory has required files from scripts/
else:
    # Defaults for 'target'
    running_on = "target"
    app_dir = "/home/pi"  # path where to look for app_conf.yaml
    modules_dir = "/home/pi/modules"  # path where to look for modules
    pibase_lib_dir = "/home/pi/modules"  # path where to look for modules
    scripts_dir = modules_dir  # scripts is not copied to the Pi, but build directory has required files from scripts/

if debug:
    my_vars = ["__file__", "__name__", "running_on", "base_path", "file_path", "file_dir", "project_dir", "script_dir", "caller_dir", "app_dir", "modules_dir", "pibase_lib_dir", "scripts_dir"]

    def format_var(var):
        val = globals()[var]
        if isinstance(val, str):
            val = f'"{val}"'
        return f"  var={val}"

    lines = [format_var(var) for var in my_vars]
    print(f'DEBUG modpath.py\n{"n".join(lines)}"\n  is_raspberrypi={is_raspberrypi()}\n  is_posix={is_posix()}\n  is_mac={is_mac()}\n  is_win={is_win()}')

# Path where to look for modules:
sys.path.append(modules_dir)
if debug:
    print(f'DEBUG: appended path modules_dir "{modules_dir}"')

# For development, add relative paths:
if running_on != "target":
    sys.path.append(scripts_dir)
    if debug:
        print(f'DEBUG: appended path scripts_dir "{scripts_dir}"')
    sys.path.append(pibase_lib_dir)
    if debug:
        print(f'DEBUG: appended path pibase_lib_dir "{pibase_lib_dir}"')
