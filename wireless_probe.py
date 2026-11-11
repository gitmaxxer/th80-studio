"""Wireless probe: can the TH80 Pro V2 be configured over 2.4 GHz or Bluetooth?

Finds every HID interface the keyboard (or its 2.4 GHz receiver) exposes, then
sends only read-only queries to the two private channels the app relies on:

  * screen channel (usage page 0xFF1C): native "read config" query, command 5
  * VIA channel (usage page 0xFF60): "get protocol version", command 1

Nothing is written unless you run the separate `clock` command with --yes.
Results are saved to probe-results/ so they can be compared and shared.

Usage:
  python wireless_probe.py list [--all]
  python wireless_probe.py snapshot NAME
  python wireless_probe.py diff NAME_BEFORE NAME_AFTER
  python wireless_probe.py probe [--device VID:PID] [--rounds 20]
  python wireless_probe.py clock --device VID:PID [--yes]
"""
import argparse, json, sys, time
from datetime import datetime
from pathlib import Path

from protocol import config_query, matches_response, clock_config, packet
from via import request as via_request

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / 'probe-results'
SCREEN_PAGE, SCREEN_USAGE = 0xFF1C, 0x92
VIA_PAGE, VIA_USAGE = 0xFF60, 0x61
TH80_VID = 0x320F
# Strict on purpose: generic names like 'receiver' would match other brands' dongles.
# An unknown receiver is found with snapshot/diff and probed with --device.
NAME_HINTS = ('epomaker', 'th80')
BUS_NAMES = {0: 'unknown', 1: 'USB', 2: 'Bluetooth', 3: 'I2C', 4: 'SPI'}
# One still image is written twice (two slots) as 65,536-byte frames in 56-byte packets.
STILL_BYTES = 2 * 65536
GIF18_BYTES = 2 * 18 * 65536


# ---------- enumeration ----------

def connection_type(info):
    """Best guess at how an interface is connected: USB, Bluetooth or unknown."""
    bus = info.get('bus_type')
    if isinstance(bus, int) and bus in BUS_NAMES and bus != 0:
        return BUS_NAMES[bus]
    path = info.get('path') or b''
    path = path.decode('utf-8', 'replace') if isinstance(path, bytes) else str(path)
    upper = path.upper()
    if 'BTHENUM' in upper or 'BTHLEDEVICE' in upper or '00001124-0000-1000-8000-00805F9B34FB' in upper \
            or '00001812-0000-1000-8000-00805F9B34FB' in upper or 'BLUETOOTH' in upper:
        return 'Bluetooth'
    if 'USB' in upper or 'VID_' in upper:
        return 'USB'
    return 'unknown'


def channel_kind(info):
    page, usage = info.get('usage_page') or 0, info.get('usage') or 0
    if page == SCREEN_PAGE and usage == SCREEN_USAGE: return 'screen'
    if page == VIA_PAGE and usage == VIA_USAGE: return 'via'
    if page >= 0xFF00: return 'vendor'
    return 'standard'


def looks_like_keyboard(info):
    if info.get('vendor_id') == TH80_VID: return True
    text = ' '.join(str(info.get(k) or '') for k in ('product_string', 'manufacturer_string')).lower()
    return any(hint in text for hint in NAME_HINTS)


def describe(info):
    return {
        'vid_pid': f"{info.get('vendor_id', 0):04x}:{info.get('product_id', 0):04x}",
        'product': info.get('product_string') or '',
        'manufacturer': info.get('manufacturer_string') or '',
        'connection': connection_type(info),
        'interface': info.get('interface_number'),
        'usage_page': f"0x{(info.get('usage_page') or 0):04x}",
        'usage': f"0x{(info.get('usage') or 0):02x}",
        'channel': channel_kind(info),
        'path': (info.get('path') or b'').decode('utf-8', 'replace') if isinstance(info.get('path'), bytes) else str(info.get('path') or ''),
    }


def parse_device(text):
    try:
        vid, pid = text.split(':')
        return int(vid, 16), int(pid, 16)
    except ValueError:
        raise SystemExit(f'Use VID:PID in hex, e.g. 320f:5055 (got {text!r}).')


def select(devices, device=None, everything=False):
    if device:
        vid, pid = device
        return [d for d in devices if d.get('vendor_id') == vid and d.get('product_id') == pid]
    return list(devices) if everything else [d for d in devices if looks_like_keyboard(d)]


# ---------- read-only probes ----------

def drain(handle, size=65):
    for _ in range(10):
        if not handle.read(size, 20): break


def screen_query(handle, offset=0, timeout=1.5):
    """Send native 'read config' (command 5) and wait for the matching reply."""
    query = config_query(offset)
    written = handle.write(query)
    if written != len(query):
        raise OSError(f'write returned {written}, expected {len(query)}')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = bytes(handle.read(64, 100))
        if response and matches_response(query, response):
            return response
    return None


def screen_query_feature(handle):
    """Fallback: same query as a feature report, for receivers that only forward those."""
    query = config_query(0)
    handle.send_feature_report(query)
    time.sleep(0.05)
    response = bytes(handle.get_feature_report(4, 64))
    return response if matches_response(query, response) else None


def via_version(handle, timeout=1.5):
    report = via_request(1)
    if handle.write(report) != len(report):
        raise OSError('incomplete VIA write')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = bytes(handle.read(65, 100))
        if not response: continue
        if response[0] == 0 and len(response) in (33, 65): response = response[1:]
        if response[:1] == b'\x01' and len(response) >= 3:
            return int.from_bytes(response[1:3], 'big')
    return None


def read_config(handle):
    data = bytearray()
    for offset in range(0, 48, 4):
        reply = screen_query(handle, offset)
        if reply is None: raise TimeoutError(f'no reply at offset {offset}')
        data.extend(reply[4:8])
    return bytes(data)


def decode_config(config):
    def unbcd(v): return (v >> 4) * 10 + (v & 15)
    s, m, h, _wd, d, mo, y = config[35:42]
    return {
        'display_mode': {0: 'clock/status', 1: 'image', 2: 'mode 2'}.get(config[33], config[33]),
        'frames': config[34],
        'keyboard_clock': f'20{unbcd(y):02d}-{unbcd(mo):02d}-{unbcd(d):02d} {unbcd(h):02d}:{unbcd(m):02d}:{unbcd(s):02d}',
        'frame_delay_ms': int.from_bytes(config[43:45], 'little'),
    }


def benchmark(handle, rounds):
    times = []
    for _ in range(rounds):
        start = time.perf_counter()
        if screen_query(handle) is None: break
        times.append(time.perf_counter() - start)
    if not times: return None
    rtt = sorted(times)[len(times) // 2]
    packets = lambda size: -(-size // 56)
    return {
        'rounds': len(times),
        'median_round_trip_ms': round(rtt * 1000, 1),
        'estimated_still_upload_s': round(packets(STILL_BYTES) * rtt, 1),
        'estimated_18_frame_gif_upload_s': round(packets(GIF18_BYTES) * rtt, 1),
    }


def probe_interface(hid, info, rounds):
    result = describe(info)
    handle = hid.device()
    try:
        handle.open_path(info['path'])
    except Exception as exc:
        result['open_error'] = str(exc)
        return result
    try:
        try: result['report_descriptor_hex'] = bytes(handle.get_report_descriptor()).hex()
        except Exception as exc: result['report_descriptor_error'] = str(exc)
        drain(handle)
        kind = result['channel']
        if kind == 'via':
            try:
                version = via_version(handle)
                result['via'] = {'answered': version is not None, 'protocol_version': version}
            except Exception as exc:
                result['via'] = {'answered': False, 'error': str(exc)}
        else:
            screen = {'answered': False}
            try:
                reply = screen_query(handle)
                if reply is None:
                    try:
                        reply = screen_query_feature(handle)
                        if reply is not None: screen['method'] = 'feature report'
                    except Exception as exc:
                        screen['feature_error'] = str(exc)
                else:
                    screen['method'] = 'output report'
                if reply is not None:
                    screen['answered'] = True
                    screen['reply_hex'] = reply.hex()
                    if screen['method'] == 'output report':
                        config = read_config(handle)
                        screen['config_hex'] = config.hex()
                        screen['decoded'] = decode_config(config)
                        screen['benchmark'] = benchmark(handle, rounds)
            except Exception as exc:
                screen['error'] = str(exc)
            result['screen'] = screen
    finally:
        handle.close()
    return result


# ---------- reporting ----------

def save(name, data):
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    return path


def print_table(rows):
    if not rows:
        print('No matching HID interfaces. Is the keyboard on and connected? Try --all.')
        return
    for r in rows:
        mark = {'screen': '  <- screen channel', 'via': '  <- VIA channel', 'vendor': '  <- private channel'}.get(r['channel'], '')
        print(f"{r['vid_pid']}  {r['connection']:<9}  if={str(r['interface']):<4} page={r['usage_page']} usage={r['usage']}  "
              f"{r['product'] or '(no name)'}{mark}")


def summarize(results):
    lines = []
    for connection in ('USB', 'Bluetooth', 'unknown'):
        group = [r for r in results if r['connection'] == connection]
        if not group: continue
        screen = any(r.get('screen', {}).get('answered') for r in group)
        via = any(r.get('via', {}).get('answered') for r in group)
        tested_screen = any('screen' in r for r in group)
        tested_via = any('via' in r for r in group)
        lines.append(f'{connection}: screen channel '
                     + ('ANSWERED' if screen else ('no answer' if tested_screen else 'not found'))
                     + ', VIA channel '
                     + ('ANSWERED' if via else ('no answer' if tested_via else 'not found')))
        for r in group:
            bench = r.get('screen', {}).get('benchmark')
            if bench:
                lines.append(f"  {r['vid_pid']}: round trip {bench['median_round_trip_ms']} ms -> still image ~{bench['estimated_still_upload_s']} s, "
                             f"18-frame GIF ~{bench['estimated_18_frame_gif_upload_s']} s")
    return lines


# ---------- commands ----------

def cmd_list(hid, args):
    rows = [describe(d) for d in select(hid.enumerate(), parse_device(args.device) if args.device else None, args.all)]
    print_table(rows)


def cmd_snapshot(hid, args):
    rows = [describe(d) for d in hid.enumerate()]
    path = save(f'snapshot-{args.name}.json', rows)
    print(f'Saved {len(rows)} interfaces to {path}')


def cmd_diff(hid, args):
    def load(name): return json.loads((RESULTS / f'snapshot-{name}.json').read_text(encoding='utf-8'))
    key = lambda r: (r['vid_pid'], r['usage_page'], r['usage'], r['path'])
    before, after = load(args.before), load(args.after)
    old = {key(r) for r in before}
    new = [r for r in after if key(r) not in old]
    gone = [r for r in before if key(r) not in {key(x) for x in after}]
    print(f'New in "{args.after}" ({len(new)}):'); print_table(new)
    print(f'\nGone since "{args.before}" ({len(gone)}):'); print_table(gone)


def cmd_probe(hid, args):
    device = parse_device(args.device) if args.device else None
    targets = [d for d in select(hid.enumerate(), device) if channel_kind(d) != 'standard']
    if not targets:
        print('No private HID channels found on the keyboard. Run `list --all` and pass --device VID:PID.')
        return 1
    print('Probing these interfaces with read-only queries:'); print_table([describe(d) for d in targets]); print()
    results = [probe_interface(hid, d, args.rounds) for d in targets]
    report = {'timestamp': datetime.now().isoformat(), 'platform': sys.platform, 'results': results}
    path = save(f"probe-{datetime.now():%Y%m%d-%H%M%S}.json", report)
    print('\n'.join(summarize(results)))
    print(f'\nFull report: {path}')
    return 0


def cmd_clock(hid, args):
    """The only write: set the keyboard clock via the screen channel, then read it back."""
    vid, pid = parse_device(args.device)
    targets = [d for d in select(hid.enumerate(), (vid, pid)) if channel_kind(d) == 'screen']
    if len(targets) != 1:
        print(f'Need exactly one screen channel on {args.device}; found {len(targets)}. Run `probe` first.')
        return 1
    if not args.yes:
        answer = input(f'Write the PC clock to the keyboard over {connection_type(targets[0])}? Type yes: ')
        if answer.strip().lower() != 'yes':
            print('Cancelled; nothing was written.')
            return 1
    handle = hid.device(); handle.open_path(targets[0]['path'])
    try:
        drain(handle)
        original = read_config(handle)
        now = datetime.now()
        wanted = clock_config(original, now)
        for command, data in ((1, b''), (6, wanted), (2, b'')):
            request = packet(command, data)
            if handle.write(request) != len(request): raise OSError(f'incomplete write for command {command}')
            deadline = time.monotonic() + 3; ok = False
            while time.monotonic() < deadline:
                reply = bytes(handle.read(64, 100))
                if reply and matches_response(request, reply):
                    if reply[7] in (0xFE, 0xFF): raise OSError(f'keyboard rejected command {command}: {reply.hex()}')
                    ok = True; break
            if not ok: raise TimeoutError(f'no acknowledgement for command {command}')
        after = read_config(handle)
        confirmed = after[39:42] == wanted[39:42] and after[33] == wanted[33]
        report = {'timestamp': now.isoformat(), 'device': args.device, 'connection': connection_type(targets[0]),
                  'before_hex': original.hex(), 'after_hex': after.hex(), 'confirmed': confirmed}
        path = save(f"clock-{now:%Y%m%d-%H%M%S}.json", report)
        print(('Clock written and read back OK. Check the screen.' if confirmed
               else 'Write acknowledged but read-back did not match.') + f' Report: {path}')
        return 0 if confirmed else 1
    finally:
        handle.close()


def main(argv=None, hid_module=None):
    parser = argparse.ArgumentParser(description='Test whether the TH80 Pro V2 can be configured over 2.4 GHz or Bluetooth.')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('list', help='show HID interfaces of the keyboard/receiver')
    p.add_argument('--all', action='store_true', help='show every HID device, not just likely keyboard ones')
    p.add_argument('--device', help='only this VID:PID')
    p = sub.add_parser('snapshot', help='save all HID interfaces under a name'); p.add_argument('name')
    p = sub.add_parser('diff', help='compare two snapshots'); p.add_argument('before'); p.add_argument('after')
    p = sub.add_parser('probe', help='read-only test of the screen and VIA channels')
    p.add_argument('--device', help='VID:PID to probe (default: anything that looks like the keyboard)')
    p.add_argument('--rounds', type=int, default=20, help='queries used to time the round trip')
    p = sub.add_parser('clock', help='WRITE TEST: set the keyboard clock over this connection')
    p.add_argument('--device', required=True); p.add_argument('--yes', action='store_true')
    args = parser.parse_args(argv)
    if hid_module is None:
        try:
            import hid as hid_module
        except ImportError:
            print('hidapi is not installed. Run Install.cmd (or: pip install -r requirements.txt).')
            return 1
    commands = {'list': cmd_list, 'snapshot': cmd_snapshot, 'diff': cmd_diff, 'probe': cmd_probe, 'clock': cmd_clock}
    return commands[args.command](hid_module, args) or 0


if __name__ == '__main__':
    sys.exit(main())
