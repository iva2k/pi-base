#!/usr/bin/env python3

"""Main / CLI for the package."""

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation

import argparse
import logging
import os
import subprocess
import sys

## Experimental: hacks to use relative import not in module (e.g. CLI)
# Experiments revealed that it is sufficient to set __package__ variable to enable relative imports.
# If any future version of Python breaks that behavior, that assumption will need to be revisited.
# __init__.py files in the relative import tree are not needed for it to work.
# import importlib
# module = importlib.import_module("path", os.path.basename(SCRIPT_DIR))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# ? sys.path.append(os.path.dirname(os.path.realpath(SCRIPT_DIR)))
# pylint: disable-next=redefined-builtin
__package__ = os.path.basename(SCRIPT_DIR)  # noqa: A001
# pylint: disable=wrong-import-position,relative-beyond-top-level
# ruff: noqa: E402

from .modpath import get_script_dir
from .make import main as make_main

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != "__main__" else None)
# logger.setLevel(logging.DEBUG)


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
    script_dir = get_script_dir(__file__)
    prog = os.path.join(script_dir, "upload.sh")
    try:
        subprocess.run(["bash", prog] + args, check=True)
    except subprocess.CalledProcessError as e:
        return e.returncode
    return 0


def main(loggr=logger) -> int:
    commands = {
        "make": make_command,
        "upload": upload_command,
    }
    commands_list = commands.keys()
    command_help_text = "Must be one of: " + ", ".join(commands_list)

    parser = argparse.ArgumentParser(description="PI-BASE CLI")
    parser.add_argument("-D", "--debug", help="Enable debugging log", action="store_true")
    parser.add_argument("command", choices=commands_list, help=command_help_text)  # , help="Arguments for command")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for command")

    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

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
