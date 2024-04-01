from __future__ import annotations
import abc
import logging
import os
from typing import Optional, Union

from pi_base.lib.gd_service import gd_connect  # pylint: disable=wrong-import-position

from .tester_common import TestError


class ResultCommitCallback(abc.ABC):
    """Abstract class all commit callbacks should inherit from."""

    @abc.abstractmethod
    def commit(self, results_buffer: list[str], file_path: str) -> tuple[TestError, str | None]:
        """Abstract method for commit the results buffer.

        This can be saving to a file, uploading to Drive, etc..

        Args:
            results_buffer : Lines to commit
            file_path      : Full path of the file

        Returns:
            Tuple of error code and reason why the commit failed if error, None if successful
        """


class ResultCommitToFileCallback(ResultCommitCallback):
    """Commits the results to a locally stored file."""

    def __init__(self) -> None:
        pass

    def commit(self, results_buffer: list[str], file_path: str) -> tuple[TestError, str | None]:
        returncode = TestError.ERR_OK
        reason = None
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for line in results_buffer:
                    f.write(line + "\n")
        except Exception as e:
            reason = str(e)
            returncode = TestError.ERR_FILE_SAVE

        return returncode, reason


class ResultCommitToGoogleDriveCallback(ResultCommitCallback):
    """Commits (uploads) the results to Google Drive."""

    def __init__(self, loggr: logging.Logger, gd_secrets_file: str, gd_folder_id: Optional[str] = None) -> None:
        self.loggr = loggr
        self.gd_secrets_file = gd_secrets_file
        self.gd_folder_id = gd_folder_id
        self.file_name = None

    def commit(self, results_buffer: list[str], file_path: str) -> tuple[TestError, str | None]:
        returncode = TestError.ERR_OK
        reason = None

        path = file_path
        for _ in range(1):  # Emulate goto by `break`
            # Authenticate with Google Drive (for results upload)
            drive_service, extras = gd_connect(self.loggr, self.gd_secrets_file, {"gd_results_folder_id": self.gd_folder_id})
            if not drive_service:
                returncode = TestError.ERR_FILE_SAVE
                reason = "Error connecting to GoogleDrive."
                break

            gd_folder_id = extras["gd_results_folder_id"] if extras else None
            if not gd_folder_id:
                returncode = TestError.ERR_NO_CONFIG
                reason = f'No "gd_results_folder_id" setting in "{self.gd_secrets_file}".'
                break

            if not os.path.isfile(file_path):  # A hack - Piggy back on the physical file written by other ResultCommitCallback.
                path = os.path.join(os.path.dirname(__file__), os.path.basename(file_path))  # TODO: (when needed) Better tmp file placement method?
                try:
                    # TODO: (soon) Can we upload file to GD from a buffer without a tmp file??
                    # Write a temporary file to upload
                    with open(path, "w", encoding="utf-8") as f:
                        for line in results_buffer:
                            f.write(line + "\n")
                except Exception as err:
                    reason = f'Error "{err}" when saving results to a temporary file "{path}".'
                    break

            try:
                drive_service.upload_file(gd_folder_id, path, "text/csv")
            except Exception as err:
                reason = f'Error "{err}" when saving results file "{path}" to GD.'
                returncode = TestError.ERR_FILE_SAVE
                break

        if path and path != file_path:
            os.remove(path)

        self.file_name = None
        return returncode, reason


class ResultCommitToDataBase(ResultCommitCallback):
    # TODO: (when needed) Implement
    def __init__(self) -> None:
        pass

    def commit(self, results_buffer: list[str], file_path: str) -> Union[None, str]:
        return None
