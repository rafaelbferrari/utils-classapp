#!/usr/bin/env python3
"""Update photo dates from YYYY-MM-DD directory names, without network or ClassApp access."""
import argparse
from collections import defaultdict
from datetime import date, datetime, time
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.tif', '.tiff'}

def folder_date(path, root):
    for parent in (path.parent, *path.parent.parents):
        if not parent.is_relative_to(root):
            break
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', parent.name):
            try:
                return date.fromisoformat(parent.name)
            except ValueError:
                return None
    return None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pasta', metavar='DIRECTORY', nargs='?', default='.', help='Directory to scan; default: current directory.')
    parser.add_argument('--dry-run', '--simular', dest='simular', action='store_true', help='List dates and counts without changing files.')
    parser.add_argument('--no-backup', '--sem-backup', dest='sem_backup', action='store_true', help='Do not create ExifTool _original backups.')
    args = parser.parse_args()
    root = Path(args.pasta).resolve()
    if not root.is_dir():
        parser.error('The specified directory does not exist.')
    tool = shutil.which('exiftool') or next((p for p in ['/opt/homebrew/bin/exiftool', '/usr/local/bin/exiftool'] if Path(p).is_file()), None)
    if not args.simular and not tool:
        parser.error('Install ExifTool with: brew install exiftool')
    groups = defaultdict(list)
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in sorted(dirs) if not d.startswith('.') and not (Path(current)/d).is_symlink()]
        for name in sorted(files):
            path = Path(current) / name
            if path.is_symlink() or path.suffix.lower() not in EXTENSIONS:
                continue
            day = folder_date(path, root)
            if day:
                groups[day].append(path)
    total = sum(map(len, groups.values()))
    print(f'{total} photos across {len(groups)} days. Assigned time: noon, Sao Paulo time zone.', flush=True)
    # Update optional downloader indexes so edited photos are not downloaded again.
    snapshots = {}
    if not args.simular:
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith('.') and not (Path(current)/d).is_symlink()]
            if 'indice.json' in files:
                p = Path(current)/'indice.json'
                if p.is_symlink():
                    continue
                raw = p.read_bytes()
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed.get('photos'), dict):
                        snapshots[p] = (raw, parsed)
                except (ValueError, AttributeError):
                    pass
    updated = set()
    failures = 0
    for day, paths in sorted(groups.items()):
        print(f'{day}: {len(paths)} photos', flush=True)
        if args.simular:
            continue
        local = datetime.combine(day, time(12), ZoneInfo('America/Sao_Paulo'))
        offset = local.strftime('%z'); offset = offset[:3]+':'+offset[3:]
        stamp = local.strftime('%Y:%m:%d %H:%M:%S')
        zoned = stamp + offset
        for i in range(0, len(paths), 100):
            batch = paths[i:i+100]
            command = [tool, f'-EXIF:DateTimeOriginal={stamp}', f'-EXIF:CreateDate={stamp}',
                       f'-EXIF:ModifyDate={stamp}', f'-EXIF:OffsetTimeOriginal={offset}',
                       f'-EXIF:OffsetTimeDigitized={offset}', f'-EXIF:OffsetTime={offset}',
                       f'-XMP-exif:DateTimeOriginal={zoned}', f'-XMP-photoshop:DateCreated={zoned}',
                       f'-XMP-xmp:CreateDate={zoned}', f'-XMP-xmp:ModifyDate={zoned}',
                       f'-FileCreateDate={zoned}', f'-FileModifyDate={zoned}']
            if args.sem_backup:
                command += ['-overwrite_original']
            result = subprocess.run(command + [str(p) for p in batch], capture_output=True, text=True)
            print(result.stdout.strip(), flush=True)
            if result.stderr:
                print(result.stderr.strip(), file=sys.stderr)
            if result.returncode:
                failures += 1
            # Even a partial batch may modify files; reconcile all hashes.
            updated.update(batch)
    for index, (raw, state) in snapshots.items():
        if index.read_bytes() != raw:
            print(f'Index in use by another process: {index}. Stop the downloader and run again to reconcile hashes.', file=sys.stderr)
            failures += 1
            continue
        changed = False
        for info in state['photos'].values():
            if not isinstance(info, dict) or not isinstance(info.get('file'), str):
                continue
            path = (index.parent/info['file']).resolve()
            if path in updated and path.is_file() and path.is_relative_to(index.parent):
                info['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                info['bytes'] = path.stat().st_size
                info['date_source'] = 'pasta_AAAA-MM-DD_hora_convencional_12h'
                changed = True
        if changed:
            # Keep created unchanged; it still represents the original publication.
            tmp = index.with_name('indice.datas-pastas.tmp')
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
            tmp.replace(index)
    if args.simular:
        print('Dry run complete. No files changed.')
    elif failures:
        print('Completed with errors. Check the messages above.', file=sys.stderr)
        return 1
    else:
        print('Done. Dates updated without recompressing images.')
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nInterrupted. You can run it again.', file=sys.stderr)
        sys.exit(130)
    except (OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
