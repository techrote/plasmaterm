"""Focused tests for the additive web-v0.1a adapter."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import plasma
import plasma_config_gen as generator


class RandomizeTests(unittest.TestCase):
    def test_native_randomize_uses_safe_absolute_command(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', False),
                  mock.patch.object(plasma.secrets, 'randbelow', return_value=91),
                  mock.patch.object(plasma.subprocess, 'run') as run):
                self.assertEqual(plasma.randomize_config(), 91)
            generator_path = os.path.join(HERE, 'plasma_config_gen.py')
            run.assert_called_once_with(
                [sys.executable, generator_path, '91',
                 '--output', os.path.abspath(config_path)],
                check=True,
            )

    def test_browser_randomize_uses_generator_api_and_is_loadable(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                self.assertEqual(plasma.randomize_config(123), 123)
                cfg, colors = plasma.load_runtime_config()
            expected, expected_colors = generator.generate_profile(123, '0')
            self.assertEqual(cfg['speed'], expected['speed'])
            self.assertEqual(colors, expected_colors)

    def test_failed_randomize_keeps_previous_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            generator.generate_config(7, config_path)
            with open(config_path, 'rb') as handle:
                previous = handle.read()
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True),
                  mock.patch.object(generator, 'generate_config',
                                    side_effect=OSError('simulated'))):
                with self.assertRaises(OSError):
                    plasma.randomize_config(8)
            with open(config_path, 'rb') as handle:
                self.assertEqual(handle.read(), previous)


class BrowserInputTests(unittest.TestCase):
    def test_press_and_repeat_timing(self):
        keys = plasma.BrowserKeyboardState()
        keys.set_owned(True)
        keys.update('down', ord('Q'))
        self.assertEqual(keys.poll(ord('Q'), 1.0), (True, False))
        self.assertEqual(keys.poll(ord('Q'), 1.2), (False, False))
        self.assertEqual(keys.poll(ord('Q'), 1.36), (False, True))

    def test_focus_loss_clears_held_keys(self):
        keys = plasma.BrowserKeyboardState()
        keys.set_owned(True)
        keys.update('down', ord('Q'))
        keys.set_owned(False)
        keys.set_owned(True)
        self.assertEqual(keys.poll(ord('Q'), 2.0), (False, False))

    def test_randomize_is_press_only(self):
        keys = plasma.BrowserKeyboardState()
        keys.set_owned(True)
        keys.update('down', ord('P'))
        self.assertEqual(keys.poll(ord('P'), 1.0), (True, False))
        self.assertEqual(keys.poll(ord('P'), 1.36), (False, True))
        self.assertFalse(keys.poll(ord('P'), 1.37)[0])


class BrowserRenderingTests(unittest.TestCase):
    def test_browser_size_and_optional_sync_delimiters(self):
        palette = plasma.compile_palette(['000000', 'FFFFFF'])
        with mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True):
            plasma.set_browser_terminal_size(8, 4)
            plain = plasma.render(0, palette, frame_time=0,
                                  synchronized_output=False)
            synced = plasma.render(0, palette, frame_time=0,
                                   synchronized_output=True)
        self.assertNotIn('\x1b[?2026h', plain)
        self.assertTrue(synced.startswith('\x1b[?2026h'))
        self.assertEqual(plain.count('\r\n'), 3)

    def test_runtime_applies_browser_key_and_marks_config_for_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            generator.generate_config(0, config_path)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                before = runtime.cfg['fy']
                runtime.handle_key_event('down', 'Q')
                runtime.step(1.0)
                runtime.handle_key_event('up', 'Q')
                self.assertGreater(runtime.cfg['fy'], before)
                self.assertIsNotNone(runtime.consume_persistence_text())
                runtime.handle_key_event('down', 'Alt', alt=True)
                runtime.handle_key_event('down', 'S', alt=True)
                runtime.step(1.1)
                runtime.handle_key_event('up', 'S', alt=True)
                runtime.handle_key_event('up', 'Alt')
                self.assertIsNotNone(runtime.consume_persistence_text())
                metrics = json.loads(runtime.metrics_json())
                self.assertTrue(metrics['keyboardOwned'])
                self.assertEqual(metrics['freqY'], runtime.cfg['fy'])

    def test_runtime_randomize_does_not_repeat_while_held(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            generator.generate_config(0, config_path)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True),
                  mock.patch.object(plasma, 'randomize_config',
                                    return_value=77) as randomize):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                runtime.handle_key_event('down', 'P')
                runtime.step(1.0)
                runtime.step(1.4)
                randomize.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
