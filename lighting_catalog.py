"""Catalog of native states actually read from this keyboard, not guessed IDs."""
import json
from pathlib import Path

DEVICE='320f:5055:TH80 Pro V2'
DEFAULT_COLORS={'Yellow-green':'0068ff000b','Green':'0035ff000c','Rainbow':'ffff010000'}

def load_catalog(root):
    path=Path(root)/'lighting-catalog.json'
    if not path.exists():
        return {'version':1,'device':DEVICE,'effects':[1,3,13,16],'speeds':[2,4],'colors':dict(DEFAULT_COLORS)}
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if data['version']!=1 or data['device']!=DEVICE: raise ValueError()
        for key in ('effects','speeds'):
            if not isinstance(data[key],list) or any(type(n) is not int or not 0<=n<=255 for n in data[key]): raise ValueError()
        if not isinstance(data['colors'],dict): raise ValueError()
        for name,block in data['colors'].items():
            if not isinstance(name,str) or not 1<=len(name)<=80 or not isinstance(block,str) or len(bytes.fromhex(block))!=5: raise ValueError()
        return data
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError('Lighting catalog is invalid or belongs to another device.') from exc

def _observe(catalog,config):
    if len(config)!=48 or config[2]>9: raise ValueError('Invalid native configuration.')
    for key,offset in (('effects',1),('speeds',3)):
        catalog[key]=sorted(set(catalog[key]+[config[offset]]))
    block=config[5:10].hex()
    for name,value in catalog['colors'].items():
        if value==block: return name
    rgb='#'+config[6:9].hex().upper()
    name=f'{rgb} · C{config[9]}' if config[5]!=255 else f'Rainbow {len(catalog["colors"])+1}'
    original=name;number=2
    while name in catalog['colors']:
        name=f'{original} ({number})';number+=1
    catalog['colors'][name]=block
    return name

def _save(root,catalog):
    path=Path(root)/'lighting-catalog.json'
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)

def observe_configuration(root,config):
    catalog=load_catalog(root);name=_observe(catalog,config)
    _save(root,catalog)
    return catalog,name

def import_captures(root):
    catalog=load_catalog(root)
    for path in sorted((Path(root)/'logs-lighting').glob('*.json')):
        try:
            capture=json.loads(path.read_text(encoding='utf-8'))
            if capture.get('status') not in ('snapshot_saved','comparison_saved'): continue
            _observe(catalog,bytes.fromhex(capture['configuration']))
        except (OSError,KeyError,TypeError,ValueError): continue
    _save(root,catalog)
    return catalog
