#!/usr/bin/env python3
from __future__ import annotations

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation

import logging
import os
import platform
import shutil
import sys
from typing import Callable, Optional

from collections.abc import Iterator

import psutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != "__main__" else None)
# logger.setLevel(logging.DEBUG)

_our_exe_name = os.path.basename(sys.argv[0])


def which(progname: str | list[str], additional_paths: Optional[list[str]] = None, exit_on_fail: bool = False) -> str | None:
    if isinstance(progname, str):
        progname = [progname]
    if not additional_paths:
        additional_paths = get_additional_paths()
    paths = [""] + additional_paths
    for name in progname:
        for path in paths:
            prog = shutil.which(os.path.join(path, name))
            if prog and os.access(prog, os.X_OK):
                return prog
    if exit_on_fail:
        print(f"{_our_exe_name}: cannot find {progname[0]} -- will not be able to continue")
        sys.exit(1)

    return None


def get_additional_paths() -> list[str]:
    paths: list[str] = []
    if platform.system() == "Darwin":
        candidates = [
            "/usr/local/bin",
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
        ]
        paths += [p for p in candidates if os.path.isdir(p)]
    return paths


def find_file(search_dir_list: list[str], filename: str, descr: str = "input", loggr: logging.Logger = logger) -> str | None:
    """Find file in all directories given.

    @see find_path() in app_utils.py

    Args:
        search_dir_list: List of directories to search
        filename: File name
        descr: Description of the file for logging. Defaults to "input".
        loggr: Logger to use. Defaults to logger.

    Returns:
        None or full path to the found file.
    """
    for i, d in enumerate(search_dir_list):
        fullpath = os.path.realpath(os.path.expanduser(os.path.join(d, filename)))
        if os.path.isfile(fullpath):
            if loggr:
                loggr.info(f'Found {descr} file "{filename}" (@idx{i})')  # full_path is useless to show in bundled app
            return fullpath
    return None


def partition_device_name(partition: psutil._common.sdiskpart) -> str:  # pyright: ignore[reportAttributeAccessIssue]
    device_name = partition.device
    if device_name == "/dev/root" and os.name != "nt":
        with open("/proc/mounts", encoding="ascii") as f:
            for line in f.readlines():
                if line.startswith("/dev/"):
                    parts = line.split()
                    if parts[1] == partition.mountpoint:
                        device_name = parts[0]
                        break
    return device_name


def disk_has_space(printer: Optional[Callable[[str]]] = None, disk_usage_limit: Optional[int] = None) -> tuple[bool, list[str]]:
    healthy = True
    summary = []
    if disk_usage_limit:
        disk_usage = psutil.disk_usage("/")
        if disk_usage.percent >= disk_usage_limit:
            healthy = False
            msg = f"Disk space usage {disk_usage.percent}% is above {disk_usage_limit}%"
            summary += [msg]
            if printer:
                printer(msg)

    # if psutil.disk_partitions()[0].fstype == 'NTFS' and psutil.win32.disk_usage(psutil.disk_partitions()[0].device).total < 10000000000:
    #     if printer: printer("Low disk space on NTFS partition")
    return healthy, summary


def disk_is_healthy_WIP(printer: Optional[Callable[[str]]] = None) -> tuple[bool, list[str]]:
    healthy = True
    summary = []
    # disk_io = psutil.disk_io_counters()
    # if disk_io.busy > 0:
    #     if printer: printer("Disk I/O is busy")
    # if disk_io.read_time > 0 or disk_io.write_time > 0:
    #     if printer: printer("Disk read/write time is not zero")
    # if disk_io.read_count == 0 and disk_io.write_count == 0:
    #     if printer: printer("No disk read/write activity")
    device_name = partition_device_name(psutil.disk_partitions()[0])
    disk_counters = psutil.disk_io_counters(perdisk=True)[device_name]
    # disk_errors = disk_counters.errors  # TODO: (when needed) FIXME - .errors is not present, digging into code can find .read_count, .write_count, etc.
    disk_errors = 1
    if disk_errors is not None and disk_errors > 0:
        healthy = False
        msg = f"{disk_errors} Disk errors detected in {device_name} || NOTE: THIS IS A DUMMY ERROR FOR WIP - NEED TO IMPLEMENT THE FUNCTION!"
        summary += [msg]
        # if printer: printer(msg)

    # if psutil.disk_partitions()[0].fstype == 'NTFS' and psutil.win32.disk_usage(psutil.disk_partitions()[0].device).total < 10000000000:
    #     if printer: printer("Low disk space on NTFS partition")
    return healthy, summary


def walklevel(root_dir: Optional[str] = None, level: int = 1) -> Iterator[tuple[str, list[str], list[str]]]:
    """Similar to os.walk() but with a level parameter.

    From https://stackoverflow.com/a/234329

    Args:
        root_dir: Directory to traverse. If None - will use current directory.
        level: How many levels to return. Defaults to 1.

    Raises:
        FileNotFoundError: If root_dir directory does not exist

    Yields:
        Iterator[tuple[str, list[str], list[str]]]: _description_

    Example:
        ```
        from os_utils import walklevel
        for root, dirs, files in walklevel('python/Lib/email'):
            print(root, "consumes", end="")
            print(sum(getsize(join(root, name)) for name in files), end="")
            print("bytes in", len(files), "non-directory files")
            if 'CVS' in dirs:
                dirs.remove('CVS')  # don't visit CVS directories
        ```
    """
    if root_dir is None:
        root_dir = os.path.realpath(os.getcwd())
    root_dir = root_dir.rstrip(os.path.sep)
    if not os.path.isdir(root_dir):
        raise FileNotFoundError(f"No such directory: {root_dir}")
    num_sep = root_dir.count(os.path.sep)
    for root, dirs, files in os.walk(root_dir):
        yield root, dirs, files
        num_sep_this = root.count(os.path.sep)
        if num_sep + level <= num_sep_this:
            del dirs[:]
