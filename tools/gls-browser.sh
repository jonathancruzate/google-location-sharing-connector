#!/bin/bash
# Launcher for the local open-source Chromium sign-in driver.
# Starts the local CONNECT forwarder if it is not already listening,
# then runs one driver step under Xvfb.
set -e
cd "$(dirname "$0")"
if ! (exec 3<>/dev/tcp/127.0.0.1/18080) 2>/dev/null; then
  nohup ./venv/bin/python local_proxy.py > proxy.log 2>&1 &
  sleep 1
fi
export GLS_CHROMIUM_EXE="${GLS_CHROMIUM_EXE:-$(pwd)/chromium-snapshot/chrome-linux/chrome}"
exec timeout "${GLS_TIMEOUT:-150}" xvfb-run -a ./venv/bin/python drive_signin.py "${1:-state}"
