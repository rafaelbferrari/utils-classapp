# Utils ClassApp

[English — principal](README.md) · [Português (Brasil)](README.pt-BR.md)

Ferramentas locais para salvar e organizar fotos de **Momentos** às quais sua própria conta do ClassApp já tem acesso. Pensadas para famílias que querem guardar o histórico escolar, escolher um período e organizar as fotos depois.

Os downloads usam chamadas HTTP diretas. O reconhecimento facial roda no Mac. Nenhuma etapa precisa de um serviço de IA na nuvem ou consome tokens de IA. Projeto independente, sem vínculo com o ClassApp.

**Este repositório contém somente código, documentação e testes artificiais. Não inclui fotos, sessões, tokens, relatórios de conta ou descritores de rostos.**

## Qual ferramenta usar?

| Tarefa | Abra no Mac | O que faz e quando é útil |
| --- | --- | --- |
| Baixar fotos em lote | **[Baixar fotos turbo.command](Baixar%20fotos%20turbo.command)** | Versão mais recente: até 32 imagens simultâneas, 12 por padrão. Permite escolher datas, retomar arquivos já salvos e recuperar falhas temporárias. |
| Descobrir o começo do histórico | [Consultar primeira data.command](Consultar%20primeira%20data.command) | Consulta a publicação mais antiga e a mais antiga com fotos disponíveis para o perfil, sem baixar imagens. |
| Corrigir datas de fotos existentes | [Ajustar datas das fotos.command](Ajustar%20datas%20das%20fotos.command) | Usa as pastas `AAAA-MM-DD` para ajustar EXIF/XMP e datas no Finder, sem acessar o ClassApp. |
| Separar fotos por pessoa | [Separar fotos por pessoa.command](Separar%20fotos%20por%20pessoa.command) | Agrupa rostos semelhantes, copia as fotos para pastas de pessoas e gera uma foto principal e uma galeria para revisar os grupos. |
| Preparar reconhecimento facial | [Instalar reconhecimento.command](Instalar%20reconhecimento.command) | Instala bibliotecas em ambiente separado e baixa os modelos públicos oficiais. Não processa fotos. |

### Versões de download

| Versão | Script | Diferença |
| --- | --- | --- |
| v1 | `baixar_momentos.py` / `Baixar fotos.command` | Download sequencial simples, filtros de publicação e retomada. |
| v2 | `baixar_momentos_v2.py` / `Baixar fotos v2.command` | Acrescenta datas EXIF/XMP e criação/modificação no Mac; também copia e corrige arquivos da v1. |
| v3 | `baixar_momentos_v3.py` / `Baixar fotos rapido.command` | Até 16 simultâneos, 12 por padrão, índice centralizado e timer de recuperação. |
| **v4** | **`baixar_momentos_v4.py` / `Baixar fotos turbo.command`** | **Até 32 simultâneos, mantendo 12 por padrão. Recomendação para novos downloads.** |

V2, v3 e v4 usam `fotos_v2` por padrão e reconhecem seu índice. Não rode dois downloaders sobre a mesma pasta. A v3/v4 compartilha uma trava; as versões antigas não conhecem todas as travas. Encerre a anterior antes de trocar de versão.

## Começar no Mac

### 1. Instalar e obter os scripts

Requisitos validados: macOS Apple Silicon, Python 3.9 ou compatível e ExifTool. Para instalar o ExifTool com Homebrew:

```sh
brew install exiftool
```

Clone este repositório ou baixe seu ZIP. No Terminal, dentro da pasta extraída:

```sh
python3 --version
```

Para o download, apenas Python e ExifTool são necessários. OpenCV, Pillow e os modelos só são necessários para reconhecimento facial e seus testes.

### 2. Configurar sua própria sessão

1. Abra o ClassApp no Chrome, faça login e entre em **Momentos** no perfil desejado.
2. Abra as ferramentas de desenvolvedor (`Option + Command + I`), selecione **Network**, recarregue a página e filtre por `graphql`.
3. Localize a requisição **POST** cujo Payload contém `operationName: EntityMomentsQuery`.
4. Clique com o botão direito nela e escolha **Copy → Copy as cURL**.

Para executar sem salvar as credenciais no disco, com essa requisição na área de transferência:

```sh
pbpaste | python3 baixar_momentos_v4.py --curl - --de 2025-01-01 --ate 2025-12-31
```

Os lançadores `.command` leem `.private/session.curl`. Se preferir usá-los, salve a requisição localmente:

```sh
mkdir -p .private
chmod 700 .private
(umask 077; pbpaste > .private/session.curl)
```

**Essa requisição contém autorização da sua conta. Não a envie por chat, issue ou commit.** O `.gitignore` a exclui. Sessões expiram: copie uma nova requisição quando necessário. O script interpreta o texto cURL sem executá-lo como comando de shell. Login e renovação de sessão não são automatizados.

### 3. Escolher um período e baixar

Dê dois cliques em **Baixar fotos turbo.command**, informe as datas e a quantidade simultânea, ou use:

```sh
python3 baixar_momentos_v4.py --curl .private/session.curl \
  --de 2025-01-01 --ate 2025-12-31 --simultaneos 12
```

Datas no formato `AAAA-MM-DD`, incluindo os dois dias. Você pode usar apenas um limite ou deixar ambos em aberto. A data é a **publicação do Momento**, convertida para São Paulo.

As fotos ficam em `fotos_v2/AAAA-MM-DD/`. O índice local guarda os arquivos e hashes para retomada. Control+C interrompe; a saída pode aguardar as requisições em andamento. Ao executar novamente, arquivos íntegros já registrados são pulados. Não apague o índice para retomar.

## Como cada recurso ajuda

### Descobrir a data mais antiga

```sh
python3 consultar_primeira_data.py
```

Percorre as páginas e calcula a data mais antiga disponível e a primeira com fotos. Salva `datas_disponiveis.json` localmente. É útil para escolher o início de um backup completo. Não fornece acesso a registros fora do perfil autenticado. [Guia da consulta](LEIA-ME-primeira-data.md).

### Datas coerentes na biblioteca de fotos

A v2/v3/v4 preserva a captura EXIF quando presente. Se ela não existir, usa a publicação como aproximação e registra a origem da data no índice. Isso ajuda a organizar os arquivos no Finder e em aplicativos de fotos, mas não comprova o dia em que a escola tirou a foto.

O ajustador agora lê as datas de `fotos/AAAA-MM-DD`, corrige os metadados e move as fotos para `fotos_v2`, sem duplicar arquivos nem criar backups de imagens. Pare os downloaders antes de usar.

```sh
python3 ajustar_datas_pastas.py --dry-run
python3 ajustar_datas_pastas.py
```

A hora usada é **12h de São Paulo**, pois a pasta só informa o dia. Os índices são atualizados. Arquivos idênticos já existentes no destino ficam em uma única cópia; arquivos diferentes com o mesmo caminho são preservados para revisão. Para somente corrigir as datas sem mover, use `--in-place /caminho/da/colecao` (esse modo antigo cria backups por padrão). [Guia do ajustador em inglês](docs/dates.md).

### Encontrar fotos de cada pessoa

A nova versão usa YuNet + AdaFace IR-50 e agrupamento global com FAISS. Reexecute o instalador ao atualizar. A saída antiga é preservada; as fotos precisam ser analisadas novamente. Grupos sem nome precisam aparecer em pelo menos duas fotos. Rostos isolados, pequenos ou desfocados ficam em `REVIEW.html`, sem criar milhares de pastas automaticamente. Menos pastas não comprova maior precisão.

A análise pode ser interrompida e retomada usando o cache. `--regroup` refaz os grupos com os descritores já calculados e arquiva a saída anterior. Nomes podem ser importados com `--labels-from /caminho/do/resultado`; uniões manuais sem nome não são transferidas. Crescimento infantil e pessoas parecidas ainda podem causar separações ou uniões incorretas. [Configurações e detalhes em inglês](docs/faces.md).

Execute **Instalar reconhecimento.command** e, depois que a coleção estiver estável, **Separar fotos por pessoa.command**. Arraste a pasta de origem para a janela quando solicitado.

O resultado é criado ao lado da origem:

```text
colecao_por_pessoa_v2/
  PESSOAS.html
  Pessoa_0001/
    PRINCIPAL.jpg
    PRINCIPAL-origem.txt
    fotos/...
  Pessoa_0002/...
  REVIEW.html
  Needs_review/...
```

A imagem principal é um recorte do rosto escolhido para facilitar a revisão. Uma foto coletiva é copiada para os grupos correspondentes; isso ocupa espaço adicional. Os originais permanecem intactos.

Os grupos são aproximações por semelhança, não identidades confirmadas. Rostos pequenos, desfocados, de lado e pessoas parecidas podem gerar erros ou vários grupos da mesma pessoa. Revise a galeria. O banco local contém descritores de rostos e deve permanecer privado. [Guia do reconhecimento](LEIA-ME-reconhecimento.md).

### Recuperar falhas sem acompanhar o Terminal

V3/v4 tentam recuperar timeouts e falhas temporárias. Depois de seis tentativas de rede, aguardam 60 segundos e tentam novamente a mesma operação. Por padrão, repetem até recuperar ou receber Control+C. Outros downloads podem continuar enquanto uma foto espera.

```sh
python3 baixar_momentos_v4.py --curl .private/session.curl \
  --simultaneos 12 --reiniciar-em 60 --max-reinicios 5
```

Autenticação inválida, falta de espaço/permissão e erros permanentes encerram a execução. O diagnóstico local fica em `erros_download.log`, sem imprimir a sessão. [Detalhes da recuperação e concorrência](README_v3.md).

## Limites conhecidos

- Apenas fotos de **Momentos**; não inclui vídeos nem anexos de comunicados.
- A consulta observada fornece `w1280`, sem garantia de resolução original.
- As publicações são consultadas sequencialmente. Mais imagens simultâneas não acelera a busca por períodos antigos e não garante maior velocidade.
- A API usada pelo site pode mudar; estes scripts não são uma integração oficial estável.
- As consultas pedem para não marcar como lido nem apagar notificações; isso não elimina eventuais logs internos do serviço.
- Não altere datas nem rode reconhecimento na mesma pasta enquanto o download ainda estiver gravando nela.
- Os scripts e lançadores foram preparados para macOS; não há validação de Windows ou Linux.

## Testes

Usam imagens artificiais, respostas de rede simuladas e diretórios temporários. Não precisam de uma conta do ClassApp nem leem a coleção de fotos.

```sh
# Preparação de bibliotecas e modelos públicos para os testes
python3 -m venv .venv-pessoas
.venv-pessoas/bin/python -m pip install -r requirements-pessoas.txt
.venv-pessoas/bin/python separar_pessoas.py --preparar-modelos

# ExifTool é necessário para testes dos metadados
.venv-pessoas/bin/python -m unittest discover -s tests -v
```

Um teste usa os modelos reais em uma imagem artificial sem rosto; os testes de agrupamento usam vetores simulados. Isso verifica o fluxo e a retomada, não a precisão em fotos reais de crianças.

Documentação adicional: [v1](README_v1.md) · [v2](README_v2.md) · [v3](README_v3.md) · [v4](README_v4.md). Reconhecimento com YuNet, AdaFace IR-50 e FAISS; SFace disponível como opção antiga. [Fontes dos modelos](docs/faces.md).

Os comentários, mensagens do Terminal e a galeria gerada usam inglês. Os nomes antigos de arquivos e parâmetros continuam compatíveis; a documentação principal apresenta os novos nomes em inglês.

## Nomear e unificar grupos de rostos

Abra **Manage face groups.command** e selecione a pasta de resultado que contém `PESSOAS.html`. Use **Save name** para salvar o nome; selecione dois ou mais grupos e use **Merge selected groups** para unificar as fotos. **Undo last change** desfaz a última alteração. Tudo permanece local, com backup dos grupos e sem alterar as fotos de origem. A interface precisa permanecer em execução durante o uso.

Ao salvar um nome no gerenciador, a pasta passa a usar esse nome mais o número do grupo (exemplo fictício: `Pessoa Exemplo - Pessoa_0001`). Os caminhos e a galeria são atualizados juntos; desfazer também restaura o nome anterior da pasta. Para nomes salvos em versões antigas, clique novamente em **Save name**.
