"""Naming, merging, and undo tests with artificial files only."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manage_face_groups import Manager

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        with sqlite3.connect(self.root/'.pessoas.sqlite3') as db:
            db.executescript('CREATE TABLE config(value TEXT); CREATE TABLE people(id INTEGER PRIMARY KEY,vector TEXT,count INTEGER,quality REAL,preview TEXT,review INTEGER); CREATE TABLE photos(path TEXT PRIMARY KEY,size INTEGER,modified INTEGER,status TEXT); CREATE TABLE appearances(person INTEGER,path TEXT,copy TEXT,PRIMARY KEY(person,path));')
            db.execute('INSERT INTO config VALUES (?)',('{}',))
            for pid in [1,2]:
                folder=self.root/f'Pessoa_{pid:04d}';(folder/'fotos').mkdir(parents=True)
                (folder/'PRINCIPAL.jpg').write_bytes(b'artificial preview')
                db.execute('INSERT INTO people VALUES (?,?,?,?,?,?)',(pid,json.dumps([1.,0.] if pid==1 else [0.9,0.1]),2,pid,'common.jpg',0))
                for name in ['common.jpg',f'unique{pid}.jpg']:
                    target=folder/'fotos'/name;target.write_bytes(name.encode())
                    db.execute('INSERT INTO appearances VALUES (?,?,?)',(pid,name,str(target.relative_to(self.root))))
        self.manager=Manager(self.root)
    def tearDown(self):
        self.manager.lock.close();self.temp.cleanup()
    def test_name_merge_deduplicate_and_undo(self):
        self.manager.rename(1,'Example Person')
        self.manager.merge([1,2],1,'Example Person')
        groups=self.manager.groups()['groups'];self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['count'],3);self.assertEqual(groups[0]['name'],'Example Person')
        self.assertFalse((self.root/'Pessoa_0002').exists())
        self.assertEqual(len(list((self.root/self.manager.folder(1)/'fotos').iterdir())),3)
        self.assertIn('Example Person',(self.root/'PESSOAS.html').read_text())
        self.manager.undo();self.assertEqual(len(self.manager.groups()['groups']),2)
        self.assertTrue((self.root/'Pessoa_0002'/'fotos'/'unique2.jpg').exists())
        self.manager.undo();self.assertTrue(all(not g['name'] for g in self.manager.groups()['groups']))
    def test_folder_rename_paths_and_duplicate_names(self):
        self.manager.rename(1,'Example Person')
        self.manager.rename(2,'Example Person')
        a=self.manager.folder(1);b=self.manager.folder(2)
        self.assertNotEqual(a,b)
        self.assertEqual(a,'Example Person - Pessoa_0001')
        self.assertTrue((self.root/a/'PRINCIPAL.jpg').is_file())
        self.assertTrue(self.manager.photo(1,0).is_file())
        with self.manager.db() as db:
            from separar_pessoas import group_folder
            self.assertEqual(group_folder(db,1),a)
        self.manager.rename(1,'')
        self.assertEqual(self.manager.folder(1),'Pessoa_0001')
        self.assertTrue(self.manager.photo(1,0).is_file())
        self.manager.undo()
        self.assertTrue((self.root/a).is_dir())

    def test_folder_names_are_safe(self):
        self.manager.rename(1,'../Example / Person:*?')
        name=self.manager.folder(1)
        self.assertNotIn('/',name)
        self.assertFalse(name.startswith('.'))
        self.assertTrue((self.root/name).is_dir())

    def test_legacy_undo_then_rename(self):
        with self.manager.db() as db:db.execute('DROP TABLE person_folders')
        folder=self.manager.history/'legacy';folder.mkdir()
        with self.manager.db() as source,sqlite3.connect(folder/'before.sqlite3') as backup:source.backup(backup)
        with self.manager.db() as db:db.execute('INSERT INTO person_names VALUES (?,?)',(1,'Legacy name'))
        action={'kind':'rename','person':1,'committed':True,'undone':False,'after':self.manager.digest(include_folders=False)}
        (folder/'action.json').write_text(json.dumps(action))
        self.manager.undo()
        self.manager.rename(1,'New name')
        self.assertTrue((self.root/'New name - Pessoa_0001').is_dir())

    def test_invalid_merge_does_not_change_data(self):
        before=self.manager.digest()
        with self.assertRaises(ValueError):self.manager.merge([1,99],1,'Example')
        self.assertEqual(before,self.manager.digest())
    def test_undo_rejects_external_changes(self):
        self.manager.rename(1,'Example')
        with self.manager.db() as db:db.execute('UPDATE people SET count=8 WHERE id=1')
        with self.assertRaises(ValueError):self.manager.undo()

if __name__=='__main__':unittest.main()
