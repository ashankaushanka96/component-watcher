#!/bin/sh

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

numproc=`ps x | grep -ai all_in_one_watcher.py | grep -v "grep" | wc -l`
if [ $numproc -lt 1 ]
then
cd "$SCRIPT_DIR"
./run.sh
fi

