# pi-base

Framework for creating Raspberry Pi appliances.

PI-BASE is a framework for quick development of appliance projects using Raspberry Pi running Linux (Raspberry Pi OS, previously called Raspbian), e.g. for IoT, home automation, custom appliances, manufacturing test stations, etc.

## Deployment

### Assemble Raspberry Pi

Acquire all the parts (Raspberry Pi board, case, power supply, Micro-SD card or M2 SSD) and assemble per the case instructions. Before installing M2 SSD into the case, write the OS to it (see instructions below).

### Create Micro-SD Card or M2 SSD with Boot Software Image

See [SDCARD](./SDCARD.md)

TODO: (when needed) Add a 'installer' user (sudoer) to install.sh to differ from default user 'pi'.

### Build the RPI App

Run `pi_base/make.py` script on the host computer.

### Upload the App to RPI

Boot RPi with the created Micro-SD Card or the M2 SSD.

Run `pi_base/upload.sh` script from host computer (run `pi_base/upload.cmd` script on Windows without bash. Note: `upload.cmd` is not maintained and lacks some latest features of `pi_base/upload.sh`).

### Install the App on RPI

Login either in RPi console or via SSH as `ssh://pi@RPI.local` <ssh://pi@RPI.local>. If you entered a different hostname and/or username in the Raspberry Pi Imager, use that hostname.

Run `/home/pi/pi-base/build/<site_id>/<project>/install.sh` (site_id is the short name of the Deployment Site it is built for by `pi_base/make.py`). It may take some time to download and install all the packages on the first run. Subsequent runs (e.g. while developing) will be faster.

RPi is ready now. Power down the RPi and make necessary connections to the system (per the instructions in each project).

## Data Backend

As a backend, pi-base currently uses `common/gd_service.py` to store backend files on GoogleDrive.

The connection details are determined by `*_secrets.json` file which is never commited to the git repo, but instead distributed by other secure means. It is included into build and also given to the tester app by `<project>/conf.yaml` files.

There is one `*_secrets.json` file for each of the Deployment Sites. There are also auxiliary file(s) for build and onboarding functions.

`*_secrets.json` file is primarily a key file for Google API libs, but we expand it to contain additional fields/props, like Google Drive folder ID. It was verified that external libs consuming that file don't mind the extra props.

To avoid any potential name collision with existing or future Google props, the additional props are named `pibase_XXX`. Currently used properties are:

- pibase_gd_results_folder_id   - Result Files    Folder ID on Google Drive
- pibase_gd_devices_folder_id   - Devices DB File Folder ID on Google Drive
- pibase_gd_devices_file_title  - Devices DB File Title     on Google Drive
- pibase_gd_sites_folder_id     - Sites DB File   Folder ID on Google Drive
- pibase_gd_sites_file_title    - Sites DB File   Title     on Google Drive

For details on creating new Service Account and setting up `*_secrets.json` key file (properties for Google APIs) see [GD_SERVICE.md](./GD_SERVICE.md). After creating the key file, add all needed `pibase_XXX` properties to it.

## Development

Either clone this git repo directly to RPi, or enable SSH on the RPi and then upload all files to it over SCP/SSH from Windows/Linux (if git is installed on Windows, it has scp implementation) using `pi_base/upload.sh` / `pi_base/upload.cmd`, then SSH to RPi and run `install.sh` from one of build subfolders.

New Projects should be created in sub-folders named `<project>` in the repo root folder. Project sub-folder should contain:

- Builder configuration file `conf.yaml`.
- `pkg` folder with folders tree containg any files to be copied to RPi root file system during install. Add an empty `.gitkeep` file if there are no files/folders to copy, as missing `pkg` sub-folder will prevent `pi_base/make.py` from working properly # TODO: (now) fix hard dependency.
- `install.sh` - should set up environment variables and invoke common_install.sh for majority of installation, and perform any custom steps.
- `requirements.txt` - contains list of python modules to be installed
- `<project>.py` - main file to be executed on RPI
- Any other files specific to the project (every file that needs to be copied to the target should be added to the `conf.yaml`)

pi-base repo contains the following files and folders:

- pi-base/lib - Various Python modules used by pi-base and available for use in the projects.
- pi-base/common - Various files shared between all projects, common installation files.
- pi-base/common/graphics - various graphics design files provided as templates for the projects.
- pi-base/pictures - photos and screenshots.
- pi-base/scripts - various utility scripts.
- blank - A blank starter project with a template for creating new projects ('blank' build type is excluded in `pi_base/make.py`).

### App Layers

The app on Raspberry Pi consists of few layers:

- `/etc/app_manager_startup.service` - systemd service that starts app_manager_startup script
- `/usr/local/bin/app_manager_startup` - plays boot sound and shows splashscreen, then starts manager.py on VT2
- `/home/pi/modules/manager.py` - reads app config yaml file, waits for network, synchronizes time, then starts the app per the yaml config.
- `/home/pi/app/<project>.py` - The app is started on VT1 (and VT4 is available for history)

Raspbery Pi on boot will execute the chain of layers to load the app, which takes full control of Raspberry Pi VT1.

It is possible to enable Raspberry Pi GUI (change INST_ENABLE_GUI setting in project's `install.sh`), and use VT7 for Graphical Interface. VT1 will still be the main app console and VT2/VT4 will be additional consoles for manager and appliance history.

It is possible to run each individual layer, e.g. for debugging or verification:

- Service: TBD
- Service script: `/usr/local/bin/app_manager_startup`
- Manager: `/home/pi/modules/manager.py --vt 2` TODO: TBD sudo?
- App itself: `/usr/bin/python -u /home/pi/app/<app type>.py`

    Some of the layers can be debugged on a workstation (PC or Mac), without RPi image deployed.

- App itself: `python <app type>/<app type>.py` e.g. `python blank/blank.py`

Note that `modpath.py` (which main goal is to locate all app resources deployed on the target) is currently crudely tries to be also helpful on the workstation, so development is possible. But it means that some files have to be placed in reachable places before the local app will work correctly. To do so invoke `python pi_base/make.py --type all` to create build directories, and also inspect modpath.py for the hard-coded helpers that may need adjustment.

### Remote Debugging

For remote debugging, VT sessions can be accessed via SSH using `conspy` package (installed by common_install.sh):

```bash
sudo conspy 1 ;# Main tester app VT
```

To exit `conspy`, quickly press `[Esc]` key 3 times.

### Toolchain

Overview:

 > `pi_base/make.py` -> `pi_base/upload.sh` -> on target: `build/<site_id>/<project>/install.sh`

#### `pi_base/make.py` [`<project>`]

(On Windows should run command: `python pi_base/make.py [--site <site_id> --type <project>]`)

Python script that makes / prepares selected project in its staging folder (which is `./build/<site_id>/<project>/`).

It reads project configuration from `<project>/conf.yaml` file and performs all necessary steps.

It performs the following steps:

  1. Read `<project>/conf.yaml` file.
  2. Create `build/<site_id>/<project>/` folder and subfolders as needed:
     1. `pkg` subfolder is prepared for it to be copied to the target system `/` (root) during installation.
  3. Copy all `common/*` files listed in 'Modules' section of `<project>/conf.yaml` file (or whole `common/` folder if there is no 'Modules'section) to pkg/home/pi/modules/.
  4. Copy individual files listed in 'Files' section of `<project>/conf.yaml` file to their selected destinations.
  5. Copy standard template files to `build/<site_id>/<project>/`:
     1. common/common_install.sh
     2. common/common_requirements.txt
     3. common/pkg/
     4. `<project>/install.sh`
     5. `<project>/requirements.txt`
     6. `<project>/pkg/`

TODO: (soon) Add command-line option to run `pi_base/upload.sh`

#### `pi_base/upload.sh` / `pi_base/upload.cmd`

Script for the host computer that copies whole pi-base folder (or selected build site subfolder) from the host computer to the target RPi device over SSH.

RPi must be powered up, booted, connected to the same network as the host computer, and SSH enabled.

TODO: (soon) Add ability to (optionally) call `build/<site_id>/<project>/install.sh` via SSH.

#### `<project>/install.sh`

Note: Make sure to call the `build/<site_id>/<project>/install.sh` file on the target. Calling source `<project>/install.sh` will produce incorrect install.

TODO: (now) Add detecting when `install.sh` is run not from `build` but from `<project>` folder.

Script that downloads and installs all necessary packages and configures the target RPi.

Should be run with `sudo` on the target RPi.

It should call common_install.sh file for all common parts to be installed.

#### `common/common_install.sh`

Script that is copied over to `build/<site_id>/<project>/common_install.sh` by `pi_base/make.py`.

It installs common parts, enables app_manager_startup.service, which is run upon RPi boot and executes `<project>/modules/manager.py`.

TODO: (when needed) Add some command line options (e.g. to force reinstall)

#### `common/common_requirements.txt`

List of Python/pip packages to be installed for all projects. Used in common/common_install.sh.

#### `<project>/requirements.txt`

List of Python/pip packages to be installed for the given projects. Used in `<project>/install.sh`

#### `/etc/systemd/system/app_manager_startup.service`

Service that is installed and enabled on the target RPi that executes /usr/local/bin/app_manager_startup script on every boot.

#### `/usr/local/bin/app_manager_startup`

Script that shows splashscreen and plays boot chime on the target RPI and then executes /home/pi/modules/manager.py.

#### `/home/pi/modules/manager.py`

Manager script that runs on the target RPi, reads /etc/manager_conf.yaml, performs various startup activities and launches project app.

#### `/home/pi/app/<project>.py`

Project app script that performs all operations required by the project.

E.g. a tester project will perform tests with connected devices and show PASS/FAIL result in the UI.

TODO: (when needed) To be implemented.

### Dev.Notes

- Install Raspberry Pi OS on a fast 4~16GB Micro-SD Card, boot RPi with it
  - Used latest 2022-04-04-raspios-bullseye-armhf.img.xz (2022-0720)
   <https://www.raspberrypi.com/software/operating-systems/>
  - Used Raspberry Pi Imager
   <https://www.raspberrypi.com/software/>
- Perform initial setup
  - Set Country / timezone
  - Connect to WiFi (or use LAN port for networking)
  - User "pi" - change password
- Enable SSH

```bash
## python 3 (python 2 not supported)
sudo apt-get install python3-dev python3-pip

## RPi.GPIO (UNUSED)
# sudo apt-get install python-rpi.gpio python3-rpi.gpio
## sudo pip install RPi.GPIO gpiozero
## sudo pip-3.2 install RPi.GPIO gpiozero
### ## gpiozero (higher-level lib, not really needed)
### sudo apt-get install python-gpiozero python3-gpiozero
### sudo pip install RPi.GPIO gpiozero
### sudo pip-3.2 install RPi.GPIO gpiozero

## TODO: (when needed) Pi Mocks (ONLY needed on platforms other than Pi, e.g. MacOS, Windows - for cross-development)
pip install git+https://github.com/iva2k/raspi-device-mocks.git
# Note, for development, use:
pip install -e git+https://github.com/iva2k/raspi-device-mocks.git#egg=raspi-device-mocks
# ... then can edit source in <env>/src/rpidevmocks/ and commit to github.
# Or, can link source directly from another location:
pip install -e c:/dev/raspi-device-mocks --no-binary :all:
pip install cliff
```

This project settled on [cliff](https://pypi.org/project/cliff/) for arguments parsing, and argparse in some instances. Other CLI tools of interest:

- Fire: <https://github.com/google/python-fire/blob/master/docs/guide.md>
- Click: <https://click.palletsprojects.com/en/7.x/>

### Large.py vs. Pyfiglet

```bash
pip install pyfiglet
```

Can use `pyfiglet --font block_xxl 'PASS'` to generate text that goes into "large.txt" file.

To edit fonts can use <https://patorjk.com/figlet-editor/#/edit>.

### VTs

To successfully run an app with text-only UI (e.g. on a text console), we need to manage Virtual Terminals (VTs). Linux on Raspberry Pi by default allocates 6 VTs.

See <https://unix.stackexchange.com/a/194218/458623> for good overview of what is happening.

We use VT1 for the main app (whether it is slideshow/video carousel or text-based tester UI), and VT2 for the app manager (the one responsible for all running processes, such as pre-app network connection, software update check, etc., and launching the app and switching to it running on VT1).

As part of the common_install.sh, VT1 and VT2 are removed from the normal system use, by disabling login on these VTs, which is done by masking getty@ttyN and autovt@ttyN systemd services for each of the VTs. common_install.sh uses INST_DISABLE_VTS environment variable (space-separated list of numbers) set by the app's install.sh, so the app's install.sh can decide which actual VTs to remove from system use by setting that variable. If app's install.sh does not set INST_DISABLE_VTS, no VTs will be disabled by default.

User of the system can still switch between VTs by Ctrl+Alt+F{n} keys on the keyboard. With VT1 used for the main app, VT2 showing the manager, the remaining VTs can be either assigned by the app to do some other features (could imagine showing appliance events log on e.g. VT3, list of all found BLE devices on VT4, etc.), or if the app installer leaves VTs enabled, they will have regular virtual terminals with logind/getty so user can (be instructed to) login and invoke normal Linux commands on the command line. VT7 can be given to the Graphical login / desktop GUI if so desired (be carefull with that, as X may decide to switch to its GUI and steal the display from VTx).

Note: Occasionally VT display stops updating and responding to Ctrl+Alt+F{n} keys, while SSH connection continues working and VT's can be accessed via `conspy`. One cause was noticed if a swap file is corrupted (error can be found is dmesg or /var/log/syslog). Do `sudo rm /var/swap && reboot`, the swap file will be recreated. Another fix is to shutdown and power off, then power on again (simple reboot does not seem to help).

### Autologin

See <https://raspberrypi.stackexchange.com/a/136099>

For 'autologin' group see <https://raspberrypi.stackexchange.com/a/105427>

Lightdm details:
<https://wiki.archlinux.org/title/LightDM#Enabling_autologin>

### SAMBA File Sharing

(for streamlined development, expose whole file system)

DISABLE FOR PRODUCTION!

```bash
sudo apt-get install samba samba-common-bin
sudo smbpasswd -a pi

sudo nano /etc/samba/smb.conf

[share]
Comment = RPi shared folder
Path = /
Browseable = yes
Writeable = Yes
only guest = no
create mask = 0777
directory mask = 0777
Public = yes
Guest ok = no


sudo /etc/init.d/samba-ad-dc restart
sudo /etc/init.d/smbd restart

```

## RPi System LEDs

It is possible to control LEDs on RPi board:

<https://raspberrypi.stackexchange.com/questions/70013/raspberry-pi-3-model-b-system-leds>

## TODOs

- (when needed) invent UI for headless use (buttons/LEDs)
- (when needed) optimize boot time. See <https://bootlin.com/doc/training/boot-time/boot-time-slides.pdf>
- (when needed) Replace boot splash with intiramfs image. See <https://gitlab.com/DarkElvenAngel/initramfs-splash>
- (when needed) nmbd.service is stuck loading without network. See <https://bugzilla.samba.org/show_bug.cgi?id=13111> - newer Samba version has a fix.

## CREDITS

- Boot sound by eardeer <https://freesound.org/people/eardeer/sounds/385281/>
