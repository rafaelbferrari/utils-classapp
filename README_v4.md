# V4 — até 32 downloads simultâneos

Abra **Baixar fotos turbo.command**, informe as datas e a quantidade de fotos simultâneas (1 a 32). Enter mantém o padrão de **12**.

Para experimentar mais concorrência, comece com 20 ou 24 e compare fotos baixadas por minuto. Mais conexões não garantem mais velocidade: metadados, rede e resposta do servidor também influenciam. Consultas ao histórico continuam sequenciais.

A v4 mantém os metadados, a recuperação automática de falhas e o índice da v3. Usa `fotos_v2` por padrão e reaproveita fotos já salvas. A v3 não foi alterada. As duas versões compartilham a trava do destino, portanto **encerre a execução atual e aguarde seu término antes de iniciar a v4**.

```sh
python3 baixar_momentos_v4.py --curl .private/session.curl --simultaneos 24 --de 2025-01-01
```

Demais detalhes: README_v3.md. A validação desta mudança foi local, sem executar downloads reais nem processar a pasta existente.
