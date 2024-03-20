#!/usr/bin/env python3

"""Paths resolver.

This module:

1. Figures out the environment it runs on and sets `running_on`
2. Reads "develop.txt" file from the app directory (uses to set some of the paths)
3. Sets all exported constants for the environment and per "develop.txt" file
4. Adds to sys.path (so python import will work):

   - app_shared_lib_dir
   - Any additional paths defined in "develop.txt" file

It also has some utility functions helping to understand the environment it works in.

Exports:
- app_dir             (str): Location of the app main script and app data files.
- app_conf_dir        (str): Location of the app configuration file app_conf.yaml (for dev: it is generated by `pi_base make`)
- app_shared_lib_dir  (str): Location of lib (common modules from app_workspace/lib shared by all app projects in the app workspace, on the target location of all copied modules)
- testscript_dir      (str): Location of tester script .csv files
- results_dir         (str): Location where to save result files
- running_on          (str): Detected environment, one of ['target', 'sources', 'pibase_sources_in_app_workspace', 'pibase_sources', 'build']
- workspace_dir       (str): Location of package workspace (for dev)
- module_dirname      (str): Location of this module / script
- site_id             (str): What site ID to use (for dev)
- project             (str): What project name to use (for dev)

Functions:
- is_raspberrypi()
- is_posix()
- is_mac()
- is_win()
- get_app_workspace_dir() -> (str): CWD (current working directory)
- get_script_dir()

in IDE

pi_base package source
(legacy app source was co-located with pi_base before it became a package):

```
{workspace}/       | repo folder
  + blank/         | pi-base project example
  + template_blank/| pi-base project template # TODO: (when needed) Implement
  + projectN/      | user projects
  + pi_base/       | pi-base stuff
    + common/      | #TODO: (now) maybe better name, or reorg the pieces differently
    + lib/         | pi-base modules
    + scripts/     | pi-base helper scripts #TODO: (now) dissolve into other places
```

Package customer repo:

```
{app_workspace}/   | app repo folder
  + projectN/      | user projects
  + lib/           | place for user common modules, shared between projects
```

in build and on target:

```
{workspace}/build/{SITE}/{project}/    |
+ common_install.sh                    |
+ common_requirements.txt              |
+ install.sh                           |
+ requirements.txt                     |
+ pkg/                                 | (and `/` on target)
  + /home/pi/                          |
     + app/                            |
     + lib/                            |
     + app_conf.yaml                   |
```
"""

# TODO: (when needed) Implement dev vs. prod, instead of posix vs. non-posix.

from __future__ import annotations

import inspect
import os
import sys

DEBUG = False
DEBUG = True

APP_DIRNAME = "app"
PI_BASE_DIR = "/home/pi"
PI_HOSTNAME = "RPI"


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


def get_top_module() -> tuple[str, str, str]:
    # import __main__ as m  # pylint: disable=import-outside-toplevel
    m = sys.modules["__main__"]
    top_filename = (m.__file__ if hasattr(m, "__file__") else None) or sys.argv[0]
    top_module_path = os.path.dirname(os.path.realpath(top_filename))
    top_module_name = os.path.splitext(os.path.basename(top_filename))[0]
    return top_filename, top_module_path, top_module_name


def get_script_dir(file_or_object_or_func: str | inspect._SourceObjectType, follow_symlinks: bool = True) -> str:
    if not file_or_object_or_func:
        raise ValueError("Please provide file_or_object_or_func argument (can be __file__).")
    if getattr(sys, "frozen", False):  # py2exe, PyInstaller, cx_Freeze
        path = os.path.realpath(sys.executable)
    elif isinstance(file_or_object_or_func, str):
        path = file_or_object_or_func
    else:
        path = inspect.getabsfile(file_or_object_or_func)
    if follow_symlinks:
        path = os.path.realpath(path)
    return os.path.dirname(path)


def _get_developer_setup(filename: str, default_site_id: str, default_project: str, default_hostname: str) -> tuple[bool, str, str, str, list[str]]:
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
    has_file = False
    if os.path.isfile(filename):
        has_file = False
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
            has_file = True
            default_site_id, default_project = my_site_id, my_project
            if rest:
                default_hostname, *rest = rest
            if DEBUG:
                print(f'DEBUG Read develop file "{filename}", site_id={default_site_id}, project={default_project}')
        # else: Ignore the data if either of the 2 fields is missing
    return has_file, default_site_id, default_project, default_hostname, rest


def print_info():
    my_vars = [
        "__file__",
        "__name__",
        "running_on",
        "workspace_dir",
        "module_path",
        "module_dirname",
        "module_is_from_editable",
        "module_is_from_package",
        "app_filename",
        "app_module_path",
        "app_module_dir",
        "app_module_name",
        "is_pibase_exe",
        "is_pibase_script",
        "in_pibase_source",
        "project_dir",
        "caller_dir",
        "caller_has_develop_file",
        "_app_workspace_path",
        "pibase_shared_lib_dir",
        "app_dir",
        "app_conf_dir",
        "app_shared_lib_dir",
        "testscript_dir",
        "results_dir",
    ]

    def format_var(var: str) -> str:
        try:
            val = globals()[var]
            if isinstance(val, str):
                val = f'"{val}"'
        except:
            val = "<undefined>"
        return f"  {var}={val}"

    lines = [format_var(var) for var in my_vars]
    vars_str = "\n  ".join(lines)
    print(f"DEBUG modpath.py\n  {vars_str}\n  is_raspberrypi={is_raspberrypi()}\n  is_posix={is_posix()}\n  is_mac={is_mac()}\n  is_win={is_win()}")


# From modpath.py we can distinguish only these options:
# 1. Debugging pi_base modules in pi_base {workspace}
# 2. If it is ran from a package by a client of pi_base
# When:                      __file__             # {workspace}/pi_base/modpath.py # {site-packages}/pi_base/modpath.py # {dist-packages}/pi_base/modpath.py
module_path = get_script_dir(__file__)  #         # {workspace}/pi_base            # {site-packages}/pi_base            # {dist-packages}/pi_base
module_dirname = os.path.basename(module_path)  # # pi_base                        # pi_base                            # pi_base
workspace_dir = os.path.dirname(module_path)  #   # {workspace}                    # {site-packages}                    # {dist-packages}
module_is_from_editable = os.path.isfile(os.path.join(module_path, "is_editable.md"))
# module_is_from_package = module_is_from_editable or "/dist-packages/" in module_path or "/site-packages/" in module_path or "\\site-packages\\" in module_path
module_is_from_package = module_is_from_editable or workspace_dir.endswith(("/dist-packages", "/site-packages", "\\site-packages"))

# From top-level module we can infer:
#                                           app_filename,                app_module_path, app_module_dir, app_module_name
# 1. sources of app                                                                     , ==app_module_name)
# 2. ?sources of {app_workspace}/lib                                                    , "lib"
# 3. ?sources of {workspace}/lib                                                        , "lib"
# 4. ?sources of {workspace}/pi_base/lib                                                , "lib"
# 5. pi_base script with pi_base editable  "{venv}\{Scripts|bin}\pi[-_]base{.exe}\__main__.py",
# 6. pi_base script from package on target "/usr/local/bin/pi_base",    "/usr/local/bin", "bin",          "pi_base"|"pi-base"
app_filename, app_module_path, app_module_name = get_top_module()
app_module_dir = os.path.basename(app_module_path)
is_pibase_exe = app_module_name in ["pi_base", "pi-base"]
is_pibase_script = "__main__" in app_filename
in_pibase_source = is_pibase_script or app_module_path.startswith(workspace_dir)  # This is surefire way to know that something run from pi_base {workspace}.

# `caller_dir` is the only way to learn where {app_workspace} is when running pi_base script with editable pi_base.
caller_dir = os.path.realpath(os.getcwd())
caller_has_develop_file = (caller_dir != workspace_dir) and os.path.isfile(os.path.realpath(os.path.join(caller_dir, "develop.txt")))
# caller_has_develop_file keep False if caller is pi_base {workspace}. develop_filename will still be found in workspace_dir.

# Now from all the above, do some heuristics to arrive to all the answers.
running_on: str = "<unknown>"
has_develop_file, site_id, project, additional_python_paths = False, "", "", []
_app_workspace_path = ""
# TODO: (soon) Suspecting `pibase_shared_lib_dir` is not needed, as our package is installed, and lib modules are imported by relative import here and by submodule import in the client.
pibase_shared_lib_dir = os.path.join(module_path, "lib")
additional_python_paths = []
hostname = PI_HOSTNAME
if not module_is_from_package or in_pibase_source:
    DEBUG = True
    running_on = (
        "pibase_sources_in_app_workspace" if caller_has_develop_file else "pibase_sources"
    )  # This is either a legacy way of running pi_base, or running pi_base script from editable pi_base package.

    # In pi_base, we currently have one app - `blank`
    _app_workspace_path = caller_dir if caller_has_develop_file else workspace_dir

    # Detect developer setup
    # If present, 'develop.txt' file (see 'SAMPLE_develop.txt') defines which app is running and choose where to find app_conf.yaml file
    develop_filename = os.path.realpath(os.path.join(_app_workspace_path, "develop.txt"))
    has_develop_file, site_id, project, hostname, additional_python_paths = _get_developer_setup(develop_filename, "BASE", "blank", PI_HOSTNAME)
    additional_python_paths = [os.path.realpath(path) for path in additional_python_paths]
    project_dir = os.path.join(_app_workspace_path, f"build/{site_id}/{project}/pkg{PI_BASE_DIR}")

    app_dir = os.path.join(_app_workspace_path, project)
    app_conf_dir = project_dir
    app_shared_lib_dir = os.path.join(_app_workspace_path, "lib")
    testscript_dir = os.path.join(_app_workspace_path, "testscripts")
    results_dir: str = os.path.join(_app_workspace_path, "testresults")

elif app_module_dir == APP_DIRNAME and not is_raspberrypi():
    # Running from build but not on target
    DEBUG = True
    running_on = "build"

    _app_workspace_path = None  # There's no good reason to try to figure out app_workspace_path for running on "build". If anyone asks, cause an exception.
    raise ValueError(f'Running on "{running_on}" is not supported.')

elif app_module_dir == APP_DIRNAME:
    # Defaults for 'target'
    running_on = "target"

    _app_workspace_path = None  # There's no app_workspace_path when running on "target". If anyone asks, cause an exception.

    app_dir = os.path.join(PI_BASE_DIR, APP_DIRNAME)
    app_conf_dir = PI_BASE_DIR
    app_shared_lib_dir = os.path.join(PI_BASE_DIR, "lib")
    testscript_dir = app_shared_lib_dir  # path where to look for test scripts
    results_dir = PI_BASE_DIR + "/testresults"

# elif app_module_dir != APP_DIRNAME:  # has_develop_file:  # module_is_from_package and not in_pibase_source

elif app_module_dir in [app_module_name, "lib"]:
    # Running app from repo sources or dev in IDE, with "develop.txt" file in {app_workspace_path}
    DEBUG = True
    # Running one of {app_workspace}/<project>/<project>.py or {app_workspace}/lib/*.py
    running_on: str = "sources"

    _app_workspace_path = os.path.dirname(app_module_path)

    # Detect developer setup
    # If present, 'develop.txt' file (see 'SAMPLE_develop.txt') defines which app is running and choose where to find app_conf.yaml file
    develop_filename = os.path.realpath(os.path.join(_app_workspace_path, "develop.txt"))
    has_develop_file, site_id, project, hostname, additional_python_paths = _get_developer_setup(develop_filename, "BASE", "blank", PI_HOSTNAME)
    additional_python_paths = [os.path.realpath(path) for path in additional_python_paths]
    project_dir = os.path.join(_app_workspace_path, f"build/{site_id}/{project}/pkg{PI_BASE_DIR}")

    app_dir = os.path.join(_app_workspace_path, project)
    app_conf_dir = project_dir
    app_shared_lib_dir = os.path.join(_app_workspace_path, "lib")
    testscript_dir = os.path.join(_app_workspace_path, "testscripts")
    results_dir: str = os.path.join(_app_workspace_path, "testresults")
elif is_pibase_exe and is_raspberrypi():
    # in command "pi_base ..." when pi_base is installed as a package, running on target
    running_on = "target"

    _app_workspace_path = None  # There's no app_workspace_path when running on "target". If anyone asks, cause an exception.

    app_dir = os.path.join(PI_BASE_DIR, APP_DIRNAME)
    app_conf_dir = PI_BASE_DIR
    app_shared_lib_dir = os.path.join(PI_BASE_DIR, "lib")
    testscript_dir = app_shared_lib_dir  # path where to look for test scripts
    results_dir = PI_BASE_DIR + "/testresults"

# elif is_pibase_exe and not is_raspberrypi():
#    pass
else:
    # Unknown situation
    app_dir = caller_dir
    app_conf_dir = caller_dir
    app_shared_lib_dir = caller_dir
    testscript_dir = caller_dir
    results_dir: str = caller_dir

    if not DEBUG:
        print_info()
    # raise RuntimeError("Unknown situation, cannot determine what is running and how to setup import paths and all locations.")
    print("pi_base.modpath: Cannot determine running environment and how to setup import paths and all locations.", file=sys.stderr)

if DEBUG:
    print_info()


def get_app_workspace_dir() -> str:
    if _app_workspace_path is None:
        raise ValueError(f'Call to get_app_workspace_dir() is unexpected, app_workspace does not exist when running on "{running_on}".')
    return _app_workspace_path


# Python paths where to find imported modules:
my_paths = [app_shared_lib_dir, pibase_shared_lib_dir]
my_paths += additional_python_paths
for my_path in reversed(my_paths):
    if my_path in sys.path:
        continue
    sys.path.insert(0, my_path)
    if DEBUG:
        print(f'DEBUG: sys.path appended with path "{my_path}"')
