#!/usr/bin/env python3
from __future__ import annotations

import signal
from subprocess import check_output
import sys
import time
from types import FrameType

from .app_utils import GetConf, get_iface, get_hostname, ping_test, cvt, open_vt, reboot
from .loggr import Loggr


SIMULATE_NETWORK_DELAY = 3


def get_seed():
    with open("/dev/random", encoding="utf-8") as f:
        r = f.read(4)
    seed = 0
    for pos, ch in enumerate(r):
        seed += ord(ch) << (pos * 8)
    return seed


class Manager:
    def __init__(self, vt_app: int = 1, vt_me: int = 2) -> None:
        self.loggr = Loggr(use_vt_number=vt_me, use_stdout=False, use_journal_name="manager.py")

        self.mandead = False
        self.conf = None
        self.info = None
        self.vt_app = vt_app
        self.vt_me = vt_me
        self.internet_connected = False
        self.ntp_synced = False
        self.server = False

        signal.signal(signal.SIGTERM, self.signal_term_handler)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if sig := getattr(signal, "SIGCHLD", None):
            signal.signal(sig, signal.SIG_IGN)

    def signal_term_handler(self, signum: int, frame: FrameType | None):
        self.mandead = True
        self.loggr.position(0, 47, "Manager killed!  ")

    def execute(self):
        self.loggr.civis()  # Cursor invisible
        self.loggr.cls()
        cvt(self.vt_me)

        row = 0
        row = self.config(row)

        row = self.wait_for_network(row)
        # if not self.internet_connected:
        #     raise

        row = self.get_time(row)
        # if not self.ntp_synced:
        #     raise

        row = self.run_server_mode(row)

        if self.server:
            # TODO: (when needed) Start web server
            pass
        else:
            row = self.run(row)

        # self.loggr.position(0, row, "Process manager.py Done.")
        self.loggr.position(0, 48, "Process manager.py Done.")

    def config(self, row: int = 0):
        filepath = "/etc/manager_conf.yaml"
        self.conf = GetConf(filepath=filepath)
        if not self.conf:
            raise FileNotFoundError(f'Error, file "{filepath}" not found')
        filepath = "/home/pi/app_conf.yaml"
        self.info = GetConf(filepath=filepath)
        if not self.info:
            raise FileNotFoundError(f'Error, file "{filepath}" not found')

        station = get_hostname()
        version = self.info.get("Version", "(n/a)")
        build = self.info.get("Build", "(n/a)")
        self.server = self.conf.get("Server")
        line_width = 64
        info_lines = ["[ Manager on VT%(vt)d ]", "", "  Station id          : %(name)s", "  Software version    : %(ver)s", "  Build number        : %(build)s"]
        values = {
            "vt": self.vt_me,
            "name": station,
            "ver": version,
            "build": build,
        }
        message = "\n".join([(line % values).ljust(line_width) for line in info_lines])
        self.loggr.position(0, row, message)
        row += 5
        # self.loggr.position(0, row)
        return row

    def wait_for_network(self, row: int = 0, timeout: int = 30):
        # TODO: (when needed) Allow WiFi, LTE, etc. (based on _conf.yaml?)
        interface = None
        if_info = {"ipaddress": None, "mac": None}
        line_width = 64
        start_lines = [
            "  Internet connected  : %(conn)s",
            "  Interface           : %(if)s",
            "  Hardware MAC        : %(mac)s",
            "  IP Address          : %(ip)s",
        ]
        count: int = 0
        while True:
            if count > timeout:
                self.loggr.cnorm()  # Cursor normal
                self.loggr.position(0, row + 6, "Network does not appear to be connected.")
                self.loggr.print("Please connect Ethernet network, or configure Wi-Fi (sudo raspi-config > 1 System Options > S1 Wireless LAN).")
                while True:
                    input_str = input("Start raspi-config ('no' will reboot) [Y/n]? ").strip()
                    self.loggr.civis()  # Cursor invisible
                    if input_str.lower() in ["n", "no"]:
                        break
                    if input_str.lower() in ["", "y", "yes"]:
                        # ? How can we invoke a function and run it interactively? cmd = 'sudo raspi-config nonint INTERACTIVE=True do_wifi_ssid_passphrase'
                        cmds = [
                            "sudo rfkill unblock wlan",
                            "sudo ifconfig wlan0 up",
                            "sudo raspi-config",
                        ]
                        for cmd in cmds:
                            try:
                                result = check_output(cmd, shell=True)
                                self.loggr.print(f"$> {cmd}\n{result}")
                            except Exception as err:  # noqa: PERF203
                                self.loggr.print(f"$> {cmd}\nError {err}")
                                continue
                        self.loggr.cls()
                        break
                self.loggr.print("\n\nRebooting...")
                reboot("r")
                time.sleep(5)
                sys.exit(0)

            if SIMULATE_NETWORK_DELAY:  # pylint: disable=using-constant-test
                # DEBUG: Simulate delay getting network connection
                if count > SIMULATE_NETWORK_DELAY:
                    interface, if_info = get_iface()
            else:
                interface, if_info = get_iface()
            self.internet_connected = False
            if interface and if_info["ipaddress"]:
                self.internet_connected = ping_test(f_timeout_seconds=1.0)
            values = {
                "if": interface if interface else "",
                "mac": if_info["mac"] if if_info["mac"] else "",
                "ip": if_info["ipaddress"] if if_info["ipaddress"] else "",
                "conn": ("Yes" + " " * 20) if self.internet_connected else f"Waiting for network {count}...  ",
            }
            message = "\n".join([(line % values).ljust(line_width) for line in start_lines])
            self.loggr.position(0, row, message)
            if self.internet_connected:
                break
            count += 1
            time.sleep(1)

        values = {
            "if": interface,
            "mac": if_info["mac"],
            "ip": if_info["ipaddress"],
            "conn": f"Yes (took {count} seconds to acquire IP Address)" if self.internet_connected else f"No  (Timeout waiting {count} seconds)",
        }
        message = "\n".join([(line % values).ljust(line_width) for line in start_lines])
        self.loggr.position(0, row, message)
        row += 5
        # self.loggr.position(0, row)
        return row

    def get_time(self, row: int = 0):
        ntp_url = "pool.ntp.org"
        # TODO: (when needed) use self.loggr.tput() to erase till end of line.
        time_str = "  Time sync           : %s                       "
        self.loggr.position(0, row, time_str % "Getting time from NTP server...")
        time.sleep(2)  # DEBUG Emulate delay getting NTP time
        try:
            result = check_output(f'sudo ntpdate "{ntp_url}"', shell=True)
            self.loggr.position(0, row, time_str % (f"Yes (Synchronized time with NTP server {ntp_url})"))
            self.ntp_synced = True
        except:
            self.loggr.position(0, row, time_str % (f"No  (Error getting time from NTP server {ntp_url})",))
        row += 2
        # self.loggr.position(0, row)
        return row

    def run_server_mode(self, row: int = 0):
        mode_str = "  App mode            : %s                       "
        self.loggr.position(0, row, mode_str % ("Server" if self.server else "Station",))
        row += 1
        # self.loggr.position(0, row)
        return row

    def run(self, row: int = 0):
        run_str = (
            "  App                 : %(name)s               \n"
            "  Path                : %(path)s               \n"
            "  VT                  : %(vt)d               \n"
            "  Status              : %(status)s               \n"
        )

        if not self.info:
            raise ValueError("Expected info to be set")
        app_path = f'/usr/bin/python -u /home/pi/app/{self.info.get("Type")}.py'
        # self.loggr.info(f'Starting app {app_path} on VT={self.vt_app}')
        self.loggr.position(
            0,
            row,
            run_str
            % {
                "name": self.info.get("Type"),
                "path": app_path,
                "vt": self.vt_app,
                "status": "Starting...",
            },
        )

        # Set cursor couple rows down to catch any blabber from open_vt()
        self.loggr.position(0, row + 5)

        result = open_vt(self.vt_app, app_path, do_sudo=True, do_chvt=True, loggr=self.loggr)
        # self.loggr.debug("DONE Starting app %s on VT=%d, result=%s" % (app_path, self.vt_app, result))

        # Let open_vt() get through and blabber all stuff out.
        time.sleep(2)

        self.loggr.position(
            0,
            row,
            run_str
            % {
                "name": self.info.get("Type"),
                "path": app_path,
                "vt": self.vt_app,
                "status": "Started",
            },
        )
        row += 5
        # Add some V space for open_vt() blabber:
        row += 2
        return row


def main():
    vt_app = 1
    vt_me = 2
    mgr = Manager(vt_app=vt_app, vt_me=vt_me)
    mgr.execute()


if __name__ == "__main__":
    main()
