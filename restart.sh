#!/bin/sh

DIR="$( cd -P "$( dirname "$0" )" && pwd )"

cd $DIR

./kill.sh

sleep 2

./run.sh

sleep 2

exit 0