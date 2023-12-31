#!/usr/bin/env python3

# import os
import signal
import sys
import time

# "modpath" must be first of our modules
from modpath import app_dir  # pylint: disable=wrong-import-position
from app_utils import eth0_mac, get_conf, get_pi_model, get_pi_revision, reboot
from large import Large
from loggr import Loggr

vt_number = None
vt_history = 4
l = Loggr(use_vt_number=vt_number, use_stdout=True, use_journal_name='blank.py')
h = Loggr(use_vt_number=vt_history, use_stdout=False, use_journal_name=None, use_sudo=True, primary_loggr=l)
signal.signal(signal.SIGINT,  signal.SIG_IGN)
large = Large()


class Test:
    """
        Test
    """

    def __init__(self, fnc_input, fnc_filter_input) -> None:
        """
            @fnc_input is getter of test data (e.g. operator input() or some other automated data provider)
            @fnc_filter_input checks for special commands in the input and returns "True" to stop test, "False" if data is not filtered and test can proceed.
        """
        self.field = "device id"
        assert fnc_filter_input is not None
        self.fnc_filter_input = fnc_filter_input
        assert fnc_input is not None
        self.fnc_input = fnc_input

    def data_entry(self):
        """
            Request data using provided fnc_input at instantiation.
            @return run,data - if run is False, data should be ignored and test loop stopped, if True, continue and call .run(data).
        """
        device_id, other = '', []
        while True:
            input_str = self.fnc_input("Enter %s: " % (self.field,))
            device_id = input_str.split(" ")[0].lower()
            # TODO: (when needed) Implement decoding of all possible QR label formats.
            other = input_str.split(" ")[1:]
            if device_id == "":
                l.print("  ID not recognized. Do not enter spaces.")
            else:
                break

        other_str = "(other entry ignored: %s)" % (' '.join(other)) if len(other) > 0 else ""
        l.debug('got user entry: "%s" %s' % (device_id, other_str))
        filt = self.fnc_filter_input(device_id)
        if filt:
            return False, ''
        return True, device_id

    def info(self, device_id) -> str:
        return f'{self.field} {device_id}'

    def pre(self):
        """ Prepare test (e.g. setup test station) """
        # l.debug('Test.pre()')
        pass

    def conf(self, device_id) -> str:
        return f'{self.field} {device_id}'

    def run(self, device_id) -> bool:
        """
            Run single test
            @return True if test passed, False if failed.
        """
        # l.debug('Test.run(%s)' % (device_id,))
        if device_id == "":
            return False

        # TODO: (when needed) Implement actual test

        # Dummy test:
        time.sleep(2)
        if device_id[-1] in ['1', '3', '5', '7', '9']:
            return True
        return False

    def post(self):
        """ Prepare test (e.g. setup test station) """
        # l.debug('Test.post()')
        pass


def filter_input(entered):
    """
    Intercept operator input
    """
    if entered == "quit":
        l.print("  Quitting...")
        h.print("  Quitting...")
        return True

    if entered == "reboot":
        l.print("  Rebooting...")
        h.print("  Rebooting...")
        reboot("r")
        return True

    if entered == "shutdown":
        l.print("  Shutting down...")
        h.print("  Shutting down...")
        reboot("h")
        return True

    return False


def main():
    pi_mac = eth0_mac()
    if pi_mac:
        for c in '><|*?":\\/':  # Remove all prohibited symbols
            pi_mac = pi_mac.replace(c, '')

    pi_model = get_pi_model()
    pi_revision = get_pi_revision()
    if not pi_model or not pi_revision:
        pi_model = '(not a Pi)'
        pi_revision = ''

    # os.chdir(app_dir)
    conf = get_conf(filepath=f'{app_dir}/app_conf.yaml')
    name = conf.get("Name")
    app_type = conf.get("Type")
    version = conf.get("Version")

    test = Test(input, filter_input)

    message = f'[ {name} ]\n{app_type} v{version}\n{pi_model} {pi_revision} MAC:{pi_mac}\n'
    # Clear display
    l.cnorm()  # Cursor normal
    l.cls(message)

    # Clear history VT
    #time.sleep(3)
    h.civis()  # Cursor invisible
    h.cls("[ %(name)s ]\n%(app_type)s v%(ver)s\n" % {'name': name, 'app_type': app_type, 'ver': version})

    test.pre()
    while True:

        run, device_id = test.data_entry()
        if not run:
            break

        # Device ID given. Run test:
        conf = test.conf(device_id)

        # Clear previous pass/fail large result, show "busy".
        large.print('busy')
        l.print('\nTesting %s' % (conf,))

        result = test.run(device_id)

        # Clear "busy", print large result:
        result_str = 'pass' if result else 'fail'
        large.print(result_str)
        l.print(f'\nDone testing {conf}\nresult: {result_str}\n')

        # Log history VT
        h.print(f'{conf} result: {result_str}')

    test.post()
    return 0


if __name__ == "__main__":
    rc = main()
    if rc != 0:  # Avoid "Uncaught Exeptions" in debugger
        sys.exit(rc)
