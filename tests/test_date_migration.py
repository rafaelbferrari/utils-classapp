"""Date migration uses artificial photos and temporary directories only."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ajustar_datas_pastas as app

class MigrationTests(unittest.TestCase):
    def test_move_duplicates_conflicts_and_dates(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/'fotos';dst=root/'fotos_v2'
            day=src/'2025-03-15';day.mkdir(parents=True);(dst/day.name).mkdir(parents=True)
            records={}
            for name,color in [('move','blue'),('duplicate','red'),('conflict','green')]:
                p=day/(name+'.jpg');Image.new('RGB',(40,40),color).save(p)
                records[name]={'file':str(p.relative_to(src)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'created':'2025-03-15T10:00:00Z'}
            (dst/day.name/'duplicate.jpg').write_bytes((day/'duplicate.jpg').read_bytes())
            Image.new('RGB',(40,40),'yellow').save(dst/day.name/'conflict.jpg')
            original_conflict=(dst/day.name/'conflict.jpg').read_bytes()
            app.save_index(src,{'photos':records})
            inode=(day/'move.jpg').stat().st_ino
            def lock(destination):return (destination/'.test-lock').open('a')
            with patch.object(app,'migration_lock',side_effect=lock),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                result=app.migrate(src,dst)
            self.assertEqual(result,1)
            self.assertFalse((day/'move.jpg').exists());self.assertFalse((day/'duplicate.jpg').exists())
            self.assertTrue((day/'conflict.jpg').exists())
            self.assertEqual((dst/day.name/'move.jpg').stat().st_ino,inode)
            self.assertEqual((dst/day.name/'conflict.jpg').read_bytes(),original_conflict)
            self.assertFalse(list(root.rglob('*_original')))
            self.assertEqual(set(app.read_index(src)['photos']),{'conflict'})
            target=app.read_index(dst)['photos'];self.assertEqual(set(target),{'move','duplicate'})
            for info in target.values():
                self.assertEqual(hashlib.sha256((dst/info['file']).read_bytes()).hexdigest(),info['sha256'])
                self.assertEqual(info['metadata_version'],2)
            tags=json.loads(subprocess.check_output([app.date_tool(),'-j','-DateTimeOriginal',str(dst/day.name/'move.jpg')]))[0]
            self.assertEqual(tags['DateTimeOriginal'],'2025:03:15 12:00:00')

    def test_dry_run_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'fotos';day=src/'2025-03-15';day.mkdir(parents=True);dst=Path(td)/'fotos_v2'
            photo=day/'example.jpg';Image.new('RGB',(10,10),'blue').save(photo);before=photo.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(app.migrate(src,dst,True),0)
            self.assertFalse(dst.exists());self.assertEqual(photo.read_bytes(),before)

if __name__=='__main__':unittest.main()
