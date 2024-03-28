#!/usr/bin/env bash

# Install software in ./pkg to the system.
_start_time_ms=$(($(date +%s%N)/1000000))

# Environment variables can be passed to us.
# If any of those are not set, defaults are used.
INST_DEBUG=${INST_DEBUG:-0}
INST_DO_QUICK=${INST_DO_QUICK:-2} ;# 0=full install, 1=skip some tedious steps, 2=skip most steps
# Set INST_ENABLE_GUI=0 for console-only mode
# Set INST_ENABLE_GUI=1 for GUI mode
INST_ENABLE_GUI=${INST_ENABLE_GUI:-0}
INST_ENABLE_USB_BOOT=${INST_ENABLE_USB_BOOT:-0}
INST_VNC_RESOLUTION=${INST_VNC_RESOLUTION:-1620x1200}
INST_DISABLE_VTS=${INST_DISABLE_VTS:-""}
INST_USE_HDMI_AUDIO=${INST_USE_HDMI_AUDIO:-1}
INST_LOCALE=${INST_LOCALE:-"en_US.UTF-8"}
INST_KBD_LAYOUT=${INST_KBD_LAYOUT:-"us"}
INST_TIMEZONE=${INST_TIMEZONE:-"America/Los_Angeles"}
INST_WIFI_COUNTRY=${INST_WIFI_COUNTRY:-"US"}
INST_USE_NMCLI=${INST_USE_NMCLI:-1}
INST_REMOTEIOT=${INST_REMOTEIOT:-""}
INST_HOSTNAME=${INST_HOSTNAME:-"RPI"}
INST_DFLT_USER=${INST_DFLT_USER:-"${SUDO_USER:-$(who -m | awk '{ print $1 }')}"}
INST_USER="$INST_DFLT_USER"

# Few Level Heading Separators for Nice Log (carriage return at the end allows
#  echo "${SEP2}SOME HEADER " to print ---> "SOME HEADER ###########")
SEP1="$(printf "%100s\r" "" | tr ' ' '#')"
SEP2="$(printf "%100s\r" "" | tr ' ' '=')"
# SEP3="$(printf "%100s\r" "" | tr ' ' '-')"

# Determine if we're sourced or executed
{ is_sourced=0; script=$(basename "$0"); }; ( return 0 2>/dev/null ) && { is_sourced=1; script=$(basename "${BASH_SOURCE[0]}"); }

myreadlink() { [ ! -h "$1" ] && { echo "$1"; return; }; (local d l; d="$(dirname -- "$1")"; l="$(expr "$(command ls -ld -- "$1")" : '.* -> \(.*\)$')"; cd -P -- "$d" || exit; myreadlink "$l" | sed "s|^\([^/].*\)\$|$d/\1|"); }
#parent="$(cd -P -- "$(dirname    "$(greadlink -f "${BASH_SOURCE[0]}" || readlink -f "${BASH_SOURCE[0]}" || readlink "${BASH_SOURCE[0]}" || echo "${BASH_SOURCE[0]}")")" &> /dev/null && pwd)"
parent="$(dirname -- "$(myreadlink "${BASH_SOURCE[0]}")" )"
parent=$(cd "$parent" || exit; pwd)  ;## resolve absolute path
parent=${parent%/}  ;## trim trailing slash

SOURCE="${parent}"
#SOURCE_NAME=$(basename "${SOURCE}")
#SOURCE_PARENT=$(dirname "${SOURCE}")10

# Parse arguments
#args="$@"
function usage() {
  echo "Usage:"
  echo "$script [-h] | [options]"
  echo " "
  echo "Install software in this folder to the system."
  echo " "
  echo "options:"
  echo "  -h | --help                        show this usage information"
  echo "  -D | --debug                       Print debugging info"
  echo "  -f | --full                        Do full install (no skipping)"
  echo "  -q | --quick                       Do quick install (skip long installs of packages if already was installed)"
  #echo "  -u | --user=<user_name>            (default \"$INST_DFLT_USER\")"
  #echo "  -n | --hostname=<host_name>        (default \"${host}\")"
  #echo "  -a | --ip=<ip_addr>                (default \"auto\"=DHCP)"
  #echo "                              Note: (*) Must run with 'sudo'"
  echo
}
while [ $# -gt 0 ]; do
  case "$1" in
  -h|--help)
    usage
    # shellcheck disable=SC2317
    return 0 2>/dev/null || exit 0
    ;;
  -D|--debug)
    INST_DEBUG=1
    ;;
  -f|--full)
    INST_DO_QUICK=0
    ;;
  -q|--quick)
    INST_DO_QUICK=2
    ;;
  *)
    echo "Unknown option/command \"$1\"." >&2
    usage
    # shellcheck disable=SC2317
    return 1 2>/dev/null || exit 1
    ;;
  esac
  shift
done

function is_pi () {
  ARCH=$(dpkg --print-architecture)
  if [ "$ARCH" = "armhf" ] ; then
    return 0
  elif [ "$ARCH" = "arm64" ] ; then
    return 0
  else
    return 1
  fi
}

# Must be on pi
if ! is_pi ; then
  echo "Only Raspberry Pi is supported."
  exit 1
fi

# Must be root
if [ "$(id -u)" -ne 0 ]; then
  echo "Script must be run as root. Try 'sudo $0 $*'"
  exit 1
fi

if is_pi ; then
  CMDLINE=/boot/cmdline.txt
else
  CMDLINE=/proc/cmdline
fi
CONFIG=/boot/config.txt

# Ensure on the very first run INST_DO_QUICK is not > 0.
[ ! -f ~/.do_quick ] && { INST_DO_QUICK=0; touch ~/.do_quick; }
# TODO: (soon) This /root/.do_quick is a bad idea for multiple apps sharing this script - when different app is installed, it should not use do_quick.

## Wrapper over `raspi-config nonint ...` non-interactive use
function use_raspi_config () {
  local ret;
  [ 0 -ne "$INST_DEBUG" ] && echo "DEBUG: raspi-config(nonint $*)"
  local result; result=$(raspi-config nonint "$@")
  ret=$?
  [ 0 -ne "$INST_DEBUG" ] && echo "DEBUG: \$?=$ret result=$result"
  return "$ret"
}

function set_autologin_shell () {
  echo "${SEP2}BOOT & LOGIN "
  use_raspi_config do_boot_behaviour B2 &
  ## TODO: (soon) Investigate why so slow? Takes whole minute!
  echo " + enable Autologin into Shell for user '${INST_USER}' "
  # echo
  # We're headlining set_usb_boot_enable()/set_usb_boot_disable()
}

function set_autologin_gui () {
  echo "${SEP2}BOOT & LOGIN "
  if [ ! -e /etc/init.d/lightdm ]; then
    sudo apt-get install lightdm
  fi
  if [ ! -e /etc/init.d/lightdm ]; then
    echo "Error, 'lightdm' is not installed correctly, file '/etc/init.d/lightdm' is missing."
    exit 1
  fi

  use_raspi_config do_boot_behaviour B4
  echo " + enable Autologin into GUI for user '${INST_USER}' "
  # echo
  # We're headlining set_usb_boot_enable()/set_usb_boot_disable()
}

function fix_autologin_UNUSED () {
  echo "${SEP2}FIX AUTOLOGIN "
  # Some things to try if autologin to GUI does not work...
  sudo apt-get install --reinstall lxsession
  sudo dpkg-reconfigure lightdm
  sudo chown "$INST_USER":"$INST_USER" "/home/$INST_USER/.Xauthority"
  sudo chmod 0600 "/home/$INST_USER/.Xauthority"
}

function set_usb_boot_enable () {
  sed -i "$CONFIG" -e "s/program_usb_boot_mode=.*//"
  echo "program_usb_boot_mode=1" >> "$CONFIG"
  echo " + enable USB boot "
  echo

  # TODO: (when needed) Implement: `vcgencmd otp_dump | grep 17` ; # If the output shown is 17:3020000a, USB boot is enabled.
}

function set_usb_boot_disable () {
  sed -i "$CONFIG" -e "s/program_usb_boot_mode=.*//"
  echo " + disable USB boot "
  echo
}

function set_vnc_resolution () {
  echo "${SEP2}VNC RESOLUTION "
  use_raspi_config do_vnc_resolution "$INST_VNC_RESOLUTION"
  echo " + Set VNC resolution to '${INST_VNC_RESOLUTION}' "
  echo
}

function backup_settings () {
  echo "${SEP2}BACKUP ORIGINAL SETTINGS "
  [ -f $CMDLINE.orig ] || sudo cp -pv $CMDLINE $CMDLINE.orig
  [ -f $CONFIG.orig  ] || sudo cp -pv $CONFIG  $CONFIG.orig
  [ -f /etc/issue.orig ] || sudo cp -pv /etc/issue /etc/issue.orig
  echo
}

function remove_old_files () {
  echo "${SEP2}REMOVE OLD FILES "

  # UNUSED
  # Add files from old versions that are obsolete here:

  echo
}

function install_packages () {
  echo "${SEP2}INSTALL PACKAGES "
  [ 0 -eq "$INST_DO_QUICK" ] && sudo apt-get update

  #REMOVE sudo apt-get install -y python-dev python-pip python-cliff
  sudo apt-get install -y python3-dev python3-pip python3-venv python3-cliff

  # For `pip install python-systemd`:
  # sudo apt-get install -y build-essential libsystemd-journal-dev libsystemd-daemon-dev libsystemd-dev
  # Or just install apt package:
  sudo apt-get install -y python3-systemd
  
  ## For `pip install wxpython` (which is pulled in by Gooey):
  # sudo apt-get install -y libghc-gtk3-dev libwxgtk3.0-gtk3-dev

  sudo apt-get install -y fbi ntpdate conspy
  #UNUSED sudo apt-get install -y python-rpi.gpio python3-rpi.gpio
  sudo apt-get install -y network-manager network-manager-gnome ;# for nmcli
  sudo apt-get install -y samba samba-common-bin
  
  # Serial terminal
  sudo apt-get install -y minicom
  # Use: $ minicom -b 115200 -D /dev/ttyUSB0  ;# To exit: Ctrl+a x

  sudo apt-get install -y screen
  # Use: $ screen /dev/ttyUSB0 115200,cs8  ;# To exit: Ctrl+a \  ;# Show keybindings: Ctrl+a ?

  # Cleanup:
  sudo apt-get autoremove -y
  echo
}

function install_files () {
  echo "${SEP2}INSTALL FILES "
  # cp -T will copy ./pkg/boot/ to /boot/ (without -T it will be /pkg/boot/)
  if [ 0 -eq "$INST_DO_QUICK" ]; then
    sudo cp -Trv "$SOURCE/pkg/" /
  else
    sudo cp -Trv -u "$SOURCE/pkg/" /
  fi

  # TODO: (when needed) copy pkg/home/pi/* files to appropriate user's home directory. Config user to use in _conf.yaml?
  #shopt -s dotglob ;# bash will not find hidden .xxx files and complain, fix it with dotglob
  #sudo cp -rv pkg/home/$INST_USER/* ~/
  #shopt -u dotglob ;# restore

  echo
}

function set_permissions () {
  echo "${SEP2}SET PERMISSIONS "
  sudo chmod -v 700 "/home/$INST_USER/app"
  sudo chown -Rv "$INST_USER:$INST_USER" "/home/$INST_USER/app"
  sudo chmod -v 700 "/home/$INST_USER/.ssh"
  sudo chown -Rv "$INST_USER:$INST_USER" "/home/$INST_USER/.ssh"
  sudo chmod -v 600 "/home/$INST_USER/.ssh/authorized_keys"
  echo
}

function disable_vt () {
  echo "${SEP2}DISABLE VTS ( ${INST_DISABLE_VTS} ) "

  # Convert INST_DISABLE_VTS space-separated string to an Array. Note - do not quote, ignore shellcheck SC2206 warning.
  # INST_DISABLE_VTS variable is not an Array (bash and others cannot export Arrays), it is
  # a space-separated list of numbers
  local arr
  # shellcheck disable=SC2206
  arr=( ${INST_DISABLE_VTS} )
  for i in "${arr[@]}"; do
    # Disable getty on VTn, so interactive script can be used on it instead.
    #sudo systemctl stop "getty@tty${i}.service"
    #sudo systemctl disable "getty@tty${i}.service"
    sudo systemctl mask "getty@tty${i}.service"
    sudo systemctl mask "autovt@tty${i}.service"
    echo " + Disable login on VT${i}"
  done  
  echo
}

function enable_services () {
  echo "${SEP2}ENABLE SERVICES "
  sudo systemctl daemon-reload

  ## SSH
  #?sudo systemctl enable ssh.service
  use_raspi_config do_ssh 0 ;# 0=enable, 1=disable (weird, huh?)
  echo " + SSH"

  #sudo systemctl start webcam-video.service
  #sudo systemctl enable webcam-video.service
  
  sudo systemctl enable app_manager_startup.service
  # sudo systemctl start app_manager_startup.service
  echo " + app_manager_startup.service"
  
  echo
}

function do_netconf() {
  # Copied from raspi-config (size 95856) and modified.
  INIT="$(ps --no-headers -o comm 1)"
  # systemctl -q is-enabled NetworkManager > /dev/null 2>&1
  # NMENABLED=$?
  # systemctl -q is-enabled dhcpcd > /dev/null 2>&1
  # DHENABLED=$?
  NMOPT="$1"

  if [ "$NMOPT" -eq 2 ] ; then # NetworkManager selected
    ENABLE_SERVICE=NetworkManager
    DISABLE_SERVICE=dhcpcd
    # NETCON="NetworkManager"
  else # dhcpcd selected
    ENABLE_SERVICE=dhcpcd
    DISABLE_SERVICE=NetworkManager
    # NETCON="dhcpcd"
  fi

  systemctl -q disable "$DISABLE_SERVICE" 2> /dev/null
  systemctl -q enable "$ENABLE_SERVICE"
  if [ "$INIT" = "systemd" ]; then
    systemctl -q stop "$DISABLE_SERVICE" 2> /dev/null
    systemctl -q --no-block start "$ENABLE_SERVICE"
  fi
}

function enable_dhcpd () {
  echo "${SEP2}NETWORK "
  # use_raspi_config do_netconf 1 &
  do_netconf 1
  echo " + enable DHCPD for Network "
  echo
}

function enable_nmcli () {
  echo "${SEP2}NETWORK "
  # use_raspi_config do_netconf 2 &
  do_netconf 2
  echo " + enable NetworkManager for Network "
  echo
}

function install_remoteiot () {
  echo "${SEP2}REMOTE CONTROL "
  local command; command="pi_base device"
  [ 0 -ne "$INST_DEBUG" ] && command="$command -D"
  if which "pi_base" ; then
    local output ret last_line re device_id
    re='.* device_id="([^"]*)"'
    device_id=
    output="$($command query 2>&1)"
    ret=$?
    if [ $ret -ne 0 ]; then
      # $command add "$SITE_ID" "$APP_TYPE" "$APP_NAME" ;# <-- these vars should come from app_conf.yaml. But it's easier to do it in Python.
      output="$($command add_at_install)" ; # Will gather vars from app_conf.yaml for us: "$SITE_ID" "$APP_TYPE" "$APP_NAME"
      ret=$?
      if [ $ret -ne 0 ]; then
        echo "Error $ret installing remote control." >&2
        exit $ret
      fi
      last_line="${output##*$'\n'}"
      # last_line: Connected this device to remoteiot.com service as device_id="RPI-BASE-blank-001" "RPI BASE Blank 001"
      if [[ $last_line =~ $re ]]; then device_id="${BASH_REMATCH[1]}"; fi

      echo " + install remote control, device_id=\"$device_id\" "
    else
      last_line="${output##*$'\n'}"
      # last_line: This device is connected to remoteiot.com service as e.g. device_id="RPI-BASE-blank-001".
      if [[ $last_line =~ $re ]]; then device_id="${BASH_REMATCH[1]}"; fi

      echo " - skipping remote control install - already installed, device_id=\"$device_id\" "
    fi
    if [ -n "$device_id" ]; then
      echo " + Changing hostname to \"$device_id\" "
      INST_HOSTNAME="$device_id"
    fi
  else
    echo "Error - Package \"pi_base\" not found, cannot install REMOTE_CONTROL." >&2
    exit 1
  fi
  echo
}

function adjust_settings () {
  echo "${SEP2}ADJUST SETTINGS "

  # Unblank the screen
  echo " + Disable screen blanking"
  echo 0 | sudo tee /sys/class/graphics/fb0/blank >/dev/null &
  ## TODO: (soon) Investigate why so slow? Takes whole minute!

  # Reset / remove all scattered settings (will be set below):
  echo " + Reset boot settings"
  sed -i $CMDLINE -e "s/ dwc_otg.lpm_enable=[0-1]//"
  #sed -i $CMDLINE -e "s/ quiet//"
  #sed -i $CMDLINE -e "s/ splash//"
  #sed -i $CMDLINE -e "s/ plymouth.ignore-serial-consoles//"
  sed -i $CMDLINE -e "s/ consoleblank=[0-1]*//"
  sed -i $CMDLINE -e "s/ plymouth.enable=[0-1]//"
  sed -i $CMDLINE -e "s/ loglevel=[0-9]//"
  sed -i $CMDLINE -e "s/ logo.nologo//"
  sed -i $CMDLINE -e "s/ vt.global_cursor_default=[0-1]//"

  echo " + Enable boot splash"
  use_raspi_config do_boot_splash 0; # 0=enable, 1=disable (adds only `quiet splash plymouth.ignore-serial-consoles`)

  echo " + Remove boot messages"
  sed -i $CMDLINE -e "s/ console=tty1/ console=tty3/"
  #                   Remove (hide) boot messages

  sed -i $CMDLINE -e "s/$/ dwc_otg.lpm_enable=0/"
  # USB Link Power Management	- 0 to disable LPM support

  #sed -i $CMDLINE -e "s/$/ quiet splash plymouth.ignore-serial-consoles/"
  #                   quiet                            : disable boot message texts
  #                   splash                           : enables splash image
  #                   plymouth.ignore-serial-consoles  : (required when use Plymouth)

  sed -i $CMDLINE -e "s/$/ consoleblank=0/"
  #                   consoleblank=X                   : console blank (screen saver) timeout in seconds

  echo " + Remove RPi boot logo"
  sed -i $CMDLINE -e "s/$/ logo.nologo/"
  #                   logo.nologo                      : removes Raspberry Pi logo in top left corner.

  echo " + Remove cursor on boot"
  sed -i $CMDLINE -e "s/$/ vt.global_cursor_default=0/"
  #                   vt.global_cursor_default=0       : removes blinking cursor (downside: also removes cursor from VT's).

  sed -i $CMDLINE -e "s/$/ loglevel=3/"
  #                   loglevel=3                       : Mute kernel logs > 3 
  # 0=KERN_EMERG, 1=KERN_ALERT, 2=KERN_CRIT, 3=KERN_ERR, 4=KERN_WARNING, 5=KERN_NOTICE, 6=KERN_INFO, 7=KERN_DEBUG

  # plymouth.enable=0 breaks splash (which uses plymouth theme).
  # Another splash method (from service) should work without plymouth.
  #? [ 0 -eq "$INST_ENABLE_GUI" ] && sed -i $CMDLINE -e "s/$/ plymouth.enable=0/"

  echo " + Enable cursor in VT"
  # To show cursor back in VT's:
  # Applicable commands in a terminal:
  #  `tput cnorm` (underlined cursor)
  #  `tput cvvis` (block cursor)
  #  `tput civis` (cursor invisible)
  # Here's how to extract the actual string (with escapes):
  #   TERM=linux tput cnorm | sed -n l
  TNORM=$(TERM=linux tput cnorm | sed -n l) ;# Get escape sequence and convert 0x1B into readable form. Side-effect: adds '$' at the end.
  TNORM="${TNORM%$}" ;# Trim '$' at the end
  # Sequence that prunes /etc/issue from previous installs:
  #   ESC_TNORM="$(printf '%s\n' "$TNORM" | sed -e 's/[][()|^$\\\/*+.]/\\&/g')" ;# Escape all RegEx special chars []()|^$\/*+.
  #   ESC_TNORM="$(printf '%s\n' "$ESC_TNORM" | sed -e 's/\\\\033/\x1b/g')" ;# Convert escaped 0x1B back.
  #   sed -i /etc/issue -e "s/$ESC_TNORM//g" ;# Remove all existing codes, so no duplicates are accumulated.
  # Having that indeciperable sequence above, it is much better to use our backup copy to reset the file each time:
  [ -f /etc/issue.orig ] && sudo cp -p /etc/issue.orig /etc/issue
  echo -n -e "$TNORM" | sudo tee -a /etc/issue
  echo " + added Show Cursor command for VT init to '/etc/issue'"
  #
  # This business with hide/show cursor is much too overcomplicated. Some final notes :
  # Some are trying to add ' -I ...' to /etc/systemd/system/getty@tty1.service.d/autologin.conf, but it has no effect on VTn(n>1)
  #
  # Another possible convoluted method is to modify terminfo for the terminal (append cursor reset code from `tput cnorm` to rs1/rs2 codes):
  # infocmp linux | sed '/^.rs[12]=/ s/,$/\\E[?12l,/' | tic - ;# will need to move the result into /etc/... for all users pre-login
  # https://unix.stackexchange.com/a/3769/458623

  echo
}

function install_python_packages () {
  echo "${SEP2}INSTALL PYTHON PACKAGES "
  # Use (PEP-0668) --break-system-packages as we need our packages to be available in system / multi-user applications.
  # TODO: (soon) Implement python venv and remove --break-system-packages
  [ -f "$SOURCE/common_requirements.txt" ] && pip install --break-system-packages -r "$SOURCE/common_requirements.txt"
  # TODO: (when needed) fail on error here
  echo
}

function update_locale () {
  echo "${SEP2}SET LOCALE & TIMEZONE "
  use_raspi_config do_change_locale "$INST_LOCALE"
  echo " + set locale: $INST_LOCALE"
  use_raspi_config do_configure_keyboard "$INST_KBD_LAYOUT"
  echo " + set keyboard layout: $INST_KBD_LAYOUT"
  # sudo locale-gen
  # sudo rm -rf /etc/localtime 2>/dev/null
  # sudo ln -s /usr/share/zoneinfo/America/Los_Angeles /etc/localtime

  use_raspi_config do_wifi_country "$INST_WIFI_COUNTRY"
  echo " + set WiFi Country: $INST_WIFI_COUNTRY"
  use_raspi_config do_change_timezone "$INST_TIMEZONE"
  echo " + set Timezone: $INST_TIMEZONE"

  echo
}

function set_audio_WIP () {
  # https://nerdiy.de/en/howto-raspberrypi-standardlautsprecher-konfigurieren/
  # https://elinux.org/R-Pi_Troubleshooting


  # Per some obscure notes, with pulseaudio installed, should not use amixer anymore ("... going back the the December 2020 release of RPiOS that added PulseAudio, one finds buried in the 400+ comments ...")
  # that explains the below struggles:
  #
  # Note: if /boot/config.txt "dtparam=audio=on" use 0,1,2; "#dtparam=audio=on" - no internal audio, use BT device
  # n=2
  #? amixer cset numid=3 $n ;# Where $n is the required interface : 0=auto, 1=analog, 2=hdmi.
  # As of RPi 3B+ and Raspberry Pi OS bullseye 2022, numid=3 is Master Playback Volume 0-65536, not an old 'PCM Playback Route', so it won't work.
  # sudo amixer controls && amixer controls ;# Give different results, none of them have 'PCM Playback Route'
  # sudo amixer contents && amixer contents ;# Give different results, none of them have 'PCM Playback Route'
  # https://github.com/raspberrypi/firmware/issues/139, however removing pulseaudio does not work.
  # Still it looks like an issue with pulseaudio's interaction with alsa.
  # Further, using `amixer -c 1 ...` gives different set of controls/contents, but still no 'PCM Playback Route'
  #
  # raspi-config (without pulseaudio) incorrectly uses `amixer cset numid=3 ...`, and it has no effect on output, but sets very low volume.

  # should use pacmd, pactl

  #
  #list=$(sudo -u $INST_USER XDG_RUNTIME_DIR=/run/user/$(id -u "$INST_USER") pacmd list-sinks | grep -e index -e alsa.name | sed s/*//g | sed s/^[' '\\t]*//g | sed s/'index: '//g | sed s/'alsa.name = '//g | sed s/'bcm2835 '//g | sed s/\"//g | tr '\n' '/')
  #?list=$(pacmd list-sinks | grep -e index -e alsa.name | sed s/*//g | sed s/^[' '\\t]*//g | sed s/'index: '//g | sed s/'alsa.name = '//g | sed s/'bcm2835 '//g | sed s/\"//g | tr '\n' '/')
  cat /proc/asound/modules ;# more easily digestible format, 0=analog, 1=hdmi(vc4), same as pacman list-sinks
  # 0 snd_bcm2835
  # 1 vc4


  AUDIO_OUT_SINK=1 ;# TODO: (when needed) choose HDMI (1) 3.5mm Jack (0) : from _conf.yaml file?
  #sudo -u $SUDO_USER XDG_RUNTIME_DIR=/run/user/$SUDO_UID pactl set-default-sink $AUDIO_OUT
  pactl set-default-sink $AUDIO_OUT_SINK
  # in /usr/share/alsa/alsa.conf:
  # defaults.ctl.card $AUDIO_OUT
  # defaults.pcm.card $AUDIO_OUT

  #? /etc/asound.conf
  # pcm.!default {
  #     type hw
  #     card $AUDIO_OUT
  # }
  # ctl.!default {
  #   type hw
  #   card $AUDIO_OUT
  # }  
}

function is_pulseaudio () {
  pgrep pulseaudio > /dev/null || pgrep pipewire-pulse > /dev/null
  return $?
}

# Robust method (should be aware of sink numbers changing...)
function set_audio_sink () {
  echo "${SEP2}AUDIO OUTPUT "
  local sink sinks; sink=$1

  # ? Enable PulseAudio
  # systemctl --global -q disable pipewire-pulse
  # systemctl --global -q disable wireplumber
  # systemctl --global -q enable pulseaudio
  # if [ -e /etc/alsa/conf.d/99-pipewire-default.conf ] ; then
  #   rm /etc/alsa/conf.d/99-pipewire-default.conf
  # fi
  # use_raspi_config do_audioconf 1  ;# PulseAudio
  # echo " + set Audio Config = PulseAudio"
  audio_mgr=
  if is_pulseaudio ; then
    audio_mgr="PulseAudio pactl"
    sinks=(69:Headphones 68:HDMI)
  elif aplay -l | grep -q "bcm2835 ALSA"; then
    audio_mgr="ALSA amixer"
    sinks=(1:Headphones 2:HDMI 0:Auto)
  else
    audio_mgr="ALSA .asoundrc"
    sinks=(0:Headphones 1:HDMI)
  fi
  sink_rec="${sinks[$sink]}"
  sink_num="${sink_rec%%:*}"
  # sink_name="${sink_rec#*:}"
  use_raspi_config do_audio "${sink_num}"
  #? sudo alsactl store
  echo " + set Audio Output = $sink_rec ($audio_mgr)"
  echo
}
function set_audio_headphones () {
  set_audio_sink 0 ;# Headphones
}
function set_audio_hdmi () {
  set_audio_sink 1 ;# HDMI
}

function configure_wdog () {
  echo "${SEP2}WATCHDOG "
  # pip3 install pywatchdog

  # Seems to be already enabled on RPI:
  # sudo modprobe bcm2835-wdt
  # echo "bcm2835-wdt" | sudo tee -a /etc/modules
  
  # Not needed, as we're using pywatchdog
  # sudo apt-get install watchdog chkconfig
  # sudo chkconfig watchdog on
  # sudo systemctl start watchdog.service

  # Add permissions for /dev/watchdog to pi user
  # Works in tandem with /etc/udev/rules.d/60-watchdog.rules which makes /dev/watchdog owned by watchdog group
  sudo groupadd watchdog 2>/dev/null
  sudo usermod -a -G watchdog pi
  echo " + Added group 'watchdog' for access to '/dev/watchdog'"
  # echo " + Configured /dev/watchdog for use in app (added watchdog group)"
  echo
}

function final_overrides () {
  ## Manipulate config files that previous steps create / overwrite
  echo "${SEP2}FINAL OVERRIDES "

  # UNUSED

  echo
}

function print_info () {
  echo "  INFO script=$script, is_sourced=$is_sourced"
  
  local args; args=(
    SOURCE
    INST_DEBUG
    INST_DO_QUICK
    INST_ENABLE_GUI
    INST_ENABLE_USB_BOOT
    INST_VNC_RESOLUTION
    INST_DISABLE_VTS
    INST_USE_HDMI_AUDIO
    INST_LOCALE
    INST_KBD_LAYOUT
    INST_TIMEZONE
    INST_WIFI_COUNTRY
    INST_USE_NMCLI
    INST_REMOTEIOT
    INST_HOSTNAME
    INST_DFLT_USER
  )

  for arg in "${args[@]}"; do
    # Get values of Array and non-Array variables
    all_elems_indirection="${arg}[@]"
    vals="${!all_elems_indirection}"
    printf "%24s = %s\r  %s \n" "" "${vals}" "$arg"
  done
  echo
}

# Debug:
#echo "DEBUG BASH_SOURCE=${BASH_SOURCE[*]}, script=$script, parent=$parent, is_sourced=$is_sourced, user=$INST_USER"
#echo "DEBUG SOURCE=${SOURCE}"
#echo "DEBUG SOURCE_PARENT=${SOURCE_PARENT}"
#echo "DEBUG SOURCE_NAME=${SOURCE_NAME}"
#is_pulseaudio && echo "DEBUG: pulseaudio found"
#echo "DEBUG SUDO_USER="$INST_DFLT_USER" SUDO_UID=$(id -u "$INST_DFLT_USER")"

echo "${SEP1}BEGIN COMMON INSTALLATION "
echo
print_info

backup_settings
# remove_old_files

[ 1 -ge "$INST_DO_QUICK" ] && install_packages
[ 1 -ge "$INST_DO_QUICK" ] && install_python_packages
install_files
set_permissions
enable_services
adjust_settings
[ 1 -ge "$INST_DO_QUICK" ] && update_locale

[ 0 -eq "$INST_ENABLE_GUI" ] && set_autologin_shell
[ 1 -eq "$INST_ENABLE_GUI" ] && set_autologin_gui
[ 0 -eq "$INST_ENABLE_USB_BOOT" ] && set_usb_boot_disable
[ 1 -eq "$INST_ENABLE_USB_BOOT" ] && set_usb_boot_enable

set_vnc_resolution
disable_vt

[ 0 -eq "$INST_USE_HDMI_AUDIO" ] && set_audio_headphones
[ 1 -eq "$INST_USE_HDMI_AUDIO" ] && set_audio_hdmi

[ 0 -eq "$INST_USE_NMCLI" ] && enable_dhcpd
[ 1 -eq "$INST_USE_NMCLI" ] && enable_nmcli

[ 1 -eq "$INST_REMOTEIOT" ] && install_remoteiot ;# Side-effect -> Generated unique name to $INST_HOSTNAME
use_raspi_config do_hostname "$INST_HOSTNAME"
echo " + Set hostname to \"$INST_HOSTNAME\" "

configure_wdog

# final_overrides

_run_time_ms=$(( $(date +%s%N)/1000000 - _start_time_ms ))
echo "${SEP1}"
echo "COMMON INSTALLATION Done. Elapsed time ${_run_time_ms%???}.${_run_time_ms: -3}s"
echo
