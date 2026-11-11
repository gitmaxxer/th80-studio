"""Native desktop frontend. Graphite shell, blue keycaps and live LCD preview."""
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from via import KEYCODES, key_name

C={'base':'#202b3b','side':'#17212e','panel':'#29374b','edge':'#41526b',
   'text':'#ecf2f8','muted':'#a8b8ce','blue':'#60caff','action':'#357ef2'}

def label(parent,text='',size=11,color=None,bg=None,weight='normal',**kwargs):
    return tk.Label(parent,text=text,fg=color or C['text'],bg=bg or parent.cget('bg'),
                    font=('Bahnschrift' if size>=20 else 'Segoe UI',size,weight),anchor='w',**kwargs)

def rounded(canvas,x1,y1,x2,y2,r=8,**kwargs):
    points=[x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,
            x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
    return canvas.create_polygon(points,smooth=True,**kwargs)

class KeyboardCanvas(tk.Canvas):
    def __init__(self,parent,layout,callback=None,height=235):
        super().__init__(parent,bg=parent.cget('bg'),highlightthickness=0,height=height)
        self.layout=layout;self.callback=callback;self.codes={};self.selected=None
        self.bind('<Configure>',lambda event:self.draw())
    def draw(self):
        self.delete('all')
        width=max(self.winfo_width(),300);height=max(self.winfo_height(),180)
        units=max(k.x+k.width for k in self.layout)
        rows=max(k.y+k.height for k in self.layout)
        unit=min((width-36)/units,(height-32)/rows)
        left=(width-unit*units)/2;top=12
        rounded(self,left-10,top-10,left+unit*units+10,top+unit*rows+10,12,fill='#111b29',outline=C['edge'],width=2)
        short={'Backspace':'Bksp','Space':'','Left Windows':'Win','Right Windows':'Win',
               'Left Ctrl':'Ctrl','Right Ctrl':'Ctrl','Left Shift':'Shift','Right Shift':'Shift',
               'Left Alt':'Alt','Right Alt':'Alt','Caps Lock':'Caps','Page Up':'PgUp','Page Down':'PgDn',
               'Left':'←','Right':'→','Up':'↑','Down':'↓','Transparent':'▽','Disabled':'×'}
        for key in self.layout:
            pos=(key.row,key.col);tag=f'key-{key.row}-{key.col}'
            x=left+key.x*unit;y=top+key.y*unit
            selected=pos==self.selected
            fill=C['action'] if selected else ('#7ca4d6' if key.row==0 else '#e0e5ec')
            rounded(self,x+2,y+2,x+key.width*unit-2,y+key.height*unit-2,5,fill=fill,outline=C['blue'] if selected else '#101e31',width=1,tags=(tag,))
            code=self.codes.get(f'{key.row},{key.col}')
            name=key_name(code) if code is not None else ('Esc' if pos==(0,0) else (f'F{key.col}' if key.row==0 else ''))
            name=short.get(name,name)
            if name.startswith('Special'): name='Fn / spec.'
            self.create_text(x+key.width*unit/2,y+key.height*unit/2,text=name,fill='#ffffff' if selected else '#20304a',font=('Segoe UI',max(7,int(unit/5))),tags=(tag,))
            if self.callback:
                self.tag_bind(tag,'<Button-1>',lambda event,p=pos:self.callback(p))
        if self.callback: self.configure(cursor='hand2')
    def set_codes(self,codes): self.codes=codes;self.draw()

def build_ui(app):
    root=app.root;root.configure(bg=C['base'])
    style=ttk.Style();style.theme_use('clam')
    style.configure('TButton',background=C['panel'],foreground=C['text'],bordercolor=C['edge'],lightcolor=C['edge'],darkcolor=C['edge'],font=('Segoe UI',10),padding=(15,9),focuscolor=C['blue'])
    style.map('TButton',background=[('active','#354965'),('disabled','#263244')],foreground=[('disabled','#6f839c')])
    style.configure('Accent.TButton',background=C['action'],bordercolor=C['action'],font=('Segoe UI',10,'bold'))
    style.map('Accent.TButton',background=[('active','#4b95ff'),('disabled','#263244')])
    style.configure('TCombobox',fieldbackground=C['side'],background=C['panel'],foreground=C['text'],arrowcolor=C['text'],bordercolor=C['edge'],padding=7)
    style.map('TCombobox',fieldbackground=[('readonly',C['side'])],foreground=[('readonly',C['text'])])
    style.configure('TSpinbox',fieldbackground=C['side'],background=C['panel'],foreground=C['text'],arrowcolor=C['text'],bordercolor=C['edge'],padding=5)
    style.configure('Horizontal.TProgressbar',background=C['blue'],troughcolor=C['side'],bordercolor=C['side'],lightcolor=C['blue'],darkcolor=C['blue'])
    root.option_add('*TCombobox*Listbox.background',C['side']);root.option_add('*TCombobox*Listbox.foreground',C['text'])
    sidebar=tk.Frame(root,bg=C['side'],width=176);sidebar.pack(side='left',fill='y');sidebar.pack_propagate(False)
    label(sidebar,'TH80\nStudio',size=29,weight='bold',color=C['blue']).pack(anchor='w',padx=22,pady=(28,4))
    label(sidebar,'Your keyboard. Your style.',size=9,color=C['muted']).pack(anchor='w',padx=22,pady=(0,34))
    app.nav_buttons={};app.pages={}
    for key,name in [('images','Screen & GIF'),('clock','Clock'),('keys','Keys'),('lighting','Lighting'),('manual','Manual')]:
        button=tk.Button(sidebar,text=name,anchor='w',bg=C['side'],fg=C['muted'],activebackground=C['panel'],activeforeground=C['text'],relief='flat',borderwidth=0,padx=18,pady=12,font=('Segoe UI',11),command=lambda p=key:app.show_page(p),takefocus=True)
        button.pack(fill='x',padx=10,pady=3);app.nav_buttons[key]=button
    label(sidebar,'EPOMAKER\nTH80 Pro V2\nUSB connection',size=10,color=C['muted'],justify='left').pack(side='bottom',anchor='w',padx=22,pady=25)
    shell=tk.Frame(root,bg=C['base']);shell.pack(side='left',fill='both',expand=True)
    header=tk.Frame(shell,bg=C['base']);header.pack(fill='x',padx=28,pady=(26,18))
    app.heading=tk.StringVar(value='Screen & GIF')
    label(header,size=25,weight='bold',textvariable=app.heading).pack(side='left')
    app.connection_label=label(header,'●  Waiting for USB',size=10,color=C['muted']);app.connection_label.pack(side='right',padx=(12,0))
    app.button=ttk.Button(header,text='Connect keyboard',command=app.start);app.button.pack(side='right')
    body=tk.Frame(shell,bg=C['base']);body.pack(fill='both',expand=True,padx=28)
    for key in app.nav_buttons:
        app.pages[key]=tk.Frame(body,bg=C['base'])
    images=app.pages['images']
    label(images,'A tiny screen with your personality.',size=11,color=C['muted']).pack(anchor='w',pady=(0,18))
    hero=tk.Frame(images,bg=C['panel']);hero.pack(fill='x')
    display=tk.Frame(hero,bg=C['panel']);display.pack(side='left',padx=22,pady=22)
    screen=tk.Frame(display,bg='#0b1522',highlightbackground=C['edge'],highlightthickness=2)
    screen.pack()
    app.preview=tk.Label(screen,text='Choose a photo or GIF\nto preview it on the screen.',width=40,height=10,bg='#0b1522',fg=C['muted'],font=('Segoe UI',10),compound='center')
    app.preview.pack(padx=10,pady=10)
    label(display,'240 × 135 pixels • upload preview',size=9,color=C['muted']).pack(anchor='w',pady=(10,0))
    controls=tk.Frame(hero,bg=C['panel']);controls.pack(side='left',fill='both',expand=True,padx=(0,20),pady=22)
    label(controls,'Photo or animation',size=18,weight='bold').pack(anchor='w',pady=(0,12))
    app.choose_button=ttk.Button(controls,text='Choose photo / GIF',command=app.choose);app.choose_button.pack(fill='x',pady=(0,8))
    app.send_button=ttk.Button(controls,text='Send to keyboard',style='Accent.TButton',state='disabled',command=app.send);app.send_button.pack(fill='x',pady=(0,14))
    label(controls,'Animation interval (ms)',size=9,color=C['muted']).pack(anchor='w')
    app.delay=tk.StringVar(value='100')
    app.delay_input=ttk.Spinbox(controls,from_=60,to=65535,increment=10,width=9,textvariable=app.delay,state='disabled');app.delay_input.pack(anchor='w',pady=6)
    app.media_info=tk.StringVar(value='GIFs are fitted to at most 18 frames per slot.')
    label(images,textvariable=app.media_info,size=10,color=C['muted'],wraplength=740).pack(anchor='w',pady=(12,2))
    app.hero_keyboard=KeyboardCanvas(images,app.layout,height=225);app.hero_keyboard.pack(fill='x',pady=(5,0))
    label(images,'Uploading replaces both saved images. Keep the cable connected until it finishes.',size=9,color=C['muted'],wraplength=740).pack(anchor='w')
    clock=app.pages['clock']
    label(clock,'Keep track of time without leaving the keyboard.',color=C['muted']).pack(anchor='w',pady=(0,22))
    clock_panel=tk.Frame(clock,bg=C['panel'],padx=28,pady=24);clock_panel.pack(fill='x')
    app.clock_preview=label(clock_panel,datetime.now().strftime('%H:%M'),size=68,color=C['blue']);app.clock_preview.pack(anchor='w')
    app.date_preview=label(clock_panel,datetime.now().strftime('%d / %m / %Y'),size=13,color=C['muted']);app.date_preview.pack(anchor='w',pady=(0,20))
    app.clock_button=ttk.Button(clock_panel,text='Set time and show clock',style='Accent.TButton',state='disabled',command=lambda:app.change_screen('clock'));app.clock_button.pack(anchor='w',pady=(0,10))
    app.image_button=ttk.Button(clock_panel,text='Back to saved image',state='disabled',command=lambda:app.change_screen('image'));app.image_button.pack(anchor='w')
    label(clock,'The preview uses your computer\'s time. The keyboard is synced when you click; your images are kept.',color=C['muted'],wraplength=720).pack(anchor='w',pady=20)
    keys=app.pages['keys']
    label(keys,'Click the keyboard to change a key.',color=C['muted']).pack(anchor='w',pady=(0,16))
    row=tk.Frame(keys,bg=C['base']);row.pack(fill='x')
    app.layer=tk.StringVar(value='Layer 1')
    app.layer_input=ttk.Combobox(row,textvariable=app.layer,values=['Layer 1'],width=14,state='disabled');app.layer_input.pack(side='left')
    app.layer_input.bind('<<ComboboxSelected>>',lambda event:app.load_keys())
    app.via_button=ttk.Button(row,text='Read keys and lighting',command=app.load_keys);app.via_button.pack(side='left',padx=12)
    app.keyboard_view=KeyboardCanvas(keys,app.layout,app.select_key,height=275);app.keyboard_view.pack(fill='x',pady=16)
    edit=tk.Frame(keys,bg=C['panel'],padx=20,pady=18);edit.pack(fill='x')
    app.key_info=tk.StringVar(value='Read the layer to see the current functions.')
    label(edit,textvariable=app.key_info,size=12).pack(anchor='w',pady=(0,12))
    action=tk.Frame(edit,bg=C['panel']);action.pack(fill='x')
    app.new_key=tk.StringVar(value='A')
    app.key_input=ttk.Combobox(action,textvariable=app.new_key,values=list(KEYCODES.values()),state='disabled',width=21);app.key_input.pack(side='left')
    app.apply_key_button=ttk.Button(action,text='Apply key',style='Accent.TButton',state='disabled',command=app.apply_key);app.apply_key_button.pack(side='left',padx=10)
    app.undo_button=ttk.Button(edit,text='Undo last change',state='disabled',command=app.undo_key);app.undo_button.pack(anchor='w',pady=(12,0))
    label(keys,'The layout comes from your VIA JSON. Only the selected key changes; the previous value is saved for undo.',color=C['muted'],wraplength=730,size=9).pack(anchor='w',pady=16)
    lighting_page=app.pages['lighting']
    light_scroll=ttk.Scrollbar(lighting_page);light_scroll.pack(side='right',fill='y')
    light_canvas=tk.Canvas(lighting_page,bg=C['base'],highlightthickness=0,yscrollcommand=light_scroll.set)
    light_canvas.pack(side='left',fill='both',expand=True);light_scroll.configure(command=light_canvas.yview)
    lighting=tk.Frame(light_canvas,bg=C['base'])
    light_window=light_canvas.create_window((0,0),window=lighting,anchor='nw')
    lighting.bind('<Configure>',lambda event:light_canvas.configure(scrollregion=light_canvas.bbox('all')))
    light_canvas.bind('<Configure>',lambda event:light_canvas.itemconfigure(light_window,width=event.width))
    light_canvas.bind('<MouseWheel>',lambda event:light_canvas.yview_scroll(-int(event.delta/120),'units'))
    label(lighting,'Whatever lighting the firmware exposes.',color=C['muted']).pack(anchor='w',pady=(0,10))
    app.light_info=tk.StringVar(value='Click Check lighting to query the available VIA controls.')
    label(lighting,textvariable=app.light_info,wraplength=700).pack(anchor='w',pady=(0,10))
    app.light_probe=ttk.Button(lighting,text='Check lighting',command=app.load_light);app.light_probe.pack(anchor='w',pady=(0,10))
    app.light_learn=ttk.Button(lighting,text='Add current state',command=app.learn_light);app.light_learn.pack(anchor='w',pady=(0,10))
    label(lighting,'Change the effect or speed with the keyboard shortcuts, then add the state to grow the lists.',color=C['muted'],wraplength=720,size=9).pack(anchor='w',pady=(0,10))
    app.light_capture=ttk.Button(lighting,text='1 · Capture before',command=app.capture_light);app.light_capture.pack(anchor='w',pady=(0,10))
    label(lighting,'Capture before, change just one setting, then capture after. Each pair starts a new comparison. Instructions are in the Manual tab.',color=C['muted'],wraplength=720,size=9).pack(anchor='w',pady=(0,14))
    light_panel=tk.Frame(lighting,bg=C['panel'],padx=24,pady=16);light_panel.pack(fill='x')
    label(light_panel,'Brightness',size=17).pack(anchor='w')
    app.brightness=tk.DoubleVar(value=128)
    app.brightness_input=tk.Scale(light_panel,from_=0,to=255,orient='horizontal',variable=app.brightness,bg=C['panel'],fg=C['text'],troughcolor=C['side'],highlightthickness=0,activebackground=C['blue'],state='disabled');app.brightness_input.pack(fill='x',pady=(6,10))
    options=tk.Frame(light_panel,bg=C['panel']);options.pack(fill='x',pady=(0,10))
    label(options,'Effect',size=10).grid(row=0,column=0,sticky='w',pady=(0,5))
    label(options,'Speed',size=10).grid(row=0,column=1,sticky='w',padx=(18,0),pady=(0,5))
    app.effect_choice=tk.StringVar(value='Keep current');app.speed_choice=tk.StringVar(value='Keep current')
    app.effect_input=ttk.Combobox(options,textvariable=app.effect_choice,values=['Keep current']+[f'Effect {n}' for n in app.native_effects],width=18,state='disabled');app.effect_input.grid(row=1,column=0,sticky='w')
    app.speed_input=ttk.Combobox(options,textvariable=app.speed_choice,values=['Keep current']+[f'Level {n}' for n in app.native_speeds],width=18,state='disabled');app.speed_input.grid(row=1,column=1,sticky='w',padx=(18,0))
    label(options,'Color',size=10).grid(row=2,column=0,sticky='w',pady=(10,5))
    app.native_color_choice=tk.StringVar(value='Keep current')
    app.native_color_input=ttk.Combobox(options,textvariable=app.native_color_choice,values=['Keep current','Custom color']+list(app.native_colors),width=30,state='disabled');app.native_color_input.grid(row=3,column=0,columnspan=2,sticky='w')
    palette=tk.Frame(light_panel,bg=C['panel']);palette.pack(fill='x',pady=(0,10))
    app.color='#60caff';app.color_buttons=[]
    for color in ['#60caff','#9678fa','#f478a3','#f4c765','#ffffff']:
        button=tk.Button(palette,text='●',font=('Segoe UI',20),bg=C['panel'],fg=color,activebackground=C['edge'],activeforeground=color,relief='flat',width=3,command=lambda c=color:app.choose_color(c),state='disabled')
        button.pack(side='left',padx=(0,8));app.color_buttons.append(button)
    app.color_info=label(light_panel,'Color: blue',color=C['muted'],size=10);app.color_info.pack(anchor='w',pady=(0,8))
    app.color_picker=ttk.Button(light_panel,text='Color wheel / HEX…',command=app.pick_color,state='disabled');app.color_picker.pack(anchor='w',pady=(0,12))
    app.light_apply=ttk.Button(light_panel,text='Apply lighting',style='Accent.TButton',state='disabled',command=app.apply_light);app.light_apply.pack(anchor='w')
    label(lighting,'The color depends on the active effect. Controls are enabled only after the keyboard replies.',color=C['muted'],wraplength=720,size=9).pack(anchor='w',pady=18)
    manual=app.pages['manual']
    label(manual,'Your guide to the TH80 Pro V2.',color=C['muted']).pack(anchor='w',pady=(0,14))
    ttk.Button(manual,text='Open official manual',command=app.open_manual).pack(anchor='w',pady=(0,16))
    guide=tk.Frame(manual,bg=C['panel']);guide.pack(fill='both',expand=True)
    scrollbar=ttk.Scrollbar(guide);scrollbar.pack(side='right',fill='y')
    text=tk.Text(guide,bg=C['panel'],fg=C['text'],font=('Segoe UI',11),wrap='word',relief='flat',borderwidth=0,padx=22,pady=20,yscrollcommand=scrollbar.set,height=12)
    text.pack(fill='both',expand=True);scrollbar.configure(command=text.yview)
    text.tag_configure('heading',font=('Bahnschrift',16),foreground=C['blue'],spacing1=16,spacing3=10)
    text.tag_configure('body',spacing3=12)
    from manual import SECTIONS
    for title,body in SECTIONS:
        text.insert('end',title+'\n','heading');text.insert('end',body+'\n\n','body')
    text.configure(state='disabled')
    footer=tk.Frame(shell,bg=C['side'],padx=24,pady=13);footer.pack(fill='x',side='bottom',pady=(18,0))
    app.status=tk.StringVar(value='Connect the keyboard over USB to start.')
    label(footer,textvariable=app.status,size=10,wraplength=800).pack(anchor='w',pady=(0,8))
    app.bar=ttk.Progressbar(footer,mode='determinate',value=0);app.bar.pack(fill='x')
    app.show_page('images')
