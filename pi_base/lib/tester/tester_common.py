"""Common utilitiies for Tester building."""

from enum import Enum


class TestError(Enum):
    """TestScript Error Codes."""

    # _init_ = "value string"
    def __init__(self, value, string):
        self.id = value
        self.string = string

    # fmt: off
    # @formatter: off
    ERR_OK                             =    0, "The test passed without issues"
    ERR_FAIL                           =    1, "The test encountered a failure"
    ERR_TIMEOUT                        =    2, "The device response timed out"
    ERR_NOT_IMPLEMENTED                =    3, "Not implemented"
    ERR_FILE_OPEN                      =    4, "Error opening file"
    ERR_DEVICE_OPEN                    =    5, "Error opening device"
    ERR_PORT_NOT_FOUND                 =    6, "Was unable to find a device connected to a port"
    ERR_PORT_PERMISSION                =    7, "The port the device is connected to does not have the correct permissions"
    ERR_PORT_CLOSED                    =    8, "The port the device was connected to was closed"
    ERR_FILE_SAVE                      =    9, "Error saving file"
    ERR_NO_CONFIG                      =   10, "Configuration not set"
    ERR_SIGNOFF                        = 1997, "Operator signed off"
    ERR_OUTPUT_WRITE_OVERRIDE          = 1998, "TODO"
    ERR_ABORT                          = 1999, "The test was aborted"
    ERR_TEST_FAIL                      = 2000, "The test limit check failed"
    ERR_TESTER_NOT_CONFIGURED          = 3000, "The tester is not configured"
    ERR_TESTER_DISCONNECTED            = 3001, "The tester or part of its equipment was disconnected"
    ERR_DUT_DISCONNECTED               = 3002, "The Device Under Test was disconnected"
    ERR_SCRIPT_FAILURE                 = 3003, "A failure with the script occurred"
    ERR_TEST_INCOMPLETE                = 3004, "The current script line failed to complete"
    ERR_DUT_NOT_SUPPORTED              = 3005, "The Device Under Test is not compatible with requested operation"
    ERR_NO_PREVIOUS_DATA_COLLECTED     = 5000, "A check is trying to be ran on data that has not been collected"
    ERR_INVALID_COMMAND                = 6000, "Unknown Script command"
    ERR_INVALID_COMMAND_ARGUMENT       = 6001, "One or more of the script arguments is invalid"
    # @formatter: on
    # fmt: on

    def __str__(self):
        return self.string

    def __repr__(self):
        return self.name

    # @classmethod
    # def _missing_value_(cls, value):
    #     for member in cls:
    #         if member.string == value:
    #             return member
    #         if member.name == value:
    #             return member
    #     return None
