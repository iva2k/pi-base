#!/usr/bin/env python3

"""Main / CLI for the package."""

import sys


def main() -> int:
    """Main function.

    Returns:
        int: Error code
    """
    print("Hello world! I'm pi_base CLI")
    return 0


if __name__ == "__main__":
    rc = main()
    if rc != 0:  # Avoid "Uncaught Exeptions" in debugger
        sys.exit(rc)
