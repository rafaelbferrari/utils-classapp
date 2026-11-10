# Fotos de Momentos do ClassApp

Script Python 3 que consulta a API GraphQL usada pelo site e baixa as fotos por HTTP. Sem automação de cliques, IA ou consumo de tokens na execução. Usa somente o perfil da requisição autenticada fornecida.

## Executar

Dê dois cliques em **Baixar fotos.command** e informe as datas inicial e final, ou pressione Enter para deixar cada limite em aberto. Ou use o Terminal nesta pasta:

```sh
python3 baixar_momentos.py --curl .private/session.curl
```

As fotos ficam em `fotos/`, separadas pela data de publicação. `fotos/indice.json` registra os IDs, tamanhos e hashes. Se interromper, execute novamente: o script confere os arquivos e pula os que já estão íntegros. A consulta reinicia da primeira página para não perder publicações novas.

## Renovar a sessão quando expirar

1. No Chrome, com sua conta aberta em **Momentos**, abra as ferramentas do desenvolvedor (`Option + Command + I`) e a aba **Network**.
2. Recarregue a página e filtre por `graphql`.
3. Localize a chamada POST cujo **Payload** tem `operationName: EntityMomentsQuery`.
4. Clique com o botão direito nessa chamada e escolha **Copy → Copy as cURL**.
5. No Terminal desta pasta, execute:

```sh
pbpaste | python3 baixar_momentos.py --curl -
```

Esse comando lê a requisição da área de transferência e mantém as credenciais apenas na memória do processo. Não cole essa requisição em chats: ela contém sua autorização de acesso. O script interpreta o texto cURL sem executá-lo como comando.

Se você salvar uma sessão local, use a pasta `.private`, excluída do Git. Nenhuma sessão é distribuída neste repositório. Pode expirar; a captura não implementa login nem renovação automática. O cabeçalho DPoP capturado funcionou no teste, mas poderá exigir nova captura se o servidor mudar sua validação.

## Opções

```sh
# Contar todas as publicações/fotos disponíveis, sem baixar
python3 baixar_momentos.py --curl .private/session.curl --listar

# Baixar até duas fotos novas para teste
python3 baixar_momentos.py --curl .private/session.curl --max-fotos 2

# Testar somente a página exportada no HAR (não é todo o histórico)
python3 baixar_momentos.py --pagina-capturada --listar
```

## Comportamento e limites

- Pagina `EntityMomentsQuery` com `limit` e `offset`, até `hasNextPage` ser falso.
- Consulta com `deleteNotifications=false`, `updateAccessed=false` e `updateStatus=null`. Isso evita pedir as atualizações de leitura usadas pelo site; não é garantia sobre logs internos do serviço.
- Baixa apenas mídias `image/*`, sem vídeos, avatares ou imagens das mensagens.
- Mantém a versão observada na consulta do site: `uri(size: "w1280")`. Não garante arquivo original ou resolução original.
- Não envia cookies nem autorização da API ao servidor de imagens. Usa os cabeçalhos Referer e User-Agent exigidos pelo servidor de imagens observado.
- Interrompe em erro de autenticação, resposta inesperada, domínio não previsto ou repetição de páginas. Não apresenta uma execução parcial como concluída.
- Índice e arquivos temporários permitem retomar após interrupção. Identificação de duplicatas usa o ID da mídia, com hash para verificar integridade dos arquivos existentes.
- A API do site não é um contrato público estável; mudanças do ClassApp podem exigir adaptação.

## Intervalo de datas

```sh
python3 baixar_momentos.py --curl .private/session.curl --de 2026-02-01 --ate 2026-11-09
```

Os limites são inclusivos e consideram a **data de publicação do Momento**, convertida para o fuso de São Paulo, não a data em que a foto foi tirada. Pode usar somente `--de` ou somente `--ate`. Sem filtros, percorre todo o histórico disponível. Como a API observada não oferece filtro de datas confirmado, o script consulta da publicação mais recente para a mais antiga, ignora fotos fora do intervalo e para ao atingir publicações anteriores ao início solicitado.
