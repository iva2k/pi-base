#!/usr/bin/env python3

# WIP: Creating: Service to manage a db in a file

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation
from __future__ import annotations

import argparse
import copy
import csv

# import importlib
import io
import logging
import os
import sys
from typing import Any, Generic, Optional, TypeVar
from collections.abc import Iterable, Mapping

from pydantic import BaseModel, create_model, ConfigDict

# "modpath" must be first of our modules
# from pi_base.modpath import get_app_workspace_dir, get_script_dir  # pylint: disable=wrong-import-position
# pylint: disable=wrong-import-order


## Experimental: hacks to use relative import not in module (e.g. CLI)
# Experiments revealed that it is sufficient to set __package__ variable to enable relative imports.
# If any future version of Python breaks that behavior, that assumption will need to be revisited.
# __init__.py files in the relative import tree are not needed for it to work.
# import importlib
# module = importlib.import_module("path", os.path.basename(SCRIPT_DIR))

# These contortions are needed to import from relative modules when running main() from CLI:
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# ? sys.path.append(os.path.dirname(os.path.realpath(SCRIPT_DIR)))
# __package__ = os.path.basename(SCRIPT_DIR)
# pylint: disable-next=redefined-builtin
__package__ = ".".join([os.path.basename(os.path.dirname(SCRIPT_DIR)), os.path.basename(SCRIPT_DIR)])  # noqa: A001
# pylint: disable=wrong-import-position,relative-beyond-top-level
# ruff: noqa: E402, TID252

from ..lib.app_utils import AtDict, GetConf, find_path, translate_config_paths
from ..lib.gd_service import gd_connect, GoogleDriveFile, FileNotUploadedError  # pyright: ignore[reportAttributeAccessIssue]


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != "__main__" else None)
# logger.setLevel(logging.DEBUG)


def eprint(*args: object, **kwargs: Mapping[str, Any]) -> None:
    kwargs1 = {"file": sys.stderr, **kwargs}
    print(*args, **kwargs1)


_ST = TypeVar("_ST")


class DbFileSchema:
    @classmethod
    def type_mapping(cls) -> dict[str, type]:
        return {
            "int": int,
            "bool": bool,
            "str": str,
            "float": float,
            # Add more types here as needed
        }

    def __init__(self, schema_conf: dict, id_template_values_add: Optional[Mapping[str, str | Mapping[str, Any]]] = None) -> None:
        self.version = self.ensure_type("version", int, schema_conf.get("version", 0))
        self.upgrade_from = self.ensure_type("upgrade_from", int, schema_conf.get("upgrade_from", max(0, self.version - 1)))
        self.upgrade_ok = self.ensure_type("upgrade_ok", bool, schema_conf.get("upgrade_ok", self.upgrade_from < self.version))

        self.items_name = self.ensure_type("items_name", str, schema_conf.get("items_name", "items"))
        self.item_name = self.ensure_type("item_name", str, schema_conf.get("item_name", "item"))  # TODO: (when needed) Or maybe create and use .plural(1) .plural("many") class "Plural" instance?
        self.col_id = self.ensure_type("col_id", str, schema_conf.get("col_id", "id"))
        self.cols = self.ensure_type("cols", dict, schema_conf.get("cols", {"name": "str"}))
        self.cols_optional = self.ensure_type("cols_optional", dict, schema_conf.get("cols_optional", {"description": "str", "notes": "str"}))

        self.col_id = self.col_id.strip().replace(" ", "_")
        self.cols = {k.strip().replace(" ", "_"): v for k, v in self.cols.items()}
        self.cols_optional = {k.strip().replace(" ", "_"): v for k, v in self.cols_optional.items()}

        if self.col_id not in self.cols:
            raise ValueError(f'col_id "{self.col_id}" must be present in cols')
        self.cols_secret = self.ensure_type("cols_secret", list, schema_conf.get("cols_secret", []))
        self.id_template = self.ensure_type("id_template", dict, schema_conf.get("id_template", {}))
        if id_template_values_add:
            if "values" not in self.id_template:
                self.id_template["values"] = id_template_values_add
            else:
                self.ensure_type("id_template.values", dict, self.id_template["values"])
                self.id_template["values"].update(id_template_values_add)

    def ensure_type(self, field: str, t: type[_ST], val) -> _ST:
        if not isinstance(val, t):
            raise TypeError(f'Expected {t.__name__}, got {type(val).__name__} in "{field}"')
        return val


# Generic type for data model classes
_T = TypeVar("_T", bound=BaseModel)


class DbFile(Generic[_T]):
    MAX_SN = 1000

    def __init__(self, config: GetConf, schema: DbFileSchema, model_type: type[_T], loggr: Optional[logging.Logger] = logger, debug: bool = False) -> None:
        if not loggr:
            raise ValueError("Please provide loggr argument")
        if not config:
            raise ValueError("Please provide config argument")
        if not schema:
            raise ValueError("Please provide schema argument")

        self.conf = config
        self.schema = schema
        self._model_type = model_type
        self.debug = debug
        self.loggr = loggr
        self.items: list[_T] = []

        # Compiled columns from database file:
        self.db_file_cols: Optional[list[str]] = None

        # Backend files:
        self.db_file: Optional[str] = None
        self.gd_file: Optional[GoogleDriveFile] = None
        # Look for database file in GoogleDrive first
        gd_secrets_file = self.conf.get_sub("GoogleDrive", "secrets", default=None)
        local_db_filename = self.conf.get_sub("Local", "db_file", default=None)
        file_paths = self.conf.get("file_paths", default=[], t=list)
        if gd_secrets_file:
            if file_paths and not isinstance(file_paths, list):
                raise ValueError(f'Expected list "file_paths" in config, got a {type(file_paths)}')
            file_paths = file_paths or []
            self.items = self.connect_gd_and_load_file(gd_secrets_file, file_paths, fail_on_no_secrets_file=not local_db_filename)
        if not self.gd_file and local_db_filename:
            if file_paths and not isinstance(file_paths, list):
                raise ValueError(f'Expected list "file_paths" in config, got a {type(file_paths)}')
            file_paths = file_paths or []
            items = self.db_file_load(local_db_filename, file_paths, create_if_missing=True)
            self.items = items or []
        if not self.gd_file and not self.db_file:
            raise FileNotFoundError(f"Cannot load {self.schema.items_name} database")

    @property
    def model_type(self) -> type[_T]:
        """Returns the Pydantic model type used by the DbFile instance."""
        return self._model_type

    def connect_gd_and_load_file(self, gd_secrets_file: str, file_paths: list[str], fail_on_no_secrets_file: bool = True) -> list[_T]:
        gd_secrets, paths = find_path(gd_secrets_file, file_paths)
        items: list[_T] = []
        if not gd_secrets:
            paths_searched = (", paths searched [" + ", ".join([f'"{p}"' for p in paths]) + "]") if paths else ""
            if fail_on_no_secrets_file:
                raise FileNotFoundError(f'Cannot find GoogleDrive secrets file "{gd_secrets_file}"{paths_searched}.')
            self.loggr.warning(f'Cannot find GoogleDrive secrets file "{gd_secrets_file}"{paths_searched}.')
        else:
            gd_items_folder_id_name = f"gd_{self.schema.items_name}_folder_id"
            gd_items_file_title_name = f"gd_{self.schema.items_name}_file_title"
            self.gds, extras = gd_connect(self.loggr, gd_secrets, {gd_items_folder_id_name: None, gd_items_file_title_name: None}, skip_msg="Cannot continue.")
            if not self.gds:
                raise ValueError("Failed loading GoogleDrive secrets or connecting.")
            self.gd_folder_id = extras[gd_items_folder_id_name] if extras else None
            self.gd_file_title = extras[gd_items_file_title_name] if extras else None
            if not self.gd_file_title or not self.gd_folder_id:
                raise ValueError(f'Expected non-empty {gd_items_folder_id_name} and {gd_items_file_title_name} in GoogleDrive secrets file "{gd_secrets}".')
            items, self.gd_file = self.db_file_load_gd(self.gd_file_title, self.gd_folder_id, create_if_missing=True)
            items = items or []
        return items

    def db_file_load_gd(self, gd_file_title: str, gd_folder_id: str, create_if_missing: bool = True):
        if not self.gds:
            raise ValueError("Expected GoogleDrive to be open, got empty self.gds.")
        items = None
        # gd_file_id = 'TBD'
        # in_file_fd = self.gds.open_file_by_id(gd_file_id)
        self.loggr.info(f'Reading {self.schema.items_name} database from GoogleDrive "{gd_file_title}" file.')
        if create_if_missing:
            in_file_fd, created = self.gds.maybe_create_file_by_title(gd_file_title, gd_folder_id)
        else:
            in_file_fd, created = self.gds.get_file_by_title(gd_file_title, gd_folder_id), False

        if created:
            items = []
            self.db_file_cols_init()
        elif in_file_fd:
            content = in_file_fd.GetContentString()
            # FileNotUploadedError would be thrown if we ignored `created`.
            # Any other exception is due to real trouble.
            buffered = io.StringIO(content)
            items = self.db_file_load_fd(buffered)
        else:  # if not in_file_fd:
            raise FileNotUploadedError("Failed to create file on GoogleDrive.")

        return items, in_file_fd

    def db_file_load(self, db_filename: str, file_paths: list[str], create_if_missing: bool = True) -> list[_T]:
        file_paths = file_paths or []
        db_filename_found, paths = find_path(db_filename, file_paths, self.loggr)
        if not db_filename_found:
            paths_searched = (", paths searched [" + ", ".join([f'"{p}"' for p in paths]) + "]") if paths else ""
            # raise FileNotFoundError(f"No {self.schema.items_name} database file found{paths_searched}.")
            self.loggr.warning(f"No {self.schema.items_name} database file found{paths_searched}.")
            db_filename_found = None
            for path in paths:
                path_found, _ = find_path(path, [], loggr=self.loggr, is_dir=True)
                if path_found:
                    db_filename_found = os.path.join(path_found, db_filename)
                    break
            self.db_file = db_filename_found
            self.db_file_cols_init()
            return []

        with open(db_filename_found, newline="", encoding="utf-8") as in_file_fd:
            self.loggr.info(f'Reading {self.schema.items_name} database from "{db_filename_found}" file.')
            items = self.db_file_load_fd(in_file_fd)
            self.db_file = db_filename_found
            return items

    def db_file_load_fd(self, in_file_fd: Iterable[str]) -> list[_T]:
        csvreader = csv.reader(in_file_fd, delimiter=",", quotechar='"')
        input_row_num = 0
        got_header = False
        columns = []
        items = []
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

                    for c in self.schema.cols:
                        key = c.replace("_", " ")
                        if c not in columns:
                            raise ValueError(f'Cannot find column {c} in {self.schema.items_name} database file "{self.db_file or self.gd_file}"')

            else:
                # Got data row
                item_data = {}
                for col, c in enumerate(columns):
                    key = c.replace(" ", "_")
                    val = row_stripped[col] if col < len(row) else None
                    item_data[key] = val
                item = self.model_type(**item_data)
                if item:
                    items += [item]
        if not got_header and not items:
            # File is empty (perhaps was just created), init the columns
            self.db_file_cols_init()
        return items

    def db_file_cols_init(self):
        self.db_file_cols = [c.replace("_", " ").title() for c in list(self.schema.cols.keys()) + list(self.schema.cols_optional.keys())]
        self.db_file_cols[0] = "# " + self.db_file_cols[0]

    def _upgrade_needed(self, upgrade_ok=False) -> tuple[bool, list[str]]:
        cols = {**self.schema.cols, **self.schema.cols_optional}
        if not self.db_file_cols:
            return True, list(cols.keys())
        db_cols = [c.lower().lstrip("#").strip() for c in self.db_file_cols]
        cols_missing = [c for c in cols if c not in db_cols]
        if upgrade_ok and any(cols_missing):
            return True, cols_missing
        # Look if any of the cols_missing have data in items.
        # If no data, adding a column may be postponed
        for item in self.items:
            for c in cols_missing:
                if getattr(item, c, ""):
                    return True, cols_missing  # If we find data in any cols_missing, then upgrade is needed.
        return False, []

    def db_file_upgrade_maybe(self) -> None:
        """Upgrade the file Schema on write if allowed and needed.

        Add all columns in the Schema to self.db_file_cols if not already there.
        """
        version = self.schema.version
        upgrade_ok = self.schema.upgrade_ok
        # upgrade_from = self.schema.upgrade_from
        needed, cols_missing = self._upgrade_needed(upgrade_ok)
        if needed:
            if not upgrade_ok and self.db_file_cols:
                raise ValueError(
                    f"Cannot write {self.schema.items_name} database to {self.db_file or self.gd_file} - schema upgrade to v{version} is needed, but not allowed by Schema.upgrade _ok={upgrade_ok}"
                )
            self.db_file_cols_init()
        if not self.db_file_cols:
            raise ValueError("Expected non-empty list in self.db_file_cols.")
        if needed:
            cols = {**self.schema.cols, **self.schema.cols_optional}
            columns = [c.lower().lstrip("#").strip() for c in self.db_file_cols]
            type_mapping = DbFileSchema.type_mapping()
            for i, item in enumerate(self.items):
                item_data = {}
                for c in columns:
                    key = c.replace(" ", "_")
                    field_type = cols[key]
                    if field_type not in type_mapping:
                        raise ValueError(f'Unknown type "{field_type}" for column "{key}" in schema for {self.schema.items_name} database')
                    t = type_mapping[field_type]
                    val = getattr(item, key, None)
                    if val is None and key in cols_missing:
                        # Here we rely on type `t` to give us a sensible default for cols_missing data.
                        # A better approach is to define default values in the Schema - for migration (and same default can be used for new items when data is not provided).
                        # Another approach is to devise a mechanism to indicate missing data in CSV file, like "NULL" in SQL.
                        val = t()
                    item_data[key] = val
                self.items[i] = self.model_type(**item_data)
            self.loggr.info(f'Upgraded file "{self.db_file or self.gd_file}" to Schema v{version}.')

    def db_file_save(self, items, out_file: str) -> None:
        self.db_file_upgrade_maybe()
        with open(out_file, "w", newline="", encoding="utf-8") as out_file_fd:
            self.loggr.info(f'Writing {self.schema.items_name} database to "{out_file}" file.')
            self.db_file_save_fd(items, out_file_fd)

    def db_file_save_fd(self, items, out_file_fd):
        if not self.db_file_cols:
            raise ValueError("Expected non-empty list in self.db_file_cols.")
        csvwriter = csv.writer(out_file_fd, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)

        # Write header
        csvwriter.writerow(self.db_file_cols)
        for item in items:
            row = []
            for c_in in self.db_file_cols:
                c = c_in.lower().lstrip("#").strip()
                key = c.replace(" ", "_")
                val = getattr(item, key, "")
                if val is None:
                    val = ""
                row += [str(val)]
            csvwriter.writerow(row)

    def db_file_save_back(self) -> int:
        try:
            if self.gd_file and self.gds:
                self.db_file_upgrade_maybe()
                self.loggr.info(f'Writing {self.schema.items_name} database to GoogleDrive "{self.gd_file["title"]}" file.')

                # buffered = io.BytesIO()
                # buffered.seek(0)
                buffered = io.StringIO()

                self.db_file_save_fd(self.items, buffered)
                buffered.seek(0)
                # self.gd_file.content = buffered
                self.gd_file.SetContentString(buffered.getvalue())
                self.gd_file.Upload()
            elif self.db_file:
                self.db_file_save(self.items, self.db_file)
        except Exception as e:  # pylint: disable:broad-exception-caught
            self.loggr.error(f'Error {type(e)} "{e}" saving {self.schema.items_name} database file')
            return -1
        return 0

    def db_add_item(self, item: _T):
        item_id = getattr(item, self.schema.col_id)
        if self.find_item_by_id(item_id):
            raise ValueError(f'Site "{item_id}" already exists in the database')
        self.items += [item]
        return self.db_file_save_back()

    def db_delete_item(self, item_id: str) -> int:
        item = self.find_item_by_id(item_id)
        if not item:
            raise ValueError(f'Device "{item_id}" is not found in the database')
        self.items.remove(item)
        return self.db_file_save_back()

    def find_item_by_id(self, item_id) -> _T | None:
        for item in self.items:
            if item_id == getattr(item, self.schema.col_id):
                return item
        return None

    def unique_item_id(self) -> tuple:
        if self.schema.col_id not in self.schema.id_template:
            raise ValueError(f'Column "{self.schema.col_id}" not found in {self.schema.id_template}')
        _iter = self.schema.id_template.get("_iterator")
        # if not _iter:
        #     raise ValueError('Item "_iterator" not found in Schema.id_template')
        _iter = AtDict(**(_iter or {"key": "sn", "fr": 0, "to": 32767, "step": 1}))
        if not _iter.fr:
            _iter.fr = 0
        if not _iter.to:
            _iter.to = 32767
        if not _iter.step:
            _iter.step = 1

        if "values" in self.schema.id_template and isinstance(self.schema.id_template["values"], dict):
            values: dict[str, int | str] = copy.copy(self.schema.id_template["values"])
        else:
            values = {}
        values[_iter.key] = _iter.fr

        while int(values["sn"]) < _iter.to:
            templates: dict[str, str] = {}
            for k, v in self.schema.id_template.items():
                if k.startswith("__") or k in ["_iterator"]:
                    continue
                if isinstance(v, str):
                    templates[k] = v.format(**values)
            if not self.find_item_by_id(templates[self.schema.col_id]):
                return tuple(templates.values())
            values[_iter.key] = int(values[_iter.key]) + _iter.step
        return tuple(None for _ in range(len(templates)))


def create_dynamic_model(schema: DbFileSchema) -> type | None:
    name = " ".join([p.capitalize() for p in schema.item_name.split("_")])
    cols = {**schema.cols, **schema.cols_optional}
    type_mapping = DbFileSchema.type_mapping()

    fields = {}
    optional_fields = []
    for field_name, field_type in cols.items():
        if field_type not in type_mapping:
            raise ValueError(f'Unknown type "{field_type}" for column "{field_name}" in schema for "{name}"')
        key = field_name.replace(" ", "_")
        if field_name in schema.cols_optional:
            fields[key] = (type_mapping[field_type], None)
            optional_fields.append(key)
        else:
            fields[key] = (type_mapping[field_type], ...)

    # Tweak pydantic validation per https://stackoverflow.com/a/63794841/2694949
    def schema_extra(schema, _model):
        for column in optional_fields:
            original_type = schema["properties"][column]["type"]
            schema["properties"][column].update({"type": ["null", original_type]})

    # pydantic v1: config = ConfigDict(schema_extra=schema_extra)
    config = ConfigDict(json_schema_extra=schema_extra)
    return create_model(name, **fields, __config__=config)


def get_db(loggr: logging.Logger, args: argparse.Namespace) -> DbFile:
    """Prepare backend database by loading config file.

    Serves as a usage example for DbFile class.
    """
    config_paths = [
        # ">root/",
        # ">base/secrets/",
        # ">base/",
        ".",
        "./secrets/",
        ">app_conf_dir/app",
        ">app_conf_dir/",
        "~",
    ]
    config_paths = translate_config_paths(config_paths)
    filename, paths = find_path(args.config_file, config_paths, loggr=logger)
    conf = GetConf(filename)
    conf.conf["config_paths"] = config_paths
    conf.conf["file_paths"] = config_paths

    schema_conf = conf.get_sub("Schema", default={}, t=dict)
    if not schema_conf:
        raise ValueError(f'Could not find "Schema" section in "{filename}"')
    if not isinstance(schema_conf, dict):
        raise TypeError(f'Expected "Schema" section to be a dict, got {type(schema_conf)} in "{filename}"')

    # Example of additional fields data for id_template, which can be populated from e.g. app_conf.yaml or other data by DbFile client.
    site_id = "SITE"
    app_type = "APP_TYPE"
    app_name = "APP_NAME"
    id_template_values_add = {
        "site_id": site_id,
        "app_type": app_type,
        "app_name": app_name,
    }
    schema = DbFileSchema(schema_conf, id_template_values_add)

    t = create_dynamic_model(schema)
    if not t:
        raise ValueError(f'Could not create dynamic model for "{schema.items_name}" database')
    return DbFile[t](config=conf, schema=schema, model_type=t, loggr=loggr, debug=args.debug)


def cmd_list(db: DbFile, args: argparse.Namespace) -> int:
    show_secret = getattr(args, "show_secret", False)
    header = []
    for c in list(db.schema.cols.keys()) + list(db.schema.cols_optional.keys()):
        key = c.replace("_", " ").title()
        header.append(key)
    print(", ".join(header))
    for item in db.items:
        vals = []
        for c in list(db.schema.cols.keys()) + list(db.schema.cols_optional.keys()):
            key = c.replace(" ", "_")
            if show_secret or c not in db.schema.cols_secret:
                val = getattr(item, key, "")
                vals.append(str(val))
            else:
                vals.append("*" * 8)
        print(", ".join(vals))
    return 0


def cmd_unique(db: DbFile, args: argparse.Namespace) -> int:
    item_id, *rest = db.unique_item_id()
    print(item_id, *rest)
    return 0


def cmd_add(db: DbFile, args: argparse.Namespace) -> int:
    item_type = db.model_type
    new_item_data = dict(zip(list(db.schema.cols.keys()) + list(db.schema.cols_optional.keys()), args.fields))
    item = item_type(**new_item_data)
    try:
        res = db.db_add_item(item)
    except ValueError as err:
        eprint(f"{err}")
        res = 1
    if not res:
        field = list(db.schema.cols.keys())[1]
        details = getattr(item, field) if len(list(db.schema.cols.keys())) > 1 else ""
        print(f'Added new {db.schema.item_name} to {db.schema.items_name} Database item_id={getattr(item, db.schema.col_id)} {field}: "{details}"')
    return res


def _parse_args(progname: str) -> tuple[argparse.Namespace, argparse.ArgumentParser]:
    parser = argparse.ArgumentParser(description="Manage Database (list,add)")

    # Common optional arguments
    parser.add_argument("-v", "--verbose", help="Verbose output", action="store_true")
    parser.add_argument("-D", "--debug", help="Debug", action="store_true")
    parser.add_argument("-c", "--config", dest="config_file", type=str, help="Config file to use", default="remote_secrets.yaml")

    # Positional argument for the command
    subparsers = parser.add_subparsers(title="Commands", dest="command")

    # "list" command
    _list_parser = subparsers.add_parser("list", help="Get list of Database items")
    # _list_parser.add_argument('-s', '--show_secret', help='Show secret key', action='store_true')

    # "add" command
    add_parser = subparsers.add_parser("add", help="Add item to Database")
    add_parser.add_argument(dest="fields", nargs=argparse.REMAINDER, help="fields")

    # "get" command
    _get_parser = subparsers.add_parser("get", help="Get Database item")

    # "unique" command
    _unique_parser = subparsers.add_parser("unique", help="Get Unique ID")

    # Parse the command line arguments
    args = parser.parse_args()
    return args, parser


def main(loggr: logging.Logger = logger) -> int:
    progname = os.path.basename(sys.argv[0])
    args, parser = _parse_args(progname)
    if loggr:
        if args.debug:
            loggr.setLevel(logging.DEBUG)
        loggr.debug(f"DEBUG {vars(args)}")

    try:
        if args.command == "list":
            return cmd_list(get_db(loggr, args), args)
        if args.command == "unique":
            return cmd_unique(get_db(loggr, args), args)
        if args.command == "add":
            return cmd_add(get_db(loggr, args), args)

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
