#!/usr/bin/env python3

"""Main / CLI for the package."""

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation

import argparse
import inspect
import logging
import os
import subprocess
import sys

try:
    from .make import main as make_main
except:
    from make import main as make_main

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != '__main__' else None)
# logger.setLevel(logging.DEBUG)

# No root first slash (will be added as necessary):
app_dir = "home/pi"
etc_dir = "etc"


def get_script_dir(follow_symlinks: bool=True) -> str:
    if getattr(sys, 'frozen', False):  # py2exe, PyInstaller, cx_Freeze
        path = os.path.abspath(sys.executable)
    else:
        path = inspect.getabsfile(get_script_dir)
    if follow_symlinks:
        path = os.path.realpath(path)
    return os.path.dirname(path)


script_dir = get_script_dir()
caller_dir = os.getcwd()
logger.debug(f'script_dir={script_dir}, caller_dir={caller_dir}')

def make_command(args):
    try:
        sys.argv[1:] = args
        # from make import main as make_main
        make_main()
    except subprocess.CalledProcessError as e:
        return e.returncode
    # except ImportError:
    #     print("Error: make.py not found or unable to import.", file=sys.stderr)
    #     return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0

def upload_command(args):
    try:
        subprocess.run(["bash", "upload.sh"] + args, check=True)
    except subprocess.CalledProcessError as e:
        return e.returncode
    return 0


def main(loggr=logger) -> int:
    commands = {
        "make"    : make_command    ,
        "upload"  : upload_command  ,
    }
    commands_list = commands.keys()
    command_help_text = "Must be one of: " + ', '.join(commands_list)

    parser = argparse.ArgumentParser(description="PI-BASE CLI")
    parser.add_argument("command", choices=commands_list, help=command_help_text) # , help="Arguments for command")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for command")

    args = parser.parse_args()

    if args.command in commands:
        res = commands[args.command](args.args)
    else:
        parser.print_help()
        return 1

    return res

if __name__ == "__main__":
    rc = main()
    if rc != 0:  # Avoid "Uncaught Exeptions" in debugger
        sys.exit(rc)
