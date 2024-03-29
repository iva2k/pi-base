# Test Script

## Introduction

`TestScript` is a Python class which is a generalized automation framework that provides ability to run custom commands with parameters from user-written scripts. It is specially suited for running automated tests, collecting data and applying test limits, for automated applications such as:

* manufacturing tests
* lab benchtop tests
* engineering characterizations and qualifications
* design validation and verification for hardware devices

`TestScript` class is implemented in `lib/test_script.py` file.

`TestScript` takes an input CSV file, which contains a sequence of commands with parameters, and performs them sequentially, producing an output CSV file with all the results, as well as a log output of all the activity.

`TestScript` class can be imported and used by other Python scripts to integrate with additional functionality, for example, as a manufacturing test program.

When used for manufacturing test, `TestScript` concludes if the device has a PASS or FAIL for the purpose of the manufacturing process.

`scripts/test_script.py` file, when run directly from a command line, can take arguments and runs in a CLI mode, which is currently limited to a simplistic tester setup. In this way it can be integrated with other (not necessarily Python) software.

## `TestScript` Input File

`TestScript` input file is a text file in a CSV format (Comma- Separated Values) that `TestScript` reads and executes, line by line, that contains commands with parameters, describing the complete test sequence.

Empty lines are ignored and written to the output results file.

Lines starting with a single '#' are treated as comments and are simply passed out to the output results file.

Lines starting with '##' are ignored and removed and not written to the output results file.

## `TestScript` Results Output File

`TestScript` results output file is a text file in CSV format that `TestScript` writes after executing the input file. The results output file contains the original, unmodified commands with parameters from the input file, all the empty and comment lines starting with '#', as well as all the added results of these commands prefaced with '##'. Lines starting with '##' in the input file are ignored and not written to the output results file, effectively being replaced by new results.

With the '#' and '##' processing, the results file produced from `TestScript` can itself be ran as an input to `TestScript` due to all the results starting with '##' removed automatically.

## `TestScript` Log Output

`TestScript` prints messages to a log output as it goes through the commands in the Input File. The log is implemented by passing `TestScript` object a `Loggr` object. `TestScript` CLI, for example, directs the log to STDOUT / console output. Other uses can choose other targets for the `Loggr`.

## `TestScript` Transcript

Transcript is a recap of all the commands with their results. `TestScript` creates the transcript as it goes through the Input File commands. `TestScript` object has a `.transcript` property, with `["ALL"]`, `["PASS"]`, and `["FAIL"]` components that can be used by Python users of `TestScript` class.

`TestScript` will print out the transcript by a `test_summary` command.

`TestScript` has `.print_summary()` method that will print out the transcript to a given `loggr`.

## `TestScript` Report

TODO: (when needed) Implement

`TestScript` report is a helper method of the `TestScript` object, that adds one row to a CSV report file. If the file does not exist, it will be created with a header row.

## Tester Equipment

`TestScript` controls tester equipment by interacting with object in `.tester_control` property (a subclass of `TesterControlInterface` class), which is dependency-injected by `TestScript.configure_tester()` method which should be called after creating an instance of `TestScript` class.

## DUT

 `TestScript` controls DUT (Device Under Test) by interacting with object in `.dut_control` property (a subclass of `DutControlInterface` class), which is dependency-injected into `TestScript` instance constructor.

## Commands

`TestScript` executes given input file line by line, interpreting all lines that are non-empty, non-comment ('#') and non-result ('##') lines, as commands with optional parameters. The first cell in the row is the command name, the rest are parameters given to the command. Number and types of parameters should match what is described in the command definition. Currently there's no support for parameter types, but there might be one added in the future. An example command is:

```csv
operator_log, "Begin programming EEPROM"
```

### Command Plugins

Some commands are hard-coded in `TestScript` and there is a plugin extension mechanism, so more commands can be added when needed by placing a `.py` file into a plugin directory given to `TestScript`. Each such file can have any number of commands implemented. Each new command should be declared as a subclass of `TestScriptCommandPluginInterface` class given in `lib/test_script.py` module, method `.define_command()` should return command definition details and method `.execute()` should implement the command.

Note about imports from plugin files: `TestScript` relies on package "pi_base" for its `pi_base.lib.os_utils` and `pi_base.lib.app_utils` and the `pi_base.modpath` module that manages imports for non-installed modules from  the `lib` directory, bot during development andwhen running on the Raspberry Pi appliance target. So plugin modules can import `TestScript` definitions absolutely without worrying where `lib` is.

Aditional commands can interact directly with `TestScript`'s properties, such as `.tester_control` for custom tester equipment and `.dut_control` for custom DUT operations, both of which are dependency-injected into `TestScript`. Reference to `TestScript` is given via the plugin mechanism and presented as `.test` property to the command instance.

### Command Checks

Commands may have "checks" functionality, as described by int `checks` property given in `.define_command()` method. "checks" value of non-0 means that the command compares data and measurements received from the DUT or the tester equipment against the test limits contained in the command parameters in the input test script file. Currently the exact non-0 number is not important, but the underlying idea is to describe how many different checks the command does. For example, if the command measures something and then compares it against min and max test limit values given in the command parameters, "checks" should be set to 2. When later such functionality is implemented, `TestScript` would keep accounting of total number of checks, and how many failed, so specific violations can be more easily tracked back to the specific command and its specific test limit parameter.

The "checks" functionality is used to determine the overall PASS/FAIL result of the test run. If the test script has no commands with "checks", then the run is a procedure that does not have PASS/FAIL outcome, and is typically intended to just collect measurements data into the results output file.

### Command Results

An individual command produces a result of `CommandResult` class, which contains a returncode, encoded by the `TestError` class. `CommandResult` also contains optional measurement outputs from the DUT and / or the tester equipment, and, for "checks" commands, also contains a "checks" result, which is either a PASS, or a FAIL outcome. A PASS command result is encoded in returncode as ERR_OK (value 0) while a FAIL command result is encoded as ERR_TEST_FAIL (value 2000).

Individual "checks" commands outcomes are combined to conclude if the overall test is a PASS (if all the "checks" are PASS) or a FAIL (if any of the "checks" is a FAIL), which are encoded by `RunResult` class. Note that a FAIL in any "checks" command does not stop the `TestScript` sequence - it will run to completion.

There are many other error conditions that commands may encounter and detect, which are encoded by other values in the returncode, that cannot be translated to a PASS or a FAIL. Those errors will stop the test sequence and produce an ERROR outcome of the test run. Generally, ERROR outcomes are "unexpected" conditions (usually unrelated to the DUT), and should be reported back to Engineering where they could fix the implementation by adding better handling of the situation (e.g. a retry mechanism, or changing wait times, etc.).

## Result Output

`TestScript` outputs are stored in a `ResultsWriter` object as the script is ran, utilizing the `ResultsWriter.add_*()` methods.

To store the results, one must create a `ResultCommitCallback` class that implements a `commit` method (see `lib/test_commit_callbacks.py`).  The `commit` method should receive a string of the test results (Note: TODO: (soon) it will be changed to a list of string shortly) along with a file name and store them as desired.

Callbacks can be registered using the `ResultsWriter.register_commit_callback` method, and triggered by calling `ResultsWriter.commit_results`.

Note that committing results does **not** clear the results buffer.  Use the `ResultsWriter.clear_results` method to clear the results between script runs.

## Tutorial 1 - Adding A New Command To `TestScript`

To add a command to `TestScript`, create a new file named "plugin_commands.py" (can be more than 1 file for more commands, file names can be anything containing "plugin" keyword - other files are not examined for extensions) in "plugins" directory that you pass to `TestScript` constructor, containing the following code:

```python3
"""Example Command Plugin."""
from __future__ import annotations

# "modpath" must be first of our modules
from pi_base.modpath import *  # pylint: disable=wildcard-import,wrong-import-position,unused-wildcard-import
from pi_base.lib.loggr import ColorCodes
from pi_base.lib.tester.tester_common import TestError
from pi_base.lib.tester.test_script import CommandResult, TestScriptCommand, TestScriptCommandPluginInterface

class TestScriptCommandCurrentTestCount(TestScriptCommandPluginInterface):
    """Logs the current test_cnt to the loggr."""

    def define_command(self) -> TestScriptCommand:
        return TestScriptCommand(command="current_test_count", args=[], results=[], checks=0)

    def execute(self, command: TestScriptCommand, cmd: str, tokens: list[str]) -> CommandResult:
        self.test.loggr.color_print(f"Current test count: {self.test.test_cnt}", color_code = ColorCodes.BLUE)
        return CommandResult(TestError.ERR_OK)
```

Modify class `TestScriptCommandCurrentTestCount` as needed - change its name, its docstring (command description), command string, args, results checks in the `.define_command()` method, and implementation code in the `.execute()` method.

### `.define_command()` Method

The `.define_command()` method should return `TestScriptCommand` instance that defines the command.

Property `command` will be the name of the command that one will write in the first column of the input file / test script to use the command.

Property `method` of `TestScriptCommand` is omitted, as it is set automatically to `self.execute` by the framework.

Property `args` should contain a list of strings representing the arguments the command needs (used for logging purposes). Parameter values are passed from the input file to `tokens` arg of the `.execute()` method.

Property `results` should contain a list of strings representing the result output fields from running the command,  returned in `results` list inside `CommandResult` instance from the `.execute()` method.

Set `checks` property value appropriately - if command does not check any test limits, set "checks" to 0. Match the value of "checks" to the count of command parameters containing test limits.

### `.execute()` Method

The `.execute()` method of the command is called when the command is encountered in the input test script file.

Argument `command` gives the `TestScriptCommand` instance from the `.define_command()` method.

Argument `cmd` gives the command name as a string, passed from the input test script file and matching the '`command` propery of the `TestScriptCommand` instance. It is useful in cases when many commands are implemented in one `.execute()` method.

Argument `tokens` gives a list of strings from the parsed script line after the command name, containing the parameters for the command. The Framework checks number of parameters and throws appropriate error if the input test script does not match the command definition. The `.execute()` method should take care of converting strings into appropriate types (e.g. int, float, bool) with all necessary validations. Return `TestError.ERR_INVALID_COMMAND_ARGUMENT` with appropriate text describing the problem in `test_info` property of `CommandResult` instance. You can use `self.token_int_val()` and `self.token_float_val()` from the base class to simplify the validations (see example code below). Add range checks for the parameters as appropriate.

The method must return a `CommandResult` instance which includes the `returncode` (ERR_OK, ERR_TEST_FAIL, etc...), `results` (the list of string results defined in the command description from above), and `test_info` string (other test information that the user might need and is printed out in the logs and the summary).

## Tutorial 2 - Command with Parameters and Test Limits

Here's a more invoved example of a voltage measurement command. It uses a parameter to choose which voltage to measure, and has min and max test limits for the voltage.

```python3
... (use the same imports as in Tutorial 1)

class TestScriptCommandCheckVoltage(TestScriptCommandPluginInterface):
    """Measure DUT voltage and check against the test limits."""

    def define_command(self) -> TestScriptCommand:
        return TestScriptCommand(command="check_voltage", args=["target", "val_min", "val_max"], results=["test_result", "val"], checks=2)

    def execute(self, command: TestScriptCommand, cmd: str, tokens: list[str]) -> CommandResult:
        rc = TestError.ERR_OK
        val, test_result = 'N/A', 'FAIL'
        min_val, max_val = 'N/A', 'N/A'
        measured = self.prep_for_measured()

        for _ in range(1):  # Emulate goto by `break`
            # args validation

            rc, target, msg = TestError.ERR_OK, tokens[0], ""
            # rc, target, msg = self.token_int_val(tokens, 0, command)
            # if rc != TestError.ERR_OK:
            #     break

            rc, min_val, msg = self.token_float_val(tokens, 1, command)
            if rc != TestError.ERR_OK:
                break

            rc, max_val, msg = self.token_float_val(tokens, 2, command)
            if rc != TestError.ERR_OK:
                break

            # measurement
            rc, val, msg = get_voltage(target)  # Can pass self.test.dut_control to get_voltage() for actual hardware access.
            if rc != TestError.ERR_OK:
                break
            measured.append({ target: val })  # Save measurements for later use.

        if rc != TestError.ERR_OK:
            self.test.loggr.error(msg)
            return CommandResult(rc, ["FAIL", val], msg)

        val_result = min_val <= val and val <= max_val
        test_result = 'PASS' if val_result else 'FAIL'
        msg = f"Voltage for target {target} is {val}, expected in range [{min_val}:{max_val}]"
        return CommandResult(TestError.ERR_OK if val_result else TestError.ERR_TEST_FAIL, [test_result, val], msg)
```

### Script Usage

With the command registered and implemented, one can now use it inside of a test script. The test script must be a CSV (Comma- Separated Values) format where each line is either a command that should be run, or a comment (started with #) or a blank line.

Note that line-end comments are also supported, just mind the last ',' comma before the '#' of the comment.

An example input test script .csv file can contain the following commands (it is expected to fail the 3rd `check_voltage` command):

```csv
operator_log, "**** Starting Voltage Tests ****"
check_voltage, 12VDC, 11.5, 12.5
check_voltage, 5VDC, 4.75, 5.25
check_voltage, 3.3VDC, 1.65, 1.95, # incorrect voltage range - should fail!
operator_log, "**** Done with Voltage Tests ****"

test_summary
```
