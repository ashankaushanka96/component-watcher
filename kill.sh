#!/bin/sh

COMPNAME="all_in_one_watcher.py"

PID=`ps -ef | grep -vw grep | grep -w $COMPNAME | awk '{print $2}'`

if [ -n "$PID" ] ;then
    kill -9 $PID
fi

exit 0