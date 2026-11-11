import json
import tempfile
import unittest
from pathlib import Path
from lighting_catalog import load_catalog, observe_configuration, import_captures


class CatalogTests(unittest.TestCase):
    def test_new_state_persists_exact_color_block_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);config=bytearray(48)
            config[1:4]=bytes([7,9,6]);config[5:10]=bytes.fromhex('00 00 00 ff 17')
            catalog,name=observe_configuration(root,bytes(config))
            self.assertIn(7,catalog['effects']);self.assertIn(6,catalog['speeds'])
            self.assertEqual(catalog['colors'][name],config[5:10].hex())
            self.assertIn('#0000FF',name)
            catalog2,name2=observe_configuration(root,bytes(config))
            self.assertEqual(name,name2);self.assertEqual(catalog,catalog2)
            self.assertEqual(load_catalog(root),catalog)

    def test_capture_import_accepts_successful_reads_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'logs-lighting';archive.mkdir()
            config=bytearray(48);config[1:4]=bytes([8,9,7])
            (archive/'good.json').write_text(json.dumps({'status':'snapshot_saved','configuration':config.hex()}))
            config[1]=250
            (archive/'failed.json').write_text(json.dumps({'status':'error','configuration':config.hex()}))
            (archive/'broken.json').write_text('{')
            catalog=import_captures(root)
            self.assertIn(8,catalog['effects']);self.assertNotIn(250,catalog['effects'])

    def test_invalid_configuration_is_never_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(ValueError): observe_configuration(root,bytes(47))
            config=bytearray(48);config[2]=255
            with self.assertRaises(ValueError): observe_configuration(root,bytes(config))
            self.assertFalse((root/'lighting-catalog.json').exists())

    def test_catalog_device_identity_and_bounds_are_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'lighting-catalog.json'
            catalog=load_catalog(root);catalog['effects']=[256]
            path.write_text(json.dumps(catalog))
            with self.assertRaises(ValueError): load_catalog(root)
            catalog['effects']=[1];catalog['device']='another-keyboard'
            path.write_text(json.dumps(catalog))
            with self.assertRaises(ValueError): load_catalog(root)

    def test_defaults_keep_visually_confirmed_color_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);config=bytearray(48);config[2]=9;config[5:10]=bytes.fromhex('00 35 ff 00 0c')
            _,name=observe_configuration(root,bytes(config))
            self.assertEqual(name,'Green')
