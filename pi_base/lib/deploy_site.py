#!/usr/bin/env python3

# WIP: Creating: Service to manage sites db

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation
from __future__ import annotations

import argparse
import csv
import io
import logging
import os

# import socket
# from subprocess import check_output
import sys
from typing import Any, Optional
from collections.abc import Iterable, Mapping

# "modpath" must be first of our modules
from pi_base.modpath import get_app_workspace_dir, get_script_dir  # pylint: disable=wrong-import-position

# pylint: disable=wrong-import-order
from .app_utils import GetConf, find_path
from .gd_service import gd_connect, FileNotUploadedError  # pyright: ignore[reportAttributeAccessIssue]


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != "__main__" else None)
logger.setLevel(logging.DEBUG)

g_conf_file_name = "deploy_site_db_secrets.yaml"
g_db_file_name = "sites.csv"

MAX_SN = 1000


def eprint(*args: object, **kwargs: Mapping[str, Any]) -> None:
    kwargs1 = {"file": sys.stderr, **kwargs}
    print(*args, **kwargs1)


class DeploySite:
    """Deployment Site."""

    def __init__(self, site_id: Optional[str] = None, site_name: Optional[str] = None, sa_client_secrets: Optional[str] = None, description: Optional[str] = None):
        self.site_id = site_id
        self.site_name = site_name
        self.sa_client_secrets = sa_client_secrets
        self.description = description


class DeploySiteDB:
    """Store of Deployment Sites."""

    # TODO: (soon) DRY - move DB code into a generic class. Use here and in remoteiot.py.

    def __init__(self, conf_file=None, db_file=None, config_paths=None, secrets_paths=None, loggr=logger, debug=False):
        self.conf_file = conf_file
        self.db_file = db_file
        self.loggr = loggr
        self.debug = debug
        self.sites = []
        # script_dir = os.path.dirname(os.path.realpath(__file__))
        # workspace = os.path.abspath(os.path.dirname(os.path.dirname(script_dir)))
        script_dir = get_script_dir(__file__)
        workspace = get_app_workspace_dir()
        self.config_paths = config_paths or [
            script_dir,
            os.path.join(workspace, "secrets"),
            workspace,
            # os.path.join(app_conf_dir, 'app'),
            # app_conf_dir,
            "~",
        ]
        self.secrets_paths = secrets_paths or [
            script_dir,
            os.path.join(workspace, "secrets"),
            workspace,
            # os.path.join(app_conf_dir, 'app'),
            # app_conf_dir,
            "~",
        ]

        # Describe columns in the sites database:
        self.cols = ["site id", "site name", "sa client secrets"]
        self.cols_optional = ["description", "notes"]
        self.cols_secret = []  # ['key']

        # Compiled columns from sites database file:
        self.db_file_cols = None

        if not self.loggr:
            raise ValueError("Please provide loggr argument")

        self.conf = self.conf_file_load()

        # Look for sites DB in GoogleDrive first
        self.gd_file = None
        gd_secrets = self.conf.get_sub("GoogleDrive", "secrets")
        if gd_secrets:
            gd_secrets_actual, _paths = find_path(gd_secrets, self.secrets_paths, self.loggr)
            if not gd_secrets_actual:
                raise FileNotFoundError(f'Cannot find GoogleDrive secrets file "{gd_secrets}".')
            self.gds, extras = gd_connect(self.loggr, gd_secrets_actual, {"gd_sites_folder_id": None, "gd_sites_file_title": None}, skip_msg="Cannot continue.")
            if not self.gds:
                raise ValueError("Failed loading GoogleDrive secrets or connecting.")
            self.gd_folder_id = extras["gd_sites_folder_id"] if extras else None
            self.gd_file_title = extras["gd_sites_file_title"] if extras else None
            if not self.gd_folder_id or not self.gd_file_title:
                raise ValueError(f'Expected non-empty GoogleDrive gd_folder_id and gd_file_title in GoogleDrive secrets file "{gd_secrets_actual}".')
            self.sites, self.gd_file = self.db_file_load_gd(self.gd_file_title, self.gd_folder_id)
        else:
            file = self.conf.get_sub("LocalFile", "file", default=g_db_file_name)
            self.sites = self.db_file_load(file)

    def db_file_load_gd(self, gd_file_title: str, gd_folder_id: str, create_if_missing: bool = True):
        # gd_file_id = 'TBD'
        # in_file_fd = self.gds.open_file_by_id(gd_file_id)
        if not self.gds:
            raise ValueError("Expected non-empty self.gds.")
        sites = None
        self.loggr.info(f'Reading sites database from GoogleDrive "{gd_file_title}" file.')
        if create_if_missing:
            in_file_fd, created = self.gds.maybe_create_file_by_title(gd_file_title, gd_folder_id)
        else:
            in_file_fd, created = self.gds.get_file_by_title(gd_file_title, gd_folder_id), False

        if created:
            sites = []
            self.db_file_cols_init()
        elif in_file_fd:
            try:
                content = in_file_fd.GetContentString()
            except FileNotUploadedError as err:
                self.db_file_cols_init()
                return [], in_file_fd
            buffered = io.StringIO(content)
            sites = self.db_file_load_fd(buffered)
        else:  # if not in_file_fd:
            raise FileNotUploadedError("Failed to create file on GoogleDrive.")

        return sites, in_file_fd

    def db_file_load(self, default_file: Optional[str] = None) -> list[DeploySite]:
        if not self.db_file:
            self.db_file, _paths = find_path(default_file or g_db_file_name, self.config_paths, self.loggr)
        if not self.db_file:
            raise ValueError("Please provide sites database file")

        with open(self.db_file, newline="", encoding="utf-8") as in_file_fd:
            self.loggr.info(f'Reading sites database from "{self.db_file}" file.')
            return self.db_file_load_fd(in_file_fd)

    def db_file_load_fd(self, in_file_fd: Iterable[str]) -> list[DeploySite]:
        csvreader = csv.reader(in_file_fd, delimiter=",", quotechar='"')
        input_row_num = 0
        got_header = False
        columns = []
        sites = []
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
                            raise ValueError(f'Cannot find column {c} in sites database file "{self.db_file}"')

            else:
                # Got data row
                site = DeploySite()
                if site:
                    for col, c in enumerate(columns):
                        key = c.replace(" ", "_")
                        val = row_stripped[col] if col < len(row) else None
                        setattr(site, key, val)
                    sites += [site]
        if not got_header and not sites:
            # File is empty (perhaps was just created), init the columns
            self.db_file_cols_init()
        return sites

    def db_file_cols_init(self):
        self.db_file_cols = [c.title() for c in self.cols + self.cols_optional]
        self.db_file_cols[0] = "# " + self.db_file_cols[0]

    def db_file_save(self, sites, out_file: str) -> None:
        with open(out_file, "w", newline="", encoding="utf-8") as out_file_fd:
            self.loggr.info(f'Writing sites database to "{out_file}" file.')
            self.db_file_save_fd(sites, out_file_fd)

    def db_file_save_fd(self, sites, out_file_fd):
        if not self.db_file_cols:
            raise ValueError("Expected non-empty list in self.db_file_cols.")
        csvwriter = csv.writer(out_file_fd, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)

        # Write header
        csvwriter.writerow(self.db_file_cols)
        for site in sites:
            row = []
            for c_in in self.db_file_cols:
                c = c_in.lower().lstrip("#").strip()
                key = c.replace(" ", "_")
                row += [getattr(site, key, "")]
            csvwriter.writerow(row)

    def db_add_site(self, site: DeploySite):
        if self.find_site_by_id(site.site_id):
            raise ValueError(f'Site "{site.site_id}" already exists in the database')
        self.sites += [site]
        try:
            if self.gd_file and self.gds:
                self.loggr.info(f'Writing site database to GoogleDrive "{self.gd_file["title"]}" file.')

                # buffered = io.BytesIO()
                # buffered.seek(0)
                buffered = io.StringIO()

                self.db_file_save_fd(self.sites, buffered)
                buffered.seek(0)
                # self.gd_file.content = buffered
                self.gd_file.SetContentString(buffered.getvalue())
                self.gd_file.Upload()
            elif self.db_file:
                self.db_file_save(self.sites, self.db_file)
        except Exception as e:  # pylint: disable:broad-exception-caught
            self.loggr.error(f'Error {type(e)} "{e}" saving site database file')
            return -1
        return 0

    def find_site_by_id(self, site_id) -> DeploySite | None:
        for site in self.sites:
            if site_id == site.site_id:
                return site
        return None

    def unique_site_id(self):
        site_id_template = self.conf.get("site_id_template", "SITE-{sn:03d}")
        site_name_template = self.conf.get("site_name_template", "SITE {sn:03d}")
        # site_group_template = self.conf.get('site_group_template', "SITE {sn:03d}")
        site_group = None
        sn = 1
        while sn < MAX_SN:
            site_id = site_id_template.format(sn=sn)
            site_name = site_name_template.format(sn=sn)
            # site_group = site_group_template.format(sn=sn)
            if not self.find_site_by_id(site_id):
                return site_id, site_name, site_group
            sn += 1
        return None, None, None

    def conf_file_load(self):
        if not self.conf_file:
            self.conf_file, _paths = find_path(g_conf_file_name, self.config_paths, self.loggr)
        if not self.conf_file:
            raise ValueError("Please provide config file")
        self.loggr.info(f"Config file {self.conf_file}")
        return GetConf(self.conf_file)

    # def add(self, name: str, site: DeploySite) -> int:
    #     return 0

    # def get(self, name: str) -> tuple[int, DeploySite | None]:
    #     return 0, None

    # def delete(self, name: str) -> int:
    #     return 0

    # def update(self, name: str, site: DeploySite) -> int:
    #     return 0


def cmd_unique(db: DeploySiteDB, _args) -> int:
    site_id, _site_name, _site_group = db.unique_site_id()
    print(site_id)
    return 0


def cmd_sites(db: DeploySiteDB, args) -> int:
    show_secret = getattr(args, "show_secret", False)
    for site in db.sites:
        vals = []
        for c in db.cols + db.cols_optional:
            key = c.replace(" ", "_")
            if show_secret or key not in db.cols_secret:
                vals += [getattr(site, key, "")]
        print(", ".join(vals))
    return 0


def cmd_add(db: DeploySiteDB, args) -> int:
    site = DeploySite(
        site_id=args.site_id,
        site_name=args.site_name,
        sa_client_secrets=args.sa_client_secrets,
        description=args.description,
    )
    try:
        res = db.db_add_site(site)
    except ValueError as err:
        eprint(f"{err}")
        res = 1
    if not res:
        print(f'Added new site to Sites DB site_id={site.site_id} "{site.site_name}"')
    return res


def _parse_args(progname: str) -> tuple[argparse.Namespace, argparse.ArgumentParser]:
    parser = argparse.ArgumentParser(description="Manage Deployment Sites (list,add)")

    # Common optional arguments
    # parser.add_argument('-v', '--verbose', help='Verbose output', action='store_true')
    parser.add_argument("-D", "--debug", help="Debug", action="store_true")
    # parser.add_argument("-c", "--config", dest="config_file", type=str, help="Config file to use", default="remote_secrets.yaml")

    # Positional argument for the command
    subparsers = parser.add_subparsers(title="Commands", dest="command")

    # Parsers for commands

    # "sites" command
    _sites_parser = subparsers.add_parser("sites", help="Get list of Deployment Sites")
    # _sites_parser.add_argument('-s', '--show_secret', help='Show secret key', action='store_true')

    # "add" command
    add_parser = subparsers.add_parser("add", help="Add a Deployment Site")
    add_parser.add_argument("site_id", type=str, help="Site id")
    add_parser.add_argument("site_name", type=str, help="Site name")
    add_parser.add_argument("sa_client_secrets", type=str, help="Site GoogleDrive ServiceAccount secrets file")
    add_parser.add_argument("-D", "--description", dest="description", help="Site description")

    # "get" command
    _get_parser = subparsers.add_parser("get", help="Get Deployment Site")

    # "unique" command
    _unique_parser = subparsers.add_parser("unique", help="Get Unique ID")

    # Parse the command line arguments
    args = parser.parse_args()
    return args, parser


def main(loggr=logger) -> int:
    progname = os.path.basename(sys.argv[0])
    args, parser = _parse_args(progname)
    if loggr:
        if args.debug:
            loggr.setLevel(logging.DEBUG)
        loggr.debug(f"DEBUG {vars(args)}")

    db = DeploySiteDB(loggr=loggr, debug=args.debug)

    try:
        if args.command == "sites":
            return cmd_sites(db, args)
        if args.command == "unique":
            return cmd_unique(db, args)
        if args.command == "add":
            return cmd_add(db, args)

    except Exception as e:  # pylint: disable:broad-exception-caught
        if loggr:
            loggr.error(f'Error {type(e)} "{e}" in command {args.command}')
        return -1

    parser.print_help()
    return 1


if __name__ == "__main__":
    rc = main()
    if rc:
        sys.exit(rc)
