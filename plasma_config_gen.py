"""Deterministic, constrained configuration generator for PlasmaTerm.

Generation provenance (version, master seed, slot) is deliberately separate
from runtime persistence. The generated file contains fully resolved values;
normal PlasmaTerm preset saves never depend on this module.

Increment GENERATOR_VERSION whenever generation behaviour changes in a way
that should define a new procedural configuration family.
"""

import argparse
import hashlib
import math
import os
import tempfile


GENERATOR_VERSION = 2
MASTER_SEED = 'PlasmaTerm/default-family/2026-08-29'
DEFAULT_SLOT = 0

PROFILE_COUNT = 10
LUT_SIZE = 256
PALETTE_SIZE = 256
FPS = 40.0

FREQUENCY_MIN = 0.16
FREQUENCY_MAX = 0.68
MIN_FREQUENCY_SEPARATION = 0.04
RADIUS_MIN = 0.28
RADIUS_MAX = 0.95
SPEED_MIN = 0.35
SPEED_MAX = 1.45
HUE_SHIFT_MAX = 60.0

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_PATH = os.path.join(SCRIPT_DIR, 'plasma.conf')
MASK_64 = (1 << 64) - 1


class StablePRNG:
    """Small explicitly specified SplitMix64 generator.

    Using a local PRNG avoids depending on Python's hash randomisation or on
    implementation details of higher-level random distributions.
    """

    def __init__(self, seed):
        self.state = seed & MASK_64

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK_64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK_64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK_64
        return (value ^ (value >> 31)) & MASK_64

    def random(self):
        return (self.next_u64() >> 11) / float(1 << 53)

    def uniform(self, low, high):
        return low + (high - low) * self.random()

    def choice(self, values):
        return values[self.next_u64() % len(values)]


def _validate_slot(slot):
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise ValueError('slot must be a non-negative integer')
    return slot


def derive_profile_seed(slot):
    """Derive one order-independent profile seed with SHA-256."""
    slot = _validate_slot(slot)
    material = (
        'PlasmaTerm deterministic configuration\n'
        f'version={GENERATOR_VERSION}\n'
        f'master-seed={MASTER_SEED}\n'
        f'slot={slot}\n'
    ).encode('utf-8')
    digest = hashlib.sha256(material).digest()
    return int.from_bytes(digest[:8], 'big')


def _clamp(value, low, high):
    return max(low, min(high, value))


def _rounded(value):
    return round(value, 6)


def _hsv_to_hex(hue_degrees, saturation, value):
    hue = (hue_degrees % 360.0) / 60.0
    segment = int(hue)
    fraction = hue - segment
    p = value * (1.0 - saturation)
    q = value * (1.0 - saturation * fraction)
    t = value * (1.0 - saturation * (1.0 - fraction))
    channels = (
        (value, t, p),
        (q, value, p),
        (p, value, t),
        (p, q, value),
        (t, p, value),
        (value, p, q),
    )[segment % 6]
    rgb = [int(round(_clamp(channel, 0.0, 1.0) * 255))
           for channel in channels]
    return ''.join(f'{channel:02X}' for channel in rgb)


def _smoothstep(value):
    return value * value * (3.0 - 2.0 * value)


def _interpolate_anchors(anchors, position):
    segment_count = len(anchors) - 1
    scaled = position * segment_count
    segment = min(segment_count - 1, int(scaled))
    amount = _smoothstep(scaled - segment)
    return anchors[segment] + (anchors[segment + 1] - anchors[segment]) * amount


def _generate_lut(rng, base_hue, hue_span, direction):
    """Generate a smooth closed HSV curve, compiled to 256 RGB entries."""
    saturation_low = rng.uniform(0.58, 0.78)
    saturation_high = rng.uniform(0.88, 1.0)
    value_low = rng.uniform(0.035, 0.16)
    value_mid_a = rng.uniform(0.48, 0.76)
    value_high = rng.uniform(0.88, 1.0)
    value_mid_b = rng.uniform(0.38, 0.68)

    hue_anchors = [
        base_hue,
        base_hue + direction * hue_span * rng.uniform(0.28, 0.42),
        base_hue + direction * hue_span,
        base_hue + direction * hue_span * rng.uniform(0.42, 0.68),
        base_hue,
    ]
    saturation_anchors = [
        saturation_low,
        saturation_high,
        rng.uniform(0.72, 0.96),
        saturation_high,
        saturation_low,
    ]
    value_anchors = [
        value_low,
        value_mid_a,
        value_high,
        value_mid_b,
        value_low,
    ]

    colors = []
    for index in range(LUT_SIZE):
        # Divide by LUT_SIZE so the final stored entry approaches, but does not
        # duplicate, the first. The implicit wrap remains visually continuous.
        position = index / LUT_SIZE
        hue = _interpolate_anchors(hue_anchors, position)
        saturation = _interpolate_anchors(saturation_anchors, position)
        value = _interpolate_anchors(value_anchors, position)
        colors.append(_hsv_to_hex(hue, saturation, value))
    return colors


def _generate_calm_rainbow_lut():
    """Return a smooth closed rainbow with a slow brightness swell."""
    colors = []
    for index in range(LUT_SIZE):
        position = index / LUT_SIZE
        value = 0.18 + 0.82 * (0.5 - 0.5 * math.cos(2.0 * math.pi * position))
        colors.append(_hsv_to_hex(position * 360.0, 0.78, value))
    return colors


def generate_profile(slot, lut_slot='0'):
    """Return one exact parameter mapping and its deterministic LUT."""
    slot = _validate_slot(slot)
    lut_slot = str(lut_slot)
    if len(lut_slot) != 1 or lut_slot not in '0123456789':
        raise ValueError('lut_slot must be a single digit from 0 to 9')
    if slot == DEFAULT_SLOT:
        return ({
            'speed': 0.35,
            'hue-shift': 2.0,
            'freq-x': 0.24,
            'freq-y': 0.32,
            'radius': 0.48,
            'palette-size': PALETTE_SIZE,
            'hue-start': 0.0,
            'hue-end': 360.0 - (360.0 / LUT_SIZE),
            'fps': FPS,
            'active-lut': lut_slot,
        }, _generate_calm_rainbow_lut())
    rng = StablePRNG(derive_profile_seed(slot))

    # Frequencies share a latent scale but are deliberately separated to avoid
    # near-identical X/Y fields and visually flat/simple interference patterns.
    detail = (rng.random() + rng.random()) * 0.5
    centre = 0.25 + detail * 0.27
    separation = rng.uniform(0.055, 0.17)
    jitter_x = rng.uniform(-0.022, 0.022)
    jitter_y = rng.uniform(-0.022, 0.022)
    if rng.random() < 0.5:
        freq_x = centre - separation * 0.5 + jitter_x
        freq_y = centre + separation * 0.5 + jitter_y
    else:
        freq_x = centre + separation * 0.5 + jitter_x
        freq_y = centre - separation * 0.5 + jitter_y
    freq_x = _clamp(freq_x, FREQUENCY_MIN, FREQUENCY_MAX)
    freq_y = _clamp(freq_y, FREQUENCY_MIN, FREQUENCY_MAX)
    if abs(freq_x - freq_y) < MIN_FREQUENCY_SEPARATION:
        adjustment = (MIN_FREQUENCY_SEPARATION
                      - abs(freq_x - freq_y)) * 0.5 + 0.002
        if freq_x >= freq_y:
            freq_x += adjustment
            freq_y -= adjustment
        else:
            freq_x -= adjustment
            freq_y += adjustment
        freq_x = _clamp(freq_x, FREQUENCY_MIN, FREQUENCY_MAX)
        freq_y = _clamp(freq_y, FREQUENCY_MIN, FREQUENCY_MAX)

    activity = (rng.random() + rng.random()) * 0.5
    speed = 0.42 + activity * 1.02 - detail * 0.10
    speed = _clamp(speed, SPEED_MIN, SPEED_MAX)
    radius = 0.80 - detail * 0.24 + rng.uniform(-0.18, 0.18)
    radius = _clamp(radius, RADIUS_MIN, RADIUS_MAX)

    base_hue = rng.uniform(0.0, 360.0)
    palette_family = rng.random()
    if palette_family < 0.52:
        hue_span = rng.uniform(70.0, 145.0)
    elif palette_family < 0.88:
        hue_span = rng.uniform(145.0, 245.0)
    else:
        hue_span = rng.uniform(245.0, 330.0)
    direction = rng.choice((-1.0, 1.0))
    hue_shift = direction * (6.0 + activity * 49.0)
    if rng.random() < 0.10:
        hue_shift = 0.0

    profile = {
        'speed': _rounded(speed),
        'hue-shift': _rounded(hue_shift),
        'freq-x': _rounded(freq_x),
        'freq-y': _rounded(freq_y),
        'radius': _rounded(radius),
        'palette-size': PALETTE_SIZE,
        'hue-start': _rounded(base_hue % 360.0),
        'hue-end': _rounded((base_hue + hue_span) % 360.0),
        'fps': FPS,
        'active-lut': lut_slot,
    }
    lut = _generate_lut(rng, base_hue, hue_span, direction)
    return profile, lut


def _format_value(value):
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = f'{value:.6f}'.rstrip('0').rstrip('.')
        return text + '.0' if '.' not in text else text
    return str(value)


def _format_profile_section(name, profile):
    lines = [f'[{name}]']
    for key in ('speed', 'hue-shift', 'freq-x', 'freq-y', 'radius',
                'palette-size', 'hue-start', 'hue-end', 'fps', 'active-lut'):
        lines.append(f'{key} = {_format_value(profile[key])}')
    return '\n'.join(lines)


def _format_lut_section(index, source_slot, colors):
    rows = [' '.join(colors[start:start + 8])
            for start in range(0, LUT_SIZE, 8)]
    return (f'# Deterministic LUT {index}; procedural source slot {source_slot}\n'
            f'[lut-{index}]\n'
            'colors =\n    ' + '\n    '.join(rows))


def generate_config_text(slot=DEFAULT_SLOT):
    """Return a complete deterministic config bank beginning at `slot`.

    The active config and preset 0 correspond to the requested base slot.
    Presets 1-9 correspond to the next nine independently derived slots.
    """
    slot = _validate_slot(slot)
    profiles = []
    luts = []
    for index in range(PROFILE_COUNT):
        source_slot = slot + index
        profile, lut = generate_profile(source_slot, str(index))
        profiles.append(profile)
        luts.append(lut)

    parts = [
        '# PlasmaTerm deterministic generated configuration',
        f'# generator-version = {GENERATOR_VERSION}',
        f'# master-seed = {MASTER_SEED}',
        f'# base-slot = {slot}',
        '# Values below are resolved state. Preset saving does not depend on',
        '# generator provenance, the master seed, or the source slot.',
        '',
        _format_profile_section('config', profiles[0]),
        '',
        '# Invisible controls while running:',
        '#   0-9 load presets; Alt+S saves the last loaded preset',
        '#   Ctrl+0-9 loads LUTs; Q/A through O/L adjust parameters',
        '#   Shift uses 10x steps; Ctrl uses 100x steps',
    ]
    for index, profile in enumerate(profiles):
        parts.extend(('', f'# Procedural source slot {slot + index}',
                      _format_profile_section(f'preset-{index}', profile)))
    for index, colors in enumerate(luts):
        parts.extend(('', _format_lut_section(index, slot + index, colors)))
    return '\n'.join(parts) + '\n'


def generate_config(slot=DEFAULT_SLOT, output_path=DEFAULT_OUTPUT_PATH):
    """Atomically write one complete deterministic PlasmaTerm config."""
    contents = generate_config_text(slot)
    destination = os.path.abspath(os.fspath(output_path))
    directory = os.path.dirname(destination)
    if not os.path.isdir(directory):
        raise FileNotFoundError(f'output directory does not exist: {directory}')

    fd, temporary = tempfile.mkstemp(
        prefix='.plasma-config-', suffix='.tmp', dir=directory, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return destination


def main():
    parser = argparse.ArgumentParser(
        description='Generate a deterministic PlasmaTerm plasma.conf.')
    parser.add_argument('slot', nargs='?', type=int, default=DEFAULT_SLOT,
                        help='non-negative base profile slot (default: 0)')
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT_PATH,
                        help='output file (default: plasma.conf beside script)')
    args = parser.parse_args()
    try:
        destination = generate_config(args.slot, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f'Generated {destination} from slot {args.slot}.')


if __name__ == '__main__':
    main()
