#!/usr/bin/env python3

from enum import IntEnum, unique
import os
from subprocess import check_output

tput_term = "linux"  # Global default term for tput()


@unique
class Color(IntEnum):
    """Basic colors."""

    BLACK = 0
    RED = 1
    GREEN = 2
    YELLOW = 3
    BLUE = 4
    PURPLE = 5
    CYAN = 6
    WHITE = 7

    def __str__(self):
        return str(self.value)

    @classmethod
    def get_value(cls, name):
        if name in cls.__members__:
            return cls[name].value
        return name


def tput_color(args=()):
    return tuple(map(Color.get_value, args))


#  TNORM=$(TERM=linux tput cnorm | sed -n l) ;# Get escape sequence and convert 0x1B into readable form. Side-effect: adds '$' at the end.
#  TNORM="${TNORM%$}" ;# Trim '$' at the end
# https://www.gnu.org/software/termutils/manual/termutils-2.0/html_chapter/tput_1.html
def tput(code, args=(), term=None):
    if os.name == "nt":
        return ""
    if term is None:
        term = tput_term
    if code in ["setaf", "setab"]:
        args = tput_color(args)
    cmd = f'tput {code} {" ".join(map(str, args))} 2>/dev/null'
    # print("DEBUG: tput('%s', term='%s') cmd='%s'" % (code, term, cmd) )
    try:
        result = check_output(cmd, env={"TERM": term}, shell=True, text=True)
        return result.replace("\n", "").replace("\r", "")
    except:
        return ""


# Colors
# tput setf 0~7
# tput setaf 0~7
# 0x00-0x07:  standard colors (as in ESC [ 30..37 m)
# 0x08-0x0f:  high intensity colors (as in ESC [ 90..97 m)
# 0x10-0xe7:  6*6*6=216 colors: 16 + 36*r + 6*g + b (0≤r,g,b≤5)
# 0xe8-0xff:  grayscale from black to white in 24 steps

# setaf/setab:
# Color       #define       Value       RGB
# black     COLOR_BLACK       0     0, 0, 0
# red       COLOR_RED         1     max,0,0
# green     COLOR_GREEN       2     0,max,0
# yellow    COLOR_YELLOW      3     max,max,0
# blue      COLOR_BLUE        4     0,0,max
# magenta   COLOR_MAGENTA     5     max,0,max
# cyan      COLOR_CYAN        6     0,max,max
# white     COLOR_WHITE       7     max,max,max

# setf/setb:
# Color       #define       Value       RGB
# black     COLOR_BLACK       0     0, 0, 0
# blue      COLOR_BLUE        1     0,0,max
# green     COLOR_GREEN       2     0,max,0
# cyan      COLOR_CYAN        3     0,max,max
# red       COLOR_RED         4     max,0,0
# magenta   COLOR_MAGENTA     5     max,0,max
# yellow    COLOR_YELLOW      6     max,max,0
# white     COLOR_WHITE       7     max,max,max


# Quick unit check
def quick_check():
    print("quick_check():")
    print(f"tput_term={tput_term}")
    # https://www.gnu.org/software/termutils/manual/termutils-2.0/html_chapter/tput_1.html
    for code, args in [
        # From ECMA-48 https://www.ecma-international.org/wp-content/uploads/ECMA-48_5th_edition_june_1991.pdf
        # 39 and 49 are the codes to reset default colors in \033[39m and \033[40m - use `tput setaf/setab 9`
        ("setaf", ("RED",)),  #  'setaf' (color)
        ("setaf", ("GREEN",)),  #  'setaf' (color)
        ("setaf", ("BLUE",)),  #  'setaf' (color)
        ("setf", ("RED",)),  #  'setf'  (color)
        ("cnorm", ()),  #  'cnorm' (cursor normal)
        ("cvvis", ()),  #  'cvvis' (block cursor)
        ("civis", ()),  #  'civis' (cursor invisible)
        ("clear", ()),  #  'clear' (Clear screen)
        ("cup", (2, 12)),  #  'cup'   (Move cursor to row #1, column #2 of screen)
        ("cols", ()),  #  co      Number of columns in a line
        ("it", ()),  #  it      Width of initial tab settings
        ("lh", ()),  #  lh      Number of rows in each label
        ("lines", ()),  #  li      Number of lines on screen or page
        ("lm", ()),  #  lm      Lines of memory if > `lines'; 0 means varies
        ("lw", ()),  #  lw      Number of columns in each label
        ("nlab", ()),  #  Nl      Number of labels on screen (start at 1)
        ("pb", ()),  #  pb      Lowest baud rate where padding is needed
        ("vt", ()),  #  vt      Virtual terminal number (CB/Unix)
        ("wsl", ()),  #  ws      Number of columns in status line
        ("xmc", ()),  #  sg      Number of blanks left by `smso' or `rmso'
        ("dim", ()),  #  mh      Begin half intensity mode
        ("dl", (2,)),  #  DL      Delete #1 lines (P*)
        ("dl1", ()),  #  dl      Delete one line (*)
        ("dsl", ()),  #  ds      Disable status line
        ("ech", (2,)),  #  ec      Erase #1 characters (P)
        ("ed", ()),  #  cd      Clear to end of display (*)
        ("el", ()),  #  ce      Clear to end of line
        ("el1", ()),  #  cb      Clear to beginning of line, inclusive
        ("hpa", (12,)),  #  ch      Move cursor to column #1 (P)
        ("ht", ()),  #  ta      Tab to next 8 space hardware tab stop
        ("hts", ()),  #  st      Set a tab in all rows, current column
        ("hu", ()),  #  hu      Move cursor up one-half line
        ("ich", (12,)),  #  IC      Insert #1 blank characters (P*)
        ("ich1", ()),  #  ic      Insert one blank character
        ("if", ()),  #  if      Name of file containing initialization string
        ("il", (2,)),  #  AL      Add #1 new blank lines (P*)
        ("il1", ()),  #  al      Add one new blank line (*)
        ("ind", ()),  #  sf      Scroll forward (up) one line
        ("indn", (12,)),  #  SF      Scroll forward #1 lines (P)
        ("rs1", ()),  #  r1      Reset terminal to sane modes
        ("rs2", ()),  #  r2      Reset terminal to sane modes
        ("rs3", ()),  #  r3      Reset terminal to sane modes
    ]:
        c = tput(code, args)
        print("  - %(code)-6s%(args)8s : '%(result)s'" % {"code": code, "args": " ".join(map(str, args)), "result": c.replace("\033", "\\033")})

    print("DONE quick_check()")


if __name__ == "__main__":
    quick_check()
