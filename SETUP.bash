#!/bin/bash
#
# readlink
if [[ $(uname) == *"Darwin"* ]]; then
    function readlink() {
        if [[ $# -gt 1 ]]; then if [[ "$1" == "-f" ]]; then shift; fi; fi
        DIR="$1"; if [[ "$DIR" != *"/"* ]]; then DIR="./$DIR"; fi # 20170228: fixed bug: path without "/"
        DIR=$(echo "${DIR%/*}") # 20160410: fixed bug: source SETUP just under the Softwares dir
        if [[ -d "$DIR" ]]; then cd "$DIR" && echo "$(pwd -P)/$(basename ${1})"; 
        else echo "$(pwd -P)/$(basename ${1})"; fi
    }
fi
CRABTOOLKITCAAP=$(dirname $(readlink -f "${BASH_SOURCE[0]}"))
export CRABTOOLKITCAAP
#
# PATH
if [[ $PATH != *"$CRABTOOLKITCAAP/bin"* ]]; then
    export PATH="$CRABTOOLKITCAAP/bin":$PATH
fi
#
# LIST
CRABTOOLKITCMD=("alma-sky-coverage.py")
# 
# CHECK
# -- 20160427 only for interactive shell
# -- http://stackoverflow.com/questions/12440287/scp-doesnt-work-when-echo-in-bashrc
if [[ $- =~ "i" ]]; then 
  for TEMPTOOLKITCMD in ${CRABTOOLKITCMD[@]}; do
    type $TEMPTOOLKITCMD
  done
fi


