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


class BrowserPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(HERE, 'web', 'index.html'), encoding='utf-8') as handle:
            cls.html = handle.read()
        with open(os.path.join(HERE, 'web', 'plasma-browser.js'), encoding='utf-8') as handle:
            cls.javascript = handle.read()
        with open(os.path.join(HERE, 'web', 'plasma-worker.js'), encoding='utf-8') as handle:
            cls.worker_javascript = handle.read()

    def test_working_page_version_is_incremented(self):
        self.assertIn('PlasmaTerm web-v0.101a', self.html)
        self.assertIn("plasmaterm.web-v0.101a.config", self.javascript)

    def test_desktop_window_is_bounded_and_centre_anchored(self):
        self.assertIn('--plasma-width: 900px', self.html)
        self.assertIn('--plasma-height: 560px', self.html)
        self.assertIn('transform: translate(-50%, -50%)', self.html)
        self.assertIn('(Math.abs(moveEvent.clientX - centreX) - startDistanceX) * 2',
                      self.javascript)
        self.assertEqual(self.html.count('data-corner='), 4)

    def test_resize_handles_are_entirely_outside_the_visual_window(self):
        self.assertIn('overflow: visible', self.html)
        for corner, horizontal, vertical in (
                ('nw', 'left: -22px', 'top: -22px'),
                ('ne', 'right: -22px', 'top: -22px'),
                ('sw', 'left: -22px', 'bottom: -22px'),
                ('se', 'right: -22px', 'bottom: -22px')):
            self.assertIn(f'.resize-handle.{corner} {{ {horizontal}; {vertical};',
                          self.html)
        self.assertIn('const startDistanceX = Math.abs(event.clientX - centreX)',
                      self.javascript)
        self.assertIn('const startDistanceY = Math.abs(event.clientY - centreY)',
                      self.javascript)

    def test_no_scroll_workspace_and_character_scaling_are_present(self):
        self.assertIn('overflow: hidden', self.html)
        self.assertNotIn('scroll-snap-type', self.html)
        self.assertNotIn('plasma-reel', self.html)
        self.assertIn('height: 100dvh', self.html)
        self.assertIn("terminalElement.addEventListener('touchmove'", self.javascript)
        self.assertIn('terminal.options.fontSize = fontSize', self.javascript)

    def test_clickable_keybed_and_energy_bridge_are_present(self):
        self.assertIn("['Q', '+ Y freq']", self.javascript)
        self.assertIn("['I', 'next LUT']", self.javascript)
        self.assertNotIn("['L',", self.javascript)
        self.assertNotIn("['E',", self.javascript)
        self.assertIn('function sendKeyDown(', self.javascript)
        self.assertIn("type: 'energy'", self.javascript)
        self.assertIn('id="energy-panel"', self.html)

    def test_title_controls_resize_protocol_and_undo_are_present(self):
        self.assertIn('id="fps-input" type="number" min="1" max="1000"', self.html)
        self.assertIn('id="fps-preset" aria-label="Frame rate presets"', self.html)
        for fps in (24, 30, 60, 120, 144, 240):
            self.assertIn(f'<option value="{fps}"', self.html)
        self.assertIn('id="pt-input" type="number" min="6" max="200"', self.html)
        self.assertIn('id="pt-preset" aria-label="Point size presets"', self.html)
        for point_size in (12, 16, 24, 36, 46, 64):
            self.assertIn(f'<option value="{point_size}"', self.html)
        self.assertIn('id="pt-down"', self.html)
        self.assertIn('id="pt-up"', self.html)
        self.assertIn("const DISPLAY_SCHEMA_VERSION = 3", self.javascript)
        self.assertIn('fontSize: 24', self.javascript)
        self.assertIn("type: 'resizePause'", self.javascript)
        self.assertIn("fitTerminal('resizeCommit')", self.javascript)
        self.assertIn("type: 'undoRandomize'", self.javascript)
        self.assertIn('function editingControlActive(', self.javascript)
        self.assertIn('let selectedFps = 24', self.javascript)
        self.assertIn("'fps = 24'", self.javascript)
        self.assertEqual(plasma.WEB_FPS_OPTIONS[0], 24)

    def test_background_field_themes_requested_surfaces_on_commit(self):
        pt_position = self.html.index('id="pt-input"')
        bg_position = self.html.index('id="bg-input"')
        fps_position = self.html.index('id="fps-input"')
        self.assertLess(pt_position, bg_position)
        self.assertLess(bg_position, fps_position)
        self.assertIn('id="bg-input" type="text" maxlength="7" value="050509"',
                      self.html)
        self.assertIn('function applyBackgroundColor(value)', self.javascript)
        self.assertIn("bgInput.addEventListener('blur', commitBackgroundField)",
                      self.javascript)
        self.assertIn("event.key !== 'Enter'", self.javascript)
        self.assertIn("rootStyle.setProperty('--energy-highlight'", self.javascript)
        self.assertIn("rootStyle.setProperty('--dock-colour'", self.javascript)
        self.assertIn('terminal.options.theme = { ...terminal.options.theme, background:',
                      self.javascript)

    def test_energy_uses_independent_targets_and_wave_dropdown(self):
        self.assertNotIn('id="energy-centre"', self.html)
        self.assertNotIn('id="energy-breadth"', self.html)
        self.assertEqual(self.html.count('data-target-bit='), 5)
        self.assertIn('id="energy-wave"', self.html)
        self.assertIn('<option value="wander-noise">Wander noise</option>', self.html)
        self.assertIn("energyWaveSelect.addEventListener('change'", self.javascript)
        self.assertIn('id="energy-width-track"', self.html)
        self.assertIn('id="energy-rate-output" type="number" min="-6" max="6"', self.html)
        self.assertIn('id="energy-rate" type="range" orient="vertical" min="-3" max="3"', self.html)
        self.assertIn('class="width-fill"', self.html)

    def test_compact_faux_windows_are_independently_draggable(self):
        self.assertEqual(self.html.count('class="faux-window'), 4)
        self.assertIn('id="controls-window"', self.html)
        self.assertIn('id="lut-window"', self.html)
        self.assertIn('data-drag-handle="controls"', self.html)
        self.assertIn('data-drag-handle="energy"', self.html)
        self.assertIn('data-drag-handle="lut"', self.html)
        self.assertIn('function resetWindowPositions()', self.javascript)
        self.assertNotIn('Play the keybed or patch', self.html)
        self.assertNotIn('Keyboard, mouse, and Energy modulation share', self.html)

    def test_functional_chrome_docking_and_lut_editor_are_present(self):
        self.assertIn('--toolbar-height: 24px', self.html)
        for element_id in ('global-reset', 'visual-mode', 'dock-controls',
                           'dock-energy', 'dock-lut', 'restore-controls',
                           'restore-energy', 'restore-lut', 'reset-keybed',
                           'reset-energy', 'export-lut'):
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertNotIn('class="window-title"', self.html)
        self.assertIn('grid-template-columns: repeat(16', self.html)
        self.assertIn('grid-template-columns: repeat(8', self.html)
        self.assertIn('for (let index = 0; index < 256;', self.javascript)
        self.assertIn("type: 'setLut'", self.javascript)
        self.assertIn("rows.push(lutState.colors.slice(index, index + 8).join(', '))", self.javascript)

    def test_lut_randomise_scale_uses_atomic_current_palette_updates(self):
        self.assertIn('id="randomise-lut"', self.html)
        self.assertIn('id="lut-random-scale" type="number" min="0" max="100"',
                      self.html)
        self.assertIn('id="lut-random-scale-slider" type="range" min="0" max="100"',
                      self.html)
        self.assertIn('function randomiseLutColors(colors, scalePercent, random = Math.random)',
                      self.javascript)
        self.assertIn('const anchorCount = 8', self.javascript)
        self.assertIn('const colors = randomiseLutColors(lutState.colors, lutRandomScale)',
                      self.javascript)
        self.assertIn('if (!sendLutColors(colors)) return', self.javascript)
        self.assertIn('updateLutFields({ ...lutState, colors }, false)', self.javascript)

    def test_keybed_latches_and_resets_are_wired(self):
        self.assertIn('id="key-latch-plus"', self.html)
        self.assertIn('id="key-latch-plusplus"', self.html)
        self.assertIn("type: 'keybedLatches'", self.javascript)
        self.assertIn("type: 'resetParameters'", self.javascript)
        self.assertIn('function resetWorkspaceLayout()', self.javascript)
        self.assertIn("event.key !== 'Escape'", self.javascript)
        self.assertIn("data.type === 'keybedLatches'", self.worker_javascript)
        self.assertIn("data.type === 'resetParameters'", self.worker_javascript)
        self.assertIn("data.type === 'setLut'", self.worker_javascript)
        self.assertIn('runtime.consume_lut_state_json()', self.worker_javascript)


class EnergyModulationTests(unittest.TestCase):
    def test_wave_shapes_at_quarter_phases(self):
        self.assertAlmostEqual(plasma.energy_wave_value('sine', 0.0), 0.0)
        self.assertAlmostEqual(plasma.energy_wave_value('sine', 0.25), 1.0)
        self.assertEqual(
            [plasma.energy_wave_value('smooth-triangle', phase)
             for phase in (0.0, 0.25, 0.5, 0.75)],
            [-1.0, 0.0, 1.0, 0.0],
        )
        self.assertAlmostEqual(
            plasma.energy_wave_value('loop-noise', 0),
            plasma.energy_wave_value('loop-noise', 1))
        self.assertAlmostEqual(
            plasma.energy_wave_value('wander-noise', 3.125),
            plasma.energy_wave_value('wander-noise', 3.125))
        self.assertNotAlmostEqual(
            plasma.energy_wave_value('wander-noise', 0.375),
            plasma.energy_wave_value('wander-noise', 1.375))
        self.assertLess(abs(
            plasma.energy_wave_value('loop-noise', 1.0 - 1e-6)
            - plasma.energy_wave_value('loop-noise', 1e-6)), 1e-4)
        self.assertLess(abs(
            plasma.energy_wave_value('wander-noise', 1.0 - 1e-6)
            - plasma.energy_wave_value('wander-noise', 1.0 + 1e-6)), 1e-4)

    def test_transient_modulation_leaves_base_and_persistence_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            generator.generate_config(0, config_path)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                base = dict(runtime.cfg)
                palette = runtime.palette
                with open(config_path, 'rb') as handle:
                    persisted = handle.read()
                runtime.configure_energy(
                    True, 100, 0.25, 1, 1, 0, 1, 'sine')
                effective = runtime._effective_energy_values(0.0)
                self.assertAlmostEqual(effective['fy'], base['fy'] + 0.3)
                self.assertEqual(runtime.cfg, base)
                self.assertIs(runtime.palette, palette)
                runtime.configure_energy(
                    False, 100, 0.25, 1, 1, 0, 1, 'sine')
                self.assertEqual(runtime._effective_energy_values(1.0), {
                    name: base[name] for name, _, _ in plasma.ENERGY_PARAMETERS
                })
                with open(config_path, 'rb') as handle:
                    self.assertEqual(handle.read(), persisted)

    def test_energy_configuration_validates_and_reports_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            generator.generate_config(0, config_path)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                runtime.configure_energy(
                    True, 25, -0.5, -1, 1, 5, 0b11001, 'smooth-triangle')
                runtime._effective_energy_values(0.25)
                metrics = json.loads(runtime.metrics_json())
                self.assertTrue(metrics['energyEnabled'])
                self.assertEqual(metrics['energyWave'], 'smooth-triangle')
                self.assertEqual(
                    metrics['energyTargets'], ['freq-y', 'hue-shift', 'radius'])
                with self.assertRaises(ValueError):
                    runtime.configure_energy(
                        True, 101, 0.5, -1, 1, 0, 1, 'sine')
                with self.assertRaises(ValueError):
                    runtime.configure_energy(
                        True, 25, 0.5, -1, 1, 0, 1.5, 'sine')
                with self.assertRaises(ValueError):
                    runtime.configure_energy(
                        True, 25, 6.01, -1, 1, 0, 1, 'sine')

    def test_signed_rate_reverses_and_zero_freezes_position(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            generator.generate_config(0, config_path)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                self.assertEqual(runtime.energy['rate'], 1)
                runtime.configure_energy(True, 100, -1, -1, 1, 0, 1, 'sine')
                reverse = runtime._effective_energy_values(0.25)
                self.assertAlmostEqual(runtime.energy_position, -0.25)
                self.assertAlmostEqual(reverse['fy'], runtime.cfg['fy'] - 0.3)
                runtime.configure_energy(True, 100, 0, -1, 1, 0, 1, 'sine')
                runtime._effective_energy_values(4)
                self.assertAlmostEqual(runtime.energy_position, -0.25)

    def test_every_energy_target_mask_including_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            generator.generate_config(0, config_path)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                base = dict(runtime.cfg)
                for mask in range(32):
                    runtime.configure_energy(
                        True, 100, 0.25, 1, 1, 0, mask, 'sine')
                    effective = runtime._effective_energy_values(0)
                    for index, (name, step, _) in enumerate(plasma.ENERGY_PARAMETERS):
                        expected = base[name] + (step * 100 if mask & (1 << index) else 0)
                        self.assertAlmostEqual(effective[name], expected)
                    metrics = json.loads(runtime.metrics_json())
                    self.assertEqual(metrics['energyTargetMask'], mask)

    def test_manual_and_preset_changes_update_base_while_energy_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            generator.generate_config(0, config_path)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                runtime.configure_energy(
                    True, 50, 0.25, 1, 1, 0, 1, 'sine')
                before = runtime.cfg['fy']
                runtime.handle_key_event('down', 'Q')
                runtime.step(1.0)
                runtime.handle_key_event('up', 'Q')
                self.assertGreater(runtime.cfg['fy'], before)
                runtime.handle_key_event('down', '1')
                runtime.step(1.1)
                runtime.handle_key_event('up', '1')
                self.assertEqual(runtime.selected_preset, 1)
                preset_base = dict(runtime.cfg)
                runtime.configure_energy(
                    False, 50, 0.25, 1, 1, 0, 1, 'sine')
                self.assertEqual(runtime._effective_energy_values(0), {
                    name: preset_base[name]
                    for name, _, _ in plasma.ENERGY_PARAMETERS
                })


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

    def test_two_randomize_snapshots_undo_in_reverse_order(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            generator.generate_config(0, config_path)

            slots = iter((1, 2, 3))
            def generate_next():
                slot = next(slots)
                generator.generate_config(slot, config_path)
                return slot

            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True),
                  mock.patch.object(plasma, 'randomize_config', side_effect=generate_next)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                runtime.set_fps(144)
                bases = [dict(runtime.cfg)]
                for frame_time in (1.0, 2.0, 3.0):
                    runtime.handle_key_event('down', 'P')
                    runtime.step(frame_time)
                    runtime.handle_key_event('up', 'P')
                    bases.append(dict(runtime.cfg))
                self.assertEqual(len(runtime.random_history), 2)
                self.assertEqual(runtime.cfg['fps'], 144)
                self.assertTrue(runtime.undo_randomize())
                self.assertEqual(runtime.cfg, bases[2])
                self.assertTrue(runtime.undo_randomize())
                self.assertEqual(runtime.cfg, bases[1])
                self.assertFalse(runtime.undo_randomize())
                self.assertEqual(json.loads(runtime.metrics_json())['undoDepth'], 0)
                restored_cfg, restored_colors = plasma.load_runtime_config()
                self.assertEqual(restored_cfg, bases[1])
                self.assertEqual(restored_colors, runtime.palette_colors)


class WebControlTests(unittest.TestCase):
    def make_runtime(self, directory, slot=0):
        config_path = os.path.join(directory, 'plasma.conf')
        generator.generate_config(slot, config_path)
        return config_path

    def test_web_fps_accepts_and_persists_custom_values_in_range(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.make_runtime(directory)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                self.assertEqual(runtime.cfg['fps'], 40)
                runtime.set_fps(1000)
                self.assertEqual(runtime.frame_interval_ms(), 1)
                runtime.set_fps(40)
                with self.assertRaises(ValueError):
                    runtime.set_fps(0)
                with self.assertRaises(ValueError):
                    runtime.set_fps(1001)
                cfg, _ = plasma.load_runtime_config()
                self.assertEqual(cfg['fps'], 40)

        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, 'plasma.conf')
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                self.assertEqual(runtime.cfg['fps'], 24)

    def test_lut_keys_cycle_both_directions_and_wrap(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.make_runtime(directory)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                runtime.cfg['active_lut'] = '9'
                plasma.write_section('config', runtime.cfg)
                runtime.handle_key_event('down', 'I')
                runtime.step(1.0)
                runtime.handle_key_event('up', 'I')
                self.assertEqual(runtime.cfg['active_lut'], '0')
                self.assertEqual(runtime.palette_colors, plasma.load_lut('0'))
                runtime.handle_key_event('down', 'K')
                runtime.step(1.1)
                runtime.handle_key_event('up', 'K')
                self.assertEqual(runtime.cfg['active_lut'], '9')
                self.assertEqual(runtime.palette_colors, plasma.load_lut('9'))

    def test_hue_shift_step_and_removed_fps_shortcuts(self):
        self.assertEqual(plasma.PARAMETER_KEYS['Y'], ('hue_shift', 0.5))
        self.assertEqual(plasma.PARAMETER_KEYS['H'], ('hue_shift', -0.5))
        self.assertEqual(plasma.ENERGY_PARAMETERS[3],
                         ('hue_shift', 0.005, 'hue-shift'))
        self.assertEqual(plasma.PARAMETER_KEYS['T'], ('speed', 0.03))
        self.assertEqual(plasma.PARAMETER_KEYS['G'], ('speed', -0.03))
        self.assertEqual(plasma.ENERGY_PARAMETERS[0], ('fy', 0.003, 'freq-y'))
        self.assertEqual(plasma.ENERGY_PARAMETERS[1], ('fx', 0.003, 'freq-x'))
        self.assertEqual(plasma.ENERGY_PARAMETERS[4], ('rad', 0.005, 'radius'))
        self.assertNotIn('O', plasma.PARAMETER_KEYS)
        self.assertNotIn('L', plasma.PARAMETER_KEYS)
        self.assertNotIn('I', plasma.PARAMETER_KEYS)
        self.assertNotIn('K', plasma.PARAMETER_KEYS)

    def test_web_keybed_latch_factors_and_modifier_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.make_runtime(directory)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                self.assertEqual(
                    [runtime._web_parameter_factor(key)
                     for key in ('Q', 'Y', 'T', 'U')],
                    [1, 1, 1, 1])
                runtime.set_keybed_latches(1)
                self.assertEqual(
                    [runtime._web_parameter_factor(key)
                     for key in ('Q', 'Y', 'T', 'U')],
                    [1.5, 1.5, 3, 3])
                runtime.set_keybed_latches(2)
                self.assertEqual(
                    [runtime._web_parameter_factor(key)
                     for key in ('Q', 'Y', 'T', 'U')],
                    [3, 3, 6, 6])
                runtime.set_keybed_latches(3)
                self.assertEqual(
                    [runtime._web_parameter_factor(key)
                     for key in ('Q', 'Y', 'T', 'U')],
                    [4.5, 4.5, 18, 18])

                runtime.set_keybed_latches(0)
                before = runtime.cfg['fy']
                runtime.handle_key_event('down', 'Q', shift=True)
                runtime.step(1.0)
                runtime.handle_key_event('up', 'Q')
                self.assertAlmostEqual(runtime.cfg['fy'] - before, 0.01)

                runtime.handle_key_event('down', '1', ctrl=True)
                runtime.step(1.1)
                runtime.handle_key_event('up', '1')
                self.assertEqual(runtime.cfg['active_lut'], '1')

    def test_native_modifier_scaling_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.make_runtime(directory)
            with mock.patch.object(plasma, 'CONFIG_FILE', config_path):
                plasma._config_cache['signature'] = None
                cfg, colors = plasma.load_runtime_config()
                before = cfg['fy']
                pressed = {ord('Q')}
                plasma._dispatch_hotkeys(
                    cfg, colors, 0,
                    lambda vk, now: (vk in pressed, False),
                    lambda vk: vk == plasma.VK_SHIFT,
                    1.0,
                )
                self.assertAlmostEqual(cfg['fy'] - before, 0.1)

    def test_keybed_reset_tracks_preset_randomize_and_undo_baselines(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.make_runtime(directory)

            def randomize_once():
                generator.generate_config(7, config_path)
                return 7

            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True),
                  mock.patch.object(plasma, 'randomize_config', side_effect=randomize_once)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                startup = {name: runtime.cfg[name]
                           for name in plasma.KEYBED_PARAMETER_NAMES}
                original_lut = runtime.cfg['active_lut']
                runtime.handle_key_event('down', 'Q')
                runtime.step(1.0)
                runtime.handle_key_event('up', 'Q')
                runtime.set_keybed_latches(3)
                self.assertTrue(runtime.reset_keybed_parameters())
                self.assertEqual(runtime.keybed_latch_mask, 0)
                self.assertEqual(
                    {name: runtime.cfg[name]
                     for name in plasma.KEYBED_PARAMETER_NAMES}, startup)
                self.assertEqual(runtime.cfg['active_lut'], original_lut)

                runtime.handle_key_event('down', '1')
                runtime.step(1.1)
                runtime.handle_key_event('up', '1')
                preset = {name: runtime.cfg[name]
                          for name in plasma.KEYBED_PARAMETER_NAMES}
                runtime.handle_key_event('down', 'T')
                runtime.step(1.2)
                runtime.handle_key_event('up', 'T')
                runtime.reset_keybed_parameters()
                self.assertEqual(
                    {name: runtime.cfg[name]
                     for name in plasma.KEYBED_PARAMETER_NAMES}, preset)

                runtime.handle_key_event('down', 'P')
                runtime.step(2.0)
                runtime.handle_key_event('up', 'P')
                randomized = {name: runtime.cfg[name]
                              for name in plasma.KEYBED_PARAMETER_NAMES}
                runtime.handle_key_event('down', 'A')
                runtime.step(2.1)
                runtime.handle_key_event('up', 'A')
                runtime.reset_keybed_parameters()
                self.assertEqual(
                    {name: runtime.cfg[name]
                     for name in plasma.KEYBED_PARAMETER_NAMES}, randomized)

                runtime.set_fps(333)
                self.assertTrue(runtime.undo_randomize())
                self.assertEqual(runtime.cfg['fps'], 333)
                runtime.handle_key_event('down', 'W')
                runtime.step(2.2)
                runtime.handle_key_event('up', 'W')
                runtime.reset_keybed_parameters()
                self.assertEqual(
                    {name: runtime.cfg[name]
                     for name in plasma.KEYBED_PARAMETER_NAMES}, preset)

    def test_atomic_lut_edit_materializes_slot_zero_and_reports_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.make_runtime(directory)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                initial = json.loads(runtime.consume_lut_state_json())
                self.assertEqual(len(initial['colors']), 256)
                self.assertIsNone(runtime.consume_lut_state_json())

                runtime.cfg['active_lut'] = 'none'
                plasma.write_section('config', runtime.cfg)
                undo_depth = len(runtime.random_history)
                colors = ['112233'] * plasma.LUT_SIZE
                colors[17] = 'ABCDEF'
                revision = runtime.replace_lut_json(json.dumps(colors))
                self.assertEqual(runtime.cfg['active_lut'], '0')
                self.assertEqual(plasma.load_lut('0'), colors)
                self.assertEqual(len(runtime.random_history), undo_depth)
                state = json.loads(runtime.consume_lut_state_json())
                self.assertEqual(state['colors'][17], 'ABCDEF')
                self.assertEqual(state['slot'], '0')
                self.assertEqual(state['revision'], revision)
                metrics = json.loads(runtime.metrics_json())
                self.assertEqual(metrics['lutSlot'], '0')
                self.assertEqual(metrics['lutRevision'], revision)

                with open(config_path, 'rb') as handle:
                    persisted = handle.read()
                with self.assertRaises(ValueError):
                    runtime.replace_lut_json(json.dumps(colors[:-1]))
                with open(config_path, 'rb') as handle:
                    self.assertEqual(handle.read(), persisted)

    def test_resize_commit_metric_excludes_ordinary_fits(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = self.make_runtime(directory)
            with (mock.patch.object(plasma, 'CONFIG_FILE', config_path),
                  mock.patch.object(plasma, 'RUNNING_IN_BROWSER', True)):
                plasma._config_cache['signature'] = None
                runtime = plasma.BrowserRuntime(8, 4)
                runtime.set_size(10, 5)
                runtime.set_size(12, 6, committed=True)
                self.assertEqual(
                    json.loads(runtime.metrics_json())['resizeCommits'], 1)


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
