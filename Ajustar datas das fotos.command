#!/bin/zsh
cd -- "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
python3 ajustar_datas_pastas.py . "$@"
resultado=$?
print '\nPressione Enter para fechar.'
read resposta
exit $resultado
