#!/bin/bash
# Real sidebar group drag in an isolated headless GNOME Shell (see dnd-test.sh for why the runtime dir is private).
# usage: group-dnd-test.sh [screenshot.png]
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
RT=$(mktemp -d /tmp/painel-rt.XXXXXX); chmod 700 "$RT"
OUT=$(mktemp -d)
trap 'rm -rf "$RT" "$OUT"' EXIT
XDG_RUNTIME_DIR=$RT dbus-run-session -- "$HERE/run.sh" "$OUT" "$HERE/group_dnd_driver.py" "$@" 2>&1 | grep -E "^variant|^during|^after|^RESULT|Traceback|Error|Warning|Critical"
