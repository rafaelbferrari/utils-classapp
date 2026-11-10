#!/usr/bin/env python3
"""Agrupa rostos localmente e copia fotos, com uma imagem principal por pessoa."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import urllib.request

REV = '48b10fa505aeb51fbd127fc60a5c660040e823b7'
MODELS = {
    'face_detection_yunet_2023mar.onnx': ('face_detection_yunet', '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'),
    'face_recognition_sface_2021dec.onnx': ('face_recognition_sface', '0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79'),
}
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.tif', '.tiff'}


def prepare_models(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for filename, (folder, expected) in MODELS.items():
        path = directory / filename
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            continue
        url = f'https://media.githubusercontent.com/media/opencv/opencv_zoo/{REV}/models/{folder}/{filename}'
        print(f'Baixando modelo oficial: {filename}', flush=True)
        tmp = path.with_suffix('.download')
        digest = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=90) as response, tmp.open('wb') as target:
            while True:
                chunk = response.read(1024*1024)
                if not chunk:
                    break
                digest.update(chunk)
                target.write(chunk)
        if digest.hexdigest() != expected:
            tmp.unlink(missing_ok=True)
            raise RuntimeError('O hash do modelo não confere; instalação interrompida.')
        tmp.replace(path)


def check_models(directory):
    for name, (_, digest) in MODELS.items():
        path = directory/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Modelos ausentes ou inválidos. Execute primeiro Instalar reconhecimento.command.')


def connect(path, config):
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS config (value TEXT)')
    previous = db.execute('SELECT value FROM config').fetchone()
    if previous and json.loads(previous[0]) != config:
        raise RuntimeError('Esta saída pertence a outra origem ou configuração. Escolha uma nova pasta de destino.')
    if not previous:
        db.execute('INSERT INTO config VALUES (?)', (json.dumps(config),))
    db.execute('CREATE TABLE IF NOT EXISTS people (id INTEGER PRIMARY KEY, vector TEXT NOT NULL, count INTEGER NOT NULL, quality REAL NOT NULL, preview TEXT NOT NULL, review INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS photos (path TEXT PRIMARY KEY, size INTEGER NOT NULL, modified INTEGER NOT NULL, status TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS appearances (person INTEGER, path TEXT, copy TEXT, PRIMARY KEY(person,path))')
    db.commit()
    return db


def choose_person(vector, people, used, threshold, margin, np):
    candidates = []
    for pid, person in people.items():
        if pid in used:
            continue
        center = person['vector'] / max(float(np.linalg.norm(person['vector'])), 1e-9)
        candidates.append((float(vector @ center), pid))
    candidates.sort(reverse=True)
    if not candidates or candidates[0][0] < threshold:
        return None, False
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < margin:
        return None, True
    return candidates[0][1], False


def load_image(path, maximum, Image, ImageOps, np, cv2):
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert('RGB')
        image.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def scan(source, destination):
    for current, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [d for d in sorted(dirs) if not d.startswith('.') and not (Path(current)/d).is_symlink() and (Path(current)/d).resolve() != destination]
        for name in sorted(files):
            path = Path(current)/name
            if not path.is_symlink() and path.suffix.lower() in EXTENSIONS:
                yield path


def save_preview(image, face, destination, cv2):
    x, y, w, h = [float(v) for v in face[:4]]
    height, width = image.shape[:2]
    pad = 0.30 * max(w, h)
    left, top = max(0, int(x-pad)), max(0, int(y-pad))
    right, bottom = min(width, int(x+w+pad)), min(height, int(y+h+pad))
    crop = image[top:bottom, left:right]
    if not crop.size:
        raise RuntimeError('Recorte de rosto vazio.')
    # Só o recorte de referência é convertido; as fotos completas são copiadas sem alteração.
    scale = min(1.0, 480/max(crop.shape[:2]))
    crop = cv2.resize(crop, (max(1,int(crop.shape[1]*scale)), max(1,int(crop.shape[0]*scale))))
    temporary = destination.with_name('PRINCIPAL.tmp.jpg')
    if not cv2.imwrite(str(temporary), crop, [cv2.IMWRITE_JPEG_QUALITY, 93]):
        raise RuntimeError('Não foi possível salvar a foto principal.')
    temporary.replace(destination)


def gallery(db, destination):
    cards = []
    for pid, count, review in db.execute('SELECT p.id, COUNT(a.path), p.review FROM people p LEFT JOIN appearances a ON a.person=p.id GROUP BY p.id ORDER BY p.id'):
        folder = f'Pessoa_{pid:04d}'
        preview_source = db.execute('SELECT preview FROM people WHERE id=?',(pid,)).fetchone()[0]
        (destination/folder/'PRINCIPAL-origem.txt').write_text('Foto usada no recorte principal: '+preview_source+'\n', encoding='utf-8')
        cards.append(f'<a class="card" href="{folder}/"><img loading="lazy" src="{folder}/PRINCIPAL.jpg" alt="Rosto de referência do grupo {pid}"><strong>{folder}</strong><span>{count} fotos'+(' · revisar semelhança' if review else '')+'</span></a>')
    document = '<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Pessoas nas fotos</title><style>body{font:16px system-ui;background:#f2f4f7;color:#172033;padding:28px}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:20px}.card{display:flex;flex-direction:column;gap:8px;background:white;padding:12px;border-radius:12px;text-decoration:none;color:inherit}img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px}span{font-size:14px;color:#526077}</style><h1>Pessoas nas fotos</h1><p>Grupos por semelhança facial. Confira os rostos antes de nomear as pessoas. Abra a pasta da pessoa para ver as cópias.</p><main>'+''.join(cards)+'</main></html>'
    tmp = destination/'PESSOAS.tmp.html'; tmp.write_text(document, encoding='utf-8'); tmp.replace(destination/'PESSOAS.html')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('origem', nargs='?', help='Pasta de fotos a ler. Os originais nunca são modificados.')
    parser.add_argument('--destino', help='Pasta de saída separada; padrão: NOME_DA_ORIGEM_por_pessoa ao lado da origem.')
    parser.add_argument('--modelos', default=str(Path(__file__).resolve().parent/'.modelos-pessoas'))
    parser.add_argument('--preparar-modelos', action='store_true', help='Somente instala modelos; não lê fotos.')
    parser.add_argument('--limiar', type=float, default=0.48, help='Similaridade mínima (0 a 1); maior separa mais pessoas. Padrão 0.48.')
    parser.add_argument('--margem', type=float, default=0.05, help='Diferença mínima entre os dois melhores grupos.')
    parser.add_argument('--tamanho', type=int, default=1600, help='Maior lado usado na análise; original não é redimensionado.')
    parser.add_argument('--max-fotos', type=int, help='Limita novas fotos analisadas para teste.')
    args = parser.parse_args()
    os.umask(0o077)
    models = Path(args.modelos).resolve()
    if args.preparar_modelos:
        prepare_models(models)
        print('Modelos instalados. Nenhuma pasta de fotos foi lida.')
        return
    if not args.origem:
        parser.error('Informe a pasta de origem explicitamente.')
    if not 0 < args.limiar < 1 or not 0 <= args.margem < 1 or args.tamanho < 320 or (args.max_fotos is not None and args.max_fotos < 1):
        parser.error('Parâmetros de análise inválidos.')
    source = Path(args.origem).expanduser().resolve()
    destination = Path(args.destino).expanduser().resolve() if args.destino else source.with_name(source.name+'_por_pessoa')
    if not source.is_dir() or source == destination or source in destination.parents or destination in source.parents:
        parser.error('Origem e destino devem ser pastas separadas, sem uma dentro da outra.')
    check_models(models)
    # Bibliotecas importadas só ao processar; --help e instalação não precisam ler imagens.
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
    import pillow_heif
    import fcntl
    pillow_heif.register_heif_opener()
    cv2.setNumThreads(max(1, min(4, os.cpu_count() or 1)))
    destination.mkdir(parents=True, exist_ok=True)
    lock = (destination/'.execucao.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('Já existe uma execução neste destino.')
    config = {'source':str(source), 'threshold':args.limiar, 'margin':args.margem, 'size':args.tamanho, 'version':1}
    db = connect(destination/'.pessoas.sqlite3', config)
    people = {pid:{'vector':np.array(json.loads(vector), dtype=np.float32), 'count':count, 'quality':quality, 'preview':preview, 'review':review} for pid,vector,count,quality,preview,review in db.execute('SELECT * FROM people')}
    detector = cv2.FaceDetectorYN.create(str(models/'face_detection_yunet_2023mar.onnx'), '', (320,320), 0.90, 0.3, 5000)
    recognizer = cv2.FaceRecognizerSF.create(str(models/'face_recognition_sface_2021dec.onnx'), '')
    processed = skipped = errors = 0
    try:
        for path in scan(source, destination):
            relative = str(path.relative_to(source))
            stat = path.stat()
            previous = db.execute('SELECT size,modified FROM photos WHERE path=?', (relative,)).fetchone()
            if previous:
                if previous != (stat.st_size,stat.st_mtime_ns):
                    print(f'Arquivo mudou desde a análise; use outro destino para reanalisar: {relative}', file=sys.stderr)
                    errors += 1
                else:
                    skipped += 1
                continue
            touched = []
            previews_before = {}
            committed = False
            try:
                image = load_image(path, args.tamanho, Image, ImageOps, np, cv2)
                detector.setInputSize((image.shape[1], image.shape[0]))
                _, faces = detector.detect(image)
                if faces is None:
                    faces = []
                # Filtra rostos muito pequenos; evita grupos de baixa qualidade.
                faces = [f for f in faces if min(f[2],f[3]) >= 36]
                used = set()
                assignments = []
                for face in sorted(faces, key=lambda f:float(f[2]*f[3]*f[-1]), reverse=True):
                    aligned = recognizer.alignCrop(image, face)
                    vector = recognizer.feature(aligned).flatten()
                    vector = vector / max(float(np.linalg.norm(vector)), 1e-9)
                    quality = float(min(face[2],face[3]) * min(1.0, cv2.Laplacian(aligned,cv2.CV_64F).var()/100) * face[-1])
                    pid, review = choose_person(vector, people, used, args.limiar, args.margem, np)
                    if pid is None:
                        pid = max(people, default=0)+1
                        people[pid] = {'vector':vector.copy(), 'count':0, 'quality':-1.0, 'preview':'', 'review':int(review)}
                    person = people[pid]
                    person['vector'] = (person['vector']*person['count'] + vector)/(person['count']+1)
                    person['count'] += 1
                    used.add(pid)
                    folder = destination/f'Pessoa_{pid:04d}'
                    photo_folder = folder/'fotos'/path.relative_to(source).parent
                    photo_folder.mkdir(parents=True, exist_ok=True)
                    target = photo_folder/path.name
                    touched.append(target)
                    shutil.copy2(path,target)
                    if quality > person['quality']:
                        preview_path = folder/'PRINCIPAL.jpg'
                        previews_before[preview_path] = preview_path.read_bytes() if preview_path.exists() else None
                        save_preview(image,face,preview_path,cv2)
                        person['quality'], person['preview'] = quality,relative
                    db.execute('INSERT OR REPLACE INTO people VALUES (?,?,?,?,?,?)', (pid,json.dumps(person['vector'].tolist()),person['count'],person['quality'],person['preview'],person['review']))
                    db.execute('INSERT OR REPLACE INTO appearances VALUES (?,?,?)', (pid,relative,str(target.relative_to(destination))))
                    assignments.append(pid)
                if not assignments:
                    target = destination/'Sem_rosto_detectado'/path.relative_to(source)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    touched.append(target)
                    shutil.copy2(path,target)
                # Só registra a foto se ela permaneceu estável durante a leitura.
                now = path.stat()
                if (now.st_size,now.st_mtime_ns) != (stat.st_size,stat.st_mtime_ns):
                    raise RuntimeError('A origem mudou durante a análise. Termine os downloads antes de executar.')
                db.execute('INSERT INTO photos VALUES (?,?,?,?)', (relative,stat.st_size,stat.st_mtime_ns,'faces' if assignments else 'no_face'))
                db.commit()
                committed = True
                processed += 1
                print(f'{processed} novas | {skipped} já analisadas | {len(people)} grupos | {relative}',flush=True)
                if processed % 25 == 0:
                    gallery(db,destination)
                if args.max_fotos and processed >= args.max_fotos:
                    print('Limite de teste atingido. Execute novamente para continuar.')
                    break
            except (Exception, KeyboardInterrupt) as exc:
                db.rollback()
                if not committed:
                    for target in touched:
                        target.unlink(missing_ok=True)
                    for preview_path, content in previews_before.items():
                        if content is None:
                            preview_path.unlink(missing_ok=True)
                        else:
                            preview_path.write_bytes(content)
                if isinstance(exc, KeyboardInterrupt):
                    raise
                # Recarrega vetores persistidos para não incorporar uma foto que falhou.
                people = {pid:{'vector':np.array(json.loads(v),dtype=np.float32),'count':n,'quality':q,'preview':p,'review':r} for pid,v,n,q,p,r in db.execute('SELECT * FROM people')}
                errors += 1
                print(f'Não foi possível processar {relative}: {exc}',file=sys.stderr,flush=True)
        gallery(db,destination)
        print(f'Finalizado: {processed} novas; {skipped} já analisadas; {len(people)} grupos; {errors} erros. Abra {destination / "PESSOAS.html"}',flush=True)
    finally:
        gallery(db,destination)
        db.close()
        lock.close()
    if errors:
        return 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nInterrompido. Execute de novo com a mesma origem e destino para continuar.',file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f'Erro: {exc}',file=sys.stderr)
        sys.exit(1)
