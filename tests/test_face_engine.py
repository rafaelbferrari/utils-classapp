import tempfile
import unittest
from pathlib import Path
import numpy as np
from face_engine import constrained_groups, copy_photo


class GlobalGroupingTests(unittest.TestCase):
    def test_same_photo_cannot_merge_even_through_another_photo(self):
        vectors=np.array([[1.,0.],[.999,.01],[.998,.02]],dtype=np.float32)
        groups=constrained_groups(vectors,['a','b','a'],[3,2,1])
        self.assertEqual(sorted(map(len,groups)),[1,2])
        for group in groups:
            paths=[['a','b','a'][i] for i in group]
            self.assertEqual(len(paths),len(set(paths)))

    def test_distinct_names_and_transitive_lookalikes_stay_separate(self):
        angles=np.deg2rad([0,40,80])
        vectors=np.column_stack((np.cos(angles),np.sin(angles))).astype(np.float32)
        groups=constrained_groups(vectors,['a','b','c'],[3,2,1],threshold=.7,floor=.3)
        self.assertEqual(sorted(map(len,groups)),[1,2])
        groups=constrained_groups(np.array([[1.,0.],[1.,0.]],dtype=np.float32),['a','b'],[1,1],['one','two'])
        self.assertEqual(len(groups),2)

    def test_global_matching_and_empty_input(self):
        vectors=np.array([[1.,0.],[0.,1.],[.99,.01]],dtype=np.float32)
        self.assertEqual(constrained_groups(vectors,['a','b','c'],[1,1,1]),[[0,2],[1]])
        self.assertEqual(constrained_groups([],[],[]),[])

    def test_copy_is_independent_of_original(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'original';target=Path(temp)/'copy'
            source.write_bytes(b'original')
            copy_photo(source,target)
            target.write_bytes(b'edited')
            self.assertEqual(source.read_bytes(),b'original')


if __name__=='__main__':unittest.main()
