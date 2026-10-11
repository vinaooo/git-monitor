#!/bin/bash
# usage: run.sh <outdir> <driver.py> [args...]   (runs inside dbus-run-session)
OUT=$1; DRIVER=$2; shift 2
export XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=GNOME
gnome-shell --headless --wayland --no-x11 --wayland-display=painel-test --virtual-monitor 1280x800 > "$OUT/shell.log" 2>&1 &
SHELL_PID=$!
for i in $(seq 1 40); do [ -S "$XDG_RUNTIME_DIR/painel-test" ] && break; sleep 0.5; done
sleep 4
WAYLAND_DISPLAY=painel-test GDK_BACKEND=wayland GTK_IM_MODULE= timeout 90 python3 "$DRIVER" "$@" 2>&1 | grep -v "IM module"
kill $SHELL_PID 2>/dev/null; wait $SHELL_PID 2>/dev/null
