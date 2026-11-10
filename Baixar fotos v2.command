#!/bin/zsh
cd -- "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
print 'Version 2 — photo dates; destination: fotos_v2'
print '1 = download from API | 2 = copy and update photos already downloaded by v1'
read modo
print 'Start date (YYYY-MM-DD; Enter for no limit):'
read inicio
print 'End date (YYYY-MM-DD; Enter for no limit):'
read fim
filtros=()
[[ -n "$inicio" ]] && filtros+=(--from "$inicio")
[[ -n "$fim" ]] && filtros+=(--to "$fim")
case "$modo" in
  1) python3 baixar_momentos_v2.py --curl .private/session.curl "${filtros[@]}" ;;
  2) python3 baixar_momentos_v2.py --import-v1 fotos "${filtros[@]}" ;;
  *) print 'Invalid option. Choose 1 or 2.' ;;
esac
print '\nPress Enter to close.'
read resposta
