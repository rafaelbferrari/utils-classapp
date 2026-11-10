# Fotos ClassApp — versão 2

Abra **Baixar fotos v2.command** e escolha:

- **1:** baixar fotos da API para `fotos_v2`, já com as datas ajustadas.
- **2:** copiar as fotos já baixadas em `fotos` para `fotos_v2` e ajustar as datas, sem baixar novamente e sem precisar de sessão autenticada.

Depois informe as datas inicial/final de publicação (AAAA-MM-DD) ou pressione Enter para deixar cada limite em aberto.

A v1 e seus arquivos não são alterados. A pasta `fotos_v2` tem um índice próprio. A opção 2 usa uma fotografia do índice atual da v1: se ela ainda estiver baixando, execute a opção 2 novamente depois que terminar para incluir as fotos restantes. Cada foto copiada é conferida pelo hash; arquivos já corrigidos são pulados na próxima execução. Evite executar duas instâncias da v2 ao mesmo tempo.

## Qual data é usada?

Se a foto tiver uma data de captura EXIF DateTimeOriginal válida, a v2 a preserva e a usa nas datas do arquivo. Se não houver essa informação, usa a data e o horário de publicação do Momento, convertidos para São Paulo. Publicação não comprova o dia em que a foto foi tirada: a escola pode publicar depois. Se o EXIF original não informar fuso horário, a v2 assume São Paulo e registra isso no índice.

A data é gravada nos metadados XMP e, nos formatos compatíveis, no EXIF quando a captura estiver ausente. As datas de criação e modificação do arquivo no Mac também são ajustadas e verificadas. O índice registra `date_source`, `photo_datetime` e `published_datetime`, permitindo distinguir captura real de publicação usada como aproximação. Os arquivos são processados pelo ExifTool, sem recompressão da imagem.

Fotos já importadas no app Fotos podem precisar ser reimportadas para que ele leia os novos metadados. Importe as cópias da pasta `fotos_v2`.

## Terminal

```sh
# Copiar e corrigir o que a v1 já baixou (sem rede)
python3 baixar_momentos_v2.py --importar-v1 fotos

# Copiar somente um intervalo de publicação
python3 baixar_momentos_v2.py --importar-v1 fotos --de 2026-02-01 --ate 2026-11-09

# Fazer novos downloads, incluindo ajuste de datas
python3 baixar_momentos_v2.py --curl .private/session.curl --de 2026-02-01 --ate 2026-11-09
```

Instale o ExifTool pelo Homebrew: `brew install exiftool`. A autenticação e os filtros de publicação seguem o comportamento da v1 descrito no README.md.

Referência técnica: [documentação do ExifTool](https://exiftool.org/faq.html).
