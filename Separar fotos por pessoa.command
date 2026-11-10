#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if [[ ! -x .venv-pessoas/bin/python ]]; then
  print 'Run Install face recognition.command first. Press Enter to close.'
  read resposta
  exit 1
fi
print 'Source directory: drag the photo directory into this window and press Enter.'
print 'Run after downloads have finished. AdaFace creates a separate SOURCE_por_pessoa_v2 output.'
print 'Run Install face recognition.command again if upgrading from SFace.'
IFS= read -r origem
# Finder escapes spaces when dragging; (Q) removes quoting without executing commands.
origem=${(Q)origem}
if [[ -z "$origem" ]]; then
  print 'No directory supplied. Exiting.'
  exit 1
fi
.venv-pessoas/bin/python separar_pessoas.py "$origem"
resultado=$?
print '\nPress Enter to close.'
read resposta
exit $resultado
