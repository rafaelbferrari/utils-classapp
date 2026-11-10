#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 -m venv .venv-pessoas &&
.venv-pessoas/bin/python -m pip install -r requirements-pessoas.txt &&
.venv-pessoas/bin/python separar_pessoas.py --preparar-modelos
resultado=$?
print '\nInstalação encerrada. Nenhuma pasta de fotos foi processada. Enter para fechar.'
read resposta
exit $resultado
