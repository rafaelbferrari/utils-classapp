"""Testa concorrência e retomada somente com rede simulada e fotos artificiais."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import baixar_momentos_v3 as app

class ParallelTests(unittest.TestCase):
    def setUp(self):
        app._STOP.clear()

    def test_timer_recovers_same_operation(self):
        action=iter([app.RetryableDownloadError('rede'),app.RetryableDownloadError('rede'),('foto','indice')])
        def operation():
            result=next(action)
            if isinstance(result,Exception):raise result
            return result
        with patch.object(app,'wait_to_restart') as waiting,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.automatic_restart(operation,60,0),('foto','indice'))
            self.assertEqual(waiting.call_count,2)

    def test_timer_does_not_retry_auth_or_disk(self):
        for error in [app.DownloadError('sessão expirada'),PermissionError('disco')]:
            with patch.object(app,'wait_to_restart') as waiting:
                with self.assertRaises(type(error)):
                    app.automatic_restart(lambda: (_ for _ in ()).throw(error))
                waiting.assert_not_called()

    def test_timer_can_be_cancelled(self):
        with patch.object(app._STOP,'wait',return_value=True),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(app.DownloadError):app.wait_to_restart(60,'Teste')

    def test_concurrency_is_bounded(self):
        lock=threading.Lock();active=0;peak=0;results=[]
        def worker(i):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            time.sleep(.02)
            with lock:active-=1
            return i
        app.process_parallel(range(16),worker,results.append,4)
        self.assertEqual(set(results),set(range(16)))
        self.assertEqual(peak,4)

    def test_successes_collected_when_one_worker_fails(self):
        barrier=threading.Barrier(3);results=[]
        def worker(i):
            barrier.wait(timeout=3)
            if i==0:raise app.DownloadError('erro simulado')
            time.sleep(.02)
            return i
        with self.assertRaises(app.DownloadError):
            app.process_parallel(range(3),worker,results.append,3)
        self.assertEqual(set(results),{1,2})

    def test_download_metadata_limit_and_resume(self):
        buf=io.BytesIO();Image.new('RGB',(48,48),'blue').save(buf,format='JPEG');image=buf.getvalue()
        data={'data':{'node':{'moments':{'nodes':[{'id':'post','created':'2026-02-01T15:00:00Z','medias':{'nodes':[{'id':str(i),'mimetype':'image/jpeg','uri':f'https://images.classapp.com.br/{i}.jpg'} for i in range(5)]}}],'pageInfo':{'hasNextPage':False}}}}}
        def fake_request(url,headers=None,payload=None):
            self.assertNotIn('authorization',headers)
            self.assertNotIn('cookie',headers)
            return image,'image/jpeg'
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'saida'
            argv=['v3','--pagina-capturada','--destino',str(dest),'--max-fotos','3']
            with patch.object(app,'read_har',return_value=('',{'variables':{}},data)),patch.object(app,'request',side_effect=fake_request),patch.object(app,'guard_other_downloaders',return_value=None),patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
                app.main()
                first=json.loads((dest/'indice.json').read_text());self.assertEqual(len(first['photos']),3)
                before={i:(dest/x['file']).stat().st_mtime_ns for i,x in first['photos'].items()}
                # Cada execução limita novas fotos, não fotos já salvas.
                app.main()
                final=json.loads((dest/'indice.json').read_text());self.assertEqual(len(final['photos']),5)
                for i,mtime in before.items():self.assertEqual((dest/final['photos'][i]['file']).stat().st_mtime_ns,mtime)
                self.assertTrue(all(x['metadata_version']==2 for x in final['photos'].values()))

if __name__=='__main__':unittest.main()
