"""HSV wheel, HEX input and native RGB mapping; no USB calls in the picker."""
import colorsys
import math
import re

def normalize_hex(value):
    value=value.strip().removeprefix('#')
    if not re.fullmatch('[0-9a-fA-F]{6}',value): raise ValueError('Use six HEX digits, such as #0066FF.')
    return '#'+value.upper()

def wheel_hex(x,y,radius,value=1):
    hue=(math.atan2(-y,x)/(2*math.pi))%1
    saturation=min(1,math.hypot(x,y)/radius)
    rgb=colorsys.hsv_to_rgb(hue,saturation,max(0,min(1,value)))
    return '#'+''.join(f'{round(channel*255):02X}' for channel in rgb)

def rgb_configuration(original,color):
    if len(original)!=48: raise ValueError('Incomplete configuration.')
    rgb=bytes.fromhex(normalize_hex(color)[1:])
    result=bytearray(original);result[5]=0;result[6:9]=rgb
    return bytes(result)

def render_wheel(size=260):
    from PIL import Image
    image=Image.new('RGBA',(size,size));pixels=image.load();radius=(size-2)/2
    for y in range(size):
        for x in range(size):
            dx=x-size/2;dy=y-size/2
            if math.hypot(dx,dy)<=radius:
                pixels[x,y]=tuple(bytes.fromhex(wheel_hex(dx,dy,radius)[1:]))+(255,)
    return image

class ColorPicker:
    def __init__(self,parent,initial):
        import tkinter as tk
        from tkinter import ttk
        from PIL import ImageTk
        from ui import C
        self.result=None
        self.window=tk.Toplevel(parent);self.window.title('Choose color · TH80 Studio')
        self.window.configure(bg=C['panel']);self.window.resizable(False,False);self.window.transient(parent)
        initial=normalize_hex(initial)
        self.h,self.s,v=colorsys.rgb_to_hsv(*(channel/255 for channel in bytes.fromhex(initial[1:])))
        self.value=tk.DoubleVar(value=v*100);self.hex=tk.StringVar(value=initial)
        tk.Label(self.window,text='Choose your color',bg=C['panel'],fg=C['text'],font=('Bahnschrift',19)).pack(pady=(18,4))
        tk.Label(self.window,text='Drag on the wheel or type a HEX code.',bg=C['panel'],fg=C['muted'],font=('Segoe UI',10)).pack(padx=24,pady=(0,14))
        self.canvas=tk.Canvas(self.window,width=280,height=280,bg=C['panel'],highlightthickness=0)
        self.canvas.pack();self.image=ImageTk.PhotoImage(render_wheel(),master=self.window)
        self.canvas.create_image(140,140,image=self.image)
        self.marker=self.canvas.create_oval(0,0,12,12,outline='white',width=3)
        self.canvas.bind('<Button-1>',self.select);self.canvas.bind('<B1-Motion>',self.select)
        tk.Label(self.window,text='Color lightness',bg=C['panel'],fg=C['muted']).pack(pady=(8,0))
        tk.Scale(self.window,from_=0,to=100,orient='horizontal',variable=self.value,command=lambda _:self.refresh(),bg=C['panel'],fg=C['text'],highlightthickness=0,length=280).pack()
        row=tk.Frame(self.window,bg=C['panel']);row.pack(pady=12)
        self.preview=tk.Label(row,width=4,height=2,bg=initial);self.preview.pack(side='left',padx=(0,12))
        entry=ttk.Entry(row,textvariable=self.hex,width=12,font=('Consolas',13));entry.pack(side='left');entry.bind('<Return>',lambda _:self.from_hex())
        ttk.Button(row,text='Read HEX',command=self.from_hex).pack(side='left',padx=(8,0))
        actions=tk.Frame(self.window,bg=C['panel']);actions.pack(pady=(0,20))
        ttk.Button(actions,text='Cancel',command=self.window.destroy).pack(side='left',padx=6)
        ttk.Button(actions,text='Use color',style='Accent.TButton',command=self.accept).pack(side='left',padx=6)
        self.refresh();self.window.grab_set()

    def select(self,event):
        x=event.x-140;y=event.y-140
        self.h=(math.atan2(-y,x)/(2*math.pi))%1;self.s=min(1,math.hypot(x,y)/129)
        self.refresh()

    def refresh(self):
        if not hasattr(self,'preview'): return
        rgb=colorsys.hsv_to_rgb(self.h,self.s,self.value.get()/100)
        color='#'+''.join(f'{round(c*255):02X}' for c in rgb)
        self.hex.set(color);self.preview.configure(bg=color)
        x=140+129*self.s*math.cos(self.h*2*math.pi);y=140-129*self.s*math.sin(self.h*2*math.pi)
        self.canvas.coords(self.marker,x-6,y-6,x+6,y+6)

    def from_hex(self):
        from tkinter import messagebox
        try: color=normalize_hex(self.hex.get())
        except ValueError as exc:
            messagebox.showerror('HEX color',str(exc),parent=self.window);return False
        self.h,self.s,v=colorsys.rgb_to_hsv(*(channel/255 for channel in bytes.fromhex(color[1:])))
        self.value.set(v*100);self.refresh();return True

    def accept(self):
        if self.from_hex(): self.result=self.hex.get();self.window.destroy()

def ask_color(parent,initial):
    picker=ColorPicker(parent,initial);parent.wait_window(picker.window)
    return picker.result
