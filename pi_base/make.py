#!/usr/bin/env python3

"""Make appliance image, class Builders and CLI.

Raises:
    ValueError: If site value not found

Returns:
    int: Error code
"""

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation

import argparse
import copy
import datetime
import errno

# import inspect
import json
import logging
import os
import platform
import shutil

# import sys
from subprocess import run, PIPE, check_output, CalledProcessError

# import sys
from timeit import default_timer as timer
import yaml

# "modpath" must be first of our modules
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# ? sys.path.append(os.path.dirname(os.path.realpath(SCRIPT_DIR)))
# pylint: disable-next=redefined-builtin
__package__ = os.path.basename(SCRIPT_DIR)  # noqa: A001
# pylint: disable=wrong-import-position,relative-beyond-top-level
# ruff: noqa: E402

from pi_base.modpath import get_app_workspace_dir, get_script_dir, site_id as develop_site_id, project as develop_project_id
from .lib.deploy_site import DeploySiteDB
from .lib.app_utils import find_path
from .lib.os_utils import walklevel


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != "__main__" else None)
# logger.setLevel(logging.DEBUG)

# No root first slash (will be added as necessary):
app_conf_dir = "home/pi"
etc_dir = "etc"

CONF_YAML = "conf.yaml"


def get_git_hash() -> str:
    try:
        result = run(["git", "rev-parse", "--short", "HEAD"], stdout=PIPE, check=False)  # noqa: S607
        githash = "-" + result.stdout.decode().strip()
    except CalledProcessError:
        githash = ""
    return githash


class Builder:
    def __init__(self, args, system, sites_db: DeploySiteDB, loggr=logger) -> None:
        self.loggr = loggr
        if not self.loggr:
            raise ValueError("Please provide loggr argument")

        self.app_info = None
        self.system = system
        self.sites_db = sites_db
        self.now = datetime.datetime.now()
        self.conf_dat = {}
        self.error = 0
        self.comment = ""
        self.type = args.type
        self.site_id = args.site
        self.app_workspace_path = args.workspace if isinstance(args.workspace, str) else get_app_workspace_dir()  # Find client project base directory
        self.package_dir = get_script_dir(__file__)  # Find package directory
        self.stage_dir = os.path.join(self.app_workspace_path, "build", self.site_id, self.type)

        self.loggr.debug(f"app_workspace_path : {self.app_workspace_path}")
        self.loggr.debug(f"package_dir        : {self.package_dir}")
        self.loggr.debug(f"stage_dir          : {self.stage_dir}")
        self.loggr.debug(f"app_conf_dir       : {app_conf_dir}")

    def rmdir(self, path) -> None:
        path = os.path.normpath(path)
        self.loggr.debug(f"removing dir {path}...")
        try:
            shutil.rmtree(path)  # ignore_errors=False, onerror=None
        except OSError as exc:  # Python = 2.5
            if exc.errno == errno.ENOENT and not os.path.isdir(path):
                pass
            # possibly handle other errno cases here, otherwise finally:
            else:
                raise

    def mkdir(self, path):
        path = os.path.normpath(path)
        self.loggr.debug(f"creating dir {path}...")
        try:
            # p = check_output(f'mkdir {path}', shell=True, text=True)
            os.makedirs(path)
        except OSError as exc:  # Python = 2.5
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            # possibly handle other errno cases here, otherwise finally:
            else:
                raise

    def write_conf(self, filepath, conf, head="", tail=""):
        filepath = os.path.normpath(filepath)
        self.mkdir(os.path.dirname(filepath))
        self.loggr.debug(f"writing file {filepath}...")
        with open(filepath, "w", encoding="utf-8") as outfile:
            y = yaml.dump(conf, default_flow_style=False)
            outfile.write(head)
            outfile.write(y)
            outfile.write(tail)

    def config(self):
        custom = False

        # Load default config, if present
        default_conf_dat = {}
        default_filename = "default_conf.yaml"
        yaml_file, _paths = find_path(
            default_filename,
            [
                self.package_dir,
                self.app_workspace_path,
            ],
            self.loggr,
        )
        if yaml_file:
            try:
                self.loggr.debug(f"opening default config {yaml_file}")
                with open(yaml_file, encoding="utf-8") as file:
                    default_conf_dat = yaml.safe_load(file)
            except Exception as e:
                self.loggr.error(f"Error opening default config {yaml_file}")

        custom_conf_dat = {}
        filename = CONF_YAML
        yaml_file = os.path.join(self.app_workspace_path, self.type, filename)
        try:
            self.loggr.debug(f"opening {yaml_file}")
            with open(yaml_file, encoding="utf-8") as file:
                custom_conf_dat = yaml.safe_load(file)
                custom = True
        except Exception as e:
            self.loggr.error(f"Error opening custom config {yaml_file}")

        # Merge defaults and custom
        self.conf_dat = {**default_conf_dat, **custom_conf_dat}  # python >= 3.5

        self.loggr.debug(json.dumps(self.conf_dat, indent=4))
        self.app_info = self.conf_dat["Info"]
        self.app_info["Site"] = self.site_id
        self.app_info["Type"] = self.type
        datestamp = datetime.datetime.now().strftime("%Y-%m%d-%H%M")
        githash = get_git_hash()
        self.app_info["Version"] = self.app_info.get("Version", datestamp)  # Generate app version from date if not specified.
        self.app_info["Build"] = datestamp + githash
        site = self.sites_db.find_site_by_id(self.site_id)
        if not site or not site.site_id or site.site_id != site.site_id:
            raise ValueError(f"Site {self.site_id} not found or sites DB not loaded")
        if not site.sa_client_secrets:
            raise ValueError(f"Client secrets file not set for site {self.site_id}")

        # If self.app_info->GoogleDrive->secrets is 'auto':
        if "GoogleDrive" in self.app_info and "secrets" in self.app_info["GoogleDrive"] and self.app_info["GoogleDrive"]["secrets"] == "auto":
            self.app_info["GoogleDrive"]["secrets"] = site.sa_client_secrets
            self.conf_dat["Files"].append({"src": os.path.join(self.app_workspace_path, "secrets", site.sa_client_secrets), "dst": "app/"})
            self.loggr.info(f"  + Added {site.sa_client_secrets} file to the build and to app_conf.yaml")

        if "PostInstall" in self.conf_dat:
            self.app_info["PostInstall"] = self.conf_dat["PostInstall"]
        return custom

    def make_modules(self, target_app: str) -> None:
        """Copies modules from common/ to staging directory target_app/modules.

        If the list is given in config file 'Modules' section, only the listed files are copied.

        Args:
            target_app: path to the staging directory
        """
        self.loggr.info("  + Creating lib folder for modules perf conf.'Modules':")
        target_dir = os.path.normpath(os.path.join(target_app, "lib"))
        # Make target_app/modules folder (make sure it is empty first)
        self.loggr.debug(f"Preparing {target_dir}")
        self.rmdir(target_dir)
        self.mkdir(target_dir)
        if "Modules" in self.conf_dat:
            # Copy only items listed in the "Modules" section of conf.yaml file
            modules = self.conf_dat.get("Modules", None) or []
            for item in modules:
                src = os.path.normpath(os.path.join(self.app_workspace_path, "lib", item))
                dst = os.path.normpath(target_dir + os.sep)  # Add '/' for shutil.copy2() to  not make it a name of the target file, but a directory for the target file
                self.loggr.debug(f"Copying {src} to {dst}")
                shutil.copy2(src, dst)
                self.loggr.info(f"    + Copied {item}")
        else:
            # No "Modules" - by default copy all files from {app_workspace_path}/lib, if it exists (don't copy subdirectories)
            src = os.path.normpath(os.path.join(self.app_workspace_path, "lib"))
            dst = os.path.normpath(target_dir)
            if os.path.isdir(src):
                self.loggr.info(f"    + Copying all files from {src} (add an empty conf.'Modules' section to disable)")

                # The optional ignore argument is a callable. If given, it
                # is called with the `src` parameter, which is the directory
                # being visited by copytree(), and `names` which is the list of
                # `src` contents, as returned by os.listdir():
                def ignore(current_dir: str, names: "list[str]") -> "list[str]":
                    ignored_names = []
                    if current_dir != src:
                        # Do not copy any sub-dirs, and do not traverse deeper
                        self.loggr.info(f"    - Skipped sudirectory {current_dir}")
                        return names
                    # Populate the ignored_names list as needed to skip copyiong these items
                    # ignored_names += []
                    for name in names:
                        item = os.path.join(current_dir, name)
                        if os.path.isfile(item):
                            self.loggr.info(f"    + Copied {item}")

                    return ignored_names

                # symlinks=False, copy_function=copy2, ignore_dangling_symlinks=False
                shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)
                self.loggr.info(f"    = Copied all files from {src}")

    def make_files_per_conf(self, target_app: str) -> None:
        """Make individual files (copy all files to their destinations in target_app).

        Args:
            target_app: path to the staging directory
        """
        if "Files" in self.conf_dat:
            self.loggr.info("  + Copying additional files per conf.'Files':")
            self.loggr.debug(f"Preparing {target_app}")
            items = self.conf_dat["Files"]
            for item in items:
                src_is_dir = item["src"][-1:] == "/"
                src = os.path.normpath(os.path.join(self.app_workspace_path, item["src"]))
                dst_is_dir = item["dst"][-1:] == "/"
                dst = os.path.normpath(os.path.join(target_app, item["dst"])) + (os.sep if dst_is_dir else "")
                self.mkdir(dst if dst_is_dir else os.path.dirname(dst))
                self.loggr.debug(f'Copying "{src}" to  "{dst}"')
                if src_is_dir:
                    # symlinks=False, ignore=None, copy_function=copy2, ignore_dangling_symlinks=False
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src=src, dst=dst)
                # TODO: (when needed) improve report for dst=''
                self.loggr.info(f'    + Copied {item["src"]} to {item["dst"]}')

    def make_ssh_cert(self, file, passphrase=""):
        cmd = ""
        if not file:
            file = "~/.ssh/ssh_cert"
        try:
            cmd = f'ssh-keygen -t ed25519 -b 4096 -f "{file}" -N "{passphrase}"'
            p = check_output(cmd, shell=True, text=True)
            # Restrict the permissions on the private key file

            if os.name == "nt":
                cmd = 'icacls "privateKeyPath" /grant :R'
            else:
                cmd = "chmod 400 ~/.ssh/id_ed25519"
                # ~/.ssh/id_ed25519.pub
                # Windows C:\Users\your-user\.ssh\id_ed25519.pub
                # /home/<user>/.ssh/id_ed25519.pub
            p = check_output(cmd, shell=True, text=True)
            return True
        except CalledProcessError as e:
            self.loggr.error(f'Error {e} while executing command "{cmd}"')
            return False

    def make_files_from_template(self, target_dir) -> None:
        """Make files staged in the templates.

        Args:
            target_app: path to the staging directory
        """
        if True:  # pylint: disable=using-constant-test
            self.loggr.info("  + Copying template files:")
            self.loggr.debug(f"Preparing {target_dir}")
            # Fixed items: (shall we require them in each _conf.yaml instead?)
            # Note: Trailing slash in "src" and "dst" is important:
            #  - slash denotes directory,
            #  - no slash in "src" means its a file,
            #  - no slash in "dst" for directory in "src" means the name of the target directory.
            items = [
                # Common files / dirs:
                {"src": os.path.join(self.package_dir, "common", "pkg/"), "dst": "./pkg"},
                {"src": os.path.join(self.package_dir, "common", "common_requirements.txt"), "dst": "./"},
                {"src": os.path.join(self.package_dir, "common", "common_install.sh"), "dst": "./"},
                # App files:
                {"src": os.path.join(self.app_workspace_path, self.type, "requirements.txt"), "dst": "./"},
                {"src": os.path.join(self.app_workspace_path, self.type, "install.sh"), "dst": "./"},
            ]
            app_pkg = os.path.join(self.app_workspace_path, self.type, "pkg/")
            if os.path.isdir(app_pkg):
                items.append({"src": app_pkg, "dst": "./pkg"})
            for item in items:
                src_is_dir = item["src"][-1:] == "/"
                src = os.path.normpath(item["src"])
                dst_is_dir = item["dst"][-1:] == "/"
                dst = os.path.normpath(os.path.join(target_dir, item["dst"])) + (os.sep if dst_is_dir else "")
                self.mkdir(dst if dst_is_dir else os.path.dirname(dst))
                self.loggr.debug(f'Copying "{src}" to  "{dst}"')
                if src_is_dir:
                    # symlinks=False, ignore=None, copy_function=copy2, ignore_dangling_symlinks=False
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src=src, dst=dst)
                # TODO: (when needed) improve report for dst=''
                self.loggr.info(f'    + Copied {item["src"]} to {item["dst"]}')

    def make(self):
        self.loggr.info(f"Making build of {self.site_id}/{self.type}:")
        custom = self.config()
        self.rmdir(self.stage_dir)
        self.mkdir(self.stage_dir)
        if "Conf" in self.conf_dat:
            # conf_info
            self.write_conf(filepath=f"{self.stage_dir}/pkg/{etc_dir}/manager_conf.yaml", conf=self.conf_dat["Conf"])
            self.loggr.info("  + Created manager_conf.yaml")
        # app_info
        self.write_conf(filepath=f"{self.stage_dir}/pkg/{app_conf_dir}/app_conf.yaml", conf=self.app_info, head=f"# Auto-generated by make.py on: {str(self.now)[:19]}\n\n")
        self.loggr.info("  + Created app_conf.yaml")
        target_app = f"{self.stage_dir}/pkg/{app_conf_dir}"
        self.make_modules(target_app)
        self.make_files_per_conf(target_app)
        self.make_files_from_template(self.stage_dir)
        self.loggr.info(f"Done Making build of {self.type}, image files copied to {self.stage_dir}.\n")


def reorder_list_item(list_of_str: "list[str]", find_item: str) -> "list[str]":
    if find_item not in list_of_str:
        return list_of_str

    index = list_of_str.index(find_item)
    return [list_of_str[index]] + list_of_str[:index] + list_of_str[index + 1 :]


def main(loggr=logger) -> int:
    start_time = timer()
    system = platform.system()
    rel = platform.release()
    if loggr:
        loggr.info(f"Running on {system}, release {rel}")
    parser = argparse.ArgumentParser()

    # Find all directories in app_workspace_path that contain CONF_YAML file:
    projects = []
    for dirpath, _, filenames in walklevel(get_app_workspace_dir()):
        project = os.path.basename(dirpath)
        if CONF_YAML in filenames and project not in projects:
            projects += [project]
    projects.sort()

    # Move develop_project_id into first position (so it will be the default)
    types_list = reorder_list_item(projects, develop_project_id) if develop_project_id else projects

    type_help_text = "Must be one of: all, " + ", ".join(types_list)

    db = DeploySiteDB(loggr=loggr)
    sites_list = [site.site_id for site in db.sites if site.site_id]
    sites_list.sort()
    # first element is the default choice
    sites_list = reorder_list_item(sites_list, develop_site_id) if develop_site_id else sites_list
    site_help_text = "Must be one of: " + ", ".join(sites_list)

    parser.add_argument("-D", "--debug", help="Enable debugging log", action="store_true")
    parser.add_argument("-t", "--type", default=types_list[0], help=type_help_text, choices=types_list + ["all"])
    parser.add_argument("-s", "--site", default=sites_list[0], help=site_help_text, choices=sites_list)
    parser.add_argument("-w", "--workspace", help="Workspace directory, defaults to current working directory")

    args = parser.parse_args()

    if args.debug and loggr:
        loggr.setLevel(logging.DEBUG)

    if args.type == "all":
        for item in types_list:
            args1 = copy.copy(args)
            args1.type = item
            build = Builder(args1, system, db)
            if build.error:
                return build.error
            build.make()
    else:
        build = Builder(args, system, db)
        if build.error:
            return build.error
        build.make()
    end_time = timer()
    if loggr:
        loggr.info(f"Elapsed time {end_time - start_time:0.2f}s")
    return 0


if __name__ == "__main__":
    main()
