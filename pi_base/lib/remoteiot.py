#!/usr/bin/env python3

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation

# WIP: Creating: Service to manage remote control of devices
from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import socket
from subprocess import check_output
import sys
from typing import IO, Optional
from collections.abc import Iterable

# "modpath" must be first of our modules
from pi_base.modpath import app_conf_dir  # pylint: disable=wrong-import-position

# pylint: disable=wrong-import-order
from .app_utils import get_conf, find_path
from .gd_service import gd_connect, GoogleDriveFile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != "__main__" else None)
# logger.setLevel(logging.DEBUG)

g_conf_file_name = "remote_secrets.yaml"
g_db_file_name = "devices.csv"

gd_secrets_file_default = "sa_client_secrets.json"
# gd_dst_dir_default = ''

MAX_SN = 1000


class Remoteiot:
    def __init__(self, yaml_file: Optional[str] = None, db_file: Optional[str] = None, gd_secrets: Optional[str] = None, loggr: Optional[logging.Logger] = logger, debug: bool = False) -> None:
        self.yaml_file = yaml_file
        self.db_file = db_file
        self.debug = debug
        if not loggr:
            raise ValueError("Please provide loggr argument")
        self.loggr = loggr

        if not app_conf_dir:
            raise RuntimeError("Was not able to find app directory")

        root = os.path.dirname(os.path.realpath(__file__))
        base = os.path.abspath(os.path.join(root, os.pardir, os.pardir))
        self.config_paths = [
            root,
            os.path.join(base, "secrets"),
            base,
            ".",
            "./remoteiot.com",
            "../remoteiot.com",
            os.path.join(app_conf_dir, "app"),
            app_conf_dir,
            "~",
        ]
        self.secrets_paths = [
            root,
            os.path.join(base, "secrets"),
            base,
            os.path.join(app_conf_dir, "app"),
            app_conf_dir,
            "~",
        ]

        # Describe columns in the device database:
        self.cols = ["key", "device id", "device name"]
        self.cols_optional = ["device group", "notes"]
        self.cols_secret = ["key"]

        # Compiled columns from device database file:
        self.db_file_cols: Optional[list[str]] = None

        self.conf = self.conf_file_load()
        # Look for devices DB in Google Drive first
        self.gd_file = None
        gd_secrets_file = self.conf.get_subkey("GoogleDrive", "secrets", os.path.join(app_conf_dir, gd_secrets_file_default))
        gd_secrets = find_path(gd_secrets_file, self.secrets_paths, self.loggr) if gd_secrets_file else None
        if gd_secrets:
            self.gds, extras = gd_connect(self.loggr, gd_secrets, {"gd_devices_folder_id": None, "gd_devices_file_title": None}, skip_msg="Cannot continue.")
            if not self.gds:
                raise ValueError("Failed loading GoogleDrive secrets or connecting.")
            self.gd_folder_id = extras["gd_devices_folder_id"] if extras else None
            self.gd_file_title = extras["gd_devices_file_title"] if extras else None
            if self.gd_file_title and self.gd_folder_id:
                devices, self.gd_file = self.db_file_load_gd(self.gd_file_title, self.gd_folder_id)
                self.devices = devices or []
            else:
                raise ValueError(f'Expected non-empty gd_devices_folder_id and gd_devices_file_title in "{gd_secrets}" file.')
        else:
            devices = self.db_file_load()
            self.devices = devices or []

    def db_file_load_gd(self, gd_file_title: str, gd_folder_id: str) -> tuple[Optional[list[dict[str, Optional[str]]]], Optional[GoogleDriveFile]]:
        if not self.gds:
            raise ValueError("Expected non-empty self.gds.")
        devices = None
        # gd_file_id = 'TBD'
        # in_file_fd = self.gds.open_file_by_id(gd_file_id)
        self.loggr.info(f'Reading device database from Google Drive "{gd_file_title}" file.')
        in_file_fd = self.gds.maybe_create_file_by_title(gd_file_title, gd_folder_id)
        if in_file_fd:
            content = in_file_fd.GetContentString()
            buffered = io.StringIO(content)
            devices = self.db_file_load_fd(buffered)
        return devices, in_file_fd

    def db_file_load(self) -> list[dict[str, Optional[str]]]:
        if not self.db_file:
            self.db_file = find_path(g_db_file_name, self.config_paths, self.loggr)
        if not self.db_file:
            # raise ValueError('Please provide device database file')
            self.loggr.warning("No device database file found.")
            return []

        with open(self.db_file, newline="", encoding="utf-8") as in_file_fd:
            self.loggr.info(f'Reading device database from "{self.db_file}" file.')
            return self.db_file_load_fd(in_file_fd)

    def db_file_load_fd(self, in_file_fd: Iterable[str]) -> list[dict[str, Optional[str]]]:
        csvreader = csv.reader(in_file_fd, delimiter=",", quotechar='"')
        input_row_num = 0
        got_header = False
        columns = []
        devices = []
        for row in csvreader:
            input_row_num += 1
            row_stripped = []
            for i, c_in in enumerate(row):
                c = c_in.strip()  # Strip comments in cells except first:
                if i > 0 and len(c) > 0 and c[0] == "#":
                    c = ""
                row_stripped += [c]
            if len(row) == 0:
                continue
            if row_stripped[0][0] == "#":
                if not got_header:
                    # Got header row - parse columns
                    got_header = True
                    columns = [c.lower().lstrip("#").strip() for c in row_stripped]
                    self.db_file_cols = row  # save header for when writing to the self.db_file

                    for c in self.cols:
                        key = c.replace(" ", "_")
                        if c not in columns:
                            raise ValueError(f'Cannot find column {c} in device database file "{self.db_file}"')

            else:
                # Got data row
                device = {}
                # for c in self.cols + self.cols_optional:
                #     key = c.replace(' ', '_')
                for col, c in enumerate(columns):
                    key = c.replace(" ", "_")
                    val = row_stripped[col] if col < len(row) else None
                    device[key] = val
                if device:
                    devices += [device]
        if not got_header and not devices:
            # File is empty (perhaps was just created), init the columns
            self.db_file_cols = [c.title() for c in self.cols + self.cols_optional]
            self.db_file_cols[0] = "# " + self.db_file_cols[0]
        return devices

    def db_file_save(self, devices: list[dict[str, Optional[str]]], out_file: str) -> None:
        with open(out_file, "w", newline="", encoding="utf-8") as out_file_fd:
            self.loggr.info(f'Writing device database to "{out_file}" file.')
            self.db_file_save_fd(devices, out_file_fd)

    def db_file_save_fd(self, devices: list[dict[str, Optional[str]]], out_file_fd: IO) -> None:
        if not self.db_file_cols:
            raise ValueError("Expected non-empty self.db_file_cols.")
        csvwriter = csv.writer(out_file_fd, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)

        # Write header
        csvwriter.writerow(self.db_file_cols)
        for device in devices:
            row = []
            for c_in in self.db_file_cols:
                c = c_in.lower().lstrip("#").strip()
                key = c.replace(" ", "_")
                row += [device.get(key, "")]
            csvwriter.writerow(row)

    def db_file_save_back(self) -> int:
        try:
            if self.gd_file and self.gds:
                self.loggr.info(f'Writing device database to Google Drive "{self.gd_file["title"]}" file.')

                # buffered = io.BytesIO()
                # buffered.seek(0)
                buffered = io.StringIO()

                self.db_file_save_fd(self.devices, buffered)
                buffered.seek(0)
                # self.gd_file.content = buffered
                self.gd_file.SetContentString(buffered.getvalue())
                self.gd_file.Upload()
            elif self.db_file:
                self.db_file_save(self.devices, self.db_file)
        except Exception as e:
            self.loggr.error(f'Error {type(e)} "{e}" saving device database file')
            return -1
        return 0

    def db_add_device(self, device_id: str, device_name: str, device_group: Optional[str]) -> int:
        if self.find_device_by_id(device_id):
            raise ValueError(f'Device "{device_id}" already exists in the database')
        device = {
            "key": self.conf.get("service_key"),
            "device_id": device_id,
            "device_name": device_name,
            "device_group": device_group,
        }
        self.devices += [device]
        return self.db_file_save_back()

    def db_delete_device(self, device_id: str) -> int:
        device = self.find_device_by_id(device_id)
        if not device:
            raise ValueError(f'Device "{device_id}" is not found in the database')
        self.devices.remove(device)
        return self.db_file_save_back()

    def find_device_by_id(self, device_id: str) -> Optional[dict[str, Optional[str]]]:
        for device in self.devices:
            if device_id == device["device_id"]:
                return device
        return None

    def unique_device_id(self, site_id: str, app_type: str, app_name: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        device_id_template = self.conf.get("device_id_template") or "RPI-{sn:03d}"
        device_name_template = self.conf.get("device_name_template") or "RPI {sn:03d}"
        # device_group_template = self.conf.get('device_group_template', "RPI {sn:03d}")
        device_group = None
        values: dict[str, int | str] = {
            "sn": 1,
            "site_id": site_id,
            "app_type": app_type,
            "app_name": app_name,
        }
        while int(values["sn"]) < MAX_SN:
            device_id = device_id_template.format(**values)
            device_name = device_name_template.format(**values)
            # device_group = device_group_template.format(**values)
            if not self.find_device_by_id(device_id):
                return device_id, device_name, device_group
            values["sn"] = int(values["sn"]) + 1
        return None, None, None

    def conf_file_load(self) -> get_conf:
        if not self.yaml_file:
            self.yaml_file = find_path(g_conf_file_name, self.config_paths, self.loggr)
        if not self.yaml_file:
            raise ValueError("Please provide config file")
        self.loggr.info(f"Config file {self.yaml_file}")
        return get_conf(self.yaml_file)

    def port_is_open(self, host: str, port: int) -> bool:
        if host == "localhost":
            host = "127.0.0.1"
        try:
            host_addr = socket.gethostbyname(host)

            # if (captive_dns_addr == host_addr):
            #     return False

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect((host, port))
            # ? s.bind((host, port))
            s.close()
            return True
        except:
            return False

    def remoteiot_is_installed(self) -> tuple[bool, Optional[str]]:
        # Check if remoteiot config file is present
        remoteiot_conf_file = "/etc/remote-iot/configure"
        if not os.path.isfile(remoteiot_conf_file):
            return False, None

        # # Check if HTTPS port is open
        # if not self.port_is_open('localhost', 443):
        #     return False, None
        # This check will fail when remote session is active (it will occupy the port).

        device_id = None
        prefix = "name="
        try:
            with open(remoteiot_conf_file, encoding="utf-8") as fd:
                conf = fd.read().split("\n")
                for line in conf:
                    if line.startswith(prefix):
                        device_id = line[len(prefix) :].strip()
                        break
        except Exception as err:
            self.loggr.error(f'Error {type(err)} "{err}" reading remoteiot config file "{remoteiot_conf_file}".')

        return True, device_id

    def remoteiot_delete_device(self, device_id: str) -> int:
        # TODO: (when implemented by remoteiot) Delete device record on remoteiot
        return 0

    def remoteiot_install_and_connect(self, device_id: str, device_name: str, device_group: Optional[str]) -> int:
        # if self.debug and os.name == 'nt': return 0  # For debug: Pretend completed ok
        service_key = self.conf.get("service_key")
        if not service_key:
            raise ValueError("Configuration does not have Remoteiot service key.")
        cmd = f"curl -s -L 'https://remoteiot.com/install/install.sh' | sudo bash -s '{service_key}' '{device_id}' '{device_name}'"
        if device_group:
            cmd += f" '{device_group}'"
        cmd_log = cmd.replace(service_key, "*" * 10)
        self.loggr.info(f"Installing remoteiot, cmd={cmd_log} ...")
        p = check_output(cmd, shell=True, text=True)
        self.loggr.info(f"DONE installing remoteiot, cmd={cmd_log} result={p}")
        return 0

    def remoteiot_uninstall(self) -> int:
        if self.debug and os.name == "nt":
            return 0  # Pretend completed ok # TODO: (now) Remove when done debugging
        service_key = self.conf.get("service_key")
        if not service_key:
            raise ValueError("Configuration does not have Remoteiot service key.")
        cmd = f"curl -s -L 'https://remoteiot.com/install/uninstall.sh' | sudo bash -s '{service_key}'"
        cmd_log = cmd.replace(service_key, "*" * 10)
        self.loggr.info(f"Uninstalling remoteiot, cmd={cmd_log} ...")
        p = check_output(cmd, shell=True, text=True)
        self.loggr.info(f"DONE uninstalling remoteiot, cmd={cmd_log} result={p}")
        return 0

    def remoteiot_add_new_device(self, site_id: str, app_type: str, app_name: str) -> tuple[int, Optional[str], Optional[str]]:
        connected, device_id = self.remoteiot_is_installed()
        if connected:
            # if self.debug and os.name == 'nt': return 0  # For debug: Pretend completed ok
            # else:
            raise ValueError(f'This device is already connected to remoteiot.com service as device_id="{device_id}".')

        device_id, device_name, device_group = self.unique_device_id(site_id, app_type, app_name)
        if not device_id or not device_name:
            raise RuntimeError("Cannot find unique device id")

        err = self.remoteiot_install_and_connect(device_id, device_name, device_group)
        if err:
            # ? raise Exception(f'Cannot install remoteiot.com service, device_id={device_id}')
            return err, None, None

        err = self.db_add_device(device_id, device_name, device_group)
        if err:
            # ? raise Exception(f'Cannot add new record to device database for device_id={device_id}')
            return err, None, None

        return 0, device_id, device_name

    def remoteiot_add_named_device(self, device_id: str, device_name: str, device_group: Optional[str]) -> tuple[int, Optional[str], Optional[str]]:
        # connected, existing_device_id = self.remoteiot_is_installed()
        # if connected:
        #     if self.debug and os.name == 'nt': return 0  # For debug: Pretend completed ok
        #     else:
        #         raise ValueError(f'This device is already connected to remoteiot.com service as device_id="{existing_device_id}".')
        # TODO: (when needed) remove existing connection for re-connecting device under old name?

        device = self.find_device_by_id(device_id)
        my_device_name = (device["device_name"] or device_name) if device else device_name
        my_device_group = device["device_group"] if device else device_group

        err = self.remoteiot_install_and_connect(device_id, my_device_name, my_device_group)
        if err:
            # ? raise Exception(f'Cannot install remoteiot.com service, device_id={device_id}')
            return err, None, None

        if not device:
            err = self.db_add_device(device_id, my_device_name, my_device_group)
            if err:
                # ? raise Exception(f'Cannot add new record to device database for device_id={device_id}')
                return err, None, None

        return 0, device_id, my_device_name

    def remoteiot_delete_named_device(self, device_id: str) -> tuple[int, str, Optional[str]]:
        device = self.find_device_by_id(device_id)
        device_name = None
        if not device:
            raise ValueError(f'Device device_id="{device_id}" is not found.')

        device_name = device["device_name"]
        # device_group = device['device_group']

        err = self.remoteiot_delete_device(device_id)
        if err:
            # ? raise Exception(f'Cannot install remoteiot.com service, device_id={device_id}')
            return err, device_id, device_name

        err = self.db_delete_device(device_id)
        if err:
            # ? raise Exception(f'Cannot add new record to device database for device_id={device_id}')
            return err, device_id, device_name

        return 0, device_id, device_name


def cmd_devices(remote: Remoteiot, args: argparse.Namespace) -> int:
    show_secret = getattr(args, "show_secret", False)
    for device in remote.devices:
        vals = []
        for c in remote.cols + remote.cols_optional:
            key = c.replace(" ", "_")
            if show_secret or key not in remote.cols_secret:
                vals += [device[key] or ""]
        print(", ".join(vals))
    return 0


def cmd_unique(remote: Remoteiot, args: argparse.Namespace) -> int:
    print(*remote.unique_device_id(args.site_id, args.app_type, args.app_name), sep=", ")
    return 0


def cmd_add(remote: Remoteiot, args: argparse.Namespace) -> int:
    res, device_id, device_name = remote.remoteiot_add_new_device(args.site_id, args.app_type, args.app_name)
    if not res:
        print(f'Connected this device to remoteiot.com service as device_id="{device_id}" "{device_name}"')
    return res


def cmd_add_named(remote: Remoteiot, args: argparse.Namespace) -> tuple[int, Optional[str], Optional[str]]:
    device_id = args.device_id
    device_name = args.device_name
    device_group = None

    res, device_id, device_name = remote.remoteiot_add_named_device(device_id, device_name, device_group)
    if not res:
        print(f'Connected this device to remoteiot.com service as device_id="{device_id}" "{device_name}"')

    return res, device_id, device_name


def cmd_add_at_install(remote: Remoteiot, args: argparse.Namespace) -> int:
    conf = get_conf(filepath=f"{app_conf_dir}/app_conf.yaml")
    site_id = conf.get("Site")  # "Site" is filled at build time by make.py
    app_name = conf.get("Name")
    app_type = conf.get("Type")
    if not site_id:
        raise ValueError(f'App configuration file "{app_conf_dir}/app_conf.yaml" does not have "Site" set.')
    if not app_name:
        raise ValueError(f'App configuration file "{app_conf_dir}/app_conf.yaml" does not have "Name" set.')
    if not app_type:
        raise ValueError(f'App configuration file "{app_conf_dir}/app_conf.yaml" does not have "Type" set.')

    res, device_id, device_name = remote.remoteiot_add_new_device(site_id, app_type, app_name)
    if not res:
        print(f'Connected this device to remoteiot.com service as device_id="{device_id}" "{device_name}"')
    return res


def cmd_query(remote: Remoteiot, args: argparse.Namespace) -> int:
    connected, device_id = remote.remoteiot_is_installed()
    if connected:
        print(f'This device is connected to remoteiot.com service as device_id="{device_id}".')
        return 0
    print("This device is NOT connected to remoteiot.com service.")
    return 1


def cmd_delete_named(remote: Remoteiot, args: argparse.Namespace) -> int:
    device_id = args.device_id
    res, device_id, device_name = remote.remoteiot_delete_named_device(device_id)
    if not res:
        print(f'Deleted device_id="{device_id}" "{device_name}" from remoteiot.com service')
    return res


def parse_args(progname: str) -> tuple[argparse.Namespace, argparse.ArgumentParser]:
    parser = argparse.ArgumentParser(description="Manage remote access (add)")

    # Common optional arguments
    parser.add_argument("-v", "--verbose", help="Verbose output", action="store_true")
    parser.add_argument("-D", "--debug", help="Debug", action="store_true")

    # Positional argument for the command
    subparsers = parser.add_subparsers(title="Commands", dest="command")

    # "devices" command
    devices_parser = subparsers.add_parser("devices", help="Get list of remote devices")
    # devices_parser.add_argument('-s', '--show_secret', help='Show secret key', action='store_true')

    # "unique" command
    unique_parser = subparsers.add_parser("unique", help="Find a unique device ID")
    unique_parser.add_argument("site_id", type=str, help="Site ID")
    unique_parser.add_argument("app_type", type=str, help="App type")
    unique_parser.add_argument("app_name", type=str, help="App name")

    # 'site_id': 'BASE', 'app_type': 'blank','app_name': 'Blank',
    # "add" command
    add_parser = subparsers.add_parser("add", help="Add remote control to this device")
    add_parser.add_argument("site_id", type=str, help="Site ID")
    add_parser.add_argument("app_type", type=str, help="App type")
    add_parser.add_argument("app_name", type=str, help="App name")

    # "add_named" command
    add_named_parser = subparsers.add_parser("add_named", help="Add remote control to this device, with given id/name")
    add_named_parser.add_argument("device_id", type=str, help="Device ID")
    add_named_parser.add_argument("device_name", type=str, help="Device name (ignored if re-adding existing device)")

    # "add_at_install" command
    add_yaml_parser = subparsers.add_parser("add_at_install", help="Add remote control to this device, using app_conf.yaml file during install")

    # "query" command
    query_parser = subparsers.add_parser("query", help="Add remote control to this device")

    # "delete_named" command
    delete_named_parser = subparsers.add_parser("delete_named", help="Delete remote control from device with given id/name")
    delete_named_parser.add_argument("device_id", type=str, help="Device ID")

    # Parse the command line arguments
    args = parser.parse_args()
    return args, parser


def _main() -> int:
    progname = os.path.basename(sys.argv[0])
    args, parser = parse_args(progname)
    if args.debug:
        logger.setLevel(logging.DEBUG)
    logger.debug(f"DEBUG {vars(args)}")

    remote = Remoteiot(debug=args.debug)

    try:
        if args.command == "devices":
            return cmd_devices(remote, args)
        if args.command == "unique":
            return cmd_unique(remote, args)
        if args.command == "add":
            return cmd_add(remote, args)
        if args.command == "add_named":
            res, _device_id, _device_name = cmd_add_named(remote, args)
            return res
        if args.command == "add_at_install":
            return cmd_add_at_install(remote, args)
        if args.command == "delete_named":
            return cmd_delete_named(remote, args)
        if args.command == "query":
            return cmd_query(remote, args)

    except Exception as e:
        logger.error(f'Error {type(e)} "{e}"')
        return -1

    parser.print_help()
    return 1


if __name__ == "__main__":
    rc = _main()
    if rc:
        sys.exit(rc)
