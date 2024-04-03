#!/usr/bin/env python3
import argparse
import sys
# import zest.releaser


# Do not edit this line:
__version__ = "0.0.34"
# instead, use commands from zest.releaser


def main():
    parser = argparse.ArgumentParser("Version module for package pi_base")
    parser.add_argument("command", help="Command", choices=["current"])
    args = parser.parse_args()
    if args.command == "current":
        print(__version__)
        sys.exit(0)

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
