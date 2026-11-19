#!/bin/bash
# Finder starts .command files in Terminal with a minimal PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")" || exit 1
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PYTHON_BIN="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo 'InstaComment needs Python 3.11 or newer.'
  echo 'Install Python from https://www.python.org/downloads/macos/ and reopen this launcher.'
  read -r -p 'Press Return to close.'
  exit 1
fi
"$PYTHON_BIN" scripts/launcher.py "$@"
status=$?
if [ "$status" -ne 0 ]; then
  echo
  read -r -p 'InstaComment stopped. Press Return to close.'
fi
exit "$status"
