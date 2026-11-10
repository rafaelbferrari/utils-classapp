#!/usr/bin/env python3
"""V4: baixa fotos em paralelo, com metadados da v2 e retomada pelo mesmo índice."""
import argparse
import base64
from datetime import date, datetime
from zoneinfo import ZoneInfo
import hashlib
import socket
import http.client
import json
import os
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
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

class RetryableDownloadError(DownloadError):
    pass

_STOP = threading.Event()

def wait_to_restart(seconds, label):
    for remaining in range(seconds, 0, -10):
        print(f'{label}: nova tentativa em {remaining}s. Control+C para interromper.', flush=True)
        if _STOP.wait(min(10, remaining)):
            raise DownloadError('Execução interrompida.')

def automatic_restart(operation, seconds=60, maximum=0, label='Download'):
    restarts = 0
    while True:
        if _STOP.is_set():
            raise DownloadError('Execução interrompida.')
        try:
            return operation()
        except RetryableDownloadError:
            if maximum and restarts >= maximum:
                raise
            restarts += 1
            print(f'{label}: tentativas rápidas esgotadas; reinício automático {restarts}.', flush=True)
            wait_to_restart(seconds, label)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DownloadError('Redirecionamento inesperado; download interrompido.')

_THREAD = threading.local()

def thread_opener():
    if not hasattr(_THREAD, 'opener'):
        _THREAD.opener = urllib.request.build_opener(NoRedirect)
    return _THREAD.opener

def validate_url(url, hosts):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443):
        raise DownloadError('Destino de rede não autorizado pelo script.')
    return p

def request(url, headers=None, payload=None):
    attempts = 6
    stage = 'consulta de publicações' if urllib.parse.urlsplit(url).hostname == API_HOST else 'download de foto'
    for attempt in range(attempts):
        if _STOP.is_set():
            raise DownloadError('Execução interrompida.')
        req = urllib.request.Request(url, headers=headers or {}, data=payload)
        reason = None
        try:
            with thread_opener().open(req, timeout=120) as response:
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
            raise RetryableDownloadError(f'Falha após {attempts} tentativas durante {stage}: {reason}. Execute novamente para retomar as fotos já salvas.') from None
        delay = min(30, 2 ** (attempt + 1))
        print(f'Falha temporária durante {stage} ({reason}). Nova tentativa {attempt + 2}/{attempts} em {delay}s.', flush=True)
        if _STOP.wait(delay):
            raise DownloadError('Execução interrompida.')

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

def exiftool_path():
    executable = shutil.which('exiftool')
    if not executable:
        for candidate in ('/opt/homebrew/bin/exiftool', '/usr/local/bin/exiftool'):
            if Path(candidate).is_file():
                executable = candidate
                break
    if not executable:
        raise DownloadError('Instale o ExifTool: brew install exiftool')
    return executable

def photo_dates(path, published):
    """Preserva data de captura EXIF; usa publicação quando ela não existe."""
    tool = exiftool_path()
    publication = datetime.fromisoformat(published.replace('Z', '+00:00'))
    if publication.tzinfo is None:
        raise DownloadError('Data de publicação sem fuso horário.')
    local = publication.astimezone(ZoneInfo('America/Sao_Paulo'))
    result = subprocess.run([tool, '-j', '-EXIF:DateTimeOriginal', '-EXIF:OffsetTimeOriginal', str(path)], capture_output=True, text=True, check=True)
    tags = json.loads(result.stdout)[0]
    original = tags.get('DateTimeOriginal')
    source = 'publicacao_do_momento'
    if original:
        try:
            capture = datetime.strptime(original[:19], '%Y:%m:%d %H:%M:%S')
            offset = tags.get('OffsetTimeOriginal')
            if offset:
                capture = datetime.fromisoformat(capture.isoformat() + offset)
            else:
                capture = capture.replace(tzinfo=ZoneInfo('America/Sao_Paulo'))
            local = capture
            source = 'captura_exif' if offset else 'captura_exif_fuso_assumido_sao_paulo'
        except ValueError:
            pass
    stamp = local.strftime('%Y:%m:%d %H:%M:%S')
    offset = local.strftime('%z')
    offset = offset[:3] + ':' + offset[3:]
    zoned = stamp + offset
    args = [tool, '-overwrite_original', f'-XMP-photoshop:DateCreated={zoned}',
            f'-XMP-xmp:CreateDate={zoned}', f'-XMP-xmp:ModifyDate={zoned}']
    if path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.tif', '.tiff'):
        # A captura real, se presente, fica preservada. O fallback é explícito no índice.
        if source == 'publicacao_do_momento':
            args += [f'-EXIF:DateTimeOriginal={stamp}', f'-EXIF:CreateDate={stamp}',
                     f'-EXIF:OffsetTimeOriginal={offset}', f'-EXIF:OffsetTimeDigitized={offset}']
    args += [f'-FileCreateDate={zoned}', f'-FileModifyDate={zoned}', str(path)]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise DownloadError('Não foi possível gravar as datas da foto; o original foi preservado.')
    os.utime(path, (local.timestamp(), local.timestamp()))
    # Confirma a gravação real dos metadados e da data de criação do Finder.
    result = subprocess.run([tool, '-j', '-XMP-photoshop:DateCreated', '-FileCreateDate', str(path)], capture_output=True, text=True, check=True)
    written = json.loads(result.stdout)[0]
    if written.get('DateCreated') != zoned:
        raise DownloadError('Falha ao verificar os metadados de data gravados.')
    birth = datetime.strptime(written['FileCreateDate'], '%Y:%m:%d %H:%M:%S%z')
    if abs(birth.timestamp() - local.timestamp()) >= 1:
        raise DownloadError('Falha ao verificar a data de criação do arquivo no Mac.')
    return {'date_source': source, 'photo_datetime': local.isoformat(), 'published_datetime': published, 'metadata_version': 2}

def import_v1(source, destination, start=None, end=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise DownloadError('Origem e destino devem ser pastas separadas, sem uma dentro da outra.')
    records = json.loads((source / 'indice.json').read_text())['photos']
    destination.mkdir(parents=True, exist_ok=True)
    index = destination / 'indice.json'
    state = json.loads(index.read_text()) if index.exists() else {'photos': {}}
    count = 0
    for key, info in records.items():
        day = publication_date(info.get('created'))
        if (start and day < start) or (end and day > end):
            continue
        relative = Path(info['file'])
        original = (source / relative).resolve()
        target = (destination / relative).resolve()
        if not original.is_relative_to(source) or not target.is_relative_to(destination):
            raise DownloadError('Caminho inválido no índice.')
        previous = state['photos'].get(key)
        if previous and previous.get('metadata_version') == 2 and target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == previous['sha256']:
            continue
        if not original.is_file():
            continue
        content = original.read_bytes()
        if hashlib.sha256(content).hexdigest() != info['sha256']:
            print('Arquivo ainda não íntegro na origem; será considerado na próxima execução.', flush=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as tmpdir:
            tmp = Path(tmpdir) / target.name
            tmp.write_bytes(content)
            dates = photo_dates(tmp, info['created'])
            digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
            size = tmp.stat().st_size
            tmp.replace(target)
        state['photos'][key] = dict(info, **dates, sha256=digest, bytes=size)
        atomic_json(index, state)
        count += 1
        print(f'Fotos copiadas com datas ajustadas: {count}', flush=True)
    print(f'Concluído: {count} fotos copiadas para {destination}. Originais preservados.')

def download_one(job, dest):
    post, media = job
    key = str(media['id'])
    image_url = media.get('uri')
    if not image_url:
        raise DownloadError('Foto sem URL disponível.')
    validate_url(image_url, IMAGE_HOSTS)
    # Nunca encaminhar a sessão da API para o servidor de imagens.
    image, content_type = request(image_url, {'Referer': 'https://classapp.co/', 'User-Agent': 'Mozilla/5.0'})
    if not content_type.startswith('image/') or not image:
        raise RetryableDownloadError('O servidor retornou conteúdo que não é uma imagem.')
    date = publication_date(post.get('created')).isoformat()
    safe = lambda s: re.sub(r'[^a-zA-Z0-9_.-]', '_', str(s))[:100]
    suffix = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif', 'image/heic': '.heic'}.get(content_type, '.img')
    relative = Path(safe(date)) / (safe(post['id']) + '_' + safe(key) + suffix)
    target = dest / relative
    target.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmpdir:
        tmp = Path(tmpdir) / target.name
        tmp.write_bytes(image)
        dates = photo_dates(tmp, post['created'])
        image = tmp.read_bytes()
        tmp.replace(target)
    info = {'file': str(relative), 'sha256': hashlib.sha256(image).hexdigest(), 'bytes': len(image), 'moment_id': str(post['id']), 'created': post.get('created'), 'original_name': media.get('origName'), 'quality': 'uri(size: w1280) conforme consulta observada'}
    info.update(dates)
    return key, info

def process_parallel(jobs, worker, consume, count):
    """No máximo count tarefas em voo; só consume altera o índice."""
    iterator = iter(jobs)
    pending = set()
    first_error = None
    pool = ThreadPoolExecutor(max_workers=count, thread_name_prefix='foto')
    try:
        def submit_next():
            try:
                job = next(iterator)
            except StopIteration:
                return False
            pending.add(pool.submit(worker, job))
            return True
        for _ in range(count):
            if not submit_next():
                break
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                try:
                    consume(future.result())
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
                        _STOP.set()
            if first_error is None:
                for _ in done:
                    submit_next()
        if first_error is not None:
            raise first_error
    except BaseException:
        _STOP.set()
        for future in pending:
            future.cancel()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)

def guard_other_downloaders(destination):
    # V1/V2 não possuem trava. Evita que disputem o índice com esta versão.
    listing = subprocess.check_output(['ps', '-axo', 'pid=,comm=,args='], text=True)
    for line in listing.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3 or int(parts[0]) == os.getpid():
            continue
        if 'python' in Path(parts[1]).name.lower() and any(name in parts[2] for name in ('baixar_momentos.py', 'baixar_momentos_v2.py')):
            raise DownloadError('Há um downloader v1/v2 em execução. Encerre-o com Control+C antes de iniciar a v4; ela retomará as fotos já salvas.')
    import fcntl
    lock = (destination / '.download-v3.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise DownloadError('Outra v3/v4 já está usando este destino.') from None
    return lock

def main():
    _STOP.clear()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curl', metavar='ARQUIVO', help='Arquivo Copy as cURL; use - para colar pela entrada padrão.')
    parser.add_argument('--har', default='.private/momentos.har')
    parser.add_argument('--pagina-capturada', action='store_true', help='Somente a página no HAR, sem consultar páginas adicionais.')
    parser.add_argument('--destino', default='fotos_v2')
    parser.add_argument('--max-fotos', type=int, help='Limita fotos novas, útil para teste.')
    parser.add_argument('--listar', action='store_true', help='Conta fotos sem baixá-las.')
    parser.add_argument('--de', type=parse_date, help='Data inicial inclusiva: AAAA-MM-DD (São Paulo).')
    parser.add_argument('--ate', type=parse_date, help='Data final inclusiva: AAAA-MM-DD (São Paulo).')
    parser.add_argument('--importar-v1', metavar='PASTA', help='Copia fotos já baixadas para fotos_v2 e ajusta suas datas, sem acessar a API.')
    parser.add_argument('--simultaneos', type=int, default=12, help='Downloads simultâneos: 1 a 32; padrão 12.')
    parser.add_argument('--reiniciar-em', type=int, default=60, help='Segundos de espera após esgotar as tentativas rápidas. Padrão 60.')
    parser.add_argument('--max-reinicios', type=int, default=0, help='Reinícios por imagem/consulta; 0 = sem limite. Padrão 0.')
    args = parser.parse_args()
    if args.reiniciar_em < 1 or args.max_reinicios < 0:
        parser.error('--reiniciar-em deve ser positivo e --max-reinicios não pode ser negativo')
    if not 1 <= args.simultaneos <= 32:
        parser.error('--simultaneos deve ficar entre 1 e 32')
    if args.de and args.ate and args.de > args.ate:
        parser.error('--de deve ser anterior ou igual a --ate')
    if args.max_fotos is not None and args.max_fotos < 1:
        parser.error('--max-fotos deve ser positivo')
    os.umask(0o077)
    if Path(args.destino).resolve() == (Path(__file__).resolve().parent / 'fotos'):
        parser.error('A v2 deve usar outra pasta; fotos está reservada à v1.')
    if not args.listar:
        exiftool_path()
    if args.importar_v1:
        import_v1(args.importar_v1, args.destino, args.de, args.ate)
        return
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
    download_lock = guard_other_downloaders(dest) if not args.listar else None
    manifest_path = dest / 'indice.json'
    state = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'photos': {}}
    downloaded = skipped = counted = posts = 0
    seen_posts = set()
    reached_start = False
    while True:
        if args.pagina_capturada:
            result = cached
        else:
            body, _ = automatic_restart(lambda: request(url, headers, json.dumps(payload).encode()), args.reiniciar_em, args.max_reinicios, 'Consulta de publicações')
            try:
                result = json.loads(body)
            except ValueError:
                raise DownloadError('Resposta da API não é JSON.') from None
        connection = moments(result)
        nodes = connection['nodes']
        fresh = [p for p in nodes if str(p['id']) not in seen_posts]
        if nodes and not fresh:
            raise DownloadError('A paginação repetiu a mesma página; execução interrompida.')
        jobs = []
        queued = set()
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
                if previous and previous.get('metadata_version') == 2:
                    candidate = dest / previous['file']
                    if candidate.is_relative_to(dest) and candidate.is_file() and hashlib.sha256(candidate.read_bytes()).hexdigest() == previous['sha256']:
                        skipped += 1
                        continue
                if key in queued:
                    continue
                if args.max_fotos and downloaded + len(jobs) >= args.max_fotos:
                    continue
                queued.add(key)
                jobs.append((post, media))
        def consume(result):
            nonlocal downloaded
            key, info = result
            state['photos'][key] = info
            downloaded += 1
            if downloaded % 10 == 0:
                atomic_json(manifest_path, state)
            print(f'Baixadas: {downloaded} | já salvas: {skipped} | simultâneas: {args.simultaneos}', flush=True)
        try:
            process_parallel(jobs, lambda job: automatic_restart(lambda: download_one(job, dest), args.reiniciar_em, args.max_reinicios, f'Foto {job[1]["id"]}'), consume, args.simultaneos)
        finally:
            if jobs:
                atomic_json(manifest_path, state)
        if args.max_fotos and downloaded >= args.max_fotos:
            print('Limite de teste atingido. Histórico ainda não concluído.')
            return
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
    except (DownloadError, OSError, ValueError, subprocess.SubprocessError) as exc:
        report_error(exc)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nInterrompido. Execute novamente para retomar.', file=sys.stderr)
        sys.exit(130)
