#!/usr/bin/env bash

# Upload all files in this folder (or the build/ sub-folder) to a remote host over SSH / SCP

# This script tries to use `rsync` if available
# Further, to eliminate multiple password prompts, it can use:
# - a `ssh_secret.txt` file that should contain SSH password
# - use `sshpass` to feed SSH password to the prompts from the file, or from a saved variable
# Unfortunately, `sshpass -e` is broken with `rsync`, so some script gymnastics is involved.

# There are some obstacles in how SSH / SCP / RSYNC work on Windows:
# 1. There could be more than 1 separate installations for the tools - WSL, MSYS and git (which has its own fork of MSYS tools)
# 2. Keys are stored in few different places, depending on tools location
# 3. MSYS `ssh -f ...` (backgrounding mode) does not work with remoteiot server for some reason, but git's ssh works.
# This script does additional gymnastics to keep working in these conditions.

_start_time_ms=$(($(date +%s%N)/1000000))

# Determine if we're sourced or executed
# { is_sourced=1; script=$(basename "${BASH_SOURCE[0]}"); }; [ "$0" = "${BASH_SOURCE[0]}" ] && { is_sourced=0; script=$(basename "$0"); }
{ is_sourced=0; script=$(basename "$0"); }; ( return 0 2>/dev/null ) && { is_sourced=1; script=$(basename "${BASH_SOURCE[0]}"); }
# echo "DEBUG is_sourced=$is_sourced"

debug=0
# debug=1

parent="$(cd -P -- "$(dirname    "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
parent=${parent%/}  ;## trim trailing slash
caller="$(PWD)"

SOURCE="${caller}"
SOURCE_BASENAME=$(basename "${SOURCE}")

BUILD="${SOURCE}/build"

ssh_secret_file=ssh_secret.txt
which=/usr/bin/which

function find_app () {
  local app; app=$1
  local path; path=$2
  if [ -n "$path" ]; then
    if [ ! -d "$path" ]; then
      # Use parent dir if path is not a directory
      path="$(dirname -- "$path")"
    fi
    if [ -x "${path}/$app" ]; then
      echo "${path}/$app"
      return 0
    fi
  fi
  "$which" "$app"
}
rsync="$($which rsync 2>/dev/null)"
# Try to find all other apps in the same place as rsync (so e.g. ssh keys will be managed in the right installation place in git bash vs. msys bash)
ssh="$(find_app ssh "$rsync" 2>/dev/null)"
scp="$(find_app scp "$rsync" 2>/dev/null)"
ssh_keygen="$(find_app ssh-keygen "$rsync" 2>/dev/null)"
sshpass="$(find_app sshpass "$rsync" 2>/dev/null)"

# Additional location (e.g. git on Windows):
ssh_git="$($which ssh 2>/dev/null)"
ssh_keygen_git="$($which ssh-keygen 2>/dev/null)"

# # Validation mods - uncomment one of the mods line:
# sshpass= ; rsync= ;# scp only
# rsync= ;# sshpass+scp
# scp= ;# rsync only
# ssh_secret_file= ;# Ignore existing secrets file

SCP_DIR=
SCP_CMD=()
do_mkdir=
# SSH_OPTS=()
SSH_OPTS=(-o "StrictHostKeyChecking=accept-new")

export SSHPASSWD=
SSH_SOCKET=
SSH_CTRL=()
pass=
ssh_secret=

user=pi
host=RPI
port=22
host_dir=
SITE=all
do_key=0

function abs_path { echo "$(cd "$(dirname "$1")" || exit; pwd)/$(basename "$1")"; }

# UNUSED
function get_password() {
  local varname; varname=$1
  local PROMPT; PROMPT=${2:-"Enter SSH password"}

  # # non-POSIX-compliant
  # read -r -s -p "$PROMPT: " $varname
  
  # POSIX-compliant
  trap 'stty echo' INT
  stty -echo
  printf "%s: " "$PROMPT"
  read -r "${varname?}"
  export "${varname?}"
  # export RSYNC_PASSWORD=${!varname}
  stty echo
  printf "\n"
}

function ssh_remove_key() {
  maybe_host="$1"
  echo "Removing saved SSH key for $maybe_host..."
  [ -z "$maybe_host" ] && maybe_host="$host"
  "$ssh_keygen" -R "${maybe_host}"
  # TODO: (when needed) To add new key right away, and avoid later prompts, use:  # echo "exit" | ssh "${user}@${host}" -T -oStrictHostKeyChecking=no
  echo "Removed saved SSH key for $maybe_host"
  echo

  if [ "$ssh_keygen" != "$ssh_keygen_git" ]; then
    echo "Removing saved (2) SSH key for $maybe_host..."
    "$ssh_keygen_git" -R "${maybe_host}"
    echo "Removed saved (2) SSH key for $maybe_host"
    echo
  fi
}

function ssh_cleanup_multiplex () {
  local user; user='*'
  local host; host='*'
  local port; port='*'
  local path; path=~/".ssh/*[@]*[+]*[=]*"
  for file in $(echo "$path"); do
    if [ -S "$file" ]; then
      basenm="$(basename "$file")"
      user_at_host="${basenm%%+*}"
      echo "Closing \"$file\" for $user_at_host:"
      ${ssh_git} -S "$file" -O exit "user_at_host"
    fi
  done
  echo "Done cleaning multiplex SSH socket files"
  echo
}

# Parse arguments
#args="$@"
function usage() {
  echo "Usage:"
  echo "$script [-h] | [options]"
  echo "  Copy folder to remote host."
  echo " "
  echo "$script [options] ssh_remove_key [host]"
  echo "  Remove saved SSH host key"
  echo " "
  echo "$script [options] ssh_cleanup"
  echo "  Close and remove SSH multiplex files"
  echo " "
  echo "options:"
  echo "  -h | --help                        show this usage information"
  echo "  -x | --secret=<secret file>        (default \"$ssh_secret_file\")"
  echo "  -u | --user=<user_name>            (default \"pi\")"
  echo "  -a | --host=<host_name_or_ip>      (default \"${host}\")"
  echo "  -p | --port=<ip_port>              (default \"${port}\")"
  echo "  -k | --key                         remove SSH key for the host"
  echo "  -d | --dir=<target_directory>      (default \"/home/<user_name>/${SOURCE_BASENAME}\")"
  echo "  -s | --site=<Site>                 upload only build sub-directory for the selected site (by default upload all sites in ./build/)"
  echo "  -D | --dev                         upload whole project directory for development (by default upload all sites in ./build/)"
  echo "  -c | --cmd=<scp_command>           (default \"scp -pr\" or \"rsync -r -e ssh\" if rsync is installed)"
  #echo "                              Note: (*) Must run with 'sudo'"
  echo
}
while test $# -gt 0; do
  case "$1" in
  ssh_remove_key)
    maybe_host=$2; shift
    [ -z "${maybe_host}" ] && maybe_host=$host
    ssh_remove_key "$maybe_host"
    # shellcheck disable=SC2317
    return 0 2>/dev/null || exit 0
    ;;
  ssh_cleanup)
    ssh_cleanup_multiplex
    # shellcheck disable=SC2317
    return 0 2>/dev/null || exit 0
    ;;
  dev) # Open developer tools
    if [ -n "$(which bcompare 2>/dev/null)" ]; then
      # sudo echo ""
      echo "Opening: bcompare ..."
      # ps ax | grep -v grep | grep -iq bcompare || bcompare &
      pgrep bcompare > /dev/null || bcompare &

      bcompare "${script}".bak "${script}" &
      # bcompare README.txt.bak README.txt &
      # [ -d "$DEV_SRC_" ] && [ -n "$(which code 2>/dev/null)" ] && code $DEV_SRC_
      # echo "Opening: sudo bcompare ..."
      # sudo -b QT_GRAPHICSSYSTEM=native bcompare inst.pkg/ /
      echo
    fi
    # shellcheck disable=SC2317
    return 0 2>/dev/null || exit 0
    ;;
  -D|--dev) # arg is flag
    SITE=for_development
    ;;
  -k|--key) # arg is flag
    do_key=1
    ;;
  -s|--site) # arg with mandatory value
    SITE=$2; shift
    [ -z "${SITE}" ] && { echo "no value specified for -s / --site" >&2; exit 1; }
    [ "for_development" == "${SITE}" ] && { echo "invalid value specified for -s / --site" >&2; exit 1; }
    ;;
  --site=*) # arg with mandatory=value
    SITE="${1#*=}"
    [ -z "${SITE}" ] && { echo "no value specified for --site" >&2; exit 1; }
    [ "for_development" == "${SITE}" ] && { echo "invalid value specified for -s / --site" >&2; exit 1; }
    ;;
  -x|-secret)
    ssh_secret_file=$2; shift
    ;;
  --secret=*) # arg with mandatory=value
    ssh_secret_file="${1#*=}"
    [ -z "${ssh_secret_file}" ] && { echo "no value specified for --secret" >&2; exit 1; }
    ;;
  -a|--host) # arg with mandatory value
    host=$2; shift
    [ -z "${host}" ] && { echo "no value specified for -a / --host" >&2; exit 1; }
    ;;
  --host=*) # arg with mandatory=value
    host="${1#*=}"
    [ -z "${host}" ] && { echo "no value specified for --host" >&2; exit 1; }
    ;;
  -p|--port) # arg with mandatory value
    port=$2; shift
    [ -z "${port}" ] && { echo "no value specified for -p / --port" >&2; exit 1; }
    ;;
  --port=*) # arg with mandatory=value
    port="${1#*=}"
    [ -z "${port}" ] && { echo "no value specified for --port" >&2; exit 1; }
    ;;
  -u|--user) # arg with mandatory value
    user=$2; shift
    [ -z "${user}" ] && { echo "no value specified for -u / --user" >&2; exit 1; }
    ;;
  --user=*) # arg with mandatory=value
    user="${1#*=}"
    [ -z "${user}" ] && { echo "no value specified for --user" >&2; exit 1; }
    ;;
  -d|--dir) # arg with mandatory value
    host_dir=$2; shift
    [ -z "${host_dir}" ] && { echo "no value specified for -p / --path" >&2; exit 1; }
    ;;
  --dir=*) # arg with mandatory=value
    host_dir="${1#*=}"
    [ -z "${host_dir}" ] && { echo "no value specified for --path" >&2; exit 1; }
    ;;
  -c|--cmd) # arg with mandatory value
    SCP_CMD=("$2"); shift
    SCP_DIR=
    [ -z "${SCP_CMD[*]}" ] && { echo "no value specified for -c / --cmd" >&2; exit 1; }
    ;;
  --cmd=*) # arg with mandatory=value
    SCP_CMD=("${1#*=}")
    SCP_DIR=
    [ -z "${SCP_CMD[*]}" ] && { echo "no value specified for --cmd" >&2; exit 1; }
    ;;
  -h|--help)
    usage
    # shellcheck disable=SC2317
    return 0 2>/dev/null || exit 0
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

# scp is finicky to create directory - seems to work only if not renaming the directory
[ -z "${host_dir}" ] && host_dir="/home/${user}"

# Debug:
# [ 1 -eq "$debug" ] && echo "DEBUG script=$script, parent=$parent, is_sourced=$is_sourced, cmd=${SCP_CMD[*]@Q}, user=$user, host=$host, host_dir=$host_dir"
# [ 1 -eq "$debug" ] && echo "DEBUG SOURCE=${SOURCE}"
# [ 1 -eq "$debug" ] && echo "DEBUG BUILD=${BUILD}"

function upload () {
  # Copy files (build package) to host
  local src           ; src=$1
  local host          ; host=$2
  local port          ; port=$3
  local dst           ; dst=$4

  local src_basename  ; src_basename=$(basename "${src}")
  local src_parent    ; src_parent=$(dirname "${src}")

  # [ 1 -eq "$debug" ] && echo "DEBUG src_parent=${src_parent}"
  # [ 1 -eq "$debug" ] && echo "DEBUG src_basename=${src_basename}"
  # [ 1 -eq "$debug" ] && echo "DEBUG Command:"
  # [ 1 -eq "$debug" ] && echo "DEBUG   cd ${src_parent} ; ${SCP_CMD[*]@Q} -pr ${src_basename}/ ${user}@${host}:${dst}"
  echo
  (
    cd "${src_parent}" || exit

    if [ 1 -eq $do_mkdir ]; then
      echo "== Making remote directory '${dst}'"
      SCRIPT="mkdir -p \"${dst}\""
      [ 1 -eq "$debug" ] && echo "DEBUG: $ ${pass:+$pass }${ssh} ${SSH_OPTS[*]} \"${user}@${host}\" \"$SCRIPT\""
      ${pass:+$pass }"${ssh}" "${SSH_OPTS[@]}" "${user}@${host}" -p "$port" "$SCRIPT"
    fi

    echo "== Copying '${src}' directory to '${host}:${dst}'  ..."
    [ 1 -eq "$debug" ] && echo "DEBUG \$ ${SCP_CMD[*]@Q} \"${src_basename}${SCP_DIR}\" \"${user}@${host}:${dst}\" "
    local result;
    "${SCP_CMD[@]}" "${src_basename}${SCP_DIR}" "${user}@${host}:${dst}"
    result=$?
    # [ 1 -eq "$debug" ] && echo "DEBUG result=$result"

    # shellcheck disable=SC2317
    [ 0 -eq "$result" ] || { return "$result" 2>/dev/null || exit "$result"; }
  )
  echo
}

function end_upload () {
  if [ -n "$SSH_SOCKET" ]; then
    # Close master connection:
    ${ssh_git} -S "$SSH_SOCKET" -O exit "${user}@${host}"
    # rm "$SSH_SOCKET" 2>/dev/null
    SSH_SOCKET=
    SSH_CTRL=()
    echo "Closed SSH connection to ${user}@${host}:${port}"
    echo
  fi

  # Cleanup secrets
  export SSHPASSWD=
  pass=
}

function prep_upload () {
  if [ -z "$ssh" ]; then
    echo "$0: 'ssh' command not found, exiting."
    exit 1
  fi

  if [ -n "${SCP_CMD[*]}" ]; then
    [ 1 -eq "$debug" ] && echo "DEBUG: -c/--command arg is given, not using defaults. SCP_CMD=${SCP_CMD[*]@Q}"
    return
  fi

  ssh_secret=$(abs_path "$ssh_secret_file")

  if [ -n "$rsync" ]; then
    # Have rsync, it can make nested directories with --mkpath
    do_mkdir=0
    # SCP_DIR reflects difference between scp and rsync commands - rsync requires directory to NOT have trailing '/'
    SCP_DIR=

    if [ -f "$ssh_secret" ]; then
      # Password in ssh_secret file
      if [ -z "$sshpass" ]; then
        echo "$0: 'sshpass' command not found, exiting."
        exit 1
      fi
      echo "Found file '$ssh_secret', taking password from it."
      pass="$sshpass -f $ssh_secret "
      my_e=(${pass:+$pass} "${ssh}" "${SSH_OPTS[@]}" -p "$port")
      SCP_CMD=("$rsync" --mkpath -raxtz --info=progress2 -e "${my_e[*]}")
    else
      SSH_SOCKET=$(mktemp -q -u ~/".ssh/${user}@${host}+${port}=XXXXXX")
      if [ -z "$SSH_SOCKET" ]; then
        echo "$0: Can't create temp file, exiting."
        exit 1
      fi
      SSH_CTRL=("-o" "ControlPath=${SSH_SOCKET}")
      [ 1 -eq "$debug" ] && echo "DEBUG SSH_SOCKET=$SSH_SOCKET"
      [ 1 -eq "$debug" ] && echo "DEBUG SSH_CTRL=${SSH_CTRL[*]@Q}"

      trap 'end_upload' INT

      echo "Opening SSH connection to ${user}@${host}:${port}..."
      # Open master connection, will ask for the password:
      [ 1 -eq "$debug" ] && echo "DEBUG \$ ${ssh_git} -M -f -N \"${SSH_OPTS[*]}\" ${SSH_CTRL[*]@Q} -o ControlPersist=yes \"${user}@${host}\" -p $port"
      # Broken: ${ssh} -M -f -N "${SSH_OPTS[@]}" $SSH_CTRL -o ControlPersist=yes "${user}@${host}" -p "$port"
      ${ssh_git} -M -f -N "${SSH_OPTS[@]}" "${SSH_CTRL[@]}" -o ControlPersist=yes "${user}@${host}" -p "$port"
      # ${ssh} -vvv -M -f -N "${SSH_OPTS[@]}" "${SSH_CTRL[@]}" -o ControlPersist=yes "${user}@${host}" -p "$port"
      # echo "DEBUG Muliplex connection created using \"$SSH_SOCKET\""
      if [ -S "$SSH_SOCKET" ]; then
        echo "Opened SSH connection to ${user}@${host}:${port}."
      else
        echo "$0: Aborted or Can't make SSH connection, exiting."
        exit 1
      fi
      # Subsequent conections will use the master, won't ask for the password.

      # `-O proxy` fixes ControlMaster use on Windows, see https://github.com/PowerShell/Win32-OpenSSH/issues/405#issuecomment-1481385347
      # first added in openssh (1:7.4p1-1) 2016-12-19
      my_e=("${ssh}" "${SSH_OPTS[@]}" ${SSH_CTRL[*]} "-O" "proxy")
      SCP_CMD=("$rsync" --mkpath -raxtz --info=progress2 -e "${my_e[*]}")
    fi
  elif [ -n "$scp" ]; then
    # No rsync, use scp
    
    if [ -n "$sshpass" ]; then
      # Prepare password and feed it into SSH using `sshpass`
      if [ -f "$ssh_secret" ]; then
        # Password in ssh_secret file
        echo "Found file '$ssh_secret', taking password from it."
        pass="$sshpass -f $ssh_secret "
      else
        # Get password into SSHPASSWD env variable
        get_password SSHPASSWD "Enter SSH password for ${user}@${host}"
        # pass="$sshpass -eSSHPASSWD " ;# Does not work!  # TODO: (when needed) Fix sshpass not working with scp under VSCode on windows.
        pass=" $sshpass -p $SSHPASSWD " ;# Works. But it is UNSECURE! Note the space before the command - to at least hide it from bash history.
      fi
    else
      pass=""
      echo
      echo "Note: To enter password only once, or keep it in secrets file \"ssh_secret\", install \"sshpass\""
      echo "Even better, install \"rsync\""
      echo
    fi

    do_mkdir=1 ;# scp cannot make nested directories on the path to the destination target.
    SCP_CMD=(${pass:+$pass} "${scp}" -pr "${SSH_OPTS[@]}" -P "$port")
    # SCP_DIR reflects difference between scp and rsync commands - scp requires directory to have trailing '/'
    SCP_DIR=/
  else
    echo "$0: Neither 'rsync' nor 'scp' is found, exiting."
    exit 1
  fi
  [ 1 -eq "$debug" ] && echo "DEBUG prep_upload() ssh_secret=$ssh_secret SSHPASSWD=$SSHPASSWD SSH_SOCKET=$SSH_SOCKET SSH_CTRL=${SSH_CTRL[*]@Q} ssh=$ssh scp=$scp sshpass=$sshpass rsync=$rsync do_mkdir=$do_mkdir SCP_CMD=${SCP_CMD[*]@Q} SCP_DIR=$SCP_DIR"
}

function print_info () {
  echo "  INFO script=$script, is_sourced=$is_sourced"
  
  local args; args=(
    ssh_secret_file
    which
    ssh
    ssh_git
    scp
    ssh_keygen
    ssh_keygen_git
    sshpass
    rsync
    user
    host
    host_dir
    SITE
    do_key
    caller
    BUILD
    SOURCE
  )

  for arg in "${args[@]}"; do
    # Get values of Array and non-Array variables
    all_elems_indirection="${arg}[@]"
    vals="${!all_elems_indirection}"
    printf "%24s = %s\r  %s \n" "" "${vals}" "$arg"
  done
  echo
}

[ 1 -eq "$debug" ] && print_info
[ 1 -eq "$is_sourced" ] && return 0

[ 1 -eq "$do_key" ] && ssh_remove_key "$host"

prep_upload
case "$SITE" in
  all)
    upload "$BUILD" "$host" "$port" "${host_dir}/pi-base/"
    ;;
  for_development)
    upload "$SOURCE" "$host" "$port" "${host_dir}/"
    ;;
  *)
    # [ 1 -eq "$debug" ] && echo "DEBUG checking site=$SITE dir=$BUILD/$SITE"
    if [ ! -d "$BUILD/$SITE" ]; then
      echo "Directory '$BUILD/$SITE' for site '$SITE' is not found in build. If it is a valid site, was build for that site done?" >&2; exit 1;
    fi
    upload "$BUILD/$SITE" "$host" "$port" "${host_dir}/pi-base/build/"
  ;;
esac
end_upload

_run_time_ms=$(( $(date +%s%N)/1000000 - _start_time_ms ))
echo "DONE. Elapsed time ${_run_time_ms%???}.${_run_time_ms: -3}s"
