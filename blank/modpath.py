#!/usr/bin/env python3

"""This is a proxy for the real modpath.py, which can be located in other folder (that python import won't find).

Raises:
    ImportError: When modpath module cannot be found.

Side Effects:
    Imports modpath module from wherever it is.
"""

import importlib.util
import os
import sys


# BEGIN These to be overriden when full modpath is imported
def get_script_dir(file_or_object_or_func, follow_symlinks=True):
    raise ImportError("Cannot load full modpath")


app_dir = None
# END These to be overriden when full modpath is imported


def import_module_from_locations(module_name, locations):
    for location in locations:
        try:
            module_path = os.path.join(location, f"{module_name}.py")
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                # Register module and its variables (as `import module_name` would do)
                globals().update(module.__dict__)
                sys.modules[module_name] = module
                return module
        except FileNotFoundError as err:  # noqa: PERF203
            continue
    raise ImportError(f'Module "{module_name}" not found in any of the specified locations')


def find_modpath():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # List of locations to search for the module
    module_locations = [
        os.path.dirname(script_dir),
        os.path.join(os.path.dirname(script_dir), "pi_base"),
        os.path.join(os.path.dirname(script_dir), os.path.pardir, "pi_base"),
    ]

    module_name_to_import = "modpath"
    imported_module = import_module_from_locations(module_name_to_import, module_locations)


find_modpath()
