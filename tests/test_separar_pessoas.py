"""Tests use only artificial images created in temporary directories."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import separar_pessoas as app
import cv2
import numpy as np
from PIL import Image

class GroupTests(unittest.TestCase):
    def test_finder_paths_and_invisible_trailing_space(self):
        import shlex
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'Sample photos';source.mkdir()
            self.assertEqual(app.normalize_directory(str(source)+'\u00a0'),source.resolve())
            self.assertEqual(app.normalize_directory(str(source)+' \u200b '),source.resolve())
            self.assertEqual(app.normalize_directory(str(source).replace(' ',r'\ ')),source.resolve())
            self.assertEqual(app.normalize_directory(shlex.quote(str(source))),source.resolve())
            actual=Path(td)/'Actual trailing space ';actual.mkdir()
            self.assertEqual(app.normalize_directory(str(actual)),actual.resolve())

    def test_missing_source_has_specific_message(self):
        with tempfile.TemporaryDirectory() as td:
            missing=str(Path(td)/'missing')
            stderr=io.StringIO()
            with patch.object(sys,'argv',['group',missing]),patch.object(app,'check_models') as models,contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as exc:app.main()
            self.assertEqual(exc.exception.code,2)
            self.assertIn('Source directory not found',stderr.getvalue())
            models.assert_not_called()

    def test_similarity_margin_and_same_photo(self):
        a=np.array([1.,0.,0.],dtype=np.float32)
        people={1:{'vector':a},2:{'vector':np.array([0.,1.,0.],dtype=np.float32)}}
        self.assertEqual(app.choose_person(a,people,set(),.48,.05,np),(1,False))
        self.assertEqual(app.choose_person(a,people,{1},.48,.05,np),(None,False))
        v=np.array([1.,1.,0.],dtype=np.float32);v/=np.linalg.norm(v)
        self.assertEqual(app.choose_person(v,people,set(),.48,.05,np),(None,True))

    def test_copies_previews_gallery_and_resume(self):
        class Detector:
            def setInputSize(self,size):pass
            def detect(self,image):
                def face(x):return np.array([x,10,40,40, 10,15,30,15,20,25,15,35,25,35,.99],dtype=np.float32)
                return None, np.array([face(0)] if image.shape[1]==80 else [face(40)] if image.shape[1]==81 else [face(0),face(40)])
        class Recognizer:
            def alignCrop(self,image,face):return np.full((112,112,3),10 if face[0]==0 else 20,dtype=np.uint8)
            def feature(self,aligned):return np.array([[1.,0.,0.]] if aligned[0,0,0]==10 else [[0.,1.,0.]],dtype=np.float32)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'artificiais';source.mkdir();dest=root/'resultado'
            for i,w in enumerate([80,81,82]):Image.new('RGB',(w,80),(100,70,20)).save(source/f'{i}.png')
            before={p.name:p.read_bytes() for p in source.iterdir()}
            argv=['separar_pessoas.py',str(source),'--destino',str(dest)]
            with patch.object(cv2,'FaceDetectorYN',SimpleNamespace(create=lambda *a:Detector())),patch.object(cv2,'FaceRecognizerSF',SimpleNamespace(create=lambda *a:Recognizer())),patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(app.main(),0)
                self.assertEqual(app.main(),0)
            for pid in [1,2]:
                folder=dest/f'Pessoa_{pid:04d}'
                self.assertTrue((folder/'PRINCIPAL.jpg').is_file())
                self.assertEqual(len(list((folder/'fotos').glob('*.png'))),2)
            self.assertTrue((dest/'PESSOAS.html').is_file())
            with sqlite3.connect(dest/'.pessoas.sqlite3') as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM photos').fetchone()[0],3)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM appearances').fetchone()[0],4)
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})

    def test_real_models_on_artificial_blank(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'artificiais';source.mkdir();dest=root/'saida'
            Image.new('RGB',(160,160),'gray').save(source/'sem_rosto.jpg')
            with patch.object(sys,'argv',['separar_pessoas.py',str(source),'--destino',str(dest)]),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(app.main(),0)
            self.assertEqual((source/'sem_rosto.jpg').read_bytes(),(dest/'Sem_rosto_detectado'/'sem_rosto.jpg').read_bytes())

if __name__=='__main__':unittest.main()
