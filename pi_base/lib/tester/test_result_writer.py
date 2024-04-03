from typing import Optional, Union

# "modpath" must be first of our modules
# pylint: disable=wrong-import-position
# ruff: noqa: E402
# from pi_base.modpath import app_conf_dir

from .tester_common import TestError
from .test_commit_callbacks import ResultCommitCallback
from .test_script_defines import RESULT_BLOCK_BEGIN, RESULT_BLOCK_END


class ResultsWriter:
    def __init__(self) -> None:
        self.results_buffer: list[str] = []
        self.callbacks: list[ResultCommitCallback] = []

    def register_commit_callback(self, callback: ResultCommitCallback) -> None:
        """Register a callback."""
        self.callbacks.append(callback)

    def add_script_line(self, script_line: str) -> None:
        """Write the script line to the results buffer.

        Args:
            script_line: Script line to write
        """
        if isinstance(script_line, list):
            script_line = ", ".join(script_line)
        self.results_buffer.append(f"{script_line.rstrip()}")

    def _add_device_response_ex(self, device_response: "list[str]") -> None:
        """Write the device response to the results buffer.

        Args:
            device_response : Device response list of lines to write
        """
        # list[ str ] -> str
        device_response_str = "\n".join(device_response)
        # Add comments to each line in response
        self.results_buffer.append(f"##, {RESULT_BLOCK_BEGIN}\n{device_response_str}\n##, {RESULT_BLOCK_END}")

    def add_device_response(self, device_response: "Union[str, list[list[str]], list[str]]") -> None:
        """Write the device response to the results buffer.

        Args:
            device_response : Device response text to write
        """
        # Split up multiline response if not already split
        if isinstance(device_response, str):
            if "\n" in device_response:
                # str -> split and remove empty lines -> list[ str ]
                device_response = [line.rstrip() for line in device_response.split("\n") if line.strip() != ""]
            else:
                device_response = [device_response]

        if not isinstance(device_response, list):
            raise TypeError("Expected device_response to be either string or list")

        if isinstance(device_response[0], list):
            # list[ list [str] ] -> list[ str ]
            device_response = [", ".join([str(cell).strip() for cell in row] if isinstance(row, list) else str(row)) for row in device_response]
            self._add_device_response_ex(device_response)

        if isinstance(device_response, list) and device_response:
            # list[ str | Any ] -> list[str]
            device_response = [line for line in device_response if isinstance(line, str)]
            self._add_device_response_ex(device_response)

    def add_result(self, result_header: Optional[str] = None, result_line: Optional[str] = None, returncode: Optional[TestError] = None) -> None:
        """Write the result(s) from the script to the buffer.

        Args:
            result_header : Header explaining the results line(s)
            result_lines  : Line to write as the result
            returncode    : Return code integer
        """
        if result_header is not None:
            self.results_buffer.append(f"##, {result_header}" + ("" if returncode is None else ", error_code"))
        if result_line is not None:
            self.results_buffer.append(f"##, {result_line}" + ("" if returncode is None else f", {returncode.name} {returncode.string}"))

    def commit_results(self, file_name: str) -> "list[tuple[ResultCommitCallback, TestError, str]]":
        """Commit (save) the result buffer to all registered save locations.

        This does *not* clear the results buffer.

        Args:
            file_name : File name of the results file

        Returns:
            List of callbacks and their results with string explaining reason for failure if not success.
        """
        callback_results = []
        for callback in self.callbacks:
            try:
                reason = callback.commit(self.results_buffer, file_name)
                err, msg = reason
                callback_results.append((callback, err, msg))
            except Exception as e:  # noqa: PERF203
                callback_results.append((callback, TestError.ERR_FILE_SAVE, f'Error: "{e}"'))
        return callback_results

    def clear_results(self) -> None:
        """Clear the results buffer."""
        self.results_buffer = []
