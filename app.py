"""TH80 desktop configurator: photos, GIF animation and clock."""
import sys, json, time, threading, queue
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

ROOT=Path(__file__).resolve().parent
MAX_NATIVE_BRIGHTNESS=9  # Observed on this TH80; reference protocol agrees.
NATIVE_EFFECTS=(1,3,13,16)
NATIVE_SPEEDS=(2,4)
NATIVE_COLORS={
    'Yellow-green':bytes.fromhex('00 68 ff 00 0b'),
    'Green':bytes.fromhex('00 35 ff 00 0c'),
    'Rainbow':bytes.fromhex('ff ff 01 00 00'),
}  # Exact bytes 5..9 captured on this TH80; do not infer arbitrary color IDs.
from protocol import config_query, matches_response, select_device
from protocol import encode_frame, photo_config, animation_config, clock_config, display_config
from transfer import Device, upload, upload_animation, write_config
from media import load_media
from via import ViaDevice, get_keycode, set_keycode, read_lighting, write_lighting, KEYCODES, key_name, read_keymap
from keyboard_layout import parse_layout
from lighting_catalog import load_catalog, import_captures, observe_configuration
from color_wheel import normalize_hex, rgb_configuration, ask_color

DEFINITION=json.loads((ROOT/'via-definition.json').read_text(encoding='utf-8-sig'))
KEY_LAYOUT=parse_layout(DEFINITION['layouts']['keymap'],8,16)

def read_via(layer,progress):
    result={'timestamp':datetime.now().isoformat(),'status':'error','layer':layer}
    try:
        with ViaDevice() as device:
            count=device.layer_count()
            if not 0<=layer<count: raise ValueError('Layer not available on this keyboard.')
            keys={}
            if device.version>=8:
                rows=DEFINITION['matrix']['rows'];cols=DEFINITION['matrix']['cols']
                matrix=read_keymap(device.exchange,layer,rows,cols,progress)
                keys={f'{key.row},{key.col}':matrix[key.row*cols+key.col] for key in KEY_LAYOUT}
            else:
                for index,key in enumerate(KEY_LAYOUT):
                    keys[f'{key.row},{key.col}']=get_keycode(device.exchange,layer,key.row,key.col)
                    progress(f'Reading keys: {index+1}/{len(KEY_LAYOUT)}')
            result.update(status='via_confirmed',version=device.version,layers=count,keys=keys,lighting=read_lighting(device.exchange),
                          message=f'Layer {layer+1} read. Click a key to configure it.')
    except Exception as exc: result['message']=str(exc)
    (ROOT/'result-via.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def write_key(layer,row,col,old,new):
    result={'timestamp':datetime.now().isoformat(),'status':'error','layer':layer,'row':row,'col':col,'old':old,'new':new}
    try:
        if (row,col) not in {(key.row,key.col) for key in KEY_LAYOUT}: raise ValueError('Key is outside the TH80 layout.')
        with ViaDevice() as device:
            if not 0<=layer<device.layer_count(): raise ValueError('Invalid layer.')
            current=get_keycode(device.exchange,layer,row,col,buffered=device.version>=8)
            if current!=old: raise ValueError('The key changed since it was read. Read the layer again before applying.')
            backup=ROOT/('key-before-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
            backup.write_text(json.dumps(result,indent=2),encoding='utf-8')
            set_keycode(device.exchange,layer,row,col,new,buffered=device.version>=8)
            result.update(status='key_acknowledged',message=f'Key changed: {key_name(old)} to {key_name(new)}. Test it on the keyboard.')
            (ROOT/'last-key.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    except Exception as exc: result['message']=str(exc)
    (ROOT/'result-key.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def read_native_lighting():
    with Device() as device: config=device.read_config()
    if len(config)!=48: raise OSError('Incomplete configuration.')
    if config[2]>MAX_NATIVE_BRIGHTNESS: raise ValueError('Brightness outside the observed 0-9 range. Capture the settings for analysis.')
    return {'channel':'native','brightness':config[2],'max_brightness':MAX_NATIVE_BRIGHTNESS,'effect':config[1],'speed':config[3]}

def probe_lighting():
    result={'timestamp':datetime.now().isoformat(),'status':'error','lighting':None}
    try:
        with ViaDevice() as device:
            lighting=read_lighting(device.exchange)
            result.update(lighting=lighting,version=device.version,
                          status='lighting_confirmed' if lighting else 'lighting_unavailable',
                          message='VIA lighting control confirmed.' if lighting else 'The keyboard answered VIA but returned no lighting values in the formats queried (current and legacy).')
        if lighting is None:
            native=read_native_lighting()
            if native:
                result.update(status='lighting_confirmed',lighting=native,
                              message=f'Brightness: {native["brightness"]}/9 · Effect: {native["effect"]} · Speed: {native["speed"]}. Color options use the captured states.')
    except Exception as exc: result['message']=str(exc)
    (ROOT/'result-lighting.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def capture_lighting(fresh=False,baseline=None):
    """Read the known screen configuration; compare captures without any writes."""
    result={'timestamp':datetime.now().isoformat(),'status':'error'}
    try:
        latest=ROOT/'lighting-capture.json'
        previous=baseline
        if previous is None and not fresh and latest.exists():
            previous=json.loads(latest.read_text(encoding='utf-8'))
        with Device() as device: current=device.read_config()
        if len(current)!=48: raise OSError('Incomplete configuration.')
        result.update(status='snapshot_saved',configuration=current.hex(),candidate_changes=[],clock_changes=[],other_changes=[],
                      message='Before saved. Change only one setting on the keyboard and click 2 · Capture after.')
        if previous:
            before=bytes.fromhex(previous['configuration'])
            if len(before)!=48: raise ValueError('Invalid previous capture.')
            changes=[{'offset':i,'before':a,'after':b} for i,(a,b) in enumerate(zip(before,current)) if a!=b]
            result.update(status='comparison_saved',previous_timestamp=previous['timestamp'],
                          candidate_changes=[item for item in changes if item['offset']<33],
                          clock_changes=[item for item in changes if 35<=item['offset']<=41],
                          other_changes=[item for item in changes if item['offset']>=33 and not 35<=item['offset']<=41])
            count=len(result['candidate_changes'])
            result['message']=f'Captures compared: {count} field(s) before the screen area changed. Log saved for analysis.'
        content=json.dumps(result,ensure_ascii=False,indent=2)
        archive=ROOT/'logs-lighting';archive.mkdir(exist_ok=True)
        (archive/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')).write_text(content,encoding='utf-8')
        latest.write_text(content,encoding='utf-8')
    except Exception as exc: result['message']=str(exc)
    (ROOT/'result-lighting-capture.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def learn_native_lighting():
    with Device() as device: config=device.read_config()
    catalog,name=observe_configuration(ROOT,config)
    return {'status':'catalog_saved','catalog':catalog,'message':f'State recorded: effect {config[1]}, speed {config[3]}, color {name}.'}

def apply_native_brightness(brightness,effect=None,speed=None,color_preset=None,custom_color=None):
    result={'timestamp':datetime.now().isoformat(),'status':'error','channel':'native','brightness':brightness}
    try:
        catalog=load_catalog(ROOT)
        if type(brightness) is not int or not 0<=brightness<=MAX_NATIVE_BRIGHTNESS:
            raise ValueError('Use a whole brightness level from 0 to 9: ten levels on this TH80.')
        if effect is not None and (type(effect) is not int or effect not in catalog['effects']):
            raise ValueError('Choose an effect recorded on this TH80.')
        if speed is not None and (type(speed) is not int or speed not in catalog['speeds']):
            raise ValueError('Choose a speed recorded on this TH80.')
        if color_preset is not None and color_preset not in catalog['colors']:
            raise ValueError('Choose one of the colors captured on this TH80.')
        if custom_color is not None:
            custom_color=normalize_hex(custom_color)
            if color_preset is not None: raise ValueError('Choose either a custom color or a captured state.')
        with Device() as device:
            original=device.read_config()
            if len(original)!=48: raise OSError('Incomplete configuration.')
            if original[2]>MAX_NATIVE_BRIGHTNESS: raise ValueError('Current brightness is outside the observed range. Capture the settings before applying.')
            result['configuration_before']=original.hex()
            (ROOT/('light-before-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
            desired=bytearray(original);desired[2]=brightness;fields={2}
            if effect is not None: desired[1]=effect;fields.add(1)
            if speed is not None: desired[3]=speed;fields.add(3)
            if color_preset is not None:
                desired[5:10]=bytes.fromhex(catalog['colors'][color_preset]);fields.update(range(5,10))
            if custom_color is not None:
                desired=bytearray(rgb_configuration(desired,custom_color));fields.update(range(5,9))
            write_config(device.exchange,bytes(desired))
            current=device.read_config();result['configuration_after']=current.hex()
            if len(current)!=48 or any(current[i]!=desired[i] for i in fields): raise OSError('The lighting change was not confirmed by the final read.')
            if any(current[i]!=original[i] for i in range(48) if i not in fields and not 35<=i<=41):
                raise OSError('Brightness was read back, but another setting also changed. Check the log before continuing.')
            result.update(status='lighting_acknowledged',effect=current[1],speed=current[3],color_preset=color_preset,custom_color=custom_color,
                          message=f'Lighting confirmed: brightness {brightness}, effect {current[1]}, speed {current[3]}. Check the keyboard.')
    except Exception as exc: result['message']=str(exc)
    (ROOT/'result-lighting.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def apply_lighting(brightness,color,channel=None,effect=None,speed=None,color_preset=None,custom_color=None):
    if channel=='native': return apply_native_brightness(brightness,effect,speed,color_preset,custom_color)
    import colorsys
    result={'timestamp':datetime.now().isoformat(),'status':'error'}
    try:
        with ViaDevice() as device:
            current=read_lighting(device.exchange)
            if current is None: raise ValueError('The firmware does not expose lighting over VIA.')
            result['before']=current
            (ROOT/('light-before-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
            hue=saturation=None
            if current['channel']!=1:
                rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
                h,s,_=colorsys.rgb_to_hsv(*rgb);hue=round(h*255);saturation=round(s*255)
            write_lighting(device.exchange,current['channel'],brightness,hue,saturation)
            result.update(status='lighting_acknowledged',message='Lighting applied. The color depends on the effect active on the keyboard.')
    except Exception as exc: result['message']=str(exc)
    (ROOT/'result-lighting.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def send_photo(frame,progress,delay_ms=None):
    result={'timestamp':datetime.now().isoformat(),'status':'error'}
    try:
        with Device() as device:
            original=device.read_config()
            result['configuration_before']=original.hex()
            # Save metadata before any write. This does not back up old images.
            backup=ROOT/('config-before-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
            backup.write_text(json.dumps(result,indent=2),encoding='utf-8')
            if delay_ms is None:
                upload(device.exchange,original,frame,progress)
                expected=photo_config(original)
            else:
                upload_animation(device.exchange,original,frame,delay_ms,progress)
                expected=animation_config(original,len(frame),delay_ms)
            current=device.read_config()
            result['configuration_after']=current.hex()
            fields=(33,34,46) if delay_ms is None else (33,34,43,44,46)
            if any(current[i]!=expected[i] for i in fields):
                raise OSError('Data sent, but the photo mode was not confirmed by the final read.')
            result['status']='upload_acknowledged'
            result['message']='Transfer confirmed by the keyboard. Check the screen!'
    except Exception as exc:
        result['message']=str(exc)+' The upload was not confirmed; the images may have been partly changed.'
    finally:
        (ROOT/'result-upload.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def set_screen(mode):
    result={'timestamp':datetime.now().isoformat(),'status':'error','operation':mode}
    try:
        with Device() as device:
            original=device.read_config()
            result['configuration_before']=original.hex()
            backup=ROOT/('config-before-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
            backup.write_text(json.dumps(result,indent=2),encoding='utf-8')
            now=datetime.now()  # Time of this Windows PC, including its local timezone.
            config=clock_config(original,now) if mode=='clock' else display_config(original,1)
            write_config(device.exchange,config)
            current=device.read_config()
            result['configuration_after']=current.hex()
            if current[33]!=config[33]: raise OSError('The screen mode was not confirmed.')
            if mode=='clock' and current[39:42]!=config[39:42]:
                raise OSError('The clock date was not confirmed.')
            result['status']='configuration_acknowledged'
            result['message']=(f'Clock set to {now:%d/%m/%Y %H:%M:%S}. Check the screen!'
                               if mode=='clock' else 'Image mode confirmed. Check the screen!')
    except Exception as exc:
        result['message']=str(exc)+' The change was not confirmed.'
    finally:
        (ROOT/'result-clock.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def probe(progress):
    import hid
    devices=hid.enumerate(0x320f,0x5055)
    result={'timestamp':datetime.now().isoformat(),'status':'error',
            'interfaces':[{k:d.get(k) for k in ['product_string','usage_page','usage','interface_number']} for d in devices],
            'responses':[], 'configuration_hex':None}
    handle=None
    try:
        progress('Looking for the screen interface…')
        device=select_device(devices)
        handle=hid.device()
        handle.open_path(device['path'])
        result['product']=handle.get_product_string()
        progress('Keyboard found. Reading the configuration…')
        # Drain stale input without emitting any output reports.
        for _ in range(10):
            if not handle.read(64,20): break
        config=bytearray()
        for offset in range(0,48,4):
            packet=config_query(offset)
            written=handle.write(packet)
            if written!=len(packet): raise OSError('Incomplete USB query.')
            deadline=time.monotonic()+2
            matched=None
            while time.monotonic()<deadline:
                response=bytes(handle.read(64,100))
                if response:
                    result['responses'].append({'offset':offset,'hex':response.hex()})
                if matches_response(packet,response):
                    matched=response
                    break
            if matched is None:
                raise TimeoutError(f'Keyboard found, but the query at offset {offset} got no confirmed reply. Uploading stays blocked.')
            config.extend(matched[4:8])
            progress(f'Reading configuration: {offset+4}/48 bytes')
        result['configuration_hex']=config.hex()
        result['status']='query_confirmed'
        result['message']='Connection and query confirmed. No settings were changed.'
    except Exception as exc:
        result['message']=str(exc)
    finally:
        if handle is not None:
            try: handle.close()
            except Exception: pass
        (ROOT/'result-connection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

class App:
    native_effects=NATIVE_EFFECTS
    native_speeds=NATIVE_SPEEDS
    native_colors=NATIVE_COLORS
    def __init__(self):
        self.root=tk.Tk()
        self.root.title('TH80 Studio')
        self.root.geometry('1120x820')
        self.root.minsize(1020,760)
        self.events=queue.Queue()
        self.busy=False
        self.connected=False
        self.media=None
        self.preview_frames=[]
        self.preview_index=0
        self.layout=KEY_LAYOUT
        self.viadata=None
        self.light_data=None
        self.selected_key=None
        self.last_key=None
        catalog_error=None
        try: self.refresh_catalog(import_captures(ROOT))
        except (OSError,ValueError) as exc: catalog_error=str(exc)
        try:
            saved=json.loads((ROOT/'last-key.json').read_text(encoding='utf-8'))
            if saved.get('status')=='key_acknowledged': self.last_key=saved
        except (OSError,ValueError): pass
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        from ui import build_ui
        build_ui(self)
        if catalog_error: self.status.set(catalog_error)
        self.root.after(100,self.poll)
        self.root.after(100,self.animate)
        self.root.after(1000,self.tick_clock)

    def show_page(self,page):
        from ui import C
        for frame in self.pages.values(): frame.pack_forget()
        self.pages[page].pack(fill='both',expand=True)
        for name,button in self.nav_buttons.items():
            button.configure(bg=C['panel'] if name==page else C['side'],fg=C['blue'] if name==page else C['muted'])
        self.heading.set({'images':'Screen & GIF','clock':'Clock','keys':'Keys','lighting':'Lighting','manual':'Manual'}[page])

    def tick_clock(self):
        now=datetime.now()
        self.clock_preview.configure(text=now.strftime('%H:%M'))
        self.date_preview.configure(text=now.strftime('%d / %m / %Y'))
        self.root.after(1000,self.tick_clock)

    def task(self,kind,function,message):
        if self.busy: return
        self.busy=True;self.update_buttons()
        self.bar.configure(mode='indeterminate');self.bar.start(12)
        self.status.set(message)
        def worker():
            try: result=function()
            except Exception as exc: result={'status':'error','message':str(exc)}
            self.events.put((kind,result))
        threading.Thread(target=worker,daemon=True).start()

    def load_keys(self):
        if self.busy: return
        layer=int(self.layer.get().split()[-1])-1
        self.viadata=None
        self.task('via',lambda:read_via(layer,lambda text:self.events.put(('progress',text))),'Querying VIA… Close other keyboard configurators.')

    def load_light(self):
        if self.busy: return
        self.light_data=None
        self.task('light-probe',probe_lighting,'Querying VIA lighting only…')

    def select_key(self,position):
        if self.busy: return
        self.selected_key=position
        self.keyboard_view.selected=position;self.keyboard_view.draw()
        if self.viadata:
            code=self.viadata['keys'][f'{position[0]},{position[1]}']
            self.key_info.set(f'Layer {self.viadata["layer"]+1} • key {position[0]},{position[1]} • current: {key_name(code)}')
            self.new_key.set(key_name(code) if code in KEYCODES else 'A')
        else: self.key_info.set('Read the layer before editing this key.')
        self.update_buttons()

    def apply_key(self):
        if self.busy or not self.viadata or self.selected_key is None: return
        choices={name:code for code,name in KEYCODES.items()}
        if self.new_key.get() not in choices: return
        row,col=self.selected_key;layer=self.viadata['layer']
        old=self.viadata['keys'][f'{row},{col}'];new=choices[self.new_key.get()]
        if old==new: self.status.set('That key already uses the chosen function.');return
        self.task('key',lambda:write_key(layer,row,col,old,new),'Applying only the selected key…')

    def undo_key(self):
        if self.busy or not self.last_key: return
        change=self.last_key.copy()
        self.task('undo',lambda:write_key(change['layer'],change['row'],change['col'],change['new'],change['old']),'Restoring the last changed key…')

    def refresh_catalog(self,catalog):
        self.native_effects=catalog['effects'];self.native_speeds=catalog['speeds']
        self.native_colors={name:bytes.fromhex(block) for name,block in catalog['colors'].items()}
        if hasattr(self,'effect_input'):
            self.effect_input.configure(values=['Keep current']+[f'Effect {n}' for n in self.native_effects])
            self.speed_input.configure(values=['Keep current']+[f'Level {n}' for n in self.native_speeds])
            self.native_color_input.configure(values=['Keep current','Custom color']+list(self.native_colors))

    def learn_light(self):
        self.task('light-learn',learn_native_lighting,'Reading the current state to add it to the catalog…')

    def pick_color(self):
        if self.busy: return
        color=ask_color(self.root,self.color)
        if color: self.choose_color(color)

    def choose_color(self,color):
        if self.busy: return
        self.color=color
        self.color_info.configure(text=f'Color: {color}',fg=color)
        if self.light_data and self.light_data['channel']=='native': self.native_color_choice.set('Custom color')

    def capture_light(self):
        before=getattr(self,'capture_before',None)
        self.task('light-capture',lambda:capture_lighting(fresh=before is None,baseline=before),'Reading settings to compare lighting…')

    def open_manual(self):
        import webbrowser
        if not webbrowser.open('https://epomaker.com/blogs/manuals/th80-pro-v2-manual'):
            messagebox.showinfo('Official manual','https://epomaker.com/blogs/manuals/th80-pro-v2-manual',parent=self.root)

    def apply_light(self):
        if self.busy or not self.light_data: return
        brightness=round(self.brightness.get());color=self.color
        channel=self.light_data['channel']
        effect=speed=color_preset=custom_color=None
        if channel=='native':
            if self.effect_choice.get()!='Keep current': effect=int(self.effect_choice.get().split()[-1])
            if self.speed_choice.get()!='Keep current': speed=int(self.speed_choice.get().split()[-1])
            if self.native_color_choice.get()=='Custom color': custom_color=color
            elif self.native_color_choice.get()!='Keep current': color_preset=self.native_color_choice.get()
        self.task('light',lambda:apply_lighting(brightness,color,channel,effect,speed,color_preset,custom_color),'Applying lighting…')

    def animate(self):
        if self.preview_frames:
            self.preview.configure(image=self.preview_frames[self.preview_index],text='')
            self.preview_index=(self.preview_index+1)%len(self.preview_frames)
        try: delay=max(60,min(65535,int(self.delay.get())))
        except ValueError: delay=100
        self.root.after(delay if len(self.preview_frames)>1 else 200,self.animate)

    def update_buttons(self):
        self.button.configure(state='disabled' if self.busy else 'normal')
        self.choose_button.configure(state='disabled' if self.busy else 'normal')
        self.send_button.configure(state='normal' if not self.busy and self.connected and self.media else 'disabled')
        for button in (self.clock_button,self.image_button):
            button.configure(state='normal' if not self.busy and self.connected else 'disabled')
        self.delay_input.configure(state='normal' if not self.busy and self.media and self.media.delay_ms else 'disabled')
        for button in (self.via_button,self.light_probe,self.light_capture,self.light_learn): button.configure(state='disabled' if self.busy else 'normal')
        self.layer_input.configure(state='readonly' if self.viadata and not self.busy else 'disabled')
        editable=not self.busy and self.viadata and self.selected_key is not None
        self.key_input.configure(state='readonly' if editable else 'disabled')
        self.apply_key_button.configure(state='normal' if editable else 'disabled')
        self.undo_button.configure(state='normal' if self.last_key and self.viadata and not self.busy else 'disabled')
        lighting=self.light_data
        enabled=lighting and not self.busy
        self.brightness_input.configure(state='normal' if enabled else 'disabled')
        self.light_apply.configure(state='normal' if enabled else 'disabled')
        native=enabled and lighting['channel']=='native'
        for combo in (self.effect_input,self.speed_input,self.native_color_input): combo.configure(state='readonly' if native else 'disabled')
        for button in self.color_buttons+[self.color_picker]: button.configure(state='normal' if enabled and (native or 'hue' in lighting) else 'disabled')
        from ui import C
        self.connection_label.configure(text='●  USB connected' if self.connected else '●  Waiting for USB',fg=C['blue'] if self.connected else C['muted'])

    def change_screen(self,mode):
        if self.busy or not self.connected: return
        self.busy=True;self.update_buttons()
        self.bar.configure(mode='indeterminate');self.bar.start(12)
        self.status.set('Setting the clock…' if mode=='clock' else 'Returning to the saved image…')
        def worker():
            try: result=set_screen(mode)
            except Exception as exc: result={'status':'error','message':str(exc)}
            self.events.put(('screen',result))
        threading.Thread(target=worker,daemon=True).start()

    def close(self):
        if self.busy:
            messagebox.showinfo('Operation in progress','Wait for the operation to finish before closing.',parent=self.root)
            return
        self.root.destroy()

    def choose(self):
        path=filedialog.askopenfilename(parent=self.root,title='Choose a photo or GIF',filetypes=[('Images','*.png *.jpg *.jpeg *.webp *.bmp *.gif'),('All files','*.*')])
        if not path: return
        try:
            media=load_media(path)
            previews=[ImageTk.PhotoImage(image.resize((320,180),Image.Resampling.NEAREST)) for image in media.frames]
            self.media=media;self.preview_frames=previews;self.preview_index=0
            self.preview.configure(image=previews[0],text='',width=0,height=0)
            self.delay.set(str(media.delay_ms or 100))
            if media.delay_ms:
                note=f'GIF: {len(media.frames)} frames, {media.delay_ms} ms per frame.'
                if media.original_count>18: note+=f' Reduced from {media.original_count} frames, sampling the full loop.'
                if media.variable_timing: note+=' Variable frame timings were fitted to one fixed interval.'
            else: note='Still photo • 240 × 135 pixels.'
            self.media_info.set(note)
            self.update_buttons()
        except Exception as exc:
            messagebox.showerror('Couldn\'t open the photo',str(exc),parent=self.root)

    def send(self):
        if self.busy or not self.connected or self.media is None: return
        delay=None
        if self.media.delay_ms:
            try:
                delay=int(self.delay.get())
                if not 60<=delay<=65535: raise ValueError()
            except ValueError:
                messagebox.showerror('Invalid interval','Use a whole-number interval from 60 to 65535 ms.',parent=self.root);return
        if not messagebox.askokcancel('Replace images','Send this photo or animation to both of the keyboard\'s image slots?\n\nBoth current images will be replaced. Keep the cable connected until it finishes.',parent=self.root): return
        self.busy=True
        self.update_buttons()
        self.bar.configure(mode='determinate',value=0)
        self.status.set('Reading the configuration and preparing the upload…')
        media=self.media
        def worker():
            try:
                frames=[encode_frame(image) for image in media.frames]
                result=send_photo(frames if delay else frames[0],lambda value:self.events.put(('percent',value)),delay)
            except Exception as exc: result={'status':'error','message':str(exc)}
            self.events.put(('sent',result))
        threading.Thread(target=worker,daemon=True).start()

    def start(self):
        if self.busy: return
        self.busy=True
        self.update_buttons()
        self.bar.configure(mode='indeterminate')
        self.bar.start(12)
        threading.Thread(target=self.worker,daemon=True).start()

    def worker(self):
        try:
            result=probe(lambda text:self.events.put(('progress',text)))
        except Exception as exc:
            result={'status':'error','message':str(exc)}
        self.events.put(('done',result))

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress': self.status.set(value)
                elif kind=='percent':
                    self.bar.configure(value=value)
                    self.status.set(f'Uploading image: {value:.0f}% — keep the cable connected.')
                else:
                    self.status.set(value['message'])
                    self.bar.stop()
                    self.bar.configure(mode='determinate',value=0 if value['status']=='error' else 100)
                    if kind=='done': self.connected=value['status']=='query_confirmed'
                    if kind in ('sent','screen') and value['status']=='error': self.connected=False
                    if kind=='via':
                        if value['status']=='via_confirmed':
                            self.viadata=value
                            self.layer_input.configure(values=[f'Layer {i+1}' for i in range(value['layers'])])
                            self.keyboard_view.set_codes(value['keys'])
                            self.hero_keyboard.set_codes(value['keys'])
                            lighting=value.get('lighting')
                            self.light_data=lighting
                            if lighting:
                                self.brightness_input.configure(to=lighting.get('max_brightness',255),resolution=1)
                                self.brightness.set(lighting['brightness'])
                                self.light_info.set('VIA control detected. Set the brightness and apply.')
                                if 'hue' in lighting:
                                    import colorsys
                                    rgb=colorsys.hsv_to_rgb(lighting['hue']/255,lighting['saturation']/255,1)
                                    self.color='#'+''.join(f'{round(c*255):02x}' for c in rgb)
                                    self.color_info.configure(text=f'Current color: {self.color}',fg=self.color)
                            else:
                                self.light_info.set('This firmware doesn\'t offer lighting on the standard VIA channels. The controls stay disabled; use the keyboard\'s lighting shortcuts.')
                            if self.selected_key: self.select_key(self.selected_key)
                        else:
                            self.viadata=None
                            self.light_info.set(value['message'])
                    if kind=='light-capture':
                        self.light_info.set(value['message'])
                        if value['status']=='snapshot_saved':
                            self.capture_before=value
                            self.light_capture.configure(text='2 · Capture after')
                        elif value['status']=='comparison_saved':
                            self.capture_before=None
                            self.light_capture.configure(text='1 · Capture before')
                    if kind=='light-learn':
                        self.light_info.set(value['message'])
                        if value['status']=='catalog_saved': self.refresh_catalog(value['catalog'])
                    if kind=='light-probe':
                        lighting=value.get('lighting')
                        self.light_data=lighting
                        self.light_info.set(value['message'])
                        if lighting:
                            self.brightness_input.configure(to=lighting.get('max_brightness',255),resolution=1)
                            self.brightness.set(lighting['brightness'])
                            if 'hue' in lighting:
                                import colorsys
                                rgb=colorsys.hsv_to_rgb(lighting['hue']/255,lighting['saturation']/255,1)
                                self.color='#'+''.join(f'{round(c*255):02x}' for c in rgb)
                                self.color_info.configure(text=f'Current color: {self.color}',fg=self.color)
                    if kind in ('key','undo') and value['status']=='key_acknowledged':
                        self.last_key=value if kind=='key' else None
                        if self.viadata and self.viadata['layer']==value['layer']:
                            self.viadata['keys'][f'{value["row"]},{value["col"]}']=value['new']
                            self.keyboard_view.set_codes(self.viadata['keys']);self.hero_keyboard.set_codes(self.viadata['keys'])
                        if kind=='undo':
                            (ROOT/'last-key.json').unlink(missing_ok=True)
                            self.status.set('Last key restored. Test it on the keyboard.')
                    self.busy=False
                    self.update_buttons()
                    if kind in ('via','key','undo') and self.viadata and self.selected_key: self.select_key(self.selected_key)
        except queue.Empty: pass
        self.root.after(100,self.poll)

    def run(self): self.root.mainloop()

if __name__=='__main__':
    if '--probe' in sys.argv:
        print(json.dumps(probe(print),ensure_ascii=False,indent=2))
    elif '--check-ui' in sys.argv:
        app=App();app.root.update();app.root.destroy();print('UI initialized successfully')
    else: App().run()
