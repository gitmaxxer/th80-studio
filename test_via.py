import json
import unittest
import tempfile
from unittest.mock import patch
import via
from pathlib import Path
from via import request, choose_interface, get_keycode, set_keycode, read_lighting, write_lighting, ViaDevice, read_keymap
from keyboard_layout import parse_layout

class ViaTests(unittest.TestCase):
    def test_buffered_single_key_uses_exact_offset_and_verifies_write(self):
        code=4;calls=[]
        def exchange(command,data=b'',prefix=None):
            nonlocal code
            calls.append((command,data))
            if command==5:
                code=int.from_bytes(data[-2:],'big')
                return bytes([5])+data
            self.assertEqual((command,data),(0x12,bytes.fromhex('03 46 02')))
            return bytes([0x12])+data+code.to_bytes(2,'big')+bytes(26)
        self.assertEqual(get_keycode(exchange,3,2,3,buffered=True),4)
        set_keycode(exchange,3,2,3,5,buffered=True)
        self.assertEqual([command for command,data in calls],[0x12,5,0x12])

    def test_buffer_read_uses_layer_offsets_and_big_endian_keycodes(self):
        memory=b''.join(code.to_bytes(2,'big') for code in range(512));calls=[]
        def exchange(command,data=b'',prefix=None):
            self.assertEqual(command,0x12)
            offset=int.from_bytes(data[:2],'big');size=data[2]
            self.assertLessEqual(size,28);calls.append((offset,size))
            return bytes([command])+data+memory[offset:offset+size]+bytes(28-size)
        keys=read_keymap(exchange,2,8,16)
        self.assertEqual(keys,list(range(256,384)))
        self.assertEqual(calls[0],(512,28));self.assertEqual(calls[-1],(764,4))
        self.assertEqual(len(calls),10)

    def test_buffer_read_rejects_invalid_layers_without_sending(self):
        with self.assertRaises(ValueError): read_keymap(lambda *args:self.fail('unexpected USB command'),8,8,16)

    def test_trace_archive_preserves_each_session(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(via,'__file__',str(Path(folder)/'via.py')):
            device=ViaDevice();device.trace=[{'command':4}];device.save_trace()
            device.trace=[{'command':8}];device.save_trace()
            traces=[json.loads(file.read_text()) for file in (Path(folder)/'logs-via').glob('*.json')]
            self.assertEqual(len(traces),2)
            self.assertIn([{'command':4}],traces)
            self.assertIn([{'command':8}],traces)
            self.assertEqual(json.loads((Path(folder)/'diagnostic-via.json').read_text()),[{'command':8}])

    def test_legacy_lighting_reads_real_values_and_ignores_channel_echoes(self):
        def exchange(command,data=b'',prefix=None):
            result=bytearray(bytes([command])+data+bytes(31-len(data)))
            if len(data)==3 and data[0]==9: result[2]=120
            if len(data)==3 and data[0]==12: result[2:4]=bytes([80,200])
            return bytes(result)
        self.assertEqual(read_lighting(exchange),{'channel':'legacy','brightness':120,'hue':80,'saturation':200})

    def test_legacy_write_uses_legacy_ids_and_confirms_readback(self):
        values={9:bytes([120]),12:bytes([80,200])};calls=[]
        def exchange(command,data=b'',prefix=None):
            calls.append((command,data))
            if command==7: values[data[0]]=data[1:]
            result=bytearray(bytes([command])+data+bytes(31-len(data)))
            if command==8: result[2:2+len(values[data[0]])]=values[data[0]]
            return bytes(result)
        write_lighting(exchange,'legacy',180,100,220)
        self.assertIn((7,bytes([9,180])),calls)
        self.assertIn((7,bytes([12,100,220])),calls)
        self.assertIn((9,b''),calls)
        self.assertEqual(values,{9:bytes([180]),12:bytes([100,220])})

    def test_legacy_echo_never_enables_writes(self):
        calls=[]
        def exchange(command,data=b'',prefix=None):
            calls.append(command)
            return bytes([command])+data+bytes(31-len(data))
        with self.assertRaises(NotImplementedError): write_lighting(exchange,'legacy',100,80,200)
        self.assertEqual(set(calls),{8})

    def test_via_accepts_matching_response_padded_to_64_bytes(self):
        class Handle:
            def write(self,data): return len(data)
            def read(self,size,timeout): return bytes.fromhex('01 00 09')+bytes(61)
        device=ViaDevice();device.handle=Handle()
        self.assertEqual(device.exchange(1)[:3],bytes.fromhex('01 00 09'))

    def test_via_accepts_zero_report_id_and_64_byte_payload(self):
        class Handle:
            def write(self,data): return len(data)
            def read(self,size,timeout): return bytes.fromhex('00 01 00 09')+bytes(61)
        device=ViaDevice();device.handle=Handle()
        self.assertEqual(device.exchange(1)[:3],bytes.fromhex('01 00 09'))

    def test_raw_hid_report_is_zero_prefixed_and_keycode_big_endian(self):
        self.assertEqual(request(5,bytes.fromhex('01 02 03 00 04'))[:7],bytes.fromhex('00 05 01 02 03 00 04'))
        self.assertEqual(len(request(1)),33)
        with self.assertRaises(ValueError): request(0x0b)

    def test_via_interface_is_exclusive(self):
        target={'vendor_id':0x320f,'product_id':0x5055,'product_string':'EPOMAKER TH80 Pro V2','usage_page':0xff60,'usage':0x61}
        screen={**target,'usage_page':0xff1c,'usage':0x92}
        self.assertEqual(choose_interface([screen,target]),target)
        with self.assertRaises(ValueError): choose_interface([{**target,'product_string':'GMK87'}])

    def test_read_and_write_use_correct_matrix_and_verify_readback(self):
        calls=[]
        def exchange(command,data=b'',prefix=None):
            calls.append((command,data))
            return bytes.fromhex('04 01 02 03 00 05') if command==4 else bytes.fromhex('05 01 02 03 00 05')
        self.assertEqual(get_keycode(exchange,1,2,3),5)
        set_keycode(exchange,1,2,3,5)
        self.assertEqual(calls,[ (4,bytes([1,2,3])),(5,bytes([1,2,3,0,5])),(4,bytes([1,2,3])) ])

    def test_mismatched_readback_is_failure(self):
        def exchange(command,data=b'',prefix=None): return bytes([command,0,0,0,0,4])
        with self.assertRaises(OSError): set_keycode(exchange,0,0,0,5)

    def test_unsupported_lighting_only_sends_queries(self):
        calls=[]
        def exchange(command,data=b'',prefix=None):
            calls.append(command);raise NotImplementedError('unsupported')
        self.assertIsNone(read_lighting(exchange))
        self.assertTrue(calls);self.assertEqual(set(calls),{8})

    def test_unchanged_echo_is_not_lighting_support(self):
        def exchange(command,data=b'',prefix=None): return bytes([command])+data+bytes(31-len(data))
        self.assertIsNone(read_lighting(exchange))

    def test_color_readback_must_confirm_written_color(self):
        def exchange(command,data=b'',prefix=None):
            result=bytearray(32);result[0]=command;result[1:1+len(data)]=data
            if command==8:
                result[3]=100 if data[1]==1 else 0
                result[4]=0
            return bytes(result)
        with self.assertRaises(OSError): write_lighting(exchange,3,100,120,200)

    def test_json_layout_keeps_wide_key_and_matrix_coordinates(self):
        layout=parse_layout([[{'x':0.5,'w':2},'1,2','1,3'],[{'y':0.25},'2,0']],8,16)
        self.assertEqual((layout[0].x,layout[0].width,layout[0].row,layout[0].col),(0.5,2,1,2))
        self.assertEqual((layout[1].x,layout[1].width),(2.5,1))
        self.assertEqual(layout[2].y,1.25)
        with self.assertRaises(ValueError): parse_layout([['8,0']],8,16)

    def test_real_definition_has_unique_matrix_keys(self):
        definition=json.loads((Path(__file__).parent/'via-definition.json').read_text(encoding='utf-8-sig'))
        keys=parse_layout(definition['layouts']['keymap'],8,16)
        self.assertGreater(len(keys),70)
        self.assertEqual(len(keys),len({(k.row,k.col) for k in keys}))
