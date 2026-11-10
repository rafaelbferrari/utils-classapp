#!/bin/zsh
cd -- "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
print 'Download acelerado — retoma fotos_v2 e preserva os ajustes de datas.'
print 'Falhas temporárias: reinício automático em 60 segundos, na mesma foto.'
print 'Encerre a v2 com Control+C antes de iniciar este download.'
print 'Data inicial (AAAA-MM-DD; Enter para sem limite):'
read inicio
print 'Data final (AAAA-MM-DD; Enter para sem limite):'
read fim
print 'Quantas fotos simultâneas? 1 a 16 (Enter = 12):'
read quantidade
quantidade=${quantidade:-12}
filtros=()
[[ -n "$inicio" ]] && filtros+=(--de "$inicio")
[[ -n "$fim" ]] && filtros+=(--ate "$fim")
python3 baixar_momentos_v3.py --curl .private/session.curl --simultaneos "$quantidade" "${filtros[@]}"
resultado=$?
print '\nPressione Enter para fechar.'
read resposta
exit $resultado
