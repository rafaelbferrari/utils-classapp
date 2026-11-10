#!/bin/zsh
cd -- "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
print 'Versão 2 — datas nas fotos; destino: fotos_v2'
print '1 = baixar da API | 2 = copiar e ajustar fotos já baixadas pela v1'
read modo
print 'Data inicial (AAAA-MM-DD; Enter para sem limite):'
read inicio
print 'Data final (AAAA-MM-DD; Enter para sem limite):'
read fim
filtros=()
[[ -n "$inicio" ]] && filtros+=(--de "$inicio")
[[ -n "$fim" ]] && filtros+=(--ate "$fim")
case "$modo" in
  1) python3 baixar_momentos_v2.py --curl .private/session.curl "${filtros[@]}" ;;
  2) python3 baixar_momentos_v2.py --importar-v1 fotos "${filtros[@]}" ;;
  *) print 'Opção inválida. Escolha 1 ou 2.' ;;
esac
print '\nPressione Enter para fechar.'
read resposta
