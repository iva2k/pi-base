#!/usr/bin/env bash

# Compare python package (extracted) to the original files, excluding:
#  - *.md
# 
SOURCE=pi_base

debug=0
# debug=1

# Determine if we're sourced or executed
# [ "$0" = "${BASH_SOURCE[0]}" ] && { is_sourced=0; script=$(basename "$0"); } || { is_sourced=1; script=$(basename "${BASH_SOURCE[0]}"); }
( return 0 2>/dev/null ) && { is_sourced=1; script=$(basename "${BASH_SOURCE[0]}"); } || { is_sourced=0; script=$(basename "$0"); }

parent="$(cd -P -- "$(dirname    "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
parent=${parent%/}  ;## trim trailing slash

SOURCE="$(dirname "${parent}")"
# SOURCE_BASENAME=$(basename "${SOURCE}")

WORKSPACE="$(dirname "${SOURCE}")"

# BUILD="${SOURCE}/build"

# Auto-detect version, find the package file, extract and set $BUILD/$BUILD_EXTR correctly:
BUILD=
BUILD_EXTR=
# VER=$(python -m setuptools_scm)
VERS=(
  "$("$parent/get-git-version.sh" )"
  "$(python3 "$SOURCE/_version.py" current )"
)
for VER in "${VERS[@]}"; do

  BUILD="$WORKSPACE/dist/pi_base-${VER}.tar.gz"
  BUILD_EXTR="$WORKSPACE/dist/pi_base-${VER}/pi_base"
  if [ -f "${BUILD}" ]; then
    # Extract .tar.gz
    [ -d "${BUILD_EXTR}" ] || { rm -rf "${BUILD_EXTR}"; }
    (cd "$WORKSPACE/dist" && tar -zxvf "$BUILD" >/dev/null 2>&1)
    [ -d "${BUILD_EXTR}" ] || { echo "Directory $BUILD_EXTR not found in the extracted package."; exit 1; }
    break
  fi
done

all_diffs=$(
  diff -u \
    <(cd "$SOURCE" && find . -type f ! -name '*.py[cod]' ! -name '*.md' ! -path '*/__pycache__/*' ! -path '*/wpa_supplicant.conf' ! -path '*/scripts/*' ! -path '*/remoteiot.com/*' | sort) \
    <(cd "$BUILD_EXTR"  && find . -type f ! -name '*.py[cod]' ! -name '*.md' ! -path '*/__pycache__/*' | sort) \
  | grep -v -e '^---' | grep -v -e '^+++'
)
diffs=$(
  echo "$all_diffs" \
  | grep -E '^([-+])'
  # | grep -E '^([<>]|---)'
)
diffs_cnt=$(echo -n "$diffs" | wc -l)

if [ "$diffs_cnt" -eq 0 ]; then 
  echo "Package ${BUILD} content matches sources"
else
  echo "Error: found $diffs_cnt file(s) different in ${BUILD} content:" >&2
  echo "'$diffs'" >&2
fi

function print_info () {
  echo "  INFO script=$script, is_sourced=$is_sourced"
  
  local args; args=(
      debug
      is_sourced
      script
      parent
      SOURCE
      # SOURCE_BASENAME
      WORKSPACE
      BUILD
      VERS
      VER
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


exit "$diffs_cnt"
