#!/usr/bin/env python3

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation

# import os
import signal
import sys
import time
from typing import Callable

# "modpath" must be first of our modules
from pi_base.modpath import app_conf_dir  # pylint: disable=wrong-import-position
from pi_base.lib.app_utils import eth0_mac, GetConf, get_pi_model, get_pi_revision, reboot
from pi_base.lib.large import Large
from pi_base.lib.loggr import Loggr


vt_number = None
vt_history = 4
loggr = Loggr(use_vt_number=vt_number, use_stdout=True, use_journal_name="blank.py")
history = Loggr(use_vt_number=vt_history, use_stdout=False, use_journal_name=None, use_sudo=True, primary_loggr=loggr)
signal.signal(signal.SIGINT, signal.SIG_IGN)
large = Large()


class Test:
    """Test."""

    def __init__(self, fnc_input: Callable, fnc_filter_input: Callable) -> None:
        """Constructor.

        Args:
            fnc_input: getter of test data (e.g. operator input() or some other automated data provider).
            fnc_filter_input: checks for special commands in the input and returns "True" to stop test, "False" if data is not filtered and test can proceed.
        """
        self.field = "device id"
        if not fnc_filter_input:
            raise ValueError("Expected non-empty fnc_filter_input.")
        self.fnc_filter_input = fnc_filter_input
        if not fnc_input:
            raise ValueError("Expected non-empty fnc_input.")
        self.fnc_input = fnc_input

    def data_entry(self) -> "tuple[bool, str]":
        """Request data using provided fnc_input at instantiation.

        Returns:
            Tuple of run,data - if run is False, data should be ignored and test loop stopped, if True, continue and call .run(data).
        """
        device_id, other = "", []
        while True:
            input_str = self.fnc_input(f"Enter {self.field}: ")
            device_id = input_str.split(" ")[0].lower()
            # TODO: (when needed) Implement decoding of all possible QR label formats.
            other = input_str.split(" ")[1:]
            if device_id == "":
                loggr.print("  ID not recognized. Do not enter spaces.")
            else:
                break
        other_str = (" ".join(other)) if len(other) > 0 else ""
        ignored = f"(other entry ignored: {other_str})"
        loggr.debug(f'got user entry: "{device_id}" {ignored}')
        filt = self.fnc_filter_input(device_id)
        if filt:
            return False, ""
        return True, device_id

    def info(self, device_id) -> str:
        return f"{self.field} {device_id}"

    def pre(self):
        """Prepare test (e.g. setup test station)."""
        # loggr.debug('Test.pre()')

    def conf(self, device_id) -> str:
        return f"{self.field} {device_id}"

    def run(self, device_id) -> bool:
        """Run single test.

        Returns:
            True if test passed, False if failed.
        """
        # loggr.debug('Test.run(%s)' % (device_id,))
        if device_id == "":
            return False

        # TODO: (when needed) Implement actual test

        # Dummy test:
        time.sleep(2)
        if device_id[-1] in ["1", "3", "5", "7", "9"]:
            return True
        return False

    def post(self):
        """Prepare test (e.g. setup test station)."""
        # loggr.debug('Test.post()')


def filter_input(entered):
    """Intercept operator input."""
    if entered == "quit":
        loggr.print("  Quitting...")
        history.print("  Quitting...")
        return True

    if entered == "reboot":
        loggr.print("  Rebooting...")
        history.print("  Rebooting...")
        reboot("r")
        return True

    if entered == "shutdown":
        loggr.print("  Shutting down...")
        history.print("  Shutting down...")
        reboot("history")
        return True

    return False


def main():
    pi_mac = eth0_mac()
    if pi_mac:
        for c in '><|*?":\\/':  # Remove all prohibited symbols
            pi_mac = pi_mac.replace(c, "")

    pi_model = get_pi_model()
    pi_revision = get_pi_revision()
    if not pi_model or not pi_revision:
        pi_model = "(not a Pi)"
        pi_revision = ""

    # os.chdir(app_conf_dir)
    conf = GetConf(filepath=f"{app_conf_dir}/app_conf.yaml")
    name = conf.get("Name")
    app_type = conf.get("Type")
    version = conf.get("Version")

    test = Test(input, filter_input)

    message = f"[ {name} ]\n{app_type} v{version}\n{pi_model} {pi_revision} MAC:{pi_mac}\n"
    # Clear display
    loggr.cnorm()  # Cursor normal
    loggr.cls(message)

    # Clear history VT
    # time.sleep(3)
    history.civis()  # Cursor invisible
    history.cls(f"[ {name} ]\n{app_type} v{version}\n")

    test.pre()
    while True:
        run, device_id = test.data_entry()
        if not run:
            break

        # Device ID given. Run test:
        test_conf = test.conf(device_id)

        # Clear previous pass/fail large result, show "busy".
        large.print("busy")
        loggr.print(f"\nTesting {test_conf}")

        result = test.run(device_id)

        # Clear "busy", print large result:
        result_str = "pass" if result else "fail"
        large.print(result_str)
        loggr.print(f"\nDone testing {test_conf}\nresult: {result_str}\n")

        # Log history VT
        history.print(f"{test_conf} result: {result_str}")

    test.post()
    return 0


if __name__ == "__main__":
    rc = main()
    if rc != 0:  # Avoid "Uncaught Exeptions" in debugger
        sys.exit(rc)
