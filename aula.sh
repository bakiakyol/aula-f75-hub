#!/bin/sh
# Run from anywhere: ./aula.sh info
cd "$(dirname "$(readlink -f "$0")")" && exec python3 -m aula "$@"
