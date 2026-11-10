#!/usr/bin/env python3
"""Update photo dates from directory names and move fotos to fotos_v2 without copying."""
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

def in_place_main():
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

def date_tool():
    tool = shutil.which('exiftool') or next((p for p in ['/opt/homebrew/bin/exiftool','/usr/local/bin/exiftool'] if Path(p).is_file()), None)
    if not tool:
        raise ValueError('Install ExifTool with: brew install exiftool')
    return tool


def set_photo_date(path, day, tool):
    local = datetime.combine(day, time(12), ZoneInfo('America/Sao_Paulo'))
    stamp = local.strftime('%Y:%m:%d %H:%M:%S')
    offset = local.strftime('%z'); offset = offset[:3]+':'+offset[3:]
    zoned = stamp+offset
    command = [tool, '-overwrite_original_in_place',
               f'-EXIF:DateTimeOriginal={stamp}', f'-EXIF:CreateDate={stamp}',
               f'-EXIF:ModifyDate={stamp}', f'-EXIF:OffsetTimeOriginal={offset}',
               f'-EXIF:OffsetTimeDigitized={offset}', f'-EXIF:OffsetTime={offset}',
               f'-XMP-exif:DateTimeOriginal={zoned}', f'-XMP-photoshop:DateCreated={zoned}',
               f'-XMP-xmp:CreateDate={zoned}', f'-XMP-xmp:ModifyDate={zoned}',
               f'-FileCreateDate={zoned}', f'-FileModifyDate={zoned}', str(path)]
    result = subprocess.run(command,capture_output=True,text=True)
    if result.returncode:
        raise ValueError('ExifTool could not update a photo. No files were moved for that operation.')
    return local


def read_index(root):
    path=root/'indice.json'
    state=json.loads(path.read_text()) if path.exists() else {'photos':{}}
    if not isinstance(state.get('photos'),dict):raise ValueError('Invalid photo index.')
    return state


def save_index(root,state):
    path=root/'indice.json';tmp=root/'indice.date-migration.tmp'
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2));tmp.replace(path)


def migration_lock(destination):
    import fcntl
    listing=subprocess.check_output(['ps','-axo','pid=,comm=,args='],text=True)
    for line in listing.splitlines():
        fields=line.strip().split(None,2)
        if len(fields)==3 and int(fields[0])!=os.getpid() and 'python' in Path(fields[1]).name.lower() and 'baixar_momentos' in fields[2]:
            raise ValueError('A downloader is running. Stop it before updating dates or moving photos.')
    destination.mkdir(parents=True,exist_ok=True)
    lock=(destination/'.download-v3.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close();raise ValueError('The destination is already in use.') from None
    return lock


def migrate(source,destination,dry_run=False):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if not source.is_dir():raise ValueError('Source directory does not exist.')
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and destination must be separate directories.')
    photos=[]
    for current,dirs,files in os.walk(source,followlinks=False):
        dirs[:]=[d for d in sorted(dirs) if not d.startswith('.') and not (Path(current)/d).is_symlink()]
        for name in sorted(files):
            path=Path(current)/name
            if path.is_symlink() or path.suffix.lower() not in EXTENSIONS:continue
            day=folder_date(path,source)
            if day:photos.append((path,day))
    print(f'{len(photos)} photos: update dates from directories, then MOVE to {destination}. No image backups or copies.',flush=True)
    if dry_run:
        for day in sorted({d for _,d in photos}):print(f'{day}: {sum(d==day for _,d in photos)} photos')
        print('Dry run complete. Nothing changed.');return 0
    tool=date_tool();lock=migration_lock(destination)
    moved=deduplicated=conflicts=0
    try:
        if source.stat().st_dev!=destination.stat().st_dev:
            raise ValueError('Source and destination must be on the same filesystem; copying is disabled.')
        src_state=read_index(source);dst_state=read_index(destination)
        reconciled=False
        for key,info in list(src_state['photos'].items()):
            if not isinstance(info,dict) or not isinstance(info.get('file'),str):continue
            rel=info['file'];oldpath=(source/rel).resolve();newpath=(destination/rel).resolve()
            previous=dst_state['photos'].get(key)
            if oldpath.is_relative_to(source) and newpath.is_relative_to(destination) and not oldpath.exists() and newpath.is_file() and previous and previous.get('file')==rel and hashlib.sha256(newpath.read_bytes()).hexdigest()==previous.get('sha256'):
                src_state['photos'].pop(key);reconciled=True
        if reconciled:save_index(source,src_state)
        source_keys={info.get('file'):key for key,info in src_state['photos'].items() if isinstance(info,dict)}
        for path,day in photos:
            relative=path.relative_to(source);target=destination/relative
            if not target.resolve().is_relative_to(destination):raise ValueError('Invalid destination path.')
            key=source_keys.get(str(relative))
            if key is None:
                match=re.fullmatch(r'\d+_(\d+)',path.stem)
                key=match.group(1) if match else 'local:'+hashlib.sha256(str(relative).encode()).hexdigest()[:24]
            previous=dst_state['photos'].get(key)
            if previous and previous.get('file')!=str(relative):
                print(f'Conflict: media ID already uses another destination path: {relative}',file=sys.stderr);conflicts+=1;continue
            original_hash=hashlib.sha256(path.read_bytes()).hexdigest()
            duplicate=False
            if target.exists():
                if not target.is_file() or target.is_symlink():
                    print(f'Conflict: destination is not a regular file: {relative}',file=sys.stderr);conflicts+=1;continue
                target_hash=hashlib.sha256(target.read_bytes()).hexdigest()
                duplicate=target_hash==original_hash or bool(previous and previous.get('migration_source_sha256')==original_hash and previous.get('sha256')==target_hash)
                if not duplicate:
                    print(f'Conflict: different file already exists; source preserved: {relative}',file=sys.stderr);conflicts+=1;continue
            working=target if duplicate else path
            local=set_photo_date(working,day,tool)
            content_hash=hashlib.sha256(working.read_bytes()).hexdigest()
            info=dict(src_state['photos'].get(key) or previous or {})
            info.update(file=str(relative),sha256=content_hash,bytes=working.stat().st_size,
                        date_source='folder_date_noon_sao_paulo',photo_datetime=local.isoformat(),
                        metadata_version=2,migration_source_sha256=original_hash)
            info.setdefault('created',local.isoformat())
            info.setdefault('moment_id',path.stem.split('_')[0])
            info.setdefault('original_name',path.name)
            # Persist the target record before the atomic move/removal. A failed move leaves the source intact.
            old=dst_state['photos'].get(key)
            dst_state['photos'][key]=info;save_index(destination,dst_state)
            try:
                if duplicate:
                    if hashlib.sha256(path.read_bytes()).hexdigest()!=original_hash:
                        raise ValueError('Source changed during migration; duplicate was not removed.')
                    path.unlink();deduplicated+=1
                else:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    if target.exists():raise ValueError('Destination appeared during migration; source preserved.')
                    path.rename(target);moved+=1
            except Exception:
                if not duplicate:
                    if old is None:dst_state['photos'].pop(key,None)
                    else:dst_state['photos'][key]=old
                    save_index(destination,dst_state)
                    if key in src_state['photos']:
                        src_state['photos'][key].update(sha256=content_hash,bytes=path.stat().st_size)
                        save_index(source,src_state)
                raise
            src_state['photos'].pop(key,None);save_index(source,src_state)
            print(f'Moved: {moved} | identical duplicates removed: {deduplicated} | conflicts: {conflicts}',flush=True)
        # Remove only empty dated directories. Non-photo files and conflicting files stay untouched.
        for current,dirs,files in os.walk(source,topdown=False,followlinks=False):
            folder=Path(current)
            if folder!=source and not folder.is_symlink() and folder_date(folder/'placeholder',source):
                try:folder.rmdir()
                except OSError:pass
        print(f'Complete: {moved} moved, {deduplicated} identical duplicates removed, {conflicts} conflicts preserved.')
        return 1 if conflicts else 0
    finally:lock.close()


def main():
    if '--in-place' in sys.argv:
        sys.argv.remove('--in-place')
        return in_place_main()
    parser=argparse.ArgumentParser(description='Update photo dates from fotos/YYYY-MM-DD and move files to fotos_v2 without copying.')
    parser.add_argument('source',nargs='?',default='fotos')
    parser.add_argument('--destination','--destino',dest='destination',default='fotos_v2')
    parser.add_argument('--dry-run','--simular',dest='dry_run',action='store_true')
    args=parser.parse_args();os.umask(0o077)
    return migrate(args.source,args.destination,args.dry_run)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nInterrupted. You can run it again.', file=sys.stderr)
        sys.exit(130)
    except (OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
