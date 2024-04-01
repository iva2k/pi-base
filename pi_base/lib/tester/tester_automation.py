#!/usr/bin/env python3


from .tester_api import TesterControlInterface, TesterIndicator, TesterServo, TesterDetector


class TesterControlExampleStation(TesterControlInterface):
    """[Example] Implementation of TesterControlInterface for EXAMPLE station."""

    def __init__(self, loggr):
        """Constructor.

        Args:
            loggr (Loggr): Logger object
        """
        self.loggr = loggr


class TesterIndicatorExampleStation(TesterIndicator):
    """[Example] Implementation of TesterIndicator for EXAMPLE station."""

    def __init__(self, loggr):
        """Constructor.

        Args:
            loggr: Logger object
        """
        self.loggr = loggr
        self._state_values = {
            # Tester states:
            # TODO: [Example] Implement values to translate to indicator hardware, e.g. LED r,g,b colors:
            "SIGNON": (0, 0, 255),
            "IDLE": (0, 0, 0),
            "BUSY": (0, 0, 0),
            "PASS": (0, 255, 0),
            "FAIL": (255, 0, 0),
        }

    def _get_colors(self, state: str) -> "tuple[int, int, int]":
        if state.upper() not in self._state_values:
            raise ValueError(f'State "{state}" is not valid, should be one of {self.states()}')
        return self._state_values[state]

    def states(self) -> "list[str]":
        return list(self._state_values.keys())

    def indicator(self, state: str) -> int:
        r, g, b = self._get_colors(state)
        try:

            def ExampleIndicator(r, g, b):
                # TODO: [Example] Implement sending values to indicator hardware
                return True  # Success

            return 0 if ExampleIndicator(r, g, b) else 1  # 0=Success, 1=Hardware error / disconnected
        except Exception as err:
            self.loggr.error(f'Error "{err}". Looks like tester was disconnected.')
            return 1  # 1=Hardware error / disconnected -> TestError.ERR_TESTER_DISCONNECTED
        return 0  # 0=Success


class TesterLidServoAutomated(TesterServo):
    """[Example] Automated implementation of Lid TesterServo."""

    def __init__(self, loggr):
        """Constructor.

        Args:
            loggr: Logger object

        Raises:
            ValueError: If loggr is not provided
        """
        if not loggr:
            raise ValueError("Please provide loggr argument")
        self.loggr = loggr
        self._state: str = "unknown"
        self._positions = ["open", "close"]

    def positions(self) -> "list[str]":
        return self._positions

    def actuate(self, position: str) -> int:
        position = position.lower()
        if position not in self._positions:
            raise ValueError(f"Unrecognized actuator command {position}, expected one of {self.positions}")
        if self._state == position:
            self.loggr.debug(f'Example Lid Servo - already in position "{position}", not moving.')
            return 0  # 0=Success, Already in position, no need to actuate

        def ExampleLidServo(position):
            # TODO: [Example] Implement sending value to Lid servo hardware, wait for completion, confirm success.
            # return True  # Success
            return False  # Hardware failed / disconnected

        self.loggr.debug(f'Example Lid Servo - moving from position "{self._state}" to "{position}".')
        if ExampleLidServo(position):
            self._state = position
            return 0  # 0=Success
        else:
            return 1  # 1=Hardware error / disconnected

    def state(self) -> str:
        return self._state


class TesterLEDDetectorAutomated(TesterDetector):
    """[Example] Automated implementation of LED TesterDetector."""

    def __init__(self, loggr):
        """Constructor.

        Args:
            loggr: Logger object

        Raises:
            ValueError: If loggr is not provided
        """
        if not loggr:
            raise ValueError("Please provide loggr argument")
        self.loggr = loggr
        self.leds = ["red", "green", "blue"]
        self.last_detected = ""

    def expected(self):
        return self.leds

    def confirm(self, expected: str) -> bool:
        expected = expected.lower()
        if expected not in self.leds:
            raise ValueError(f"Unrecognized detector command {expected}, expected one of {self.leds}")

        def ExampleLEDDetector() -> str:
            # TODO: [Example] Implement Hardware detecting the LED color and comparing it to `expected`:
            # return 'red'
            # return 'green'
            # return 'blue'
            return ""  # Not detected

        self.last_detected = ExampleLEDDetector()
        self.loggr.debug(f'Example UI LED Detector - detected "{self.last_detected}"')
        return self.last_detected == expected
