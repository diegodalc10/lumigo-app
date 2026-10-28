import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from storage import validate_storage

class StorageTests(unittest.TestCase):
 def test_required_mount_existing_database_and_path(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); db=root/'lumigo.sqlite3'
   with patch.dict(os.environ,{'LUMIGO_REQUIRE_PERSISTENT':'1','LUMIGO_DATA_DIR':directory,'LUMIGO_ALLOW_EMPTY_DB':'0'}):
    with patch('storage.os.path.ismount',return_value=False):
     with self.assertRaises(RuntimeError): validate_storage(db)
    with patch('storage.os.path.ismount',return_value=True):
     with self.assertRaises(RuntimeError): validate_storage(db)
     db.touch(); validate_storage(db)
     with self.assertRaises(RuntimeError): validate_storage(root.parent/'outside.sqlite3')
