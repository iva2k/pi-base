#!/usr/bin/env python3

from __future__ import annotations

import copy
import os
import time
import logging
import platform

from enum import Enum
from subprocess import Popen, PIPE, DEVNULL
from typing import Any
from collections.abc import Mapping

from . import tput

os.system("")  # Enable ANSI color codes  # noqa: S605, S607


class ColorCodes(Enum):
    """The color codes for command line output."""

    RED = "\u001b[31m"
    GREEN = "\u001b[32m"
    YELLOW = "\u001b[33m"
    BLUE = "\u001b[34m"
    MAGENTA = "\u001b[35m"
    CYAN = "\u001b[36m"
    DEFAULT = "\u001b[0m"

    _RED = "\u001b[0;31m"
    _GREEN = "\u001b[0;32m"
    _YELLOW = "\u001b[0;33m"
    _BLUE = "\u001b[0;34m"
    _MAGENTA = "\u001b[0;35m"
    _CYAN = "\u001b[0;36m"
    _DEFAULT = "\u001b[0;0m"


if platform.system() not in ("Darwin", "Windows"):
    from systemd import journal  # pylint: disable=import-error
#     name = __name__
#     log = logging.getLogger(name)
#     log_fmt = logging.Formatter("%(levelname)s %(message)s")
#     log_ch = journal.JournaldLogHandler()
#     log_ch.setFormatter(log_fmt)
#     log.addHandler(log_ch)
#     log.setLevel(logging.DEBUG)
#     log.warning("loggr warn")
#     log.info("loggr info")
#     log.error("loggr error")
#     log.debug("loggr debug")


class Vt:
    """Helper logger class for VT."""

    def __init__(self, vt_number, use_sudo=False, loggr=None):
        self.vt_term = None
        self.vt = None
        self.vt_number = vt_number
        self.use_sudo = use_sudo
        self.loggr = loggr
        if vt_number is None or vt_number == 0:
            return
        self.term = None
        if os.name == "nt":  # TODO: (when needed) include MacOS
            pass
        else:
            self.term = f"/dev/tty{vt_number:d}"
        if self.term:
            if self.use_sudo:
                pass
            else:
                try:
                    if self.loggr:
                        self.loggr.debug(f"VT({self.vt_number}) vt.opening {self.term}")
                    self.vt = open(self.term, "w", encoding="utf-8")
                except Exception as err:
                    if self.loggr:
                        self.loggr.error(f"VT({self.vt_number}) Open failed, error {type(err)} {err}, VT output disabled.")
                    self.vt = None
                    self.vt_number = 0
        # self.tput_clear = tput.tput('clear', (), self.vt_term)
        self.tput_cnorm = tput.tput("cnorm", (), self.vt_term)
        self.tput_civis = tput.tput("civis", (), self.vt_term)

    def __del__(self):
        if self.vt:
            # show cursor
            self.vt.write(self.tput_cnorm)
            self.flush()
            self.vt.close()
            if self.loggr:
                self.loggr.debug(f"VT({self.vt_number}) vt.closed")

    # def clear(self):
    #     if self.vt:
    #         if self.loggr: self.loggr.debug(f'VT({self.vt_number}) vt.clear()')
    #         self.vt.write(self.tput_clear)
    #         self.flush()

    def print(self, *tstr: object, sep=" ", end="\n"):
        proc = None
        file = None
        if self.use_sudo and self.term:
            try:
                # cmd = ['sudo', 'tee', self.term, '>', '/dev/null']
                cmd = ["sudo", "tee", self.term]
                if self.loggr:
                    self.loggr.debug(f'VT({self.vt_number}) Popen({" ".join(cmd)})')
                proc = Popen(cmd, stdin=PIPE, stdout=DEVNULL, stderr=DEVNULL, text=True)
                file = proc.stdin
            except Exception as err:
                if self.loggr:
                    self.loggr.error(f"VT({self.vt_number}) Popen() failed, error {type(err)} {err}, VT output disabled.")
                proc = None
                file = None
                self.use_sudo = False  # Disable future tries
        elif self.vt:
            file = self.vt
            if self.loggr:
                self.loggr.debug(f"VT({self.vt_number}) vt.print()")

        if file:
            try:
                separator = None
                for item in tstr:
                    if separator:
                        file.write(separator)
                    file.write(str(item))
                    separator = sep
                if end:
                    file.write(end)
                file.flush()
            except Exception as err:
                if self.loggr:
                    self.loggr.error(f"VT({self.vt_number}) file.write() failed, error {type(err)} {err}")

        if self.use_sudo and proc:
            if self.loggr:
                self.loggr.debug(f'VT({self.vt_number}) Close Popen({" ".join(cmd)})')
            if file:
                file.close()
            proc.wait()

    def flush(self):
        if self.vt:
            if self.loggr:
                self.loggr.debug(f"VT({self.vt_number}) vt.flush()")
            self.vt.flush()


class Loggr(logging.Logger):
    """Multi-logger, helps organize output and logs.

    Optionally sends logs to:
    1. VT
    2. stdout
    3. journal
    """

    def __init__(self, use_vt_number=None, use_stdout=True, use_journal_name=None, use_sudo=False, level: int = logging.DEBUG, primary_loggr=None):
        super().__init__(name="Loggr", level=level)
        self.level = level
        self.primary_loggr = primary_loggr
        self.stdout_term = None  # Define TERM for stdout
        self.use_vt_number = use_vt_number
        self.vt_term = None  # Define TERM for vt
        self.vt = Vt(use_vt_number, use_sudo=use_sudo, loggr=primary_loggr) if use_vt_number else None
        self.use_stdout = use_stdout
        self.use_journal_name = use_journal_name
        self.journal = None
        if use_journal_name and os.name != "nt":
            self.journal = logging.getLogger(use_journal_name)
            self.journal.propagate = False  # Important to disallow sending the logs to the parent.
            log_fmt = logging.Formatter("%(levelname)s %(message)s")
            if platform.system() not in ("Darwin", "Windows"):
                try:
                    # This API from `pip install systemd~=0.16.1`, however, it fails installing / compiling on 64-bit RPI OS
                    log_ch = journal.JournaldLogHandler()
                except:
                    # This API from `apt-get install python3-systemd` (or `pip install systemd-python`, but that requires more apt packages, so use pre-packaged apt package instead)
                    log_ch = journal.JournalHandler()
                log_ch.setFormatter(log_fmt)
                self.journal.addHandler(log_ch)
            self.setLevel(level)

    def setLevel(self, level: int):
        self.level = level
        if self.journal:
            # self.journal.setLevel(level) # TODO: (when needed) Need a more elegant way to set separate log levels
            self.journal.setLevel(logging.DEBUG)

    def cls(self, *tstr: object):
        """Clear screen, and optionally print."""
        self.tput_print("clear", ())
        if len(tstr) > 0:
            self.print(*tstr)

    # @overload
    # def log(self, level: int, msg: object, *args: object, **kwargs: Mapping[str, Any]): ...
    def log(self, level: int, msg: object, *tstr: object, color_code: ColorCodes | str = ColorCodes.DEFAULT, **kwargs: Mapping[str, Any]):
        """Print message(s), with log level that can be masked."""
        if not level:
            level = logging.NOTSET
        kwargs1 = {"sep": " ", "end": "\n", **kwargs}
        if level >= self.level:
            level_str = f"{logging.getLevelName(level):8s}"
            if self.vt:
                self.vt.print(level_str, msg, *tstr, **kwargs1)
            if self.use_stdout:
                self.color_print(f"{level_str}: {' '.join([str(item) for item in ([msg] + list(tstr))])}", color_code=color_code)
            if self.journal:
                self.journal.log(level, msg, *tstr)

    def critical(self, msg: object, *tstr: object, **kwargs: Mapping[str, Any]):
        self.log(logging.CRITICAL, msg, *tstr, color_code=ColorCodes.RED, **kwargs)

    def error(self, msg: object, *tstr: object, **kwargs: Mapping[str, Any]):
        self.log(logging.ERROR, msg, *tstr, color_code=ColorCodes.YELLOW, **kwargs)

    def warning(self, msg: object, *tstr: object, **kwargs: Mapping[str, Any]):
        self.log(logging.WARNING, msg, *tstr, color_code=ColorCodes.BLUE, **kwargs)

    def info(self, msg: object, *tstr: object, **kwargs: Mapping[str, Any]):
        self.log(logging.INFO, msg, *tstr, color_code=ColorCodes.CYAN, **kwargs)

    def debug(self, msg: object, *tstr: object, **kwargs: Mapping[str, Any]):
        self.log(logging.DEBUG, msg, *tstr, color_code=ColorCodes.DEFAULT, **kwargs)

    def print(self, *tstr: object, **kwargs: Mapping[str, Any]):
        """Print message(s), unmasked."""
        kwargs1 = {"sep": " ", "end": "\n", **kwargs}
        kwargs2 = copy.copy(kwargs)
        if "sep" in kwargs2:
            del kwargs2["sep"]
        if "end" in kwargs2:
            del kwargs2["end"]
        if self.vt:
            self.vt.print(*tstr, **kwargs1)
        if self.use_stdout:
            print(*tstr, **kwargs1)
        if self.journal:
            self.journal.info(*tstr, **kwargs2)

    def log_box(self, text: str, width: int = 50, color_code: ColorCodes | str = ColorCodes.DEFAULT) -> None:
        """Log provided text in a box of given width (centered).

        Output Example:
        ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
        ┃            Test Setup            ┃
        ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

        Args:
            text    Text to log in box
            width   Width of box to create
        """
        if width is None:
            width = len(text) * 2
        self.color_print("┏" + "━" * width + "┓")
        self.color_print("┃", end="")
        self.color_print(f"{text:^{width}}", color_code=color_code, end="")
        self.color_print("┃")
        self.color_print("┗" + "━" * width + "┛")

    def get_user_input(self, text: str, color_code: ColorCodes | str = ColorCodes.YELLOW) -> str:
        """Gets user input utilizing colored text.

        Args:
            text: The user prompt to display
            color_code: The color you want to print the text to the console as

        Returns:
            User input
        """
        self.color_print(text, color_code=color_code, end=" ")
        return input()

    def get_user_yes_no_input(self, text: str, color_code: ColorCodes | str = ColorCodes.YELLOW) -> bool:
        """Gets a yes/no user confirmation.

        Args:
            text: The user prompt to display (Yes/No instructions are expected to be included here)
            color_code: The color you want to print the text to the console as

        Returns:
            True if "Yes", False if "No"
        """
        result = False
        while True:
            response = self.get_user_input(text, color_code)
            if response.lower() in ("yes", "y"):
                result = True
                break
            if response.lower() in ("no", "n"):
                result = False
                break
            self.color_print("Response must be [Y]es or [N]o.", ColorCodes.RED)
        return result

    def color_print(self, text: str, color_code: ColorCodes | str = ColorCodes.DEFAULT, end: str = "\n", filter_text: str = "") -> None:
        """Prints the text as both an std output using the given color code.

        Args:
            text        : The text to output and save
            color_code  : The color you want to print the text to the console as
            end         : String to print at the end of the text
            filter_text : Text that should appear as colored
        """
        color_code = color_code.value if isinstance(color_code, ColorCodes) else color_code
        if filter_text == "":
            filter_text = text
        elif filter_text not in text:
            color_code = ColorCodes.DEFAULT.value
            filter_text = text
        index = text.find(filter_text)
        strlen = len(filter_text)
        message = text[:index] + color_code + text[index : index + strlen] + ColorCodes.DEFAULT.value + text[index + strlen :]
        kwargs: Mapping[str, Any] = {"end": end}
        self.print(message, **kwargs)

    def position(self, x: int, y: int, *tstr: object) -> None:
        """Move cursor to position on screen, and optionally print.

        0,0 is top left, x is horizontal, y is vertical.
        """
        self.tput_print("cup", (y, x))
        if len(tstr) > 0:
            self.print(*tstr)

    def el(self, *tstr) -> None:
        """Clear to end of line, and optionally print."""
        self.tput_print("el", ())
        if len(tstr) > 0:
            self.print(*tstr)

    def ed(self, *tstr):
        """Clear to end of display, and optionally print."""
        self.tput_print("ed", ())
        if len(tstr) > 0:
            self.print(*tstr)

    def dl(self, num=1) -> None:
        """Delete <num> lines.

        ('dl'   , ( 2,   )),   #  DL      Delete #1 lines (P*)
        """
        self.tput_print("dl", (num,))

    def ech(self, num=1) -> None:
        """Delete <num> characters."""
        self.tput_print("ech", (num,))

    def cnorm(self) -> None:
        """Cursor normal."""
        self.tput_print("cnorm", ())

    def cblock(self) -> None:
        """Cursor block."""
        self.tput_print("cvvis", ())

    def civis(self):
        """Cursor invisible."""
        self.tput_print("civis", ())

    def cols(self, term=None) -> int:
        """Return number of visible columns in the terminal."""
        str_val = self.tput("cols", (), term)
        return int(str_val)

    def lines(self, term=None) -> int:
        """Return number of visible lines in the terminal."""
        str_val = self.tput("lines", (), term)
        return int(str_val)

    # TODO: (soon) Use tput.tput for Escape sequences, e.g.:
    #  TNORM=$(TERM=linux tput.tput cnorm | sed -n l) ;# Get escape sequence and convert 0x1B into readable form. Side-effect: adds '$' at the end.
    #  TNORM="${TNORM%$}" ;# Trim '$' at the end

    # TODO: (when needed) Implement erase line to end
    # TODO: (when needed) Implement color text codes
    # TODO: (when needed) Implement bold text codes

    # Expose tput.tput for our own commands
    def tput(self, code, args=(), term=None):
        return tput.tput(code, args, term)

    def tput_print(self, code, args=()):
        str_val = self.tput(code, args, self.vt_term)
        if self.vt:
            self.vt.print(str_val, end="")
        if self.use_stdout:
            str_val = self.tput(code, args, self.stdout_term)
            print(str_val, end="")

    # TODO: (when needed) Implement color text codes
    # TODO: (when needed) Implement bold text codes


# Quick unit check
def quick_check():
    loggr = Loggr(use_vt_number=2, use_journal_name="testloggr", use_stdout=True)
    print("sleeping 3")
    time.sleep(3)
    loggr.cls("cleared!")
    loggr.log(logging.INFO, "voila1")
    loggr.log(logging.INFO, "voila2")
    loggr.position(10, 40)
    loggr.log(logging.INFO, "position 10,42")
    print("sleeping 3")
    time.sleep(3)
    loggr.print("DONE")
    # print("DONE")


def position_check():
    loggr = Loggr(use_vt_number=2, use_journal_name="testloggr", use_stdout=True)
    print("sleeping 3")
    time.sleep(5)
    loggr.cls("0,0")
    loggr.position(10, 10, "10,10")
    loggr.position(0, 10, "0,10")
    loggr.position(30, 3, "30,3")
    loggr.position(20, 2, "20,2")
    loggr.position(10, 1, "10,1")
    loggr.position(20, 10, "20,10")
    loggr.position(1, 9, "1,9")
    loggr.position(0, 11, "0,11")

    print("sleeping 3")
    time.sleep(3)
    loggr.print("DONE")
    # print("DONE")


def vt_check():
    loggr = Loggr(use_vt_number=4, use_journal_name=None, use_stdout=False, use_sudo=True)
    loggr.cls("0,0")
    loggr.position(10, 10, "10,10")
    loggr.position(0, 10, "0,10")
    loggr.position(30, 3, "30,3")
    loggr.position(20, 2, "20,2")
    loggr.position(10, 1, "10,1")
    loggr.position(20, 10, "20,10")
    loggr.position(1, 9, "1,9")
    loggr.position(0, 11, "0,11")
    loggr.print("DONE")
    # print("DONE")


def journal_check():
    # Trying to screw up journal
    # Creating a root logger may break the journal logger (it will also log to the console through it's parent).
    logging.basicConfig(level=logging.INFO)
    g_logger = logging.getLogger(__name__ if __name__ != "__main__" else None)
    g_logger.setLevel(logging.DEBUG)

    loggr = Loggr(use_vt_number=None, use_journal_name="testloggrjournal", use_stdout=False)
    # These should appear only in journal, not on the console:
    # loggr.critical("loggr critical")
    loggr.error("loggr error")
    loggr.warning("loggr warn")
    loggr.info("loggr info")
    loggr.debug("loggr debug")
    loggr.print("DONE")
    # print("DONE")


if __name__ == "__main__":
    # quick_check()
    # position_check()
    # vt_check()
    journal_check()
