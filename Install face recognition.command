#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 -m venv .venv-pessoas &&
.venv-pessoas/bin/python -m pip install -r requirements-pessoas.txt &&
.venv-pessoas/bin/python separar_pessoas.py --prepare-models
resultado=$?
print '\nInstallation finished. No photo directories were processed. Press Enter to close.'
read resposta
exit $resultado
