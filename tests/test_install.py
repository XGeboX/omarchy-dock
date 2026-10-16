from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch
import json
import tempfile


ROOT = Path(__file__).resolve().parent.parent
loader = SourceFileLoader('dock_cli', str(ROOT / 'bin/omarchy-dock'))
spec = spec_from_loader(loader.name, loader)
dock = module_from_spec(spec)
loader.exec_module(dock)


class InstallTests(TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix='omarchy-dock-test-'))
        self.home_patch = patch.object(Path, 'home', return_value=self.home)
        self.home_patch.start()
        self.root_patch = patch.object(dock.os, 'geteuid', return_value=1000)
        self.root_patch.start()
        self.env_patch = patch.dict(dock.os.environ, {'XDG_CONFIG_HOME': str(self.home / '.config'), 'XDG_STATE_HOME': str(self.home / '.local/state')})
        self.env_patch.start()
        self.calls = []

        def command(args):
            self.calls.append(args)
            if args[-1] == 'ping':
                return 'ok'
            if args[-1] == 'motionProfile':
                return json.dumps({'version': '0.7.0-dev', 'icons': 'original', 'positioning': 'reduced-drift'})
            if args[-1] == 'listPlugins':
                return '[{"id":"xgebox.dock"}]'
            return ''

        self.run_patch = patch.object(dock, 'command', side_effect=command)
        self.run_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.run_patch.stop()
        self.root_patch.stop()
        self.home_patch.stop()

    def test_first_enable_creates_discoverable_plugin_and_configuration(self):
        dock.enable()
        target = self.home / '.config/omarchy/plugins/xgebox.dock'
        self.assertTrue(target.is_symlink())
        self.assertEqual(json.loads((target / 'manifest.json').read_text())['id'], 'xgebox.dock')
        config = json.loads((self.home / '.config/omarchy-dock/config.json').read_text())
        self.assertEqual(config['pinned'], [])
        self.assertEqual(config['magnification'], 1.55)
        self.assertIn(['omarchy', 'plugin', 'enable', 'xgebox.dock'], self.calls)

    def test_existing_preferences_survive_repeated_enable(self):
        path = self.home / '.config/omarchy-dock/config.json'
        path.parent.mkdir(parents=True)
        original = '{"pinned":[{"class":"fixture.app"}],"iconSize":64,"magnify":false}\n'
        path.write_text(original)
        dock.enable()
        dock.enable()
        self.assertEqual(path.read_text(), original)

    def test_shell_configuration_is_backed_up_without_local_rewrite(self):
        path = self.home / '.config/omarchy/shell.json'
        path.parent.mkdir(parents=True)
        original = '{"plugins":["fixture.service"],"bar":{"id":"fixture.bar"}}\n'
        path.write_text(original)
        dock.enable()
        self.assertEqual(path.read_text(), original)
        backups = list((self.home / '.local/state/omarchy-dock/backups').glob('*/shell.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)

    def test_foreign_plugin_directory_is_preserved(self):
        target = self.home / '.config/omarchy/plugins/xgebox.dock'
        target.mkdir(parents=True)
        marker = target / 'unrelated.txt'
        marker.write_text('fixture')
        with self.assertRaises(dock.DockError):
            dock.enable()
        self.assertEqual(marker.read_text(), 'fixture')
        self.assertNotIn(['omarchy', 'plugin', 'enable', 'xgebox.dock'], self.calls)

    def test_invalid_existing_configuration_is_preserved(self):
        path = self.home / '.config/omarchy-dock/config.json'
        path.parent.mkdir(parents=True)
        path.write_text('{broken')
        with self.assertRaises(dock.DockError):
            dock.enable()
        self.assertEqual(path.read_text(), '{broken')

    def test_disable_keeps_preferences_and_installed_source(self):
        dock.enable()
        path = self.home / '.config/omarchy-dock/config.json'
        before = path.read_bytes()
        dock.disable()
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue((self.home / '.config/omarchy/plugins/xgebox.dock').is_symlink())
        self.assertIn(['omarchy', 'plugin', 'disable', 'xgebox.dock'], self.calls)

    def test_missing_shell_does_not_create_configuration(self):
        with patch.object(dock, 'command', side_effect=dock.DockError('shell unavailable')):
            with self.assertRaises(dock.DockError):
                dock.enable()
        self.assertFalse((self.home / '.config/omarchy-dock/config.json').exists())

    def test_stale_runtime_is_reported(self):
        def stale(args):
            if args[-1] == 'ping':
                return 'ok'
            if args[-1] == 'motionProfile':
                return '{"version":"0.1.0"}'
            if args[-1] == 'listPlugins':
                return '[{"id":"xgebox.dock"}]'
            return ''
        with patch.object(dock, 'command', side_effect=stale), patch.object(dock.time, 'sleep'):
            with self.assertRaisesRegex(dock.DockError, 'restart shell'):
                dock.enable()

    def test_registration_finishes_before_enable(self):
        registrations = []

        def delayed(args):
            if args[-1] == 'ping':
                return 'ok'
            if args[-1] == 'listPlugins':
                registrations.append(True)
                return '[]' if len(registrations) < 3 else '[{"id":"xgebox.dock"}]'
            if args[-2:] == ['enable', 'xgebox.dock'] and len(registrations) < 3:
                raise dock.DockError('plugin unknown before scan finishes')
            if args[-1] == 'motionProfile':
                return '{"version":"0.7.0-dev"}'
            return ''

        with patch.object(dock, 'command', side_effect=delayed), patch.object(dock.time, 'sleep'):
            dock.enable()
        self.assertEqual(len(registrations), 3)

    def test_concurrent_foreign_installation_is_not_activated(self):
        target = self.home / '.config/omarchy/plugins/xgebox.dock'

        def other_installation(_):
            target.mkdir(parents=True)
            (target / 'unrelated.txt').write_text('fixture')

        with patch.object(dock, 'backup_preferences', side_effect=other_installation):
            with self.assertRaises(dock.DockError):
                dock.enable()
        self.assertNotIn(['omarchy', 'plugin', 'enable', 'xgebox.dock'], self.calls)

    def test_concurrent_invalid_preferences_are_not_activated(self):
        config = self.home / '.config/omarchy-dock/config.json'

        def other_preferences(_):
            config.parent.mkdir(parents=True)
            config.write_text('{broken')

        with patch.object(dock, 'backup_preferences', side_effect=other_preferences):
            with self.assertRaises(dock.DockError):
                dock.enable()
        self.assertEqual(config.read_text(), '{broken')
        self.assertNotIn(['omarchy', 'plugin', 'enable', 'xgebox.dock'], self.calls)

    def test_custom_config_root_is_initialized_and_backed_up(self):
        custom = self.home / 'custom-config'
        with patch.dict(dock.os.environ, {'XDG_CONFIG_HOME': str(custom)}):
            dock.enable()
            config = custom / 'omarchy-dock/config.json'
            self.assertTrue(config.is_file())
            dock.enable()
            backups = list((self.home / '.local/state/omarchy-dock/backups').glob('*/config.json'))
            self.assertTrue(backups)
            self.assertEqual(backups[0].read_bytes(), config.read_bytes())
        self.assertFalse((self.home / '.config/omarchy-dock/config.json').exists())

    def test_root_activation_is_refused(self):
        with patch.object(dock.os, 'geteuid', return_value=0):
            with self.assertRaises(dock.DockError):
                dock.enable()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    main()
