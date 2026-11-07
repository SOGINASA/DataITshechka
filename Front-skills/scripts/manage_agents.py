#!/usr/bin/env python3
"""Register six native frontend roles by symlink. Preview by default; preserve foreign paths."""
import argparse
import json
import os
import sys
from pathlib import Path
from render_agents import load_roles, check
ROOT=Path(__file__).resolve().parents[1]
HOSTS={'codex':(Path('.codex/agents'),'.toml','codex'),
       'claude':(Path('.claude/agents'),'.md','claude')}

def make_plan(root,home,target):
    plan=[]
    for host in HOSTS if target=='both' else (target,):
        folder,suffix,adapter=HOSTS[host]
        for role in load_roles(root):
            name=role['name']
            source=(root/'agents'/adapter/(name+suffix)).resolve()
            destination=home/folder/(name+suffix)
            if not source.is_file():
                raise ValueError(f'Missing native agent: {source}; run scripts/render_agents.py --write')
            exists=os.path.lexists(destination)
            ours=destination.is_symlink() and destination.resolve()==source
            plan.append(dict(host=host,agent=name,source=str(source),destination=str(destination),
                             state='installed' if ours else 'conflict' if exists else 'missing'))
    return plan

def apply_install(plan):
    conflicts=[r['destination'] for r in plan if r['state']=='conflict']
    if conflicts:
        raise ValueError('Nothing installed; refusing to overwrite: '+', '.join(conflicts))
    made=[]
    try:
        for row in plan:
            if row['state']=='missing':
                dest=Path(row['destination'])
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.symlink_to(row['source'],target_is_directory=False)
                made.append((dest,Path(row['source'])))
    except OSError:
        for dest,source in reversed(made):
            if dest.is_symlink() and dest.resolve()==source:
                dest.unlink()
        raise

def apply_remove(plan):
    for row in plan:
        dest=Path(row['destination'])
        if dest.is_symlink() and dest.resolve()==Path(row['source']):
            dest.unlink()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('install','remove','status'))
    parser.add_argument('--target',choices=('both','codex','claude'),default='both')
    parser.add_argument('--home',type=Path,default=Path.home())
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        if args.action=='install' and check(ROOT):
            raise ValueError('Adapters differ from sources/current kit location; run scripts/render_agents.py --write first')
        home=args.home.expanduser().resolve()
        plan=make_plan(ROOT,home,args.target)
        if args.apply and args.action=='install':
            apply_install(plan)
        elif args.apply and args.action=='remove':
            apply_remove(plan)
        after=make_plan(ROOT,home,args.target) if args.apply else plan
        print(json.dumps(dict(action=args.action,applied=args.apply and args.action!='status',kit_root=str(ROOT),agents=after),ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(str(exc),file=sys.stderr)
        return 1
if __name__=='__main__':
    sys.exit(main())
