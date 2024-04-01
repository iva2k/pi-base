#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import datetime
from functools import wraps
import importlib
import inspect
import json
import logging
import os
import platform
from subprocess import check_output, run, CalledProcessError
import threading
import time
from typing import Any, Callable, Optional, overload, TypeVar, TYPE_CHECKING
from collections.abc import Awaitable
from collections.abc import Generator, Mapping
from uuid import getnode as get_mac
# import zmq

import requests


if TYPE_CHECKING:
    from .loggr import Loggr


class AtDict(dict):
    # See https://stackoverflow.com/a/1328686
    # See more complete implementation https://github.com/Infinidat/munch/tree/develop "pip install munch" `from munch import Munch as AtDict; __all__ = ["AtDict"]`
    __getattr__ = dict.__getitem__

    # __setattr__ = dict.__setitem__
    # __delattr__ = dict.__delitem__
    def __setattr__(self, key, value):
        super().__setitem__(key, value)

    def __delattr__(self, item):
        super().__delitem__(item)


class Flag:
    def __init__(self, value) -> None:
        self.value = value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value


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


def uptime() -> str:
    cmd = "uptime"
    p = check_output(cmd, shell=True, text=True)
    x = p.split()
    return x[0]


def reboot(reboot_type: str, delay: int = 0, loggr: Optional[logging.Logger] = None) -> None:
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


def get_hostname() -> str:
    cmd = "hostname"
    result = check_output(cmd, shell=True, text=True)
    return result[:-1]


def set_hostname(wants: str) -> tuple[bool, str]:
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


def is_up() -> bool:
    cmd = "ping -c 1 8.8.8.8 2>/dev/null"
    try:
        p = check_output(cmd, shell=True, text=True)
    except CalledProcessError as e:
        return False
    return True


class iface_dev:
    def __init__(self) -> None:
        self.done = False
        self.ifaces: Optional[dict[str, list[str]]] = None
        self.t = threading.Thread(target=self.worker)
        self.t.start()

    def worker(self) -> None:
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
                    if len(iface) > 0 and mac and ip:
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

    def dump(self) -> None:
        print(f"\033[6;6H{self.ifaces!s}")


def get_ifconfig() -> list[str]:
    cmd = "ifconfig"
    try:
        p = check_output(cmd, shell=True, text=True)
    except:
        p = ""
    return p.split("\n")


def data_amount(if_type: str = "ppp0") -> tuple[int, int]:
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


def ifconfig() -> dict[str, dict[str, Optional[str]]]:
    out = get_ifconfig()
    ifaces: dict[str, dict[str, Optional[str]]] = {}
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


def get_iface(if_list: Optional[list[str]] = None, require_connected: bool = True) -> tuple[Optional[str], dict[str, Optional[str]]]:
    """Issue ifconfig command and parse the output to determine which interfaces are up.

    By up, it means the interface has been assigned an ipv4 address.

    Args:
        if_list: List of interface names to search for

    Returns:
        Tuple of eth0, dict of interface properties - for the first found connected interface from the given if_list
    """
    if not if_list:
        if_list = ["wlan0", "eth0"]
    ifaces = ifconfig()
    for key in if_list:
        if key in ifaces and (not require_connected or ifaces[key]["ipaddress"] is not None):
            return key, ifaces[key]
    return None, {"ipaddress": None, "mac": None}


def list_iw() -> list[str]:
    """List all WLAN interfaces (Linux only)."""
    cmd = "iw dev | awk '$1==\"Interface\"{print $2}'"
    try:
        p = check_output(cmd, shell=True, text=True)
    except:
        p = ""
    return [x for x in p.split("\n") if x]  # Remove blanks


def ping_test(url: str = "www.google.com", f_timeout_seconds: Optional[float] = None) -> bool:
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


def _fix_aiohttp() -> None:
    """Silence annoying aiohttp RuntimeError upon exit on Windows.

    See https://github.com/aio-libs/aiohttp/issues/4324#issuecomment-733884349
    """
    if platform.system() == "Windows":
        my_asyncio = importlib.import_module("asyncio")

        def silence_event_loop_closed(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                try:
                    return func(self, *args, **kwargs)
                except RuntimeError as e:
                    if str(e) != "Event loop is closed":
                        raise

            return wrapper

        # pylint: disable-next=protected-access
        my_asyncio.proactor_events._ProactorBasePipeTransport.__del__ = silence_event_loop_closed(my_asyncio.proactor_events._ProactorBasePipeTransport.__del__)  # noqa: SLF001


def _fix_aiohttp1() -> None:
    """Silence annoying aiohttp RuntimeError upon exit on Windows, by adding sleep during event loop shutdown."""
    if platform.system() == "Windows":
        my_asyncio = importlib.import_module("asyncio")
        origin_shutdown = my_asyncio.BaseEventLoop.shutdown_default_executor

        async def _shutdown(self):
            await origin_shutdown(self)
            await my_asyncio.sleep(1)

        my_asyncio.BaseEventLoop.shutdown_default_executor = _shutdown


_fix_aiohttp()
# _fix_aiohttp1()

_AT = TypeVar("_AT")


def run_async(future: Awaitable[_AT]) -> _AT:
    """Run the given future (result of an async function call) on an event loop until completion.

    Args:
        future: Future to run on an event loop (a result of an async function call)

    Returns:
        Result of the future
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(future)


def run_maybe_async(maybe_future: _AT | Awaitable[_AT]) -> _AT:
    """If the given maybe_future (result of a function call - either async, but not awaited or sync) is not awaited async call, run it on event loop until completion.

    Args:
        maybe_future: Future to run on an event loop (a result of an async function call) or result of non-async function call to pass through

    Returns:
        Result of the future
    """
    if inspect.isawaitable(maybe_future):
        return run_async(maybe_future)
    else:
        # TODO: (soon) Report Pyright bug that barks on completely legit TypeGuard-ed code:
        return maybe_future  # pyright: ignore[reportReturnType]


# app_info

# Allow list and dict types so .get() can get the whoie section
# _T = TypeVar("_T", str, float, int, bool, list, dict)
# _VT = TypeVar("_VT", str, float, int, bool, list, dict)
_T = TypeVar("_T")
_VT = TypeVar("_VT", bound=Any)


class GetConf:
    """Read configuration file (.yaml or .json) and provide access to its contents."""

    def __init__(self, filepath: Optional[str] = None) -> None:
        self.filepath: Optional[str] = None
        # self.conf: dict[str, bool | int | str | list | dict] = {}
        self.conf = {}
        if filepath:
            self.read_file(filepath)

    def read_file(self, filepath: str) -> None:
        with open(filepath, encoding="utf-8") as file:
            ext = os.path.splitext(filepath)[1].lower()
            if ext in [".yaml", ".yml"]:
                # import yaml  # pylint: disable:import-outside-toplevel
                yaml = importlib.import_module("yaml")

                self.conf = yaml.safe_load(file)
            elif ext in [".json"]:
                self.conf = json.load(file)
            else:
                raise NotImplementedError(f"Unsupported file type: {ext}")
                # TODO: (when needed) Implement for .ini .cfg .conf .xml
            self.filepath = filepath

    def __setitem__(self, key, val):
        self.conf[key] = val

    @overload
    def get(self, key: str, default: None = None, t: type[_VT] = str, check: bool = False) -> _VT | None:
        ...

    @overload
    def get(self, key: str, default: _T, t: type[_VT] = str, check: bool = False) -> _VT | _T:
        ...

    def get(self, key: str, default: _T | None = None, t: Optional[type[_VT]] = str, check: bool = False) -> _VT | _T | dict | None:
        if key in self.conf:
            # return self.conf[key]
            val = self.conf[key]
            if t and not isinstance(val, t):
                if check:
                    raise TypeError(f'Expected "{key}" to be of type "{t}", got a "{type(val)}"')
                if default is not None and not isinstance(val, type(default)):
                    return default
            return val
        return default

    @overload
    def get_subkey(self, key: str, key2: str, default: None = None, t: type[_VT] = str, check: bool = False) -> _VT | None:
        ...

    @overload
    def get_subkey(self, key: str, key2: str, default: _T, t: type[_VT] = str, check: bool = False) -> _VT | _T:
        ...

    def get_subkey(self, key: str, key2: str, default: _T | None = None, t: Optional[type[_VT]] = str, check: bool = False) -> _VT | _T | dict | None:
        if key in self.conf:
            conf = self.conf[key]
            if conf and key2 in conf:
                # return conf[key2]
                val = conf[key2]
                if t and not isinstance(val, t):
                    # if (not isinstance(val, t)) if t else isinstance(val, list):
                    if check:
                        raise TypeError(f'Expected "{key}.{key2}" to be of type "{t}", got a "{type(val)}"')
                    if default is not None and not isinstance(val, type(default)):
                        return default
                return val
        return default

    @overload
    def get_sub(self, *keys: str, default: None = None, t: type[_VT] = str, check: bool = False) -> _VT | None:
        ...

    @overload
    def get_sub(self, *keys: str, default: _T, t: type[_VT] = str, check: bool = False) -> _VT | _T:
        ...

    def get_sub(self, *keys: str, default: _T | None = None, t: Optional[type[_VT]] = str, check: bool = False) -> _VT | _T | dict | None:
        """Get sub-key of any depth, presented by `keys` list.

        Note: always provide default value and t type by name, otherwise they will be used as keys.

        Args:
            keys: keys to traverse to get the value.
            default: Default value to return if one of the keys is not found in the data. Defaults to None.
            t: Type of data expected to return. Defaults to str.
            check: True to enforce t type of return data. Defaults to False.

        Raises:
            TypeError: If check=True and data type does not match t.

        Returns:
            Value: the data as selected by the keys, or default.
        """
        val = default if len(keys) == 0 else self.conf
        try:
            for key in keys:
                if not val or not isinstance(val, dict):  # More generic: if not val or not hasattr(val, "__getitem__"):
                    return default
                if key in val:
                    val = val[key]
                else:
                    return default
            if len(keys) > 0 and val != self.conf:
                if t and not isinstance(val, t):
                    keys_str = ".".join(keys)
                    if check:
                        raise TypeError(f'Expected "{keys_str}" to be of type "{t}", got a "{type(val)}"')
                    if default is not None and not isinstance(val, type(default)):
                        return default
                return val
        except Exception:  # pylint: disable=broad-exception-caught
            if check:
                raise
        return default

    def dump(self) -> None:
        print(self.conf)


def get_fg_vt() -> None:
    # TODO: (when needed) Implement, use `cat /sys/class/tty/tty0/active` --> tty2 or `sudo fgconsole` -> 2
    pass


def reset_vt(vt_number: int) -> list[int]:
    # TODO: (when needed) reset vt to a login shell (kill all processes on the given VT)
    pids_killed: list[int] = []
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


def cvt(vt_number: int = 1, loggr: Optional[logging.Logger] = None) -> None:
    cmd = f"chvt {vt_number}"
    try:
        result = check_output(cmd, shell=True, text=True)
        if loggr:
            loggr.debug(f"cvt({vt_number}) cmd={cmd} result={result}")
    except Exception as err:
        if loggr:
            loggr.error(f'Error {type(err)} "{err}" in cvt({vt_number}) cmd={cmd}')


def open_vt(vt_number: int, app_path: str, user: Optional[str] = None, do_sudo: bool = True, do_chvt: bool = True, do_nohup: bool = True, loggr: Optional[logging.Logger] = None) -> str:
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


def get_pi_revision() -> Optional[str]:
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


def get_pi_model() -> Optional[str]:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as cpuinfo:
            for line in cpuinfo:
                if line.startswith("Model"):
                    return line[line.index(":") + 1 :].strip()
        raise RuntimeError("No model found.")
    except:
        return None


def eth0_mac() -> Optional[str]:
    mac = None
    try:
        mac_int = get_mac()
        mac = f"{mac_int:012x}"
    except:
        ifaces = ifconfig()
        key = "eth0"
        if key in ifaces:
            iface = ifaces[key]
            if "mac" in iface:
                mac = iface["mac"]
    return mac


def strftimedelta(format_str: str, td: datetime.timedelta) -> str:
    """Formats a timedelta object into a string based on the provided format string.

    It is intended to be similar to time.strftime and datetime.strftime() methods,
    but due to inherent nature of time delta, this function does not support the
    following format specifiers:

    %a, %A, %b, %B, %c, %d, %I, %j, %m, %p, %U, %w, %W, %x, %X, %y, %Y, %z, %Z

    The format string can include specifiers for days (%d), hours (%H), minutes (%M),
    seconds (%S), and microseconds (%f). If a higher unit specifier is not present
    in the format string, its value is converted and added to the next lower unit
    that is included. For example, if the format string only includes minutes and
    seconds, days and hours are converted to minutes.

    If the timedelta is negative, a minus sign is prefixed to the largest unit
    specified in the format string. This function correctly handles transferring
    values between units and formatting negative timedeltas.

    Args:
        format_str: The format string defining how the timedelta should be
        formatted. It supports the following specifiers: %d (days), %H (hours),
        %M (minutes), %S (seconds), and %f (microseconds).
    td: The timedelta object to format.

    Returns:
        The formatted string representation of the timedelta.

    Example:
        ```
        from datetime import timedelta
        td = timedelta(days=1, hours=2, minutes=30)
        strftimedelta('%H:%M:%S', td)
        # '26:30:00'
        ```
    """
    # Handle negative timedelta
    is_negative = td.total_seconds() < 0
    td = abs(td)

    # Calculate hours and minutes from seconds
    seconds = td.seconds
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    # Mapping for format specifiers to their corresponding values
    format_specifiers = {"%d": td.days, "%H": hours, "%M": minutes, "%S": seconds, "%f": td.microseconds}

    # Find the largest specifier in the format, and transfer the values down to it.
    # Mapping for format specifiers to transfer their corresponding values down
    specifiers_transfer = {"%d": 24, "%H": 60, "%M": 60, "%S": 1000000, "%f": 0}
    largest_specifier = None
    transfer = 0
    for specifier, value in specifiers_transfer.items():
        if specifier in format_str:
            largest_specifier = specifier
            format_specifiers[specifier] += transfer
            break
        transfer = (transfer + format_specifiers[specifier]) * value
        del format_specifiers[specifier]

    # Replace format specifiers in the format_str with their corresponding values
    for specifier, value in format_specifiers.items():
        formatted_value = f"{value:02}" if specifier != "%f" else f"{value:06}"
        if specifier == largest_specifier and is_negative:
            formatted_value = "-" + formatted_value
        format_str = format_str.replace(specifier, formatted_value)

    return format_str


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


def find_path(path_name: str, paths: list[str], loggr: Optional[logging.Logger] = None, is_dir: bool = False) -> tuple[str | None, list[str]]:
    path_basename = os.path.basename(path_name)
    if path_basename != path_name:
        paths = [os.path.dirname(path_name)]
    for path in paths:
        # Do ~ expansion, and use absolute path
        full_path = os.path.realpath(os.path.expanduser(os.path.join(path, path_basename)))
        if (os.path.isdir if is_dir else os.path.isfile)(full_path):
            if loggr:
                loggr.debug(f'{"Directory" if is_dir else "File"} "{path_name}" found at "{full_path}".')
            return full_path, paths
    if loggr:
        paths_str = '", "'.join([f'"{p}"' for p in paths])
        loggr.warning(f'{"Directory" if is_dir else "File"} "{path_name}" not found. Paths searched: [{paths_str}]')
    return None, paths


def translate_config_paths(config_paths: list[str], translations: Optional[list[tuple[str, str | Callable[[str], str]]]] = None) -> list[str]:
    """Translate config_paths - replace shortcuts given in translations with their full paths.

    It does NOT check paths existence or correctness.

    Args:
        config_paths: Paths to translate.
        translations: Translations list, each item is (from, to).
            It is recommended to start shortcut strings with ">" char which is distinguished from any valid path. Defaults to:
              - "./": Current working directory
              - ">root/": Root directory (where this module is located)
              - ">base/": Base directory (2 directories up from root)
              - ">app_conf_dir/": App config directory (load from pi_base.modpath when given in config_paths)

    Returns:
        List of translated paths.
    """

    def get_app_conf_dir(_shortcut: str) -> str:
        # from pi_base.modpath import app_conf_dir  # pylint: disable=wrong-import-position
        modpath = importlib.import_module("pi_base.modpath")
        return modpath.app_conf_dir

    def translate_one(path: str, translations: Optional[list[tuple[str, str | Callable[[str], str]]]] = None) -> str:
        if not translations:
            return path
        for t in translations:
            p, v = t
            p = p.rstrip("/")
            if path == p or path.startswith(p + "/"):
                if callable(v):
                    v = v(p + "/")
                path = v + path[len(p) :]
        return path

    if not translations:
        root = os.path.dirname(os.path.realpath(__file__))
        base = os.path.abspath(os.path.join(root, os.pardir, os.pardir))
        translations = [
            ("./", os.getcwd()),
            (">root/", root),
            (">base/", base),
            (">app_conf_dir/", get_app_conf_dir),
        ]
    return [translate_one(p, translations) for p in config_paths]


def maybe_create_file_dir(file_path: str, loggr: logging.Logger) -> str:
    """Ensure directory for the file exists, create if needed.

    Args:
        file_path: Full path to the file
        loggr: Logger

    Returns:
        File directory path
    """
    if file_path:
        file_dir = os.path.dirname(os.path.realpath(file_path))
        if not os.path.isdir(file_dir):
            if loggr:
                loggr.info(f'Path "{file_dir}" not found, creating...')
            try:
                os.makedirs(file_dir)
            except OSError as err:
                if loggr:
                    loggr.error(f'Error {err.errno} "{err.strerror}" creating directory "{file_dir}".')
                raise
            if loggr:
                loggr.info(f'Path "{file_dir}" created.')
    return file_dir


def download_and_execute(
    url: str, downloaded_file_path: str, command: Optional[list[str]] = None, remove_after: bool = False, timeout: int = 30, loggr: Optional[logging.Logger | Loggr] = None
) -> int:
    """Download from given URL a file and either execute the file or optionally execute the given command. Intended use is to download and install software.

    Args:
        url: URL to the download file
        downloaded_file_path: Path to where store the file
        command: Command to execute once the file is downloaded. Defaults to None.
        remove_after: True to remove downloaded file after. Defaults to False.
        timeout: Maximum time to wait. Defaults to 30.

    Returns:
        Error code, 0 for success
    """
    # Download the executable file
    try:
        with open(downloaded_file_path, "wb") as file:
            response = requests.get(url, stream=True, timeout=timeout)
            response.raise_for_status()
            log_kwargs: Mapping[str, Any] = {"end": ""}
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
                    if loggr:
                        loggr.info(".", **log_kwargs)
    except requests.exceptions.RequestException as e:
        if loggr:
            loggr.error(f'Error {type(e)} "{e}" while downloading file "{downloaded_file_path}" from {url}.')
        return 1

    # Run the downloaded executable
    if not command:
        command = [downloaded_file_path]
    try:
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

    def __init__(self, interval: float, task_fnc: Callable, *args: object, **kwargs: Mapping[str, Any]) -> None:
        """Constructor.

        Args:
            interval: Period or the task (in seconds)
            task_fnc: Task function to call
            *args: Optional arguments to pass to the task function.
            **kwargs: Optional keyword arguments to pass to the task function.
        """
        super().__init__()
        self.interval = interval
        self._task_fnc: Optional[Callable] = task_fnc
        self._args: object = args
        self._kwargs: Optional[Mapping[str, Any]] = kwargs
        self._kill_event = threading.Event()
        self._pause_event = threading.Event()
        super().start()

    def __del__(self) -> None:
        self.kill()

    def run(self) -> None:
        gen = self._interval_generator()
        next(gen)  # Start the generator
        while not self._kill_event.is_set():
            try:
                next_run = next(gen)
                time.sleep(max(0, next_run - time.monotonic()))
                if not self._pause_event.is_set() and self._task_fnc:
                    if self._kwargs:
                        self._task_fnc(*self._args, **self._kwargs)
                    else:
                        self._task_fnc(*self._args)
            except StopIteration:  # noqa: PERF203
                break

    def kill(self) -> None:
        self._kill_event.set()
        self._pause_event.set()
        self.interval = 0
        self._task_fnc, self._args, self._kwargs = None, None, None
        self.join()

    def stop(self) -> None:
        self._pause_event.set()

    def start(self) -> None:
        self._pause_event.clear()

    def _interval_generator(self) -> Generator[float, None, None]:
        last_time = time.monotonic()
        while True:
            next_time = last_time + self.interval
            if next_time < time.monotonic():
                # Catch up schedule / skip the run(s) if the previous task run took longer than the interval
                next_time = time.monotonic() + self.interval
            last_time = next_time
            yield next_time


def print_task(*args: object) -> None:
    print(*args)


def unittest_periodic_task() -> None:
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

    print("DONE")


def main() -> None:
    unittest_periodic_task()


if __name__ == "__main__":
    main()
