#!/usr/bin/env python3
"""Validate kit paths, source checksums, local skill frontmatter and image integrity."""
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote
ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    errors = []
    skills = sorted((ROOT / 'skills').glob('*/SKILL.md'))
    expected = {'frontend-craft', 'frontend-qa', 'ecc-library', 'ml-engineering', 'backend-engineering', 'frontend-team'}
    if {p.parent.name for p in skills} != expected:
        errors.append('Expected exactly the six authored entrypoints')
    for p in skills:
        content = p.read_text()
        if not content.startswith('---\n') or len(content.split('---', 2)) < 3:
            errors.append(f'Invalid frontmatter: {p}')
            continue
        front = content.split('---', 2)[1]
        if not re.search(r'^name: ' + re.escape(p.parent.name) + r'$', front, re.M):
            errors.append(f'Name/folder mismatch: {p}')
        if not re.search(r'^description: .+', front, re.M):
            errors.append(f'Missing description: {p}')
    # Authored Markdown only. Vendored examples include intentional placeholders/paths.
    authored = list((ROOT / 'skills').rglob('*.md')) + [ROOT / 'README-RU.md', ROOT / 'ML-GUIDE-RU.md', ROOT / 'BACKEND-GUIDE-RU.md', ROOT / 'FRONTEND-AGENTS-GUIDE-RU.md', ROOT / 'AGENTS.md', ROOT / 'CLAUDE.md']
    for p in authored:
        if not p.exists():
            errors.append(f'Missing authored document: {p}')
            continue
        for target in re.findall(r'\]\(([^)]+)\)', p.read_text()):
            if '://' in target or target.startswith('#'):
                continue
            target = unquote(target.split('#')[0].split(' "')[0])
            if target and not (p.parent / target).exists():
                errors.append(f'Broken reference: {p.relative_to(ROOT)} -> {target}')
    from render_agents import check as check_agents
    errors.extend('Native agent drift: ' + p for p in check_agents(ROOT))
    catalog = json.loads((ROOT / 'catalog/ecc-skills.json').read_text())
    if len(catalog) != 311 or len({r['name'] for r in catalog}) != 311:
        errors.append('ECC canonical catalog count or uniqueness mismatch')
    canonical = {p.relative_to(ROOT).as_posix() for p in (ROOT / 'library/ecc/skills').glob('*/SKILL.md')}
    if {r['path'] for r in catalog} != canonical:
        errors.append('Catalog does not exactly match canonical entrypoints')
    for row in catalog:
        p = ROOT / row['path']
        if not p.is_file() or sha(p) != row['sha256']:
            errors.append(f'ECC entrypoint checksum mismatch: {row["name"]}')
    images = json.loads((ROOT / 'skills/frontend-craft/references/reference-manifest.json').read_text())
    if len(images) != 63 or {r['id'] for r in images} != set(range(1, 64)):
        errors.append('Reference image count or IDs mismatch')
    for row in images:
        p = ROOT / 'skills/frontend-craft' / row['path']
        if not p.is_file() or sha(p) != row['sha256']:
            errors.append(f'Image checksum mismatch: {row["id"]}')
    manifest = ROOT / 'catalog/upstream-sha256.json'
    if not manifest.exists():
        errors.append('Missing full upstream manifest')
    else:
        hashes = json.loads(manifest.read_text())
        actual = {p.relative_to(ROOT / 'library/ecc').as_posix() for p in (ROOT / 'library/ecc').rglob('*') if p.is_file()}
        if set(hashes) != actual:
            errors.append('Full upstream file inventory mismatch')
        for rel, checksum in hashes.items():
            p = ROOT / 'library/ecc' / rel
            if not p.is_file() or sha(p) != checksum:
                errors.append('Upstream file changed: ' + rel)
    print(json.dumps({'status': 'FAIL' if errors else 'PASS', 'authored_skills': len(skills),
                      'ecc_skills': len(catalog), 'reference_images': len(images), 'frontend_agents': 6, 'native_agent_files': 12,
                      'errors': errors, 'scope': 'Structural/integrity checks, not model behavior or full upstream audit.'}, ensure_ascii=False, indent=2))
    return bool(errors)

if __name__ == '__main__':
    sys.exit(main())
