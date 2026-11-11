"""Exercise app operations with only the physical USB boundary replaced."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app

class SimulatedKeyboard:
    def __init__(self):
        self.config=bytes(range(48));self.commands=[];self.closed=False
    def __enter__(self): return self
    def __exit__(self,*args): self.closed=True
    def read_config(self): return self.config
    def exchange(self,command,data=b'',position=0):
        self.commands.append(command)
        if command==6: self.config=data
        return bytes(4)

class OperationTests(unittest.TestCase):
    def test_custom_hex_preserves_auxiliary_color_and_other_settings(self):
        device=SimulatedKeyboard();before=device.config
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            result=app.apply_native_brightness(2,custom_color='#0066ff')
            self.assertEqual(result['status'],'lighting_acknowledged')
            self.assertEqual(result['custom_color'],'#0066FF')
            self.assertEqual(device.config[5:9],bytes.fromhex('00 00 66 ff'))
            self.assertEqual(device.config[:5]+device.config[9:],before[:5]+before[9:])

    def test_invalid_or_conflicting_hex_never_opens_usb(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device') as device:
            for color,preset in [('ZZFFFF',None),('#0066FF','Green')]:
                self.assertEqual(app.apply_native_brightness(2,color_preset=preset,custom_color=color)['status'],'error')
            device.assert_not_called()

    def test_learned_effect_and_speed_can_be_applied_without_guessing_ids(self):
        device=SimulatedKeyboard();state=bytearray(device.config);state[1]=7;state[3]=6;device.config=bytes(state)
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            learned=app.learn_native_lighting()
            self.assertEqual(learned['status'],'catalog_saved');self.assertEqual(device.commands,[])
            state[1]=1;state[3]=2;device.config=bytes(state)
            result=app.apply_native_brightness(2,effect=7,speed=6)
            self.assertEqual(result['status'],'lighting_acknowledged')
            self.assertEqual((device.config[1],device.config[3]),(7,6))

    def test_custom_color_requires_readback_and_preserved_auxiliary_byte(self):
        device=SimulatedKeyboard()
        def exchange(command,data=b'',position=0):
            if command==6:
                changed=bytearray(data);changed[9]=255;device.config=bytes(changed)
            return bytes(4)
        device.exchange=exchange
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            self.assertEqual(app.apply_native_brightness(2,custom_color='#0066FF')['status'],'error')

    def test_native_color_replays_captured_block_and_preserves_everything_else(self):
        device=SimulatedKeyboard();before=device.config
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            result=app.apply_native_brightness(9,color_preset='Green')
            self.assertEqual(result['status'],'lighting_acknowledged')
            self.assertEqual(device.config[5:10],bytes.fromhex('00 35 ff 00 0c'))
            self.assertEqual(device.config[:2]+device.config[3:5]+device.config[10:],before[:2]+before[3:5]+before[10:])
            self.assertEqual(result['color_preset'],'Green')

    def test_native_rainbow_uses_captured_configuration(self):
        device=SimulatedKeyboard()
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            result=app.apply_native_brightness(9,color_preset='Rainbow')
            self.assertEqual(result['status'],'lighting_acknowledged')
            self.assertEqual(device.config[5:10],bytes.fromhex('ff ff 01 00 00'))

    def test_native_unknown_color_does_not_write(self):
        device=SimulatedKeyboard()
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            self.assertEqual(app.apply_native_brightness(9,color_preset='unknown')['status'],'error')
            self.assertEqual(device.commands,[])

    def test_guided_capture_starts_fresh_and_uses_explicit_baseline(self):
        device=SimulatedKeyboard()
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            app.capture_lighting()
            config=bytearray(device.config);config[8]=80;device.config=bytes(config)
            first=app.capture_lighting(fresh=True)
            self.assertEqual(first['status'],'snapshot_saved')
            config[8]=100;device.config=bytes(config)
            second=app.capture_lighting(baseline=first)
            self.assertEqual(second['candidate_changes'],[{'offset':8,'before':80,'after':100}])
            self.assertEqual(second['previous_timestamp'],first['timestamp'])

    def test_native_effect_and_speed_only_change_selected_fields(self):
        device=SimulatedKeyboard();before=device.config
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            result=app.apply_native_brightness(9,effect=16,speed=4)
            self.assertEqual(result['status'],'lighting_acknowledged')
            self.assertEqual(device.config[1:4],bytes([16,9,4]))
            self.assertEqual(device.config[:1]+device.config[4:],before[:1]+before[4:])

    def test_unobserved_effect_and_speed_do_not_send_commands(self):
        device=SimulatedKeyboard()
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            self.assertEqual(app.apply_native_brightness(5,effect=255)['status'],'error')
            self.assertEqual(app.apply_native_brightness(5,speed=255)['status'],'error')
            self.assertEqual(device.commands,[])
    def test_native_brightness_preserves_every_other_field_and_saves_backup(self):
        device=SimulatedKeyboard();before=device.config
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            result=app.apply_native_brightness(9)
            self.assertEqual(result['status'],'lighting_acknowledged')
            self.assertEqual(device.commands,[1,6,2])
            self.assertEqual(device.config[:2],before[:2])
            self.assertEqual(device.config[2],9)
            self.assertEqual(device.config[3:],before[3:])
            backups=list(Path(folder).glob('light-before-*.json'))
            self.assertEqual(len(backups),1)
            self.assertEqual(json.loads(backups[0].read_text())['configuration_before'],before.hex())

    def test_native_brightness_rejects_unobserved_values_before_usb(self):
        device=SimulatedKeyboard()
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            for brightness in (-1,10,255,2.5):
                self.assertEqual(app.apply_native_brightness(brightness)['status'],'error')
            self.assertEqual(device.commands,[])

    def test_native_brightness_reads_ninth_level(self):
        device=SimulatedKeyboard();config=bytearray(device.config);config[2]=9;device.config=bytes(config)
        with patch.object(app,'Device',lambda:device):
            self.assertEqual(app.read_native_lighting(),{'channel':'native','brightness':9,'max_brightness':9,'effect':1,'speed':3})

    def test_native_brightness_requires_actual_readback(self):
        device=SimulatedKeyboard()
        device.exchange=lambda *args:bytes(4)
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            result=app.apply_native_brightness(3)
            self.assertEqual(result['status'],'error')
            self.assertIn('confirmed',result['message'])

    def test_lighting_capture_only_reads_and_compares_non_clock_fields(self):
        device=SimulatedKeyboard()
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            first=app.capture_lighting()
            self.assertEqual(first['status'],'snapshot_saved')
            changed=bytearray(device.config);changed[2]=90;changed[35]=20
            device.config=bytes(changed)
            second=app.capture_lighting()
            self.assertEqual(second['status'],'comparison_saved')
            self.assertEqual(second['candidate_changes'],[{'offset':2,'before':2,'after':90}])
            self.assertEqual(second['clock_changes'],[{'offset':35,'before':35,'after':20}])
            self.assertEqual(device.commands,[])
            self.assertEqual(len(list((Path(folder)/'logs-lighting').glob('*.json'))),2)

    def test_clock_preserves_frame_counts_and_saves_backup_before_writing(self):
        device=SimulatedKeyboard()
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            result=app.set_screen('clock')
            self.assertEqual(result['status'],'configuration_acknowledged')
            self.assertEqual(device.commands,[1,6,2])
            self.assertEqual((device.config[34],device.config[46]),(34,46))
            backups=list(Path(folder).glob('config-before-*.json'))
            self.assertEqual(len(backups),1)
            self.assertEqual(json.loads(backups[0].read_text())['configuration_before'],bytes(range(48)).hex())
            self.assertTrue(device.closed)

    def test_upload_failure_is_recorded_and_device_closed(self):
        device=SimulatedKeyboard()
        def fail(*args): raise TimeoutError('Missing ACK')
        device.exchange=fail
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'ROOT',Path(folder)), patch.object(app,'Device',lambda:device):
            result=app.send_photo([bytes(65536),bytes(65536)],lambda value:None,100)
            self.assertEqual(result['status'],'error')
            self.assertIn('Missing ACK',result['message'])
            saved=json.loads((Path(folder)/'result-upload.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['status'],'error')
            self.assertTrue(device.closed)
