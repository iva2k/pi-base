#!/usr/bin/env python3

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty

# "modpath" must be first of our modules
# pylint: disable=wrong-import-position
# ruff: noqa: E402

# Shared monorepo lib
# from .defs import Color, keys

if TYPE_CHECKING:
    from pi_base.lib.loggr import Loggr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != "__main__" else None)
# logger.setLevel(logging.DEBUG)

# ANSI Terminal defines.
# See https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797


# Colors
class Color:
    C_BLACK = 0
    C_RED = 1
    C_GREEN = 2
    C_YELLOW = 3
    C_BLUE = 4
    C_MAGENTA = 5
    C_CYAN = 6
    C_WHITE = 7
    ATTR_INTENSITY = 8
    C_GRAY = C_BLACK | ATTR_INTENSITY
    C_B_RED = C_RED | ATTR_INTENSITY
    C_B_GREEN = C_GREEN | ATTR_INTENSITY
    C_B_YELLOW = C_YELLOW | ATTR_INTENSITY
    C_B_BLUE = C_BLUE | ATTR_INTENSITY
    C_B_MAGENTA = C_MAGENTA | ATTR_INTENSITY
    C_B_CYAN = C_CYAN | ATTR_INTENSITY
    C_B_WHITE = C_WHITE | ATTR_INTENSITY


# Keys
class keys:
    KEY_UP = 1
    KEY_DOWN = 2
    KEY_LEFT = 3
    KEY_RIGHT = 4
    KEY_HOME = 5
    KEY_END = 6
    KEY_PGUP = 7
    KEY_PGDN = 8
    KEY_QUIT = 9
    KEY_ENTER = 10
    KEY_BACKSPACE = 11
    KEY_DELETE = 12
    KEY_TAB = 13
    KEY_SHIFT_TAB = 14
    KEY_ESC = 20
    KEY_F1 = 30
    KEY_F2 = 31
    KEY_F3 = 32
    KEY_F4 = 33
    KEY_F5 = 34
    KEY_F6 = 35
    KEY_F7 = 36
    KEY_F8 = 37
    KEY_F9 = 38
    KEY_F10 = 39

    MOUSE_PREFIX = b"\x1b[M"
    MOUSE_LEN = 6
    MOUSE_X10_BUTTON1 = 32
    MOUSE_VT200_BUTTON1 = 1

    if os.name == "nt":
        KEYMAP = {
            # TODO: (when needed) Implement b"\xE0..." codes
            b"\x00H": KEY_UP,
            b"\x00P": KEY_DOWN,
            b"\x00K": KEY_LEFT,
            b"\x00M": KEY_RIGHT,
            b"\x00G": KEY_HOME,
            b"\x00O": KEY_END,
            b"\x00I": KEY_PGUP,
            b"\x00Q": KEY_PGDN,
            b"\x03": KEY_QUIT,
            b"\r": KEY_ENTER,
            b"\t": KEY_TAB,
            b"\x1b[Z": KEY_SHIFT_TAB,
            b"\x08": KEY_BACKSPACE,
            b"\x7f": KEY_BACKSPACE,
            b"\x00S": KEY_DELETE,
            # TODO: (when needed) Check and fix these:
            b"\x1b[3~": KEY_DELETE,
            b"\x1b": KEY_ESC,
            b"\x1bOP": KEY_F1,
            b"\x1bOQ": KEY_F2,
            b"\x1bOR": KEY_F3,
            b"\x1bOS": KEY_F4,
            b"\x1b[15~": KEY_F5,
            b"\x1b[17~": KEY_F6,
            b"\x1b[18~": KEY_F7,
            b"\x1b[19~": KEY_F8,
            b"\x1b[20~": KEY_F9,
            b"\x1b[21~": KEY_F10,
        }

    elif os.name == "posix":
        KEYMAP = {
            b"\x1b[A": KEY_UP,
            b"\x1b[B": KEY_DOWN,
            b"\x1b[D": KEY_LEFT,
            b"\x1b[C": KEY_RIGHT,
            b"\x1b[H": KEY_HOME,
            b"\x1b[F": KEY_END,
            b"\x1bOH": KEY_HOME,
            b"\x1bOF": KEY_END,
            b"\x1b[1~": KEY_HOME,
            b"\x1b[4~": KEY_END,
            b"\x1b[5~": KEY_PGUP,
            b"\x1b[6~": KEY_PGDN,
            b"\x03": KEY_QUIT,
            b"\r": KEY_ENTER,
            b"\n": KEY_ENTER,
            b"\t": KEY_TAB,
            b"\x1b[Z": KEY_SHIFT_TAB,
            b"\x1b[\t": KEY_SHIFT_TAB,
            b"\x7f": KEY_BACKSPACE,
            b"\x1b[3~": KEY_DELETE,
            b"\x1b": KEY_ESC,
            b"\x1bOP": KEY_F1,
            b"\x1bOQ": KEY_F2,
            b"\x1bOR": KEY_F3,
            b"\x1bOS": KEY_F4,
            b"\x1b[15~": KEY_F5,
            b"\x1b[17~": KEY_F6,
            b"\x1b[18~": KEY_F7,
            b"\x1b[19~": KEY_F8,
            b"\x1b[20~": KEY_F9,
            b"\x1b[21~": KEY_F10,
        }

    elif os.name == "mac":
        # TODO: (when needed) Check and fix these:
        KEYMAP = {
            b"\x1b[A": KEY_UP,
            b"\x1b[B": KEY_DOWN,
            b"\x1b[D": KEY_LEFT,
            b"\x1b[C": KEY_RIGHT,
            b"\x1b[H": KEY_HOME,
            b"\x1b[F": KEY_END,
            b"\x1bOH": KEY_HOME,
            b"\x1bOF": KEY_END,
            b"\x1b[1~": KEY_HOME,
            b"\x1b[4~": KEY_END,
            b"\x1b[5~": KEY_PGUP,
            b"\x1b[6~": KEY_PGDN,
            b"\x03": KEY_QUIT,
            b"\r": KEY_ENTER,
            b"\t": KEY_TAB,
            b"\x1b[Z": KEY_SHIFT_TAB,
            b"\x7f": KEY_BACKSPACE,
            b"\x1b[3~": KEY_DELETE,
            b"\x1b": KEY_ESC,
            b"\x1bOP": KEY_F1,
            b"\x1bOQ": KEY_F2,
            b"\x1bOR": KEY_F3,
            b"\x1bOS": KEY_F4,
            b"\x1b[15~": KEY_F5,
            b"\x1b[17~": KEY_F6,
            b"\x1b[18~": KEY_F7,
            b"\x1b[19~": KEY_F8,
            b"\x1b[20~": KEY_F9,
            b"\x1b[21~": KEY_F10,
        }

    else:
        raise NotImplementedError("Unsupported OS")


class _Screen:
    """Represents screen on ANSI terminal with stdin and stdout."""

    @staticmethod
    def wr(s) -> None:
        """Write string to screen."""
        if isinstance(s, str):
            s = bytes(s, "utf-8")
        os.write(1, s)

    @staticmethod
    def wr_fixedw(s, width) -> None:
        """Write string in a fixed-width field."""
        s = s[:width]
        _Screen.wr(s)
        _Screen.wr(" " * (width - len(s)))
        # Doesn't work here, as it doesn't advance cursor
        # Screen.clear_num_pos(width - len(s))

    @classmethod
    def init_tty(cls):
        if os.name == "nt":
            pass
        else:
            cls.org_termios = termios.tcgetattr(0)
            tty.setraw(0)

    @classmethod
    def deinit_tty(cls):
        if os.name == "nt":
            pass
        else:
            termios.tcsetattr(0, termios.TCSANOW, cls.org_termios)

    # Clear specified number of positions
    @staticmethod
    def clear_num_pos(num) -> None:
        if num > 0:
            _Screen.wr(f"\x1b[{num}X")

    @staticmethod
    def get_cursor_pos() -> tuple[int, int]:
        _Screen.wr("\x1b[6n")
        if os.name == "nt":
            res = True
        else:
            # import select
            res = select.select([0], [], [], 0.2)[0]
            if not res:
                return -1, -1
        # if os.name == "nt":
        #     resp = msvcrt.getch()
        # else:
        #     resp = os.read(0, 32)
        # assert resp.startswith(b"\x1b[8;") and resp[-1:] == b"t"
        # vals = resp[:-1].split(b";")
        # return (int(vals[2]), int(vals[1]))

        data = b""
        while not data.endswith(b"R"):
            if os.name == "nt":
                data = data + msvcrt.getch()
            else:
                data = data + os.read(0, 32)
        # response data = "^[[{y};{x}R"
        res = re.match(r".*\[(?P<y>\d*);*(?P<x>\d*)R", data.decode())
        if not res:
            return -1, -1
        x = int(res.group("x")) - 1
        y = int(res.group("y")) - 1
        return x, y


class UserInput:
    def __init__(self, end_on_tab: bool = False, include_endchar: bool = False, debug: bool = False, loggr: logging.Logger | Loggr = logger) -> None:
        self.end_on_tab = end_on_tab
        self.include_endchar = include_endchar
        self.debug = debug
        self.loggr = loggr

        self.keys = keys()
        self.multikeys: list[bytes] = [k for k in self.keys.KEYMAP if isinstance(k, bytes) and len(k) > 1]

        self.key_story = b""
        self.kbuf = b""
        self.top_line = 0
        self.cur_line = 0
        self.row = 0
        # self.col = 0
        self.x = 0
        self.y = 0
        self.height = 1  # height
        self.width = 80  # width
        self.margin = 0
        self.total_lines = 1
        self.t = ""
        self.h = 1
        self.w = 32
        self.focus = False
        # self.set(text)
        self.col = 0  # len(text)
        # self.adjust_cursor_eol()
        self.just_started = True
        self.finish_dialog = False
        self.content: list[str] = [""]

    def reset(self) -> None:
        self.key_story = b""
        self.kbuf = b""
        self.top_line = 0
        self.cur_line = 0
        self.row = 0
        # self.col = 0
        self.x = 0
        self.y = 0
        self.height = 1  # height
        self.width = 80  # width
        self.margin = 0
        self.total_lines = 1
        self.t = ""
        self.h = 1
        self.w = 32
        self.focus = False
        # self.set(text)
        self.col = 0  # len(text)
        # self.adjust_cursor_eol()
        self.just_started = True
        self.finish_dialog = False
        self.content: list[str] = [""]

    def goto(self, x: int, y: int) -> None:
        # TODO: When Python is 3.5, update this to use bytes
        _Screen.wr(f"\x1b[{y + 1};{x + 1}H")

    def cursor(self, onoff: bool) -> None:
        if onoff:
            _Screen.wr(b"\x1b[?25h")
        else:
            _Screen.wr(b"\x1b[?25l")

    def set_cursor(self):
        self.goto(self.col + self.x, self.row + self.y)
        self.cursor(onoff=True)

    def attr_color(self, fg: int, bg: int = -1):
        MAX_COLOR = 8
        FG_CODE_BASE = 30
        BG_CODE_BASE = 40
        if bg == -1:
            bg = fg >> 4
            fg &= 0xF
        if bg is None:
            if fg > MAX_COLOR:
                _Screen.wr(f"\x1b[{FG_CODE_BASE + fg - MAX_COLOR};1m")
            else:
                _Screen.wr(f"\x1b[{FG_CODE_BASE + fg}m")
        else:
            if bg > MAX_COLOR:
                raise ValueError(f"Expected bg <= {MAX_COLOR}")
            if fg > MAX_COLOR:
                _Screen.wr(f"\x1b[{FG_CODE_BASE + fg - MAX_COLOR};{BG_CODE_BASE + bg};1m")
            else:
                _Screen.wr(f"\x1b[0;{FG_CODE_BASE + fg};{BG_CODE_BASE + bg}m")

    def attr_reset(self):
        _Screen.wr(b"\x1b[0m")

    def show_line(self, line: str, i: int):
        if self.just_started:
            fg = Color.C_WHITE
        else:
            fg = Color.C_BLACK
        # self.attr_color(fg, Color.C_CYAN)
        # super().show_line(line, i)
        line = line[self.margin :]
        line = line[: self.width]
        _Screen.wr(line)
        _Screen.clear_num_pos(self.width - len(line))

        self.attr_reset()

    def adjust_cursor_eol(self):
        # Returns True if entire window needs redraw
        val = 0
        if self.content:
            val = self.col + self.margin
            if val > 0:
                # Note: adjust_cursor_eol() may be called from widgets
                # where self.content is not guaranteed to be a str.
                val = min(val, len(self.content[self.cur_line]))
        if val > self.width - 1:
            self.margin = val - (self.width - 1)
            self.col = self.width - 1
            return True
        else:
            self.col = val - self.margin
            return False

    def redraw(self):
        self.cursor(onoff=False)
        i = self.top_line
        for c in range(self.height):
            self.goto(self.x, self.y + c)
            if i >= self.total_lines:
                self.show_line("", -1)
            else:
                self.show_line(self.content[i], i)
                # self.show_line(self.t if i == 0 else "", i)
                i += 1
        self.set_cursor()

    def update_line(self):
        self.cursor(onoff=False)
        self.goto(self.x, self.row + self.y)
        self.show_line(self.content[self.cur_line], self.cur_line)
        self.set_cursor()

    def next_line(self):
        if self.row + 1 == self.height:
            self.top_line += 1
            return True
            # self.redraw()
        else:
            self.row += 1
            return False
            # self.set_cursor()

    def handle_cursor_keys(self, key) -> bool:
        if not self.total_lines:
            return False
        if key == self.keys.KEY_DOWN:
            # if self.cur_line + 1 != self.total_lines:
            #     self.cur_line += 1
            #     redraw = self.adjust_cursor_eol()
            #     if self.next_line() or redraw:
            #         self.redraw()
            #     else:
            #         self.set_cursor()
            pass
        elif key == self.keys.KEY_UP:
            # if self.cur_line > 0:
            #     self.cur_line -= 1
            #     redraw = self.adjust_cursor_eol()
            #     if self.row == 0:
            #         if self.top_line > 0:
            #             self.top_line -= 1
            #             self.redraw()
            #     else:
            #         self.row -= 1
            #         if redraw:
            #             self.redraw()
            #         else:
            #             self.set_cursor()
            pass
        elif key == self.keys.KEY_LEFT:
            if self.col > 0:
                self.col -= 1
                self.set_cursor()
            elif self.margin > 0:
                self.margin -= 1
                self.redraw()
        elif key == self.keys.KEY_RIGHT:
            self.col += 1
            if self.adjust_cursor_eol():
                self.redraw()
            else:
                self.set_cursor()
        elif key == self.keys.KEY_HOME:
            self.col = 0
            if self.margin > 0:
                self.margin = 0
                self.redraw()
            else:
                self.set_cursor()
        elif key == self.keys.KEY_END:
            self.col = len(self.content[self.cur_line])
            if self.adjust_cursor_eol():
                self.redraw()
            else:
                self.set_cursor()
        elif key == self.keys.KEY_PGUP:
            # self.cur_line -= self.height
            # self.top_line -= self.height
            # if self.top_line < 0:
            #     self.top_line = 0
            #     self.cur_line = 0
            #     self.row = 0
            # elif self.cur_line < 0:
            #     self.cur_line = 0
            #     self.row = 0
            # self.adjust_cursor_eol()
            # self.redraw()
            pass
        elif key == self.keys.KEY_PGDN:
            # self.cur_line += self.height
            # self.top_line += self.height
            # if self.cur_line >= self.total_lines:
            #     self.top_line = self.total_lines - self.height
            #     self.cur_line = self.total_lines - 1
            #     if self.top_line >= 0:
            #         self.row = self.height - 1
            #     else:
            #         self.top_line = 0
            #         self.row = self.cur_line
            # self.adjust_cursor_eol()
            # self.redraw()
            pass
        else:
            return False
        return True

    def handle_mouse(self, col: int, row: int) -> bool:
        row -= self.y
        col -= self.x
        if 0 <= row < self.height and 0 <= col < self.width:
            cur_line = self.top_line + row
            if cur_line < self.total_lines:
                self.row = row
                self.col = col
                self.cur_line = cur_line
                self.adjust_cursor_eol()
                self.set_cursor()
                return True
        return False

    def handle_key(self, key) -> bool | int | None:
        if key == self.keys.KEY_QUIT:
            return key
        if self.handle_cursor_keys(key):
            return None
        return self.handle_edit_key(key)

    def handle_edit_key(self, key) -> bool | None:
        line = self.content[self.cur_line]
        if key == self.keys.KEY_ENTER or (self.end_on_tab and key == self.keys.KEY_TAB):
            if self.include_endchar:
                mymap = {
                    self.keys.KEY_ENTER: b"\n",
                    self.keys.KEY_TAB: b"\t",
                }
                k = mymap[key]
                line = line[: self.col + self.margin] + str(k, "utf-8") + line[self.col + self.margin :]
                self.content[self.cur_line] = line
                self.col += 1

            # self.content[self.cur_line] = l[:self.col + self.margin]
            # self.cur_line += 1
            # self.content[self.cur_line:self.cur_line] = [l[self.col + self.margin:]]
            # self.total_lines += 1
            # self.col = 0
            # self.margin = 0
            # self.next_line()
            # self.redraw()
            return True

        if self.just_started:
            if key != self.keys.KEY_BACKSPACE:
                # Overwrite initial string with new content
                # self.set_lines([""])
                self.content = [""]
                self.col = 0
            self.just_started = False

        if key == self.keys.KEY_BACKSPACE:
            if self.col + self.margin:
                if self.col:
                    self.col -= 1
                else:
                    self.margin -= 1
                line = line[: self.col + self.margin] + line[self.col + self.margin + 1 :]
                self.content[self.cur_line] = line
                self.update_line()
        elif key == self.keys.KEY_DELETE:
            line = line[: self.col + self.margin] + line[self.col + self.margin + 1 :]
            self.content[self.cur_line] = line
            self.update_line()
        else:
            line = line[: self.col + self.margin] + str(key, "utf-8") + line[self.col + self.margin :]
            self.content[self.cur_line] = line
            self.col += 1
            self.adjust_cursor_eol()
            self.update_line()
        return None

    def get_chrs(self) -> bytes:
        if self.kbuf:
            # key = self.kbuf[0:1]
            # self.kbuf = self.kbuf[1:]
            key = self.kbuf
            self.kbuf = b""
        elif os.name == "nt":
            key = msvcrt.getch()
        else:
            key = os.read(0, 32)
        return key

    def maybe_multikey(self, key) -> tuple[int, bool]:
        """Determine if can map, or need to read another byte to map a multikey sequence.

        Args:
            key: One or more bytes of keys input.

        Returns:
            can_map, need_more: count of key bytes that can be mapped, and whether more bytes are needed.
        """
        if key.startswith(self.keys.MOUSE_PREFIX):
            need_len = 6
            return need_len if len(key) >= need_len else 0, len(key) < need_len
        if self.keys.MOUSE_PREFIX.startswith(key) and len(key) < len(self.keys.MOUSE_PREFIX):
            return 0, True

        # return any(multikey.startswith(key) and len(key) < len(multikey) for multikey in self.multikeys)
        for multikey in self.keys.KEYMAP:
            if key == multikey:
                return len(multikey), False  # No more bytes needed, can map
            if multikey.startswith(key) and len(key) < len(multikey):
                return 0, True  # More bytes needed to map
        return 0, False

    def get_input(self) -> bytes | int | list[int] | None:
        key = self.get_chrs()
        # length_multi = 0
        while True:
            can_map, need_more = self.maybe_multikey(key)
            if not need_more:
                break
            # length_multi = len(key)
            key = key + self.get_chrs()

        self.key_story = self.key_story + key

        if can_map:
            if key.startswith(self.keys.MOUSE_PREFIX) and len(key) == self.keys.MOUSE_LEN:
                # Decode mouse input (X10 compatibility mode SET_X10_MOUSE, Normal tracking mode SET_VT200_MOUSE, MOUSE_VT200_BUTTON1=):
                if key[3] not in [self.keys.MOUSE_X10_BUTTON1, self.keys.MOUSE_VT200_BUTTON1]:
                    return None
                row = key[5] - 33
                col = key[4] - 33
                return [col, row]
            key = self.keys.KEYMAP.get(key, key)
        else:
            # Put the remainder of the key into the buffer
            key = key.decode()
            self.kbuf = key[1:].encode()
            key = key[0:1].encode()

        return key

    def handle_input(self, inp):
        if isinstance(inp, list):
            res = self.handle_mouse(inp[0], inp[1])
        else:
            res = self.handle_key(inp)
        return res

    def loop(self) -> bool | int:
        self.redraw()
        while True:
            key = self.get_input()
            if key is None:
                continue
            res = self.handle_input(key)

            # if res is not None and res is not True:
            if res is not None:
                return res

    def input(self, msg: str, default: str | None = None) -> str:
        _Screen.init_tty()
        self.reset()
        self.content = [default or ""]
        if msg:
            _Screen.wr(msg)
        x, y = _Screen.get_cursor_pos()
        if x > 0 and y > 0:
            self.x = x
            self.y = y
        res = self.loop()
        data = ""
        if res is True:
            _Screen.wr("\r\n")
            if self.debug and self.loggr:
                key_story_str = ";".join([bytes([c]).decode() for c in self.key_story])
                key_story_str = convert_non_printable_to_hex(key_story_str)
                self.loggr.debug(f'input keys received: "{key_story_str}" -> "{self.content[0]}"')
            data = self.content[0]
        _Screen.deinit_tty()
        return data


def convert_non_printable_to_hex(input_string: str) -> str:
    result = []
    for character in input_string:
        if character.isprintable():
            result.append(character)
        else:
            result.append(f"x{ord(character):02x}")
    return "".join(result)
