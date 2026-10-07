import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ops import greif_media_release as release

ROOT = Path(__file__).resolve().parents[1]


class StandaloneMediaRunner(unittest.TestCase):
    def test_provider_validation_uses_the_standalone_failure_class(self):
        for service, operation, params, error in (
            ('fal', 'models', {'limit': False}, 'invalid_parameters'),
            ('inference', 'app_run', {'app': 'example/app', 'input': {}}, 'write_tool_required'),
        ):
            result = subprocess.run(['/usr/bin/python3', str(ROOT / 'automation_integrations/api_read.py'),
                '/nonexistent-no-secret-read'], input=json.dumps({'service': service, 'operation': operation,
                'params': params}), capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)['error'], error)

    def test_reader_fix_is_guarded_and_composes_with_original_rollback(self):
        with tempfile.TemporaryDirectory() as temp:
            root, project, package = [Path(temp) / name for name in ('runtime', 'project', 'release')]
            target = root / 'release/api_read.py'
            source = project / 'automation_integrations/api_read.py'
            for path in (target, source):
                path.parent.mkdir(parents=True)
            target.write_bytes(b'installed-v1')
            source.write_bytes(b'corrected-v2')
            package.mkdir()
            (package / '0.before').write_bytes(b'original-v0')
            (package / '0.after').write_bytes(b'installed-v1')
            (package / 'manifest.json').write_text(json.dumps({'entries': [{'target': str(target), 'index': 0,
                'before': release.sha(b'original-v0'), 'after': release.sha(b'installed-v1')}], 'protected': {}}))
            release.fix_reader(project, root, package)
            self.assertEqual(target.read_bytes(), b'corrected-v2')
            with self.assertRaises(ValueError):
                release.fix_reader(project, root, package)
            release.apply(package / 'reader-fix', rollback=True)
            release.apply(package, rollback=True)
            self.assertEqual(target.read_bytes(), b'original-v0')


if __name__ == '__main__':
    unittest.main()
