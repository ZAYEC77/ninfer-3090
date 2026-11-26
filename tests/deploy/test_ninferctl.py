"""Deployment failure recovery, without Docker, GPU access or production changes."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('ninferctl', str(Path(__file__).resolve().parents[2]/'ninferctl'))
spec = importlib.util.spec_from_loader(loader.name, loader)
ctl = importlib.util.module_from_spec(spec)
loader.exec_module(ctl)


class DeploymentRecovery(unittest.TestCase):
    def exercise(self, fail=False, running=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); state = root/'.local'; verify = state/'verification'; verify.mkdir(parents=True)
            original = 'NINFER_IMAGE=old\nNINFER_CONTEXT=135168\n'
            (root/'.env').write_text(original)
            service = {'Image': 'old', 'State': {'Running': running}}
            def command(*args, **kwargs):
                if args[:3] == ('docker', 'image', 'inspect'):
                    return json.dumps([{'Id': 'new', 'Config': {'Labels': {'org.opencontainers.image.revision': 'revision'}}}])
                if args[:3] == ('docker', 'compose', 'create'):
                    service['Image'] = 'new' if 'NINFER_IMAGE=new\n' in (root/'.env').read_text() else 'old'
                if args[:2] == ('supervisorctl', 'stop'):
                    service['State']['Running'] = False
                if args[:2] == ('supervisorctl', 'start'):
                    service['State']['Running'] = True
                    service['Image'] = 'new' if 'NINFER_IMAGE=new\n' in (root/'.env').read_text() else 'old'
                return 'release/test'
            def checks():
                if fail: raise RuntimeError('New runtime failed live verification')
                return {'ok': True}
            def stop_failed(*args, **kwargs): service['State']['Running'] = False
            with patch.multiple(ctl, ROOT=root, STATE=state, VERIFY=verify), \
                 patch.object(ctl, 'image', side_effect=lambda: service), \
                 patch.object(ctl, 'run', side_effect=command), \
                 patch.object(ctl, 'verify', side_effect=checks), \
                 patch.object(ctl, 'wait_idle'), patch.object(ctl, 'wait_ready'), \
                 patch.object(ctl.subprocess, 'run', side_effect=stop_failed):
                if fail:
                    with self.assertRaisesRegex(RuntimeError, 'live verification'):
                        ctl.deploy('test-image', 'revision')
                    self.assertEqual((root/'.env').read_text(), original)
                    self.assertEqual(service['Image'], 'old')
                    self.assertEqual(service['State']['Running'], running)
                    self.assertFalse((verify/'deployment.json').exists())
                else:
                    ctl.deploy('test-image', 'revision')
                    self.assertEqual(service['Image'], 'new')
                    self.assertTrue(service['State']['Running'])
                    self.assertIn('NINFER_CONTEXT=135168\n', (root/'.env').read_text())
                    self.assertEqual(json.loads((state/'deployment-lock.json').read_text())['image_id'], 'new')
            self.assertFalse(list(root.rglob('*before*')))
            self.assertFalse(list(root.rglob('*.bak')))
    def test_success_keeps_unrelated_configuration(self): self.exercise()
    def test_failed_verification_restores_running_service(self): self.exercise(fail=True)
    def test_failed_first_start_keeps_originally_stopped_service_stopped(self): self.exercise(fail=True, running=False)


if __name__ == '__main__': unittest.main()
