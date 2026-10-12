#!/bin/bash
# Integration test: run-in-background + Shell search provider, in an isolated headless GNOME (private runtime dir, see dnd-test.sh).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
RT=$(mktemp -d /tmp/painel-rt.XXXXXX); chmod 700 "$RT"
OUT=$(mktemp -d)
trap 'rm -rf "$RT" "$OUT"' EXIT
XDG_RUNTIME_DIR=$RT dbus-run-session -- "$HERE/run.sh" "$OUT" "$HERE/bg_driver.py" 2>&1 | grep -E "^PASS|^FAIL|^RESULT|Traceback|Error|File "
