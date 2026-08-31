import argparse
import ctypes
import json
import math
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from configparser import ConfigParser, Error as ConfigError

if os.name == 'nt':
    import msvcrt
else:
    msvcrt = None

# --- Config file support ---
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plasma.conf')
_config_cache = {'signature': None}
LUT_KEYS = '0123456789'
LUT_SIZE = 256
MAX_PALETTE_SIZE = 1024
RUNNING_IN_BROWSER = sys.platform == 'emscripten'
_browser_terminal_size = os.terminal_size((80, 24))

def set_browser_terminal_size(columns, lines):
    """Update the terminal dimensions supplied by the browser host."""
    global _browser_terminal_size
    columns = max(2, int(columns))
    lines = max(2, int(lines))
    _browser_terminal_size = os.terminal_size((columns, lines))

def get_plasmaterm_size():
    """Return host dimensions without changing native terminal behaviour."""
    if RUNNING_IN_BROWSER:
        return _browser_terminal_size
    return os.get_terminal_size()

def ensure_config_file():
    """Generate a complete default config only when plasma.conf is absent."""
    if os.path.isfile(CONFIG_FILE):
        return False
    try:
        from plasma_config_gen import generate_config
        generate_config(output_path=CONFIG_FILE)
    except Exception as exc:
        raise RuntimeError(
            f'{CONFIG_FILE} is missing and deterministic generation failed: '
            f'{exc}') from exc
    if not os.path.isfile(CONFIG_FILE):
        raise RuntimeError(
            f'configuration generator did not create {CONFIG_FILE}')
    return True

# Compact-keyboard layout. Each upper-row key increases a value and the key
# immediately below it decreases the same value. Shift is 10x and Ctrl is
# 100x. Alt+S is reserved for saving the active preset slot.
PARAMETER_KEYS = {
    'Q': ('fy', 0.01),
    'A': ('fy', -0.01),
    'W': ('fx', 0.01),
    'S': ('fx', -0.01),
    'E': ('hue_start', 1.0),
    'D': ('hue_start', -1.0),
    'R': ('hue_end', 1.0),
    'F': ('hue_end', -1.0),
    'T': ('speed', 0.03),
    'G': ('speed', -0.03),
    'Y': ('hue_shift', 0.5),
    'H': ('hue_shift', -0.5),
    'U': ('rad', 0.01),
    'J': ('rad', -0.01),
}
LUT_CYCLE_KEYS = {'I': 1, 'K': -1}
ENERGY_PARAMETERS = (
    ('fy', 0.003, 'freq-y'),
    ('fx', 0.003, 'freq-x'),
    ('speed', 0.02, 'speed'),
    ('hue_shift', 0.005, 'hue-shift'),
    ('rad', 0.005, 'radius'),
)
ENERGY_WAVES = frozenset(
    ('sine', 'smooth-triangle', 'loop-noise', 'wander-noise'))
WEB_FPS_OPTIONS = (24.0, 30.0, 60.0, 120.0, 144.0, 240.0)
WEB_KEYBED_KEYS = frozenset(('Q', 'A', 'W', 'S', 'T', 'G', 'Y', 'H',
                             'U', 'J'))
KEYBED_PARAMETER_NAMES = ('fy', 'fx', 'speed', 'hue_shift', 'rad')
RANDOMIZE_KEY = 'P'
RANDOM_SLOT_LIMIT = 2 ** 31

_key_down = {}
_key_repeat_at = {}
_keys_suppressed_until_release = set()
KEY_REPEAT_DELAY = 0.35
KEY_REPEAT_INTERVAL = 0.06

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_ALT = 0x12
VIEWPORT_KEYBOARD_OWNER = 'viewport'

def _command_virtual_keys():
    """Return every key whose transient state belongs to PlasmaTerm."""
    return ({ord(key) for key in LUT_KEYS}
            | {ord(key) for key in PARAMETER_KEYS}
            | {ord(key) for key in LUT_CYCLE_KEYS}
            | {ord(RANDOMIZE_KEY)}
            | {VK_SHIFT, VK_CONTROL, VK_ALT})

def clear_transient_keyboard_state(suppress_held=False):
    """Clear input state that cannot survive an ownership/focus boundary.

    When requested, keys physically held at the boundary are ignored until
    released. This prevents a key held across Alt-Tab or a modal transition
    from becoming a new press when the viewport regains ownership.
    """
    _key_down.clear()
    _key_repeat_at.clear()
    _keys_suppressed_until_release.clear()

    if suppress_held and os.name == 'nt':
        for vk in _command_virtual_keys():
            state = ctypes.windll.user32.GetAsyncKeyState(vk)
            if state & 0x8000:
                _keys_suppressed_until_release.add(vk)

class ViewportKeyboardOwnership:
    """Single authority for whether PlasmaTerm may dispatch keyboard input.

    Document focus and the logical UI owner are deliberately separate. Future
    text fields, dialogs, or other UI can call set_owner() while active, then
    return ownership to VIEWPORT_KEYBOARD_OWNER when finished.
    """

    def __init__(self):
        self.document_window = None
        self.document_focused = False
        self.terminal_document_focused = True
        self._focus_sequence_tail = ''
        self.owner = VIEWPORT_KEYBOARD_OWNER
        self._previously_owned = False

    def bind_to_current_document(self):
        """Bind this run to the currently foreground terminal window."""
        if os.name != 'nt':
            return
        self.document_window = ctypes.windll.user32.GetForegroundWindow()
        self.refresh_document_focus()

    def viewport_has_keyboard_ownership(self):
        return (self.document_focused
                and self.owner == VIEWPORT_KEYBOARD_OWNER)

    def set_owner(self, owner):
        """Assign logical keyboard ownership; use 'viewport' to restore it."""
        self.owner = owner
        self._handle_ownership_transition()

    def refresh_document_focus(self):
        """Refresh physical focus and return viewport ownership state."""
        self._consume_terminal_focus_events()
        if os.name != 'nt' or not self.document_window:
            self.document_focused = False
        else:
            foreground = ctypes.windll.user32.GetForegroundWindow()
            self.document_focused = (foreground == self.document_window
                                     and self.terminal_document_focused)
        self._handle_ownership_transition()
        return self.viewport_has_keyboard_ownership()

    def _consume_terminal_focus_events(self):
        """Consume DECSET 1004 focus reports and discard other input bytes.

        Native HWND focus handles Alt-Tab and other-window changes. Terminal
        focus reporting adds document/tab focus within one Windows Terminal
        window, where several tabs share the same HWND.
        """
        if os.name != 'nt' or msvcrt is None:
            return
        while msvcrt.kbhit():
            char = msvcrt.getwch()
            if char == '\x03':
                raise KeyboardInterrupt
            self._focus_sequence_tail = (self._focus_sequence_tail + char)[-3:]
            if self._focus_sequence_tail == '\x1b[I':
                self.terminal_document_focused = True
                self._focus_sequence_tail = ''
            elif self._focus_sequence_tail == '\x1b[O':
                self.terminal_document_focused = False
                self._focus_sequence_tail = ''

    def revoke(self):
        """Revoke ownership and clear all transient input immediately."""
        self.owner = None
        self._handle_ownership_transition()

    def _handle_ownership_transition(self):
        owned = self.viewport_has_keyboard_ownership()
        if owned != self._previously_owned:
            # Reset on both loss and regain. The regain reset also catches keys
            # first pressed while PlasmaTerm was unfocused.
            clear_transient_keyboard_state(suppress_held=True)
        self._previously_owned = owned

_keyboard_ownership = ViewportKeyboardOwnership()

def viewport_has_keyboard_ownership():
    """Public ownership query for the central keyboard dispatch gate."""
    return _keyboard_ownership.viewport_has_keyboard_ownership()

def set_keyboard_input_owner(owner):
    """Future UI hook: claim input, or pass 'viewport' to restore it."""
    _keyboard_ownership.set_owner(owner)

CONFIG_KEYS = (
    ('speed', 'speed'),
    ('hue_shift', 'hue-shift'),
    ('fx', 'freq-x'),
    ('fy', 'freq-y'),
    ('rad', 'radius'),
    ('palette_size', 'palette-size'),
    ('hue_start', 'hue-start'),
    ('hue_end', 'hue-end'),
    ('fps', 'fps'),
    ('active_lut', 'active-lut'),
)

def validate_config(values):
    if not 2 <= values['palette_size'] <= MAX_PALETTE_SIZE:
        raise ValueError(
            f'palette-size must be between 2 and {MAX_PALETTE_SIZE}')
    if not 1.0 <= values['fps'] <= 1000.0:
        raise ValueError('fps must be between 1 and 1000')
    if values['active_lut'] not in ('none', *LUT_KEYS):
        raise ValueError('active-lut must be none or a number from 0 to 9')
    if not all(math.isfinite(value) for key, value in values.items()
               if key not in ('palette_size', 'active_lut')):
        raise ValueError('all numeric config values must be finite')
    return values

def load_config(parser=None, section='config'):
    """Load and validate the live settings from plasma.conf."""
    if parser is None:
        parser = ConfigParser()
        if not parser.read(CONFIG_FILE, encoding='utf-8'):
            raise FileNotFoundError(CONFIG_FILE)

    values = {
        'speed': parser.getfloat(section, 'speed', fallback=1.0),
        'hue_shift': parser.getfloat(section, 'hue-shift', fallback=0.0),
        'fx': parser.getfloat(section, 'freq-x', fallback=0.35),
        'fy': parser.getfloat(section, 'freq-y', fallback=0.45),
        'rad': parser.getfloat(section, 'radius', fallback=0.6),
        'palette_size': parser.getint(section, 'palette-size', fallback=256),
        'hue_start': parser.getfloat(section, 'hue-start', fallback=0.0),
        'hue_end': parser.getfloat(section, 'hue-end', fallback=360.0),
        'fps': parser.getfloat(section, 'fps', fallback=40.0),
        'active_lut': parser.get(section, 'active-lut', fallback='none').lower(),
    }
    return validate_config(values)

def check_config():
    """Return the config file signature when it has changed, otherwise None."""
    try:
        stat = os.stat(CONFIG_FILE)
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature != _config_cache['signature']:
            return signature
    except OSError:
        pass
    return None

def _section_text(values):
    """Serialize one config/preset section without rewriting the whole file."""
    lines = []
    for internal_name, file_name in CONFIG_KEYS:
        value = values[internal_name]
        if internal_name == 'palette_size':
            value = int(value)
        lines.append(f'{file_name} = {value}')
    return '\n'.join(lines)

def _replace_section_text(original, section, values):
    """Return config text with one INI section added or replaced."""
    pattern = re.compile(
        rf'^\[{re.escape(section)}\][ \t]*\r?\n.*?(?=^\[|\Z)',
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(original)
    if match:
        replacement = match.group(0)
        for internal_name, file_name in CONFIG_KEYS:
            value = values[internal_name]
            if internal_name == 'palette_size':
                value = int(value)
            key_pattern = re.compile(
                rf'^{re.escape(file_name)}[ \t]*=.*$', re.MULTILINE)
            new_line = f'{file_name} = {value}'
            if key_pattern.search(replacement):
                replacement = key_pattern.sub(new_line, replacement, count=1)
            else:
                replacement = replacement.rstrip() + '\n' + new_line + '\n'
        updated = original[:match.start()] + replacement + original[match.end():]
    else:
        replacement = f'[{section}]\n{_section_text(values)}\n'
        updated = original.rstrip() + '\n\n' + replacement
    return updated


def _replace_lut_text(original, slot, colors):
    """Return config text with one fixed-size LUT added or replaced."""
    if slot not in LUT_KEYS or len(colors) != LUT_SIZE:
        raise ValueError('LUT writes require a valid slot and 256 colours')
    rows = [' '.join(colors[i:i + 8]) for i in range(0, LUT_SIZE, 8)]
    replacement = (f'[lut-{slot}]\ncolors =\n    '
                   + '\n    '.join(rows) + '\n')
    pattern = re.compile(
        rf'^\[lut-{re.escape(slot)}\][ \t]*\r?\n.*?'
        rf'(?=^# Placeholder palette:|^\[|\Z)',
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(original)
    if match:
        return original[:match.start()] + replacement + original[match.end():]
    return original.rstrip() + '\n\n' + replacement


def _write_config_text(updated):
    """Atomically replace plasma.conf with already-rendered text."""
    config_dir = os.path.dirname(CONFIG_FILE)
    fd, temp_path = tempfile.mkstemp(
        prefix='.plasma-', suffix='.tmp', dir=config_dir, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, CONFIG_FILE)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def write_section(section, values):
    """Atomically add or replace one INI section while preserving comments."""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as handle:
        original = handle.read()
    _write_config_text(_replace_section_text(original, section, values))


def write_lut(slot, colors):
    """Atomically add or replace one fixed-size hexadecimal LUT section."""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as handle:
        original = handle.read()
    _write_config_text(_replace_lut_text(original, slot, colors))


def write_lut_and_config(slot, colors, values):
    """Atomically persist a LUT and its activating config transaction."""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as handle:
        original = handle.read()
    updated = _replace_lut_text(original, slot, colors)
    updated = _replace_section_text(updated, 'config', values)
    _write_config_text(updated)

def load_lut(slot, parser=None):
    """Load and validate one fixed 256-colour hexadecimal LUT."""
    if slot not in LUT_KEYS:
        raise ValueError('invalid LUT slot')
    if parser is None:
        parser = ConfigParser()
        if not parser.read(CONFIG_FILE, encoding='utf-8'):
            raise FileNotFoundError(CONFIG_FILE)
    raw = parser.get(f'lut-{slot}', 'colors')
    colors = raw.replace(',', ' ').split()
    if len(colors) != LUT_SIZE:
        raise ValueError(f'lut-{slot} must contain exactly 256 colours')
    for color in colors:
        if len(color) != 6 or any(c not in '0123456789abcdefABCDEF'
                                  for c in color):
            raise ValueError(f'invalid RGB value in lut-{slot}: {color}')
    return [color.upper() for color in colors]

def resolve_palette(cfg, parser=None):
    """Return either the active stored LUT or the procedural hue palette."""
    if cfg['active_lut'] == 'none':
        return build_palette(
            cfg['palette_size'], cfg['hue_start'], cfg['hue_end'])
    return load_lut(cfg['active_lut'], parser)

def load_runtime_config():
    """Load parameters and the active LUT as one validated transaction."""
    parser = ConfigParser()
    if not parser.read(CONFIG_FILE, encoding='utf-8'):
        raise FileNotFoundError(CONFIG_FILE)
    cfg = load_config(parser)
    return cfg, resolve_palette(cfg, parser)

def load_preset(slot):
    """Load a complete preset, returning None when the slot is empty/invalid."""
    parser = ConfigParser()
    if not parser.read(CONFIG_FILE, encoding='utf-8'):
        return None
    section = f'preset-{slot}'
    if not parser.has_section(section):
        return None
    try:
        return load_config(parser, section)
    except (ConfigError, ValueError):
        return None

def resample_palette(colors, size=LUT_SIZE):
    """Resize a palette by nearest-neighbour sampling for LUT saves."""
    if len(colors) == size:
        return list(colors)
    if len(colors) < 2:
        raise ValueError('cannot resample an empty palette')
    return [colors[round(i * (len(colors) - 1) / (size - 1))]
            for i in range(size)]

def _poll_virtual_key(vk, now):
    """Return (pressed_now, repeat_now) for one Windows virtual key."""
    state = ctypes.windll.user32.GetAsyncKeyState(vk)
    down = bool(state & 0x8000)
    pressed_since_poll = bool(state & 0x0001)

    if vk in _keys_suppressed_until_release:
        if not down:
            _keys_suppressed_until_release.discard(vk)
        _key_down[vk] = False
        _key_repeat_at.pop(vk, None)
        return False, False

    was_down = _key_down.get(vk, False)
    pressed_now = pressed_since_poll or (down and not was_down)
    repeat_now = False

    if pressed_now:
        _key_repeat_at[vk] = now + KEY_REPEAT_DELAY
    elif down and now >= _key_repeat_at.get(vk, float('inf')):
        repeat_now = True
        _key_repeat_at[vk] = now + KEY_REPEAT_INTERVAL
    elif not down:
        _key_repeat_at.pop(vk, None)

    _key_down[vk] = down
    return pressed_now, repeat_now

def _modifier_is_down(vk):
    """Read a modifier, respecting the post-ownership release latch."""
    state = ctypes.windll.user32.GetAsyncKeyState(vk)
    down = bool(state & 0x8000)
    if vk in _keys_suppressed_until_release:
        if not down:
            _keys_suppressed_until_release.discard(vk)
        return False
    return down

def _apply_parameter_delta(cfg, key, factor):
    """Apply one bounded parameter-key adjustment."""
    name, step = PARAMETER_KEYS[key]
    value = cfg[name] + step * factor
    if name == 'palette_size':
        value = max(2, min(MAX_PALETTE_SIZE, int(round(value))))
    elif name == 'fps':
        value = max(1.0, min(1000.0, round(value, 10)))
    else:
        value = round(value, 10)
    cfg[name] = value


def _noise_gradient(index):
    """Return a deterministic signed gradient for an integer lattice point."""
    value = math.sin(int(index) * 127.1 + 311.7) * 43758.5453123
    return (value - math.floor(value)) * 2.0 - 1.0


def _gradient_noise(position, period=None):
    """Return smooth deterministic 1D gradient noise near the range -1..1."""
    lattice = math.floor(position)
    fraction = position - lattice
    left_index = lattice if period is None else lattice % period
    right_index = lattice + 1 if period is None else (lattice + 1) % period
    left = _noise_gradient(left_index) * fraction
    right = _noise_gradient(right_index) * (fraction - 1.0)
    fade = fraction ** 3 * (fraction * (fraction * 6.0 - 15.0) + 10.0)
    return max(-1.0, min(1.0, (left + (right - left) * fade) * 2.5))


def energy_wave_value(wave, position):
    """Return a normalized oscillator sample for a signed phase position."""
    if wave not in ENERGY_WAVES:
        raise ValueError(f'unsupported energy wave: {wave}')
    position = float(position)
    phase = position % 1.0
    if wave == 'sine':
        return math.sin(phase * 2.0 * math.pi)
    if wave == 'smooth-triangle':
        triangle = 1.0 - 4.0 * abs(phase - 0.5)
        normalized = (triangle + 1.0) * 0.5
        smoothed = normalized * normalized * (3.0 - 2.0 * normalized)
        return smoothed * 2.0 - 1.0
    if wave == 'loop-noise':
        return _gradient_noise(phase * 4.0, period=4)
    return _gradient_noise(position)


def randomize_config(slot=None):
    """Regenerate the complete configuration from one random generator slot.

    Native Python invokes the generator as a safe absolute-path command. The
    browser cannot spawn processes, so it uses the generator's existing API.
    In both cases the generator owns the atomic replacement operation.
    """
    if slot is None:
        slot = secrets.randbelow(RANDOM_SLOT_LIMIT)
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise ValueError('slot must be a non-negative integer')

    generator_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'plasma_config_gen.py')
    if RUNNING_IN_BROWSER:
        from plasma_config_gen import generate_config
        generate_config(slot, output_path=CONFIG_FILE)
    else:
        subprocess.run(
            [sys.executable, generator_path, str(slot),
             '--output', os.path.abspath(CONFIG_FILE)],
            check=True,
        )
    return slot

def _dispatch_hotkeys(cfg, colors, selected_preset, poll_key,
                      modifier_is_down, now, parameter_factor=None,
                      action_callback=None):
    """Apply shared command semantics using a host-specific logical key API."""
    shift = modifier_is_down(VK_SHIFT)
    ctrl = modifier_is_down(VK_CONTROL)
    alt = modifier_is_down(VK_ALT)
    native_factor = 100 if ctrl else 10 if shift else 1
    changed = False
    palette_changed = False

    def report_action(action):
        if action_callback is not None:
            action_callback(action)

    randomize_pressed, _ = poll_key(ord(RANDOMIZE_KEY), now)
    if randomize_pressed and not (shift or ctrl or alt):
        try:
            random_slot = randomize_config()
            new_cfg, new_colors = load_runtime_config()
        except (OSError, ConfigError, ValueError, subprocess.SubprocessError):
            return selected_preset, None, None, False
        preserved_fps = cfg['fps']
        cfg.clear()
        cfg.update(new_cfg)
        cfg['fps'] = preserved_fps
        write_section('config', cfg)
        report_action('randomize')
        return 0, new_colors, random_slot, True

    for digit in LUT_KEYS:
        pressed, _ = poll_key(ord(digit), now)
        if not pressed or alt or shift:
            continue
        if ctrl:
            try:
                colors = load_lut(digit)
            except (ConfigError, KeyError, ValueError):
                continue
            cfg['active_lut'] = digit
            changed = True
            palette_changed = True
        else:
            selected_preset = int(digit)
            preset = load_preset(selected_preset)
            if preset is not None:
                try:
                    colors = resolve_palette(preset)
                except (ConfigError, KeyError, ValueError):
                    continue
                preserved_fps = cfg['fps']
                cfg.update(preset)
                cfg['fps'] = preserved_fps
                changed = True
                palette_changed = True
                report_action('preset-load')

    for key, direction in LUT_CYCLE_KEYS.items():
        pressed, repeated = poll_key(ord(key), now)
        if not (pressed or repeated) or alt:
            continue
        active = cfg['active_lut']
        if active in LUT_KEYS:
            slot = (int(active) + direction) % len(LUT_KEYS)
        else:
            slot = 0 if direction > 0 else len(LUT_KEYS) - 1
        try:
            colors = load_lut(str(slot))
        except (ConfigError, KeyError, ValueError):
            continue
        cfg['active_lut'] = str(slot)
        changed = True
        palette_changed = True

    saved = False
    for key in PARAMETER_KEYS:
        pressed, repeated = poll_key(ord(key), now)
        if not (pressed or repeated):
            continue
        if key == 'S' and alt:
            if pressed:
                write_section(f'preset-{selected_preset}', cfg)
                saved = True
            continue
        if alt:
            continue
        factor = (native_factor if parameter_factor is None
                  else parameter_factor(key))
        _apply_parameter_delta(cfg, key, factor)
        changed = True
        if (cfg['active_lut'] == 'none'
                and PARAMETER_KEYS[key][0] in ('palette_size', 'hue_start',
                                               'hue_end')):
            palette_changed = True

    if changed:
        if palette_changed:
            try:
                colors = resolve_palette(cfg)
            except (ConfigError, KeyError, ValueError):
                return selected_preset, None, None, saved
        write_section('config', cfg)
        return (selected_preset, colors if palette_changed else None,
                None, True)
    return selected_preset, None, None, saved

def poll_hotkeys(cfg, colors, selected_preset, now=None):
    """Handle invisible direct-load, save, LUT, and parameter controls."""
    if os.name != 'nt':
        return selected_preset, None

    # Authoritative gate: no individual command may bypass viewport ownership.
    if not _keyboard_ownership.refresh_document_focus():
        return selected_preset, None

    if now is None:
        now = time.perf_counter()
    selected_preset, new_colors, _, _ = _dispatch_hotkeys(
        cfg, colors, selected_preset, _poll_virtual_key,
        _modifier_is_down, now)
    return selected_preset, new_colors

class BrowserKeyboardState:
    """Logical browser key state with native-equivalent repeat semantics."""

    def __init__(self):
        self.owned = False
        self._down = set()
        self._pressed = set()
        self._repeat_at = {}
        self.update_count = 0
        self.pressed_poll_count = 0
        self.last_action = ''

    def set_owned(self, owned):
        owned = bool(owned)
        if owned != self.owned:
            self.clear()
        self.owned = owned

    def clear(self):
        self._down.clear()
        self._pressed.clear()
        self._repeat_at.clear()

    def update(self, action, vk, shift=False, ctrl=False, alt=False):
        if not self.owned:
            return
        self.update_count += 1
        self.last_action = f'{action}:{vk}'
        for modifier, down in ((VK_SHIFT, shift), (VK_CONTROL, ctrl),
                               (VK_ALT, alt)):
            if down:
                self._down.add(modifier)
            else:
                self._down.discard(modifier)
        if action == 'down':
            if vk not in self._down:
                self._pressed.add(vk)
            self._down.add(vk)
        elif action == 'up':
            self._down.discard(vk)
            self._repeat_at.pop(vk, None)

    def poll(self, vk, now):
        if not self.owned:
            return False, False
        pressed = vk in self._pressed
        self._pressed.discard(vk)
        if pressed:
            self.pressed_poll_count += 1
        down = vk in self._down
        repeated = False
        if pressed:
            self._repeat_at[vk] = now + KEY_REPEAT_DELAY
        elif down and now >= self._repeat_at.get(vk, float('inf')):
            repeated = True
            self._repeat_at[vk] = now + KEY_REPEAT_INTERVAL
        elif not down:
            self._repeat_at.pop(vk, None)
        return pressed, repeated

    def modifier_is_down(self, vk):
        return self.owned and vk in self._down

class BrowserRuntime:
    """Small frame-at-a-time host for Pyodide's yielding worker loop."""

    def __init__(self, columns=80, lines=24, synchronized_output=False):
        set_browser_terminal_size(columns, lines)
        generated = ensure_config_file()
        self.cfg, self.palette_colors = load_runtime_config()
        self.palette = compile_palette(self.palette_colors)
        self.keyboard = BrowserKeyboardState()
        self.keyboard.set_owned(True)
        self.synchronized_output = bool(synchronized_output)
        self.selected_preset = 0
        self.last_random_slot = None
        self.t = 0.0
        self.last_frame_time = None
        self._persistence_dirty = generated
        self.resize_commit_count = 0
        self.random_history = []
        self.keybed_latch_mask = 0
        self._parameter_baseline = {}
        self.lut_revision = 0
        self._lut_state_dirty = True
        if generated:
            self.cfg['fps'] = WEB_FPS_OPTIONS[0]
            write_section('config', self.cfg)
            self._persistence_dirty = True
        self._capture_parameter_baseline()
        self.energy = {
            'enabled': False,
            'depth': 25.0,
            'rate': 1.0,
            'width_min': -1.0,
            'width_max': 1.0,
            'offset': 0.0,
            'target_mask': 1 << 2,
            'wave': 'sine',
        }
        self.energy_position = 0.0
        self.energy_output = 0.0
        self.energy_targets = ('speed',)

    def set_size(self, columns, lines, committed=False):
        set_browser_terminal_size(columns, lines)
        if committed:
            self.resize_commit_count += 1

    def set_fps(self, fps):
        if isinstance(fps, bool):
            raise ValueError('web FPS must be numeric')
        try:
            fps = float(fps)
        except (TypeError, ValueError) as exc:
            raise ValueError('web FPS must be numeric') from exc
        if not math.isfinite(fps) or not 1.0 <= fps <= 1000.0:
            raise ValueError('web FPS must be between 1 and 1000')
        if self.cfg['fps'] == fps:
            return
        self.cfg['fps'] = fps
        write_section('config', self.cfg)
        self._persistence_dirty = True

    def undo_randomize(self):
        if not self.random_history:
            return False
        preserved_fps = self.cfg['fps']
        cfg, colors, selected_preset = self.random_history.pop()
        self.cfg.clear()
        self.cfg.update(cfg)
        self.cfg['fps'] = preserved_fps
        self.palette_colors = list(colors)
        self.palette = compile_palette(self.palette_colors)
        self._mark_lut_state_dirty()
        self.selected_preset = selected_preset
        if self.cfg['active_lut'] != 'none':
            write_lut(self.cfg['active_lut'], self.palette_colors)
        write_section('config', self.cfg)
        self._capture_parameter_baseline()
        self._persistence_dirty = True
        return True

    def _capture_parameter_baseline(self):
        """Snapshot only parameters owned by the compact web keybed."""
        self._parameter_baseline = {
            name: self.cfg[name] for name in KEYBED_PARAMETER_NAMES
        }

    def _handle_hotkey_action(self, action):
        if action in ('preset-load', 'randomize'):
            self._capture_parameter_baseline()

    def set_keybed_latches(self, mask):
        """Set the browser-only +/++ latch mask (bit 0/bit 1)."""
        if isinstance(mask, bool):
            raise ValueError('keybed latch mask must be an integer')
        try:
            value = float(mask)
        except (TypeError, ValueError) as exc:
            raise ValueError('keybed latch mask must be an integer') from exc
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError('keybed latch mask must be an integer')
        mask = int(value)
        if not 0 <= mask <= 3:
            raise ValueError('keybed latch mask must be between 0 and 3')
        self.keybed_latch_mask = mask

    def _web_parameter_factor(self, key):
        """Return the latched factor for one web parameter command."""
        if key not in WEB_KEYBED_KEYS:
            return 1.0
        parameter = PARAMETER_KEYS[key][0]
        high_range = parameter in ('speed', 'rad')
        factor = 1.0
        if self.keybed_latch_mask & 1:
            factor *= 3.0 if high_range else 1.5
        if self.keybed_latch_mask & 2:
            factor *= 6.0 if high_range else 3.0
        return factor

    def reset_keybed_parameters(self):
        """Restore the current keybed baseline without touching LUT or FPS."""
        self.keyboard.clear()
        latches_changed = self.keybed_latch_mask != 0
        self.set_keybed_latches(0)
        changed = any(
            self.cfg[name] != value
            for name, value in self._parameter_baseline.items())
        if changed:
            self.cfg.update(self._parameter_baseline)
            write_section('config', self.cfg)
            self._persistence_dirty = True
        return changed or latches_changed

    def _mark_lut_state_dirty(self):
        self.lut_revision += 1
        self._lut_state_dirty = True

    def replace_lut_json(self, json_text):
        """Validate and atomically apply a complete browser LUT payload."""
        try:
            values = json.loads(str(json_text))
        except (TypeError, ValueError) as exc:
            raise ValueError('LUT payload must be valid JSON') from exc
        if not isinstance(values, list) or len(values) != LUT_SIZE:
            raise ValueError('LUT payload must contain exactly 256 colours')
        colors = []
        for value in values:
            if (not isinstance(value, str)
                    or re.fullmatch(r'[0-9A-Fa-f]{6}', value) is None):
                raise ValueError('every LUT value must be exactly RRGGBB')
            colors.append(value.upper())

        slot = self.cfg['active_lut']
        if slot == 'none':
            slot = '0'
        updated_cfg = dict(self.cfg)
        updated_cfg['active_lut'] = slot
        write_lut_and_config(slot, colors, updated_cfg)

        self.cfg.clear()
        self.cfg.update(updated_cfg)
        self.palette_colors = colors
        self.palette = compile_palette(colors)
        self._mark_lut_state_dirty()
        self._persistence_dirty = True
        return self.lut_revision

    def consume_lut_state_json(self):
        """Return the complete LUT editor state only after palette changes."""
        if not self._lut_state_dirty:
            return None
        self._lut_state_dirty = False
        return json.dumps({
            'colors': resample_palette(self.palette_colors, LUT_SIZE),
            'slot': self.cfg['active_lut'],
            'revision': self.lut_revision,
        })

    def set_keyboard_ownership(self, owned):
        self.keyboard.set_owned(owned)

    def handle_key_event(self, action, key, shift=False, ctrl=False, alt=False):
        names = {'SHIFT': VK_SHIFT, 'CONTROL': VK_CONTROL, 'ALT': VK_ALT}
        action = str(action)
        normalized = str(key).upper()
        if normalized in names:
            vk = names[normalized]
        elif len(normalized) == 1:
            vk = ord(normalized)
        else:
            return
        self.keyboard.update(action, vk, shift, ctrl, alt)

    def configure_energy(self, enabled, depth, rate, width_min, width_max,
                         offset, target_mask, wave):
        """Validate and replace the browser-only transient modulation state."""
        values = (depth, rate, width_min, width_max, offset)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError('energy numeric values must be finite')
        depth = float(depth)
        rate = float(rate)
        width_min = float(width_min)
        width_max = float(width_max)
        offset = float(offset)
        if isinstance(target_mask, bool):
            raise ValueError('energy target mask must be an integer')
        target_mask_value = float(target_mask)
        if (not math.isfinite(target_mask_value)
                or not target_mask_value.is_integer()):
            raise ValueError('energy target mask must be an integer')
        target_mask = int(target_mask_value)
        wave = str(wave)
        if not 0.0 <= depth <= 100.0:
            raise ValueError('energy depth must be between 0 and 100')
        if not -6.0 <= rate <= 6.0:
            raise ValueError('energy rate must be between -6 and 6')
        if not -1.0 <= width_min <= width_max <= 1.0:
            raise ValueError('energy width must be ordered within -1 and 1')
        if not -100.0 <= offset <= 100.0:
            raise ValueError('energy offset must be between -100 and 100')
        if not 0 <= target_mask < (1 << len(ENERGY_PARAMETERS)):
            raise ValueError('energy target mask is outside the parameter ring')
        if wave not in ENERGY_WAVES:
            raise ValueError(f'unsupported energy wave: {wave}')
        was_enabled = self.energy['enabled']
        self.energy.update({
            'enabled': bool(enabled),
            'depth': depth,
            'rate': rate,
            'width_min': width_min,
            'width_max': width_max,
            'offset': offset,
            'target_mask': target_mask,
            'wave': wave,
        })
        self.energy_targets = tuple(
            parameter[2] for index, parameter in enumerate(ENERGY_PARAMETERS)
            if target_mask & (1 << index))
        if self.energy['enabled'] and not was_enabled:
            self.energy_position = 0.0
        if not self.energy['enabled']:
            self.energy_output = 0.0

    def _effective_energy_values(self, elapsed):
        """Return render parameters with transient modulation applied."""
        effective = {name: self.cfg[name] for name, _, _ in ENERGY_PARAMETERS}
        if not self.energy['enabled']:
            self.energy_output = 0.0
            return effective
        self.energy_position += elapsed * self.energy['rate']
        wave = energy_wave_value(self.energy['wave'], self.energy_position)
        envelope = self.energy['width_min'] + (wave + 1.0) * 0.5 * (
            self.energy['width_max'] - self.energy['width_min'])
        self.energy_output = self.energy['offset'] + self.energy['depth'] * envelope
        for index in range(len(ENERGY_PARAMETERS)):
            if not self.energy['target_mask'] & (1 << index):
                continue
            name, step, _ = ENERGY_PARAMETERS[index]
            effective[name] = self.cfg[name] + step * self.energy_output
        return effective

    def _reload_external_config(self):
        signature = check_config()
        if signature is None:
            return
        try:
            new_cfg, new_colors = load_runtime_config()
        except (OSError, ConfigError, ValueError):
            return
        previous_slot = self.cfg['active_lut']
        palette_changed = (new_colors != self.palette_colors
                           or new_cfg['active_lut'] != previous_slot)
        self.cfg.update(new_cfg)
        self.palette_colors = new_colors
        self.palette = compile_palette(new_colors)
        if palette_changed:
            self._mark_lut_state_dirty()
        _config_cache['signature'] = signature

    def step(self, frame_time=None):
        if frame_time is None:
            frame_time = time.perf_counter()
        if self.last_frame_time is None:
            elapsed = 0.0
        else:
            elapsed = max(0.0, frame_time - self.last_frame_time)
        self.last_frame_time = frame_time

        self._reload_external_config()
        before_random = (
            dict(self.cfg), list(self.palette_colors), self.selected_preset)
        selected, changed_colors, random_slot, persistence_dirty = _dispatch_hotkeys(
            self.cfg, self.palette_colors, self.selected_preset,
            self.keyboard.poll, self.keyboard.modifier_is_down, frame_time,
            parameter_factor=self._web_parameter_factor,
            action_callback=self._handle_hotkey_action)
        self.selected_preset = selected
        if changed_colors is not None:
            self.palette_colors = changed_colors
            self.palette = compile_palette(changed_colors)
            self._mark_lut_state_dirty()
            self._persistence_dirty = True
        if random_slot is not None:
            self.random_history.append(before_random)
            self.random_history = self.random_history[-2:]
            self.last_random_slot = random_slot
        if persistence_dirty:
            self._persistence_dirty = True

        effective = self._effective_energy_values(elapsed)
        self.t += elapsed * 2.0 * effective['speed']
        return render(
            self.t,
            self.palette,
            hue_shift=effective['hue_shift'],
            fx=effective['fx'],
            fy=effective['fy'],
            rad=effective['rad'],
            frame_time=frame_time,
            synchronized_output=self.synchronized_output,
        )

    def frame_interval_ms(self):
        return 1000.0 / self.cfg['fps']

    def metrics_json(self):
        """Return bridge-friendly observability without nested Python proxies."""
        return json.dumps({
            'lastRandomSlot': self.last_random_slot,
            'freqY': self.cfg['fy'],
            'activeLut': self.cfg['active_lut'],
            'fps': self.cfg['fps'],
            'resizeCommits': self.resize_commit_count,
            'undoDepth': len(self.random_history),
            'keyboardOwned': self.keyboard.owned,
            'keyUpdates': self.keyboard.update_count,
            'pressedPolls': self.keyboard.pressed_poll_count,
            'lastAction': self.keyboard.last_action,
            'energyEnabled': self.energy['enabled'],
            'energyOutput': self.energy_output,
            'energyPhase': self.energy_position % 1.0,
            'energyPosition': self.energy_position,
            'energyWave': self.energy['wave'],
            'energyTargets': self.energy_targets,
            'energyTargetMask': self.energy['target_mask'],
            'keybedLatchMask': self.keybed_latch_mask,
            'lutSlot': self.cfg['active_lut'],
            'lutRevision': self.lut_revision,
        })

    def consume_persistence_text(self):
        if not self._persistence_dirty:
            return None
        self._persistence_dirty = False
        with open(CONFIG_FILE, 'r', encoding='utf-8') as handle:
            return handle.read()

def hsv(h):
    h = (h % 1.0) * 6
    i = int(h)
    f = h - i
    segs = [(1,f,0),(f,1,0),(0,1,f),(0,f,1),(f,0,1),(1,0,f)]
    r,g,b = segs[i % 6]
    return int(r*255), int(g*255), int(b*255)

def build_palette(size, hue_start, hue_end):
    """Build a hexadecimal RGB LUT over a hue range in degrees.

    A range such as 330 -> 30 crosses through red. Equal endpoints mean a
    complete 360-degree palette. Full-circle palettes omit the duplicate end
    colour; partial ranges include both endpoints.
    """
    start = hue_start % 360.0
    span = (hue_end - hue_start) % 360.0
    full_circle = math.isclose(span, 0.0, abs_tol=1e-9)
    if full_circle:
        span = 360.0

    denominator = size if full_circle else size - 1
    palette = []
    for i in range(size):
        hue = (start + span * i / denominator) / 360.0
        r, g, b = hsv(hue)
        palette.append(f'{r:02X}{g:02X}{b:02X}')
    return palette

def compile_palette(colors):
    """Compile hexadecimal LUT entries into terminal background sequences."""
    palette = []
    for color in colors:
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        # A coloured space is cheaper for the terminal to render than a
        # foreground-coloured full-block glyph.
        palette.append(f'\x1b[48;2;{r};{g};{b}m')
    return palette

def render(t, palette, hue_shift=0.0, fx=0.35, fy=0.45, rad=0.6,
           frame_time=None, synchronized_output=True):
    size = get_plasmaterm_size()
    cols, rows = size.columns, size.lines
    cx, cy = cols / 2, rows / 2
    palette_size = len(palette)

    # Sample the clock once per frame. hue-shift is expressed in degrees/sec
    # and rotates indices within the selected palette.
    if frame_time is None:
        frame_time = time.perf_counter()
    hue_offset = int(frame_time * hue_shift * palette_size / 360.0) % palette_size

    lines = []
    for y in range(rows):
        row = []
        previous_idx = -1
        for x in range(cols):
            v = (math.sin(x * fx + t)
                 + math.sin(y * fy - t * 1.2)
                 + math.sin((x + y) * 0.25 + t * 0.6)
                 + math.sin(math.hypot(x - cx, y - cy) * rad - t)) / 4
            v = (v + 1) / 2
            idx = min(palette_size - 1, int(v * palette_size))
            idx = (idx + hue_offset) % palette_size

            # Only change the background when the quantized colour changes.
            # Adjacent cells with the same index become a compact colour run.
            if idx != previous_idx:
                row.append(palette[idx])
                previous_idx = idx
            row.append(' ')
        lines.append(''.join(row))

    # Windows Terminal 1.23+ displays this as one synchronized update when the
    # frame is parsed within its synchronization timeout.
    frame = '\x1b[H' + '\r\n'.join(lines) + '\x1b[0m'
    if synchronized_output:
        return '\x1b[?2026h' + frame + '\x1b[?2026l'
    return frame

def main():
    ensure_config_file()
    parser = argparse.ArgumentParser(
        prog='plasma.py',
        description='Procedural plasma/wave animation for Windows Terminal.',
    )
    parser.add_argument('--speed', '-s', type=float, default=0.6, help='Time rate multiplier (default: 0.6). Increase for faster cycling.')
    parser.add_argument('--hue-shift', '--hs', type=float, default=0.6, help='Color hue rotation speed (default: 0.6).')
    parser.add_argument('--freq-x', '-x', type=float, default=0.35, help='Horizontal sine frequency multiplier (default: 0.35). Increase for more undulating waves.')
    parser.add_argument('--freq-y', '-y', type=float, default=0.45, help='Vertical sine frequency multiplier (default: 0.45). Decrease for slower vertical undulations.')
    parser.add_argument('--radius', '-r', type=float, default=0.6, help='Radial effect strength (default: 0.6). Increase for larger center glow.')
    parser.add_argument('--palette-size', type=int, default=256, help='Number of procedurally generated colours (default: 256; maximum: 1024).')
    parser.add_argument('--hue-start', type=float, default=0.0, help='First palette hue in degrees (default: 0).')
    parser.add_argument('--hue-end', type=float, default=360.0, help='Last palette hue in degrees (default: 360).')
    parser.add_argument('--fps', type=float, default=40.0, help='Maximum frame rate (default: 40).')
    args = parser.parse_args()

    # Initial config from CLI args
    cfg = {
        'speed': args.speed,
        'hue_shift': args.hue_shift,
        'fx': args.freq_x,
        'fy': args.freq_y,
        'rad': args.radius,
        'palette_size': args.palette_size,
        'hue_start': args.hue_start,
        'hue_end': args.hue_end,
        'fps': args.fps,
        'active_lut': 'none',
    }

    palette_colors = resolve_palette(cfg)
    palette = compile_palette(palette_colors)
    t = 0.0
    selected_preset = 0
    last_frame_time = time.perf_counter()
    timer_period_set = False

    if os.name == 'nt':
        timer_period_set = ctypes.windll.winmm.timeBeginPeriod(1) == 0
        _keyboard_ownership.bind_to_current_document()

    try:
        # Use a clean full-screen buffer and hide the cursor for the session.
        output = sys.stdout.buffer
        output.write(b'\x1b[?1004h\x1b[?1049h\x1b[?25l\x1b[2J')
        output.flush()

        while True:
            frame_start = time.perf_counter()
            elapsed = frame_start - last_frame_time
            last_frame_time = frame_start

            # Poll config file each frame (cheap check)
            signature = check_config()
            if signature is not None:
                try:
                    new_cfg, new_colors = load_runtime_config()
                    cfg.update(new_cfg)
                    palette_colors = new_colors
                    palette = compile_palette(palette_colors)
                    _config_cache['signature'] = signature
                except (OSError, ConfigError, ValueError) as exc:
                    # An editor may briefly leave a partial file while saving.
                    # Keep the last valid settings and try again next frame.
                    sys.stderr.write(f'\x1b[HConfig error: {exc}\x1b[K\n')

            # Invisible controls: 0-9 directly load presets, Alt+S saves the
            # last selected slot, Ctrl+0-9 loads LUTs, and letter pairs adjust
            # parameters with Shift/Ctrl coarse steps.
            selected_preset, changed_colors = poll_hotkeys(
                cfg, palette_colors, selected_preset, frame_start)
            if changed_colors is not None:
                palette_colors = changed_colors
                palette = compile_palette(palette_colors)

            t += elapsed * 2.0 * cfg['speed']
            frame = render(
                t,
                palette,
                hue_shift=cfg['hue_shift'],
                fx=cfg['fx'],
                fy=cfg['fy'],
                rad=cfg['rad'],
                frame_time=frame_start,
            )
            output.write(frame.encode('ascii'))
            output.flush()

            delay = (1.0 / cfg['fps']) - (time.perf_counter() - frame_start)
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        _keyboard_ownership.revoke()
        clear_transient_keyboard_state()
        output.write(b'\x1b[0m\x1b[?25h\x1b[?1049l\x1b[?1004l')
        output.flush()
        if timer_period_set:
            ctypes.windll.winmm.timeEndPeriod(1)

if __name__ == '__main__':
    main()
