import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from app import write_key, probe_lighting, read_via

class Keyboard:
    version=12
    def __init__(self,code=4): self.code=code;self.commands=[]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def layer_count(self): return 4
    def exchange(self,command,data=b'',prefix=None):
        self.commands.append(command)
        if command==5: self.code=int.from_bytes(data[-2:],'big')
        response=bytearray(32);response[0]=command;response[1:4]=data[:3]
        response[4:6]=self.code.to_bytes(2,'big')
        return bytes(response)

class KeyOperationTests(unittest.TestCase):
    def test_protocol_9_reads_layout_from_buffer_without_command_4(self):
        device=Keyboard();device.version=9
        memory=b''.join(code.to_bytes(2,'big') for code in range(128))
        def exchange(command,data=b'',prefix=None):
            device.commands.append(command)
            if command==8: raise NotImplementedError('unsupported lighting')
            self.assertEqual(command,0x12)
            offset=int.from_bytes(data[:2],'big');size=data[2]
            return bytes([command])+data+memory[offset:offset+size]+bytes(28-size)
        device.exchange=exchange
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'ROOT',Path(folder)),patch.object(app,'ViaDevice',lambda:device):
            result=read_via(0,lambda value:None)
            self.assertEqual(result['status'],'via_confirmed')
            self.assertEqual(len(result['keys']),len(app.KEY_LAYOUT))
            for key in app.KEY_LAYOUT:
                self.assertEqual(result['keys'][f'{key.row},{key.col}'],key.row*16+key.col)
            self.assertNotIn(4,device.commands)

    def test_lighting_probe_does_not_depend_on_keymap_or_layer_count(self):
        device=Keyboard()
        def exchange(command,data=b'',prefix=None):
            if command!=8: raise AssertionError('The lighting query must not read layers or keys.')
            raise NotImplementedError('unsupported lighting')
        device.exchange=exchange
        def layer_count(): raise AssertionError('The lighting query must not read layers.')
        device.layer_count=layer_count
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'ROOT',Path(folder)),patch.object(app,'ViaDevice',lambda:device),patch.object(app,'read_native_lighting',lambda:None):
            result=probe_lighting()
            self.assertEqual(result['status'],'lighting_unavailable')
            self.assertIsNone(result['lighting'])

    def test_changed_key_is_not_overwritten_by_stale_ui(self):
        device=Keyboard(6)
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'ROOT',Path(folder)),patch.object(app,'ViaDevice',lambda:device):
            result=write_key(0,0,0,4,5)
            self.assertEqual(result['status'],'error')
            self.assertEqual(device.commands,[0x12])
            self.assertEqual(device.code,6)

    def test_single_key_write_saves_old_value_for_undo(self):
        device=Keyboard(4)
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'ROOT',Path(folder)),patch.object(app,'ViaDevice',lambda:device):
            result=write_key(0,0,0,4,5)
            self.assertEqual(result['status'],'key_acknowledged')
            self.assertEqual(device.commands,[0x12,5,0x12])
            self.assertTrue((Path(folder)/'last-key.json').exists())
            self.assertEqual(result['old'],4);self.assertEqual(result['new'],5)
