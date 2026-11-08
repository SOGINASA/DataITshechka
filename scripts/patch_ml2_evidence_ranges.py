"""Apply the range fix to the pinned API release without replacing its integration.

Usage: python scripts/patch_ml2_evidence_ranges.py /path/to/deployed/app
Run on a staged copy first. This does not restart workers or deploy an image.
"""
import hashlib
import json
from pathlib import Path
import sys


def patch(root):
    source = Path(__file__).resolve().parents[1] / 'ml2'
    runtime = root / 'ml2_runtime'
    manifest_path = runtime / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    service_path = root / 'services/ml2.py'
    service = service_path.read_text()
    old = "            row = deepcopy(common)"
    new = """            # Preserve criterion-specific evidence bounds from ML2's wire schema.
            row = schema['properties']['results']['properties'][criterion['id']]
            row = deepcopy(common if row.get('$ref') == '#/$defs/assessment' else row)"""
    if service.count(old) != 1:
        raise ValueError('Unexpected adapter version; review before applying')
    service = service.replace(old, new)
    service = service.replace("'adapter_version': 'ml2-api-1'", "'adapter_version': 'ml2-api-1-range-fix'")
    service = service.replace("'source_tree': MANIFEST['source_tree'],", 
                              "'runtime_hotfix': MANIFEST.get('hotfix'), 'source_tree': MANIFEST['source_tree'],")
    replacements = {}
    for name in ('decoding.py', 'engine.py', 'prompts/system.txt'):
        existing = (runtime / name).read_bytes()
        if hashlib.sha256(existing).hexdigest() != manifest['files'][name]:
            raise ValueError(f'Deployed file differs from manifest: {name}')
        replacements[runtime / name] = (source / name).read_bytes()
    manifest['hotfix'] = {
        'id': '20261108-evidence-ranges',
        'base_source_revision': manifest['source_revision'],
        'base_source_tree': manifest['source_tree'],
        'adapter_sha256': hashlib.sha256(service.encode()).hexdigest(),
        'description': 'Criterion ranges in prompt and evidence enums; adapter preserves enums.',
    }
    manifest['prompt_version'] = 'ml2-cqa-10'
    for path, content in replacements.items():
        manifest['files'][str(path.relative_to(runtime))] = hashlib.sha256(content).hexdigest()
    for path, content in replacements.items():
        path.write_bytes(content)
    service_path.write_text(service)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    patch(Path(sys.argv[1]).resolve())
