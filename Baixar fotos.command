#!/bin/zsh
cd -- "${0:A:h}" || exit 1
print 'Data inicial (AAAA-MM-DD; Enter para todo o histórico):'
read inicio
print 'Data final (AAAA-MM-DD; Enter para a mais recente):'
read fim
filtros=()
[[ -n "$inicio" ]] && filtros+=(--de "$inicio")
[[ -n "$fim" ]] && filtros+=(--ate "$fim")
python3 baixar_momentos.py --curl .private/session.curl "${filtros[@]}"
result=$?
print '\nPressione Enter para fechar.'
read answer
exit $result
