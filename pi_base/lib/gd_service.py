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

from __future__ import annotations

import inspect
import logging
import mimetypes
import os
import sys
from typing import Optional

from apiclient import errors
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials, client
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from pydrive2.files import GoogleDriveFile, MediaIoReadable, ApiRequestError, FileNotUploadedError

from .app_utils import GetConf  # pylint: disable=relative-beyond-top-level

__all__ = [
    # Unused imports for export
    "ApiRequestError",
    "FileNotUploadedError",
    # API:
    "gd_connect",
    "GoogleDriveService",
    "GoogleDrive",
    "GoogleDriveFile",
    # Examples:
    # "check_file_write",
    # "check_file_upload",
    # "check_list_files",
    # "drive_delete_file",
    # "upload_file",
]


class GoogleDriveService:
    def __init__(self, loggr: Optional[logging.Logger] = None) -> None:
        self.loggr = loggr
        self._secrets_file: Optional[str] = None
        self.credentials: Optional[ServiceAccountCredentials | client.OAuth2Credentials] = None
        self.drive: Optional[GoogleDrive] = None
        self.service: Optional[Resource] = None
        self.gauth = None

    def authenticate_in_browser(self, secrets_file: str) -> Optional[ServiceAccountCredentials | client.OAuth2Credentials]:
        """Authenticate using local webserver and webbrowser. Very slow and requires user interaction.

        Args:
            secrets_file: Path to secrets json file

        Returns:
            Credentials object
        """
        self._secrets_file = secrets_file
        if not self.credentials:
            self.gauth = GoogleAuth(
                settings={
                    "client_config_backend": "file",
                    "client_config_file": self._secrets_file,
                    "save_credentials": False,
                    # Try:
                    # "save_credentials": True,
                    # "save_credentials_backend": 'file',
                    # "save_credentials_file": "creds.json",
                    # https://developers.google.com/drive/api/quickstart/python - see refresh token
                    "oauth_scope": ["https://www.googleapis.com/auth/drive"],
                }
            )
            if self.gauth:
                self.gauth.LocalWebserverAuth()  # Creates local webserver and auto handles authentication.
                # ? self.gauth.CommandLineAuth()  # Doesn't work for our use case: 1. It requires a token to be collected from visiting very long URL. 2. Trying that URL fails with redirect uri mismatch.
                self.credentials = self.gauth.credentials
                # print(f'Credentials: {self.gauth.credentials}')
        return self.credentials

    def authenticate_sa(self, secrets_file: str) -> Optional[ServiceAccountCredentials | client.OAuth2Credentials]:
        """Authenticate using service account.

        Args:
            secrets_file: Path to service account secrets json file

        Returns:
            Credentials object
        """
        self._secrets_file = secrets_file
        if not self.credentials:
            self.gauth = GoogleAuth(
                settings={
                    "client_config_backend": "file",
                    "client_config_file": self._secrets_file,
                    "save_credentials": False,
                    # Try:
                    # "save_credentials": True,
                    # "save_credentials_backend": 'file',
                    # "save_credentials_file": "creds.json",
                    # https://developers.google.com/drive/api/quickstart/python - see refresh token
                    "oauth_scope": ["https://www.googleapis.com/auth/drive"],
                }
            )
            if self.gauth:
                # scopes = ["https://www.googleapis.com/auth/drive"] # Either list or str works, however, ServiceAccountCredentials.from_json_keyfile_name() has no type annotation for the list.
                scopes = "https://www.googleapis.com/auth/drive"
                self.gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(self._secrets_file, scopes)
                self.credentials = self.gauth.credentials
                # if self.loggr: self.loggr.debug(f'Credentials: {self.gauth.credentials}')
        return self.credentials

    def get_drive(self) -> Optional[GoogleDrive]:
        if not self.drive:
            # Must call self.authenticate_*() method before.
            if not self.gauth:
                raise ValueError("Expected non-empty self.gauth.")
            if not self.credentials:
                raise ValueError("Expected non-empty self.credentials.")

            self.drive = GoogleDrive(self.gauth)
        return self.drive

    def get_service(self, api: str = "drive", api_version: str = "v3") -> Optional[Resource]:
        if not self.service:
            # see https://github.com/iterative/PyDrive2/issues/185#issuecomment-1269331395
            if not self.credentials:
                raise ValueError("Expected non-empty self.credentials.")
            http_timeout = 10
            http = Http(timeout=http_timeout)
            http_auth = self.credentials.authorize(http)
            self.service = build(api, api_version, http=http_auth, cache_discovery=False)
        return self.service

    def open_file_by_id(self, file_id: str) -> Optional[MediaIoReadable]:
        drive = self.get_drive()
        if not drive:
            return None
        # Create a file with the same id
        gfile = drive.CreateFile({"id": file_id})
        return gfile.GetContentIOBuffer()

    def read_file_by_id(self, file_id: str) -> Optional[tuple[GoogleDriveFile, str]]:
        # service = self.get_service()
        drive = self.get_drive()
        if not drive:
            return None
        # Create a file with the same id
        gfile = drive.CreateFile({"id": file_id})
        # Save the content as a string
        content = gfile.GetContentString()
        # Transform the content into a dataframe
        # df = pd.read_csv(content)
        return gfile, content

    def upload_file(
        self, dir_id: Optional[str], file_path: str, mimetype: str, dst_filename: Optional[str] = None, dst_mimetype: Optional[str] = None, resumable: bool = True
    ) -> Optional[GoogleDriveFile]:
        """Upload a file (optionally resumable, and optionally with conversion if dst_mimetype provided and is different than mimetype).

        Args:
            dir_id: ID of the parent directory to upload to
            file_path: Path to the source file to upload
            mimetype: MIME type of the source file
            dst_filename: Name of the destination file
            dst_mimetype: MIME type of the destination file (provide different value for automatic conversion)
            resumable: Use resumable upload

        Returns:
            Uploaded file object
        """
        service = self.get_service()
        if not service:
            return None
        if not hasattr(service, "files"):
            raise ValueError('Expected GoogleDrive "drive" service to have "files" attribute')
        if not mimetype:
            mimetype_maybe = mimetypes.guess_type(file_path)[0]
            mimetype = mimetype_maybe or "application/octet-stream"

        if not dst_filename:
            dst_filename = os.path.basename(file_path)
        if not dst_mimetype:
            dst_mimetype = mimetype
        file = None
        try:
            file_metadata: dict[str, str | list[str]] = {
                "name": dst_filename,
                "mimeType": dst_mimetype,
            }
            if dir_id:
                file_metadata["parents"] = [dir_id]
            media = MediaFileUpload(file_path, mimetype=mimetype, resumable=resumable)
            # pylint: disable=maybe-no-member
            files_service = service.files()  # pyright: ignore[reportAttributeAccessIssue]
            if files_service:
                file = files_service.create(body=file_metadata, media_body=media, fields="id", supportsAllDrives=dir_id is not None).execute()
            # supportsAllDrives=True is important to use so 'parents' works correctly.
            # if self.loggr: self.loggr.info(f'Uploaded "{file_path}" to "{dst_filename}" in folder id "{dir_id}", created file ID: "{file.get("id")}"')

        except HttpError as error:
            # if self.loggr: self.loggr.error(f'File upload failed, error: {error}')
            file = None
            raise error  # noqa: TRY201

        return file

    # https://developers.google.com/drive/api/v2/reference/files/list
    @classmethod
    def retrieve_all_files(cls, service: Resource) -> list[GoogleDriveFile]:
        """Retrieve a list of File resources.

        Args:
            service: Drive API service instance.

        Returns:
            List of File resources.
        """
        result = []
        page_token = None
        if not hasattr(service, "files"):
            raise ValueError('Expected GoogleDrive "drive" service to have "files" attribute')
        while True:
            try:
                param: dict[str, str] = {}
                if page_token:
                    param["pageToken"] = page_token
                page_token = None
                files_service = service.files()  # pyright: ignore[reportAttributeAccessIssue]
                if files_service:
                    files = files_service.list(**param).execute()
                    if files:
                        result.extend(files.get("items", []))
                        page_token = files.get("nextPageToken")
                if not page_token:
                    break
            except errors.HttpError as error:
                print(f"An error occurred: {error}")
                break
        return result

    @classmethod
    def retrieve_all_drives(cls, service: Resource) -> list[GoogleDrive]:
        """Retrieve a list of Drive resources.

        Args:
            service: Drive API service instance.

        Returns:
            List of Drive resources.
        """
        result = []
        page_token = None
        if not hasattr(service, "drives"):
            raise ValueError('Expected GoogleDrive "drive" service to have "drives" attribute')
        while True:
            try:
                param: dict[str, str] = {}
                if page_token:
                    param["pageToken"] = page_token
                page_token = None
                drives_service = service.drives()  # pyright: ignore[reportAttributeAccessIssue]
                if drives_service:
                    drives = drives_service.list(**param).execute()
                    if drives:
                        result.extend(drives.get("items", []))
                        page_token = drives.get("nextPageToken")
                if not page_token:
                    break
            except errors.HttpError as error:
                print(f"An error occurred: {error}")
                break
        return result

    def drive_create_folder(self, parent_folder_id: str, subfolder_name: str) -> Optional[GoogleDriveFile]:
        if not self.drive:
            raise ValueError("Expected non-empty self.drive.")
        new_folder = self.drive.CreateFile({"title": subfolder_name, "parents": [{"kind": "drive#fileLink", "id": parent_folder_id}], "mimeType": "application/vnd.google-apps.folder"})
        new_folder.Upload()
        return new_folder

    def maybe_create_file_by_title(self, title: str, parent_directory_id: str) -> tuple[GoogleDriveFile | None, bool]:
        created = False
        file = self.get_file_by_title(title, parent_directory_id)
        if not file:
            drive = self.get_drive()
            if drive:
                file = drive.CreateFile({"parents": [{"id": parent_directory_id}], "title": title})  # Create GoogleDriveFile instance with title.
                # file.SetContentString(contents) # Set content of the file from given string.
                # file.Upload()
                created = True

        return file, created

    def get_file_by_title(self, title: str, parent_directory_id: str) -> Optional[GoogleDriveFile]:
        # based on drive_get_id_of_title() from https://docs.iterative.ai/PyDrive2/quickstart/#return-file-id-via-file-title
        drive = self.get_drive()
        if drive:
            foldered_list = drive.ListFile({"q": f"'{parent_directory_id}' in parents and trashed=false"}).GetList()
            for file in foldered_list:
                if file["title"] == title:
                    return file
        return None

    def get_file_id_by_title(self, title: str, parent_directory_id: str) -> Optional[str]:
        file = self.get_file_by_title(title, parent_directory_id)
        return file["id"] if file else None

    # HOME_DIRECTORY=""
    # ROOT_FOLDER_NAME=""
    # USERNAME=""
    def interactive_folder_browser(self, folder_list: list[dict[str, str | list]], parent_id: str, browsed: Optional[list[str]] = None) -> Optional[str]:
        if not browsed:
            browsed = []
        for element in folder_list:
            if isinstance(element, dict):
                print(element["title"])
            else:
                print(element)
        print("Enter Name of Folder You Want to Use\nEnter '/' to use current folder\nEnter ':' to create New Folder and use that")
        inp = input()
        if inp == "/":
            return parent_id

        if inp == ":":
            print("Enter Name of Folder You Want to Create")
            inp = input()
            newfolder = self.drive_create_folder(parent_id, inp)
            # if not os.path.exists(HOME_DIRECTORY+ROOT_FOLDER_NAME+os.path.sep+USERNAME):
            #   os.makedirs(HOME_DIRECTORY+ROOT_FOLDER_NAME+os.path.sep+USERNAME)
            return newfolder["id"] if newfolder else None

        folder_selected = inp
        for element in folder_list:
            if isinstance(element, dict) and element["title"] == folder_selected:
                if not isinstance(element["list"], list):
                    return None  # This should not be happening, but type system is simplistic, need schema instead.
                struc: list[dict[str, str | list]] = element["list"]
                browsed.append(folder_selected)
                print("Inside " + folder_selected)
                if not isinstance(element["id"], str):
                    return None  # This should not be happening, but type system is simplistic, need schema instead.
                return self.interactive_folder_browser(struc, element["id"], browsed)
        return None


def gd_connect(
    loggr: Optional[logging.Logger],
    gd_secrets: str,
    extra_fields_with_values: Optional[dict[str, Optional[str]]] = None,
    extra_mode: str = "override",
    skip_msg: str = "Will skip uploading results files.",
    prefix: str = "pibase_",
) -> tuple[Optional[GoogleDriveService], dict[str, Optional[str]]]:
    """Helper function: Open secrets file and Authenticate with Google Drive, and additionally load extra fields from the secrets file.

    Args:
        loggr: Logger object
        gd_secrets: File with GD secrets
        extra_fields_with_values: Keys define extra fields to load from gd_secrets file, how to use the values is determined by extra_mode. Defaults to None.
        extra_mode: 'override' will load field from secrets file if given value is None. 'default' will use given value as fallback if secrets file does not have the field set.
                            'override' mode is intended for command line args that should override secrets file values. Defaults to 'override'.
        skip_msg: Text to add to loggr messages when cannot load gd_secrets or connect. Defaults to 'Will skip uploading results files.'.
        prefix: Prefix for all field names in gd_secrets file. Defaults to 'pibase_'.

    Returns:
        Tuple of Google Drive service object, dict with extra fields from the secrets file.
    """
    if extra_fields_with_values is None:
        extra_fields_with_values = {}
    gds, extra = None, {}
    if gd_secrets:
        if os.path.isfile(gd_secrets):
            try:
                secrets = GetConf(filepath=gd_secrets)
                for k, v_in in extra_fields_with_values.items():
                    if extra_mode == "override" and v_in is None:
                        v = secrets.get(prefix + k)
                    elif extra_mode == "default":
                        v = secrets.get(prefix + k, v_in)
                    else:
                        v = v_in
                    extra[k] = v
            except Exception as err:
                if loggr:
                    loggr.error(f'Error {type(err)} "{err}" loading GoogleDrive Account file "{gd_secrets}". {skip_msg}')
        elif loggr:
            loggr.warning(f'GoogleDrive Account file "{gd_secrets}" not found. {skip_msg}')

        # Validate that all requested extra items are present
        for k, v in extra.items():
            if not v:
                if loggr:
                    loggr.warning(f'GoogleDrive Folder ID ({prefix + k}) is not configured in the secrets file "{gd_secrets}". {skip_msg}')
                return None, {}

        try:
            gds = GoogleDriveService()
            gds.authenticate_sa(gd_secrets)
            if loggr:
                loggr.info("Authenticated with GoogleDrive.")
        except Exception as err:
            if loggr:
                loggr.error(f'Failed authenticating with GoogleDrive, error "{err}". {skip_msg}')
            return None, {}
    return gds, extra


def check_file_write(drive: GoogleDrive, dir_id: str, filename: str, contents: str) -> None:
    file1 = drive.CreateFile({"parents": [{"id": dir_id}], "title": filename})  # Create GoogleDriveFile instance with title.
    file1.SetContentString(contents)  # Set content of the file from given string.
    file1.Upload()
    print(f'Created file "{filename}" in Drive/Folder "{dir_id}", size:{len(contents)}')


def check_file_upload(drive: GoogleDrive, dir_id: str) -> None:
    filename = "1.jpg"
    gfile = drive.CreateFile({"parents": [{"id": dir_id}]})
    # Read file and set it as the content of this instance.
    gfile.SetContentFile(filename)
    gfile.Upload()  # Upload the file.


def check_list_files(drive: GoogleDrive, folder_id: str) -> None:
    # Auto-iterate through all files that matches this query
    query_fmt = "'{id}' in parents and trashed=false"
    query = query_fmt.format(id=folder_id)
    file_list = drive.ListFile({"q": query}).GetList()
    # file_list = drive.ListFile({'q': query, 'corpora': 'drive', 'teamDriveId': f'{folder_id}', 'includeTeamDriveItems': True, 'supportsTeamDrives': True}).GetList()
    # Should use `'supportsAllDrives' = True` instead of deprecated `'includeTeamDriveItems': True`
    print("-" * 80)
    print(f'Drive/Folder ID "{folder_id}" items: {len(file_list)}')
    for i, file1 in enumerate(file_list):
        print(f'  {i+1:3d}. title: {file1["title"]}, id: {file1["id"]}')
    print("-" * 80)


def drive_delete_file(drive: GoogleDrive, file_id: str) -> None:
    file = drive.CreateFile({"id": file_id})
    # file.Trash()  # Move file to trash.
    # file.UnTrash()  # Move file out of trash.
    file.Delete()  # Permanently delete the file.
    print(f'Deleted file id "{file_id}"')


def upload_file(
    service: Resource, dir_id: str, file_path: str, mimetype: str, dst_filename: Optional[str] = None, dst_mimetype: Optional[str] = None, resumable: bool = True
) -> Optional[GoogleDriveFile]:
    """Upload a file (optionally resumable, and optionally with conversion if dst_mimetype provided and is different than mimetype).

    Args:
        dir_id: ID of the parent directory to upload to
        file_path: Path to the source file to upload
        mimetype: MIME type of the source file
        dst_filename: Name of the destination file
        dst_mimetype: MIME type of the destination file (provide different value for automatic conversion)
        resumable: Use resumable upload

    Returns:
        ID of the file uploaded
    """
    if not hasattr(service, "files"):
        raise ValueError('Expected GoogleDrive "drive" service to have "files" attribute')
    if not mimetype:
        mimetype_maybe = mimetypes.guess_type(file_path)[0]
        mimetype = mimetype_maybe or "application/octet-stream"

    if not dst_filename:
        dst_filename = os.path.basename(file_path)
    if not dst_mimetype:
        dst_mimetype = mimetype
    file = None
    try:
        file_metadata: dict[str, str | list[str]] = {
            "name": dst_filename,
            "mimeType": dst_mimetype,
        }
        if dir_id:
            file_metadata["parents"] = [dir_id]
        media = MediaFileUpload(file_path, mimetype=mimetype, resumable=resumable)
        files_service = service.files()  # pyright: ignore[reportAttributeAccessIssue]
        if files_service:
            file = files_service.create(body=file_metadata, media_body=media, fields="id", supportsAllDrives=dir_id is not None).execute()
            # supportsAllDrives=True is important to use so 'parents' works correctly.
            print(f'Uploaded "{file_path}" to "{dst_filename}" in folder id "{dir_id}", created file ID: "{file.get("id")}"')

    except HttpError as error:
        # print(F'upload_file() failed, error: {error}')
        file = None
        raise error  # noqa: TRY201

    return file


def demo(use_sa: bool = True) -> None:
    def get_script_dir(follow_symlinks: bool = True) -> str:
        if getattr(sys, "frozen", False):  # py2exe, PyInstaller, cx_Freeze
            path = os.path.abspath(sys.executable)
        else:
            path = inspect.getabsfile(get_script_dir)
        if follow_symlinks:
            path = os.path.realpath(path)
        return os.path.dirname(path)

    script_dir = get_script_dir()
    # caller_dir = os.getcwd()
    base_dir = os.path.dirname(os.path.dirname(script_dir))

    demo_secrets_file = os.path.realpath(os.path.join(base_dir, "client_secrets.json"))
    demo_sa_secrets_file = os.path.realpath(os.path.join(base_dir, "sa_client_secrets.json"))
    demo_csv_file = os.path.realpath(os.path.join(base_dir, "test.csv"))

    dir_ids = [
        # 'root',
        "1ps5YqAjqVO06v9C72XNUboxnHVTLKDTm",  # MyDrive(private) / Pibase / BaseAdmin
    ]
    mygd = GoogleDriveService()
    if use_sa:
        print("=" * 80)
        print(f'Using Service Account, secrets file "{demo_sa_secrets_file}"')
        mygd.authenticate_sa(demo_sa_secrets_file)
    else:
        print("=" * 80)
        print(f'Using User Account, secrets file "{demo_secrets_file}"')
        mygd.authenticate_in_browser(demo_secrets_file)
    drive = mygd.get_drive()
    if not drive:
        raise ConnectionError("Could not get drive from GoogleDrive")

    if False:  # pylint: disable=using-constant-test
        for dir_id in dir_ids:
            filename = f'Hello-{"SA" if use_sa else "User"}.txt'
            try:
                check_file_write(drive, dir_id, filename, "Hello World!")
            except Exception as err:
                print(f'check_file_write("{dir_id}") failed, Error {err}')
    # check_file_upload(drive)

    # see https://github.com/iterative/PyDrive2/issues/185#issuecomment-1269331395
    service = mygd.get_service()
    if not service:
        raise ConnectionError("Could not get service from GoogleDrive")
    drives = GoogleDriveService.retrieve_all_drives(service) if service else []
    print("-" * 80)
    print(f"All Drives: items:{len(drives)}")
    for i, item in enumerate(drives):
        print(f'  {i:3d}. id={item["id"]} name="{item["name"]}"')
    print("-" * 80)

    for dir_id in dir_ids:
        try:
            check_list_files(drive, dir_id)
        except Exception as err:  # noqa: PERF203
            print(f'check_list_files("{dir_id}") failed, Error {err}')
            continue

    file_ids = [
        "1pKFPXp_8j0_OCNQRgX-G8MYovbvnImwm",
    ]
    for file_id in file_ids:
        try:
            drive_delete_file(drive, file_id)
        except Exception as err:  # noqa: PERF203
            print(f'drive_delete_file("{file_id}") failed, Error {err}')
            continue

    file_path = demo_csv_file
    mimetype = "text/csv"
    for dir_id in dir_ids:
        try:
            file1 = upload_file(service, dir_id, file_path, mimetype)
        except Exception as err:  # noqa: PERF203
            print(f'upload_file("{dir_id}, {file_path}") failed, Error {err}')
            continue


if __name__ == "__main__":
    # Quick demo / examples / tests:
    demo(use_sa=True)
    # demo(use_sa=False)
