#!/usr/bin/env python3
"""Consulta a publicação mais antiga e o primeiro Momento com fotos; não baixa imagens."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import baixar_momentos_v3 as api

QUERY = '''query EntityMomentsQuery($entityId: ID!, $limit: Int, $offset: Int,
$orderBy: [EntityMomentsOrder], $deleteNotifications: Boolean,
$updateStatus: RecipientStatus, $updateAccessed: Boolean) {
  node(id: $entityId) {
    ... on Entity {
      moments(limit: $limit, offset: $offset, orderBy: $orderBy,
        deleteNotifications: $deleteNotifications, updateAccessed: $updateAccessed,
        updateStatus: $updateStatus) {
        nodes { id: dbId created medias { nodes { mimetype } } }
        pageInfo { hasNextPage }
      }
    }
  }
}'''


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise api.DownloadError('Publicação sem fuso horário na resposta.')
    return result.astimezone(ZoneInfo('America/Sao_Paulo'))


def consult(url, headers, entity_id):
    variables = {'entityId': entity_id, 'limit': 200, 'offset': 0,
                 'orderBy': {'column':'CREATED','direction':'DESC'},
                 'deleteNotifications':False,'updateStatus':None,'updateAccessed':False}
    first = first_photo = None
    seen = set()
    pages = 0
    while True:
        payload = {'operationName':'EntityMomentsQuery','query':QUERY,'variables':variables}
        body, _ = api.automatic_restart(lambda: api.request(url, headers, json.dumps(payload).encode()),
                                        60, 3, 'Consulta de datas')
        try:
            connection = api.moments(json.loads(body))
        except ValueError:
            raise api.DownloadError('Resposta da consulta não é JSON válido.') from None
        nodes = connection['nodes']
        pages += 1
        print(f'Consultando datas: página {pages}. Nenhuma imagem é baixada.',flush=True)
        for post in nodes:
            key = str(post['id'])
            if key in seen:
                raise api.DownloadError('A API repetiu publicações; não foi possível confirmar a data mais antiga.')
            seen.add(key)
            stamp = timestamp(post['created'])
            if first is None or stamp < first:
                first = stamp
            if (first_photo is None or stamp < first_photo) and any(m.get('mimetype','').startswith('image/') for m in post.get('medias',{}).get('nodes',[])):
                first_photo = stamp
        if not connection['pageInfo']['hasNextPage']:
            break
        if not nodes:
            raise api.DownloadError('Página vazia apesar da indicação de mais publicações.')
        variables['offset'] += len(nodes)
    return {'primeiro_momento':first.isoformat() if first else None,
            'primeiro_momento_com_fotos':first_photo.isoformat() if first_photo else None,
            'data_inicial_para_download':first_photo.date().isoformat() if first_photo else None,
            'fuso':'America/Sao_Paulo','paginas_consultadas':pages,
            'observacao':'Datas de publicação disponíveis para este perfil; não são datas comprovadas de captura das fotos.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curl',default=str(Path(__file__).resolve().parent/'.private/session.curl'))
    parser.add_argument('--saida',default=str(Path(__file__).resolve().parent/'datas_disponiveis.json'))
    args = parser.parse_args()
    api._STOP.clear()
    raw = sys.stdin.read() if args.curl == '-' else Path(args.curl).read_text()
    url, original, headers = api.parse_curl(raw)
    result = consult(url,headers,original['variables']['entityId'])
    if result['primeiro_momento']:
        print('Momento mais antigo:',timestamp(result['primeiro_momento']).strftime('%d/%m/%Y às %H:%M'))
    else:
        print('Nenhum Momento disponível neste perfil.')
    if result['data_inicial_para_download']:
        print('Primeiro Momento com fotos:',timestamp(result['primeiro_momento_com_fotos']).strftime('%d/%m/%Y às %H:%M'))
        print('Data inicial que você pode usar no downloader:',result['data_inicial_para_download'])
    else:
        print('Nenhum Momento com fotos disponível neste perfil.')
    api.atomic_json(Path(args.saida), result)
    print('Resultado salvo em:',args.saida)


if __name__=='__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nConsulta interrompida.',file=sys.stderr)
        sys.exit(130)
    except (api.DownloadError,OSError,ValueError) as exc:
        api.report_error(exc)
        sys.exit(1)
