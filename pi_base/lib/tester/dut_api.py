#!/usr/bin/env python3
"""DUT Control API definitions and common code."""

from __future__ import annotations

from enum import Enum

# import sys

from pi_base.modpath import app_conf_dir

from .tester_common import TestError


app_conf_dir = app_conf_dir + ""


class DutControlType(Enum):
    NO_CONTROL = 0
    USBSERIAL_ON_DUT = 1  # USB-Serial chip is on device. Serial port is removed every time when DUT is disconnected.
    USBSERIAL_ADAPTER = 2  # USB-Serial chip is in USB-Serial Adapter (a.k.a. "Comms Adapter"). Serial port is attached to the host.


class DutControlInterface:
    """Abstract interface for DUT Control implementation."""

    _device_id = ""

    def close(self) -> None:
        """Close connections."""

    def abort(self) -> None:
        """Aborts running operation."""

    def reset_info(self) -> None:
        """Reset device info for new run."""

    def soak(self, delay_s) -> None:
        """Soak - pump streams of data."""

    def pre(self) -> TestError:
        """In tester lifecycle: Perform pre-test."""
        return TestError.ERR_NOT_IMPLEMENTED

    def post(self) -> TestError:
        """In tester lifecycle: Perform post-test."""
        return TestError.ERR_NOT_IMPLEMENTED

    def dut_start(self) -> TestError:
        """In tester lifecycle: Perform pre-dut."""
        return TestError.ERR_NOT_IMPLEMENTED

    def dut_end(self) -> TestError:
        """In tester lifecycle: Perform post-dut."""
        return TestError.ERR_NOT_IMPLEMENTED

    def get_versions(self) -> tuple[str, str, str, str]:
        """Get DUT versions info.

        Returns:
            Tuple of device_id, board_version, firmware_version, chip_ver
        """
        return (self.device_id or "N/A", "N/A", "N/A", "N/A")

    def info(self) -> str:
        """Get DUT Control driver info."""
        raise NotImplementedError

    @property
    def device_id(self) -> str:
        return self._device_id

    @device_id.setter
    def device_id(self, value: str) -> None:
        self._device_id = value


class DutControlNone(DutControlInterface):
    """Dummy DUT Control implementation."""

    def __init__(self) -> None:
        pass

    def pre(self) -> TestError:
        return TestError.ERR_OK

    def post(self) -> TestError:
        return TestError.ERR_OK

    def dut_start(self) -> TestError:
        return TestError.ERR_OK

    def dut_end(self) -> TestError:
        return TestError.ERR_OK

    def info(self) -> str:
        raise NotImplementedError
