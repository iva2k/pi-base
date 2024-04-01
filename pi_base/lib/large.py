#!/usr/bin/env python3

import inspect
import sys
import os

from . import tput


class Large:
    """Print large message(s) on terminal."""

    def __init__(self, filepath=None) -> None:
        """Constructor.

        Args:
            filepath: chooses which text file to load with strings composing large message(s).

        Messages are blocks of text, each message followed by a single line with `# <key> <color_fg> <color_bg> <name>` format, where:
         * <key> is used to select the message
         * <color_fg> is used to set the message color (using `tput setaf <color>`)
         * <color_bg> is used to set the background color (using `tput setab <color>`)
         * <name> can be used for printing same message to regular logs
        All text in the message block is used as is, except 'M' is converted to a block character (see `conversions`).

        TODO: (later) consider using pyfiglet (though on reviewing available fonts, none were suitable for the purpose)
        """
        if filepath is None:
            # Default file to open:
            filepath = os.path.join(os.path.abspath(os.path.dirname(__file__)), "large.txt")
        self.term = None  # TODO: (when needed) Set to the actual TERM for tput.
        conversions = [
            ("M", "█"),
            ("\n", ""),
            ("\r", ""),
        ]
        self.color_reset = tput.tput("sgr0", (), self.term)
        # self.color_reset_fg = tput.tput('setaf', (9,), self.term)
        # self.color_reset_bg = tput.tput('setab', (0,), self.term)
        # TODO: (soon) Remove hard-coded color_reset_fg/color_reset_bg (use init args?)
        self.tput_clear = tput.tput("clear", (), self.term)
        # print('DEBUG: block=%d' % (ord(block[0])) )
        with open(filepath, encoding="utf-8") as f:
            x = f.readlines()
        pf = {}
        index = 0
        lines = []
        max_cols = 0
        rows = 0
        for line_in in x:
            if line_in[0] == "#":
                # separator, save result item
                [key, color_fg, color_bg, name] = line_in.replace("\n", "").replace("\r", "").replace("\t", " ").split(" ")[1:]
                pf[key] = {
                    "name": name,
                    "large": lines,
                    "color_fg": color_fg,
                    "color_bg": color_bg,
                    "cols": max_cols,
                    "rows": rows,
                }
                index += 1
                lines = []
                max_cols = 0
                rows = 0
            else:
                line = line_in
                for k, v in conversions:
                    line = line.replace(k, v)
                    if max_cols < len(line):
                        max_cols = len(line)
                lines += [line]
                rows += 1
        self.pf = pf
        self.count = index

    def result(self, key):
        return self.pf.get(key, {"name": "", "large": "", "color_fg": "", "color_bg": "", "rows": 0, "cols": 0})

    def print(self, key, do_clear=True, do_color=True):
        data = self.result(key)
        pf = data["name"]
        large = data["large"]
        if do_clear:
            print(self.tput_clear)
        if do_color:
            color_fg = data["color_fg"]
            color_bg = data["color_bg"]
            color_fg_code = tput.tput("setaf", (color_fg,), self.term)
            color_bg_code = tput.tput("setab", (color_bg,), self.term)
            # print(color_fg_code + color_bg_code + '\n'.join(large) + self.color_reset_fg + self.color_reset_bg)
            print(color_fg_code + color_bg_code + "\n".join(large) + self.color_reset)
        else:
            print("\n".join(large))
        return pf


# Quick unit check


def quick_check(path):
    # large = Large(f'{path}/large.txt')
    large = Large()
    for key in ["pass", "fail", "busy"]:
        result = large.result(key)
        print(f'{key} {result["name"]} {result["rows"]} x {result["cols"]}')
        name = large.print(key, do_clear=False)
        print("\n\n\n\n")


def main():
    def get_script_dir(follow_symlinks=True, func=main):
        if getattr(sys, "frozen", False):  # py2exe, PyInstaller, cx_Freeze
            path = os.path.abspath(sys.executable)
        else:
            path = inspect.getabsfile(get_script_dir)
        if follow_symlinks:
            path = os.path.realpath(path)
        return os.path.dirname(path)

    script_dir = get_script_dir()
    caller_dir = os.getcwd()
    print(f"DEBUG: script_dir={script_dir}, caller_dir={caller_dir}")
    quick_check(script_dir)


if __name__ == "__main__":
    main()
