# Separar automaticamente fotos por pessoa

## Como usar no Mac

Primeiro execute **Instalar reconhecimento.command** para instalar as dependências e os modelos. Depois que seus downloads terminarem:

1. Dê dois cliques em **Separar fotos por pessoa.command**.
2. Arraste a pasta com as fotos (por exemplo `fotos`) para a janela do Terminal e pressione Enter.
3. Aguarde. A saída será criada **ao lado da origem**, por exemplo `fotos_por_pessoa`.
4. Abra **PESSOAS.html** na saída para ver a galeria de rostos.

Cada grupo terá esta estrutura:

```
fotos_por_pessoa/
  PESSOAS.html
  Pessoa_0001/
    PRINCIPAL.jpg
    PRINCIPAL-origem.txt
    fotos/
      2026-02-01/
        foto.jpg
  Pessoa_0002/
    PRINCIPAL.jpg
    fotos/...
  Sem_rosto_detectado/...
```

**PRINCIPAL.jpg** é um recorte de referência do rosto. O script escolhe um rosto maior e mais nítido entre as aparições analisadas, podendo atualizar a referência à medida que encontra fotos melhores. `PRINCIPAL-origem.txt` informa qual foto gerou o recorte. As fotos completas são copiadas sem recompressão e com suas datas de modificação preservadas. Uma foto com várias pessoas é copiada para cada grupo correspondente, podendo ocupar bastante espaço adicional.

## Processamento local

O agrupamento usa os modelos YuNet e SFace do OpenCV. Não precisa de chave de API ou acesso ao ClassApp; não envia fotos, rostos ou descritores para a internet; não usa tokens de IA. A instalação baixa bibliotecas e dois modelos públicos oficiais. Depois, a análise funciona offline.

A saída contém um banco local oculto `.pessoas.sqlite3`, usado para retomar a análise. Ele guarda as associações de fotos e os descritores de rosto. Não apague esse arquivo para continuar uma execução anterior. Os originais não são movidos, renomeados nem editados.

Rode somente quando a pasta de origem estiver estável, depois dos downloads e eventuais ajustes de datas. Se um arquivo mudar após ser analisado, o script sinaliza e pede uma nova pasta de saída para reanálise. Evite modificar arquivos da origem durante a execução.

## Conferência e nomes

Os nomes `Pessoa_0001` são grupos de **semelhança**, não identidades confirmadas. Pode haver confusão entre crianças parecidas, gêmeos, rostos de lado ou desfocados, assim como vários grupos da mesma pessoa. A galeria e as fotos principais facilitam a revisão. Rostos muito pequenos ou não detectados não são classificados: fotos sem rosto utilizável ficam em `Sem_rosto_detectado`.

Grupos criados por dúvida entre dois candidatos recebem “revisar semelhança” na galeria. Outros grupos também precisam de conferência. O algoritmo é incremental e conservador: a ordem das imagens influencia os grupos. Ele não une automaticamente grupos já separados.

Durante o processamento e antes de futuras retomadas, mantenha os nomes `Pessoa_0001` etc. Depois que terminar e não pretender retomar nesse destino, você pode renomear as pastas manualmente. A galeria usa os nomes originais e seus links deixam de funcionar após renomeá-los.

## Retomar e ajustar

Pode interromper com Control+C e executar novamente com a mesma origem/destino. Fotos já registradas são puladas; a galeria é atualizada a cada 25 fotos e ao encerrar. Não execute duas instâncias no mesmo destino (o script bloqueia a segunda). Se remover cópias da saída manualmente, use um novo destino para reconstruí-la.

Teste limitado, quando quiser:

```sh
.venv-pessoas/bin/python separar_pessoas.py /caminho/das/fotos --max-fotos 30
```

Mais conservador, usando um destino novo:

```sh
.venv-pessoas/bin/python separar_pessoas.py /caminho/das/fotos --limiar 0.55 --destino /caminho/novo_resultado
```

Limiar maior tende a separar mais grupos; menor tende a unir mais rostos. Padrão: 0.48. A margem entre candidatos é 0.05. O mesmo grupo não recebe dois rostos diferentes da mesma foto, para reduzir misturas em fotos coletivas.

Em outro Mac, mantenha os scripts e `requirements-pessoas.txt` juntos e execute **Instalar reconhecimento.command** primeiro. A combinação validada usa Python 3.9 e macOS Apple Silicon, com ambiente virtual separado dos scripts de download.

Documentação dos modelos: [OpenCV — Face Detection and Recognition](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html). Os modelos são baixados de uma revisão fixa do repositório oficial e conferidos por SHA-256.
