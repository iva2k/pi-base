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
from typing import Optional

# "modpath" must be first of our modules
from pi_base.modpath import get_app_workspace_dir, get_script_dir  # pylint: disable=wrong-import-position
from .app_utils import get_conf, find_path
from .gd_service import gd_connect, FileNotUploadedError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != "__main__" else None)
logger.setLevel(logging.DEBUG)

progname = os.path.basename(sys.argv[0])

g_conf_file_name = "deploy_site_db_secrets.yaml"
g_db_file_name = "sites.csv"

MAX_SN = 1000


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


class DeploySite:
    """Deployment Site."""

    def __init__(self, site_id: Optional[str] = None, site_name: Optional[str] = None, sa_client_secrets: Optional[str] = None, description: Optional[str] = None):
        self.site_id = site_id
        self.site_name = site_name
        self.sa_client_secrets = sa_client_secrets
        self.description = description

    # Enable Subscript Notation:
    def __delitem__(self, key):
        self.__delattr__(key)

    def __getitem__(self, key):
        return self.__getattribute__(key)

    def __setitem__(self, key, value):
        self.__setattr__(key, value)

    def __contains__(self, key):
        return hasattr(self, key)


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

        # Look for sites DB in Google Drive first
        self.gd_file = None
        gd_secrets = self.conf.get_subkey("GoogleDrive", "secrets", None)
        if gd_secrets:
            gd_secrets = find_path(gd_secrets, self.secrets_paths, self.loggr)
            self.gds, extras = gd_connect(self.loggr, gd_secrets, {"gd_sites_folder_id": None, "gd_sites_file_title": None}, skip_msg="Cannot continue.")
            if not self.gds:
                raise ValueError("Failed loading GoogleDrive secrets or connecting.")
            self.gd_folder_id = extras["gd_sites_folder_id"] if extras else None
            self.gd_file_title = extras["gd_sites_file_title"] if extras else None
            self.sites, self.gd_file = self.db_file_load_gd(self.gd_file_title, self.gd_folder_id)
        else:
            self.sites = self.db_file_load()

    def db_file_load_gd(self, gd_file_title, gd_folder_id):
        # gd_file_id = 'TBD'
        # in_file_fd = self.gds.open_file_by_id(gd_file_id)
        in_file_fd = self.gds.maybe_create_file_by_title(gd_file_title, gd_folder_id)
        self.loggr.info(f'Reading sites database from Google Drive "{gd_file_title}" file.')
        try:
            content = in_file_fd.GetContentString()
        except FileNotUploadedError as err:
            self.db_file_cols_init()
            return [], in_file_fd
        buffered = io.StringIO(content)
        sites = self.db_file_load_fd(buffered)
        return sites, in_file_fd

    def db_file_load(self) -> list[DeploySite]:
        if not self.db_file:
            self.db_file = find_path(g_db_file_name, self.config_paths, self.loggr)
        if not self.db_file:
            raise ValueError("Please provide sites database file")

        with open(self.db_file, newline="", encoding="utf-8") as in_file_fd:
            self.loggr.info(f'Reading sites database from "{self.db_file}" file.')
            return self.db_file_load_fd(in_file_fd)

    def db_file_load_fd(self, in_file_fd) -> list[DeploySite]:
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
                # for c in self.cols + self.cols_optional:
                #     key = c.replace(' ', '_')
                for col, c in enumerate(columns):
                    key = c.replace(" ", "_")
                    val = row_stripped[col] if col < len(row) else None
                    site[key] = val
                if site:
                    sites += [site]
        if not got_header and not sites:
            # File is empty (perhaps was just created), init the columns
            self.db_file_cols_init()
        return sites

    def db_file_cols_init(self):
        self.db_file_cols = [c.title() for c in self.cols + self.cols_optional]
        self.db_file_cols[0] = "# " + self.db_file_cols[0]

    def db_file_save(self, sites, out_file):
        with open(out_file, "w", newline="", encoding="utf-8") as out_file_fd:
            self.loggr.info(f'Writing sites database to "{out_file}" file.')
            return self.db_file_save_fd(sites, out_file_fd)

    def db_file_save_fd(self, sites, out_file_fd):
        csvwriter = csv.writer(out_file_fd, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)

        # Write header
        csvwriter.writerow(self.db_file_cols)
        for site in sites:
            row = []
            for c_in in self.db_file_cols:
                c = c_in.lower().lstrip("#").strip()
                key = c.replace(" ", "_")
                row += [site.get(key, "")]
            csvwriter.writerow(row)

    def db_add_site(self, site: DeploySite):
        if self.find_site_by_id(site.site_id):
            raise ValueError(f'Site "{site.site_id}" already exists in the database')
        self.sites += [site]
        try:
            if self.gd_file and self.gds:
                self.loggr.info(f'Writing site database to Google Drive "{self.gd_file["title"]}" file.')

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
        except Exception as e:
            self.loggr.error(f'Error {type(e)} "{e}" saving site database file')
            return -1
        return 0

    def find_site_by_id(self, site_id) -> DeploySite | None:
        for site in self.sites:
            if site_id == site["site_id"]:
                return site
        return None

    def unique_site_id(self):
        site_id_template = self.conf.get("site_id_template", "RPI-{sn:03d}")
        site_name_template = self.conf.get("site_name_template", "RPI {sn:03d}")
        # site_group_template = self.conf.get('site_group_template', "RPI {sn:03d}")
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
            self.conf_file = find_path(g_conf_file_name, self.config_paths, self.loggr)
        if not self.conf_file:
            raise ValueError("Please provide config file")
        self.loggr.info(f"Config file {self.conf_file}")
        return get_conf(self.conf_file)

    def add(self, name: str, site: DeploySite) -> int:
        pass

    def get(self, name: str) -> tuple[int, DeploySite]:
        return 0, None

    def delete(self, name: str) -> int:
        return 0

    def update(self, name: str, site: DeploySite) -> int:
        return 0


def cmd_sites(db, args):
    show_secret = getattr(args, "show_secret", False)
    for site in db.sites:
        vals = []
        for c in db.cols + db.cols_optional:
            key = c.replace(" ", "_")
            if show_secret or key not in db.cols_secret:
                vals += [site[key]]
        print(", ".join(vals))
    return 0


def cmd_add(db, args):
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


def parse_args():
    parser = argparse.ArgumentParser(description="Manage Deployment Sites (list,add)")

    # Common optional arguments
    # parser.add_argument('-v', '--verbose', help='Verbose output', action='store_true')
    parser.add_argument("-D", "--debug", help="Debug", action="store_true")

    # Positional argument for the command
    subparsers = parser.add_subparsers(title="Commands", dest="command")

    # Parsers for commands
    sites_parser = subparsers.add_parser("sites", help="Get list of Deployment Sites")
    add_parser = subparsers.add_parser("add", help="Add a Deployment Site")
    get_parser = subparsers.add_parser("get", help="Get Deployment Site")

    # Optional arguments for the "sites" command
    # sites_parser.add_argument('-s', '--show_secret', help='Show secret key', action='store_true')

    # Additional args for "add" command
    add_parser.add_argument("site_id", type=str, help="Site id")
    add_parser.add_argument("site_name", type=str, help="Site name")
    add_parser.add_argument("sa_client_secrets", type=str, help="Site GoogleDrive ServiceAccount secrets file")
    add_parser.add_argument("-D", "--description", dest="description", help="Site description")

    # Parse the command line arguments
    args = parser.parse_args()
    return args, parser


def main(loggr=logger):
    args, parser = parse_args()
    if loggr:
        if args.debug:
            loggr.setLevel(logging.DEBUG)
        loggr.debug(f"DEBUG {vars(args)}")

    db = DeploySiteDB(loggr=loggr, debug=args.debug)

    try:
        if args.command == "sites":
            return cmd_sites(db, args)
        # if args.command == 'unique':
        #     return cmd_unique(db, args)
        if args.command == "add":
            return cmd_add(db, args)

    except Exception as e:
        if loggr:
            loggr.error(f'Error {type(e)} "{e}"')
        return -1

    parser.print_help()
    return 1


if __name__ == "__main__":
    rc = main()
    if rc:
        sys.exit(rc)
