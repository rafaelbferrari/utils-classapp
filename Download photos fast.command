#!/bin/zsh
cd -- "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
print 'Fast download — resume fotos_v2 and preserve date metadata.'
print 'Temporary failures: retry the same photo automatically after 60 seconds.'
print 'Stop v2 with Control+C before starting this download.'
print 'Start date (YYYY-MM-DD; Enter for no limit):'
read inicio
print 'End date (YYYY-MM-DD; Enter for no limit):'
read fim
print 'Concurrent photos? 1 to 16 (Enter = 12):'
read quantidade
quantidade=${quantidade:-12}
filtros=()
[[ -n "$inicio" ]] && filtros+=(--from "$inicio")
[[ -n "$fim" ]] && filtros+=(--to "$fim")
python3 baixar_momentos_v3.py --curl .private/session.curl --concurrent "$quantidade" "${filtros[@]}"
resultado=$?
print '\nPress Enter to close.'
read resposta
exit $resultado
