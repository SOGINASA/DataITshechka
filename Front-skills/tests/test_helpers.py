import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
contrast = module('contrast', 'skills/frontend-craft/scripts/contrast.py')
manager = module('manager', 'scripts/manage_skills.py')
finder = module('finder', 'scripts/find_skill.py')

class HelpersTest(unittest.TestCase):
    def test_contrast_known_values_and_validation(self):
        self.assertAlmostEqual(contrast.contrast('#000', '#fff'), 21)
        self.assertAlmostEqual(contrast.contrast('#abc', '#abc'), 1)
        self.assertAlmostEqual(contrast.contrast('#777777', '#FFFFFF'), 4.478089, places=5)
        for bad in ('red', '#0000', '#11223344', '#xyz', ''):
            with self.assertRaises(ValueError):
                contrast.normalize(bad)

    def test_search_exact_name_and_russian_alias(self):
        self.assertEqual(finder.search('react-testing')[0]['name'], 'react-testing')
        self.assertTrue(any('motion' in r['name'] for r in finder.search('анимация')))
        self.assertTrue(any(r['name'] == 'mle-workflow' for r in finder.search('машинное обучение')))
        self.assertEqual(finder.search('бёкенд')[0]['name'], 'backend-patterns')
        self.assertEqual({r['name'] for r in finder.search('', category='machine-learning')},
                         {'mle-workflow', 'ml-adoption-playbook', 'pytorch-patterns'})
        self.assertEqual(finder.search('no-such-skill-xyz'), [])
        for row in finder.search('react'):
            self.assertTrue(Path(row['absolute_path']).is_file())

    def test_install_idempotent_and_safe_remove(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            plan = manager.make_plan(ROOT, home, 'both')
            self.assertEqual(len(plan), 12)
            self.assertFalse((home / '.agents').exists())  # plan is read-only
            manager.apply_install(plan)
            self.assertTrue(all(r['state'] == 'installed' for r in manager.make_plan(ROOT, home, 'both')))
            manager.apply_install(manager.make_plan(ROOT, home, 'both'))
            other = home / '.agents/skills/other'; other.mkdir()
            (other / 'keep').write_text('preserve')
            manager.apply_remove(manager.make_plan(ROOT, home, 'both'))
            self.assertTrue((other / 'keep').exists())
            self.assertTrue(all(r['state'] == 'missing' for r in manager.make_plan(ROOT, home, 'both')))

    def test_collision_is_preflighted_before_any_write(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            existing = home / '.claude/skills/frontend-qa'
            existing.mkdir(parents=True); (existing / 'keep').write_text('original')
            with self.assertRaises(ValueError):
                manager.apply_install(manager.make_plan(ROOT, home, 'both'))
            self.assertFalse((home / '.agents').exists())
            self.assertEqual((existing / 'keep').read_text(), 'original')
            manager.apply_remove(manager.make_plan(ROOT, home, 'both'))
            self.assertTrue((existing / 'keep').exists())

    def test_dangling_foreign_symlink_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp); dest = home / '.agents/skills/ecc-library'
            dest.parent.mkdir(parents=True); dest.symlink_to(home / 'missing-foreign')
            plan = manager.make_plan(ROOT, home, 'codex')
            self.assertTrue(any(r['state'] == 'conflict' for r in plan))
            manager.apply_remove(plan)
            self.assertTrue(dest.is_symlink())

    def test_cli_preview_does_not_install(self):
        with tempfile.TemporaryDirectory() as temp:
            p = subprocess.run([sys.executable, str(ROOT / 'scripts/manage_skills.py'), 'install', '--home', temp], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0)
            self.assertFalse(json.loads(p.stdout)['applied'])
            self.assertEqual(list(Path(temp).iterdir()), [])

if __name__ == '__main__':
    unittest.main()
