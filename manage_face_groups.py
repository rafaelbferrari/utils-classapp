#!/usr/bin/env python3
"""Local-only interface to name, merge, and undo face groups."""
import argparse
from datetime import datetime
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import threading
import urllib.parse
import uuid
import webbrowser

class Manager:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.database = self.root/'.pessoas.sqlite3'
        if not self.database.is_file():
            raise ValueError('Choose the grouping result directory containing .pessoas.sqlite3.')
        self.lock = (self.root/'.execucao.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Face grouping or another manager is running in this directory.') from None
        self.mutex = threading.RLock()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS person_names (person INTEGER PRIMARY KEY, name TEXT NOT NULL)')
        self.history = self.root/'.management-history'
        self.history.mkdir(exist_ok=True)

    def db(self):
        return sqlite3.connect(self.database)

    def digest(self):
        with self.db() as db:
            rows = {table: sorted(db.execute('SELECT * FROM '+table).fetchall(), key=repr)
                    for table in ('config','people','photos','appearances','person_names')}
        return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()

    def safe(self, relative):
        path = (self.root/relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Invalid output path.')
        return path

    def groups(self):
        with self.db() as db:
            result = [{'id':pid,'name':name or '', 'count':count,'review':bool(review)} for pid,name,count,review in db.execute('SELECT p.id,n.name,COUNT(a.path),p.review FROM people p LEFT JOIN person_names n ON n.person=p.id LEFT JOIN appearances a ON a.person=p.id GROUP BY p.id ORDER BY p.id')]
        return {'groups':result,'can_undo':self.latest() is not None}

    def latest(self):
        for folder in sorted(self.history.iterdir(), reverse=True):
            path = folder/'action.json'
            if path.is_file():
                action = json.loads(path.read_text())
                if action.get('committed') and not action.get('undone'):
                    return folder, action
        return None

    def snapshot(self, action):
        folder = self.history/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-'+uuid.uuid4().hex[:6])
        folder.mkdir()
        with self.db() as source, sqlite3.connect(folder/'before.sqlite3') as backup:
            source.backup(backup)
        action.update(committed=False,undone=False)
        (folder/'action.json').write_text(json.dumps(action))
        return folder

    def finish(self, folder, action):
        action.update(committed=True,after=self.digest(),undone=False)
        (folder/'action.json').write_text(json.dumps(action))
        self.refresh_gallery()

    def refresh_gallery(self):
        from separar_pessoas import gallery
        with self.db() as db:
            gallery(db,self.root)

    def rename(self, pid, name):
        name = str(name).strip()
        if len(name)>100 or any(ord(c)<32 for c in name):
            raise ValueError('Names must have at most 100 characters and no control characters.')
        with self.mutex:
            with self.db() as db:
                if not db.execute('SELECT 1 FROM people WHERE id=?',(pid,)).fetchone():
                    raise ValueError('Group not found.')
            action={'kind':'rename','person':pid}
            folder=self.snapshot(action)
            with self.db() as db:
                db.execute('INSERT OR REPLACE INTO person_names VALUES (?,?)',(pid,name))
            self.finish(folder,action)

    def merge(self, ids, target, name):
        ids=sorted(set(int(i) for i in ids))
        if len(ids)<2 or target not in ids:
            raise ValueError('Select at least two groups and keep one of them as the target.')
        name=str(name).strip()
        if len(name)>100 or any(ord(c)<32 for c in name):
            raise ValueError('Invalid name.')
        with self.mutex:
            with self.db() as db:
                people=[db.execute('SELECT * FROM people WHERE id=?',(pid,)).fetchone() for pid in ids]
                if any(p is None for p in people):raise ValueError('A selected group no longer exists.')
                appearances=[]
                for pid in ids:
                    appearances.extend(db.execute('SELECT path,copy FROM appearances WHERE person=?',(pid,)))
            # Prepare a complete replacement first; original group trees stay intact until ready.
            stage=self.root/('.merge-staging-'+uuid.uuid4().hex)
            stage.mkdir()
            unique={}
            try:
                for path,copy in appearances:
                    if path in unique:continue
                    source=self.safe(copy)
                    rel=Path('fotos')/path
                    dest=stage/rel
                    if not dest.resolve().is_relative_to(stage.resolve()):raise ValueError('Invalid photo path.')
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,dest)
                    unique[path]=str(Path(f'Pessoa_{target:04d}')/rel)
                best=max(people,key=lambda p:p[3])
                shutil.copy2(self.root/f'Pessoa_{best[0]:04d}'/'PRINCIPAL.jpg',stage/'PRINCIPAL.jpg')
                vectors=[json.loads(p[1]) for p in people]
                total=sum(p[2] for p in people)
                vector=[sum(v[j]*p[2] for v,p in zip(vectors,people))/max(total,1) for j in range(len(vectors[0]))]
                action={'kind':'merge','ids':ids,'target':target}
                folder=self.snapshot(action)
                archived=folder/'groups';archived.mkdir()
                moved=[]
                try:
                    for pid in ids:
                        src=self.root/f'Pessoa_{pid:04d}'
                        src.rename(archived/src.name);moved.append(src.name)
                    stage.rename(self.root/f'Pessoa_{target:04d}')
                    with self.db() as db:
                        for pid in ids:
                            db.execute('DELETE FROM appearances WHERE person=?',(pid,))
                            db.execute('DELETE FROM people WHERE id=?',(pid,))
                            db.execute('DELETE FROM person_names WHERE person=?',(pid,))
                        db.execute('INSERT INTO people VALUES (?,?,?,?,?,?)',(target,json.dumps(vector),total,best[3],best[4],0))
                        db.execute('INSERT INTO person_names VALUES (?,?)',(target,name))
                        db.executemany('INSERT INTO appearances VALUES (?,?,?)',[(target,p,c) for p,c in unique.items()])
                except Exception:
                    replacement=self.root/f'Pessoa_{target:04d}'
                    if replacement.exists() and (archived/replacement.name).exists():
                        shutil.rmtree(replacement)
                    for part in moved:
                        (archived/part).rename(self.root/part)
                    raise
                self.finish(folder,action)
            finally:
                if stage.exists():shutil.rmtree(stage)

    def undo(self):
        with self.mutex:
            latest=self.latest()
            if not latest:raise ValueError('There is no action to undo.')
            folder,action=latest
            if self.digest()!=action['after']:
                raise ValueError('Grouping data changed outside this manager; automatic undo is unavailable. Backups are preserved.')
            if action['kind']=='merge':
                current=self.root/f'Pessoa_{action["target"]:04d}'
                current.rename(folder/'merged-result')
                for pid in action['ids']:
                    src=folder/'groups'/f'Pessoa_{pid:04d}'
                    src.rename(self.root/src.name)
            with sqlite3.connect(folder/'before.sqlite3') as source,self.db() as target:
                source.backup(target)
            action['undone']=True
            (folder/'action.json').write_text(json.dumps(action))
            self.refresh_gallery()

    def photo(self,pid,index=None):
        if index is None:return self.safe(f'Pessoa_{pid:04d}/PRINCIPAL.jpg')
        with self.db() as db:
            row=db.execute('SELECT copy FROM appearances WHERE person=? ORDER BY path LIMIT 1 OFFSET ?',(pid,index)).fetchone()
        if not row:raise ValueError('Photo not found.')
        return self.safe(row[0])

PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Manage face groups</title>
<style>body{font:16px system-ui;background:#f3f5f8;color:#162237;margin:0}header{padding:24px 5vw;background:#fff;border-bottom:1px solid #dce1e8}h1{margin:0 0 8px}p{color:#526071}button,input,select{font:inherit;border:1px solid #c6ced9;border-radius:8px;padding:10px}button{cursor:pointer;background:#fff}button.primary{background:#244bc4;color:white;border-color:#244bc4}button:disabled{opacity:.5;cursor:wait}.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:20px}main{padding:24px 5vw;display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:20px}.card{background:#fff;padding:14px;border:2px solid transparent;border-radius:14px}.card.selected{border-color:#244bc4}img.face{width:100%;aspect-ratio:1;object-fit:cover;border-radius:9px}.card label{display:block;margin:10px 0}.card input.name{box-sizing:border-box;width:100%;margin:8px 0}.buttons{display:flex;gap:8px}.small{font-size:13px;color:#526071}#status{min-height:24px;color:#244bc4}dialog{border:0;border-radius:16px;max-width:900px;width:85vw;padding:24px}dialog::backdrop{background:#0007}.photos{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;max-height:65vh;overflow:auto}.photos img{width:100%;border-radius:8px}input[type=checkbox]{accent-color:#244bc4}#search{min-width:220px}</style>
<header><h1>Manage face groups</h1><p>Name people and merge groups that show the same person. Original source photos remain unchanged.</p><div class="toolbar"><input id="search" placeholder="Search names or group IDs" aria-label="Search groups"><button id="merge" class="primary">Merge selected groups</button><button id="clear">Clear selection</button><button id="undo">Undo last change</button><span id="selection"></span></div><p id="status" role="status"></p></header><main id="groups"></main>
<dialog id="mergeDialog"><h2>Merge selected groups</h2><p>All unique photos will be collected under the retained group. A backup is saved so this can be undone.</p><label>Keep group <select id="target"></select></label><p><label>Person’s name <input id="mergedName" maxlength="100"></label></p><p id="mergeSummary"></p><button id="confirmMerge" class="primary">Merge groups</button> <button onclick="document.querySelector('#mergeDialog').close()">Cancel</button></dialog>
<dialog id="photoDialog"><h2 id="photoTitle"></h2><button onclick="document.querySelector('#photoDialog').close()">Close</button><p></p><div class="photos" id="photoGrid"></div></dialog>
<script>const TOKEN='__TOKEN__';let groups=[],selected=new Set(),busy=false,canUndo=false;const $=s=>document.querySelector(s);function status(s){$('#status').textContent=s}async function api(path,data){const r=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':TOKEN},body:JSON.stringify(data)}:{});const result=await r.json();if(!r.ok)throw Error(result.error||'Request failed');return result}function label(g){return g.name||`Person ${String(g.id).padStart(4,'0')}`}function setBusy(b){busy=b;document.querySelectorAll('button').forEach(x=>x.disabled=b);if(!b)$('#undo').disabled=!canUndo}async function load(){const r=await api('/api/groups');groups=r.groups;canUndo=r.can_undo;selected=new Set([...selected].filter(id=>groups.some(g=>g.id===id)));render();$('#undo').disabled=!r.can_undo}function render(){const q=$('#search').value.toLowerCase();$('#groups').replaceChildren();for(const g of groups){if(!`${label(g)} ${g.id}`.toLowerCase().includes(q))continue;const c=document.createElement('section');c.className='card'+(selected.has(g.id)?' selected':'');const img=document.createElement('img');img.className='face';img.src=`/image/${g.id}?v=${Date.now()}`;img.alt=`Reference face for ${label(g)}`;c.append(img);const l=document.createElement('label');const check=document.createElement('input');check.type='checkbox';check.checked=selected.has(g.id);check.onchange=()=>{check.checked?selected.add(g.id):selected.delete(g.id);render()};l.append(check,document.createTextNode(` Group ${g.id} · ${g.count} photos`));c.append(l);const input=document.createElement('input');input.className='name';input.placeholder='Enter person’s name';input.value=g.name;input.maxLength=100;input.setAttribute('aria-label',`Name for group ${g.id}`);c.append(input);const buttons=document.createElement('div');buttons.className='buttons';const save=document.createElement('button');save.textContent='Save name';save.onclick=()=>mutate('/api/name',{id:g.id,name:input.value},'Name saved.');const view=document.createElement('button');view.textContent='View photos';view.onclick=()=>showPhotos(g);buttons.append(save,view);c.append(buttons);if(g.review){const p=document.createElement('p');p.className='small';p.textContent='Review similarity';c.append(p)}$('#groups').append(c)}$('#selection').textContent=`${selected.size} groups selected`}async function mutate(path,data,message){if(busy)return;setBusy(true);status('Saving…');try{await api(path,data);await load();status(message)}catch(e){status(e.message)}finally{setBusy(false)}}function showPhotos(g){$('#photoTitle').textContent=label(g);$('#photoGrid').replaceChildren();for(let i=0;i<g.count;i++){const a=document.createElement('a');a.href=`/image/${g.id}/${i}`;a.target='_blank';a.rel='noopener';const img=document.createElement('img');img.loading='lazy';img.src=a.href;img.alt=`Photo ${i+1}`;a.append(img);$('#photoGrid').append(a)}$('#photoDialog').showModal()}$('#search').oninput=render;$('#clear').onclick=()=>{selected.clear();render()};$('#merge').onclick=()=>{if(selected.size<2){status('Select at least two groups showing the same person.');return}const chosen=groups.filter(g=>selected.has(g.id));$('#target').replaceChildren();for(const g of chosen){const o=document.createElement('option');o.value=g.id;o.textContent=`${label(g)} (group ${g.id})`;$('#target').append(o)}$('#mergedName').value=chosen[0].name;$('#mergeSummary').textContent=`${chosen.length} groups selected. Duplicate photos will appear once in the merged group.`;$('#mergeDialog').showModal()};$('#target').onchange=()=>{$('#mergedName').value=groups.find(g=>g.id===Number($('#target').value)).name};$('#confirmMerge').onclick=async()=>{$('#mergeDialog').close();await mutate('/api/merge',{ids:[...selected],target:Number($('#target').value),name:$('#mergedName').value},'Groups merged. You can undo this change.');selected.clear();render()};$('#undo').onclick=()=>mutate('/api/undo',{},'Last change undone.');load().catch(e=>status(e.message));</script></html>'''


def serve(manager,port=0):
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,body,content_type='application/json'):
            if isinstance(body,dict):body=json.dumps(body).encode()
            elif isinstance(body,str):body=body.encode()
            self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.end_headers();self.wfile.write(body)
        def allowed(self):
            return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
        def do_GET(self):
            if not self.allowed():return self.send(403,{'error':'Invalid host.'})
            path=urllib.parse.urlsplit(self.path).path
            try:
                with manager.mutex:
                    if path=='/':return self.send(200,PAGE.replace('__TOKEN__',token),'text/html; charset=utf-8')
                    if path=='/api/groups':return self.send(200,manager.groups())
                    if path.startswith('/image/'):
                        parts=path.split('/')[2:];pid=int(parts[0]);index=int(parts[1]) if len(parts)>1 else None
                        image=manager.photo(pid,index)
                        types={'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp','.heic':'image/heic','.tiff':'image/tiff'}
                        return self.send(200,image.read_bytes(),types.get(image.suffix.lower(),'application/octet-stream'))
                return self.send(404,{'error':'Not found.'})
            except (ValueError,OSError):return self.send(404,{'error':'Photo or group not found.'})
        def do_POST(self):
            if not self.allowed() or self.headers.get('X-Local-Token')!=token:return self.send(403,{'error':'Invalid local request token.'})
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://127.0.0.1:{self.server.server_port}':return self.send(403,{'error':'Invalid origin.'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<16384:raise ValueError('Invalid request size.')
                data=json.loads(self.rfile.read(length))
                if self.path=='/api/name':manager.rename(int(data['id']),data.get('name',''))
                elif self.path=='/api/merge':manager.merge(data['ids'],int(data['target']),data.get('name',''))
                elif self.path=='/api/undo':manager.undo()
                else:return self.send(404,{'error':'Not found.'})
                return self.send(200,{'ok':True})
            except ValueError as exc:return self.send(400,{'error':str(exc)})
            except (KeyError,TypeError):return self.send(400,{'error':'Invalid request. Check the selected groups and try again.'})
            except Exception:return self.send(500,{'error':'Could not save this change. Backups were preserved; check available disk space.'})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',help='Grouping result directory containing .pessoas.sqlite3.')
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args();os.umask(0o077)
    manager=Manager(args.directory);server=serve(manager,args.port)
    address=f'http://127.0.0.1:{server.server_port}'
    (manager.root/'MANAGE.html').write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Manage face groups</title><h1>Manage face groups</h1><p>Keep the local manager running, then <a href="{address}">open the editing interface</a>.</p><p>If this link has expired, restart Manage face groups.command.</p>')
    print('Local face group manager:',address,flush=True)
    print('Names and changes stay on this Mac. Keep this window open. Control+C stops the manager.',flush=True)
    if not args.no_open:webbrowser.open(address)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();manager.lock.close()

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as exc:raise SystemExit(str(exc))
