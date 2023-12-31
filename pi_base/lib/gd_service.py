#!/usr/bin/env python3

# Based on
#  - https://cloud.google.com/iam/docs/service-accounts
#  - https://docs.iterative.ai/PyDrive2/quickstart/#authentication

# Using Service Account:
# See https://www.labnol.org/google-api-service-account-220404
# 1. Create Google Cloud Project (PiBaseDemo)
# 2. Enable Google APIs - Google Drive API, IAM,
# 3. Create a Service Account (one for each external location). Create a Key File for Service Account, download JSON (don't save in Git)
# 4. Create and Share a Drive Folder - add the email address of the service account

# Using User Account:
# Note: Make sure to include terminating slash in 'http://localhost:8080/' for �Authorized redirect URIs�.
# (downloaded .json file will not have the terminating slash to muddy the matter, but it works ok, just need the slash in GD Auth config)

import inspect
import mimetypes
import os
import sys
from typing import Dict, Tuple

from apiclient import errors
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from pydrive2.files import FileNotUploadedError

from app_utils import get_conf


def get_script_dir(follow_symlinks=True):
    if getattr(sys, 'frozen', False):  # py2exe, PyInstaller, cx_Freeze
        path = os.path.abspath(sys.executable)
    else:
        path = inspect.getabsfile(get_script_dir)
    if follow_symlinks:
        path = os.path.realpath(path)
    return os.path.dirname(path)


script_dir = get_script_dir()
caller_dir = os.getcwd()
base_dir = os.path.dirname(os.path.dirname(script_dir))

demo_secrets_file = os.path.realpath(os.path.join(base_dir, "client_secrets.json"))
demo_sa_secrets_file = os.path.realpath(os.path.join(base_dir, "sa_client_secrets.json"))
demo_csv_file = os.path.realpath(os.path.join(base_dir, "test.csv"))


class GoogleDriveService:
    def __init__(self, loggr=None):
        self.loggr = loggr
        self._secrets_file = None
        self.credentials = None
        self.drive = None
        self.service = None
        self.gauth = None

    def authenticate_in_browser(self, secrets_file):
        """Authenticate using local webserver and webbrowser. Very slow and requires user interaction.

        Args:
            secrets_file (string): Path to secrets json file

        Returns:
            object: credentials
        """
        self._secrets_file = secrets_file
        if not self.credentials:
            self.gauth = GoogleAuth(settings={
                "client_config_backend": "file",
                "client_config_file": self._secrets_file,
                "save_credentials": False,
                # Try:
                # "save_credentials": True,
                # "save_credentials_backend": 'file',
                # "save_credentials_file": "creds.json",
                # https://developers.google.com/drive/api/quickstart/python - see refresh token
                "oauth_scope": ["https://www.googleapis.com/auth/drive"],
            })
            self.gauth.LocalWebserverAuth()  # Creates local webserver and auto handles authentication.
            # ? self.gauth.CommandLineAuth()  # Doesn't work for our use case: 1. It requires a token to be collected from visiting very long URL. 2. Trying that URL fails with redirect uri mismatch.
            self.credentials = self.gauth.credentials
            # print(f'Credentials: {self.gauth.credentials}')
        return self.credentials

    def authenticate_sa(self, secrets_file):
        """Authenticate using service account.

        Args:
            secrets_file (string): Path to service account secrets json file

        Returns:
            object: credentials
        """
        self._secrets_file = secrets_file
        if not self.credentials:
            self.gauth = GoogleAuth(settings={
                "client_config_backend": "file",
                "client_config_file": self._secrets_file,
                "save_credentials": False,
                # Try:
                # "save_credentials": True,
                # "save_credentials_backend": 'file',
                # "save_credentials_file": "creds.json",
                # https://developers.google.com/drive/api/quickstart/python - see refresh token
                "oauth_scope": ["https://www.googleapis.com/auth/drive"],
            })
            SCOPES = ['https://www.googleapis.com/auth/drive']
            self.gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(self._secrets_file, SCOPES)
            self.credentials = self.gauth.credentials
            # if self.loggr: self.loggr.debug(f'Credentials: {self.gauth.credentials}')
        return self.credentials

    def get_drive(self):
        if not self.drive:
            # Must call self.authenticate_*() method before.
            assert self.gauth
            assert self.credentials
            self.drive = GoogleDrive(self.gauth)
        return self.drive

    def get_service(self, api='drive', api_version='v3'):
        if not self.service:
            # see https://github.com/iterative/PyDrive2/issues/185#issuecomment-1269331395
            assert self.credentials
            http_timeout = 10
            http = Http(timeout=http_timeout)
            http_auth = self.credentials.authorize(http)
            self.service = build(api, api_version, http=http_auth, cache_discovery=False)
        return self.service

    def open_file_by_id(self, file_id):
        drive = self.get_drive()
        # Create a file with the same id
        gfile = drive.CreateFile({'id': file_id})
        gfile_fd = gfile.GetContentIOBuffer()
        return gfile_fd

    def read_file_by_id(self, file_id):
        # service = self.get_service()
        drive = self.get_drive()
        # Create a file with the same id
        gfile = drive.CreateFile({'id': file_id})
        # Save the content as a string
        content = gfile.GetContentString()
        # Transform the content into a dataframe
        # df = pd.read_csv(content)
        return gfile, content

    def upload_file(self, dir_id, file_path, mimetype, dst_filename=None, dst_mimetype=None, resumable=True):
        """Upload a file (optionally resumable, and optionally with conversion if dst_mimetype provided and is different than mimetype)
        Returns: uploaded file object
        """
        service = self.get_service()
        if not mimetype:
            mimetype = mimetypes.guess_type(file_path)[0]
            if not mimetype:
                mimetype = 'application/octet-stream'

        if not dst_filename:
            dst_filename = os.path.basename(file_path)
        if not dst_mimetype:
            dst_mimetype = mimetype
        file = None
        try:
            file_metadata = {
                'name': dst_filename,
                'mimeType': dst_mimetype,
            }
            if dir_id:
                file_metadata['parents'] = [dir_id]
            media = MediaFileUpload(file_path, mimetype=mimetype, resumable=resumable)
            # pylint: disable=maybe-no-member
            file = service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=dir_id is not None).execute()
            # supportsAllDrives=True is important to use so 'parents' works correctly.
            # if self.loggr: self.loggr.info(f'Uploaded "{file_path}" to "{dst_filename}" in folder id "{dir_id}", created file ID: "{file.get("id")}"')

        except HttpError as error:
            # if self.loggr: self.loggr.error(f'File upload failed, error: {error}')
            file = None
            raise error

        return file

    # https://developers.google.com/drive/api/v2/reference/files/list
    @classmethod
    def retrieve_all_files(cls, service):
        """Retrieve a list of File resources.

        Args:
            service: Drive API service instance.
        Returns:
            List of File resources.
        """
        result = []
        page_token = None
        while True:
            try:
                param = {}
                if page_token:
                    param['pageToken'] = page_token
                files = service.files().list(**param).execute()

                result.extend(files['items'])
                page_token = files.get('nextPageToken')
                if not page_token:
                    break
            except errors.HttpError as error:
                print(f'An error occurred: {error}')
                break
        return result

    @classmethod
    def retrieve_all_drives(cls, service):
        """Retrieve a list of Drive resources.

        Args:
            service: Drive API service instance.
        Returns:
            List of Drive resources.
        """
        result = []
        page_token = None
        while True:
            try:
                param = {}
                if page_token:
                    param['pageToken'] = page_token
                drives = service.drives().list(**param).execute()

                if 'items' in drives:
                    result.extend(drives['items'])
                else:
                    pass
                page_token = drives.get('nextPageToken')
                if not page_token:
                    break
            except errors.HttpError as error:
                print(f'An error occurred: {error}')
                break
        return result

    def drive_create_folder(self, parent_folder_id, subfolder_name):
        assert self.drive
        newFolder = self.drive.CreateFile({'title': subfolder_name, "parents": [{"kind": "drive#fileLink", "id": parent_folder_id}], "mimeType": "application/vnd.google-apps.folder"})
        newFolder.Upload()
        return newFolder

    def maybe_create_file_by_title(self, title, parent_directory_id):
        file = self.get_file_by_title(title, parent_directory_id)
        if not file:
            drive = self.get_drive()
            file = drive.CreateFile({'parents': [{'id': parent_directory_id}], 'title': title})  # Create GoogleDriveFile instance with title.
            # file.SetContentString(contents) # Set content of the file from given string.
            # file.Upload()

        return file

    def get_file_by_title(self, title, parent_directory_id):
        # based on drive_get_id_of_title() from https://docs.iterative.ai/PyDrive2/quickstart/#return-file-id-via-file-title
        drive = self.get_drive()
        foldered_list = drive.ListFile({'q':  f"'{parent_directory_id}' in parents and trashed=false"}).GetList()
        for file in foldered_list:
            if file['title'] == title:
                return file
        return None

    def get_file_id_by_title(self, title, parent_directory_id):
        file = self.get_file_by_title(title, parent_directory_id)
        return file['id'] if file else None

    # HOME_DIRECTORY=""
    # ROOT_FOLDER_NAME=""
    # USERNAME=""
    def interactive_folder_browser(self, folder_list, parent_id, browsed=None):
        if not browsed:
            browsed = []
        for element in folder_list:
            if isinstance(element, dict):
                print(element['title'])
            else:
                print(element)
        print("Enter Name of Folder You Want to Use\nEnter '/' to use current folder\nEnter ':' to create New Folder and use that")
        inp = input()
        if inp == '/':
            return parent_id
        elif inp == ':':
            print("Enter Name of Folder You Want to Create")
            inp = input()
            newfolder = self.drive_create_folder(parent_id, inp)
            # if not os.path.exists(HOME_DIRECTORY+ROOT_FOLDER_NAME+os.path.sep+USERNAME):
            #   os.makedirs(HOME_DIRECTORY+ROOT_FOLDER_NAME+os.path.sep+USERNAME)
            return newfolder['id']

        else:
            folder_selected = inp
            for element in folder_list:
                if isinstance(element, dict):
                    if element["title"] == folder_selected:
                        struc = element["list"]
                        browsed.append(folder_selected)
                        print("Inside " + folder_selected)
                        return self.interactive_folder_browser(struc, element['id'], browsed)


def gd_connect(loggr, gd_secrets, extra_fields_with_values: Dict[str, str] = None, extra_mode: str = 'override', skip_msg: str = 'Will skip uploading results files.', prefix: str = 'pibase_') -> Tuple[GoogleDriveService, Dict[str, str]]:
    """Helper function: Open secrets file and Authenticate with Google Drive.
    Additionally load extra fields from the secrets file.

    Args:
        loggr (Loggr): Logger object
        gd_secrets (str): File with GD secrets
        extra_fields_with_values (Dict[str, str], optional): Keys define extra fields to load from gd_secrets file, how to use the values is determined by extra_mode. Defaults to None.
        extra_mode (str, optional): 'override' will load field from secrets file if given value is None. 'default' will use given value as fallback if secrets file does not have the field set.
                            'override' mode is intended for command line args that should override secrets file values. Defaults to 'override'.
        skip_msg (str, optional): Text to add to loggr messages when cannot load gd_secrets or connect. Defaults to 'Will skip uploading results files.'.
        prefix (str, optional): Prefix for all field names in gd_secrets file. Defaults to 'pibase_'.

    Returns:
        Tuple[GoogleDriveService, Dict[str, str]]: Google Drive service object, Extra fields from the secrets file.
    """
    if extra_fields_with_values is None:
        extra_fields_with_values = {}
    gds, extra = None, {}
    if gd_secrets:
        if os.path.isfile(gd_secrets):
            try:
                secrets = get_conf(filepath=gd_secrets)
                for k, v in extra_fields_with_values.items():
                    if extra_mode == 'override' and v is None:
                        v = secrets.get(prefix + k)
                    elif extra_mode == 'default':
                        v = secrets.get(prefix + k, v)
                    extra[k] = v
            except Exception as err:
                if loggr:
                    loggr.error(f'Error "{err}" loading GD Account file "{gd_secrets}". {skip_msg}')
        else:
            if loggr:
                loggr.warning(f'GD Account file "{gd_secrets}" not found. {skip_msg}')

        # Validate that all requested extra items are present
        for k, v in extra.items():
            if not v:
                if loggr:
                    loggr.warning(f'GD Folder ID ({prefix + k}) is not configured in the secrets file "{gd_secrets}". {skip_msg}')
                return None, {}

        try:
            gds = GoogleDriveService()
            gds.authenticate_sa(gd_secrets)
            if loggr:
                loggr.info('Authenticated with GD.')
        except Exception as err:
            if loggr:
                loggr.error(f'Failed authenticating with GD, error "{err}". {skip_msg}')
            return None, {}
    return gds, extra


def check_file_write(drive, dir_id, filename, contents):
    file1 = drive.CreateFile({'parents': [{'id': dir_id}], 'title': filename})  # Create GoogleDriveFile instance with title.
    file1.SetContentString(contents)  # Set content of the file from given string.
    file1.Upload()
    print(f'Created file "{filename}" in Drive/Folder "{dir_id}", size:{len(contents)}')


def check_file_upload(drive, dir_id):
    filename = '1.jpg'
    gfile = drive.CreateFile({'parents': [{'id': dir_id}]})
    # Read file and set it as the content of this instance.
    gfile.SetContentFile(filename)
    gfile.Upload()  # Upload the file.


def check_list_files(drive, folder_id):
    # Auto-iterate through all files that matches this query
    query_fmt = "'{id}' in parents and trashed=false"
    query = query_fmt.format(id=folder_id)
    file_list = drive.ListFile({'q': query}).GetList()
    # file_list = drive.ListFile({'q': query, 'corpora': 'drive', 'teamDriveId': f'{folder_id}', 'includeTeamDriveItems': True, 'supportsTeamDrives': True}).GetList()
    # Should use `'supportsAllDrives' = True` instead of deprecated `'includeTeamDriveItems': True`
    print('-' * 80)
    print(f'Drive/Folder ID "{folder_id}" items: {len(file_list)}')
    for i, file1 in enumerate(file_list):
        print(f'  {i+1:3d}. title: {file1["title"]}, id: {file1["id"]}')
    print('-' * 80)


def drive_delete_file(drive, file_id):
    file = drive.CreateFile({'id': file_id})
    # file.Trash()  # Move file to trash.
    # file.UnTrash()  # Move file out of trash.
    file.Delete()  # Permanently delete the file.
    print(f'Deleted file id "{file_id}"')


def upload_file(service, dir_id, file_path, mimetype, dst_filename=None, dst_mimetype=None, resumable=True):
    """Upload a file (optionally resumable, and optionally with conversion if dst_mimetype provided and is different than mimetype)
    Returns: ID of the file uploaded
    """
    if not mimetype:
        mimetype = mimetypes.guess_type(file_path)[0]
        if not mimetype:
            mimetype = 'application/octet-stream'

    if not dst_filename:
        dst_filename = os.path.basename(file_path)
    if not dst_mimetype:
        dst_mimetype = mimetype
    file = None
    try:
        file_metadata = {
            'name': dst_filename,
            'mimeType': dst_mimetype,
        }
        if dir_id:
            file_metadata['parents'] = [dir_id]
        media = MediaFileUpload(file_path, mimetype=mimetype, resumable=resumable)
        # pylint: disable=maybe-no-member
        file = service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=dir_id is not None).execute()
        # supportsAllDrives=True is important to use so 'parents' works correctly.
        print(f'Uploaded "{file_path}" to "{dst_filename}" in folder id "{dir_id}", created file ID: "{file.get("id")}"')

    except HttpError as error:
        # print(F'upload_file() failed, error: {error}')
        file = None
        raise error

    return file


def demo(use_sa=True):
    dir_ids = [
        # 'root',
        '1ps5YqAjqVO06v9C72XNUboxnHVTLKDTm',  # MyDrive(private) / Pibase / BaseAdmin
    ]
    mygd = GoogleDriveService()
    if use_sa:
        print('=' * 80)
        print(f'Using Service Account, secrets file "{demo_sa_secrets_file}"')
        mygd.authenticate_sa(demo_sa_secrets_file)
    else:
        print('=' * 80)
        print(f'Using User Account, secrets file "{demo_secrets_file}"')
        mygd.authenticate_in_browser(demo_secrets_file)
    drive = mygd.get_drive()

    if False:  # pylint: disable=using-constant-test
        for dir_id in dir_ids:
            filename = f'Hello-{"SA" if use_sa else "User"}.txt'
            try:
                check_file_write(drive, dir_id, filename, 'Hello World!')
            except Exception as err:
                print(f'check_file_write("{dir_id}") failed, Error {err}')
    # check_file_upload(drive)

    # see https://github.com/iterative/PyDrive2/issues/185#issuecomment-1269331395
    service = mygd.get_service()
    drives = GoogleDriveService.retrieve_all_drives(service)
    print('-' * 80)
    print(f'All Drives: items:{len(drives)}')
    for i, item in enumerate(drives):
        print(f'  {i:3d}. id={item["id"]} name="{item["name"]}"')
    print('-' * 80)

    for dir_id in dir_ids:
        try:
            check_list_files(drive, dir_id)
        except Exception as err:
            print(f'check_list_files("{dir_id}") failed, Error {err}')

    file_ids = [
        '1pKFPXp_8j0_OCNQRgX-G8MYovbvnImwm',
    ]
    for file_id in file_ids:
        try:
            drive_delete_file(drive, file_id)
        except Exception as err:
            print(f'drive_delete_file("{file_id}") failed, Error {err}')

    file_path = demo_csv_file
    mimetype = 'text/csv'
    for dir_id in dir_ids:
        try:
            file1 = upload_file(service, dir_id, file_path, mimetype)
        except Exception as err:
            print(f'upload_file("{dir_id}, {file_path}") failed, Error {err}')


if __name__ == '__main__':
    # Quick demo / examples / tests:
    demo(use_sa=True)
    # demo(use_sa=False)
