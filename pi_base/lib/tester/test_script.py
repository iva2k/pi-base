#!/usr/bin/env python3

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation

from __future__ import annotations

import argparse
import csv
from enum import Enum
import fnmatch
import importlib
import inspect
import logging
import os
import signal
import sys
import time
import traceback
from datetime import datetime
from timeit import default_timer as timer
from types import ModuleType, SimpleNamespace
from typing import Any, Callable, Optional, TYPE_CHECKING

# "modpath" must be first of our modules
# pylint: disable=wrong-import-position
# ruff: noqa: E402
from pi_base.modpath import app_dir
from pi_base.lib.loggr import ColorCodes, Loggr
from pi_base.lib.app_utils import AtDict, Flag, run_maybe_async
from pi_base.lib.os_utils import walklevel

from .tester_common import TestError
from .dut_api import DutControlType, DutControlInterface
from .test_script_defines import RESULT_BLOCK_BEGIN, RESULT_BLOCK_END
from .test_commit_callbacks import ResultCommitToFileCallback, ResultCommitToGoogleDriveCallback
from .test_result_writer import ResultsWriter

# from my_coolname import generate as coolname_generate


if TYPE_CHECKING:
    from collections.abc import Awaitable
    from io import TextIOWrapper
    from .data_entry import DataEntryInterface
    from .tester_api import TesterControlInterface

MAX_LINES_IN_SHORT_INFO = 2


def excel_col_name(col_num: int) -> str:
    """Convert an integer column (1-based) to an Excel column name."""
    chars = []
    while col_num > 0:
        chars.append(chr((col_num - 1) % 26 + ord("A")))
        col_num = (col_num - 1) // 26
    return "".join(chars[::-1])  # Return chars in reversed order


class CommandResult:
    """Wrapper for delivering command results."""

    def __init__(
        self,
        returncode: TestError,
        results=None,
        test_info="",
        block_data=None,
        command_name: Optional[str] = None,
        checks: Optional[int] = None,
        lineno: Optional[int] = None,
        elapsed_time: Optional[float] = None,
    ) -> None:
        """Constructor.

        Args:
            returncode: One of TestError.ERR_*
            results: Measurement results (singular)
            test_info: Test failure description
            block_data: Measurement results (block, to be written over multiple rows in results file). Defaults to None.
            command_name : Name of the command that this result is from
            checks : Number of checks
            lineno : Line in the script this command is from
            elapsed_time : Elapsed time in seconds
        """
        if results is None:
            results = []
        self.returncode = returncode
        self.results = results
        self.test_info = test_info
        self.block_data = block_data
        self.command_name = command_name
        self.checks = checks
        self.lineno = lineno
        self.elapsed_time = elapsed_time

    def full(self):
        """Split out new style data."""
        return self.returncode, self.results, self.test_info, self.block_data

    def triplet(self):
        """Split out old style data (without block_data)."""
        return self.returncode, self.results, self.test_info


class RunResult(Enum):
    NONE = None
    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    ERROR = "error"

    def __str__(self):
        return self.value

    def __repr__(self):
        return self.name


class TestScriptCommand:
    def __init__(
        self,
        command: str,
        method: Optional[Callable[[TestScriptCommand, str, list[str]], CommandResult] | Callable[[TestScriptCommand, str, list[str]], Awaitable[CommandResult]]] = None,
        args: Optional[list[str]] = None,
        results: Optional[list[str]] = None,
        checks: int = 0,
        a_class: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        self.command = command
        self.method = method  # `method` is allowed to be None here only for plugin mechanism that auto-assigns it to the default execute() method.
        self.args = args
        self.results = results
        self.checks = checks
        self.a_class = a_class
        self.description = description
        self.module: Optional[ModuleType] = None
        self.obj: Optional[type[TestScriptCommandPluginInterface]] = None

    @classmethod
    def is_num_tokens_ok(cls, num_tokens: int, num_expected_tokens: range | int) -> bool:
        """Confirms that the number of tokens present in the line is the number of expected.

        If they dont match then the script is stopped since as future behavior can no longer
        be guaranteed.

        Args:
            num_tokens              : Number of tokens present in the line
            num_expected_tokens     : Number (or a range) of tokens expected

        Returns:
            True if the number of tokens is valid for the command.
        """
        result = True
        if isinstance(num_expected_tokens, range):
            if num_tokens not in num_expected_tokens:
                result = False
        elif num_tokens != num_expected_tokens:
            result = False
        return result

    def run(self, cmd: str, tokens: list[str], input_row_num: int, loggr: Loggr) -> CommandResult:
        if not self.method:
            raise ValueError(f"Expected method to be defined in {self.__class__.__name__}.")
        args_cnt_max = len(self.args) if self.args else 0
        args_cnt_min = len([c for c in self.args if not c.endswith("?")]) if self.args else 0  # Non-optional args
        if args_cnt_min != args_cnt_max:
            args_cnt = range(args_cnt_min, args_cnt_max + 1)
        else:
            args_cnt = args_cnt_max

        command_result = CommandResult(TestError.ERR_TEST_INCOMPLETE)
        if TestScriptCommand.is_num_tokens_ok(len(tokens) - 1, args_cnt):
            start_time = timer()
            # Note that tokens[0] (the command name) is always passed in so methods can be overloaded
            try:
                command_result = run_maybe_async(self.method(self, tokens[0], tokens[1 : args_cnt_max + 1]))
                if not isinstance(command_result, CommandResult):
                    raise TypeError('Expected command "{tokens[0]}" to produce type "CommandResult", got "{type(command_result)}"')

            except:  # Script failure
                command_result.returncode = TestError.ERR_SCRIPT_FAILURE
                command_result.test_info = traceback.format_exc()

            command_result.command_name = tokens[0]
            command_result.checks = self.checks
            command_result.lineno = input_row_num
            command_result.elapsed_time = timer() - start_time
        else:
            loggr.error(f"Number of tokens ({len(tokens) - 1}) on script line {input_row_num} for command " + f'"{tokens[0]}" does not match the expected number of tokens ({args_cnt})).')
            command_result.returncode = TestError.ERR_INVALID_COMMAND_ARGUMENT
        if not command_result.test_info and self.checks:
            loggr.warning(f'Command "{cmd}" is declared as making {self.checks} checks, but did not provide test_info for result={command_result.returncode.name}.')
            command_result.test_info = "(N/A)"  # Fixup missing test_info to be non-empty, which many functions rely upon.
        return command_result


class TestScriptCommandPluginInterface:
    def __init__(self, test_script: TestScript):
        if not test_script:
            raise ValueError("Please provide test_script argument")
        self.test = test_script

        self.command: Optional[TestScriptCommand] = self.define_command()
        if self.command is None:
            raise RuntimeError("TestScriptCommandPluginInterface.command is not set - check that `define_command()` is implemented correctly")
        if not hasattr(self, "COMMAND"):
            self.COMMAND = self.command.command
        if not self.command.method:
            if type(self).execute_async != TestScriptCommandPluginInterface.execute_async:
                self.command.method = self.execute_async
                if type(self).execute != TestScriptCommandPluginInterface.execute:
                    raise TypeError(f"Both execute and execute_async are defined in {self.__class__.__name__}, only one must be defined")
            elif type(self).execute != TestScriptCommandPluginInterface.execute:
                self.command.method = self.execute
            else:
                raise TypeError(f"Both execute and execute_async are NOT defined in {self.__class__.__name__}, one must be defined")
        self.command.a_class = self.command.a_class or self.__class__.__name__
        self.command.description = self.command.description or self.__class__.__doc__

    def prep_for_measured(self, command: Optional[str] = None) -> list:
        """Helper method to ensure measurements data section is created."""
        if not command:
            if not hasattr(self, "COMMAND"):
                raise ValueError(f"{self.__class__.__name__}.COMMAND is not set")
            command = self.COMMAND
        if self.test.measured is None:
            self.test.measured = {}
        if command not in self.test.measured:
            self.test.measured[command] = []
        return self.test.measured[command]

    def token_int_val(self, tokens: list[str], i: int, cmd: TestScriptCommand) -> tuple[TestError, int, str]:
        """Helper method for tokens (command args) str -> int conversion."""
        if i >= len(tokens):
            return TestError.ERR_INVALID_COMMAND_ARGUMENT, 0, f"Row {self.test.input_row_num} column {i+1} not filled"

        try:
            return TestError.ERR_OK, int(tokens[i]), ""
        except:
            param = cmd.args[i] if cmd.args else f"arg{i}"
            message = f'Row {self.test.input_row_num} column {i+1} ({excel_col_name(i+1)}): Fail using arg "{param}" value "{tokens[i]}", expected integer.'
            return TestError.ERR_INVALID_COMMAND_ARGUMENT, 0, message

    def token_float_val(self, tokens: list[str], i: int, cmd: TestScriptCommand) -> tuple[TestError, float, str]:
        """Helper method for tokens (command args) str -> int conversion."""
        if i >= len(tokens):
            return TestError.ERR_INVALID_COMMAND_ARGUMENT, 0, "Row {self.test.input_row_num} column {i+1} not filled"
        try:
            return TestError.ERR_OK, float(tokens[i]), ""
        except:
            param = cmd.args[i] if cmd.args else f"arg{i}"
            message = f'Row {self.test.input_row_num} column {i+1} ({excel_col_name(i+1)}): Fail using arg "{param}" value "{tokens[i]}", expected float.'
            return TestError.ERR_INVALID_COMMAND_ARGUMENT, 0, message

    def define_command(self):
        raise NotImplementedError("Please implement `.define_command()` method")

    def implements(self) -> TestScriptCommand:
        if not self.command:
            raise ValueError(f"Expected command to be defined in {self.__class__.__name__}.")
        return self.command

    async def execute_async(self, command: TestScriptCommand, cmd, tokens) -> CommandResult:
        # raise NotImplementedError("Please implement `.execute()` method")
        return CommandResult(TestError.ERR_NOT_IMPLEMENTED)

    def execute(self, command: TestScriptCommand, cmd, tokens) -> CommandResult:
        # return CommandResult(TestError.ERR_DUT_NOT_SUPPORTED, ["N/A", "N/A", "N/A", "N/A", "N/A"], None)
        # raise NotImplementedError("Please implement `.execute()` method")
        return CommandResult(TestError.ERR_NOT_IMPLEMENTED)


class TestScriptCommandOperatorLog(TestScriptCommandPluginInterface):
    """Logs the message to the loggr."""

    def define_command(self) -> TestScriptCommand:
        return TestScriptCommand(command="operator_log", args=["message"], results=[], checks=0)

    def execute(self, command: TestScriptCommand, cmd: str, tokens: list[str]) -> CommandResult:
        self.test.loggr.color_print(tokens[0], color_code=ColorCodes.BLUE)
        return CommandResult(TestError.ERR_OK)


class TestScriptCommandOperatorInput(TestScriptCommandPluginInterface):
    """Logs the message to the loggr, inputs the response from the operator."""

    def define_command(self) -> TestScriptCommand:
        return TestScriptCommand(command="operator_input", args=["message"], results=["barcode_text"], checks=0)

    def execute(self, command: TestScriptCommand, cmd: str, tokens: list[str]) -> CommandResult:
        message = tokens[0]
        self.test.loggr.color_print(message, color_code=ColorCodes.BLUE)
        fnc_input = input
        # input_str = self.fnc_input(message + " and hit [Enter]: ").strip()
        input_str = fnc_input(message + " and hit [Enter]: ").strip()

        return CommandResult(TestError.ERR_OK, [input_str])


class TestScriptCommandTestSummary(TestScriptCommandPluginInterface):
    """Generates a summary result CSV that can be parsed and saved."""

    COMMAND = "test_summary"

    def define_command(self) -> TestScriptCommand:
        return TestScriptCommand(command=self.COMMAND, args=[], results=[], checks=0)

    def execute(self, command: TestScriptCommand, cmd: str, tokens: list[str]) -> CommandResult:
        self.test.determine_run_result(None)  # Early conclusion of test result. Subsequent command can change that.

        comment_mark = "##"
        summary = [f"{comment_mark},lineno,name,run_time,returncode,info"]
        for result in self.test.dut_transcript.all:
            line = (
                f"{comment_mark},L{result.lineno:03d},{result.command_name},{time.strftime(':%M:%S', time.gmtime(result.elapsed_time))},"
                f"{result.returncode}, {'' if result.test_info is None else result.test_info}"
            )
            summary.append(line)

        final_result = self.test.get_pass_fail()
        summary.append(f"{comment_mark},num_pass,num_fail,total_tests,device_result")
        summary.append(f"{comment_mark},{self.test.pass_cnt},{self.test.fail_cnt},{self.test.test_cnt},{final_result}")
        summary = "\n".join(summary)
        measured = self.prep_for_measured()
        measured.append(summary)
        self.test.results_writer.add_script_line(summary)
        return CommandResult(TestError.ERR_OK)


def filter_strings(strings: list[str], filters: list[str], return_matched: bool = False) -> list[str]:
    # TODO: (when needed) Move to app_utils
    filtered_strings = []
    for string in strings:
        matches_filter = False
        for fltr in filters:
            if fnmatch.fnmatch(string, fltr):
                matches_filter = True
                break
        if matches_filter == return_matched:
            filtered_strings.append(string)
    return filtered_strings


def get_longest_common_path(path1: str, path2: str) -> tuple[str, str, str, str, str]:
    # TODO: (when needed) Move to app_utils
    path1 = os.path.abspath(path1)
    path2 = os.path.abspath(path2)
    path1_dirname = path1 if os.path.isdir(path1) else os.path.dirname(path1)
    path2_dirname = path2 if os.path.isdir(path2) else os.path.dirname(path2)

    # Get all the elements in the path
    path1_elements = path1.split(os.path.sep)
    path2_elements = path2.split(os.path.sep)

    # Find the longest common prefix
    i = 0
    while i < min(len(path1_elements), len(path2_elements)):
        if path1_elements[i] == path2_elements[i]:
            i += 1
        else:
            break

    common_prefix = os.path.sep.join(path1_elements[:i] if i < len(path1_elements) else path1_elements)
    path1_remainder = os.path.join(*path1_elements[i:]) if i < len(path1_elements) else ""
    path2_remainder = os.path.join(*path2_elements[i:]) if i < len(path2_elements) else ""
    path1_relative = os.path.relpath(path1, path2_dirname)
    path2_relative = os.path.relpath(path2, path1_dirname)

    return common_prefix, path1_remainder, path2_remainder, path1_relative, path2_relative


def get_command_plugins(
    directory: Optional[str], level: int = 1, file_filter: Optional[list[str]] = None, loggr: Optional[Loggr] = None
) -> list[tuple[ModuleType, type[TestScriptCommandPluginInterface]]]:
    plugins: list[tuple[ModuleType, type[TestScriptCommandPluginInterface]]] = []
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    # Same as `for root, dirs, filenames in os.walk(directory):`, but with limited depth
    for root, _dirs, filenames in walklevel(directory, level):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            if file_filter:
                file_basename = os.path.basename(os.path.splitext(filename)[0])
                filter_res = filter_strings([file_basename], file_filter, return_matched=True)
                if not filter_res:
                    continue

            module_imported: Optional[ModuleType] = None
            module_path = os.path.join(root, filename)
            prefix, _path1_rem, _path2_rel, _path1_from2, module_path_from_root = get_longest_common_path(SCRIPT_DIR, module_path)
            m1 = os.path.splitext(module_path_from_root)[0]
            is_rel = os.path.sep not in m1 or m1.startswith((os.path.curdir + os.path.sep, os.path.pardir + os.path.sep))
            # is_outside = m1.startswith(os.path.pardir + os.path.sep)
            m2 = m1.replace(os.path.pardir + os.path.sep, ".")
            m3 = "." + m2 if is_rel else m2
            module_pypath = m3.replace(os.path.sep, ".")
            package = os.path.basename(SCRIPT_DIR)
            if loggr:
                loggr.debug(f'Checking file "{module_path}" for command plugins, module_pypath={module_pypath}, package={package}, __package__={__package__}')

            modules: list[tuple[str | None, str]] = [
                (None, module_pypath.lstrip(".")),  # Try absolute path, without package
                (None, module_pypath.split(".")[-1]),  # Try bare module name, without package
            ]
            if __package__ and is_rel:
                modules.insert(0, (__package__, module_pypath))
            else:
                modules.append((package, "." + module_pypath if not is_rel else module_pypath))

            err = None
            i = -1
            for i, module in enumerate(modules):
                pkg, pypath = module
                try:
                    module_imported = importlib.import_module(pypath, pkg)
                except Exception as e:
                    err = e
                    continue
                # Successful import
                if loggr:
                    loggr.debug(f'Imported module "{module_path}" using package={pkg}, path={pypath} ({i + 1} of {len(modules)})')
                break

            # module = __import__(module_name)
            # module = importlib.import_module(module_name)
            if module_imported:
                for _filename, obj in inspect.getmembers(module_imported):
                    if inspect.isclass(obj) and obj != TestScriptCommandPluginInterface and issubclass(obj, TestScriptCommandPluginInterface):
                        plugins.append((module_imported, obj))
            elif loggr:
                loggr.error(f"Failed to import {module_path}: {err}")
    return plugins


class TestTranscript:
    def __init__(self) -> None:
        self.all: list[CommandResult] = []
        self.passed: list[CommandResult] = []
        self.failed: list[CommandResult] = []

    def reset(self) -> None:
        self.all = []
        self.passed = []
        self.failed = []

    def add(self, test_result: CommandResult) -> None:
        """Add command / test result to the transcipt and to the pass/fail dictionary of all tests.

        Args:
            test_result : CommandResult of the completed command / test
        """
        self.all.append(test_result)
        if test_result.returncode == TestError.ERR_OK:
            self.passed.append(test_result)
        else:
            self.failed.append(test_result)

    @property
    def pass_cnt(self):
        return len([c for c in self.passed if (c.checks or 0) > 0])

    @property
    def fail_cnt(self):
        return len([c for c in self.failed if (c.checks or 0) > 0])

    @property
    def test_cnt(self):
        return len([c for c in self.all if (c.checks or 0) > 0])


class TestScript:
    """Test Script executor."""

    VALID_RETURN_CODES = (TestError.ERR_OK, TestError.ERR_TEST_FAIL)
    DISCONNECT_RETURN_CODES = (TestError.ERR_PORT_CLOSED, TestError.ERR_TESTER_DISCONNECTED, TestError.ERR_DUT_DISCONNECTED)

    def __init__(
        self,
        results_writer: ResultsWriter,
        loggr: Loggr,
        verbose: bool = False,
        debug: bool = False,
        data_entry: Optional[DataEntryInterface] = None,
        ignore_ble: bool = False,
        plugins_dir: Optional[str] = None,
        tester_control: Optional[TesterControlInterface] = None,
        dut_control: Optional[DutControlInterface] = None,
    ) -> None:
        if not loggr:
            raise ValueError("Please provide loggr argument")
        if not hasattr(loggr, "color_print"):
            raise ValueError('Please provide loggr argument with additional "color_print()" method')
        if not hasattr(loggr, "log_box"):
            raise ValueError('Please provide loggr argument with additional "log_box()" method')

        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

        self.results_writer = results_writer
        self.loggr = loggr
        self.verbose: bool = verbose
        self.debug: bool = debug
        self.data_entry: Optional[DataEntryInterface] = data_entry
        self.plugins_dir: Optional[str] = plugins_dir or SCRIPT_DIR
        self.dut_control: Optional[DutControlInterface] = dut_control
        self.tester_control: Optional[TesterControlInterface] = tester_control

        # Dictionary of commands, extended by plugins:
        self.commands: list[TestScriptCommand] = []

        self.plugins = AtDict()
        self.plugins.cnt_embedded = self.add_commands_from_plugins(SCRIPT_DIR, 1, file_filter=[self.__class__.__module__.rsplit(".", maxsplit=1)[-1]])
        self.plugins.cnt_extensions = self.add_commands_from_plugins(self.plugins_dir, 1, file_filter=["*plugin*"])

        self.commands_map = {cmd.command: cmd for cmd in self.commands}

        # Unfortunately, we have to list all properties here, duplicating code in self.dut_restart(), as
        # pylint is dumb and throws W0201 if we don't.
        # ATTENTION: When adding new properties, also add them to self.reset()

        self._stop = Flag(value=False)  # Signal for stopping long-running operations, can be passed by ref.

        self.start_time = time.time()

        self.dut_transcript = TestTranscript()
        self.tester_transcript = TestTranscript()
        self.measured: dict[
            str, list
        ] = {}  # Storage for all plugin commands measurements. Each measurement command is allowed to add it's name to the dict, and store any data as needed in the object under that key.
        self.plugin_config: dict[str, Any] = {}  # Storage for all plugin config settings. TODO: (when needed) Naming TBD.
        # Example of properties to store in self.measured
        # self.access_point_id = None
        # self.label_out_file: Optional[str] = None

        self.lot_num: Optional[str] = None
        self.board_ver: Optional[str] = None
        self.firmware_ver: Optional[str] = None
        self.dut_id: Optional[str] = None
        self.chip_ver: Optional[str] = None
        self.device_name: Optional[str] = None

        self.input_row_num: int = -1
        self.fail_line: Optional[int] = None
        self.fail_cmd: Optional[str] = None
        self.run_result: RunResult = RunResult.NONE
        self.run_result_code: Optional[TestError] = None
        self.last_returncode: Optional[TestError] = None

        # self.tester_board_ver, self.tester_firmware_ver, self.tester_mac, self.tester_chip_ver = None, None, None, None

        self.dut_restart()

    def __del__(self):
        if self.dut_control:
            try:
                self.dut_control.close()
            except:  # noqa: S110
                pass

        if self.tester_control:
            try:
                self.tester_control.close()
            except:  # noqa: S110
                pass

    @property
    def pass_cnt(self):
        return self.dut_transcript.pass_cnt

    @property
    def fail_cnt(self):
        return self.dut_transcript.fail_cnt

    @property
    def test_cnt(self):
        return self.dut_transcript.test_cnt

    def add_commands_from_plugins(self, directory: Optional[str], level: int = 1, file_filter: Optional[list[str]] = None) -> int:
        # Discover plugins with addditional commands:
        plugins = get_command_plugins(directory, level, file_filter, self.loggr)  # TODO: (now) Implement plugins directory (especially mechanism to transfer them to RPi)
        count = 0
        for plugin in plugins:
            module, obj = plugin
            try:
                instance = obj(self)
                command: TestScriptCommand = instance.implements()
                command.module = module
                command.obj = obj
            except Exception as e:
                self.loggr.warning(f'Error "{e}" importing plugin from {module.__name__}:{obj.__name__}, skipped.')
                continue
            cmds = [cmd for cmd in self.commands if cmd.command == command.command]
            if cmds:
                prev_str = " The previous command is not from a plugin"
                if cmds[-1].module and cmds[-1].obj:
                    prev_module = cmds[-1].module.__name__
                    prev_obj = cmds[-1].obj.__name__
                    prev_str = f" The previous command is defined in {prev_module}:{prev_obj}"
                msg = f'Duplicate command "{command.command}" in {module.__name__}:{obj.__name__}.{prev_str}'
                self.loggr.error(msg)
                raise ValueError(msg)
            self.commands.append(command)
            self.loggr.info(f'Added command "{command.command}" from {module.__name__}:{obj.__name__}.')
            count += 1
        return count

    # region - SCRIPT HELPERS
    def show_script_documentation(self) -> None:
        """Prints out the script documentation for commands."""
        print("------------ COMMANDS ------------ ")
        for cmd in self.commands:
            print(f"Command: {cmd.command}", end="")
            print(f'{", ".join([""] + (cmd.args or []))}')
            if len(cmd.results or []) > 0:
                print(f'Outputs: {", ".join(cmd.results or [])}')
            else:
                print("Outputs: N/A")
            print()
        print("------------ ERROR CODES ------------ ")
        for returncode in TestError:
            code = returncode.id
            name = returncode.name
            description = returncode.string
            print(f"{code:05d} {name:<32} {description}")

    def _log_test_result(self, cmd, command_result) -> None:
        """Prints to the console the test result."""
        command = cmd.command
        line = command_result.lineno or self.input_row_num
        details = command_result.test_info or ""
        if cmd.checks:
            # Only show testcases ('checks' is not 0)
            test_result = command_result.returncode == TestError.ERR_OK
            if test_result:
                # ? TBD: We may want to NOT print the `details` for PASS tests (or need to scrub all messages to not imply something is wrong, as they were "fail_details" originally)
                self.loggr.color_print(f"PASS Test L{line:03d} {command} -- {details}", color_code=ColorCodes.GREEN)
            else:
                self.loggr.color_print(f"FAIL Test L{line:03d} {command} -- {details}", color_code=ColorCodes.RED)
        elif command_result.returncode != TestError.ERR_OK:
            self.loggr.color_print(f"ERR  Command L{line:03d} {command} -- {details}", color_code=ColorCodes.RED)

    def get_pass_fail(self) -> str:
        """Returns PASS/FAIL string based on test_result."""
        return self.run_result.name
        # return "PASS" if test_result else "FAIL"

    def abort(self):
        """Aborts the running script."""
        self._stop.value = True
        # TODO: (soon) Implement change observer in Flag class, then self.tester_control/self.dut_control could subscribe to the change.
        if self.dut_control:
            self.dut_control.abort()
        if self.tester_control:
            self.tester_control.abort()

    def tester_restart(self):
        self.tester_transcript.reset()
        if self.tester_control:
            self.tester_control.reset_info()

    def dut_restart(self):
        """Resets the test script state."""
        self.start_time = time.time()

        self.dut_transcript.reset()
        self.measured = {}

        self.lot_num = None
        self.board_ver = None
        self.firmware_ver = None
        self.dut_id = None
        self.chip_ver = None
        self.device_name = None

        self.input_row_num = -1
        self.fail_line = None
        self.fail_cmd = None
        self.run_result = RunResult.NONE
        self.run_result_code = None
        self.last_returncode = None

        if self.dut_control:
            self.dut_control.reset_info()

    def _soak(self, delay_s):
        # TODO: (when needed when both self.tester_control and self.dut_control are set) Implement threading and parallel soak(), or better use periodic tasks to pump data.
        if self.tester_control:
            if self.dut_control:
                raise NotImplementedError("Cannot soak both tester_control and dut_control. Implement threading.")
            self.tester_control.soak(delay_s)
        elif self.dut_control:
            self.dut_control.soak(delay_s)
        elif delay_s is not None:
            self.loggr.info(f"Soaking for {delay_s} seconds.")
            end_time = timer() + delay_s
            while True:
                if self._stop.value:  # Check abort
                    return TestError.ERR_ABORT
                if timer() > end_time:
                    break
                time.sleep(0.1)
        return TestError.ERR_OK

    def get_tester_versions(self):
        return self.tester_control.get_versions() if self.tester_control else ("N/A", "N/A", "N/A", "N/A")

    def get_dut_versions(self):
        if not self.dut_control:
            return ("N/A", "N/A", "N/A", "N/A")

        self.device_name, self.board_ver, self.firmware_ver, self.dut_id, self.chip_ver = None, None, None, None, None
        self.dut_id, self.board_ver, self.firmware_ver, self.chip_ver = self.dut_control.get_versions()
        if self.dut_id not in ["NA", None]:
            # TODO: (now) Move into dut_control:
            command_result = self.generate_name(self.dut_id, self.board_ver, self.firmware_ver, self.chip_ver)
            if command_result.returncode != TestError.ERR_OK:
                command_result.results = [self.board_ver, self.firmware_ver, self.dut_id, self.chip_ver, None]
                return command_result
            self.device_name = command_result.results[0]
        return self.dut_id, self.board_ver, self.firmware_ver, self.chip_ver

    def generate_name(self, device_id, board_ver, firmware_ver, chip_ver):
        if not device_id or device_id == "NA":  # ?  or len(device_id) != 17:
            # No device_id retrieved from the device
            return CommandResult(TestError.ERR_NO_PREVIOUS_DATA_COLLECTED, [None])

        # try:
        #     device_name = coolname_generate(device_id, ver, autoinstall=True, loggr=self.loggr)
        # except FileNotFoundError as err:
        #     test_info = f'Error "{err}" when trying to generate device name from device_id.'
        #     self.loggr.error(test_info)
        #     return CommandResult(TestError.ERR_TESTER_NOT_CONFIGURED, [None], test_info)
        # return CommandResult(TestError.ERR_OK, [device_name], None)
        return CommandResult(TestError.ERR_TESTER_NOT_CONFIGURED, [None], "generate_name() method not implemented.")

    def indicator_set(self, state: str) -> TestError:
        if self.tester_control:
            return self.tester_control.indicator_set(state)
        return TestError.ERR_OK

    # endregion

    # region DEVICE INTERACTION
    def post(self) -> TestError:
        # Restore all instrument settings that test may fiddle with
        start_time = timer()
        self.loggr.debug("Test.post()")

        if self.dut_control:
            self.dut_control.post()

        if self.tester_control:
            self.tester_control.post()

        result = CommandResult(TestError.ERR_OK, checks=0, command_name="post", elapsed_time=timer() - start_time, lineno=999)
        self.tester_transcript.add(result)
        return TestError.ERR_OK

    def pre(self) -> TestError:
        """Test pre - called every time when tester software loads.

        Opens all necessary resources.

        Returns:
            Error code
        """
        self.loggr.debug("Test.pre()")
        self.tester_transcript.reset()
        start_time = timer()
        self.tester_restart()
        returncode = TestError.ERR_OK
        for _ in range(1):  # Emulate goto by `break`
            if self._stop.value:  # Check abort
                returncode = TestError.ERR_ABORT
                break

            if self.tester_control:
                returncode = self.tester_control.pre()
                if returncode != TestError.ERR_OK:
                    break

            if self.dut_control:
                returncode = self.dut_control.pre()
                if returncode != TestError.ERR_OK:
                    break

        result = CommandResult(returncode, checks=0, command_name="pre", elapsed_time=timer() - start_time, lineno=0)
        self.tester_transcript.add(result)
        return returncode

    def dut_start(self) -> tuple[TestError, str]:
        start_time = timer()
        self.dut_restart()
        self.results_writer.clear_results()
        returncode = TestError.ERR_OK

        for _ in range(1):  # Emulate goto by `break`
            if self.tester_control:
                returncode = self.tester_control.dut_start()
                if returncode != TestError.ERR_OK:
                    break

            if self.dut_control:
                returncode = self.dut_control.dut_start()
                if returncode != TestError.ERR_OK:
                    break

        dut_id = ""  # TODO: (when needed) Get device_id from DUT while opening in dut_start
        result = CommandResult(returncode, checks=0, command_name="dut_start", elapsed_time=timer() - start_time, lineno=0)
        self.dut_transcript.add(result)
        return returncode, dut_id

    def dut_end(self) -> TestError:
        start_time = timer()
        returncode = TestError.ERR_OK

        if self.dut_control:
            returncode = self.dut_control.dut_end()

        if self.tester_control:
            returncode = self.tester_control.dut_end()

        result = CommandResult(returncode, checks=0, command_name="dut_end", elapsed_time=timer() - start_time, lineno=999)
        self.dut_transcript.add(result)
        return returncode

    def _row_int_val(self, tokens, i, default=0):
        c = tokens[i]
        try:
            c_int = int(c)
        except:
            self.loggr.warning(f'Row {self.input_row_num} cell {i+1}: Fail using value "{c}", expected integer, using "{default}" instead.')
            c_int = default
        return c_int

    def _add_to_transcript(self, test_result: CommandResult) -> None:
        """Add command / test result to the transcipt and to the pass/fail dictionary of all tests.

        Args:
            test_result : CommandResult of the completed command / test
        """

    def _cmd_get_versions(self, cmd, tokens) -> CommandResult:
        if not self.dut_control:
            return CommandResult(TestError.ERR_DUT_NOT_SUPPORTED, ["N/A", "N/A", "N/A", "N/A", "N/A"])
            # raise ValueError("No DUT serial connected.")
        self.get_dut_versions()  # Use side effect - setting properties
        return CommandResult(TestError.ERR_OK, [self.dut_id, self.board_ver, self.firmware_ver, self.chip_ver, self.device_name])

    # endregion

    def _run_one_line(self, tokens: list[str]) -> tuple[TestError, list[str], str]:
        """Parse the CSV line and takes the appropriate action.

        Args:
            tokens : list of parsed line tokens from command CSV file

        Returns:
            Tuple of error code, list of results, test info
        """
        returncode = TestError.ERR_OK
        results = []  # results = ['some result 1', 'some result 2']
        test_info = ""

        if self._stop.value:  # Check abort
            return TestError.ERR_ABORT, [], ""

        if len(tokens) and not tokens[0].startswith("#"):
            cmd = self.commands_map.get(tokens[0])
            if cmd:
                # Use Optional args 'somearg?'
                command_result = cmd.run(tokens[0], tokens, self.input_row_num, self.loggr)

                returncode, results, test_info, block_data = command_result.full()
                # Should not count commands that don't check (i.e. "test") something. Some commands are not test cases.
                # TODO: (soon) Decide if makes sense to exclude non-checks: if cmd.checks: #?? or returncode != TestError.ERR_OK:
                # Failing non-checks should abort??
                self.dut_transcript.add(command_result)
                self._log_test_result(cmd, command_result)

                if block_data is not None:
                    # ? cleaned_output = [[str(result).strip() for result in line] for line in block_data]
                    self.results_writer.add_device_response(block_data)
                    # For commands with block results, do not write results out.
                elif cmd.results:
                    self.results_writer.add_result(result_header=", ".join(cmd.results), result_line=", ".join([str(c) for c in results]), returncode=returncode)

            else:
                self.loggr.error(f'Row {self.input_row_num}: Unknown command "{tokens[0]}", stopping.')
                returncode = TestError.ERR_INVALID_COMMAND
                results = ["UNKNOWN COMMAND"]

        # Check for stop semaphore
        if self._stop.value and returncode in [TestError.ERR_OK, TestError.ERR_OUTPUT_WRITE_OVERRIDE]:
            returncode = TestError.ERR_ABORT
            results = []
            test_info = ""

        elif returncode not in [TestError.ERR_OK, TestError.ERR_TEST_FAIL, TestError.ERR_SCRIPT_FAILURE]:
            test_info = self.describe_error(returncode)

        return returncode, results, test_info

    def determine_run_result(self, returncode: Optional[TestError] = None) -> TestError:
        if self.last_returncode is None:
            if returncode is None:
                returncode = TestError.ERR_OK
        elif returncode is None:
            returncode = self.last_returncode
        elif returncode != self.last_returncode:
            self.loggr.warning(f'Test result {self.last_returncode.name} was changed to {returncode.name} by other commands since "test_summary" command.')

        # returncode contains result from the last command. Preserve as it may differ from the result.
        self.last_returncode = returncode

        # Any error besides pass/fail is considered abnormal, terminates the test sequence, and returned to caller
        if returncode == TestError.ERR_OK and self.fail_cnt == 0:
            self.run_result = RunResult.PASS
            self.run_result_code = TestError.ERR_OK
        elif returncode in TestScript.VALID_RETURN_CODES:
            self.run_result = RunResult.FAIL
            self.run_result_code = TestError.ERR_TEST_FAIL
        else:
            self.run_result = RunResult.ERROR
            self.run_result_code = returncode
        return self.run_result_code

    def exec_csv_fd(self, lot_num: str, in_file_fd: TextIOWrapper, in_file_name: str) -> tuple[TestError, None | str, None | str]:
        # Acquire control over DUT
        self.loggr.info("Connecting to device...")
        self.run_result = RunResult.NONE
        self.last_returncode: Optional[TestError] = None
        returncode, dut_id = self.dut_start()
        if returncode != TestError.ERR_OK:
            res = self.determine_run_result(returncode)
            return res, None, None

        # self.loggr.info(f'\nTesting {dut_info}')
        self.lot_num = lot_num
        self.loggr.info(f'Reading commands from "{in_file_name}" file.')

        # Read raw lines for passing through to results file
        in_file_fd.seek(0)
        raw_lines = in_file_fd.readlines()
        csvreader = csv.reader(raw_lines, dialect="excel", delimiter=",", quotechar='"', skipinitialspace=True)

        returncode = TestError.ERR_OK
        skipping_block = False
        for line_number, row in enumerate(csvreader, 1):
            # Tokenize (strip and clip all after end-of line comments))
            tokens = []
            for i, c_in in enumerate(row):
                c = c_in.strip()  # Strip comments in cells except first:
                if i > 0 and len(c) > 0 and c[0] == "#":
                    # Remove all cells past the comment '#'
                    break
                tokens.append(c)

            if skipping_block:
                # If we are in the middle of a previous Result block response,
                # Result blocks: keep skipping until the end of the response is reached
                if RESULT_BLOCK_END in tokens[0]:
                    # Result block end - skip
                    skipping_block = False
                continue

            if len(tokens) == 0 or not tokens[0]:
                # Empty line: Prevent tripping in the following checks. Will re-check below.
                pass
            elif RESULT_BLOCK_BEGIN in tokens[0]:
                # Result blocks: Skip and don't pass to output self.results_write
                skipping_block = True
                continue
            elif tokens[0].startswith("##"):
                # Result line: Skip and don't pass to output self.results_write
                continue

            # Output the raw line to preserve spacing (cleaner diff between output and input files)
            self.input_row_num = line_number
            self.results_writer.add_script_line(raw_lines[line_number - 1])

            if len(tokens) == 0 or not tokens[0]:
                # Empty line: Skip
                continue

            # We don't skip Comment lines here as they take time to write out, so we let self.run() process them to detect Abort in self._stop.value:
            returncode, results, test_info = self._run_one_line(tokens)

            if returncode not in TestScript.VALID_RETURN_CODES:
                # Any error besides pass/fail is considered abnormal, terminates the test sequence, and returned to caller
                self.fail_line = line_number
                self.fail_cmd = tokens[0]
                self.results_writer.add_script_line(test_info)  # Write the stack trace to the output result
                break

        tester_info = self.get_tester_info()
        dut_info = self.get_dut_info()
        self.dut_end()

        res = self.determine_run_result(returncode)
        # if self.test_cnt > 0:
        #     if self.fail_cnt == 0:
        #         self.loggr.print(f'PASS {self.test_cnt} tests.')
        #     else:
        #         self.loggr.print(f'FAIL {self.fail_cnt} of {self.test_cnt} tests.')
        return res, tester_info, dut_info

    def exec_csv(self, lot_num: str, in_file_name: str) -> tuple[TestError, None | str, None | str]:
        returncode = TestError.ERR_OK
        tester_info = None
        dut_info = None
        try:
            with open(in_file_name, newline="", encoding="utf-8") as in_file_fd:
                try:
                    returncode, tester_info, dut_info = self.exec_csv_fd(lot_num, in_file_fd, in_file_name)
                # except OSError as err: # TODO: (soon) Implement detecting serial port disconnect or other similar IO failures. Will need to remove "catch"es in many places.
                #     self.loggr.error(f'Error {err}. Looks like tester was disconnected.')
                #     return TestError.ERR_PORT_CLOSED
                # except SerialCantControlDevice as err:
                #     self.loggr.error(f'Error "{err}" when executing test script file "{in_file_name}"')
                #     return TestError.ERR_DUT_DISCONNECTED, dut_info
                except Exception as err:
                    self.loggr.error(f'Error "{err}" when executing test script file "{in_file_name}"')
                    return TestError.ERR_FAIL, tester_info, dut_info
        except OSError as err:
            self.loggr.error(f'Error "{err}" when opening file "{in_file_name}"')
            return TestError.ERR_FILE_OPEN, tester_info, dut_info
        return returncode, tester_info, dut_info

    def describe_error(self, returncode: TestError) -> str:
        if returncode == TestError.ERR_OK:
            return "PASS"
        if returncode == TestError.ERR_TEST_FAIL:
            return "FAIL"

        code = returncode.id
        name = returncode.name
        description = returncode.string
        return f'code={name} ({code:05d}: {description}), L{self.fail_line or 0:03d} {self.fail_cmd or ""}'

    def get_tester_control_info(self):
        return self.tester_control.info() if self.tester_control else ""

    def get_tester_info(self):
        return self.tester_control.device_id if self.tester_control else ""

    def get_dut_control_info(self):
        return self.dut_control.info() if self.dut_control else ""

    def get_dut_info(self):
        return self.dut_control.device_id if self.dut_control else ""

    def write_report(self, reportfile, timestamp, elapsed_time, fields=None, **kwargs) -> None:
        """Write a row to a .CSV report file describing the test.

        Args:
            reportfile: File path to write to
            timestamp: Test start time
            elapsed_time: Test duration
            fields: Fields in the report file. Note: Changing fields on an existing report file is not going to adjust existing header and data rows.
            **kwargs: Values for the custom fields
        """
        self.loggr.info(f'Writing report file "{reportfile}"...')

        # timestamp = time.localtime(time.time())
        flashdate = time.strftime("%Y-%m-%d", timestamp)
        flashtime = time.strftime("%H:%M:%S", timestamp)
        # reportfile = os.path.join(label_dir, f'report_{time.strftime("%Y-%m-%d", timestamp)}.csv')
        if not fields:
            fields = [
                "date",
                "time",
                "device_name",
                # "mac", # TODO: (when needed) Add device Eth mac, WiFi mac, BLE mac
                "device_id",
                "test_success",
                "elapsed_time",
            ]
        fmt = ",".join(["{" + field + "}" for field in fields]) + "\n"
        header = "# " + ",".join(["" + field.replace("_", " ").title() + "" for field in fields]) + "\n"
        test_success = self.run_result == RunResult.PASS
        line = fmt.format(
            date=flashdate, time=flashtime, device_name=self.device_name, device_id=self.dut_id, test_success=test_success, lot_number=str(self.lot_num), elapsed_time=str(elapsed_time), **kwargs
        )
        file_existed = os.path.isfile(reportfile)
        # TODO: (soon) Set report file permissions - when running as root (from manager), should make it `chown pi:pi`. Perhaps a better fix is to make NOT run as root.
        with open(reportfile, "a+", encoding="utf-8") as f:
            if not file_existed:
                f.write(header)
            f.write(line)
        self.loggr.info("Done writing report file.")

    def print_summary(self, fmt=None, loggr=None, output_mode="fail_only") -> None:
        """Prints the test summary to a custom loggr or to the instance's `self.loggr`.

        Args:
            loggr : Logger, if None, will use self.loggr
            output_mode : Filter for tests to show.
                pass_only     -> Will output only passing tests with a check
                fail_only     -> Will output only failing tests with a check
                pass_and_fail -> Will output passing or failing tests with a check
                all           -> Will output all tests
        """
        if loggr is None:
            loggr = self.loggr

        if loggr is None:
            return

        if output_mode not in ("all", "pass_only", "fail_only", "pass_and_fail"):
            output_mode = "fail_only"

        left = "  "  # Can become an arg, if needed.
        info_max_len = 60
        if not fmt:
            # Default format
            fmt = "| {line:4} | {result:^8} | {time:^10} | {command:<20} | {info:<" + str(info_max_len) + "} |"
            # Acid test format for `empty` below:
            # fmt = '| {line:4} | {result:^8} | {command:<20} | {info:<' + str(info_max_len) + '} | {time:^10} |'
        header = fmt.format(line="Line", result="Result", time="Run Time", command="Command", info="Info")
        s = ""
        empty = f" |\n{left}| {s:4} | {s:^8} | {s:^10} | {s:<20} | "  # TODO: (when needed) DRY - derive `empty` from the `fmt` arg in its most general form, as hard-coded empty will break for a custom fmt, see "Acid test" above.

        header_len = len(header)
        loggr.print(left + "=" * header_len)
        loggr.print(left + header)
        loggr.print(left + "-" * header_len)

        for _, t in enumerate(self.dut_transcript.all, 1):
            # Skip tests that shouldn't be printed out based on the output mode
            if (
                (output_mode == "pass_only" and (t.returncode != TestError.ERR_OK or t.checks == 0))
                or (output_mode == "fail_only" and (t.returncode != TestError.ERR_TEST_FAIL or t.checks == 0))
                or (output_mode == "pass_and_fail" and t.checks == 0)
            ):
                continue

            # if not t.test_info and t.returncode in TestScript.VALID_RETURN_CODES:
            #     continue
            info = t.test_info or ""
            time_str = time.strftime("%M:%S", time.gmtime(t.elapsed_time))

            if t.returncode == TestError.ERR_OK:
                rc_str = "PASS----" if (t.checks or 0) > 0 else "--------"
                color_code = ColorCodes.GREEN
                filter_text = "PASS"

            elif t.returncode == TestError.ERR_TEST_FAIL:
                rc_str = "----FAIL"
                color_code = ColorCodes.RED
                filter_text = "FAIL"

            else:
                rc_str = " ERROR! "
                color_code = ColorCodes.CYAN
                filter_text = "ERROR!"
                info = f"({t.returncode}) {self.describe_error(t.returncode)}"

            if info and len(info) > info_max_len:
                info_lines = [info[i : i + info_max_len] for i in range(0, len(info), info_max_len)]
                if t.returncode in TestScript.VALID_RETURN_CODES and len(info_lines) > MAX_LINES_IN_SHORT_INFO:
                    # For normal test outcome truncate long info to MAX_LINES_IN_SHORT_INFO lines
                    info_lines[1] = info_lines[1][: info_max_len - 4].strip() + " ..."
                    info_lines = info_lines[:2]
                # Handle special case when last line ends up being shorter than column:
                info_lines[-1] = info_lines[-1].ljust(info_max_len)
                info = empty.join(info_lines)

            # loggr.print(f'  | L{t.lineno:03d} | {rc_str} | {time_str:^6} | {t.command_name:20s} | {info}')
            loggr.color_print(left + fmt.format(line="L" + f"{t.lineno:03d}", result=rc_str, time=time_str, command=t.command_name, info=info or ""), color_code=color_code, filter_text=filter_text)
        loggr.print(left + "=" * header_len)


def cli(args) -> int:
    """Command Line Interface."""
    test_success = False
    start_time = timer()
    ignore_ports = ["/dev/ttyAMA0"] if os.name == "posix" else None
    ignore_ble = True

    results_directory = os.path.join(os.path.abspath(os.path.dirname(__file__)), "MfgTestResults")
    os.makedirs(results_directory, exist_ok=True)

    # Can also use tools.rpi/common/loggr.py here
    loggr = Loggr(level=logging.DEBUG if args.debug else logging.INFO)
    log_filename = "device_serial.log" if args.debug else None
    log_filename2 = "tester_serial.log" if args.debug else None

    # Validate args

    if args.csv and not args.lot_number:
        raise ValueError("Please provide lot number (with -L/--lot parameter)")

    if args.out_file is None:
        if args.csv:
            name, ext = os.path.splitext(os.path.basename(args.csv))
            args.out_file = f"{name}_results_{datetime.now().strftime('%m_%d_%Y__%H_%M_%S')}{ext}"
        else:
            args.out_file = "measurement_results.csv"

    out_file = args.out_file
    if os.path.dirname(out_file) == "":
        out_file = os.path.join(results_directory, out_file)
    out_file = os.path.realpath(out_file)
    loggr.info(f'Writing output results to "{out_file}" file.')

    # The safest bet is to assume it is a device with USB-Serial chip on the board:
    # tester_type = TesterControlType.USBSERIAL_ON_TESTER  # TODO: (when needed) Add to args
    tester_control: Optional[TesterControlInterface] = None
    # if tester_type in [TesterControlType.USBSERIAL_ON_TESTER]:
    #     tester_control = TesterControlSerial(loggr, port=args.tester_port, baudrate=115200, timeout=1, ignore_ports=ignore_ports, ignore_ble=ignore_ble, log_filename=log_filename)

    dut_type = DutControlType.USBSERIAL_ADAPTER  # TODO: (when needed) Add to args
    dut_control: Optional[DutControlInterface] = None
    # if dut_type in [DutControlType.USBSERIAL_ON_DUT, DutControlType.USBSERIAL_ADAPTER]:
    #     dut_control = DutControlSerial(loggr, port=args.dut_port, baudrate=115200, timeout=1, ignore_ports=ignore_ports, ignore_ble=ignore_ble, dut_type=dut_type, log_filename=log_filename2)

    # Initialize and register results callbacks
    results_writer = ResultsWriter()
    local_file_callback = ResultCommitToFileCallback()
    results_writer.register_commit_callback(local_file_callback)
    if args.gd_secrets:
        if os.path.isfile(args.gd_secrets):
            gd_file_callback = ResultCommitToGoogleDriveCallback(loggr, args.gd_secrets, args.gd_folder_id)
            results_writer.register_commit_callback(gd_file_callback)
        else:
            loggr.error(f'File "{args.gd_secrets}" not found.')
            raise FileNotFoundError(f'File "{args.gd_secrets}" not found.')

    test = TestScript(
        results_writer=results_writer,
        loggr=loggr,
        verbose=args.verbose,
        debug=args.debug,
        # data_entry=data_entry,
        plugins_dir=args.plugins_dir,
        tester_control=tester_control,
        dut_control=dut_control,
    )

    # Set up signals to handle Ctrl-C signal.SIGINT
    def signal_term_handler(signum, frame):
        loggr.info(f"Got signal {signum} frame {frame}.")
        test.abort()

    signal.signal(signal.SIGTERM, signal_term_handler)
    signal.signal(signal.SIGINT, signal_term_handler)

    if sig := getattr(signal, "SIGBREAK", None):
        signal.signal(sig, signal_term_handler)

    if sig := getattr(signal, "SIGCHLD", None):
        signal.signal(sig, signal.SIG_IGN)

    returncode = test.pre()
    # ? if returncode == TestError.ERR_FILE_OPEN and log_filename:
    #     loggr.error(f'Failed opening log file {log_filename}.')
    if returncode != TestError.ERR_OK:
        loggr.error("Exiting.")
        return -returncode.id if returncode.id > 0 else returncode.id

    if args.csv:
        returncode, tester_info, dut_info = test.exec_csv(args.lot_number, args.csv)
        test_success = test.run_result == RunResult.PASS
        results_writer.commit_results(out_file)

    test.post()
    test.print_summary(output_mode="all")

    # test.print_summary(loggr)

    elapsed_time = timer() - start_time
    time_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))

    if returncode in TestScript.VALID_RETURN_CODES:
        loggr.print(f"DONE. Elapsed time {time_str}.")
    else:
        loggr.print(f"Terminated due to unexpected error, {test.describe_error(returncode)}. Elapsed time {time_str}.")

    return 0 if test_success else (test.fail_cnt or 1)


def _parse_args() -> argparse.Namespace:
    gd_secrets_file_default = "sa_client_secrets.json"

    # caller_dir = os.getcwd()
    file_path = os.path.realpath(os.path.dirname(__file__))
    base_path = os.path.dirname(file_path)

    default_args = SimpleNamespace(
        plugins_dir=os.path.realpath(app_dir),
        gd_secrets=os.path.join(base_path, gd_secrets_file_default),
    )

    parser = argparse.ArgumentParser(description="Test Script CLI")
    parser.add_argument("-v", "--verbose", action="store_true", help="Include raw data in the output")
    parser.add_argument("-D", "--debug", action="store_true", help="Enable debugging and log")
    parser.add_argument("-t", "--tester_port", help="Serial port connected to tester serial device", dest="tester_port", default="auto")
    parser.add_argument("-p", "--port", help="Serial port connected to DUT device", dest="dut_port", default="auto")
    # parser.add_argument("-t", "--target", type=int, help="Optical LED<->sensor pair to use", dest="target", choices=range(1, 4))
    parser.add_argument("-L", "--lot", help="Lot number", dest="lot_number")
    parser.add_argument("-X", "--plugins", help="eXtension directory to scan for command plugins", dest="plugins_dir", default=default_args.plugins_dir)
    parser.add_argument("-a", "--account", help="Google Drive account secrets file", dest="gd_secrets", default=default_args.gd_secrets)
    parser.add_argument("-f", "--folder", help="Google Drive destination folder ID", dest="gd_folder_id")

    parser.add_argument("-c", "--csv", help="CSV file with steps to do", dest="csv")
    parser.add_argument("-o", "--output", help="CSV output file to write results to", dest="out_file")
    return parser.parse_args()


def _main() -> int:
    """Main Script Runner."""
    args = _parse_args()
    return cli(args)


if __name__ == "__main__":
    rc = _main()
    if rc != 0:  # Avoid "Uncaught Exceptions" in debugger
        sys.exit(rc)
