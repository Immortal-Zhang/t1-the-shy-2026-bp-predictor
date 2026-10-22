#!/bin/bash
cd "$(dirname "$0")"
./start.sh
status=$?
if [[ "$status" != 0 ]]; then read -r -p 'Startup failed. Press Enter to close. ' _; fi
exit "$status"
