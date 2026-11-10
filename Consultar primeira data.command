#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 consultar_primeira_data.py
resultado=$?
print '\nPressione Enter para fechar.'
read resposta
exit $resultado
