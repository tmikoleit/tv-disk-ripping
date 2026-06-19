#!/bin/bash
# Wrapper script to run disk ripping automation tool from Operational folder
# Usage: ./run_process.sh community 1 2

cd "$(dirname "$0")/Operational"
python3 process_rips.py "$@"
