from __future__ import annotations

from enum import Enum
import re
from typing import Callable, Optional, TYPE_CHECKING

# "modpath" must be first of our modules
# pylint: disable=wrong-import-position
# ruff: noqa: E402
from pi_base.modpath import app_conf_dir
from pi_base.lib.tester.tester_common import TestError

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


class DataEntry:
    """Class to facilitate data entry for test."""

    ERR_OK = 0
    ERR_CANCEL = 1
    ERR_RETRY = 2
    ERR_BARCODE_FORMAT = 3
    ERR_UNKNOWN_PN = 4

    def __init__(self, fnc_input: Callable[[str], str], input_filter: FilterInterface, loggr: Loggr) -> None:
        """Constructor.

        @fnc_input is getter of test data (e.g. operator input() or some other automated data provider)
        @input_filter object should implement FilterInterface that checks for special commands in the input and returns "True" to stop test, "False" if data is not filtered and test can proceed.
        """
        # self.ensure_lot_len = 5
        # self.ensure_lot_digits = True
        self.ensure_lot_len = None
        self.ensure_lot_digits = False

        self.operator_field_name = "operator ID"
        self.operator_id = None

        self.dut_field_name = "device serial number"
        self.dut_id = None

        self.lot_field_name = "LOT Number"
        self.lot_num = None

        if not input_filter:
            raise ValueError("Please provide input_filter argument")
        self.input_filter = input_filter

        if not fnc_input:
            raise ValueError("Please provide fnc_input argument")
        self.fnc_input = fnc_input

        if not loggr:
            raise ValueError("Please provide loggr argument")
        self.loggr = loggr

        self.data_fmt = "{dut_pn}-v{dut_rev}-SN{dut_sn}"  # Format of DataEntry.data_entry() return when barcodes are scanned.

    def operator_signon(self) -> tuple[FilterResult, str]:
        """Request operator sign-on using provided fnc_input at instantiation.

        Returns: run,data - if run is not FilterResult.FILTER_NONE, data should be ignored and test loop stopped, if FilterResult.FILTER_NONE, continue.
        """
        operator_id = ""
        while True:
            input_str = self.fnc_input(f"Enter {self.operator_field_name}: ")
            operator_id = input_str.strip()
            # TODO: (when needed) Implement decoding of all possible QR label formats.
            if operator_id == "":
                if self.loggr:
                    self.loggr.print(f"  {self.operator_field_name} not recognized. Do not enter spaces.")
            else:
                break

        if self.loggr:
            self.loggr.debug(f'got user entry: "{operator_id}"')
        filt = self.input_filter.filter_input(self, operator_id, allow_signoff=False)
        if filt != FilterResult.FILTER_NONE:
            return filt, ""
        self.operator_id = operator_id
        return FilterResult.FILTER_NONE, operator_id

    def operator_lot_num(self) -> tuple[FilterResult, str]:
        """Requests the operator to input the LOT number.

        Returns:
            FilterResult, str : A valid 5 digit lot number
        """
        lot_num = ""
        filt = FilterResult.FILTER_NONE

        while True:
            if self.lot_num is None:
                message = "Enter the LOT number: "
            else:
                message = f"Enter the LOT number or press ENTER to use the current one ({self.lot_num}): "

            lot_num = self.fnc_input(message).strip()

            if len(lot_num) > 0:  # If value entered, parse the input
                # Check if any filters apply (sign-off, etc...)
                if (filt := self.input_filter.filter_input(self, lot_num, allow_signoff=True)) == FilterResult.FILTER_NONE:
                    try:  # If non apply then check if LOT number given is valid
                        # Check that the lot number is 5 digits
                        if self.ensure_lot_len and self.ensure_lot_len != len(lot_num):
                            raise ValueError
                        if self.ensure_lot_digits:
                            int(lot_num)  # Check that it is a number
                        self.lot_num = lot_num  # Given LOT number is valid, accept it
                    except:
                        if self.loggr:
                            self.loggr.print(
                                f'Given LOT number "{lot_num}" is not valid, please give a {str(self.ensure_lot_len) + "-" if self.ensure_lot_len else ""}{"digit" if self.ensure_lot_digits else "letter"} LOT number.'
                            )
                    else:
                        break
                else:
                    break
            elif self.lot_num:
                # If empty entry then use the current lot number
                lot_num = self.lot_num
                break
        return filt, lot_num

    def operator_info(self, operator_id: Optional[str] = None) -> str:
        if not operator_id:
            operator_id = self.operator_id
        return f"{self.operator_field_name} {operator_id}"

    @classmethod
    def barcode_pcba_pn_sn(cls, value: str, pn_prefix: str = "", sn_prefixes: Optional[list[str]] = None) -> tuple[int, str | None, str | None, str | None]:
        """Decode all possible PCBA QR label formats.

        Args:
            value (str): Input value

        Returns:
            number,str,str,str: Error code, PN, Rev, SN
        """
        #  Currently supported formats:
        # 'dd.ddddd-dd S/N:0002'
        # 'dd.ddddd SN 0123'
        if not sn_prefixes:
            sn_prefixes = ["SN", "S/N"]
        sn_prefix = "|".join(sn_prefixes)
        p = re.compile(f"^{pn_prefix}([0-9]+)[.]([0-9]+)(-[0-9]+)?[ ]*({sn_prefix})[:]?[ ]*([0-9]+)$")
        m = p.match(value.strip().upper())
        if not m:
            return DataEntry.ERR_BARCODE_FORMAT, None, None, None
        else:
            pn = m.group(1) + "." + m.group(2)
            rev = m.group(3).lstrip("-")
            sn = m.group(5)
            return DataEntry.ERR_OK, pn, rev, sn

    @classmethod
    def barcode_dut(cls, value: str, pn_refix: str, allowed_pns: Optional[list[str]] = None) -> tuple[int, None | str, None | str, None | str]:
        """Decode all possible QR label formats and ensure they match known hardware.

        Args:
            value (str): Input value

        Returns:
            number,str,str,str: Error code, PN, Rev, SN
        """
        returncode, pn, rev, sn = cls.barcode_pcba_pn_sn(value, pn_refix)
        if returncode != DataEntry.ERR_OK:
            return returncode, pn, rev, sn
        if allowed_pns and pn not in allowed_pns:
            return DataEntry.ERR_UNKNOWN_PN, pn, rev, sn
        return DataEntry.ERR_OK, pn, rev, sn

    @classmethod
    def barcode_serial_label_WIP(cls, value: str) -> tuple[int, None, None, str | None]:
        """Decode all possible QR label formats from serial label.

        Args:
            value (str): Input value

        Returns:
            number,str,str,str: Error code, PN, Rev, SN
        """
        # MAC address with colons
        p = re.compile("^([0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F])$")
        m = p.match(value.strip().upper())
        if not m:
            return DataEntry.ERR_BARCODE_FORMAT, None, None, None
        else:
            sn = m.group(1).lower()
            return DataEntry.ERR_OK, None, None, sn

    @classmethod
    def barcode_serial_pin_label(cls, value: str) -> tuple[int, None, None, None | str, None | str]:
        """Decode all possible QR label formats from serial label.

        Args:
            value (str): Input value

        Returns:
            number,str,str,str,str: Error code, PN, Rev, SN, PIN
        """
        # MAC address with colons
        p = re.compile("^([0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ([0-9][0-9][0-9][0-9])$")
        m = p.match(value.strip().upper())
        if not m:
            return DataEntry.ERR_BARCODE_FORMAT, None, None, None, None
        else:
            sn = m.group(1).lower()
            pin = m.group(2).lower()
            return DataEntry.ERR_OK, None, None, sn, pin

    def dut_connect_no_qr(self) -> tuple[FilterResult, Optional[str], bool]:
        """Request "enter" using provided fnc_input at instantiation.

        Returns: run,data,is_barcode - if run is not FilterResult.FILTER_NONE, data should be ignored and test loop stopped, if FilterResult.FILTER_NONE, continue and call .run(data).
        """
        while True:
            input_str = self.fnc_input("Connect device and hit [Enter]: ").strip()

            filt = self.input_filter.filter_input(self, input_str, allow_signoff=True)
            if filt != FilterResult.FILTER_NONE:
                return filt, None, False

            break
        if len(input_str) > 0 and self.loggr:
            self.loggr.debug(f'got user entry: "{input_str}", ignoring')
        return FilterResult.FILTER_NONE, None, False

    def dut_label_sn_pin(self, pre_message: Optional[str] = None) -> tuple[FilterResult, Optional[str], Optional[str], bool]:
        """Request barcode scan or SN/PIN and "enter" using provided fnc_input at instantiation.

        Returns: run,sn,pin,is_barcode - if run is not FilterResult.FILTER_NONE, sn and pin should be ignored and test loop stopped, if FilterResult.FILTER_NONE, use sn and pin andcontinue.
        """
        while True:
            input_str = self.fnc_input(((pre_message + " ") if pre_message else "") + "Scan barcode on device Serial Label, or enter \n  SERIAL NUMBER [space] PIN  \n and hit [Enter]: ").strip()

            filt = self.input_filter.filter_input(self, input_str, allow_signoff=True)
            if filt != FilterResult.FILTER_NONE:
                return filt, None, None, False

            returncode, pn, rev, sn, pin = DataEntry.barcode_serial_pin_label(input_str)
            if returncode == DataEntry.ERR_OK:
                # Got a barcode scan
                if self.loggr:
                    self.loggr.print(f"  Got serial label barcode: SN={sn}, PIN={pin}.")
                return FilterResult.FILTER_NONE, sn, pin, True

    def dut_connect_qr_WIP(self) -> tuple[FilterResult, Optional[str], bool]:
        """Request barcode scan or SN/MAC and "enter" using provided fnc_input at instantiation.

        Returns: run,data,is_barcode - if run is not FilterResult.FILTER_NONE, data should be ignored and test loop stopped, if FilterResult.FILTER_NONE, continue and call .run(data).
        """
        while True:
            input_str = self.fnc_input("Scan device serial label QR code or enter serial number and hit [Enter]: ").strip()

            filt = self.input_filter.filter_input(self, input_str, allow_signoff=True)
            if filt != FilterResult.FILTER_NONE:
                return filt, None, False

            returncode, pn, rev, sn = DataEntry.barcode_serial_label_WIP(input_str)
            if returncode == TestError.ERR_OK:
                # Got a barcode scan
                if self.loggr:
                    self.loggr.print(f"  Got serial label barcode: SN={sn}.")
                return FilterResult.FILTER_NONE, sn, True

            dut_id = input_str.split(" ")[0].lower()
            other = input_str.split(" ")[1:]
            if self.loggr:
                if len(other) or dut_id == "":
                    self.loggr.print(f'  {self.dut_field_name} "{input_str}" not recognized. Do not enter spaces.')
            else:
                break

        if self.loggr:
            self.loggr.debug(f'got user entry: "{dut_id}"')
        self.dut_id = dut_id
        return FilterResult.FILTER_NONE, dut_id, False

    def dut_pn_entry(self) -> tuple[FilterResult, None | str, bool]:  # TODO: (when needed) Clone and Modify to scan serial label and use at the end of test run
        """Request data using provided fnc_input at instantiation.

        Returns: run,data,is_barcode - if run is not FilterResult.FILTER_NONE, data should be ignored and test loop stopped, if FilterResult.FILTER_NONE, continue and call .run(data).
        """
        pn_refix = ""
        pns = [
            "10.00001",
            "10.00002",  # TODO: (when needed) Set accepted part numbers in config file (app_conf.yaml?? or use work order file somehow?)
        ]
        dut_id = ""
        while True:
            input_str = self.fnc_input(f"Scan/Enter {self.dut_field_name}: ").strip()

            filt = self.input_filter.filter_input(self, input_str, allow_signoff=True)
            if filt != FilterResult.FILTER_NONE:
                return filt, None, False

            returncode, pn, rev, sn = DataEntry.barcode_dut(input_str, pn_refix, pns)
            if returncode == TestError.ERR_OK:
                # Got a barcode scan
                dut_sn = None
                if self.loggr:
                    self.loggr.print(f"  Got board barcode: PN={pn_refix}{pn} Rev={rev} SN={sn}.")
                dut_pn, dut_rev, dut_sn = pn, rev, sn
                if dut_sn:
                    # For barcode scanner use, we have to delay
                    # Format sub-assembly ID from DUT SN
                    return (
                        FilterResult.FILTER_NONE,
                        self.data_fmt.format(
                            dut_pn=dut_pn,
                            dut_rev=dut_rev,
                            dut_sn=dut_sn,
                        ),
                        True,
                    )

            dut_id = input_str.split(" ")[0].lower()
            other = input_str.split(" ")[1:]
            if len(other) or dut_id == "":
                if self.loggr:
                    self.loggr.print(f'  {self.dut_field_name} "{input_str}" not recognized. Do not enter spaces.')
            else:
                break

        if self.loggr:
            self.loggr.debug(f'got user entry: "{dut_id}"')
        self.dut_id = dut_id
        return FilterResult.FILTER_NONE, dut_id, False

    def dut_info(self, dut_id: Optional[str] = None) -> str:
        if not dut_id:
            dut_id = self.dut_id
        return f"{self.dut_field_name} {dut_id}"
