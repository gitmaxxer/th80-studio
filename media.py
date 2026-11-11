"""Decode composed GIF frames and sample their timeline for a fixed-delay LCD."""
from dataclasses import dataclass
from bisect import bisect_right
from PIL import Image, ImageOps

@dataclass
class Media:
    frames: list
    delay_ms: int | None
    original_count: int
    variable_timing: bool=False

def fit_frame(source):
    image=ImageOps.exif_transpose(source).convert('RGBA')
    background=Image.new('RGBA',image.size,'black')
    background.alpha_composite(image)
    return ImageOps.fit(background.convert('RGB'),(240,135),method=Image.Resampling.LANCZOS)

def load_media(path):
    with Image.open(path) as source:
        # Animated files other than GIF use their first frame in this version.
        count=getattr(source,'n_frames',1) if source.format=='GIF' else 1
        if count>1000: raise ValueError('GIF too long. Use a file with at most 1000 frames.')
        if count==1: return Media([fit_frame(source)],None,1)
        ends=[];durations=[];total=0
        for index in range(count):
            source.seek(index)
            duration=max(10,int(source.info.get('duration',100) or 100))
            durations.append(duration);total+=duration;ends.append(total)
        output_count=min(count,18)
        delay=min(65535,max(60,round(total/output_count)))
        indices=[min(count-1,bisect_right(ends,i*total/output_count)) for i in range(output_count)]
        decoded={}
        for index in sorted(set(indices)):
            source.seek(index)
            decoded[index]=fit_frame(source)
        return Media([decoded[index].copy() for index in indices],delay,count,len(set(durations))>1)
