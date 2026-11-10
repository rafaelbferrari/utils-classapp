# Ajustar datas pela estrutura de pastas

Copie juntos `ajustar_datas_pastas.py` e `Ajustar datas das fotos.command` para a pasta que contém as subpastas de fotos, por exemplo:

```
Minha pasta de fotos/
  ajustar_datas_pastas.py
  Ajustar datas das fotos.command
  2026-02-01/
    foto.jpg
  2026-02-02/
    outra.jpg
```

Dê dois cliques em `Ajustar datas das fotos.command`. Ele percorre a pasta onde os dois arquivos estão e suas subpastas, usando a pasta de data mais próxima de cada foto. Também pode executar no Terminal, dentro da pasta desejada:

```sh
python3 /caminho/para/ajustar_datas_pastas.py
```

Para apenas conferir, sem alterar:

```sh
python3 ajustar_datas_pastas.py --simular
```

O script sobrescreve as datas EXIF/XMP e as datas de criação/modificação do arquivo no Mac com o dia da pasta AAAA-MM-DD, às **12h no fuso de São Paulo**. A hora é convencional: a estrutura não informa o horário real. Ele usa o dia da pasta mesmo que já exista outra data EXIF. Não consegue descobrir a data real da captura a partir das pastas.

Cria um backup `foto.jpg_original` na primeira alteração. Pode repetir; os backups são ignorados e preservados. Para dispensar backups, use `--sem-backup`. Não há recompressão das imagens.

Fotos fora de pastas com data válida, links simbólicos, pastas ocultas, vídeos e arquivos temporários são ignorados. Formatos: JPEG, PNG, WebP, HEIC/HEIF e TIFF. Nenhuma chamada ao ClassApp, internet ou IA.

Rode **depois que o downloader terminar**. Quando encontrar `indice.json` dentro da pasta percorrida, atualiza seus hashes para que o downloader reconheça as fotos editadas. A data original de publicação no índice é preservada. Use uma instância do ajustador por vez.

Dependências: Python 3 e ExifTool. Instale o ExifTool com `brew install exiftool`.
