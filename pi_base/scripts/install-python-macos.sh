#!/usr/bin/env bash

PY_VER=3.9.4
#PY_VER=3.9.16

# Must be NOT root
if [ "$(id -u)" -eq 0 ]; then
  echo "Script must be run NOT as root. Try '$0 $*' (without sudo)"
  exit 1
fi

# Install Homebrew if not yet installed
[ -x "$(which brew 2>/dev/null)" ] || { xcode-select --install; /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; }

# Install pyenv
brew install pyenv 

# Add pyenv to manage $PATH
[ -f ~/.zshrc        ] && { echo -e 'if command -v pyenv 1>/dev/null 2>&1; then\n  eval "$(pyenv init -)"\nfi' >> ~/.zshrc          ; }
[ -f ~/.bash_profile ] && { echo -e 'if command -v pyenv 1>/dev/null 2>&1; then\n  eval "$(pyenv init -)"\nfi' >> ~/.bash_profile   ; }

# Add virtualenvwrapper: # TBD - not sure if it is useful

# Do a brew install:
PY_VER2="$(echo "$PY_VER" | awk -F. '{print $1 "." $2}')"
# IFS="." read -ra parts <<< "$PY_VER"; PY_VER2="${parts[0]}.${parts[1]}"

brew install "python@$PY_VER2"

# # Do a temporary pyenv install:
# pyenv install $PY_VER
# pyenv global $PY_VER
# # and verify it worked 
# pyenv version

# Can use user-space python

# pyenv uninstall -f $PY_VER

# Link brew python into pyenv:
(cd "$(brew --prefix "python@$PY_VER2")"     || exit; 
  ln -sfv . ~/.pyenv/versions/$PY_VER
  ln -sfv "Frameworks/Python.framework/Versions/$PY_VER2/include/python$PY_VER2" include)
(cd "$(brew --prefix "python@$PY_VER2")/bin" || exit
  ln -sfv "idle$PY_VER2" idle3
  ln -sfv "pip$PY_VER2" pip3
  ln -sfv "python$PY_VER2" python3
  ln -sfv "wheel$PY_VER2" wheel3
  ln -sfv idle3 idle
  ln -sfv pip3 pip
  ln -sfv python3 python
  ln -sfv wheel3 wheel)

pyenv rehash
pyenv global $PY_VER

# Upgrade pip:
python3 -m pip install --upgrade pip

(
echo "DONE."
echo "INSTALLED PYTHON VERSIONS:"
pyenv versions
echo
echo "PYTHON3:"
which python3
echo "PYTHON3 VERSION:"
python3 --version
echo
echo "PIP3:"
which pip3
echo "PIP3 VERSION:"
pip3 --version
)