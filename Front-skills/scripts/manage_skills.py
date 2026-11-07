#!/usr/bin/env python3
"""Register six kit skills via symlinks. Preview by default; never overwrite conflicts."""
import argparse
import json
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('frontend-craft', 'frontend-qa', 'ecc-library', 'ml-engineering', 'backend-engineering', 'frontend-team')
HOSTS = {'codex': Path('.agents/skills'), 'claude': Path('.claude/skills')}

def make_plan(root, home, target):
    plan = []
    for host in HOSTS if target == 'both' else (target,):
        for name in SKILLS:
            source = (root / 'skills' / name).resolve()
            destination = home / HOSTS[host] / name
            if not (source / 'SKILL.md').is_file():
                raise ValueError(f'Missing source skill: {source}')
            exists = os.path.lexists(destination)
            ours = destination.is_symlink() and destination.resolve() == source
            plan.append({'host': host, 'skill': name, 'source': str(source),
                         'destination': str(destination),
                         'state': 'installed' if ours else 'conflict' if exists else 'missing'})
    return plan

def apply_install(plan):
    conflicts = [row['destination'] for row in plan if row['state'] == 'conflict']
    if conflicts:
        raise ValueError('Refusing to overwrite existing paths; nothing installed: ' + ', '.join(conflicts))
    made = []
    try:
        for row in plan:
            if row['state'] == 'missing':
                dest = Path(row['destination'])
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.symlink_to(row['source'], target_is_directory=True)
                made.append((dest, Path(row['source'])))
    except OSError:
        for dest, source in reversed(made):
            if dest.is_symlink() and dest.resolve() == source:
                dest.unlink()
        raise

def apply_remove(plan):
    for row in plan:
        dest = Path(row['destination'])
        if dest.is_symlink() and dest.resolve() == Path(row['source']):
            dest.unlink()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'remove', 'status'))
    parser.add_argument('--target', choices=('both', 'codex', 'claude'), default='both')
    parser.add_argument('--home', type=Path, default=Path.home(), help='Alternate home for isolated tests')
    parser.add_argument('--apply', action='store_true', help='Apply install/remove; otherwise preview only')
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    try:
        plan = make_plan(ROOT, home, args.target)
        if args.apply and args.action == 'install':
            apply_install(plan)
        elif args.apply and args.action == 'remove':
            apply_remove(plan)
        after = make_plan(ROOT, home, args.target) if args.apply else plan
        print(json.dumps({'action': args.action, 'applied': args.apply and args.action != 'status',
                          'kit_root': str(ROOT), 'skills': after}, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
