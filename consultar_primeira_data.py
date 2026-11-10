#!/usr/bin/env python3
"""Find the oldest publication and oldest Moment with photos, without downloading images."""
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
        raise api.DownloadError('The response contains a publication without a time zone.')
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
                                        60, 3, 'Date lookup')
        try:
            connection = api.moments(json.loads(body))
        except ValueError:
            raise api.DownloadError('The lookup response is not valid JSON.') from None
        nodes = connection['nodes']
        pages += 1
        print(f'Checking dates: page {pages}. No images are downloaded.',flush=True)
        for post in nodes:
            key = str(post['id'])
            if key in seen:
                raise api.DownloadError('The API repeated publications; could not confirm the oldest date.')
            seen.add(key)
            stamp = timestamp(post['created'])
            if first is None or stamp < first:
                first = stamp
            if (first_photo is None or stamp < first_photo) and any(m.get('mimetype','').startswith('image/') for m in post.get('medias',{}).get('nodes',[])):
                first_photo = stamp
        if not connection['pageInfo']['hasNextPage']:
            break
        if not nodes:
            raise api.DownloadError('Empty page despite an indication of more publications.')
        variables['offset'] += len(nodes)
    return {'primeiro_momento':first.isoformat() if first else None,
            'primeiro_momento_com_fotos':first_photo.isoformat() if first_photo else None,
            'data_inicial_para_download':first_photo.date().isoformat() if first_photo else None,
            'fuso':'America/Sao_Paulo','paginas_consultadas':pages,
            'observacao':'Publication dates available to this profile, not verified photo capture dates.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curl',default=str(Path(__file__).resolve().parent/'.private/session.curl'))
    parser.add_argument('--output', '--saida', metavar='FILE', dest='saida',default=str(Path(__file__).resolve().parent/'datas_disponiveis.json'))
    args = parser.parse_args()
    api._STOP.clear()
    raw = sys.stdin.read() if args.curl == '-' else Path(args.curl).read_text()
    url, original, headers = api.parse_curl(raw)
    result = consult(url,headers,original['variables']['entityId'])
    if result['primeiro_momento']:
        print('Oldest Moment:',timestamp(result['primeiro_momento']).strftime('%d/%m/%Y at %H:%M'))
    else:
        print('No Moments are available to this profile.')
    if result['data_inicial_para_download']:
        print('Oldest Moment with photos:',timestamp(result['primeiro_momento_com_fotos']).strftime('%d/%m/%Y at %H:%M'))
        print('Start date to use in the downloader:',result['data_inicial_para_download'])
    else:
        print('No Moments with photos are available to this profile.')
    api.atomic_json(Path(args.saida), result)
    print('Result saved to:',args.saida)


if __name__=='__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nLookup interrupted.',file=sys.stderr)
        sys.exit(130)
    except (api.DownloadError,OSError,ValueError) as exc:
        api.report_error(exc)
        sys.exit(1)
