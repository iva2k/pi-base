#!/usr/bin/env python3

"""Print labels from Python software on Zebra ZT411 (203dpi) and ZT610 printers (both using ZPL language).

CUPS was supposed to be supporting ZPL, but recent development is on a path to remove PPD and drivers support
and drop non-IPP printers. Investing into CUPS on that path makes very little sense.

Current CUPS-based alternative to PPD/driver use ippeveprinter that might be workable, except on any Debian Linux
it had lost critical file `ippeveps``, so printing PDF does not seem possible. Building from sources could be a
possibility to bring ippeveps back, but eventual success is highly questionable without PPD support.

Further, CUPS creator, Michael R Sweet had left Apple & CUPS project (https://www.phoronix.com/news/CUPS-Lead-Developer-Leaves-APPL)
and now consults as CTO of Lakeside Robotics Corp. (his wife is CEO).

- https://lakesiderobotics.ca/printing.html
- https://www.linkedin.com/company/lakeside-robotics-ca/
- https://www.linkedin.com/in/michael-sweet-90848120/

He recently developed a promising package LPrint that supports ZPL / Zebra label printers:

- https://www.msweet.org/lprint/
- https://github.com/michaelrsweet/lprint

The package is in Debian / Ubuntu repos, and installs on RPi.

MacOS - LPrint TBD.

Latest trend is to use IPP / everywhere / driverless:

```
ippeveprinter -D file:///Users/Shared/Print/ -c /usr/libexec/cups/command/ippeveps -F application/pdf  -P /private/etc/cups/ppd/Direct_PDF.ppd Qwe
ippeveprinter -D printer_uri -c /usr/libexec/cups/command/ippeveps -F application/pdf  -P ppd_file printer_name
ippeveprinter -D printer_uri -c /usr/libexec/cups/command/ippeveps -F application/pdf,application/postscript,image/jpeg,image/pwg-raster,image/urf \
-P ppd_file -r _print,_universal -i IMAGEPNG -l LOCATION printer_name
```

Investigated ippeveprinter and ZPL... Where is 'ippeveps' command file (needed for ippeventprinter to work with ZPL)?
- source exists in apple repo https://github.com/apple/cups/blob/master/tools/ippeveps.c
- source exists in OpenPrinting repo https://github.com/OpenPrinting/cups/blob/master/tools/ippeveps.c
- Debian packaging organized differently
- ippeveps files are missing in Debian packages (ippeveprint is in cups-ipp-utils package)
- in Fedora packaging (cups-printerapp and ps-printer-app packages) is also organized differently, file might be present, but can't cherry-pick one package, need to use them all
"""

# We're not going after extreme performance here
# pylint: disable=logging-fstring-interpolation


import argparse
import logging
import os
import platform
import subprocess
import sys
from collections.abc import Mapping
from abc import ABC, abstractmethod
from typing import Any, Optional

from .app_utils import AtDict
from .os_utils import which

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != "__main__" else None)
logger.setLevel(logging.DEBUG)

# conn = cups.Connection()
# printers = conn.getPrinters()
# printer_name = printers.keys()[0]
# conn.printFile(printer_name,'/home/pi/Desktop/a.pdf',"",{})


def eprint(*args: object, **kwargs: Mapping[str, Any]) -> None:
    kwargs1 = {"file": sys.stderr, **kwargs}
    print(*args, **kwargs1)


def shell(cmd: "list[str]") -> "tuple[int, str, str]":
    """Shell command utility.

    Args:
        cmd: command and arguments list

    Returns:
        Tuple of returncode, stdout, stderr from the command
    """
    # logger.debug(f'Running command "{cmd}"')
    output = subprocess.run(cmd, text=True, capture_output=True, check=False)
    logger.debug(f'Shell command: "{output}"')
    return output.returncode, output.stdout, output.stderr


def is_ext(ext: str, filename: str) -> bool:
    file_path, file_ext = os.path.splitext(filename)
    return ext.lower() == file_ext.lower()


def convert_to_png(file: str, outfile: Optional[str] = None) -> str:
    if not outfile:
        outfile = file + ".png"
    magick = which(["magick", "C:/Program Files/ImageMagick-7.1.0-Q16/magick.exe"])
    if not magick or not os.access(magick, os.X_OK):
        raise FileNotFoundError('"magick" command is not found. Is ImageMagick installed and added to PATH?')
    logger.debug(f"Converting {file} to {outfile} ...")
    out = subprocess.check_output(
        # TODO: (when needed) Implement scaling to dpi etc.: convert -density 320 "$_input_pdf" -scale 926x1463 -type grayscale -depth 8 -crop 812x1218+52+166 "$_output_png"
        f'"{magick}" convert {file} {outfile}',
        shell=True,
        text=True,
    )
    logger.debug(f"{out}")
    if not os.path.isfile(outfile):
        raise ChildProcessError(f"Failed converting {file}, result file {outfile} not created.")
    return outfile


class PrintError(Exception):
    pass


class PrinterInterface(ABC):
    """Abstract interface for Printer implementations."""

    @abstractmethod
    def install(self) -> int:
        """Install required dependencies on the OS."""
        return -1

    @abstractmethod
    def uninstall(self) -> int:
        """Uninstall all OS components that self.install() installed."""
        return -1

    @abstractmethod
    def get_devices(self) -> "dict[str, dict[str, str]]":
        """Get list of available devices.

        Based on pycups: @see http://nagyak.eastron.hu/doc/system-config-printer-libs-1.2.4/pycups-1.9.51/html/
        # 'pusb://Zebra%20Technologies/ZTC%20ZT411-300dpi%20ZPL?serial=99J204300180': {'device-class': 'direct', 'device-info': 'Zebra Technologies ZTC ZT411-300dpi ZPL', 'device-make-and-model': 'Zebra Technologies ZTC ZT411-300dpi ZPL', 'device-id': 'SERN:99J204300180;MANUFACTURER:Zebra Technologies ;COMMAND SET:ZPL;MODEL:ZTC ZT411-300dpi ZPL;CLASS:PRINTER;OPTIONS:XML;', 'device-location': ''}
        # 'https': {'device-class': 'network', 'device-info': 'Internet Printing Protocol (https)', 'device-make-and-model': 'Unknown', 'device-id': '', 'device-location': ''}

        Returns:
            Dict indexed by "device-uri", of dicts representing devices, indexed by attribute, such as "device-id", "device-info"

        """
        return {}

    @abstractmethod
    def get_printers(self) -> "dict[str, dict[str, str]]":
        """Get list of added printers.

        Based on pycups: @see http://nagyak.eastron.hu/doc/system-config-printer-libs-1.2.4/pycups-1.9.51/html/

        Returns:
            Dict indexed by name, of dicts representing queues, indexed by attribute, such as "device-uri", "printer-make-and-model".
            # {'ZT411': {'printer-is-shared': False, 'printer-state': 3, 'printer-state-message': '', 'printer-state-reasons': ['none'], 'printer-type': 2134092, 'printer-uri-supported': 'ipp://localhost/printers/ZT411', 'printer-location': 'Travelling Zebra', 'printer-info': 'ZT411',
            # 'device-uri': 'pusb://Zebra%20Technologies/ZTC%20ZT411-300dpi%20ZPL?serial=99J204300180&Opt=BXVG',
            # 'printer-make-and-model': 'Zebra ZT411-300dpi Driver (peninsula-group.com)' }}
        """
        return {}

    @abstractmethod
    def print_test(self, printer_name: str, options: "Optional[dict[str, str]]" = None) -> int:
        """Print test page."""
        return -1

    @abstractmethod
    def print_file(self, printer_name: str, file_name: str, doc_name: str = "", options: "Optional[dict[str, str]]" = None) -> int:
        """Print given file."""
        return -1

    def autoadd_printers(self, options: "Optional[dict[str, str]]" = None) -> "tuple[int, dict[str, dict[str, str]]]":
        """Add all found compatible printers."""
        return (-1, {})

    def autoadd_zebra(self) -> int:
        """Attempts to add the Zebra ZT411 printer."""
        return -1

    @abstractmethod
    def add_printer(self, printer_name: str, printer_uri: str, ppd_file: str, options: "Optional[dict[str, str]]" = None) -> int:
        """Add given printer."""
        return -1

    @abstractmethod
    def delete_printer(self, printer_name: str, options: "Optional[dict[str, str]]" = None) -> int:
        """Delete previously added printer."""
        return -1


class CupsPrinter(PrinterInterface):
    """Printer using CUPS.

    Other commands:
      * cupsctl --debug-logging
      * cupsctl --no-debug-logging
    """

    def __init__(self) -> None:
        # `pip3 install pycups``
        import cups  # pylint: disable=import-outside-toplevel

        self.cups = cups
        self.conn = cups.Connection()

        # ippeveprinter --version
        # RPi:
        # CUPS v2.3.3op2
        # Ubintu 22 LTS:
        # CUPS v2.4.1
        # TODO: (when needed) Check if OS package is installed
        # TODO: (when needed) Implement installing OS package

    def install(self) -> int:
        returncode, _, _ = shell(["sudo", "apt-get", "install", "cups"])
        if returncode:
            returncode, _, _ = shell(["sudo", "usermod", "-a", "-G", "lpadmin", "pi"])
        if returncode:
            returncode, _, _ = shell(["pip", "install", "pycups"])
        return 0 if returncode == 1 else -1

    def uninstall(self) -> int:
        returncode, _, _ = shell(["sudo", "apt-get", "--purge", "remove", "cups"])
        returncode2, _, _ = shell(["pip", "uninstall", "pycups"])
        return 0 if returncode == 1 and returncode2 == 1 else 1

    def get_devices(self) -> "dict[str, dict[str, str]]":
        # .getDevices() takes a bit of time. Is there a timeout param?
        devices: "dict[str, dict[str, str]]" = self.conn.getDevices() if self.conn else {}
        # 'pusb://Zebra%20Technologies/ZTC%20ZT411-300dpi%20ZPL?serial=99J204300180': {'device-class': 'direct', 'device-info': 'Zebra Technologies ZTC ZT411-300dpi ZPL', 'device-make-and-model': 'Zebra Technologies ZTC ZT411-300dpi ZPL', 'device-id': 'SERN:99J204300180;MANUFACTURER:Zebra Technologies ;COMMAND SET:ZPL;MODEL:ZTC ZT411-300dpi ZPL;CLASS:PRINTER;OPTIONS:XML;', 'device-location': ''}
        # 'https': {'device-class': 'network', 'device-info': 'Internet Printing Protocol (https)', 'device-make-and-model': 'Unknown', 'device-id': '', 'device-location': ''}
        return devices

    def get_printers(self) -> "dict[str, dict[str,str]]":
        printers: "dict[str, dict[str, str]]" = self.conn.getPrinters() if self.conn else {}
        # {'ZT411': {'printer-is-shared': False, 'printer-state': 3, 'printer-state-message': '', 'printer-state-reasons': ['none'], 'printer-type': 2134092, 'printer-uri-supported': 'ipp://localhost/printers/ZT411', 'printer-location': 'Travelling Zebra', 'printer-info': 'ZT411',
        # 'device-uri': 'pusb://Zebra%20Technologies/ZTC%20ZT411-300dpi%20ZPL?serial=99J204300180&Opt=BXVG',
        # 'printer-make-and-model': 'Zebra ZT411-300dpi Driver (peninsula-group.com)' }}
        return printers

    def print_test(self, printer_name: str, options: "Optional[dict[str, str]]" = None) -> int:
        file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "printer-test-label.png"))
        return self.print_file(printer_name, file_path, options=options)

    def print_file(self, printer_name: str, file_name: str, doc_name: str = "", options: "Optional[dict[str, str]]" = None) -> int:
        returncode = -1
        if os.path.isfile(file_name):
            options = options if options else {}
            # SVG files don't print on Zebra with Peninsula Group driver (missing CUPS filter?)
            # https://unix.stackexchange.com/questions/372379/what-file-formats-does-cups-support
            if os.path.splitext(file_name)[1].lower() == ".svg":
                logger.warning(f'Got "{file_name}" file to print which has SVG extension. SVG files are (typically) not supported by label printers. Please use PDF. Will try anyway...')

            # TODO: (when needed) self.cups.setUser('pi')
            if printer_name in self.get_printers():
                returncode = self.conn.printFile(printer_name, file_name, doc_name, options)
            else:
                logger.warning(f'Unrecognized printer name given "{printer_name}"')
        else:
            logger.warning(f'File "{file_name}" does not exit.')
        return returncode

    def delete_printer(self, printer_name: str, options: "Optional[dict[str, str]]" = None) -> int:
        cmd = ["lpadmin", "-x", printer_name]
        res, out, err = shell(cmd)
        return res

    def autoadd_zebra(self, default_name: str = "ZT411") -> int:
        """Attempts to automatically detect and add the Zebra ZT411 under the name 'ZT411'."""
        returncode = -1
        devices = self.get_devices()
        for device in devices:
            if "zebra" in device.lower():
                uri = device
                default_options = {
                    "PageSize": "w144h72",
                    "MediaSize": "w144h72",
                    # TODO: (when needed): 'Resolution'        : '302dpi', # Zebra ZT411 has different resolutions (print head options). Ours is 302dpi.
                    "Resolution": "203dpi",
                    "zeMediaTracking": "Web",
                    "MediaType": "Thermal",
                    "Darkness": "30",
                    "zePrintRate": "1",
                    "zeLabelTop": "200",
                    "zePrintMode": "Applicator",
                    "zeTearOffPosition": "1000",
                    "zeErrorReprint": "Saved",
                }
                options = []
                for opt, val in default_options.items():
                    options.append("-o")
                    options.append(f"{opt}={val}")
                returncode, _, _ = shell(["sudo", "lpadmin", "-p", default_name, "-E", "-v", uri, "-m", "drv:///sample.drv/zebra.ppd"] + options)
                break

        return returncode

    def add_printer(self, printer_name: str, printer_uri: str, ppd_file: str, options: "Optional[dict[str, str]]" = None) -> int:
        """Install a printer.

        CUPS: @see https://www.cups.org/doc/admin.html
        Currently broken.
        PPD files are on deprecation notice, will be removed in CUPS 3.0, release imminent.

        Args:
            printer_name: Name of the printer
            printer_uri: URI of the printer
            ppd_file: Path to ppd file to use
            options: Optional arguments (description, location). Defaults to None.

        Returns:
            int: Error code
        """
        cmd = [
            "lpadmin",
            "-p",
            printer_name,
            "-E",  # Enable printer
            "-v",
            printer_uri,
            # TODO: (when needed) # "-m", ppd_file,
            "-m",
            "everywhere",  # TODO: (when needed) ppd file created in /etc/cups/ppd/,
            "-o",
            "printer-is-shared=false",
        ]
        if options and "description" in options:
            cmd += ["-D", options["description"]]
        if options and "location" in options:
            cmd += ["-L", options["location"]]
        res, out, err = shell(cmd)
        # TODO: (when needed) lpadmin: Printer drivers are deprecated and will stop working in a future version of CUPS.
        # lpadmin: System V interface scripts are no longer supported for security reasons. -> don't use '-i' options
        if res:
            raise OSError(res, err)

        # Enable the printer
        res, out, err = shell(["cupsenable", printer_name])

        # Set the printer as the default
        res, out, err = shell(["lpadmin", "-d", printer_name])

        return res

    # to install CUPS on Linux:
    # sudo apt-get install cups -y.
    # sudo systemctl start cups.
    # sudo systemctl enable cups.
    # sudo nano /etc/cups/cupsd.conf.
    # sudo systemctl restart cups.
    # # /etc/cups/cupsd.conf
    # # sudo usermod -aG lpadmin username

    # CUPS admin via web interface
    # http://localhost:631


class LprintPrinter(PrinterInterface):
    """Printer using LPrint.

    # Investigated lprint and ZPL

    https://www.msweet.org/lprint/lprint.html

    - It is promised to be replacement for PPD drivers now and when CUPS 3.0 removes PPD drivers support.
    - Realities are glum - segfaults and not working out of the box with latest v1.2.0 (in snap).
    - snap has its own issues, e.g. `sudo lprint ...` does not work ($PATH for root?) - workaround `sudo /snap/bin/lprint ...`
    - server crashes and has tons of bugs
    - Web interface: was able to add a printer, but never printed a test page.
    - No test page in CLI (only WEb)

    ## Commands:

        - lprint drivers
        - lprint devices
        - lprint add -d ZT411 -v "socket://192.168.1.20" -m zpl_2inch-203dpi-tt
        - lprint add -d printer_name -v printer_uri -m zpl_2inch-203dpi-tt

    Example Linux service (watches directory for new files and prints them) https://gist.github.com/dreamcat4/4240184f9299b211d2106bfef2d55518

    Installation:
    # sudo apt-get install lprint ;# gets v1.0 on Debian/Ubuntu/RPi
    sudo apt-get install snapd
    Note: snap uncovers a problem with /etc/ld.so.preload file on RPi - comment out the line in  /etc/ld.so.preload. Offending package is
    raspi-copies-and-fills v0.13. `sudo apt-get remove --purge raspi-copies-and-fills`
    sudo snap install core
    sudo snap install lprint ;# gets v1.2.0
    sudo snap connect lprint:raw-usb
    #sudo snap set lprint auth-service=other
    #sudo snap set lprint server-port=32101
    sudo snap start lprint.lprint-server
    open http://rpi.local:32101
    sudo snap stop lprint.lprint-server
    (resides in /snap/bin/lprint)
    v1.2.0 vs apt-get v1.0

    Base Class:
        PrinterInterface
    """

    def __init__(self) -> None:
        # lprint --version
        # RPi:
        # lprint v1.0
        # Ubintu 22 LTS:
        # lprint v1.0
        # TODO: (when needed) Check if OS package is installed
        pass

    def install(self) -> int:
        # TODO: (when needed) Improve installing OS packages - live stdio/stderr, handle errors (and recover/continue)
        for cmd in [
            ["sudo", "apt-get", "update"],
            ["sudo", "apt-get", "install", "-y", "snapd"],
            ["sudo", "snap", "install", "core"],
            ["sudo", "snap", "install", "lprint"],
            ["sudo", "snap", "connect", "lprint:raw-usb"],  # Must for USB-connected printer
            # ["sudo", "snap",  "set", "lprint", "auth-service=cups",],
            [
                "sudo",
                "snap",
                "set",
                "lprint",
                "server-port=32101",
            ],
            ["sudo", "snap", "start", "lprint.lprint-server"],
        ]:
            logger.debug(f"cmd={cmd}")
            res, out, err = shell(cmd)
            print(out)
            eprint(err)
        return True

    def uninstall(self) -> int:
        # TODO: (when needed) Implement
        return -1

    def web_off(self) -> int:
        # TODO: (when needed) Implement
        # "sudo snap start lprint.lprint-server",
        return -1

    def web_on(self) -> int:
        # TODO: (when needed) Implement
        # "sudo snap stop?? lprint.lprint-server",
        return -1
        # lprint server -o server-name=HOSTNAME -o server-port=NNN -o auth-service=cups
        # `-o admin-group=GROUP`

    def get_devices(self) -> "dict[str, dict[str, str]]":
        cmd = ["lprint", "devices"]
        res, out, err = shell(cmd)
        lines = out.split("\n")
        devices: "dict[str, dict[str, str]]" = {}
        for line in lines:
            # TODO: (when needed) implement format parsing, normalize to same format as CupsPrinter
            # 'pusb://Zebra%20Technologies/ZTC%20ZT411-300dpi%20ZPL?serial=99J204300180': {'device-class': 'direct', 'device-info': 'Zebra Technologies ZTC ZT411-300dpi ZPL', 'device-make-and-model': 'Zebra Technologies ZTC ZT411-300dpi ZPL', 'device-id': 'SERN:99J204300180;MANUFACTURER:Zebra Technologies ;COMMAND SET:ZPL;MODEL:ZTC ZT411-300dpi ZPL;CLASS:PRINTER;OPTIONS:XML;', 'device-location': ''}
            # 'https': {'device-class': 'network', 'device-info': 'Internet Printing Protocol (https)', 'device-make-and-model': 'Unknown', 'device-id': '', 'device-location': ''}
            devices[line] = {"device-id": ""}
        return devices

    def get_printers(self) -> "dict[str, dict[str, str]]":
        cmd = ["lprint", "printers"]
        res, out, err = shell(cmd)
        lines = out.split("\n")
        printers: "dict[str, dict[str, str]]" = {}
        for line in lines:
            # TODO: (when needed) implement format parsing, normalize to the same format as CupsPrinter
            printers[line] = {"device-id": "", "printer-make-and-model": ""}
        return printers
        # printers = [self.parse_printer(p) for p in out.split("\n")]
        # for name, printer in printers.items():
        #     self.loggr.info(name, printer["device-uri"])
        # return printers

    def print_test(self, printer_name: str, options: "Optional[dict[str, str]]" = None) -> int:
        options = options if options else {}
        # TODO: (when needed) Implement
        return -1

    def print_file(self, printer_name: str, file_name: str, doc_name: str = "", options: "Optional[dict[str, str]]" = None) -> int:
        # TODO: (when needed) Implement lprint options for printing
        # Example for 4x6inch label
        #  lprint -o media-top-offset=3.5mm -o print-color-mode=bi-level -o media-tracking=continuous -o media-type=labels-continuous \
        #    -o media=oe_4x6-label_4x6in -o orientation-requested=portrait "$_output_png"
        options = options if options else {}

        file_to_print = file_name
        if is_ext(".pdf", file_name):
            file_to_print = convert_to_png(file_name)

        cmd = ["lprint", "-d", printer_name, file_to_print]
        # TODO: (when needed) Explore available options: `lprint options -d PRINTER`
        res, out, err = shell(cmd)
        return res

    def print_file_lp(self, printer_name: str, file_name: str) -> int:
        # TODO: (when needed) check if it works:
        # Without CUPS, use lp:
        try:
            lp = which("lp")
            if not lp:
                raise FileNotFoundError
            subprocess.run([lp, "-d", printer_name, file_name], check=True)
            # subprocess.run([lpr, "--P", printer_name, file_name], check=True)
        except subprocess.CalledProcessError as e:
            print(f'Error running "lp": {e}')
            return e.returncode
        except FileNotFoundError as e:
            print('"lp" command not found.')
            return e.errno
        return 0

    def delete_printer(self, printer_name: str, options: "Optional[dict[str, str]]" = None) -> int:
        # TODO: (when needed) check if it works:
        cmd = ["lprint", "delete", "-d", printer_name]
        res, out, err = shell(cmd)
        return res

    def autoadd_printers(self, options: "Optional[dict[str, str]]" = None) -> "tuple[int, dict[str, dict[str, str]]]":
        # had_printers = self.get_printers()
        cmd = [
            "lprint",
            "autoadd",
            # "-d", printer_name,
            # "-v", printer_uri,
            # "-m", ppd_file,  # from "lprint drives", e.g. "zpl_2inch-203dpi-tt"
            # "-o", "printer-is-shared=false",
        ]
        # if 'description' in options:
        #     cmd += ["-o", f'??printer-description={options["description"]}']
        if options and "location" in options:
            cmd += ["-o", f'printer-location={options["location"]}']
        res, out, err = shell(cmd)
        if res:
            raise OSError(res, err)

        # Enable the printer?

        # Set the printer as the default?

        printers = self.get_printers()
        # TODO: (when needed) printers -= had_printers
        return res, printers

    def add_printer(self, printer_name: str, printer_uri: str, ppd_file: str, options: "Optional[dict[str, str]]" = None) -> int:
        """Install a printer.

        Args:
            printer_name: Name of the printer
            printer_uri: URI of the printer
            ppd_file: Path to ppd file to use, one of LPrint -m files (see "lprint drivers"), e.g. zpl_2inch-203dpi-tt
            options: Optional arguments (description, location). Defaults to None.

        Returns:
            int: Error code
        """
        # if printer_uri == 'auto':
        #     res, printers = self.autoadd_printers(options)
        #     # TODO: (when needed) report all added printers
        #     return res

        # lprint add -d ZT411 -v "socket://192.168.1.20" -m zpl_2inch-203dpi-tt
        # lprint add -d printer_name -v printer_uri -m
        # man lprint-add
        cmd = [
            "lprint",
            "add",
            "-d",
            printer_name,
            "-v",
            printer_uri,
            "-m",
            ppd_file,  # from "lprint drives", e.g. "zpl_2inch-203dpi-tt"
            # "-o", "printer-is-shared=false",
        ]
        # if 'description' in options:
        #     cmd += ["-o", f'??printer-description={options["description"]}']
        if options and "location" in options:
            cmd += ["-o", f'printer-location={options["location"]}']
        res, out, err = shell(cmd)
        if res:
            raise OSError(res, err)

        # Enable the printer?

        # Set the printer as the default?

        return res


# on Windows:
def winPrint1() -> None:
    # `pip3 install pywin32`
    from win32 import win32print  # pylint: disable=import-outside-toplevel

    printer_name = win32print.GetDefaultPrinter()
    if not printer_name:
        raise ValueError("No default printer found")

    file_name = "document.pdf"
    printer_handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(printer_handle, 1, ("test of raw data", None, "RAW"))  # pyright: ignore[reportArgumentType]
        try:
            win32print.StartPagePrinter(printer_handle)
            with open(file_name, "rb") as f:
                win32print.WritePrinter(printer_handle, f.read())
            win32print.EndPagePrinter(printer_handle)
        finally:
            win32print.EndDocPrinter(printer_handle)
    except Exception as e:
        print(f'Error printing file "{file_name}": {e}')
    finally:
        win32print.ClosePrinter(printer_handle)
    printer_handle = None


def winPrint2() -> None:
    from win32 import win32print  # pylint: disable=import-outside-toplevel
    import win32ui  # pylint: disable=import-outside-toplevel

    printer_name = win32print.GetDefaultPrinter()
    if not printer_name:
        raise ValueError("No default printer found")

    # Example of looking up a printer by name:
    # drivers = win32print.EnumPrinterDrivers(None, None, 2)
    # hPrinter = win32print.OpenPrinter(printer_name)
    # printer_info = win32print.GetPrinter(hPrinter, 2)
    # for driver in drivers:
    #     if driver["Name"] == printer_info["pDriverName"]:
    #         printer_driver = driver

    hprinter = win32print.OpenPrinter(printer_name)
    if not hprinter:
        raise ValueError("Unable to open printer")
    dc = win32ui.CreateDC()
    if dc:
        dc.CreatePrinterDC(printer_name)
        PHYSICALWIDTH = 110
        PHYSICALHEIGHT = 111
        printer_size = dc.GetDeviceCaps(PHYSICALWIDTH), dc.GetDeviceCaps(PHYSICALHEIGHT)
        dc.StartDoc("Label Document")
        dc.StartPage()
        fontdata = {"height": 80}
        font = win32ui.CreateFont(fontdata)
        dc.SelectObject(font)
        dc.TextOut(0, 10, "Sample: 3174")
        dc.TextOut(0, 90, "Date:26/02/21")
        dc.TextOut(0, 180, "sample_name")
        # See exmple of printing .bmp file: https://gist.github.com/buptxge/2fc61a3f914645cf8ae2c9a258ca06c9
        dc.EndPage()
        dc.EndDoc()
        dc.DeleteDC()
        win32print.ClosePrinter(hprinter)


def maybe_get_printer_handler(driver_type: str, *args: object, **kwargs: Mapping[str, Any]) -> Optional[PrinterInterface]:
    inst: Optional[PrinterInterface] = None
    if driver_type.lower() == "cups":
        inst = CupsPrinter(*args, **kwargs)
    if driver_type.lower() == "lprint":
        inst = LprintPrinter(*args, **kwargs)
    # TODO: (when needed): Implement Windows printer class 'WinPrinter'
    # if driver_type.lower() == 'win':
    #     inst = WinPrinter(*args, **kwargs)
    return inst


def OsPrinter(*args: object, **kwargs: Mapping[str, Any]) -> PrinterInterface:
    if os.name == "nt":  # Windows
        driver_type = "Win"
        # driver_type = 'LPrint'  # for debugging LPrint piping on Windows. Can try LPrint on Windows some day.
    elif platform.system() == "Darwin" or os.name == "posix":  # MacOS
        driver_type = "CUPS"
    else:
        raise NotImplementedError(f"Unsupported OS {os.name}")

    printer = maybe_get_printer_handler(driver_type)
    if not printer:
        raise ValueError(f"Error getting printer class for {driver_type}")
    return printer


def cmd_install(options: "Optional[dict[str, str]]" = None) -> int:
    printer = OsPrinter()
    return printer.install()


def cmd_uninstall(options: "Optional[dict[str, str]]" = None) -> int:
    printer = OsPrinter()
    return printer.uninstall()


def cmd_devices(options: "Optional[dict[str, str]]" = None) -> int:
    printer = OsPrinter()
    devices = printer.get_devices()
    for device in devices:
        print(device, devices[device]["device-id"])
        # 'pusb://Zebra%20Technologies/ZTC%20ZT411-300dpi%20ZPL?serial=99J204300180': {'device-class': 'direct', 'device-info': 'Zebra Technologies ZTC ZT411-300dpi ZPL', 'device-make-and-model': 'Zebra Technologies ZTC ZT411-300dpi ZPL', 'device-id': 'SERN:99J204300180;MANUFACTURER:Zebra Technologies ;COMMAND SET:ZPL;MODEL:ZTC ZT411-300dpi ZPL;CLASS:PRINTER;OPTIONS:XML;', 'device-location': ''}
        # 'https': {'device-class': 'network', 'device-info': 'Internet Printing Protocol (https)', 'device-make-and-model': 'Unknown', 'device-id': '', 'device-location': ''}
    return 0


def _print_printers(printers: "dict[str, dict[str, str]]") -> None:
    for printer in printers:
        # {'ZT411': {'printer-is-shared': False, 'printer-state': 3, 'printer-state-message': '', 'printer-state-reasons': ['none'], 'printer-type': 2134092, 'printer-uri-supported': 'ipp://localhost/printers/ZT411', 'printer-location': 'Travelling Zebra', 'printer-info': 'ZT411', 'device-uri': 'pusb://Zebra%20Technologies/ZTC%20ZT411-300dpi%20ZPL?serial=99J204300180&Opt=BXVG',
        # 'printer-make-and-model': 'Zebra ZT411-300dpi Driver (peninsula-group.com)' }}
        print(printer, printers[printer]["device-uri"], printers[printer]["printer-make-and-model"])


def cmd_printers(options: "Optional[dict[str, str]]" = None) -> int:
    printer = OsPrinter()
    printers = printer.get_printers()
    _print_printers(printers)
    return 0


def cmd_add_printer(printer_name: str, printer_uri: str, ppd_file: str, options: "Optional[dict[str, str]]" = None) -> int:
    printer = OsPrinter()
    # First delete the printer if exists
    try:
        printer.delete_printer(printer_name)
    except:  # noqa: S110
        pass  # Silently ignore errors
    return printer.add_printer(printer_name, printer_uri, ppd_file, options)


def cmd_autoadd_printers(options: "Optional[dict[str, str]]" = None) -> int:
    printer = OsPrinter()
    # ? printer.autoadd_zebra()
    res, printers = printer.autoadd_printers(options)
    _print_printers(printers)
    return res


def cmd_delete_printer(printer_name: str, options: "Optional[dict[str, str]]" = None) -> int:
    printer = OsPrinter()
    return printer.delete_printer(printer_name, options)


def cmd_print_test(printer_name: str, options: "Optional[dict[str, str]]" = None) -> int:
    if options is None:
        options = {}
    printer = OsPrinter()
    return printer.print_test(printer_name, options)


def cmd_print_file(printer_name: str, file_name: str, options: "Optional[dict[str, str]]" = None) -> int:
    if options is None:
        options = {}
    printer = OsPrinter()
    doc_name = os.path.basename(file_name)
    return printer.print_file(printer_name, file_name, doc_name, options)


def parse_args() -> "tuple[argparse.Namespace, argparse.ArgumentParser]":
    parser = argparse.ArgumentParser(description="Manage printers (add,delete) or print a PDF/PNG file")

    # Common optional arguments
    parser.add_argument("-v", "--verbose", help="Verbose output", action="store_true")

    # Positional argument for the command
    subparsers = parser.add_subparsers(title="Commands", dest="command")

    # Parsers for commands
    install_parser = subparsers.add_parser("install", help="Install required dependencies on the OS")
    uninstall_parser = subparsers.add_parser("uninstall", help='Uninstall all OS components that "install" command installed')
    devices_parser = subparsers.add_parser("devices", help="Get list of available devices")
    printers_parser = subparsers.add_parser("printers", help="Get list of added printers")

    # Additional args for "add" command
    add_parser = subparsers.add_parser("add", help="Add a new printer")
    add_parser.add_argument("printer_name", type=str, help="Printer name")
    add_parser.add_argument("printer_uri", type=str, help="Printer URI")
    add_parser.add_argument("ppd_file", type=str, help="Printer driver PPD file")
    add_parser.add_argument("-L", "--location", dest="location", help="Printer location")
    add_parser.add_argument("-D", "--description", dest="description", help="Printer description")
    # add_parser.add_argument('rest', nargs=argparse.REMAINDER)

    # Additional args for "autoadd" command
    autoadd_parser = subparsers.add_parser("autoadd", help="Auto add all printers")
    # ? autoadd_parser.add_argument('printer_name', type=str, help='Printer name')

    # Additional args for "delete" command
    delete_parser = subparsers.add_parser("delete", help="Delete printer")
    delete_parser.add_argument("printer_name", type=str, help="Printer name")

    # Additional args for "test" command
    test_parser = subparsers.add_parser("test", help="Print test page")
    test_parser.add_argument("printer_name", type=str, help="Printer name")

    # Additional args for "print" command
    print_parser = subparsers.add_parser("print", help="Print PDF file")
    print_parser.add_argument("printer_name", type=str, help="Printer name")
    print_parser.add_argument("file_name", type=str, help="The name of the PDF file")
    print_parser.add_argument("rest", nargs=argparse.REMAINDER)

    # Parse the command line arguments
    args = parser.parse_args()
    return args, parser


def main() -> int:
    args, parser = parse_args()
    logger.debug(f"DEBUG {vars(args)}")

    try:
        if args.command == "install":
            options = AtDict()
            return cmd_install(options)

        if args.command == "uninstall":
            options = AtDict()
            return cmd_uninstall(options)

        if args.command == "devices":
            options = AtDict()
            return cmd_devices(options)

        if args.command == "printers":
            options = AtDict()
            return cmd_printers(options)

        if args.command == "add":
            options = AtDict()
            if args.location:
                options["location"] = args.location
            if args.description:
                options["description"] = args.description
            return cmd_add_printer(args.printer_name, args.printer_uri, args.ppd_file, options)

        if args.command == "autoadd":
            options = AtDict()
            return cmd_autoadd_printers(options)

        if args.command == "delete":
            options = AtDict()
            return cmd_delete_printer(args.printer_name, options)

        if args.command == "test":
            options = AtDict()
            return cmd_print_test(args.printer_name, options)

        if args.command == "print":
            return cmd_print_file(args.printer_name, args.file_name, options=args.rest)

    except Exception as e:
        logger.error(f'Error {type(e)} "{e}"')
        return -1

    parser.print_help()
    return 1


if __name__ == "__main__":
    rc = main()
    if rc:
        sys.exit(rc)
# Debugging LPrint:
# python printer.py add ZT411 usb// zpl_2inch-203dpi-tt -L "Ilya's desk" -D "Zebra label printer

# List ppd files:
# lpinfo -m
# ...
# drv:///sample.drv/zebra.ppd Zebra ZPL Label Printer
# printer_uri = "usb://Zebra/ZT230"

# List backends / connected printers:
# lpinfo -v
# ...
# network dnssd://Foo%20Fighter-1969._pdl-datastream._tcp.local./?uuid=4e216bea-c3de-4f65-a710-c99e11c80d2b
# direct usb://ZP/LazerJet%20MFP?serial=42
