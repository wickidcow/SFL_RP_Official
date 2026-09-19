from __future__ import annotations
from pathlib import Path
import argparse, base64, json, shutil, tempfile, zipfile

VANILLA_MODEL_TEMPLATES = {
    'item/generated','item/handheld','item/bow','item/crossbow','item/handheld_rod',
    'block/block','block/cube','block/cube_all','block/cube_bottom_top','block/cube_column',
    'block/orientable','block/slab','block/stairs','block/thin_block','block/cube_top',
}
TRANSPARENT_ALIAS_TEXTURES = {
    ('_minecraft','item/empty'),
    ('_minecraft','item/base/blank'),
    ('_minecraft','item/iamissing'),
    ('_b_minecraft','item/empty'),
    ('_b_minecraft','item/base/blank'),
    ('_b_minecraft','item/iamissing'),
}
TRANSPARENT_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAEklEQVR4nGNgGAWjYBSMAggAAAQQAAFVN1rQAAAAAElFTkSuQmCC'
)

def active_dirs(root: Path):
    names = [
        '', 'ia_overlay_1_21_2_plus', 'ia_overlay_1_21_4_plus',
        'ia_overlay_1_21_6_plus', 'ia_overlay_modern_atlas',
        'ia_overlay_26_1_plus', 'albion_26_3'
    ]
    return [root / n if n else root for n in names if (root / n if n else root).exists()]

def build_effective(root: Path):
    eff = {}
    for d in active_dirs(root):
        ad = d/'assets'
        if not ad.exists():
            continue
        for p in ad.rglob('*'):
            if p.is_file():
                eff[p.relative_to(d).as_posix()] = p
    return eff

def exists_texture(eff, ns, path):
    return f'assets/{ns}/textures/{path}.png' in eff

def exists_model(eff, ns, path):
    if ns == 'minecraft':
        return True
    return f'assets/{ns}/models/{path}.json' in eff

def canonical_alias(ns: str):
    if ns.startswith('_b_'):
        return ns[3:]
    if ns.startswith('_'):
        return ns[1:]
    return None

def make_transparent(root: Path, ns: str, path: str):
    target = root/'assets'/ns/'textures'/f'{path}.png'
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(TRANSPARENT_PNG)

def fix_value(ref: str, kind: str, current_ns: str, eff, stats):
    if not isinstance(ref, str) or ref.startswith('#'):
        return ref
    if ':' in ref:
        ns, path = ref.split(':',1)
    else:
        ns, path = current_ns, ref

    if kind == 'model':
        if exists_model(eff, ns, path):
            return ref
        if path in VANILLA_MODEL_TEMPLATES:
            stats['model_parent_rewrites'] += 1
            return f'minecraft:{path}'
        return ref

    if exists_texture(eff, ns, path):
        return ref

    alias = canonical_alias(ns)
    if alias:
        if alias != 'minecraft' and exists_texture(eff, alias, path):
            stats['addon_texture_rewrites'] += 1
            return f'{alias}:{path}'

        if alias == 'minecraft':
            if (ns,path) in TRANSPARENT_ALIAS_TEXTURES:
                return ref
            private = path.startswith('block/__albion_item/') or path in {'toro/knight','front'}
            if not private and (path.startswith('block/') or path.startswith('item/')):
                stats['vanilla_texture_rewrites'] += 1
                return f'minecraft:{path}'
    return ref

def walk_json(obj, current_ns, eff, stats):
    if isinstance(obj, dict):
        if isinstance(obj.get('textures'), dict):
            if 'gui_light' in obj['textures'] and obj.get('gui_light') in ('front', 'side'):
                del obj['textures']['gui_light']
                stats['invalid_texture_keys_removed'] += 1
            for k,v in list(obj['textures'].items()):
                if isinstance(v,str):
                    obj['textures'][k] = fix_value(v,'texture',current_ns,eff,stats)
        for k,v in list(obj.items()):
            if k in ('parent','model') and isinstance(v,str):
                obj[k] = fix_value(v,'model',current_ns,eff,stats)
            walk_json(v,current_ns,eff,stats)
    elif isinstance(obj, list):
        for v in obj:
            walk_json(v,current_ns,eff,stats)

def repair_tree(root: Path, icon: Path|None=None):
    stats = {
        'addon_texture_rewrites':0,
        'vanilla_texture_rewrites':0,
        'model_parent_rewrites':0,
        'invalid_texture_keys_removed':0,
        'json_files_changed':0,
        'pack_icon_replaced':0,
    }
    for ns,path in TRANSPARENT_ALIAS_TEXTURES:
        make_transparent(root,ns,path)
    eff = build_effective(root)

    for p in root.rglob('*.json'):
        if 'assets' not in p.parts:
            continue
        try:
            obj = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        try:
            idx=p.parts.index('assets')
            current_ns=p.parts[idx+1]
        except Exception:
            current_ns='minecraft'
        before=json.dumps(obj,sort_keys=True,separators=(',',':'))
        walk_json(obj,current_ns,eff,stats)
        after=json.dumps(obj,sort_keys=True,separators=(',',':'))
        if after != before:
            p.write_text(json.dumps(obj,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
            stats['json_files_changed'] += 1

    if icon:
        shutil.copyfile(icon, root/'pack.png')
        stats['pack_icon_replaced']=1
    return stats

def validate_reachable(root: Path):
    eff=build_effective(root)
    itemdefs={k:v for k,v in eff.items() if k.startswith('assets/minecraft/items/') and k.endswith('.json')}
    queue=[]
    for rel,p in itemdefs.items():
        try:o=json.loads(p.read_text())
        except Exception: continue
        def collect(x):
            if isinstance(x,dict):
                for k,v in x.items():
                    if k=='model' and isinstance(v,str): queue.append((v,'minecraft',rel))
                    collect(v)
            elif isinstance(x,list):
                for v in x: collect(v)
        collect(o)
    visited=set(); miss_m={}; miss_t={}
    while queue:
        ref,defns,origin=queue.pop()
        ns,path=(ref.split(':',1) if ':' in ref else (defns,ref))
        key=(ns,path)
        if key in visited: continue
        visited.add(key)
        rel=f'assets/{ns}/models/{path}.json'; p=eff.get(rel)
        if ns=='minecraft' and p is None: continue
        if p is None:
            miss_m.setdefault(f'{ns}:{path}',origin); continue
        try:o=json.loads(p.read_text())
        except Exception: continue
        def rec(x):
            if isinstance(x,dict):
                tex=x.get('textures')
                if isinstance(tex,dict):
                    for v in tex.values():
                        if not isinstance(v,str) or v.startswith('#'): continue
                        tns,tpath=(v.split(':',1) if ':' in v else (ns,v))
                        if tns=='minecraft': continue
                        if f'assets/{tns}/textures/{tpath}.png' not in eff:
                            miss_t.setdefault(f'{tns}:{tpath}',p.relative_to(root).as_posix())
                for k,v in x.items():
                    if k in ('model','parent') and isinstance(v,str): queue.append((v,ns,p.relative_to(root).as_posix()))
                    rec(v)
            elif isinstance(x,list):
                for v in x: rec(v)
        rec(o)
    return miss_m,miss_t,len(itemdefs),len(visited)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('input_zip',type=Path)
    ap.add_argument('output_zip',type=Path)
    ap.add_argument('--icon',type=Path)
    args=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/'pack'; root.mkdir()
        with zipfile.ZipFile(args.input_zip) as z: z.extractall(root)
        stats=repair_tree(root,args.icon)
        miss_m,miss_t,itemdefs,models=validate_reachable(root)
        print('repair stats',stats)
        print('reachable',itemdefs,'item definitions',models,'models')
        if miss_m or miss_t:
            for k,v in list(miss_m.items())[:50]: print('MISSING MODEL',k,'<-',v)
            for k,v in list(miss_t.items())[:50]: print('MISSING TEXTURE',k,'<-',v)
            raise SystemExit(f'Asset validation failed: {len(miss_m)} missing models, {len(miss_t)} missing textures')
        args.output_zip.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(args.output_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for p in sorted(root.rglob('*')):
                if p.is_file(): z.write(p,p.relative_to(root).as_posix())
        print('wrote',args.output_zip,args.output_zip.stat().st_size)

if __name__=='__main__': main()
