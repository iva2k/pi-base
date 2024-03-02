#!/usr/bin/env bash

# Compare python package (extracted) to the original files, excluding:
#  - *.md
# 
SOURCE=pi_base
# Auto-extract version and set $BUILD correctly:
VER=$(python -m setuptools_scm)
BUILD=dist/pi_base-${VER}/pi_base

all_diffs=$(
  diff -u \
    <(cd "$SOURCE" && find . -type f ! -name '*.py[cod]' ! -name '*.md' ! -path '*/__pycache__/*' ! -path '*/pictures*' ! -path '*/scripts/*' ! -path '*/tests/*' ! -path '*/remoteiot.com/*' | sort) \
    <(cd "$BUILD"  && find . -type f ! -name '*.py[cod]' ! -name '*.md' ! -path '*/__pycache__/*' | sort) \
  | grep -v -e '^---' | grep -v -e '^+++'
)
diffs=$(
  echo "$all_diffs" \
  | grep -E '^([-+])'
  # | grep -E '^([<>]|---)'
)
diffs_cnt=$(echo -n "$diffs" | wc -l)

if [ "$diffs_cnt" -eq 0 ]; then 
  echo "Package content matches sources"
else
  echo "Error: found $diffs_cnt file(s) different:" >&2
  echo "'$diffs'" >&2
fi
exit "$diffs_cnt"
