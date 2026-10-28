#!/bin/sh
# Runs inside industreal/direct-proof:1 (run.sh): Weston headless (GL), $BIN with the given args,
# one screenshot after $AFTER s to $OUT; prints the tail of the application log.
set -u
export XDG_RUNTIME_DIR=/tmp/xdg; mkdir -p $XDG_RUNTIME_DIR; chmod 700 $XDG_RUNTIME_DIR
export LIBGL_ALWAYS_SOFTWARE=1
weston --backend=headless --renderer=gl --width=1280 --height=800 --shell=kiosk --debug \
  --socket=wayland-1 --idle-time=0 >/tmp/weston.log 2>&1 &
wpid=$!
for i in $(seq 50); do [ -S $XDG_RUNTIME_DIR/wayland-1 ] && break; sleep 0.1; done
export WAYLAND_DISPLAY=wayland-1
$BIN --display-driver wayland --rendering-driver opengl3 "$@" >/tmp/app.log 2>&1 &
apid=$!
sleep ${AFTER:-6}
cd /tmp && rm -f wayland-screenshot*.png && weston-screenshooter >/tmp/ss.log 2>&1
f=$(ls /tmp/wayland-screenshot*.png 2>/dev/null | head -1)
[ -n "$f" ] && cp "$f" "$OUT" || { echo "no screenshot"; cat /tmp/ss.log; }
kill $apid 2>/dev/null; sleep 0.3; kill $wpid 2>/dev/null
echo "--- app log"; grep -vE "^\s*$" /tmp/app.log | tail -${LOGN:-15}
[ -n "${WLOG:-}" ] && { echo "--- weston log"; tail -20 /tmp/weston.log; }
true
