#!/usr/bin/env python3

import logging
import os
import platform
import shutil
import sys
from typing import List, Tuple

import psutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != '__main__' else None)
# logger.setLevel(logging.DEBUG)

_our_exe_name = os.path.basename(sys.argv[0])


def which(progname, additional_paths: List[str] = None, exit_on_fail=False):
    if isinstance(progname, str):
        progname = [progname]
    if not additional_paths:
        additional_paths = get_additional_paths()
    paths = [''] + additional_paths
    for name in progname:
        for path in paths:
            prog = shutil.which(os.path.join(path, name))
            if prog and os.access(prog, os.X_OK):
                return prog
    if exit_on_fail:
        print(f'{_our_exe_name}: cannot find {progname[0]} -- will not be able to continue')
        sys.exit(1)

    return None


def get_additional_paths():
    paths = []
    if platform.system() == 'Darwin':
        candidates = [
            '/usr/local/bin',
            '/opt/homebrew/bin',
            '/opt/homebrew/sbin',
        ]
        paths += [p for p in candidates if os.path.isdir(p)]
    return paths


def find_file(search_dir_list, filename, descr='input'):
    for i, d in enumerate(search_dir_list):
        fullpath = os.path.realpath(os.path.expanduser(os.path.join(d, filename)))
        if os.path.isfile(fullpath):
            logger.info(f'Found {descr} file "{filename}" (@idx{i})')  # full_path is useless to show in bundled app
            return fullpath
    return None


def partition_device_name(partition: psutil._common.sdiskpart) -> str:
    device_name = partition.device
    if device_name == '/dev/root' and os.name != 'nt':
        with open('/proc/mounts', 'r', encoding='ascii') as f:
            for line in f.readlines():
                if line.startswith('/dev/'):
                    parts = line.split()
                    if parts[1] == partition.mountpoint:
                        device_name = parts[0]
                        break
    return device_name


def disk_has_space(printer=None, disk_usage_limit: int = None) -> Tuple[bool, List[str]]:
    healthy = True
    summary = []
    if disk_usage_limit:
        disk_usage = psutil.disk_usage('/')
        if disk_usage.percent >= disk_usage_limit:
            healthy = False
            msg = f'Disk space usage {disk_usage.percent}% is above {disk_usage_limit}%'
            summary += [msg]
            if printer:
                printer(msg)

    # if psutil.disk_partitions()[0].fstype == 'NTFS' and psutil.win32.disk_usage(psutil.disk_partitions()[0].device).total < 10000000000:
    #     if printer: printer("Low disk space on NTFS partition")
    return healthy, summary


def disk_is_healthy(printer=None) -> Tuple[bool, List[str]]:
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
    disk_errors = disk_counters.errors
    if disk_errors is not None and disk_errors > 0:
        healthy = False
        msg = f'{disk_errors} Disk errors detected in {device_name}'
        summary += [msg]
        # if printer: printer(msg)
    # if psutil.disk_partitions()[0].fstype == 'NTFS' and psutil.win32.disk_usage(psutil.disk_partitions()[0].device).total < 10000000000:
    #     if printer: printer("Low disk space on NTFS partition")
    return healthy, summary
