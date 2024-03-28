#!/usr/bin/env python3

import os
from serial import Serial, SerialException

if os.name == "nt":
    import contextlib
    from serial import win32
    import ctypes
    import msvcrt

    WIN_MAX_COMPORT = 8

    class WinSerial(Serial):
        """Override of pyserial Serial class for non-posix (Windows).

        We only need fileno() method in this class, so we can make it work in pexpect / fdpexpect
        """

        def __init__(self, *args, **kwargs):
            self.is_open = False
            self._fd_port_handle = None
            self._orgTimeouts = None
            self._port_handle = None
            self._overlapped_read = None
            self._overlapped_write = None
            self._rts_state = None
            self._dtr_state = None

            super().__init__(*args, **kwargs)

        def open(self):
            """Open port with current settings. This may throw a SerialException if the port cannot be opened.

            Overriding Serial class method to extract _fd_port_handle for fileno() method.
            """
            if self._port is None or self.name is None:  # pyright: ignore[reportAttributeAccessIssue]
                raise SerialException("Port must be configured before it can be used.")
            if self.is_open:
                raise SerialException("Port is already open.")
            # the "\\.\COMx" format is required for devices other than COM1-COM8
            # not all versions of windows seem to support this properly
            # so that the first few ports are used with the DOS device name
            port = self.name
            try:
                if port.upper().startswith("COM") and int(port[3:]) > WIN_MAX_COMPORT:
                    port = "\\\\.\\" + port
            except ValueError:
                # for like COMnotanumber
                pass

            # A hackish way to get both self._fd_port_handle (which can be used in fdpexpect)
            # and a Windows handle for all existing Serial functionality
            self._fd_port_handle = os.open(
                port,
                os.O_RDWR
                # On Windows - keep file in binary mode (no CRLF translations).
                | getattr(os, "O_BINARY", 0)
                # On Linux - don't make the file controlling TTY for the process.
                | getattr(os, "O_NOCTTY", 0)
                | getattr(os, "O_NONBLOCK", 0),
            )
            self._port_handle = msvcrt.get_osfhandle(self._fd_port_handle)
            # See also win32file._get_osfhandle from the PyWin32 lib

            # self._port_handle = win32.CreateFile(
            #         port,
            #         win32.GENERIC_READ | win32.GENERIC_WRITE,
            #         0,  # exclusive access
            #         None,  # no security
            #         win32.OPEN_EXISTING,
            #         win32.FILE_ATTRIBUTE_NORMAL | win32.FILE_FLAG_OVERLAPPED,
            #         0)
            if self._port_handle == win32.INVALID_HANDLE_VALUE:  # pyright: ignore[reportAttributeAccessIssue]
                self._port_handle = None  # 'cause __del__ is called anyway
                raise SerialException(f"could not open port {self.portstr!r}: {ctypes.WinError()!r}")

            try:
                self._overlapped_read = win32.OVERLAPPED()
                self._overlapped_read.hEvent = win32.CreateEvent(None, 1, 0, None)
                self._overlapped_write = win32.OVERLAPPED()
                # ~ self._overlapped_write.hEvent = win32.CreateEvent(None, 1, 0, None)
                self._overlapped_write.hEvent = win32.CreateEvent(None, 0, 0, None)

                # Setup a 4k buffer
                win32.SetupComm(self._port_handle, 4096, 4096)

                # Save original timeout values:
                self._orgTimeouts = win32.COMMTIMEOUTS()
                win32.GetCommTimeouts(self._port_handle, ctypes.byref(self._orgTimeouts))

                self._reconfigure_port()  # pyright: ignore[reportAttributeAccessIssue]

                # Clear buffers:
                # Remove anything that was there
                win32.PurgeComm(self._port_handle, win32.PURGE_TXCLEAR | win32.PURGE_TXABORT | win32.PURGE_RXCLEAR | win32.PURGE_RXABORT)
            except:
                # try:
                with contextlib.suppress(Exception):
                    self._close()  # pyright: ignore[reportAttributeAccessIssue]
                # except:
                #     # ignore any exception when closing the port
                #     # also to keep original exception that happened when setting up
                #     pass
                self._port_handle = None
                raise
            else:
                self.is_open = True

        def fileno(self):
            return self._fd_port_handle

        def setDTRAndRTS(self, dtr, rts):
            comDCB = win32.DCB()
            win32.GetCommState(self._port_handle, ctypes.byref(comDCB))
            comDCB.fRtsControl = win32.RTS_CONTROL_ENABLE if rts else win32.RTS_CONTROL_DISABLE  # pyright: ignore[reportAttributeAccessIssue]
            comDCB.fDtrControl = win32.DTR_CONTROL_ENABLE if dtr else win32.DTR_CONTROL_DISABLE  # pyright: ignore[reportAttributeAccessIssue]
            win32.SetCommState(self._port_handle, ctypes.byref(comDCB))
            self._rts_state = rts
            self._dtr_state = dtr

    def GetSerial():
        return WinSerial

else:
    import fcntl  # pylint: disable=import-error
    import struct  # pylint: disable=import-error
    import termios  # pylint: disable=import-error

    class LinSerial(Serial):
        def __init__(self, *args, **kwargs):
            self.TIOCMSET = getattr(termios, "TIOCMSET", 0x5418)
            self.TIOCMGET = getattr(termios, "TIOCMGET", 0x5415)
            self.TIOCM_DTR = getattr(termios, "TIOCM_DTR", 0x002)
            self.TIOCM_RTS = getattr(termios, "TIOCM_RTS", 0x004)
            super().__init__(*args, **kwargs)

        def setDTRAndRTS(self, dtr, rts):
            status = struct.unpack("I", fcntl.ioctl(self.fileno(), self.TIOCMGET, struct.pack("I", 0)))[0]
            if dtr:
                status |= self.TIOCM_DTR
            else:
                status &= ~self.TIOCM_DTR
            if rts:
                status |= self.TIOCM_RTS
            else:
                status &= ~self.TIOCM_RTS
            # print(status)
            fcntl.ioctl(self.fileno(), self.TIOCMSET, struct.pack("I", status))

    def GetSerial():
        return LinSerial
