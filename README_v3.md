# V3 — download acelerado

1. Se a v2 ainda estiver rodando, encerre-a com Control+C no Terminal.
2. Abra **Baixar fotos rapido.command**.
3. Informe o intervalo de datas e o número de fotos simultâneas (Enter = 12).

A v3 usa **fotos_v2** e seu índice por padrão: reaproveita as fotos já baixadas e verificadas. Mantém a gravação das datas da v2. Os scripts anteriores não foram alterados por esta versão e continuam disponíveis.

## O que ficou mais rápido

Até doze fotos são baixadas e processadas em paralelo por padrão; pode configurar de 1 a 16. Foi removida a pausa fixa de 150 ms entre fotos. O índice é atualizado por um único coordenador, a cada 10 fotos e ao finalizar cada lote/página, inclusive em falhas tratadas. Cada trabalhador usa uma conexão HTTP independente e arquivo temporário próprio.

Consultas de publicações continuam sequenciais. O script ainda precisa percorrer o histórico do mais recente até o período solicitado. Por isso, o ganho maior aparece quando ele chega às fotos do intervalo. O ganho real depende da conexão, do ClassApp, do disco e do processamento de metadados; não foi medido contra o serviço real.

## Terminal

```sh
python3 baixar_momentos_v3.py --curl .private/session.curl --de 2024-01-01 --ate 2024-01-31 --simultaneos 12
```

Se houver muitas falhas, reduza para `--simultaneos 2`. A autenticação, os filtros de publicação, os metadados e a resolução w1280 seguem a v2. O arquivo de diagnóstico continua sendo `erros_download.log`.

A v3 recusa iniciar se encontrar um downloader v1/v2 em execução e bloqueia duas v3 no mesmo destino. Não inicie a v1/v2 enquanto a v3 estiver rodando: versões antigas não conhecem a nova trava. Não ajuste datas nem analise rostos nessa mesma pasta durante o download.

Ao interromper com Control+C, a execução pode aguardar as requisições já em andamento terminarem. Uma queda abrupta pode deixar até um pequeno lote sem registro; ao retomar, essas fotos podem ser baixadas de novo. O índice é substituído de forma atômica.

Testes locais: concorrência limitada, preservação dos sucessos quando um trabalhador falha, metadados e retomada. Usaram fotos artificiais e rede simulada, sem processar a pasta de fotos existente.

## Timer de recuperação automática

Depois que uma imagem ou consulta esgotar as seis tentativas de rede, a v3 aguarda **60 segundos**, com contagem regressiva, e tenta a mesma operação novamente. A recuperação ocorre dentro do processo: não volta à primeira página e não baixa de novo as fotos que já foram registradas. Outros trabalhadores podem continuar enquanto uma imagem aguarda. As esperas continuam até a rede voltar ou você interromper com Control+C.

A cada requisição, o tempo máximo de espera por resposta permanece 120 segundos. Portanto, a contagem de 60 segundos começa somente depois de esgotadas as tentativas iniciais.

Erros de autenticação, falta de espaço/permissão, configuração, metadados e HTTP não temporário encerram a execução. Uma espera não resolve esses casos. Para evitar recuperação indefinida, configure um limite de reinícios por operação:

```sh
python3 baixar_momentos_v3.py --curl .private/session.curl --reiniciar-em 60 --max-reinicios 5
```

`--max-reinicios 0` (padrão) significa sem limite. `--reiniciar-em 120` muda o intervalo para dois minutos. Uma execução que já estava aberta precisa ser encerrada e iniciada novamente para receber esta alteração.
