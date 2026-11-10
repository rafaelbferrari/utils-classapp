#!/usr/bin/env python3
"""Baixa fotos de Momentos por HTTP. Não executa comandos cURL recebidos."""
import argparse
import base64
from datetime import date, datetime
from zoneinfo import ZoneInfo
import hashlib
import socket
import http.client
import json
import os
from pathlib import Path
import re
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_HOST = 'web.classapp.com.br'
IMAGE_HOSTS = {'images.classapp.com.br'}

class DownloadError(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DownloadError('Redirecionamento inesperado; download interrompido.')

OPENER = urllib.request.build_opener(NoRedirect)

def validate_url(url, hosts):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443):
        raise DownloadError('Destino de rede não autorizado pelo script.')
    return p

def request(url, headers=None, payload=None):
    attempts = 6
    stage = 'consulta de publicações' if urllib.parse.urlsplit(url).hostname == API_HOST else 'download de foto'
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers=headers or {}, data=payload)
        reason = None
        try:
            with OPENER.open(req, timeout=120) as response:
                return response.read(), response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise DownloadError('Sessão expirada ou acesso recusado. Copie uma nova chamada autenticada do Chrome.') from None
            if exc.code not in (429, 500, 502, 503, 504):
                raise DownloadError(f'Falha HTTP {exc.code} durante {stage}.') from None
            reason = f'HTTP {exc.code}'
        except (urllib.error.URLError, socket.timeout, TimeoutError,
                ConnectionError, http.client.IncompleteRead, http.client.RemoteDisconnected) as exc:
            reason = 'tempo de espera esgotado' if isinstance(exc, (socket.timeout, TimeoutError)) else 'conexão interrompida'
        if attempt == attempts - 1:
            raise DownloadError(f'Falha após {attempts} tentativas durante {stage}: {reason}. Execute novamente para retomar as fotos já salvas.') from None
        delay = min(30, 2 ** (attempt + 1))
        print(f'Falha temporária durante {stage} ({reason}). Nova tentativa {attempt + 2}/{attempts} em {delay}s.', flush=True)
        time.sleep(delay)

def read_har(path):
    har = json.loads(Path(path).read_text())
    for entry in har['log']['entries']:
        try:
            payload = json.loads(entry['request'].get('postData', {}).get('text', '{}'))
        except (ValueError, TypeError):
            continue
        if payload.get('operationName') == 'EntityMomentsQuery':
            content = entry['response']['content']
            raw = content.get('text', '')
            if content.get('encoding') == 'base64':
                raw = base64.b64decode(raw)
            return entry['request']['url'], payload, json.loads(raw)
    raise DownloadError('Captura sem EntityMomentsQuery. Abra Network e recarregue Momentos antes de exportar.')

def parse_curl(text):
    # shlex interpreta aspas; nunca executar este texto em shell/subprocess.
    parts = shlex.split(text.replace('\\\n', ''))
    if not parts or parts[0] != 'curl':
        raise DownloadError('Esperava o texto de “Copy as cURL” do Chrome.')
    url, headers, payload = None, {}, None
    i = 1
    while i < len(parts):
        part = parts[i]
        if part.startswith('https://'):
            if url is not None:
                raise DownloadError('Forneça apenas uma chamada cURL.')
            url = part
        elif part in ('-H', '--header', '-b', '--cookie', '--data-raw', '--data', '--data-binary', '-d', '-X', '--request'):
            i += 1
            if i >= len(parts):
                raise DownloadError('Chamada cURL incompleta.')
            value = parts[i]
            if part in ('-H', '--header'):
                name, sep, val = value.partition(':')
                if sep and name.lower() in {'authorization', 'dpop', 'cookie', 'content-type', 'origin', 'referer', 'user-agent', 'accept'}:
                    headers[name.lower()] = val.strip()
            elif part in ('-b', '--cookie'):
                if '=' not in value:
                    raise DownloadError('Cookie deve estar no texto; arquivos de cookies não são aceitos.')
                headers['cookie'] = value
            elif part in ('--data-raw', '--data', '--data-binary', '-d'):
                payload = json.loads(bytes(value[1:], 'utf8').decode('unicode_escape') if value.startswith('$') else value)
        i += 1
    if not url or not payload:
        raise DownloadError('Copie a chamada POST EntityMomentsQuery, não a requisição OPTIONS.')
    p = validate_url(url, {API_HOST})
    if p.path != '/graphql' or payload.get('operationName') != 'EntityMomentsQuery':
        raise DownloadError('Use a chamada EntityMomentsQuery do ClassApp.')
    if not any(headers.get(k) for k in ('cookie', 'authorization')):
        raise DownloadError('Chamada sem cookie/autorização. O HAR sanitizado não contém autenticação.')
    headers['content-type'] = 'application/json'
    return url, payload, headers

def moments(data):
    if data.get('errors'):
        raise DownloadError('A API retornou erro GraphQL. Verifique a sessão e a consulta; nenhum detalhe privado foi impresso.')
    try:
        connection = data['data']['node']['moments']
        assert isinstance(connection['nodes'], list)
        assert isinstance(connection['pageInfo']['hasNextPage'], bool)
        return connection
    except (KeyError, TypeError, AssertionError):
        raise DownloadError('Resposta inesperada da API de Momentos.') from None

def atomic_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)

def parse_date(value):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError('Use uma data válida no formato AAAA-MM-DD.') from None

def publication_date(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError
        return stamp.astimezone(ZoneInfo('America/Sao_Paulo')).date()
    except (ValueError, TypeError, AttributeError):
        raise DownloadError('Data de publicação ausente ou inválida; filtro não pode ser aplicado.') from None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curl', metavar='ARQUIVO', help='Arquivo Copy as cURL; use - para colar pela entrada padrão.')
    parser.add_argument('--har', default='.private/momentos.har')
    parser.add_argument('--pagina-capturada', action='store_true', help='Somente a página no HAR, sem consultar páginas adicionais.')
    parser.add_argument('--destino', default='fotos')
    parser.add_argument('--max-fotos', type=int, help='Limita fotos novas, útil para teste.')
    parser.add_argument('--listar', action='store_true', help='Conta fotos sem baixá-las.')
    parser.add_argument('--de', type=parse_date, help='Data inicial inclusiva: AAAA-MM-DD (São Paulo).')
    parser.add_argument('--ate', type=parse_date, help='Data final inclusiva: AAAA-MM-DD (São Paulo).')
    args = parser.parse_args()
    if args.de and args.ate and args.de > args.ate:
        parser.error('--de deve ser anterior ou igual a --ate')
    if args.max_fotos is not None and args.max_fotos < 1:
        parser.error('--max-fotos deve ser positivo')
    os.umask(0o077)
    if args.pagina_capturada:
        _, payload, cached = read_har(args.har)
        print('MODO CAPTURA: apenas uma página; não representa todo o histórico.', flush=True)
        url, headers = None, None
    elif args.curl:
        if args.curl == '-':
            print('Cole Copy as cURL e termine com Ctrl+D numa linha vazia:', file=sys.stderr)
            text = sys.stdin.read()
        else:
            text = Path(args.curl).read_text()
        url, payload, headers = parse_curl(text)
        cached = None
    else:
        parser.error('Use --curl ARQUIVO (histórico completo) ou --pagina-capturada (teste da captura).')
    variables = payload['variables']
    variables.update(deleteNotifications=False, updateStatus=None, updateAccessed=False, offset=0, search='')
    variables['orderBy'] = {'column': 'CREATED', 'direction': 'DESC'}
    if args.de or args.ate:
        print(f'Período de publicação: {args.de or "início do histórico"} até {args.ate or "mais recente"} (São Paulo, inclusive).', flush=True)
    dest = Path(args.destino).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / 'indice.json'
    state = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'photos': {}}
    downloaded = skipped = counted = posts = 0
    seen_posts = set()
    reached_start = False
    while True:
        if args.pagina_capturada:
            result = cached
        else:
            body, _ = request(url, headers, json.dumps(payload).encode())
            try:
                result = json.loads(body)
            except ValueError:
                raise DownloadError('Resposta da API não é JSON.') from None
        connection = moments(result)
        nodes = connection['nodes']
        fresh = [p for p in nodes if str(p['id']) not in seen_posts]
        if nodes and not fresh:
            raise DownloadError('A paginação repetiu a mesma página; execução interrompida.')
        for post in fresh:
            seen_posts.add(str(post['id']))
            posts += 1
            if args.de or args.ate:
                day = publication_date(post.get('created'))
                if args.de and day < args.de:
                    reached_start = True
                    continue
                if args.ate and day > args.ate:
                    continue
            for media in post.get('medias', {}).get('nodes', []):
                if not media.get('mimetype', '').startswith('image/'):
                    continue
                counted += 1
                if args.listar:
                    continue
                key = str(media['id'])
                previous = state['photos'].get(key)
                if previous:
                    candidate = dest / previous['file']
                    if candidate.is_relative_to(dest) and candidate.is_file() and hashlib.sha256(candidate.read_bytes()).hexdigest() == previous['sha256']:
                        skipped += 1
                        continue
                image_url = media.get('uri')
                if not image_url:
                    raise DownloadError('Foto sem URL disponível.')
                validate_url(image_url, IMAGE_HOSTS)
                # Nunca encaminhar a sessão da API para o servidor de imagens.
                image, content_type = request(image_url, {'Referer': 'https://classapp.co/', 'User-Agent': 'Mozilla/5.0'})
                if not content_type.startswith('image/') or not image:
                    raise DownloadError('O servidor retornou conteúdo que não é uma imagem.')
                date = str(post.get('created', 'sem-data'))[:10]
                safe = lambda s: re.sub(r'[^a-zA-Z0-9_.-]', '_', str(s))[:100]
                suffix = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif', 'image/heic': '.heic'}.get(content_type, '.img')
                relative = Path(safe(date)) / (safe(post['id']) + '_' + safe(key) + suffix)
                target = dest / relative
                target.parent.mkdir(exist_ok=True)
                tmp = target.with_suffix('.part')
                tmp.write_bytes(image)
                tmp.replace(target)
                state['photos'][key] = {'file': str(relative), 'sha256': hashlib.sha256(image).hexdigest(), 'bytes': len(image), 'moment_id': str(post['id']), 'created': post.get('created'), 'original_name': media.get('origName'), 'quality': 'uri(size: w1280) conforme consulta observada'}
                atomic_json(manifest_path, state)
                downloaded += 1
                print(f'Baixadas: {downloaded} | já salvas: {skipped}', flush=True)
                if args.max_fotos and downloaded >= args.max_fotos:
                    print('Limite de teste atingido. Histórico ainda não concluído.')
                    return
                time.sleep(0.15)
        print(f'Publicações: {posts} | referências a fotos: {counted}', flush=True)
        if reached_start or args.pagina_capturada or not connection['pageInfo']['hasNextPage']:
            break
        if not nodes:
            raise DownloadError('API indicou próxima página, mas retornou uma página vazia.')
        variables['offset'] += len(nodes)
        time.sleep(0.5)
    print(('Página capturada concluída.' if args.pagina_capturada else ('Período solicitado concluído.' if args.de or args.ate else 'Histórico disponível concluído.')) + f' Novas: {downloaded}; já salvas: {skipped}; fotos encontradas: {counted}.')

def describe_error(exc):
    """Diagnóstico sem imprimir cookies, URLs assinadas ou conteúdo da API."""
    if isinstance(exc, DownloadError):
        return str(exc)
    filename = getattr(exc, 'filename', None)
    file_label = ''
    if filename:
        name = Path(str(filename)).name if '://' not in str(filename) else '(rede)'
        file_label = f' Arquivo: {name}.'
    if isinstance(exc, FileNotFoundError):
        return 'Arquivo ou pasta não encontrado.' + file_label
    if isinstance(exc, PermissionError):
        return 'Sem permissão para ler ou gravar.' + file_label
    if isinstance(exc, json.JSONDecodeError):
        return f'JSON inválido ou incompleto (linha {exc.lineno}, coluna {exc.colno}). Pode ser o índice ou a configuração.'
    if isinstance(exc, UnicodeError):
        return 'Não foi possível decodificar o arquivo ou a resposta recebida.'
    if isinstance(exc, OSError):
        import errno
        code = getattr(exc, 'errno', None)
        reasons = {errno.ENOSPC: 'Espaço insuficiente no disco.', errno.EROFS: 'O destino está em um disco somente para leitura.', errno.EMFILE: 'Limite de arquivos abertos atingido.', errno.EIO: 'Falha de entrada/saída no disco ou dispositivo.', errno.ENAMETOOLONG: 'Nome de arquivo ou caminho muito longo.', errno.ETIMEDOUT: 'Tempo de conexão esgotado.'}
        return reasons.get(code, f'Falha de leitura, gravação ou conexão ({type(exc).__name__}, código {code}).') + file_label
    if isinstance(exc, ValueError):
        return 'Configuração ou data inválida; confira o texto cURL e o formato das datas.'
    return f'Falha ao executar ferramenta de metadados ({type(exc).__name__}). Confira se o ExifTool está instalado.'

def report_error(exc):
    message = describe_error(exc)
    print(f'Erro: {message}', file=sys.stderr)
    try:
        import traceback
        log = Path(__file__).resolve().parent / 'erros_download.log'
        frames = traceback.extract_tb(exc.__traceback__)
        location = ' > '.join(f'{Path(f.filename).name}:{f.lineno} ({f.name})' for f in frames)
        with log.open('a', encoding='utf-8') as output:
            stamp = datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds')
            output.write(f'{stamp} | {type(exc).__name__} | {message} | {location}\n')
        print(f'Diagnóstico salvo em: {log}', file=sys.stderr)
    except OSError:
        print('Também não foi possível gravar o log de diagnóstico.', file=sys.stderr)

if __name__ == '__main__':
    try:
        main()
    except (DownloadError, OSError, ValueError) as exc:
        report_error(exc)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nInterrompido. Execute novamente para retomar.', file=sys.stderr)
        sys.exit(130)
