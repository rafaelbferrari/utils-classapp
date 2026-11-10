#!/bin/zsh
cd -- "${0:A:h}" || exit 1
print 'Start date (YYYY-MM-DD; Enter for full history):'
read inicio
print 'End date (YYYY-MM-DD; Enter for the latest):'
read fim
filtros=()
[[ -n "$inicio" ]] && filtros+=(--from "$inicio")
[[ -n "$fim" ]] && filtros+=(--to "$fim")
python3 baixar_momentos.py --curl .private/session.curl "${filtros[@]}"
result=$?
print '\nPress Enter to close.'
read answer
exit $result
