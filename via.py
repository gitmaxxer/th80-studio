"""VIA Raw HID. Explicit allowlist excludes reset, firmware and bootloader commands.

Reference: QMK quantum/via.h and quantum/via.c.
"""
import time,json
from datetime import datetime
from pathlib import Path

def request(command,data=b''):
    if command not in (1,4,5,7,8,9,0x11,0x12) or len(data)>31:
        raise ValueError('VIA command not allowed.')
    return b'\x00'+bytes([command])+data+bytes(31-len(data))

def choose_interface(devices):
    matches=[d for d in devices if d.get('vendor_id')==0x320f and d.get('product_id')==0x5055
             and d.get('product_string')=='EPOMAKER TH80 Pro V2'
             and d.get('usage_page')==0xff60 and d.get('usage')==0x61]
    if len(matches)!=1: raise ValueError('Connect only one TH80 Pro V2 over USB to use VIA.')
    return matches[0]

class ViaDevice:
    def __enter__(self):
        import hid
        self.trace=[]
        info=choose_interface(hid.enumerate(0x320f,0x5055));self.handle=hid.device()
        try:
            self.handle.open_path(info['path'])
            try:
                descriptor=bytes(self.handle.get_report_descriptor())
                self.trace.append({'report_descriptor_hex':descriptor.hex()})
            except Exception as exc:
                self.trace.append({'descriptor_error':str(exc)})
            for _ in range(10):
                stale=bytes(self.handle.read(65,20))
                if not stale: break
                self.trace.append({'stale_hex':stale.hex()})
            reply=self.exchange(1)
            self.version=int.from_bytes(reply[1:3],'big')
            if not 1<=self.version<=12: raise ValueError(f'Unrecognized VIA version: {self.version}.')
        except Exception:
            self.handle.close();self.save_trace();raise
        return self
    def save_trace(self):
        root=Path(__file__).resolve().parent
        content=json.dumps(self.trace,ensure_ascii=False,indent=2)
        archive=root/'logs-via';archive.mkdir(exist_ok=True)
        (archive/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')).write_text(content,encoding='utf-8')
        (root/'diagnostic-via.json').write_text(content,encoding='utf-8')
    def __exit__(self,*args):
        try: self.handle.close()
        finally: self.save_trace()
    def exchange(self,command,data=b'',prefix=None):
        report=request(command,data)
        if not hasattr(self,'trace'): self.trace=[]
        self.trace.append({'command':command,'sent_hex':report.hex(),'sent_length':len(report)})
        if self.handle.write(report)!=33: raise OSError('Incomplete VIA write.')
        expected=prefix if prefix is not None else bytes([command])
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            response=bytes(self.handle.read(65,100))
            if not response: continue
            self.trace.append({'received_hex':response.hex(),'received_length':len(response)})
            # HID backends may return payloads padded to the report size, with
            # or without the leading zero report ID. Validate the command data.
            if response[0]==0 and len(response) in (33,65): response=response[1:]
            if response[0]==0xff: raise NotImplementedError('This feature isn\'t exposed by the VIA firmware.')
            if len(response) in (32,64) and response.startswith(expected): return response[:32]
        raise TimeoutError(f'No VIA acknowledgement for command 0x{command:02X}. Details in diagnostic-via.json. Close other configurators and try again.')
    def layer_count(self):
        count=self.exchange(0x11)[1]
        if not 1<=count<=8: raise ValueError('Unrecognized VIA layer count.')
        return count

def read_keymap(exchange,layer,rows,cols,progress=None):
    """VIA 8+: read matrix bytes in blocks, as WestBerry fastReadRawMatrix does."""
    if not 0<=layer<8 or not 1<=rows<=8 or not 1<=cols<=16:
        raise ValueError('Invalid matrix or layer.')
    length=rows*cols*2;raw=bytearray()
    for position in range(0,length,28):
        size=min(28,length-position)
        offset=layer*length+position
        data=offset.to_bytes(2,'big')+bytes([size])
        reply=exchange(0x12,data,bytes([0x12])+data)
        block=reply[4:4+size]
        if len(block)!=size: raise OSError('Incomplete key block.')
        raw.extend(block)
        if progress: progress(f'Reading matrix: {len(raw)//2}/{rows*cols}')
    return [int.from_bytes(raw[i:i+2],'big') for i in range(0,length,2)]

def get_keycode(exchange,layer,row,col,buffered=False):
    if not 0<=layer<8 or not 0<=row<8 or not 0<=col<16: raise ValueError('Invalid key position.')
    if buffered:
        # TH80 definition: 8 rows x 16 columns, two bytes per key.
        offset=(layer*128+row*16+col)*2
        data=offset.to_bytes(2,'big')+bytes([2])
        response=exchange(0x12,data,bytes([0x12])+data)
        if len(response)<6: raise OSError('Incomplete key read.')
        return int.from_bytes(response[4:6],'big')
    coordinates=bytes([layer,row,col])
    response=exchange(4,coordinates,bytes([4])+coordinates)
    return int.from_bytes(response[4:6],'big')

def set_keycode(exchange,layer,row,col,code,buffered=False):
    if not 0<=code<=65535: raise ValueError('Invalid keycode.')
    if not 0<=layer<8 or not 0<=row<8 or not 0<=col<16: raise ValueError('Invalid key position.')
    data=bytes([layer,row,col])+code.to_bytes(2,'big')
    exchange(5,data,bytes([5])+data)
    if get_keycode(exchange,layer,row,col,buffered=buffered)!=code: raise OSError('The new key was not confirmed by the final read.')

def legacy_lighting_value(exchange,identifier,size):
    # VIA v2: one value ID, no channel. Same IDs as WestBerry's keyboard API.
    values=[]
    for sentinel in (b'\xa5\x5a',b'\x5a\xa5'):
        reply=exchange(8,bytes([identifier])+sentinel,bytes([8,identifier]))
        values.append(reply[2:2+size])
    if values[0]!=values[1] or len(values[0])!=size:
        raise NotImplementedError('Legacy lighting query returned no confirmed data.')
    return values[0]

def read_lighting(exchange):
    def value(channel,identifier,size):
        # Unsupported vendor handlers sometimes echo queries without filling them.
        first=exchange(8,bytes([channel,identifier,0xa5,0x5a]),bytes([8,channel,identifier]))[3:3+size]
        second=exchange(8,bytes([channel,identifier,0x5a,0xa5]),bytes([8,channel,identifier]))[3:3+size]
        if first!=second: raise NotImplementedError('Lighting query returned no confirmed data.')
        return first
    for channel in (3,2,1):
        try:
            brightness=value(channel,1,1)[0]
            result={'channel':channel,'brightness':brightness}
            if channel in (2,3):
                color=value(channel,4,2)
                result.update(hue=color[0],saturation=color[1])
            return result
        except NotImplementedError: continue
    try:
        brightness=legacy_lighting_value(exchange,9,1)[0]
        color=legacy_lighting_value(exchange,12,2)
        return {'channel':'legacy','brightness':brightness,'hue':color[0],'saturation':color[1]}
    except NotImplementedError: pass
    return None

def write_lighting(exchange,channel,brightness,hue=None,saturation=None):
    if channel not in (1,2,3,'legacy') or not 0<=brightness<=255: raise ValueError('Invalid lighting.')
    if channel==1 and hue is not None: raise ValueError('This channel doesn\'t accept color.')
    if hue is not None and (saturation is None or not 0<=hue<=255 or not 0<=saturation<=255): raise ValueError('Invalid color.')
    if channel=='legacy':
        legacy_lighting_value(exchange,9,1)
        if hue is not None: legacy_lighting_value(exchange,12,2)
        data=bytes([9,brightness]);exchange(7,data,bytes([7])+data)
        if hue is not None:
            data=bytes([12,hue,saturation]);exchange(7,data,bytes([7])+data)
        exchange(9)
        if abs(legacy_lighting_value(exchange,9,1)[0]-brightness)>2:
            raise OSError('Brightness was not confirmed.')
        if hue is not None:
            color=legacy_lighting_value(exchange,12,2)
            difference=abs(color[0]-hue)
            if min(difference,256-difference)>2 or abs(color[1]-saturation)>2:
                raise OSError('Color was not confirmed.')
        return
    # Confirm channel support before any write.
    exchange(8,bytes([channel,1]),bytes([8,channel,1]))
    if hue is not None:
        exchange(8,bytes([channel,4]),bytes([8,channel,4]))
    data=bytes([channel,1,brightness]);exchange(7,data,bytes([7])+data)
    if hue is not None:
        data=bytes([channel,4,hue,saturation]);exchange(7,data,bytes([7])+data)
    exchange(9,bytes([channel]),bytes([9,channel]))
    value=exchange(8,bytes([channel,1]),bytes([8,channel,1]))[3]
    if abs(value-brightness)>2: raise OSError('Brightness was not confirmed.')
    if hue is not None:
        color=exchange(8,bytes([channel,4]),bytes([8,channel,4]))
        hue_distance=min(abs(color[3]-hue),256-abs(color[3]-hue))
        if hue_distance>2 or abs(color[4]-saturation)>2: raise OSError('Color was not confirmed.')

KEYCODES={0:'Disabled',1:'Transparent'}
KEYCODES.update({4+i:chr(65+i) for i in range(26)})
KEYCODES.update({30+i:str((i+1)%10) for i in range(10)})
KEYCODES.update({58+i:f'F{i+1}' for i in range(12)})
KEYCODES.update({40:'Enter',41:'Esc',42:'Backspace',43:'Tab',44:'Space',45:'-',46:'=',47:'[',48:']',49:'\\',51:';',52:"'",53:'`',54:',',55:'.',56:'/',57:'Caps Lock',70:'Print Screen',71:'Scroll Lock',72:'Pause',73:'Insert',74:'Home',75:'Page Up',76:'Delete',77:'End',78:'Page Down',79:'Right',80:'Left',81:'Down',82:'Up',224:'Left Ctrl',225:'Left Shift',226:'Left Alt',227:'Left Windows',228:'Right Ctrl',229:'Right Shift',230:'Right Alt',231:'Right Windows'})

def key_name(code): return KEYCODES.get(code,f'Special 0x{code:04X}')
