#!/usr/bin/env python3
"""V4: download photos concurrently with v2 metadata and index-based resume."""
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
        print(f'{label}: retrying in {remaining}s. Press Control+C to stop.', flush=True)
        if _STOP.wait(min(10, remaining)):
            raise DownloadError('Execution interrupted.')

def automatic_restart(operation, seconds=60, maximum=0, label='Download'):
    restarts = 0
    while True:
        if _STOP.is_set():
            raise DownloadError('Execution interrupted.')
        try:
            return operation()
        except RetryableDownloadError:
            if maximum and restarts >= maximum:
                raise
            restarts += 1
            print(f'{label}: initial attempts exhausted; automatic restart {restarts}.', flush=True)
            wait_to_restart(seconds, label)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DownloadError('Unexpected redirect; download stopped.')

_THREAD = threading.local()

def thread_opener():
    if not hasattr(_THREAD, 'opener'):
        _THREAD.opener = urllib.request.build_opener(NoRedirect)
    return _THREAD.opener

def validate_url(url, hosts):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443):
        raise DownloadError('Network destination is not allowed by this script.')
    return p

def request(url, headers=None, payload=None):
    attempts = 6
    stage = 'publication lookup' if urllib.parse.urlsplit(url).hostname == API_HOST else 'photo download'
    for attempt in range(attempts):
        if _STOP.is_set():
            raise DownloadError('Execution interrupted.')
        req = urllib.request.Request(url, headers=headers or {}, data=payload)
        reason = None
        try:
            with thread_opener().open(req, timeout=120) as response:
                return response.read(), response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise DownloadError('Session expired or access denied. Copy a new authenticated request from Chrome.') from None
            if exc.code not in (429, 500, 502, 503, 504):
                raise DownloadError(f'HTTP {exc.code} failed during {stage}.') from None
            reason = f'HTTP {exc.code}'
        except (urllib.error.URLError, socket.timeout, TimeoutError,
                ConnectionError, http.client.IncompleteRead, http.client.RemoteDisconnected) as exc:
            reason = 'timed out' if isinstance(exc, (socket.timeout, TimeoutError)) else 'connection interrupted'
        if attempt == attempts - 1:
            raise RetryableDownloadError(f'Failed after {attempts} attempts during {stage}: {reason}. Run again to resume using the saved photos.') from None
        delay = min(30, 2 ** (attempt + 1))
        print(f'Temporary failure during {stage} ({reason}). Attempt {attempt + 2}/{attempts} in {delay}s.', flush=True)
        if _STOP.wait(delay):
            raise DownloadError('Execution interrupted.')

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
    raise DownloadError('Capture has no EntityMomentsQuery. Open Network and reload Moments before exporting.')

def parse_curl(text):
    # shlex handles quoting; never execute this text in a shell or subprocess.
    parts = shlex.split(text.replace('\\\n', ''))
    if not parts or parts[0] != 'curl':
        raise DownloadError('Expected the text from Chrome’s Copy as cURL.')
    url, headers, payload = None, {}, None
    i = 1
    while i < len(parts):
        part = parts[i]
        if part.startswith('https://'):
            if url is not None:
                raise DownloadError('Provide exactly one cURL request.')
            url = part
        elif part in ('-H', '--header', '-b', '--cookie', '--data-raw', '--data', '--data-binary', '-d', '-X', '--request'):
            i += 1
            if i >= len(parts):
                raise DownloadError('Incomplete cURL request.')
            value = parts[i]
            if part in ('-H', '--header'):
                name, sep, val = value.partition(':')
                if sep and name.lower() in {'authorization', 'dpop', 'cookie', 'content-type', 'origin', 'referer', 'user-agent', 'accept'}:
                    headers[name.lower()] = val.strip()
            elif part in ('-b', '--cookie'):
                if '=' not in value:
                    raise DownloadError('Cookies must be inline; cookie files are not supported.')
                headers['cookie'] = value
            elif part in ('--data-raw', '--data', '--data-binary', '-d'):
                payload = json.loads(bytes(value[1:], 'utf8').decode('unicode_escape') if value.startswith('$') else value)
        i += 1
    if not url or not payload:
        raise DownloadError('Copy the EntityMomentsQuery POST request, rather than OPTIONS.')
    p = validate_url(url, {API_HOST})
    if p.path != '/graphql' or payload.get('operationName') != 'EntityMomentsQuery':
        raise DownloadError('Use the ClassApp EntityMomentsQuery request.')
    if not any(headers.get(k) for k in ('cookie', 'authorization')):
        raise DownloadError('Request has no cookie or authorization. Sanitized HAR files do not contain authentication.')
    headers['content-type'] = 'application/json'
    return url, payload, headers

def moments(data):
    if data.get('errors'):
        raise DownloadError('The API returned a GraphQL error. Check the session and query; private details were not printed.')
    try:
        connection = data['data']['node']['moments']
        assert isinstance(connection['nodes'], list)
        assert isinstance(connection['pageInfo']['hasNextPage'], bool)
        return connection
    except (KeyError, TypeError, AssertionError):
        raise DownloadError('Unexpected Moments API response.') from None

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
        raise argparse.ArgumentTypeError('Use a valid date in YYYY-MM-DD format.') from None

def publication_date(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError
        return stamp.astimezone(ZoneInfo('America/Sao_Paulo')).date()
    except (ValueError, TypeError, AttributeError):
        raise DownloadError('Missing or invalid publication date; cannot apply the filter.') from None

def exiftool_path():
    executable = shutil.which('exiftool')
    if not executable:
        for candidate in ('/opt/homebrew/bin/exiftool', '/usr/local/bin/exiftool'):
            if Path(candidate).is_file():
                executable = candidate
                break
    if not executable:
        raise DownloadError('Install ExifTool: brew install exiftool')
    return executable

def photo_dates(path, published):
    """Preserve the EXIF capture date; fall back to publication when absent."""
    tool = exiftool_path()
    publication = datetime.fromisoformat(published.replace('Z', '+00:00'))
    if publication.tzinfo is None:
        raise DownloadError('Publication date has no time zone.')
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
        # Preserve existing capture metadata. Record the fallback explicitly in the index.
        if source == 'publicacao_do_momento':
            args += [f'-EXIF:DateTimeOriginal={stamp}', f'-EXIF:CreateDate={stamp}',
                     f'-EXIF:OffsetTimeOriginal={offset}', f'-EXIF:OffsetTimeDigitized={offset}']
    args += [f'-FileCreateDate={zoned}', f'-FileModifyDate={zoned}', str(path)]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise DownloadError('Could not write photo dates; the original was preserved.')
    os.utime(path, (local.timestamp(), local.timestamp()))
    # Verify the written metadata and Finder creation date.
    result = subprocess.run([tool, '-j', '-XMP-photoshop:DateCreated', '-FileCreateDate', str(path)], capture_output=True, text=True, check=True)
    written = json.loads(result.stdout)[0]
    if written.get('DateCreated') != zoned:
        raise DownloadError('Failed to verify the written date metadata.')
    birth = datetime.strptime(written['FileCreateDate'], '%Y:%m:%d %H:%M:%S%z')
    if abs(birth.timestamp() - local.timestamp()) >= 1:
        raise DownloadError('Failed to verify the file creation date on macOS.')
    return {'date_source': source, 'photo_datetime': local.isoformat(), 'published_datetime': published, 'metadata_version': 2}

def import_v1(source, destination, start=None, end=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise DownloadError('Source and destination must be separate directories, neither inside the other.')
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
            raise DownloadError('Invalid path in the index.')
        previous = state['photos'].get(key)
        if previous and previous.get('metadata_version') == 2 and target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == previous['sha256']:
            continue
        if not original.is_file():
            continue
        content = original.read_bytes()
        if hashlib.sha256(content).hexdigest() != info['sha256']:
            print('Source file is not yet intact; it will be checked on the next run.', flush=True)
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
        print(f'Photos copied with corrected dates: {count}', flush=True)
    print(f'Done: {count} photos copied to {destination}. Originals preserved.')

def download_one(job, dest):
    post, media = job
    key = str(media['id'])
    image_url = media.get('uri')
    if not image_url:
        raise DownloadError('Photo has no available URL.')
    validate_url(image_url, IMAGE_HOSTS)
    # Never forward API session credentials to the image server.
    image, content_type = request(image_url, {'Referer': 'https://classapp.co/', 'User-Agent': 'Mozilla/5.0'})
    if not content_type.startswith('image/') or not image:
        raise RetryableDownloadError('The server returned content that is not an image.')
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
    info = {'file': str(relative), 'sha256': hashlib.sha256(image).hexdigest(), 'bytes': len(image), 'moment_id': str(post['id']), 'created': post.get('created'), 'original_name': media.get('origName'), 'quality': 'uri(size: w1280) as observed in the query'}
    info.update(dates)
    return key, info

def process_parallel(jobs, worker, consume, count):
    """Keep at most count jobs in flight; only consume updates the index."""
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
    # V1/V2 have no lock; prevent them from competing for this index.
    listing = subprocess.check_output(['ps', '-axo', 'pid=,comm=,args='], text=True)
    for line in listing.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3 or int(parts[0]) == os.getpid():
            continue
        if 'python' in Path(parts[1]).name.lower() and any(name in parts[2] for name in ('baixar_momentos.py', 'baixar_momentos_v2.py')):
            raise DownloadError('A v1/v2 downloader is running. Stop it with Control+C before starting v4; saved photos will be reused.')
    import fcntl
    lock = (destination / '.download-v3.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise DownloadError('Another v3/v4 is already using this destination.') from None
    return lock

def main():
    _STOP.clear()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curl', metavar='FILE', help='Copy as cURL file; use - to read standard input.')
    parser.add_argument('--har', default='.private/momentos.har')
    parser.add_argument('--captured-page', '--pagina-capturada', dest='pagina_capturada', action='store_true', help='Use only the captured HAR page, without fetching more pages.')
    parser.add_argument('--destination', '--destino', metavar='DIRECTORY', dest='destino', default='fotos_v2')
    parser.add_argument('--max-photos', '--max-fotos', metavar='COUNT', dest='max_fotos', type=int, help='Limit new photos, useful for testing.')
    parser.add_argument('--count-only', '--listar', dest='listar', action='store_true', help='Count photos without downloading them.')
    parser.add_argument('--from', '--de', metavar='DATE', dest='de', type=parse_date, help='Inclusive start date: YYYY-MM-DD (Sao Paulo).')
    parser.add_argument('--to', '--ate', metavar='DATE', dest='ate', type=parse_date, help='Inclusive end date: YYYY-MM-DD (Sao Paulo).')
    parser.add_argument('--import-v1', '--importar-v1', dest='importar_v1', metavar='DIRECTORY', help='Copy previously downloaded photos to fotos_v2 and update dates without accessing the API.')
    parser.add_argument('--concurrent', '--simultaneos', metavar='COUNT', dest='simultaneos', type=int, default=12, help='Concurrent downloads: 1 to 32; default 12.')
    parser.add_argument('--retry-delay', '--reiniciar-em', metavar='SECONDS', dest='reiniciar_em', type=int, default=60, help='Seconds to wait after initial attempts are exhausted. Default 60.')
    parser.add_argument('--max-restarts', '--max-reinicios', metavar='COUNT', dest='max_reinicios', type=int, default=0, help='Restarts per image or query; 0 means unlimited. Default 0.')
    args = parser.parse_args()
    if args.reiniciar_em < 1 or args.max_reinicios < 0:
        parser.error('--retry-delay must be positive and --max-restarts cannot be negative')
    if not 1 <= args.simultaneos <= 32:
        parser.error('--concurrent must be between 1 and 32')
    if args.de and args.ate and args.de > args.ate:
        parser.error('--from must be earlier than or equal to --to')
    if args.max_fotos is not None and args.max_fotos < 1:
        parser.error('--max-photos must be positive')
    os.umask(0o077)
    if Path(args.destino).resolve() == (Path(__file__).resolve().parent / 'fotos'):
        parser.error('Use a different directory; fotos is reserved for v1.')
    if not args.listar:
        exiftool_path()
    if args.importar_v1:
        import_v1(args.importar_v1, args.destino, args.de, args.ate)
        return
    if args.pagina_capturada:
        _, payload, cached = read_har(args.har)
        print('CAPTURE MODE: one page only; this is not the full history.', flush=True)
        url, headers = None, None
    elif args.curl:
        if args.curl == '-':
            print('Paste Copy as cURL and finish with Ctrl+D on an empty line:', file=sys.stderr)
            text = sys.stdin.read()
        else:
            text = Path(args.curl).read_text()
        url, payload, headers = parse_curl(text)
        cached = None
    else:
        parser.error('Use --curl FILE (full history) or --captured-page (capture test).')
    variables = payload['variables']
    variables.update(deleteNotifications=False, updateStatus=None, updateAccessed=False, offset=0, search='')
    variables['orderBy'] = {'column': 'CREATED', 'direction': 'DESC'}
    if args.de or args.ate:
        print(f'Publication period: {args.de or "start of history"} to {args.ate or "latest"} (Sao Paulo, inclusive).', flush=True)
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
            body, _ = automatic_restart(lambda: request(url, headers, json.dumps(payload).encode()), args.reiniciar_em, args.max_reinicios, 'Publication lookup')
            try:
                result = json.loads(body)
            except ValueError:
                raise DownloadError('The API response is not JSON.') from None
        connection = moments(result)
        nodes = connection['nodes']
        fresh = [p for p in nodes if str(p['id']) not in seen_posts]
        if nodes and not fresh:
            raise DownloadError('Pagination repeated the same page; execution stopped.')
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
            print(f'Downloaded: {downloaded} | already saved: {skipped} | concurrent: {args.simultaneos}', flush=True)
        try:
            process_parallel(jobs, lambda job: automatic_restart(lambda: download_one(job, dest), args.reiniciar_em, args.max_reinicios, f'Photo {job[1]["id"]}'), consume, args.simultaneos)
        finally:
            if jobs:
                atomic_json(manifest_path, state)
        if args.max_fotos and downloaded >= args.max_fotos:
            print('Test limit reached. History is not complete yet.')
            return
        print(f'Publications: {posts} | photo references: {counted}', flush=True)
        if reached_start or args.pagina_capturada or not connection['pageInfo']['hasNextPage']:
            break
        if not nodes:
            raise DownloadError('The API indicated another page but returned an empty one.')
        variables['offset'] += len(nodes)
        time.sleep(0.5)
    print(('Captured page complete.' if args.pagina_capturada else ('Requested period complete.' if args.de or args.ate else 'Available history complete.')) + f' New: {downloaded}; already saved: {skipped}; photos found: {counted}.')

def describe_error(exc):
    """Report diagnostics without exposing cookies, signed URLs, or API content."""
    if isinstance(exc, DownloadError):
        return str(exc)
    filename = getattr(exc, 'filename', None)
    file_label = ''
    if filename:
        name = Path(str(filename)).name if '://' not in str(filename) else '(network)'
        file_label = f' File: {name}.'
    if isinstance(exc, FileNotFoundError):
        return 'File or directory not found.' + file_label
    if isinstance(exc, PermissionError):
        return 'Permission denied while reading or writing.' + file_label
    if isinstance(exc, json.JSONDecodeError):
        return f'Invalid or incomplete JSON (line {exc.lineno}, column {exc.colno}). Check the index or configuration.'
    if isinstance(exc, UnicodeError):
        return 'Could not decode the file or received response.'
    if isinstance(exc, OSError):
        import errno
        code = getattr(exc, 'errno', None)
        reasons = {errno.ENOSPC: 'Not enough disk space.', errno.EROFS: 'The destination is on a read-only disk.', errno.EMFILE: 'Open file limit reached.', errno.EIO: 'Disk or device input/output failure.', errno.ENAMETOOLONG: 'File name or path is too long.', errno.ETIMEDOUT: 'Connection timed out.'}
        return reasons.get(code, f'Read, write, or connection failure ({type(exc).__name__}, code {code}).') + file_label
    if isinstance(exc, ValueError):
        return 'Invalid configuration or date; check the cURL text and date format.'
    return f'Metadata tool failed ({type(exc).__name__}). Check that ExifTool is installed.'

def report_error(exc):
    message = describe_error(exc)
    print(f'Error: {message}', file=sys.stderr)
    try:
        import traceback
        log = Path(__file__).resolve().parent / 'erros_download.log'
        frames = traceback.extract_tb(exc.__traceback__)
        location = ' > '.join(f'{Path(f.filename).name}:{f.lineno} ({f.name})' for f in frames)
        with log.open('a', encoding='utf-8') as output:
            stamp = datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds')
            output.write(f'{stamp} | {type(exc).__name__} | {message} | {location}\n')
        print(f'Diagnostics saved to: {log}', file=sys.stderr)
    except OSError:
        print('Could not write the diagnostic log either.', file=sys.stderr)

if __name__ == '__main__':
    try:
        main()
    except (DownloadError, OSError, ValueError, subprocess.SubprocessError) as exc:
        report_error(exc)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nInterrupted. Run again to resume.', file=sys.stderr)
        sys.exit(130)
