#!/usr/bin/env python3
"""Tester Control API definitions and common code."""

from __future__ import annotations

from enum import Enum
from typing import Callable, Optional

from .tester_common import TestError


class TesterControlType(Enum):
    NO_CONTROL = 0
    USBSERIAL_ON_TESTER = 3  # Tester is a dedicated board with USB-Serial on-board.


class TesterControlInterface:
    """Abstract interface for Tester Control implementation."""

    _device_id = None

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
        return TestError.ERR_OK

    def post(self) -> TestError:
        """In tester lifecycle: Perform post-test."""
        return TestError.ERR_OK

    def dut_start(self) -> TestError:
        """In tester lifecycle: Perform pre-dut."""
        return TestError.ERR_OK

    def dut_end(self) -> TestError:
        """In tester lifecycle: Perform post-dut."""
        return TestError.ERR_OK

    def get_versions(self) -> tuple[str, str, str, str]:
        """Get Tester versions info.

        Returns:
            Tuple of device_id, board_version, firmware_version, chip_ver
        """
        return (self.device_id or "N/A", "N/A", "N/A", "N/A")

    def info(self) -> str:
        """Get Tester Control driver info."""
        return ""

    @property
    def device_id(self) -> str | None:
        return self._device_id

    @device_id.setter
    def device_id(self, value: str) -> None:
        self._device_id = value

    def indicator_set(self, state: str) -> TestError:
        """Set tester state indicator."""
        return TestError.ERR_OK


class WIP_TesterIndicatorComponent:
    """Implementation of Tester Indicator Component.

    It encapsulates registering for indicator signals and dispatches the signals to the actual device.

    TODO: (when needed) Implement. With introduction of TesterControlInterface in TestScript, indicator functionality was disconnected as any specific hardware is not implemented.
    """

    def __init__(self, register_indicator_fnc: Optional[Callable[[Callable[[str], TestError], bool], None]] = None) -> None:
        self.register_indicator_fnc = register_indicator_fnc
        self.registered = False
        self.tester_indicator = None

    def indicator_set(self, state: str) -> TestError:
        if self.tester_indicator:
            return TestError.ERR_TESTER_DISCONNECTED if self.tester_indicator.indicator(state) else TestError.ERR_OK
        return TestError.ERR_OK

    def _register(self, do_register=True) -> None:
        if self.register_indicator_fnc and self.registered != do_register:
            self.register_indicator_fnc(self.indicator_set, do_register)
            self.registered = do_register

    def register(self) -> None:
        self._register(do_register=True)

    def unregister(self) -> None:
        self._register(do_register=False)


class TesterIndicator(TesterControlInterface):
    """Abstract interface for Tester Indicator implementation."""

    def states(self) -> list[str]:
        """Return list of possible states.

        Returns:
            List of possible states
        """
        return []

    def indicator(self, state: str) -> int:
        """Set indicator state / display information.

        Args:
            state: State to indicate, Should be one of self.states()

        Returns:
            Error code: 0=OK, 1=ERR_TESTER_DISCONNECTED
        """
        return 0


class TesterServo(TesterControlInterface):
    """Abstract interface for Tester Servo implementations."""

    def positions(self) -> list[str]:
        """Return list of possible positions.

        Returns:
            List of possible positions
        """
        return []

    def actuate(self, position: str) -> int:
        """Move servo to position.

        Args:
            position: Should be one of self.positions()

        Returns:
            Error code, 0=OK
        """
        return 0

    def state(self) -> str:
        """Return current servo position.

        Returns:
            Current position
        """
        return "unknown"


class TesterDetector(TesterControlInterface):
    """Abstract interface for Tester Detector implementations."""

    def expected(self) -> list[str]:
        """Return list of possible expected values.

        Returns:
            List of possible values that can be detected
        """
        return []

    def confirm(self, expected: str) -> bool:
        """Run detector and confirm its reading match the expected.

        Args:
            expected: Expected detector value

        Returns:
            True if detector confirms the expected value
        """
        return False

    def read(self) -> str | None:
        """Run detector and return its reading."""
        return None


class TesterLidServoManual(TesterServo):
    """Manual (operator performed) implementation of Lid TesterServo."""

    def __init__(self, loggr) -> None:
        """Constructor.

        Args:
            loggr: Logger object - should have .get_user_input() method

        Raises:
            ValueError: If loggr is not provided
            ValueError: If loggr does not have .get_user_input() method
        """
        if not loggr:
            raise ValueError("Please provide loggr argument")
        if not hasattr(loggr, "get_user_input"):
            raise ValueError('Please provide loggr argument with additional "get_user_input()" method')
        self.loggr = loggr
        self._state: str = "unknown"
        self._positions = ["open", "close"]

    def positions(self) -> list[str]:
        return self._positions

    def actuate(self, position: str):
        position = position.lower()
        if position not in self._positions:
            raise ValueError(f"Unrecognized actuator command {position}, expected one of {self.positions}")
        if self._state == position:
            return 0  # Already in position, no need to actuate

        self._state = position
        # message = 'Ensure the lid is OPEN' if position == 'open' else 'Ensure the lid is CLOSED'
        message = "OPEN the LID" if position == "open" else "CLOSE the LID"
        self.loggr.get_user_input(f"{message} and press Enter to continue:")
        return 0  # Success

    def state(self):
        return self._state


class TesterLEDDetectorManual(TesterDetector):
    """Manual (operator confirmed) implementation of LED TesterDetector."""

    def __init__(self, loggr):
        """Constructor.

        Args:
            loggr: Logger object - should have .get_user_yes_no_input() method

        Raises:
            ValueError: If loggr is not provided
            ValueError: If loggr does not have .get_user_yes_no_input() method
        """
        if not loggr:
            raise ValueError("Please provide loggr argument")
        if not hasattr(loggr, "get_user_yes_no_input"):
            raise ValueError('Please provide loggr argument with additional "get_user_yes_no_input()" method')
        self.loggr = loggr
        self.leds = ["red", "green", "blue"]

    def expected(self):
        return self.leds

    def confirm(self, expected):
        expected = expected.lower()
        if expected not in self.leds:
            raise ValueError(f"Unrecognized detector command {expected}, expected one of {self.leds}")
        message = f"Is the LED currently {expected.upper()} ([Y]es or [N]o):"
        return self.loggr.get_user_yes_no_input(message)


class TesterQRDetectorManual(TesterDetector):
    """Manual (operator entered) implementation of Tester QR Detector."""

    def __init__(self, logger):
        self.loggr = logger

    def expected(self):
        return None  # No fixed values are expected

    def confirm(self, expected):
        # expected = expected.lower()
        result = self.read()
        return result == expected

    def read(self):
        """Run detector and return its reading."""
        message = "Scan or Enter the QR code: "
        return self.loggr.get_user_input(message)
