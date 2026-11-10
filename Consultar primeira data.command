#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 consultar_primeira_data.py
resultado=$?
print '\nPress Enter to close.'
read resposta
exit $resultado
