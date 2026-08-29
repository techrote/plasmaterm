"""Focused validation for PlasmaTerm deterministic configuration generation."""

import configparser
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import plasma
import plasma_config_gen as generator


HEX_COLOR = re.compile(r'^[0-9A-F]{6}$')


class DeterministicGenerationTests(unittest.TestCase):
    def test_same_slot_is_byte_identical(self):
        self.assertEqual(generator.generate_config_text(17),
                         generator.generate_config_text(17))

    def test_different_slots_are_different(self):
        self.assertNotEqual(generator.generate_config_text(17),
                            generator.generate_config_text(18))

    def test_slot_generation_is_order_independent(self):
        expected = {slot: generator.generate_profile(slot, str(slot % 10))
                    for slot in (17, 2, 99)}
        actual = {slot: generator.generate_profile(slot, str(slot % 10))
                  for slot in (99, 17, 2)}
        self.assertEqual(expected, actual)

    def test_new_python_processes_are_identical(self):
        expression = (
            'import hashlib, plasma_config_gen as g; '
            'print(hashlib.sha256(g.generate_config_text(37).encode()).hexdigest())'
        )
        command = [sys.executable, '-c', expression]
        first = subprocess.check_output(command, cwd=HERE, text=True).strip()
        second = subprocess.check_output(command, cwd=HERE, text=True).strip()
        local = hashlib.sha256(
            generator.generate_config_text(37).encode()).hexdigest()
        self.assertEqual(first, second)
        self.assertEqual(first, local)

    def test_generated_profile_envelope_across_many_slots(self):
        for slot in range(128):
            profile, lut = generator.generate_profile(slot, str(slot % 10))
            self.assertGreaterEqual(profile['speed'], generator.SPEED_MIN)
            self.assertLessEqual(profile['speed'], generator.SPEED_MAX)
            self.assertGreaterEqual(profile['freq-x'], generator.FREQUENCY_MIN)
            self.assertLessEqual(profile['freq-x'], generator.FREQUENCY_MAX)
            self.assertGreaterEqual(profile['freq-y'], generator.FREQUENCY_MIN)
            self.assertLessEqual(profile['freq-y'], generator.FREQUENCY_MAX)
            self.assertGreaterEqual(
                abs(profile['freq-x'] - profile['freq-y']), 0.039)
            self.assertGreaterEqual(profile['radius'], generator.RADIUS_MIN)
            self.assertLessEqual(profile['radius'], generator.RADIUS_MAX)
            self.assertLessEqual(abs(profile['hue-shift']),
                                 generator.HUE_SHIFT_MAX)
            self.assertEqual(profile['palette-size'], 256)
            self.assertEqual(profile['fps'], 40.0)
            self.assertGreaterEqual(profile['hue-start'], 0.0)
            self.assertLess(profile['hue-start'], 360.0)
            self.assertGreaterEqual(profile['hue-end'], 0.0)
            self.assertLess(profile['hue-end'], 360.0)

            self.assertEqual(len(lut), generator.LUT_SIZE)
            self.assertTrue(all(HEX_COLOR.fullmatch(color) for color in lut))
            self.assertGreaterEqual(len(set(lut)), 200)
            brightness = [max(int(color[index:index + 2], 16)
                              for index in (0, 2, 4)) for color in lut]
            self.assertGreaterEqual(max(brightness) - min(brightness), 150)

            rgb = [tuple(int(color[index:index + 2], 16)
                         for index in (0, 2, 4)) for color in lut]
            largest_step = max(
                max(abs(a - b) for a, b in zip(rgb[index],
                                               rgb[(index + 1) % len(rgb)]))
                for index in range(len(rgb)))
            self.assertLessEqual(largest_step, 24)

    def test_complete_config_format(self):
        parser = configparser.ConfigParser()
        parser.read_string(generator.generate_config_text(12))
        self.assertEqual(len(parser['config']), 10)
        for index in range(10):
            self.assertTrue(parser.has_section(f'preset-{index}'))
            self.assertTrue(parser.has_section(f'lut-{index}'))
            colors = parser.get(f'lut-{index}', 'colors').split()
            self.assertEqual(len(colors), 256)
            self.assertTrue(all(HEX_COLOR.fullmatch(color)
                                for color in colors))


class BootstrapAndPersistenceTests(unittest.TestCase):
    def test_missing_config_is_generated_and_loadable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'plasma.conf')
            with mock.patch.object(plasma, 'CONFIG_FILE', path):
                self.assertTrue(plasma.ensure_config_file())
                self.assertTrue(os.path.isfile(path))
                config, colors = plasma.load_runtime_config()
                self.assertEqual(config['palette_size'], 256)
                self.assertEqual(config['fps'], 40.0)
                self.assertEqual(len(colors), 256)

    def test_existing_config_is_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'plasma.conf')
            original = b'user-owned config bytes\n'
            with open(path, 'wb') as handle:
                handle.write(original)
            with mock.patch.object(plasma, 'CONFIG_FILE', path):
                self.assertFalse(plasma.ensure_config_file())
            with open(path, 'rb') as handle:
                self.assertEqual(handle.read(), original)

    def test_saved_preset_contains_exact_values_without_generator_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'plasma.conf')
            generator.generate_config(4, path)
            with mock.patch.object(plasma, 'CONFIG_FILE', path):
                config, _ = plasma.load_runtime_config()
                config.update({
                    'speed': 1.234567,
                    'hue_shift': -23.75,
                    'fx': 0.314159,
                    'fy': 0.271828,
                    'rad': 0.654321,
                    'hue_start': 12.5,
                    'hue_end': 278.25,
                })
                plasma.write_section('preset-6', config)
                with mock.patch.dict(sys.modules, {'plasma_config_gen': None}):
                    loaded = plasma.load_preset(6)
                self.assertEqual(loaded, config)


if __name__ == '__main__':
    unittest.main()
