# Consultar a primeira data disponível

Abra **Consultar primeira data.command**. Ele consulta os Momentos disponíveis para o perfil da sessão local e mostra:

- A publicação mais antiga.
- A publicação mais antiga que contém fotos.
- A data inicial no formato AAAA-MM-DD para usar no downloader.

O resultado fica em `datas_disponiveis.json`. Não baixa imagens, não modifica fotos nem o índice de downloads. Solicita à API que não marque publicações como lidas ou apague notificações. Datas no fuso de São Paulo; são datas de publicação, não necessariamente de captura.

O teste da ordenação crescente não foi confiável, então o script percorre todas as páginas e calcula o menor valor; pode levar alguns minutos. A consulta solicita apenas IDs, datas e tipos de mídia. O histórico é o disponível para a sessão/perfil atual, não todo o acervo da escola.

Usa as funções de autenticação e recuperação de rede de `baixar_momentos_v3.py`; mantenha esse arquivo junto ao script. A sessão é lida de `.private/session.curl`. Se expirar, renove-a como descrito no README.md.

Terminal:

```sh
python3 consultar_primeira_data.py
```

Se houver erro, a execução termina sem substituir um resultado anterior. Confira a data de modificação de `datas_disponiveis.json` antes de reutilizá-lo.
