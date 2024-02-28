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
from subprocess import check_output, CalledProcessError
# import sys
from timeit import default_timer as timer
import yaml

# "modpath" must be first of our modules
try:
    from .modpath import get_script_dir, base_path  # pylint: disable=wrong-import-position
except:
    from modpath import get_script_dir, base_path  # pylint: disable=wrong-import-position

try:
    from .lib.deploy_site import DeploySiteDB  # pylint: disable=wrong-import-position
except:
    from deploy_site import DeploySiteDB  # pylint: disable=wrong-import-position


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != '__main__' else None)
# logger.setLevel(logging.DEBUG)

# No root first slash (will be added as necessary):
app_dir = "home/pi"
etc_dir = "etc"

script_dir = get_script_dir()
caller_dir = os.getcwd()
logger.debug(f'script_dir={script_dir}, caller_dir={caller_dir}')


class Builder:
    def __init__(self, args, system, sites_db: DeploySiteDB):
        self.app_info = None
        self.system = system
        self.sites_db = sites_db
        self.now = datetime.datetime.now()
        self.conf_dat = {}
        self.error = 0
        self.ver = "0.0.0"
        self.comment = ""
        self.type = args.type
        self.site_id = args.site
        self.base_dir = os.path.dirname(script_dir)  # TODO: (now) Redesign it to be: This is base dir of the project (not connected to the pi_base package location)
        self.package_dir = self.base_dir  # TODO: (now) Find pacage dir for pi_base/lib and pi_base/common assets
        self.stage_dir = os.path.join(self.base_dir, 'build', self.site_id, self.type)
        logger.debug(f'base_dir    : {self.base_dir}')
        logger.debug(f'package_dir : {self.package_dir}')
        logger.debug(f'stage_dir   : {self.stage_dir}')
        logger.debug(f'app_dir     : {app_dir}')

    def rmdir(self, path):
        path = os.path.normpath(path)
        logger.debug(f'removing dir {path}...')
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
        logger.debug(f'creating dir {path}...')
        try:
            # p = check_output(f'mkdir {path}', shell=True, text=True)
            os.makedirs(path)
        except OSError as exc:  # Python = 2.5
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            # possibly handle other errno cases here, otherwise finally:
            else:
                raise

    def write_conf(self, filepath, conf, head='', tail=''):
        filepath = os.path.normpath(filepath)
        self.mkdir(os.path.dirname(filepath))
        logger.debug(f'writing file {filepath}...')
        with open(filepath, "w", encoding='utf-8') as outfile:
            y = yaml.dump(conf, default_flow_style=False)
            outfile.write(head)
            outfile.write(y)
            outfile.write(tail)

    def config(self):
        custom = False
        try:
            yaml_file = os.path.join(base_path, self.type, 'conf.yaml')
            logger.debug(f'opening {yaml_file}')
            file = open(yaml_file, encoding='utf-8')
            custom = True
        except:
            yaml_file = os.path.join(script_dir, 'default_conf.yaml')
            logger.debug(f'opening {yaml_file}')
            file = open(yaml_file, encoding='utf-8')
            # TODO: (when needed) Perhaps opening default_conf.yaml is not at all what we need here. Should default be pre-loaded?
        self.conf_dat = yaml.safe_load(file)
        file.close()
        logger.debug(json.dumps(self.conf_dat, indent=4, default="DEFAULT"))
        self.app_info = self.conf_dat['Info']
        self.app_info['Site'] = self.site_id
        self.app_info['Type'] = self.type
        self.app_info['Version'] = self.ver
        site = self.sites_db.find_site_by_id(self.site_id)
        if not site:
            raise ValueError(f'Site {self.site_id} not found or sites DB not loaded')

        # If self.app_info->GoogleDrive->secrets is 'auto':
        if 'GoogleDrive' in self.app_info and 'secrets' in self.app_info['GoogleDrive'] and self.app_info['GoogleDrive']['secrets'] == 'auto':
            self.app_info['GoogleDrive']['secrets'] = site.sa_client_secrets
            self.conf_dat['Files'].append({'src': os.path.join('secrets', site.sa_client_secrets), 'dst': 'app/'})
            logger.info(f'  + Added {site.sa_client_secrets} file to the build and to app_conf.yaml')

        if 'PostInstall' in self.conf_dat:
            self.app_info['PostInstall'] = self.conf_dat['PostInstall']
        return custom

    def make_modules(self, target_app):
        """ Copies modules from common/ to staging directory target_app/modules.

        If the list is given in config file 'Modules' section, only the listed files are copied.
        """
        logger.info("  + Creating modules folder:")
        # Make target_app/modules folder (make sure it is empty first)
        target_dir = os.path.normpath(os.path.join(target_app, 'modules'))
        logger.debug(f'Preparing {target_dir}')
        self.rmdir(target_dir)
        self.mkdir(target_dir)
        if 'Modules' in self.conf_dat:
            for item in self.conf_dat['Modules']:
                src = os.path.normpath(os.path.join(self.package_dir, 'pi_base', 'lib', item))
                dst = os.path.normpath(target_dir + os.sep)
                logger.debug(f'Copying {src} to {dst}')
                shutil.copy2(src, dst)
                logger.info(f'    + Copied {item}')
        else:
            # TODO: (now) Redesign using of base_dir/common to be conditional on it's presence, not on the absence of 'Modules' section in config.
            src = os.path.normpath(os.path.join(self.base_dir, 'common'))
            dst = target_dir
            logger.debug(f'Copying {src} to {dst}')
            # symlinks=False, ignore=None, copy_function=copy2, ignore_dangling_symlinks=False
            shutil.copytree(src, dst, dirs_exist_ok=True)
            logger.info("    + Copied all files from common/")

    def make_files_per_conf(self, target_app):
        # Make individual files (copy all files to their destinations in target_app)
        if 'Files' in self.conf_dat:
            logger.info("  + Copying additional files per conf.'Files':")
            logger.debug(f'Preparing {target_app}')
            items = self.conf_dat["Files"]
            for item in items:
                src_is_dir = item['src'][-1:] == '/'
                src = os.path.normpath(os.path.join(self.base_dir, item['src']))
                dst_is_dir = item['dst'][-1:] == '/'
                dst = os.path.normpath(os.path.join(target_app, item['dst'])) + (os.sep if dst_is_dir else '')
                self.mkdir(dst if dst_is_dir else os.path.dirname(dst))
                logger.debug(f'Copying "{src}" to  "{dst}"')
                if src_is_dir:
                    # symlinks=False, ignore=None, copy_function=copy2, ignore_dangling_symlinks=False
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src=src, dst=dst)
                # TODO: (when needed) improve report for dst=''
                logger.info(f'    + Copied {item["src"]} to {item["dst"]}')

    def make_ssh_cert(self, file, passphrase=""):
        cmd = ''
        if not file:
            file = '~/.ssh/ssh_cert'
        try:
            cmd = f'ssh-keygen -t ed25519 -b 4096 -f "{file}" -N "{passphrase}"'
            p = check_output(cmd, shell=True, text=True)
            # Restrict the permissions on the private key file

            if os.name == 'nt':
                cmd = 'icacls "privateKeyPath" /grant :R'
            else:
                cmd = 'chmod 400 ~/.ssh/id_ed25519'
                # ~/.ssh/id_ed25519.pub
                # Windows C:\Users\your-user\.ssh\id_ed25519.pub
                # /home/<user>/.ssh/id_ed25519.pub
            p = check_output(cmd, shell=True, text=True)
            return True
        except CalledProcessError as e:
            logger.error(f'Error {e} while executing command "{cmd}"')
            return False

    def make_files_from_template(self, target_dir):
        # Make files staged in the templates
        if True:  # pylint: disable=using-constant-test
            logger.info('  + Copying template files:')
            logger.debug(f'Preparing {target_dir}')
            # Fixed items: (shall we require them in each _conf.yaml instead?)
            items = [
                # Common files / dirs:
                # TODO: (now) Use self.package_dir instead of self.base_dir:
                {'src': 'pi_base/common/pkg/',                     'dst': './pkg'},
                {'src': 'pi_base/common/common_requirements.txt',  'dst': './'},
                {'src': 'pi_base/common/common_install.sh',        'dst': './'},

                # App files:
                {'src': f'{self.type}/pkg/',             'dst': './pkg'},
                {'src': f'{self.type}/requirements.txt', 'dst': './'},
                {'src': f'{self.type}/install.sh',       'dst': './'},
            ]
            for item in items:
                src_is_dir = item['src'][-1:] == '/'
                src = os.path.normpath(os.path.join(self.base_dir, item['src']))
                dst_is_dir = item['dst'][-1:] == '/'
                dst = os.path.normpath(os.path.join(target_dir, item['dst'])) + (os.sep if dst_is_dir else '')
                self.mkdir(dst if dst_is_dir else os.path.dirname(dst))
                logger.debug(f'Copying "{src}" to  "{dst}"')
                if src_is_dir:
                    # symlinks=False, ignore=None, copy_function=copy2, ignore_dangling_symlinks=False
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src=src, dst=dst)
                # TODO: (when needed) improve report for dst=''
                logger.info(f'    + Copied {item["src"]} to {item["dst"]}')

    def make(self):
        logger.info(f'Making build of {self.site_id}/{self.type}:')
        custom = self.config()
        self.rmdir(self.stage_dir)
        self.mkdir(self.stage_dir)
        if 'Conf' in self.conf_dat:
            # conf_info
            self.write_conf(
                filepath=f'{self.stage_dir}/pkg/{etc_dir}/manager_conf.yaml',
                conf=self.conf_dat['Conf']
            )
            logger.info("  + Created manager_conf.yaml")
        # app_info
        self.write_conf(
            filepath=f'{self.stage_dir}/pkg/{app_dir}/app_conf.yaml',
            conf=self.app_info,
            head=f'# Auto-generated by make.py on: {str(self.now)[:19]}\n\n'
        )
        logger.info("  + Created app_conf.yaml")
        target_app = f'{self.stage_dir}/pkg/{app_dir}'
        self.make_modules(target_app)
        self.make_files_per_conf(target_app)
        self.make_files_from_template(self.stage_dir)
        logger.info(f'Done Making build of {self.type}.\n')


def find_package_dir():
    # TODO: (now) Here's an idea, implement robust design:
    import pkgutil

    data = pkgutil.get_data(__name__, "templates/temp_file")


def find_package_dir2():
    # TODO: (now) Here's an idea, implement robust design: Deprecated in python 3.11 in 2021:
    try:
        from importlib import resources as impresources
    except ImportError:
        # Try backported to PY<37 `importlib_resources`.
        import importlib_resources as impresources

    from . import common  # relative-import the *package* containing the templates

    try:
        inp_file = impresources.files(common) / 'temp_file'
        with inp_file.open("rb") as f:  # or "rt" as text file with universal newlines
            template = f.read()
    except AttributeError:
        # Python < PY3.9, fall back to method deprecated in PY3.11.
        template = impresources.read_text(common, 'temp_file')
        # or for a file-like stream:
        template = impresources.open_text(common, 'temp_file')

def main() -> int:
    start_time = timer()
    system = platform.system()
    rel = platform.release()
    logger.info(f'Running on {system}, release {rel}')
    parser = argparse.ArgumentParser()

    db = DeploySiteDB()

    # first element is the default choice
    types_list = ['blank']  # TODO: (now) implement automatic list of projects generation, #TODO: (soon) Implement blank project special handling
    type_help_text = "Must be one of: all, " + ', '.join(types_list)

    # first element is the default choice
    sites_list = [site.site_id for site in db.sites]
    site_help_text = "Must be one of: " + ', '.join(sites_list)

    parser.add_argument('-D', '--debug', help='Enable debugging log', action='store_true')
    parser.add_argument('-t', '--type', default=types_list[0], help=type_help_text, choices=types_list+["all"])
    parser.add_argument('-s', '--site', default=sites_list[0], help=site_help_text, choices=sites_list)

    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

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
    print(f'Elapsed time {end_time - start_time:0.2f}s')
    return 0


if __name__ == "__main__":
    main()
