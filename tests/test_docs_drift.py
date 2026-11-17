"""Docs must not reference scripts, paths or CLI flags that do not exist (stale-runbook guard)."""
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMAND = re.compile(r'(?:python3\s+|\./|sudo\s+)((?:scripts/[\w/.-]+\.(?:py|sh))|install\.sh|uninstall\.sh|update\.sh)\b(.*)')
PATH = re.compile(r'(?<![\w/.-])((?:\./)?(?:scripts|tests|deploy|docs)/[\w./-]+\.(?:py|sh|md|yaml|yml|conf|service|timer|example))')


def documents():
    names = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '*.md', '.github/*'], capture_output=True,
                           text=True, check=True).stdout.split()
    return [ROOT / n for n in names]


class DocsDrift(unittest.TestCase):
    def test_referenced_paths_exist(self):
        missing = [(d.name, m) for d in documents() for m in PATH.findall(d.read_text(errors='replace'))
                   if not (ROOT / m.lstrip('./')).exists()]
        self.assertFalse(missing)

    def test_documented_flags_are_accepted(self):
        helps, bad = {}, []
        for doc in documents():
            for line in doc.read_text(errors='replace').replace('\\\n', ' ').splitlines():
                match = COMMAND.search(line)
                if not match:
                    continue
                script = match.group(1)
                if not (ROOT / script).exists():
                    bad.append((doc.name, script)); continue
                flags = re.findall(r'(?<![\w-])(--[a-z][a-z0-9-]+)', match.group(2))
                if not flags or script == 'scripts/qa.sh':  # qa.sh has no options and would recurse
                    continue
                if script not in helps:
                    argv = (['bash'] if script.endswith('.sh') else [sys.executable]) + [str(ROOT / script), '--help']
                    out = subprocess.run(argv, capture_output=True, text=True, timeout=60, cwd=ROOT)
                    helps[script] = out.stdout + out.stderr
                bad += [(doc.name, script, flag) for flag in flags if flag not in helps[script]]
        self.assertFalse(sorted(set(bad)))
        self.assertGreater(len(helps), 5)

    def test_env_example_matches_compose_variables(self):
        used = set(re.findall(r'\$\{([A-Z0-9_]+)', (ROOT / 'docker-compose.yml').read_text()))
        documented = set(re.findall(r'^#?\s*([A-Z0-9_]+)=', (ROOT / '.env.example').read_text(), re.M))
        self.assertFalse(used - documented, 'Compose variables missing from .env.example')
        self.assertFalse(documented - used, '.env.example variables Compose ignores')


if __name__ == '__main__':
    unittest.main()
