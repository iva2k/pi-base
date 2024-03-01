#!/usr/bin/env python3

import datetime
import json
import os
import platform
import time

# import zmq
import threading
from subprocess import run, check_output, CalledProcessError
from uuid import getnode as get_mac

import requests
import yaml


def get_os_name() -> str:
    # if platform.system() == "Windows":
    if os.name == "nt":
        return "Windows"
    if platform.system() == "Darwin":
        return "MacOS"
    # if platform.system() == "Linux":
    if os.name == "posix":  # Linux
        return "Linux"

    return "Unknown"


def uptime():
    cmd = "uptime"
    p = check_output(cmd, shell=True, text=True)
    x = p.split()
    return x[0]


def reboot(reboot_type, delay=0, loggr=None):
    if reboot_type in ("r", "h"):
        message = "System is shutting down." if reboot_type == "h" else "System is rebooting."
        cmd = f'sudo shutdown -{reboot_type} now "{message}"&'
        if delay != 0:
            time.sleep(delay)
            # cmd = ('sleep %n && ' % delay) + cmd
        # Popen(cmd, shell=True, text=True)
        p = check_output(cmd, shell=True, text=True)
        if loggr:
            loggr.debug(f"reboot() cmd={cmd} result={p}")


def get_hostname():
    cmd = "hostname"
    result = check_output(cmd, shell=True, text=True)
    return result[:-1]


def set_hostname(wants):
    # TODO: (soon) change implementation to use raspi-config, instead of hosts_str
    hosts_str = """127.0.1.1	{wants}
127.0.0.1	localhost
::1		localhost ip6-localhost ip6-loopback
ff02::1		ip6-allnodes
ff02::2		ip6-allrouters
"""
    out = get_hostname()
    if out == wants:
        return False, out
    cmd = f"echo '{wants}' | sudo tee /etc/hostname >/dev/null"
    result = check_output(cmd, shell=True, text=True)
    final = hosts_str.format(wants=wants)
    cmd = f"echo '{final}' | sudo tee /etc/hosts >/dev/null"
    result = check_output(cmd, shell=True, text=True)
    return True, out


def is_up():
    cmd = "ping -c 1 8.8.8.8 2>/dev/null"
    try:
        p = check_output(cmd, shell=True, text=True)
    except CalledProcessError as e:
        return False
    return True


class iface_dev:
    def __init__(self):
        self.done = False
        self.t = threading.Thread(target=self.worker)
        self.t.start()
        self.ifaces = None

    def worker(self):
        cmd = "ifconfig"
        self.ifaces = {}
        iface = ""
        ip = ""
        mac = ""

        while not self.done:
            time.sleep(0.1)
            p = check_output(cmd, shell=True, text=True)
            out = p.split("\n")
            count = 10
            iface = ""
            for line in out:
                if len(line) == 0:
                    count += 1
                    if len(iface) > 0:
                        print(f"\033[{count};6H{iface} {mac} {ip}")
                        self.ifaces[iface] = [mac, ip]
                    ip = ""
                    mac = ""

                params = line.lstrip().split(" ")
                if params[0].endswith(":"):
                    addr = ""
                    ip = ""
                    iface = params[0]
                if params[0] == "inet":
                    ip = params[1]
                if params[0] == "ether":
                    mac = params[1]

    def dump(self):
        print(f"\033[6;6H{self.ifaces!s}")


def get_ifconfig():
    cmd = "ifconfig"
    try:
        p = check_output(cmd, shell=True, text=True)
    except:
        p = ""
    return p.split("\n")


def data_amount(if_type="ppp0"):
    out = get_ifconfig()
    iface = ""
    for line in out:
        params = line.lstrip().split(" ")
        if params[0].endswith(":"):
            iface = params[0][:-1]
        if params[0] == "RX" and params[4] == "bytes":
            rxbytes = int(params[5])
        if params[0] == "TX" and params[4] == "bytes":
            txbytes = int(params[5])
            if iface == if_type:
                return txbytes, rxbytes
    return -1, -1


def ifconfig():
    out = get_ifconfig()
    ifaces = {}
    iface = ""
    for line in out:
        params = line.lstrip().split(" ")
        if params[0].endswith(":"):
            iface = params[0][:-1]
            ifaces[iface] = {"ipaddress": None, "mac": None}
        if params[0] == "inet":
            ifaces[iface]["ipaddress"] = params[1]
        if params[0] == "ether":
            ifaces[iface]["mac"] = params[1]
    return ifaces


def get_iface(if_list=None, require_connected=True):
    """Issue ifconfig command and parse the output to determine which interfaces are up.

    By up, it means the interface has been assigned an ipv4 address.

    returns eth0, wlan0, or emtpy (no interface active)
    """
    if not if_list:
        if_list = ["wlan0", "eth0"]
    ifaces = ifconfig()
    for key in if_list:
        if key in ifaces and (not require_connected or ifaces[key]["ipaddress"] is not None):
            return key, ifaces[key]
    return None, {"ipaddress": None, "mac": None}


def list_iw():
    """List all WLAN interfaces (Linux only)."""
    cmd = "iw dev | awk '$1==\"Interface\"{print $2}'"
    try:
        p = check_output(cmd, shell=True, text=True)
    except:
        p = ""
    return [x for x in p.split("\n") if x]  # Remove blanks


def ping_test(url="www.google.com", f_timeout_seconds=None):
    options = ""
    count = 3
    interval = 0.3
    if f_timeout_seconds is not None:
        # options += f'-w {int(f_timeout_seconds + 0.5)} '
        options += f"-W {f_timeout_seconds:f} "
    cmd = f"ping -c {count} -i {interval:f} {options} {url}"
    try:
        result = check_output(cmd, shell=True, text=True)
        return True
    except:
        return False


# app_info


class get_conf:
    """Read configuration file (.yaml or .json)."""

    def __init__(self, filepath="app_conf.yaml"):
        self.filepath = filepath
        self.conf = {}
        with open(filepath, encoding="utf-8") as file:
            ext = os.path.splitext(filepath)[1].lower()
            if ext == ".yaml":
                self.conf = yaml.safe_load(file)
            elif ext == ".json":
                self.conf = json.load(file)
            # TODO: (when needed) .ini .xml

    def get(self, key, default=None):
        if key in self.conf:
            return self.conf[key]
        return default

    def get_subkey(self, key, key2, default=None):
        if key in self.conf:
            conf = self.conf[key]
            if conf and key2 in conf:
                return conf[key2]
        return default

    def dump(self):
        print(self.conf)


def get_fg_vt():
    # TODO: (when needed) Implement, use `cat /sys/class/tty/tty0/active` --> tty2 or `sudo fgconsole` -> 2
    pass


def reset_vt(vt_number):
    # TODO: (when needed) reset vt to a login shell (kill all processes on the given VT)
    pids_killed = []
    # Get list of PIDs of VTn device:
    cmd = f"sudo /usr/bin/fuser /dev/tty{vt_number} 2>/dev/null"
    try:
        result = check_output(cmd, shell=True, text=True)
    except:
        result = ""
    # print("DEBUG: reset_vt() cmd='%s' got result='%s'" %(cmd, result))
    # fuser sends to STDERR '/dev/tty1:', the result is in form '   123 456 789' with a list of PIDs.

    # Cut off the device prefix:
    pids = result.split(" ")
    # print("DEBUG: reset_vt() pids=%s" % (pids,))
    for pid in pids:
        # fuser command returns bunch of header spaces, skip empty pid's.
        if pid != "":
            pid_n = int(pid)
            if pid_n > 0:
                cmd = f"sudo kill -SIGKILL {pid_n}"
                try:
                    result = check_output(cmd, shell=True, text=True)
                    pids_killed += [pid_n]
                except:  # noqa: S110
                    pass  # Silently ignore kill errors
    return pids_killed
    # deallocvt


def cvt(vt_number=1, loggr=None):
    cmd = f"chvt {vt_number}"
    try:
        result = check_output(cmd, shell=True, text=True)
        if loggr:
            loggr.debug(f"cvt({vt_number}) cmd={cmd} result={result}")
    except Exception as err:
        if loggr:
            loggr.error(f'Error {type(err)} "{err}" in cvt({vt_number}) cmd={cmd}')


def open_vt(vt_number, app_path, user=None, do_sudo=True, do_chvt=True, do_nohup=True, loggr=None):
    # Use `exec < /dev/tty1` at the start of the target script
    # See https://superuser.com/questions/584931/howto-start-an-interactive-script-at-ubuntu-startup

    # Kill current process(es) on VT (otherwise 2 or more processes pile up on one TTY and it is ugly)
    reset_vt(vt_number)

    # Add `exec < /dev/ttyN` and `sudo -u <user>` to the app_path
    su = f"sudo -u {user} " if user else ""
    command = f'/usr/bin/bash -c "exec < /dev/tty{vt_number} && {su}{app_path}"'

    options = "-f "
    if do_chvt:
        options += "-s "
    # if x: options += '-u '
    # if y: options += '-l '
    # cmd = 'sudo /bin/openvt -c 1 -f -- %s' % (app_path)
    # cmd = 'sudo /bin/openvt -c 1 -f -s -u -l -- %s' % (app_path)
    openvt_cmd = f'{"sudo " if do_sudo else ""}/usr/bin/openvt -c {vt_number} {options}-- {command}'.replace('"', '\\"')

    if do_nohup:
        # Wrap openvt_cmd in `nohup`.
        cmd = f'/usr/bin/nohup /usr/bin/bash -c "{openvt_cmd}" >&2'
    else:
        cmd = f'/usr/bin/bash -c "{openvt_cmd}" '
    # cmd = openvt_cmd

    result = check_output(cmd, shell=True, text=True)
    if loggr is not None:
        loggr.debug(f"open_vt() cmd={cmd} result={result}")
    return result


def get_pi_revision():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as cpuinfo:
            for line in cpuinfo:
                if line.startswith("Revision"):
                    # return int(line[line.index(':') + 1:], 16) & 0xFFFFF
                    return line[line.index(":") + 1 :].strip()
                # https://www.raspberrypi-spy.co.uk/2012/09/checking-your-raspberry-pi-board-version/
        raise RuntimeError("No revision found.")
    except:
        return None


def get_pi_model():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as cpuinfo:
            for line in cpuinfo:
                if line.startswith("Model"):
                    return line[line.index(":") + 1 :].strip()
        raise RuntimeError("No model found.")
    except:
        return None


def eth0_mac():
    try:
        mac = get_mac()
        mac = f"{mac:012x}"
    except:
        mac = None
    if not mac:
        ifaces = ifconfig()
        key = "eth0"
        if key in ifaces:
            iface = ifaces[key]
            if "mac" in iface:
                mac = iface["mac"]
    return mac


def strftimedelta(format_str: str, td: datetime.timedelta) -> str:
    zero_td = datetime.timedelta(0)
    # Create a datetime object with a dummy date
    dummy_date = datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc)
    # Add the timedelta object to the dummy date to get a datetime object
    td_datetime = dummy_date + td
    # Format the datetime object using strftime() and the given format string
    if td >= zero_td:
        formatted_td = td_datetime.strftime(format_str)
    else:
        formatted_td = "-" + (zero_td - td_datetime).strftime(format_str)
    return formatted_td


def path_sanitize(path_str: str, replace: str = "", more: str = "") -> str:
    """Remove all symbols prohibited in path."""
    out = path_str
    for c in '><|*?":' + more:
        out = out.replace(c, replace)
    if os.name == "nt" and len(path_str) > 1 and path_str[1] == ":":
        # Restore colon after Drive name on Windows.
        out = f"{out[:1]}:{out[1+len(replace):]}"
    return out


def path_part_sanitize(part: str, replace: str = "", more: str = "") -> str:
    """Remove all symbols prohibited in path part."""
    out = part
    for c in '><|*?":\\/' + more:
        out = out.replace(c, replace)
    return out


def find_path(path_name: str, paths: list[str], loggr=None, is_dir=False) -> str:
    path_basename = os.path.basename(path_name)
    if path_basename != path_name:
        paths = [os.path.dirname(path_name)] + paths
    for path in paths:
        # Do ~ expansion, and use absolute path
        full_path = os.path.realpath(os.path.expanduser(os.path.join(path, path_basename)))
        if (os.path.isdir if is_dir else os.path.isfile)(full_path):
            if loggr:
                loggr.debug(f'{"Directory" if is_dir else "File"} "{path_name}" found at "{full_path}".')
            return full_path
    if loggr:
        paths_str = '", "'.join(paths)
        loggr.warning(f'{"Directory" if is_dir else "File"} "{path_name}" not found. Paths searched: "{paths_str}"')
    return None


def download_and_execute(url, downloaded_file_path, command=None, remove_after=False, timeout=30, loggr=None) -> int:
    """Download from given URL a file and either execute the file or optionally execute the given command. Intended use is to download and install software.

    Args:
        url (str): URL to the download file
        downloaded_file_path (str): Path to where store the file
        command (_type_, optional): Command to execute once the file is downloaded. Defaults to None.
        remove_after (bool, optional): True to remove downloaded file after. Defaults to False.
        timeout (int, optional): Maximum time to wait. Defaults to 30.

    Returns:
        int: Error code
    """
    # Download the executable file
    try:
        with open(downloaded_file_path, "wb") as file:
            response = requests.get(url, stream=True, timeout=timeout)
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
                    if loggr:
                        loggr.info(".", end="")
    except requests.exceptions.RequestException as e:
        if loggr:
            loggr.error(f'Error {type(e)} "{e}" while downloading file "{downloaded_file_path}" from {url}.')
        return 1

    # Run the downloaded executable
    try:
        if not command:
            command = [downloaded_file_path]
        run(command, shell=True, check=True)
    except CalledProcessError as e:
        if loggr:
            loggr.error(f'Error {type(e)} "{e}" while running the command "{" ".join(command)}" for the downloaded file "{downloaded_file_path}".')
        # TODO: (when needed) Remove the downloaded file.
        return 1

    # Optionally, you can remove the downloaded file after it's executed
    if remove_after:
        try:
            os.remove(downloaded_file_path)
        except OSError as e:
            if loggr:
                loggr.error(f'Error {type(e)} "{e}" trying to remove the downloaded file "{downloaded_file_path}".')

    return 0


class PeriodicTask(threading.Thread):
    """Helper class to manage periodic tasks."""

    def __init__(self, interval, task_fnc, *args, **kwargs):
        """Constructor.

        Args:
            interval (int | float): Period or the task
            task_fnc (function): Task function to call
            *args: Optional arguments to pass to the task function.
            **kwargs: Optional keyword arguments to pass to the task function.
        """
        super().__init__()
        self.interval = interval
        self._task_fnc, self._args, self._kwargs = task_fnc, args, kwargs
        self._kill_event = threading.Event()
        self._pause_event = threading.Event()
        super().start()

    def __del__(self):
        self.kill()

    def run(self):
        gen = self._interval_generator()
        next(gen)  # Start the generator
        while not self._kill_event.is_set():
            try:
                next_run = next(gen)
                time.sleep(max(0, next_run - time.monotonic()))
                if not self._pause_event.is_set():
                    self._task_fnc(*self._args, **self._kwargs)
            except StopIteration:  # noqa: PERF203
                break

    def kill(self):
        self._kill_event.set()
        self._pause_event.set()
        self.interval = 0
        self._task_fnc, self._args, self._kwargs = None, None, None
        self.join()

    def stop(self):
        self._pause_event.set()

    def start(self):
        self._pause_event.clear()

    def _interval_generator(self):
        last_time = time.monotonic()
        while True:
            next_time = last_time + self.interval
            if next_time < time.monotonic():
                # Catch up schedule / skip the run(s) if the previous task run took longer than the interval
                next_time = time.monotonic() + self.interval
            last_time = next_time
            yield next_time


def print_task(*args):
    print(*args)


def unittest_periodic_task():
    pt = PeriodicTask(0.5, print_task, "  - task1")
    pt2 = PeriodicTask(3, print_task, "  -        task2")

    print("starting 1, 2:")
    pt.start()
    pt2.start()
    time.sleep(3)

    print("stopping 1:")
    pt.stop()
    time.sleep(3)

    print("re-starting 1:")
    pt.start()
    time.sleep(3)

    print("stopping 1:")
    pt.stop()
    time.sleep(3)

    print("re-starting 1:")
    pt.start()
    time.sleep(3)

    print("killing:")
    pt.kill()
    pt2.kill()

    print("re-starting 1:")
    pt.start()
    time.sleep(3)

    pt = None
    pt2 = None
    print("DONE")


def main():
    unittest_periodic_task()


if __name__ == "__main__":
    main()
