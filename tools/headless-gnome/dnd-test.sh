#!/bin/bash
# Real drag-and-drop test in an isolated headless GNOME Shell. Everything (D-Bus, portals, wayland socket) lives in
# a private XDG_RUNTIME_DIR: sharing the real one makes the nested xdg-document-portal unmount the user's
# /run/user/$UID/doc and breaks `flatpak run` ("bwrap: Can't find source path .../doc/by-app/...").
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
RT=$(mktemp -d /tmp/painel-rt.XXXXXX); chmod 700 "$RT"
OUT=$(mktemp -d)
trap 'rm -rf "$RT" "$OUT"' EXIT
XDG_RUNTIME_DIR=$RT dbus-run-session -- "$HERE/run.sh" "$OUT" "$HERE/dnd_driver.py" "${1:-current}" 2>&1 | grep -E "^variant|^during|^after|^RESULT|Traceback|Error"
