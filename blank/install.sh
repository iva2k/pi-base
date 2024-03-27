#!/usr/bin/env bash

# Install software in this folder to the system.
_start_time_ms=$(($(date +%s%N)/1000000))

# Environment variables passed to common_install.sh.
export INST_DEBUG=0
export INST_DO_QUICK=2 ;# 0=full install, 1=skip some tedious steps, 2=skip most steps
# Set INST_ENABLE_GUI=0 for console-only mode
# Set INST_ENABLE_GUI=1 for GUI mode
export INST_ENABLE_GUI=0
# export INST_ENABLE_GUI=1
export INST_ENABLE_USB_BOOT=0
export INST_VNC_RESOLUTION=1620x1200
export INST_DISABLE_VTS="1 2"
export INST_USE_HDMI_AUDIO=1
export INST_LOCALE=en_US.UTF-8
export INST_KBD_LAYOUT=us
export INST_TIMEZONE=America/Los_Angeles
export INST_WIFI_COUNTRY=US
export INST_USE_NMCLI=0
export INST_REMOTEIOT=1
export INST_HOSTNAME=RPI
#INST_DFLT_USER=pi
export INST_DFLT_USER="${SUDO_USER:-$(who -m | awk '{ print $1 }')}"
#INST_USER="$INST_DFLT_USER"

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

if [ ! -f "${SOURCE}/common_install.sh" ]; then
  echo "Please run this script only from build directory on Raspberry Pi."
  exit 1
fi

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

# Ensure on the very first run INST_DO_QUICK is not > 0.
[ ! -f ~/.do_quick ] && { INST_DO_QUICK=0; touch ~/.do_quick; }

function backup_settings () {
  echo "${SEP2}BACKUP ORIGINAL SETTINGS "

  # UNUSED

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
  # sudo apt-get install -y fbi ntpdate

  # UNUSED

  # Cleanup:
  sudo apt-get autoremove -y
  echo
}

function install_files () {
  echo "${SEP2}INSTALL FILES "

  # UNUSED

  echo
}

function set_permissions () {
  # echo "${SEP2}SET PERMISSIONS "

  # UNUSED

  echo
}


function enable_modules () {
  echo "${SEP2}ENABLE MODULES "

  # UNUSED

  echo
}

function enable_services () {
  echo "${SEP2}ENABLE SERVICES "
  # sudo systemctl daemon-reload

  # UNUSED
  
  echo
}

function adjust_settings () {
  echo "${SEP2}ADJUST SETTINGS "

  # UNUSED

  echo
}

function install_python_packages () {
  echo "${SEP2}INSTALL PYTHON PACKAGES "
  # Use (PEP-0668) --break-system-packages as we need our packages to be available in system / multi-user applications.
  # TODO: (soon) Implement python venv and remove --break-system-packages
  [ -f "$SOURCE/requirements.txt" ] && pip install --break-system-packages -r "$SOURCE/requirements.txt"
  # TODO: (when needed) fail on error here
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
#echo "DEBUG SUDO_USER="$INST_DFLT_USER" SUDO_UID=$(id -u "$INST_DFLT_USER")"

## Install common package (uses INST_* env variables)
if [ -x "${SOURCE}/common_install.sh" ]; then
  "${SOURCE}/common_install.sh"
else
  echo "common_install.sh file not found."
fi

echo "${SEP1}BEGIN APP INSTALLATION "
echo
print_info

# backup_settings
# remove_old_files

# [ 1 -ge "$INST_DO_QUICK" ] && install_packages
[ 1 -ge "$INST_DO_QUICK" ] && install_python_packages
# install_files
# set_permissions
# enable_modules
# enable_services
# adjust_settings

# final_overrides

_run_time_ms=$(( $(date +%s%N)/1000000 - _start_time_ms ))
echo "${SEP1}"
echo "APP INSTALLATION Done. Elapsed time ${_run_time_ms%???}.${_run_time_ms: -3}s"
echo
