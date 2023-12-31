#!/usr/bin/env python3

# Targeting printing labels from Python software on Zebra ZT411 (203dpi) and ZT610 printers (both using ZPL language).
# CUPS was supposed to be supporting ZPL, but recent development is on a path to remove PPD and drivers support
# and drop non-IPP printers.
# Investing into CUPS on that path makes very little sense.
# Current CUPS-based alternative to PPD/driver use that might be workable is ippeveprinter, except on any Debian Linux
#  it had lost critical file `ippeveps``, so printing PDF does not seem possible. Building from sources could be a
# possibility to bring ippeveps back, but eventual success is highly questionable without PPD support.
#
# Further, CUPS creator, Michael R Sweet had left Apple & CUPS project (https://www.phoronix.com/news/CUPS-Lead-Developer-Leaves-APPL)
# and now consults as CTO of Lakeside Robotics Corp. (his wife is CEO).
# https://lakesiderobotics.ca/printing.html
# https://www.linkedin.com/company/lakeside-robotics-ca/
# https://www.linkedin.com/in/michael-sweet-90848120/
# He recently developed a promising package LPrint that supports ZPL / Zebra label printers:
# https://www.msweet.org/lprint/
# https://github.com/michaelrsweet/lprint
# The package is in Debian / Ubuntu repos, and installs on RPi.
# MacOS - LPrint TBD.

# Latest trend is use IPP / everywhere / driverless
# ippeveprinter -D file:///Users/Shared/Print/ -c /usr/libexec/cups/command/ippeveps -F application/pdf  -P /private/etc/cups/ppd/Direct_PDF.ppd Qwe
# ippeveprinter -D printer_uri -c /usr/libexec/cups/command/ippeveps -F application/pdf  -P ppd_file printer_name
# ippeveprinter -D printer_uri -c /usr/libexec/cups/command/ippeveps -F application/pdf,application/postscript,image/jpeg,image/pwg-raster,image/urf -P ppd_file -r _print,_universal -i IMAGEPNG -l LOCATION printer_name
# Investigated ippeveprinter and ZPL:
# Where is 'ippeveps' command file (needed for ippeventprinter to work with ZPL)?
# - source exists in apple repo https://github.com/apple/cups/blob/master/tools/ippeveps.c
# - source exists in OpenPrinting repo https://github.com/OpenPrinting/cups/blob/master/tools/ippeveps.c
# - Debian packaging organized differently
# - ippeveps files are missing in Debian packages (ippeveprint is in cups-ipp-utils package)
# - in Fedora packaging (cups-printerapp and ps-printer-app packages) is also organized differently, file might be present, but can't cherry-pick one package, need to use them all


import argparse
import logging
import os
import platform
import subprocess
import sys
from typing import List, Dict, Tuple
from abc import ABC, abstractmethod

from os_utils import which

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__ if __name__ != '__main__' else None)
logger.setLevel(logging.DEBUG)

# conn = cups.Connection()
# printers = conn.getPrinters()
# printer_name = printers.keys()[0]
# conn.printFile(printer_name,'/home/pi/Desktop/a.pdf',"",{})


class atdict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def shell(cmd):
    """Shell command utility

    Args:
        cmd ([str]): command and arguments list

    Returns:
        number, str, str: Returncode, stdout, stderr
    """
    # logger.debug(f'Running command "{cmd}"')
    output = subprocess.run(cmd, text=True, capture_output=True, check=False)
    logger.debug(f'Shell command: "{output}"')
    return output.returncode, output.stdout, output.stderr


def is_ext(ext, filename):
    file_path, file_ext = os.path.splitext(filename)
    return ext.lower() == file_ext.lower()


def convert_to_png(file, outfile=None):
    if not outfile:
        outfile = file + '.png'
    magick = which(['magick', 'C:/Program Files/ImageMagick-7.1.0-Q16/magick.exe'])
    if not os.access(magick, os.X_OK):
        raise Exception('"magick" command is not found. Is ImageMagick installed and added to PATH?')
    else:
        logger.debug(f'Converting {file} to {outfile} ...')
        out = subprocess.check_output(
            # TODO: (when needed) Implement scaling to dpi etc.: convert -density 320 "$_input_pdf" -scale 926x1463 -type grayscale -depth 8 -crop 812x1218+52+166 "$_output_png"
            f'"{magick}" convert {file} {outfile}',
            shell=True,
            text=True)
        logger.debug(f'{out}')
    if not os.path.isfile(outfile):
        raise Exception(f'Failed converting {file}, result file {outfile} not created.')
    return outfile


class PrintError(Exception):
    pass


class PrinterInterface(ABC):
    """Abstract interface for Printer implementations
    """

    @abstractmethod
    def install(self) -> bool:
        """Install required dependencies on the OS
        """
        return False

    @abstractmethod
    def uninstall(self) -> bool:
        """Uninstall all OS components that self.install() installed
        """
        return False

    @abstractmethod
    def get_devices(self) -> List[str]:
        """Get list of available devices

        Returns:
            list[Dict[str, str]]: _description_
        """
        return False

    @abstractmethod
    def get_printers(self) -> List[Dict[str, str]]:
        """Get list of added printers

        Returns:
            list[Dict[str, str]]: _description_
        """
        return []

    @abstractmethod
    def print_test(self, printer_name: str, options: Dict[str, str] = None) -> int:
        """Print test page
        """
        return -1

    @abstractmethod
    def print_file(self, printer_name: str, file_name: str, doc_name: str = '', options: Dict[str, str] = None) -> int:
        """Print given file
        """
        return -1

    def autoadd_printers(self, options: Dict[str, str] = None) -> Tuple[int, List[Dict[str, str]]]:
        """Add all found compatible printers
        """
        return ()

    def autoadd_zebra(self) -> int:
        """Attempts to add the Zebra ZT411 printer
        """
        return -1

    @abstractmethod
    def add_printer(self, printer_name: str, printer_uri: str, ppd_file: str, options: Dict[str, str] = None) -> int:
        """Add given printer
        """
        return -1

    @abstractmethod
    def delete_printer(self, printer_name: str, options: Dict[str, str] = None) -> int:
        """Delete previously added printer
        """
        return -1


class CupsPrinter(PrinterInterface):
    """Printer using CUPS

    Other commands:
      * cupsctl --debug-logging
      * cupsctl --no-debug-logging

    Args:
        PrinterInterface (_type_): _description_
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

    def install(self) -> bool:
        returncode, _, _ = shell(["sudo", "apt-get", "install", "cups"])
        if returncode:
            returncode, _, _ = shell(["sudo", "usermod", "-a", "-G", "lpadmin", "pi"])
        if returncode:
            returncode, _, _ = shell(["pip", "install", "pycups"])
        return returncode == 1

    def uninstall(self) -> bool:
        returncode, _, _ = shell(["sudo", "apt-get", "--purge", "remove", "cups"])
        returncode2, _, _ = shell(["pip", "uninstall", "pycups"])
        return returncode == 1 and returncode2 == 1

    def get_devices(self):
        devices = self.conn.getDevices()  # Takes a bit of time. Is there a timeout param?
        return devices

    def get_printers(self):
        printers = self.conn.getPrinters()
        return printers

    def print_test(self, printer_name: str, options: Dict[str, str] = None) -> int:
        file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "printer-test-label.png"))
        return self.print_file(printer_name, file_path, options=options)

    def print_file(self, printer_name, file_name, doc_name='', options=None) -> int:
        returncode = -1
        if os.path.isfile(file_name):
            options = options if options else {}
            # SVG files don't print on Zebra with Peninsula Group driver (missing CUPS filter?)
            # https://unix.stackexchange.com/questions/372379/what-file-formats-does-cups-support
            if os.path.splitext(file_name)[1].lower() == '.svg':
                logger.warning(f'Got "{file_name}" file to print which has SVG extension. SVG files are (typically) not supported by label printers. Please use PDF. Will try anyway...')

            # TODO: (when needed) self.cups.setUser('pi')
            if printer_name in self.get_printers():
                returncode = self.conn.printFile(printer_name, file_name, doc_name, options)
            else:
                logger.warning(f'Unrecognized printer name given "{printer_name}"')
        else:
            logger.warning(f'File "{file_name}" does not exit.')
        return returncode

    def delete_printer(self, printer_name: str, options: Dict[str, str] = None):
        cmd = ["lpadmin", "-x", printer_name]
        res, out, err = shell(cmd)
        return res

    def autoadd_zebra(self, default_name="ZT411") -> int:
        """
        Attempts to automatically detect and add the Zebra ZT411 under the name 'ZT411'
        """
        returncode = -1
        devices = self.get_devices()
        for device in devices:
            if "zebra" in device.lower():
                uri = device
                default_options = {
                    'PageSize': 'w144h72',
                    'MediaSize': 'w144h72',
                    # TODO: (when needed): 'Resolution'        : '302dpi', # Zebra ZT411 has different resolutions (print head options). Ours is 302dpi.
                    'Resolution': '203dpi',
                    'zeMediaTracking': 'Web',
                    'MediaType': 'Thermal',
                    'Darkness': '30',
                    'zePrintRate': '1',
                    'zeLabelTop': '200',
                    'zePrintMode': 'Applicator',
                    'zeTearOffPosition': '1000',
                    'zeErrorReprint': 'Saved'
                }
                options = []
                for opt, val in default_options.items():
                    options.append("-o")
                    options.append(f"{opt}={val}")
                returncode, _, _ = shell(["sudo", "lpadmin", "-p", default_name, "-E", "-v", uri, "-m", "drv:///sample.drv/zebra.ppd"] + options)
                break

        return returncode

    def add_printer(self, printer_name: str, printer_uri: str, ppd_file: str, options: Dict[str, str] = None):
        """Install a printer
        CUPS: @see https://www.cups.org/doc/admin.html
        Currently broken.
        PPD files are on deprecation notice, will be removed in CUPS 3.0, release imminent.

        Args:
            printer_name (str): _description_
            printer_uri (str): _description_
            ppd_file (str): _description_
            options (Dict[str, str], optional): _description_. Defaults to None.

        Returns:
            int: Error code
        """
        cmd = [
            "lpadmin",
            "-p", printer_name,
            "-E",  # Enable printer
            "-v", printer_uri,
            # TODO: (when needed) # "-m", ppd_file,
            "-m", "everywhere",  # TODO: (when needed) ppd file created in /etc/cups/ppd/,
            "-o", "printer-is-shared=false",
        ]
        if 'description' in options:
            cmd += ["-D", options['description']]
        if 'location' in options:
            cmd += ["-L", options['location']]
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
    # sudo apt-get install cups –y.
    # sudo systemctl start cups.
    # sudo systemctl enable cups.
    # sudo nano /etc/cups/cupsd.conf.
    # sudo systemctl restart cups.
    # # /etc/cups/cupsd.conf
    # # sudo usermod -aG lpadmin username

    # CUPS admin via web interface
    # http://localhost:631


class LprintPrinter(PrinterInterface):
    """Printer using LPrint

    # Investigated lprint and ZPL
    * https://www.msweet.org/lprint/lprint.html
    - It is promised to be replacement for PPD drivers now and when CUPS 3.0 removes PPD drivers support.
    - Realities are glum - segfaults and not working out of the box with latest v1.2.0 (in snap).
    - snap has its own issues, e.g. `sudo lprint ...` does not work ($PATH for root?) - workaround `sudo /snap/bin/lprint ...`
    - server crashes and has tons of bugs
    - Web interface: was able to add a printer, but never printed a test page.
    - No test page in CLI (only WEb)

    * Commands:
    lprint drivers
    lprint devices
    lprint add -d ZT411 -v "socket://192.168.1.20" -m zpl_2inch-203dpi-tt
    lprint add -d printer_name -v printer_uri -m zpl_2inch-203dpi-tt

    Example Linux service (watches directory for new files and prints them) https://gist.github.com/dreamcat4/4240184f9299b211d2106bfef2d55518

    Installation:
    # sudo apt-get install lprint ;# gets v1.0 on Debian/Ubuntu/RPi
    sudo apt-get install snapd
    Note: snap uncovers a problem with /etc/ld.so.preload file on RPi - comment out the line in  /etc/ld.so.preload. Offending package is raspi-copies-and-fills v0.13. `sudo apt-get remove --purge raspi-copies-and-fills`
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

    Args:
        PrinterInterface (_type_): _description_
    """

    def __init__(self) -> None:

        # lprint --version
        # RPi:
        # lprint v1.0
        # Ubintu 22 LTS:
        # lprint v1.0
        # TODO: (when needed) Check if OS package is installed
        pass

    def install(self):
        # TODO: (when needed) Improve installing OS packages - live stdio/stderr, handle errors (and recover/continue)
        for cmd in [
            ["sudo", "apt-get",  "update"],
            ["sudo", "apt-get",  "install", "-y", "snapd"],
            ["sudo", "snap",  "install", "core"],
            ["sudo", "snap",  "install", "lprint"],
            ["sudo", "snap",  "connect", "lprint:raw-usb"],  # Must for USB-connected printer
            #["sudo", "snap",  "set", "lprint", "auth-service=cups",],
            ["sudo", "snap",  "set", "lprint", "server-port=32101", ],
            ["sudo", "snap",  "start", "lprint.lprint-server"],
        ]:
            logger.debug(f'cmd={cmd}')
            res, out, err = shell(cmd)
            print(out)
            eprint(err)

    def uninstall(self):
        # TODO: (when needed) Implement
        pass

    def web_off(self):
        # TODO: (when needed) Implement
        # "sudo snap start lprint.lprint-server",
        pass

    def web_on(self):
        # TODO: (when needed) Implement
        # "sudo snap stop?? lprint.lprint-server",
        pass
        # lprint server -o server-name=HOSTNAME -o server-port=NNN -o auth-service=cups
        # `-o admin-group=GROUP`

    def get_devices(self):
        cmd = ["lprint", "devices"]
        res, out, err = shell(cmd)
        l = out.split('\n')
        # TODO: (when needed) implement format parsing, normalize to same format as CupsPrinter
        devices = [p for p in l]
        # for printer in printers:
        #     print(printer, printers[printer]["device-uri"])
        return devices

    def get_printers(self):
        cmd = ["lprint", "printers"]
        res, out, err = shell(cmd)
        l = out.split('\n')
        # TODO: (when needed) implement format parsing, normalize to same format as CupsPrinter
        printers = [p for p in l]
        # for printer in printers:
        #     print(printer, printers[printer]["device-uri"])
        return printers

    def print_test(self, printer_name: str, options=None):
        options = options if options else {}
        # TODO: (when needed) Implement

    def print_file(self, printer_name, file_name, doc_name='', options=None):
        # TODO: (when needed) Implement lprint options for printing
        # Example for 4x6inch label
        #  lprint -o media-top-offset=3.5mm -o print-color-mode=bi-level -o media-tracking=continuous -o media-type=labels-continuous -o media=oe_4x6-label_4x6in -o orientation-requested=portrait "$_output_png"
        options = options if options else {}

        file_to_print = file_name
        if is_ext('.pdf', file_name):
            file_to_print = convert_to_png(file_name)

        cmd = [
            "lprint",
            "-d", printer_name,
            file_to_print
        ]
        # TODO: (when needed) Explore available options: `lprint options -d PRINTER`
        res, out, err = shell(cmd)
        return res

    def print_file_lp(self, printer_name, file_name):
        # TODO: (when needed) implement
        # Without CUPS, use lp:
        os.system(f'lp -d {printer_name} {file_name}')
        # os.system(f'lpr -P  {printer_name} {file_name}')
        return 0

    def delete_printer(self, printer_name: str, options: Dict[str, str] = None):
        # TODO: (when needed) check if it works:
        cmd = ["lprint", "delete", "-d", printer_name]
        res, out, err = shell(cmd)
        return res

    def autoadd_printers(self, options: Dict[str, str] = None):
        # had_printers = self.get_printers()
        cmd = [
            "lprint", "autoadd",
            # "-d", printer_name,
            # "-v", printer_uri,
            # "-m", ppd_file,  # from "lprint drives", e.g. "zpl_2inch-203dpi-tt"
            # "-o", "printer-is-shared=false",
        ]
        # if 'description' in options:
        #     cmd += ["-o", f'??printer-description={options["description"]}']
        if 'location' in options:
            cmd += ["-o", f'printer-location={options["location"]}']
        res, out, err = shell(cmd)
        if res:
            raise OSError(res, err)

        # Enable the printer?

        # Set the printer as the default?

        printers = self.get_printers()
        # TODO: (when needed) printers -= had_printers
        return res, printers

    def add_printer(self, printer_name: str, printer_uri: str, ppd_file: str, options: Dict[str, str] = None):
        """Install a printer

        Args:
            printer_name (str): _description_
            printer_uri (str): _description_, " TODO: if 'auto', invoke self.autoadd_printers()
            ppd_file (str): One of LPrint -m files (see "lprint drivers"), e.g. zpl_2inch-203dpi-tt
            options (Dict[str, str], optional): _description_. Defaults to None.

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
            "lprint", "add",
            "-d", printer_name,
            "-v", printer_uri,
            "-m", ppd_file,  # from "lprint drives", e.g. "zpl_2inch-203dpi-tt"
            # "-o", "printer-is-shared=false",
        ]
        # if 'description' in options:
        #     cmd += ["-o", f'??printer-description={options["description"]}']
        if 'location' in options:
            cmd += ["-o", f'printer-location={options["location"]}']
        res, out, err = shell(cmd)
        if res:
            raise OSError(res, err)

        # Enable the printer?

        # Set the printer as the default?

        return res


# on Windows:
def winPrint1():
    # `pip3 install pywin32`
    import win32.win32print as win32print  # pylint: disable=import-outside-toplevel
    printer_name = win32print.GetDefaultPrinter()
    file_name = "document.pdf"
    printer_handle = win32print.OpenPrinter(printer_name)
    win32print.StartDocPrinter(printer_handle, 1, ("test of raw data", None, "RAW"))
    win32print.StartPagePrinter(printer_handle)
    with open(file_name, "rb") as f:
        win32print.WritePrinter(printer_handle, f.read())
    win32print.EndPagePrinter(printer_handle)
    win32print.EndDocPrinter(printer_handle)
    win32print.ClosePrinter(printer_handle)
    printer_handle = None


def winPrint2():
    import win32ui  # pylint: disable=import-outside-toplevel
    dc = win32ui.CreateDC()
    dc.CreatePrinterDC()
    dc.StartDoc('Label Document')
    dc.StartPage()
    fontdata = {'height': 80}
    font = win32ui.CreateFont(fontdata)
    dc.SelectObject(font)
    dc.TextOut(0, 10, 'Sample: 3174')
    dc.TextOut(0, 90, 'Date:26/02/21')
    dc.TextOut(0, 180, 'sample_name')
    dc.EndPage()
    dc.EndDoc()


def Printer(driver_type: str, *args, **kwargs) -> PrinterInterface:
    inst = None
    if driver_type.lower() == 'cups':
        inst = CupsPrinter(*args, **kwargs)
    if driver_type.lower() == 'lprint':
        inst = LprintPrinter(*args, **kwargs)
    # TODO: (when needed): Implement Windows printer class 'WinPrinter'
    # if driver_type.lower() == 'win':
    #     inst = WinPrinter(*args, **kwargs)
    return inst


def OsPrinter(*args, **kwargs) -> PrinterInterface:
    if os.name == 'nt':  # Windows
        driver_type = 'Win'
        # driver_type = 'LPrint'  # for debugging LPrint piping on Windows. Can try LPrint on Windows some day.
    elif platform.system() == 'Darwin':  # MacOS
        driver_type = 'CUPS'
    elif os.name == 'posix':  # Linux, MacOS
        driver_type = 'CUPS'
    else:
        raise Exception(f'Unsupported OS {os.name}')

    printer = Printer(driver_type)
    if not printer:
        raise ValueError(f'Error getting printer class for {driver_type}')
    return printer


def cmd_install(options=None):
    printer = OsPrinter()
    return printer.install()


def cmd_uninstall(options=None):
    printer = OsPrinter()
    return printer.uninstall()


def cmd_devices(options=None):
    printer = OsPrinter()
    devices = printer.get_devices()
    for device in devices:
        print(device, devices[device]['device-id'])
        # 'pusb://Zebra%20Technologies/ZTC%20ZT411-300dpi%20ZPL?serial=99J204300180': {'device-class': 'direct', 'device-info': 'Zebra Technologies ZTC ZT411-300dpi ZPL', 'device-make-and-model': 'Zebra Technologies ZTC ZT411-300dpi ZPL', 'device-id': 'SERN:99J204300180;MANUFACTURER:Zebra Technologies ;COMMAND SET:ZPL;MODEL:ZTC ZT411-300dpi ZPL;CLASS:PRINTER;OPTIONS:XML;', 'device-location': ''}
        # 'https': {'device-class': 'network', 'device-info': 'Internet Printing Protocol (https)', 'device-make-and-model': 'Unknown', 'device-id': '', 'device-location': ''}
    return 0


def _print_printers(printers):
    for printer in printers:
        # {'ZT411': {'printer-is-shared': False, 'printer-state': 3, 'printer-state-message': '', 'printer-state-reasons': ['none'], 'printer-type': 2134092, 'printer-uri-supported': 'ipp://localhost/printers/ZT411', 'printer-location': 'Travelling Zebra', 'printer-info': 'ZT411', 'device-uri': 'pusb://Zebra%20Technologies/ZTC%20ZT411-300dpi%20ZPL?serial=99J204300180&Opt=BXVG',
        # 'printer-make-and-model': 'Zebra ZT411-300dpi Driver (peninsula-group.com)' }}
        print(printer,
              printers[printer]["device-uri"],
              printers[printer]["printer-make-and-model"]
              )


def cmd_printers(options=None):
    printer = OsPrinter()
    printers = printer.get_printers()
    _print_printers(printers)
    return 0


def cmd_add_printer(printer_name, printer_uri, ppd_file, options=None):
    printer = OsPrinter()
    # First delete the printer if exists
    try:
        printer.delete_printer(printer_name)
    except:
        pass  # Ignore errors
    return printer.add_printer(printer_name, printer_uri, ppd_file, options)


def cmd_autoadd_printers(options=None):
    printer = OsPrinter()
    res, printers = printer.autoadd_printers(options)
    _print_printers(printers)
    return res


def cmd_delete_printer(printer_name, options=None):
    printer = OsPrinter()
    return printer.delete_printer(printer_name, options)


def cmd_print_test(printer_name, options={}):
    printer = OsPrinter()
    return printer.print_test(printer_name, options)


def cmd_print_file(printer_name, file_name, options={}):
    printer = OsPrinter()
    doc_name = os.path.basename(file_name)
    return printer.print_file(printer_name, file_name, doc_name, options)


def parse_args():
    parser = argparse.ArgumentParser(description='Manage printers (add,delete) or print a PDF/PNG file')

    # Common optional arguments
    parser.add_argument('-v', '--verbose', help='Verbose output', action='store_true')

    # Positional argument for the command
    subparsers = parser.add_subparsers(title='Commands', dest='command')

    # Parsers for commands
    install_parser = subparsers.add_parser('install', help='Install required dependencies on the OS')
    uninstall_parser = subparsers.add_parser('uninstall', help='Uninstall all OS components that "install" command installed')
    devices_parser = subparsers.add_parser('devices', help='Get list of available devices')
    printers_parser = subparsers.add_parser('printers', help='Get list of added printers')
    add_parser = subparsers.add_parser('add', help='Add a new printer')
    autoadd_parser = subparsers.add_parser('autoadd', help='Auto add all printers')
    delete_parser = subparsers.add_parser('delete', help='Delete printer')
    test_parser = subparsers.add_parser('test', help='Print test page')
    print_parser = subparsers.add_parser('print', help='Print PDF file')

    # Additional args for "add" command
    add_parser.add_argument('printer_name', type=str, help='Printer name')
    add_parser.add_argument('printer_uri', type=str, help='Printer URI')
    add_parser.add_argument('ppd_file', type=str, help='Printer driver PPD file')
    add_parser.add_argument('-L', '--location', dest='location', help='Printer location')
    add_parser.add_argument('-D', '--description', dest='description', help='Printer description')
    # add_parser.add_argument('rest', nargs=argparse.REMAINDER)

    # Additional args for "autoadd" command
    # ? autoadd_parser.add_argument('printer_name', type=str, help='Printer name')

    # Additional args for "delete" command
    delete_parser.add_argument('printer_name', type=str, help='Printer name')

    # Additional args for "test" command
    test_parser.add_argument('printer_name', type=str, help='Printer name')

    # Additional args for "print" command
    print_parser.add_argument('printer_name', type=str, help='Printer name')
    print_parser.add_argument('file_name', type=str, help='The name of the PDF file')
    print_parser.add_argument('rest', nargs=argparse.REMAINDER)

    # Parse the command line arguments
    args = parser.parse_args()
    return args, parser


def main():
    args, parser = parse_args()
    logger.debug(f'DEBUG {vars(args)}')

    try:
        if args.command == 'install':
            options = atdict()
            return cmd_install(options)

        if args.command == 'uninstall':
            options = atdict()
            return cmd_uninstall(options)

        if args.command == 'devices':
            options = atdict()
            return cmd_devices(options)

        if args.command == 'printers':
            options = atdict()
            return cmd_printers(options)

        if args.command == 'add':
            options = atdict()
            if args.location:
                options['location'] = args.location
            if args.description:
                options['description'] = args.description
            return cmd_add_printer(args.printer_name, args.printer_uri, args.ppd_file, options)

        if args.command == 'autoadd':
            options = atdict()
            return cmd_autoadd_printers(options)

        if args.command == 'delete':
            options = atdict()
            return cmd_delete_printer(args.printer_name, options)

        if args.command == 'test':
            options = atdict()
            return cmd_print_test(args.printer_name, options)

        if args.command == 'print':
            return cmd_print_file(args.printer_name, args.file_name, options=args.rest)

    except Exception as e:
        logger.error(f'Error {type(e)} {e}')
        return -1

    parser.print_help()
    return 1


if __name__ == '__main__':
    printer = OsPrinter()
    printer.autoadd_zebra()
    exit()
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
