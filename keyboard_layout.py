"""Subset of KLE geometry present in the user's VIA definition."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Key:
    row:int
    col:int
    x:float
    y:float
    width:float=1
    height:float=1

def parse_layout(rows,matrix_rows,matrix_cols):
    keys=[];y=0
    for line in rows:
        if not isinstance(line,list): continue
        x=0;w=h=1
        for item in line:
            if isinstance(item,dict):
                x+=item.get('x',0);y+=item.get('y',0)
                w=item.get('w',w);h=item.get('h',h)
            elif isinstance(item,str):
                coordinate=item.split('\n')[0]
                r,c=map(int,coordinate.split(','))
                if not 0<=r<matrix_rows or not 0<=c<matrix_cols: raise ValueError('Key is outside the VIA matrix.')
                keys.append(Key(r,c,x,y,w,h));x+=w;w=h=1
        y+=1
    if len({(key.row,key.col) for key in keys})!=len(keys): raise ValueError('Duplicate VIA coordinates.')
    return keys
