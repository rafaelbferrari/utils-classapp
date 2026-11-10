#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if [[ ! -x .venv-pessoas/bin/python ]]; then
  print 'Execute primeiro Instalar reconhecimento.command. Enter para fechar.'
  read resposta
  exit 1
fi
print 'Pasta de origem: arraste a pasta de fotos para esta janela e pressione Enter.'
print 'Execute depois que os downloads terminarem.'
IFS= read -r origem
# Arrastar do Finder usa escape de espaços; (Q) remove somente as aspas/escapes, sem executar comandos.
origem=${(Q)origem}
if [[ -z "$origem" ]]; then
  print 'Nenhuma pasta informada. Encerrado.'
  exit 1
fi
.venv-pessoas/bin/python separar_pessoas.py "$origem"
resultado=$?
print '\nPressione Enter para fechar.'
read resposta
exit $resultado
