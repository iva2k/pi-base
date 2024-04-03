from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Optional, TYPE_CHECKING
from collections.abc import Mapping

# "modpath" must be first of our modules
# pylint: disable=wrong-import-position
# ruff: noqa: E402
from pi_base.modpath import app_conf_dir
from pi_base.lib.app_utils import AtDict

# Shared monorepo lib

if TYPE_CHECKING:
    from pi_base.lib.loggr import Loggr

app_conf_dir += ""


class FilterResult(Enum):
    FILTER_NONE = 0
    FILTER_QUIT = 1
    FILTER_REBOOT = 2
    FILTER_SHUTDOWN = 3
    FILTER_SIGNOFF = 4


class FilterInterface:
    def filter_input(self, data_entry, entry, allow_signoff=False) -> FilterResult:
        return FilterResult.FILTER_NONE


class DataEntryResult(Enum):
    ERR_OK = 0
    ERR_CANCEL = 1
    ERR_RETRY = 2
    ERR_BARCODE_FORMAT = 3
    ERR_UNKNOWN_PN = 4


class DataEntryInterface:
    """Abstract class - Interface to facilitate data entry for test.

    Various methods ask for data from the operator using provided loggr for output and fnc_input for data entry at instantiation.
    """

    # Field names
    FIELD_OPERATOR_ID = "operator ID"
    FIELD_DUT_NAME = "device"
    FIELD_DUT_ID = "device serial number"
    FIELD_LOT_NUM = "LOT number"

    # Message strings. Subclasses can override.
    MSG_ENTER_LOT_NUM = "Enter {FIELD_LOT_NUM} and hit [ENTER]: "  # Can use {FIELD_LOT_NUM}
    MSG_ENTER_LOT_NUM_KEEP = "Enter {FIELD_LOT_NUM} or press [ENTER] to use the current one ({prev_lot_num}): "  # Can use {FIELD_LOT_NUM} and {prev_lot_num}
    MSG_ENTER_OPERATOR_ID = "Enter {FIELD_OPERATOR_ID} and hit [ENTER]: "  # Can use {FIELD_OPERATOR_ID}
    MSG_CONNECT_DUT = "Connect {FIELD_DUT_NAME} and hit [ENTER]: "  # Can use {FIELD_DUT_NAME}, {FIELD_DUT_ID}
    MSG_DISCONNECT_DUT = "Disconnect {FIELD_DUT_NAME} and hit [ENTER]: "  # Can use {FIELD_DUT_NAME}
    MSG_ENTER_DUT_ID = "Enter {FIELD_DUT_ID} from the serial label and hit [ENTER]: "  # Can use {FIELD_DUT_ID}
    MSG_BAD_OPERATOR_ID = "  {FIELD_OPERATOR_ID} not recognized. Do not enter spaces."  # Can use {FIELD_OPERATOR_ID}
    MSG_BAD_LOT_NUM = '  Invalid {FIELD_LOT_NUM} "{lot_num}", please give a {lot_length}{lot_symbol} LOT number.'  # Can use {FIELD_LOT_NUM}, {lot_num}, {lot_length} and {lot_symbol}
    MSG_BAD_DUT_ID = "  Invalid {FIELD_DUT_ID}"  # Can use {FIELD_DUT_ID}

    def check_if_barcode(self, input_str: str) -> tuple[bool, str]:
        raise NotImplementedError
        # is_barcode = False
        # return input_str, is_barcode

    def enter_operator_id(self) -> tuple[FilterResult, bool, str]:
        """Request operator to sign-on.

        Returns:
            run,is_barcode,data - if run is FilterResult.FILTER_NONE - continue with the data, else ignore the data and stop the test loop.
        """
        raise NotImplementedError

    def enter_lot_num(self) -> tuple[FilterResult, bool, str]:
        """Requests LOT number.

        Returns:
            run,is_barcode,data - if run is FilterResult.FILTER_NONE - continue with the data, else ignore the data and stop the test loop.
        """
        raise NotImplementedError

    def enter_dut_connected(self) -> tuple[FilterResult, bool, str]:
        """Request to connect DUT and "enter".

        Returns:
            run,is_barcode,data - if run is FilterResult.FILTER_NONE - continue with the data, else ignore the data and stop the test loop.
        """
        raise NotImplementedError

    def enter_dut_disconnected(self) -> tuple[FilterResult, bool, str]:
        """Request to disconnect DUT and "enter".

        Returns:
            run,is_barcode,data - if run is FilterResult.FILTER_NONE - continue with the data, else ignore the data and stop the test loop.
        """
        raise NotImplementedError

    def enter_label_data(self) -> tuple[FilterResult, bool, str]:
        """Request to enter data from the serial label and "enter".

        Returns:
             run,is_barcode,data - if run is FilterResult.FILTER_NONE - continue with the data, else ignore the data and stop the test loop.
        """
        raise NotImplementedError

    def get_operator_info(self, operator_id: Optional[str] = None) -> str:
        raise NotImplementedError

    def get_dut_info(self) -> str:
        raise NotImplementedError


class DataEntry(DataEntryInterface):
    """Class with typical interactions to facilitate data entry for test.

    Standard interactions with the operator and minimal data validations are provided by this class.

    Sub-class it and override methods to customize interactions and data validation.
    """

    def __init__(self, fnc_input: Callable[[str], str], input_filter: FilterInterface, loggr: Loggr, options: Optional[Mapping[str, Any]] = None) -> None:
        """Constructor.

        Args:
            fnc_input: getter of test data (e.g. operator input() or some other automated data provider)
            input_filter: object should implement FilterInterface that checks for special commands in the input and returns "True" to stop test, "False" if data is not filtered and test can proceed.
        """
        # self.ensure_lot_len = 5
        # self.ensure_lot_digits = True
        self.ensure_lot_len = None
        self.ensure_lot_digits = False

        self.operator_id = None
        self.dut_id = None
        self.lot_num = None

        if not fnc_input:
            raise ValueError("Please provide fnc_input argument")
        self.fnc_input = fnc_input

        if not input_filter:
            raise ValueError("Please provide input_filter argument")
        self.input_filter = input_filter

        if not loggr:
            raise ValueError("Please provide loggr argument")
        self.loggr = loggr

        # Configure the barcode scanner (USB HID keyboard type) to add TAB suffix, then with "scanner_suffix"
        # we can detect (see self.check_if_barcode()) that an entry is from scanner, not from keyboard.
        # That requires to use CustomInput.input passed for fnc_input.
        opts: dict[str, Any] = {
            "scanner_suffix": ["\t"],
        }
        opts.update(options if options else {})
        if isinstance(opts["scanner_suffix"], str):
            opts["scanner_suffix"] = [opts["scanner_suffix"]]

        self.options = AtDict(**opts)
        self.data_fmt = "{dut_pn}-v{dut_rev}-SN{dut_sn}"  # Format of DataEntry.data_entry() return when barcodes are scanned.

    def check_if_barcode(self, input_str: str) -> tuple[bool, str]:
        is_barcode = False
        for suffix in self.options["scanner_suffix"]:
            while input_str.endswith(suffix):
                input_str = input_str[: -len(suffix)]
                is_barcode = True
        return is_barcode, input_str

    def filtered_input(self, prompt: str, allow_signoff: bool = True) -> tuple[FilterResult, bool, str]:
        # self.test.loggr.color_print(message, color_code = ColorCodes.BLUE)
        # fnc_input = input
        # input_str = self.fnc_input(message + " and hit [Enter]: ").strip()
        # input_str = fnc_input(message + " and hit [Enter]: ").strip()
        input_str = self.fnc_input(prompt)
        is_barcode, input_str = self.check_if_barcode(input_str)
        input_str = input_str.strip()
        filt = self.input_filter.filter_input(self, input_str, allow_signoff=allow_signoff)
        if filt != FilterResult.FILTER_NONE:
            return filt, is_barcode, ""
        if len(input_str) > 0 and self.loggr:
            self.loggr.debug(f'got user entry: "{input_str}"')
        return filt, is_barcode, input_str

    def enter_operator_id(self) -> tuple[FilterResult, bool, str]:
        is_barcode = False
        prompt = self.MSG_ENTER_OPERATOR_ID.format(FIELD_OPERATOR_ID=self.FIELD_OPERATOR_ID)
        while True:
            filt, is_barcode, input_str = self.filtered_input(prompt, allow_signoff=False)
            if filt != FilterResult.FILTER_NONE:
                return filt, is_barcode, ""
            # TODO: (when needed) Implement decoding of all possible QR label formats.
            if not input_str:
                if self.loggr:
                    self.loggr.print(self.MSG_BAD_OPERATOR_ID.format(FIELD_OPERATOR_ID=self.FIELD_OPERATOR_ID))
                continue
            break
        self.operator_id = input_str
        return FilterResult.FILTER_NONE, is_barcode, input_str

    def enter_lot_num(self) -> tuple[FilterResult, bool, str]:
        is_barcode = False
        filt = FilterResult.FILTER_NONE

        if self.lot_num is None:
            prompt = self.MSG_ENTER_LOT_NUM.format(FIELD_LOT_NUM=self.FIELD_LOT_NUM)
        else:
            prompt = self.MSG_ENTER_LOT_NUM_KEEP.format(FIELD_LOT_NUM=self.FIELD_LOT_NUM, prev_lot_num=self.lot_num)
        while True:
            filt, is_barcode, input_str = self.filtered_input(prompt)
            if filt != FilterResult.FILTER_NONE:
                return filt, is_barcode, ""

            if input_str:  # If value entered, parse and validate the input
                try:  # If non apply then check if LOT number given is valid
                    # Check that the lot number is 5 digits
                    if self.ensure_lot_len and self.ensure_lot_len != len(input_str):
                        raise ValueError
                    if self.ensure_lot_digits:
                        int(input_str)  # Check that it is a number
                    self.lot_num = input_str  # Given LOT number is valid, accept it
                except:
                    if self.loggr:
                        self.loggr.print(
                            self.MSG_BAD_LOT_NUM.format(
                                lot_num=input_str, lot_length=str(self.ensure_lot_len) + "-" if self.ensure_lot_len else "", lot_symbol="digit" if self.ensure_lot_digits else "letter"
                            )
                        )
                else:
                    break
            elif self.lot_num:
                # If empty entry then use the current non-empty lot number
                input_str = self.lot_num
                break
        return filt, is_barcode, input_str

    def enter_dut_connected(self) -> tuple[FilterResult, bool, str]:
        is_barcode = False
        while True:
            prompt = self.MSG_CONNECT_DUT.format(FIELD_DUT_NAME=self.FIELD_DUT_NAME, FIELD_DUT_ID=self.FIELD_DUT_ID)
            filt, is_barcode, input_str = self.filtered_input(prompt)
            if filt != FilterResult.FILTER_NONE:
                return filt, is_barcode, ""
            break
        return filt, is_barcode, input_str

    def enter_dut_disconnected(self) -> tuple[FilterResult, bool, str]:
        is_barcode = False
        while True:
            prompt = self.MSG_DISCONNECT_DUT.format(FIELD_DUT_NAME=self.FIELD_DUT_NAME, FIELD_DUT_ID=self.FIELD_DUT_ID)
            filt, is_barcode, input_str = self.filtered_input(prompt)
            if filt != FilterResult.FILTER_NONE:
                return filt, is_barcode, ""
            break
        return filt, is_barcode, input_str

    def enter_label_data(self) -> tuple[FilterResult, bool, str]:
        is_barcode = False
        while True:
            prompt = self.MSG_ENTER_DUT_ID.format(FIELD_DUT_ID=self.FIELD_DUT_ID)
            filt, is_barcode, input_str = self.filtered_input(prompt)
            if filt != FilterResult.FILTER_NONE:
                return filt, is_barcode, ""
            if not input_str:
                if self.loggr:
                    self.loggr.print(self.MSG_BAD_DUT_ID.format(FIELD_DUT_ID=self.FIELD_DUT_ID))
                continue
            break
        return filt, is_barcode, input_str

    def get_operator_info(self, operator_id: Optional[str] = None) -> str:
        if not operator_id:
            operator_id = self.operator_id
        return f"{self.FIELD_OPERATOR_ID} {operator_id}"

    def get_dut_info(self) -> str:
        return f"{self.FIELD_DUT_ID} {self.dut_id}"
