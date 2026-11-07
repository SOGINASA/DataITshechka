import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import render_agents as renderer
import manage_agents as manager

class AgentTests(unittest.TestCase):
    def test_native_roundtrip_and_knowledge_paths(self):
        roles=renderer.load_roles(ROOT)
        generated=renderer.render(ROOT)
        self.assertEqual(len(roles),6)
        self.assertEqual(len(generated),12)
        self.assertEqual(renderer.check(ROOT),[])
        for role in roles:
            codex=tomllib.loads(generated['agents/codex/'+role['name']+'.toml'])
            self.assertEqual(set(codex),{'name','description','developer_instructions'})
            self.assertEqual(codex['name'],role['name'])
            for skill in role['skills']:
                self.assertIn(str(ROOT/'skills'/skill/'SKILL.md'),codex['developer_instructions'])
            claude=generated['agents/claude/'+role['name']+'.md']
            front,body=claude.split('---\n',2)[1:]
            self.assertIn('model: inherit\n',front)
            self.assertEqual(body.lstrip(),codex['developer_instructions'])
            self.assertIn('  - Agent\n',front)
            self.assertEqual('  - Write\n' in front,role['mode']!='write')

    def test_alternate_kit_path_escapes_and_works(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'Kit "with quotes" and spaces'
            shutil.copytree(ROOT/'agents',root/'agents')
            for skill in ('frontend-craft','frontend-qa','ecc-library'):
                p=root/'skills'/skill/'SKILL.md'; p.parent.mkdir(parents=True); p.write_text('fixture')
            p=root/'skills/frontend-team/references/agent-contract.md'; p.parent.mkdir(parents=True); p.write_text('contract')
            generated=renderer.render(root)
            for rel,content in generated.items():
                self.assertNotIn(str(ROOT),content)
                p=root/rel; p.write_text(content)
            self.assertEqual(renderer.check(root),[])
            for rel,content in generated.items():
                if rel.endswith('.toml'):
                    self.assertIn(str(root),tomllib.loads(content)['developer_instructions'])

    def test_install_twice_and_remove_only_ours(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            plan=manager.make_plan(ROOT,home,'both')
            self.assertEqual(len(plan),12)
            self.assertEqual(list(home.iterdir()),[])
            manager.apply_install(plan)
            installed=manager.make_plan(ROOT,home,'both')
            self.assertTrue(all(r['state']=='installed' for r in installed))
            manager.apply_install(installed)
            for row in installed:
                self.assertEqual(Path(row['destination']).read_bytes(),Path(row['source']).read_bytes())
            keep=home/'.claude/agents/other.md'; keep.write_text('user agent')
            manager.apply_remove(installed)
            self.assertEqual(keep.read_text(),'user agent')
            self.assertTrue(all(r['state']=='missing' for r in manager.make_plan(ROOT,home,'both')))

    def test_late_host_conflict_prevents_all_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            dest=home/'.claude/agents/frontend-performance-reviewer.md'
            dest.parent.mkdir(parents=True); dest.write_text('existing user agent')
            with self.assertRaises(ValueError):
                manager.apply_install(manager.make_plan(ROOT,home,'both'))
            self.assertFalse((home/'.codex').exists())
            manager.apply_remove(manager.make_plan(ROOT,home,'both'))
            self.assertEqual(dest.read_text(),'existing user agent')

    def test_foreign_dangling_link_is_not_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp); dest=home/'.codex/agents/frontend-designer.toml'
            dest.parent.mkdir(parents=True); dest.symlink_to(home/'does-not-exist')
            plan=manager.make_plan(ROOT,home,'codex')
            with self.assertRaises(ValueError): manager.apply_install(plan)
            manager.apply_remove(plan)
            self.assertTrue(dest.is_symlink())

    def test_partial_error_rolls_back_new_links(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp); plan=manager.make_plan(ROOT,home,'both')
            original=Path.symlink_to
            calls=[]
            def fail_later(path,*args,**kwargs):
                calls.append(path)
                if len(calls)==4: raise OSError('simulated permission failure')
                return original(path,*args,**kwargs)
            with patch.object(Path,'symlink_to',fail_later):
                with self.assertRaises(OSError): manager.apply_install(plan)
            self.assertTrue(all(r['state']=='missing' for r in manager.make_plan(ROOT,home,'both')))

    def test_cli_is_preview_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            result=subprocess.run([sys.executable,str(ROOT/'scripts/manage_agents.py'),'install','--home',temp],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(json.loads(result.stdout)['applied'])
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_configuration_files_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            files={home/'.codex/config.toml':'model = "existing-choice"\n',home/'.claude/settings.json':'{"permissions": {}}\n'}
            for p,body in files.items(): p.parent.mkdir(parents=True); p.write_text(body)
            manager.apply_install(manager.make_plan(ROOT,home,'both'))
            manager.apply_remove(manager.make_plan(ROOT,home,'both'))
            for p,body in files.items(): self.assertEqual(p.read_text(),body)

if __name__=='__main__': unittest.main()
