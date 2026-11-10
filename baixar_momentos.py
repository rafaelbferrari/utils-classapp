#!/usr/bin/env python3
"""Download Moments photos over HTTP. Never execute supplied cURL commands."""
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
        raise DownloadError('Unexpected redirect; download stopped.')

OPENER = urllib.request.build_opener(NoRedirect)

def validate_url(url, hosts):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443):
        raise DownloadError('Network destination is not allowed by this script.')
    return p

def request(url, headers=None, payload=None):
    attempts = 6
    stage = 'publication lookup' if urllib.parse.urlsplit(url).hostname == API_HOST else 'photo download'
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers=headers or {}, data=payload)
        reason = None
        try:
            with OPENER.open(req, timeout=120) as response:
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
            raise DownloadError(f'Failed after {attempts} attempts during {stage}: {reason}. Run again to resume using the saved photos.') from None
        delay = min(30, 2 ** (attempt + 1))
        print(f'Temporary failure during {stage} ({reason}). Attempt {attempt + 2}/{attempts} in {delay}s.', flush=True)
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

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curl', metavar='FILE', help='Copy as cURL file; use - to read standard input.')
    parser.add_argument('--har', default='.private/momentos.har')
    parser.add_argument('--captured-page', '--pagina-capturada', dest='pagina_capturada', action='store_true', help='Use only the captured HAR page, without fetching more pages.')
    parser.add_argument('--destination', '--destino', metavar='DIRECTORY', dest='destino', default='fotos')
    parser.add_argument('--max-photos', '--max-fotos', metavar='COUNT', dest='max_fotos', type=int, help='Limit new photos, useful for testing.')
    parser.add_argument('--count-only', '--listar', dest='listar', action='store_true', help='Count photos without downloading them.')
    parser.add_argument('--from', '--de', metavar='DATE', dest='de', type=parse_date, help='Inclusive start date: YYYY-MM-DD (Sao Paulo).')
    parser.add_argument('--to', '--ate', metavar='DATE', dest='ate', type=parse_date, help='Inclusive end date: YYYY-MM-DD (Sao Paulo).')
    args = parser.parse_args()
    if args.de and args.ate and args.de > args.ate:
        parser.error('--from must be earlier than or equal to --to')
    if args.max_fotos is not None and args.max_fotos < 1:
        parser.error('--max-photos must be positive')
    os.umask(0o077)
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
                raise DownloadError('The API response is not JSON.') from None
        connection = moments(result)
        nodes = connection['nodes']
        fresh = [p for p in nodes if str(p['id']) not in seen_posts]
        if nodes and not fresh:
            raise DownloadError('Pagination repeated the same page; execution stopped.')
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
                    raise DownloadError('Photo has no available URL.')
                validate_url(image_url, IMAGE_HOSTS)
                # Never forward API session credentials to the image server.
                image, content_type = request(image_url, {'Referer': 'https://classapp.co/', 'User-Agent': 'Mozilla/5.0'})
                if not content_type.startswith('image/') or not image:
                    raise DownloadError('The server returned content that is not an image.')
                date = str(post.get('created', 'sem-data'))[:10]
                safe = lambda s: re.sub(r'[^a-zA-Z0-9_.-]', '_', str(s))[:100]
                suffix = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif', 'image/heic': '.heic'}.get(content_type, '.img')
                relative = Path(safe(date)) / (safe(post['id']) + '_' + safe(key) + suffix)
                target = dest / relative
                target.parent.mkdir(exist_ok=True)
                tmp = target.with_suffix('.part')
                tmp.write_bytes(image)
                tmp.replace(target)
                state['photos'][key] = {'file': str(relative), 'sha256': hashlib.sha256(image).hexdigest(), 'bytes': len(image), 'moment_id': str(post['id']), 'created': post.get('created'), 'original_name': media.get('origName'), 'quality': 'uri(size: w1280) as observed in the query'}
                atomic_json(manifest_path, state)
                downloaded += 1
                print(f'Downloaded: {downloaded} | already saved: {skipped}', flush=True)
                if args.max_fotos and downloaded >= args.max_fotos:
                    print('Test limit reached. History is not complete yet.')
                    return
                time.sleep(0.15)
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
    except (DownloadError, OSError, ValueError) as exc:
        report_error(exc)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nInterrupted. Run again to resume.', file=sys.stderr)
        sys.exit(130)
