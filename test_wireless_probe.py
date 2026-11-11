import io, json, tempfile, unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import wireless_probe as wp


def make_config():
    config = bytearray(48)
    config[33] = 1; config[34] = 1
    config[35:42] = bytes([0x30, 0x15, 0x09, 3, 0x11, 0x11, 0x26])  # 2026-11-11 09:15:30
    config[43:45] = (100).to_bytes(2, 'little')
    return config


class FakeKeyboard:
    """Answers the native screen protocol like the TH80 does over USB."""
    def __init__(self):
        self.config = make_config(); self.pending = []; self.writes = []
    def write(self, data):
        data = bytes(data); self.writes.append(data)
        command = data[3]
        reply = bytearray(64); reply[:4] = data[:4]
        if command == 5:
            offset = int.from_bytes(data[5:8], 'little')
            reply[4:8] = self.config[offset:offset + 4]
        elif command == 6:
            self.config[:] = data[8:8 + data[4]]
        self.pending.append(bytes(reply))
        return len(data)
    def read(self, size, timeout):
        return self.pending.pop(0) if self.pending else b''


class SilentReceiver:
    """Accepts writes but never answers, like a receiver that doesn't forward vendor reports."""
    def __init__(self): self.writes = []
    def write(self, data): self.writes.append(bytes(data)); return len(data)
    def read(self, size, timeout): return b''
    def send_feature_report(self, data): return len(data)
    def get_feature_report(self, report_id, size): return b'\x00' * size


class FakeVia:
    def __init__(self): self.pending = []
    def write(self, data):
        self.pending.append(b'\x01\x00\x0c' + bytes(29)); return len(data)
    def read(self, size, timeout): return self.pending.pop(0) if self.pending else b''


class FakeHid:
    def __init__(self, devices, backends):
        self.devices = devices; self.backends = backends; self.opened = []
    def enumerate(self, vid=0, pid=0): return list(self.devices)
    def device(self):
        hid = self
        class Handle:
            def open_path(self, path):
                hid.opened.append(path); self.backend = hid.backends[path]
            def get_report_descriptor(self): return b'\x06\x1c\xff'
            def close(self): pass
            def __getattr__(self, name): return getattr(self.backend, name)
        return Handle()


def info(path, vid=0x320f, pid=0x5055, page=wp.SCREEN_PAGE, usage=wp.SCREEN_USAGE, product='EPOMAKER TH80 Pro V2', bus=1, maker='EPOMAKER'):
    return {'path': path, 'vendor_id': vid, 'product_id': pid, 'usage_page': page, 'usage': usage,
            'product_string': product, 'manufacturer_string': maker, 'interface_number': 2, 'bus_type': bus}


class WirelessProbeTests(unittest.TestCase):
    def run_main(self, argv, hid, folder):
        out = io.StringIO()
        with patch.object(wp, 'RESULTS', Path(folder)), redirect_stdout(out):
            code = wp.main(argv, hid)
        return code, out.getvalue()

    def test_connection_type_from_bus_and_path(self):
        self.assertEqual(wp.connection_type({'bus_type': 2}), 'Bluetooth')
        self.assertEqual(wp.connection_type({'bus_type': 0, 'path': b'\\\\?\\HID#{00001812-0000-1000-8000-00805f9b34fb}_Dev'}), 'Bluetooth')
        self.assertEqual(wp.connection_type({'path': b'\\\\?\\HID#VID_320F&PID_5055&MI_02'}), 'USB')

    def test_unrelated_devices_are_never_probed_by_default(self):
        mouse = info(b'mouse', vid=0x046d, pid=0xc077, page=0xff00, usage=1, product='USB Receiver', maker='Logitech')
        hid = FakeHid([mouse], {b'mouse': SilentReceiver()})
        with tempfile.TemporaryDirectory() as folder:
            code, out = self.run_main(['probe'], hid, folder)
        self.assertEqual(code, 1); self.assertEqual(hid.opened, [])

    def test_probe_reads_config_and_estimates_upload_time(self):
        hid = FakeHid([info(b'kb')], {b'kb': FakeKeyboard()})
        with tempfile.TemporaryDirectory() as folder:
            code, out = self.run_main(['probe', '--rounds', '3'], hid, folder)
            report = json.loads(next(Path(folder).glob('probe-*.json')).read_text())
        self.assertEqual(code, 0)
        screen = report['results'][0]['screen']
        self.assertTrue(screen['answered'])
        self.assertEqual(screen['decoded']['keyboard_clock'], '2026-11-11 09:15:30')
        self.assertEqual(screen['benchmark']['rounds'], 3)
        self.assertIn('USB: screen channel ANSWERED', out)

    def test_probe_only_sends_read_queries(self):
        keyboard = FakeKeyboard()
        hid = FakeHid([info(b'kb')], {b'kb': keyboard})
        with tempfile.TemporaryDirectory() as folder:
            self.run_main(['probe', '--rounds', '2'], hid, folder)
        self.assertTrue(keyboard.writes)
        self.assertEqual({w[3] for w in keyboard.writes}, {5})
        self.assertEqual(keyboard.config, make_config())

    def test_silent_receiver_is_reported_as_no_answer(self):
        dongle = info(b'rx', vid=0x1234, pid=0x5088, product='2.4G Wireless Receiver', maker='', bus=1)
        hid = FakeHid([dongle], {b'rx': SilentReceiver()})
        with tempfile.TemporaryDirectory() as folder:
            code, out = self.run_main(['probe'], hid, folder)
            self.assertEqual(hid.opened, [])
            code, out = self.run_main(['probe', '--device', '1234:5088'], hid, folder)
        self.assertIn('screen channel no answer', out)

    def test_via_channel_version_is_read(self):
        via = info(b'via', page=wp.VIA_PAGE, usage=wp.VIA_USAGE, bus=2)
        hid = FakeHid([via], {b'via': FakeVia()})
        with tempfile.TemporaryDirectory() as folder:
            code, out = self.run_main(['probe'], hid, folder)
        self.assertIn('Bluetooth: screen channel not found, VIA channel ANSWERED', out)

    def test_clock_needs_confirmation_and_writes_nothing_without_it(self):
        keyboard = FakeKeyboard()
        hid = FakeHid([info(b'kb')], {b'kb': keyboard})
        with tempfile.TemporaryDirectory() as folder, patch('builtins.input', return_value='no'):
            code, out = self.run_main(['clock', '--device', '320f:5055'], hid, folder)
        self.assertEqual(code, 1); self.assertEqual(hid.opened, [])

    def test_clock_writes_and_confirms(self):
        keyboard = FakeKeyboard()
        hid = FakeHid([info(b'kb')], {b'kb': keyboard})
        with tempfile.TemporaryDirectory() as folder:
            code, out = self.run_main(['clock', '--device', '320f:5055', '--yes'], hid, folder)
        self.assertEqual(code, 0)
        self.assertEqual(keyboard.config[33], 0)
        self.assertIn('read back OK', out)

    def test_snapshot_diff_finds_new_receiver(self):
        usb = info(b'kb'); rx = info(b'rx', pid=0x5088, product='2.4G Wireless Receiver')
        with tempfile.TemporaryDirectory() as folder:
            self.run_main(['snapshot', 'before'], FakeHid([usb], {}), folder)
            self.run_main(['snapshot', 'after'], FakeHid([usb, rx], {}), folder)
            code, out = self.run_main(['diff', 'before', 'after'], FakeHid([], {}), folder)
        self.assertIn('320f:5088', out.split('Gone')[0])

    def test_upload_estimate_math(self):
        self.assertEqual(-(-wp.STILL_BYTES // 56), 2341)


if __name__ == '__main__':
    unittest.main()
