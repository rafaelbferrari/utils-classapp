"""AdaFace feature caching and constrained global grouping for separar_pessoas.py."""
import ctypes
from datetime import datetime
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import urllib.request
import uuid

MODEL_NAME='adaface_ir_50.onnx'
MODEL_SHA='9c0ae385d7362323c92d218de598d32e52a9130b78faac6a8a924091aca62c0b'
MODEL_URL='https://github.com/yakhyo/adaface-onnx/releases/download/weights/'+MODEL_NAME


def prepare_model(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/MODEL_NAME
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==MODEL_SHA:return
    print('Downloading AdaFace IR-50 (about 166 MB); no photos are uploaded.',flush=True)
    temp=path.with_suffix('.download');digest=hashlib.sha256()
    with urllib.request.urlopen(MODEL_URL,timeout=120) as response,temp.open('wb') as output:
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            digest.update(chunk);output.write(chunk)
    if digest.hexdigest()!=MODEL_SHA:
        temp.unlink(missing_ok=True);raise RuntimeError('AdaFace model checksum mismatch.')
    temp.replace(path)


class AdaFace:
    def __init__(self,path):
        import onnxruntime as ort
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
        self.input=self.session.get_inputs()[0].name

    def aligned(self,image,face):
        import cv2
        import numpy as np
        template=np.array([[38.2946,51.6963],[73.5318,51.5014],[56.0252,71.7366],[41.5493,92.3655],[70.7299,92.2041]],dtype=np.float32)
        points=face[4:14].reshape(5,2).astype(np.float32)
        matrix,_=cv2.estimateAffinePartial2D(points,template,method=cv2.LMEDS)
        if matrix is None:raise ValueError('Face alignment failed.')
        return cv2.warpAffine(image,matrix,(112,112),borderValue=0)

    def feature(self,aligned):
        import cv2
        import numpy as np
        # AdaFace expects BGR, unlike many ArcFace exports. Do not swap RGB channels.
        blob=cv2.dnn.blobFromImage(aligned,1/127.5,(112,112),(127.5,127.5,127.5),swapRB=False)
        vector=self.session.run(None,{self.input:blob})[0].reshape(-1).astype(np.float32)
        norm=np.linalg.norm(vector)
        if not np.isfinite(norm) or norm<=0:raise ValueError('Invalid face descriptor.')
        return vector/norm


def copy_photo(source,target):
    """Use independent APFS copy-on-write clones on macOS, never links to originals."""
    source,target=Path(source),Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    if sys.platform=='darwin':
        libc=ctypes.CDLL(None,use_errno=True)
        clone=getattr(libc,'clonefile',None)
        if clone:
            clone.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint32];clone.restype=ctypes.c_int
            if clone(os.fsencode(source),os.fsencode(target),0)==0:return
    if shutil.disk_usage(target.parent).free<source.stat().st_size+256*1024*1024:
        raise OSError('Not enough free space to safely copy another photo.')
    shutil.copy2(source,target)


def cache_connect(path,config):
    db=sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS settings(value TEXT)')
    previous=db.execute('SELECT value FROM settings').fetchone()
    if previous and json.loads(previous[0])!=config:
        db.close();raise RuntimeError('The face cache uses another model or detection configuration. Choose a new output directory.')
    if not previous:db.execute('INSERT INTO settings VALUES (?)',(json.dumps(config),))
    db.execute('CREATE TABLE IF NOT EXISTS photos(path TEXT PRIMARY KEY,size INTEGER,modified INTEGER,status TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS faces(id INTEGER PRIMARY KEY,path TEXT,vector BLOB,quality REAL,crop TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS rejected(id INTEGER PRIMARY KEY,path TEXT,crop TEXT,reason TEXT)')
    db.commit();return db


def constrained_groups(vectors,photos,qualities,names=None,threshold=.42,floor=.25,neighbors=30):
    """Global HNSW candidates, co-occurrence constraints, and diverse-reference checks."""
    import faiss
    import numpy as np
    n=len(vectors)
    if not n:return []
    vectors=np.ascontiguousarray(vectors,dtype=np.float32)
    vectors/=np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-8)
    faiss.omp_set_num_threads(4)
    index=faiss.IndexHNSWFlat(vectors.shape[1],32,faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efConstruction=100;index.hnsw.efSearch=96;index.add(vectors)
    parent=list(range(n));members={i:[i] for i in range(n)}
    seen={i:({photos[i]} if photos[i] is not None else set()) for i in range(n)}
    tags={i:({names[i]} if names and names[i] else set()) for i in range(n)}
    refs={i:[i] for i in range(n)}
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    edges=[]
    for start in range(0,n,512):
        scores,ids=index.search(vectors[start:start+512],min(neighbors+1,n))
        for offset,(distances,indices) in enumerate(zip(scores,ids)):
            i=start+offset
            for score,j in zip(distances,indices):
                j=int(j)
                if j<0 or i==j or score<threshold:continue
                # Directional candidates are deduplicated after sorting; reciprocal matches are not required.
                edges.append((float(score),min(i,j),max(i,j)))
    edges=sorted(set(edges),reverse=True)
    for score,i,j in edges:
        a,b=find(i),find(j)
        if a==b or seen[a]&seen[b]:continue
        if tags[a] and tags[b] and tags[a]!=tags[b]:continue
        # Cross-reference support limits transitive chains through lookalike faces.
        if float(np.min(vectors[refs[a]]@vectors[refs[b]].T))<floor:continue
        if len(members[a])<len(members[b]):a,b=b,a
        parent[b]=a;members[a]+=members.pop(b);seen[a]|=seen.pop(b);tags[a]|=tags.pop(b)
        candidates=list(dict.fromkeys(refs[a]+refs.pop(b)))
        # Keep up to eight diverse references, anchored by the clearest appearance.
        chosen=[max(candidates,key=lambda k:qualities[k])]
        while len(chosen)<min(8,len(candidates)):
            remaining=[k for k in candidates if k not in chosen]
            chosen.append(min(remaining,key=lambda k:float(np.max(vectors[k]@vectors[chosen].T))))
        refs[a]=chosen
    return sorted(members.values(),key=lambda g:min(g))


def label_references(directories,recognizer,detector,cv2,np,Image,ImageOps,helper,size):
    refs=[];used=set()
    for directory in directories:
        directory=Path(directory).resolve();database=directory/'.pessoas.sqlite3'
        if database in used or not database.exists():continue
        used.add(database)
        # SQLite backup creates a consistent in-memory snapshot, even for an open read-only manager.
        source=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True);db=sqlite3.connect(':memory:')
        source.backup(db);source.close()
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='person_names'").fetchone()
        if not exists:db.close();continue
        rows=db.execute("SELECT p.id,n.name FROM people p JOIN person_names n ON p.id=n.person WHERE trim(n.name)!=''").fetchall()
        for pid,name in rows:
            folder=helper.group_folder(db,pid);path=(directory/folder/'PRINCIPAL.jpg').resolve()
            if not path.is_relative_to(directory) or not path.exists():continue
            try:
                image=helper.load_image(path,size,Image,ImageOps,np,cv2)
                detector.setInputSize((image.shape[1],image.shape[0]));_,faces=detector.detect(image)
                if faces is None or len(faces)!=1:continue
                face=faces[0];aligned=recognizer.aligned(image,face)
                refs.append((recognizer.feature(aligned),str(name),1e6,str(path)))
            except (ValueError,OSError,cv2.error):continue
        db.close()
    print(f'Imported {len(refs)} named reference faces from previous outputs.',flush=True)
    return refs


def export_result(source,destination,cache,rows,groups,vectors,seeds,args,helper):
    import numpy as np
    import manage_face_groups
    stage=destination/('.export-staging-'+uuid.uuid4().hex);stage.mkdir()
    db=None
    try:
        config={'source':str(source),'engine':'adaface-ir50','version':2,'threshold':args.limiar,'min_photos':args.min_photos}
        db=helper.connect(stage/'.pessoas.sqlite3',config)
        db.execute('CREATE TABLE person_names(person INTEGER PRIMARY KEY,name TEXT NOT NULL)')
        db.execute('CREATE TABLE person_folders(person INTEGER PRIMARY KEY,folder TEXT NOT NULL UNIQUE)')
        db.executemany('INSERT INTO photos VALUES (?,?,?,?)',cache.execute('SELECT * FROM photos').fetchall())
        source_faces=len(rows);pid=0;pending=[]
        for cluster in groups:
            indices=[i for i in cluster if i<source_faces]
            if not indices:continue
            paths=sorted({rows[i][1] for i in indices})
            labels={seeds[i-source_faces][1] for i in cluster if i>=source_faces}
            if len(paths)<args.min_photos and not labels:
                pending.extend(indices);continue
            pid+=1;name=sorted(labels)[0] if labels else ''
            folder=manage_face_groups.Manager.named_folder(pid,name)
            out=stage/folder;(out/'fotos').mkdir(parents=True)
            best=max(indices,key=lambda i:rows[i][3]);best_row=rows[best]
            shutil.copy2(destination/best_row[4],out/'PRINCIPAL.jpg')
            mean=np.mean(vectors[indices],axis=0)
            mean/=max(float(np.linalg.norm(mean)),1e-8)
            db.execute('INSERT INTO people VALUES (?,?,?,?,?,?)',(pid,json.dumps(mean.tolist()),len(indices),best_row[3],best_row[1],0))
            if name:db.execute('INSERT INTO person_names VALUES (?,?)',(pid,name))
            db.execute('INSERT INTO person_folders VALUES (?,?)',(pid,folder))
            for path in paths:
                origin=(source/path).resolve();target=(out/'fotos'/path).resolve()
                if not origin.is_relative_to(source) or not target.is_relative_to(out.resolve()):raise RuntimeError('Invalid cached photo path.')
                copy_photo(origin,target)
                db.execute('INSERT INTO appearances VALUES (?,?,?)',(pid,path,str(target.relative_to(stage))))
        review=stage/'Needs_review';review.mkdir()
        cards=[]
        for i in pending:
            fid,path,_,quality,crop=rows[i]
            target=review/f'face_{fid}.jpg';shutil.copy2(destination/crop,target)
            cards.append(f'<figure><img loading="lazy" src="Needs_review/face_{fid}.jpg" alt="Unconfirmed face"><figcaption>{html.escape(path)}</figcaption></figure>')
        rejected=cache.execute('SELECT id,path,crop,reason FROM rejected').fetchall()
        for rid,path,crop,reason in rejected:
            shutil.copy2(destination/crop,review/f'rejected_{rid}.jpg')
            cards.append(f'<figure><img loading="lazy" src="Needs_review/rejected_{rid}.jpg" alt="Filtered face"><figcaption>{html.escape(reason+": "+path)}</figcaption></figure>')
        (stage/'REVIEW.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Unconfirmed faces</title><style>body{font:16px system-ui}main{display:flex;flex-wrap:wrap}figure{width:160px;overflow-wrap:anywhere}img{width:160px}</style><h1>Faces needing more evidence</h1><p>These faces need more distinct photos or were too small or blurred for recognition. They were not assigned person directories.</p><main>'+''.join(cards)+'</main></html>')
        db.commit();helper.gallery(db,stage);db.close();db=None
        summary={'engine':'AdaFace IR-50','photos_analyzed':cache.execute('SELECT COUNT(*) FROM photos').fetchone()[0],
                 'usable_face_appearances':source_faces,'person_groups':pid,'unconfirmed_faces':len(pending),'filtered_faces':len(rejected),
                 'min_photos':args.min_photos,'threshold':args.limiar,'named_references':len(seeds)}
        (stage/'analysis_summary.json').write_text(json.dumps(summary,indent=2))
        # Archive the earlier export instead of overwriting manual edits or folders.
        old_db=destination/'.pessoas.sqlite3'
        old_folders=[]
        if old_db.exists():
            with sqlite3.connect(old_db) as previous:
                old_folders=[helper.group_folder(previous,r[0]) for r in previous.execute('SELECT id FROM people')]
        backup=destination/'.previous-exports'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        published=[];archived=[]
        try:
            for name in old_folders+['.pessoas.sqlite3','PESSOAS.html','REVIEW.html','Needs_review','analysis_summary.json']:
                path=destination/name
                if path.exists():
                    backup.mkdir(parents=True,exist_ok=True);path.rename(backup/name);archived.append(name)
            for path in list(stage.iterdir()):
                path.rename(destination/path.name);published.append(path.name)
        except BaseException:
            for name in published:
                p=destination/name
                if p.is_dir():shutil.rmtree(p)
                else:p.unlink(missing_ok=True)
            for name in archived:(backup/name).rename(destination/name)
            raise
        print('Analysis complete:',json.dumps(summary),flush=True)
        print('Gallery:',destination/'PESSOAS.html',flush=True)
        print('Unconfirmed faces:',destination/'REVIEW.html',flush=True)
        return summary
    finally:
        if db is not None:db.close()
        if stage.exists():shutil.rmtree(stage)


def run(args,source,destination,helper):
    import cv2
    import numpy as np
    import pillow_heif
    from PIL import Image,ImageOps
    import fcntl
    pillow_heif.register_heif_opener();cv2.setNumThreads(4)
    model=Path(args.modelos)/MODEL_NAME
    if not model.exists() or hashlib.sha256(model.read_bytes()).hexdigest()!=MODEL_SHA:
        raise RuntimeError('Run Install face recognition.command to install the AdaFace model first.')
    destination.mkdir(parents=True,exist_ok=True)
    lock=(destination/'.execucao.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('Grouping or its manager is active in this destination.') from None
    cache=None
    try:
        detector=cv2.FaceDetectorYN.create(str(Path(args.modelos)/'face_detection_yunet_2023mar.onnx'),'',(320,320),.90,.3,5000)
        recognizer=AdaFace(model)
        config={'source':str(source),'model_sha256':MODEL_SHA,'size':args.tamanho,'min_face':args.min_face,'min_sharpness':args.min_sharpness,'version':2}
        cache=cache_connect(destination/'.face-cache.sqlite3',config)
        processed=skipped=errors=0
        for path in helper.scan(source,destination):
            relative=str(path.relative_to(source));stat=path.stat()
            previous=cache.execute('SELECT size,modified FROM photos WHERE path=?',(relative,)).fetchone()
            if previous:
                if previous!=(stat.st_size,stat.st_mtime_ns):raise RuntimeError('A cached source photo changed. Use a new destination to avoid stale face descriptors.')
                skipped+=1;continue
            crops=[]
            try:
                image=helper.load_image(path,args.tamanho,Image,ImageOps,np,cv2)
                detector.setInputSize((image.shape[1],image.shape[0]));_,faces=detector.detect(image)
                count=0
                for face in ([] if faces is None else faces):
                    aligned=recognizer.aligned(image,face)
                    sharp=float(cv2.Laplacian(aligned,cv2.CV_64F).var())
                    reason='Small face' if min(face[2],face[3])<args.min_face else ('Blurred face' if sharp<args.min_sharpness else '')
                    if reason:
                        cursor=cache.execute('INSERT INTO rejected(path,crop,reason) VALUES (?,?,?)',(relative,'',reason))
                        rid=cursor.lastrowid;crop=Path('.rejected-crops')/f'{rid}.jpg';(destination/crop).parent.mkdir(exist_ok=True)
                        helper.save_preview(image,face,destination/crop,cv2);crops.append(destination/crop)
                        cache.execute('UPDATE rejected SET crop=? WHERE id=?',(str(crop),rid))
                        continue
                    vector=recognizer.feature(aligned)
                    quality=float(min(face[2],face[3])*min(1.,sharp/100)*face[-1])
                    cursor=cache.execute('INSERT INTO faces(path,vector,quality,crop) VALUES (?,?,?,?)',(relative,vector.tobytes(),quality,''))
                    fid=cursor.lastrowid;crop=Path('.face-crops')/f'{fid}.jpg';(destination/crop).parent.mkdir(exist_ok=True)
                    helper.save_preview(image,face,destination/crop,cv2);crops.append(destination/crop)
                    cache.execute('UPDATE faces SET crop=? WHERE id=?',(str(crop),fid));count+=1
                after=path.stat()
                if (after.st_size,after.st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):raise RuntimeError('Source changed during extraction; finish downloads first.')
                cache.execute('INSERT INTO photos VALUES (?,?,?,?)',(relative,stat.st_size,stat.st_mtime_ns,'faces' if count else 'no_usable_face'));cache.commit()
                processed+=1
                print(f'Feature extraction: {processed} new | {skipped} cached | {cache.execute("SELECT COUNT(*) FROM faces").fetchone()[0]} face appearances',flush=True)
                if args.max_fotos and processed>=args.max_fotos:break
            except (Exception,KeyboardInterrupt) as exc:
                cache.rollback()
                for crop in crops:crop.unlink(missing_ok=True)
                if isinstance(exc,KeyboardInterrupt):raise
                errors+=1;print(f'Could not analyze {relative}: {exc}',file=sys.stderr)
        if errors:raise RuntimeError(f'{errors} photos failed. Features were cached; rerun to retry before exporting groups.')
        # Avoid silently regenerating manually edited exports when nothing changed.
        if (destination/'.pessoas.sqlite3').exists() and not processed and not args.regroup:
            print('No new photos. Existing groups and manual corrections were preserved. Use --regroup to rebuild from cached features.')
            return 0
        rows=cache.execute('SELECT id,path,vector,quality,crop FROM faces ORDER BY id').fetchall()
        vectors=[np.frombuffer(row[2],dtype=np.float32).copy() for row in rows]
        label_dirs=[Path(p) for p in (args.labels_from or [])]
        default=source.with_name(source.name+'_por_pessoa')
        if default.exists():label_dirs.append(default)
        if (destination/'.pessoas.sqlite3').exists():label_dirs.append(destination)
        seeds=label_references(label_dirs,recognizer,detector,cv2,np,Image,ImageOps,helper,args.tamanho)
        vectors += [s[0] for s in seeds]
        photos=[r[1] for r in rows]+[None]*len(seeds)
        qualities=[r[3] for r in rows]+[s[2] for s in seeds]
        names=['']*len(rows)+[s[1].casefold().strip() for s in seeds]
        print(f'Global grouping: {len(rows)} face appearances, {len(seeds)} named references. This stage creates no folders until grouping finishes.',flush=True)
        vectors=np.asarray(vectors,dtype=np.float32) if vectors else np.empty((0,512),dtype=np.float32)
        clusters=constrained_groups(vectors,photos,qualities,names,args.limiar,args.reference_floor)
        export_result(source,destination,cache,rows,clusters,vectors,seeds,args,helper)
        return 0
    finally:
        if cache is not None:cache.close()
        lock.close()
