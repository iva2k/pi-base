#!/usr/bin/env bash

CONF_FILE="p_scm.toml"

function git_version() {
  echo -e '# DO NOT EDIT!\n# Automatic clone of pyproject.toml for hacky use of setuptools_scm SCM versioning\n[tool.setuptools_scm]\n\n' > "$CONF_FILE" && cat "pyproject.toml" >> "$CONF_FILE" && python3 -m setuptools_scm "--config=$CONF_FILE"
}

git_version "$@"