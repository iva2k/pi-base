#!/usr/bin/env bash

PRINTER=ZT411

# Few Level Heading Separators for Nice Log (carriage return at the end allows
#  echo "${SEP2}SOME HEADER " to print ---> "SOME HEADER ###########")
SEP1="$(printf "%100s\r" "" | tr ' ' '#')"
SEP2="$(printf "%100s\r" "" | tr ' ' '=')"
# SEP3="$(printf "%100s\r" "" | tr ' ' '-')"

echo "${SEP2}ADD - SHOW RESULT: PRINTERS - LIST "
python3 printer.py printers
# Shows sub-command output - list of NEWLY added printers

echo "${SEP2}PRINT - ACTION : PDF"
python3 printer.py print $PRINTER printer-test-label.pdf
# Shows sub-command action - prints the file, shows result

echo "${SEP2}PRINT - ACTION : PNG"
python3 printer.py print $PRINTER printer-test-label.png
# Shows sub-command action - prints the file, shows result
