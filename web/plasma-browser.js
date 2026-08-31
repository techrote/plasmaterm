const CONFIG_STORAGE_KEY = 'plasmaterm.web-v0.2b.config';
const LEGACY_CONFIG_STORAGE_KEYS = [
  'plasmaterm.web-v0.101a.config',
  'plasmaterm.web-v0.1a.config',
];
const DISPLAY_STORAGE_KEY = 'plasmaterm.web-v0.2b.display';
const FPS_DEFAULT_MIGRATION_KEY = 'plasmaterm.web-v0.2b.fps-default-60';
const DISPLAY_SCHEMA_VERSION = 5;
const DEFAULT_GRID = Object.freeze({ columns: 36, lines: 24 });
const DEFAULT_FPS = 60;
const DEFAULT_DISPLAY = Object.freeze({
  version: DISPLAY_SCHEMA_VERSION,
  width: 538,
  height: 602,
  fontSize: 24,
});
const PARAMETER_KEYS = new Set('QAWSEDRFTGYHUJIK');
const DIGIT_KEYS = new Set('0123456789');
const MODIFIER_KEYS = new Set(['Shift', 'Control', 'Alt']);
const COMMAND_KEYS = new Set([...PARAMETER_KEYS, ...DIGIT_KEYS, ...MODIFIER_KEYS, 'P']);
const KEY_ROWS = [
  [
    ['Q', '+ Y freq'], ['W', '+ X freq'], ['T', '+ speed'], ['Y', '+ hue shift'],
    ['U', '+ radius'], ['I', 'next LUT'], ['P', 'randomize'],
  ],
  [
    ['A', '− Y freq'], ['S', '− X freq'], ['G', '− speed'], ['H', '− hue shift'],
    ['J', '− radius'], ['K', 'prev LUT'],
  ],
];
const ENERGY_TARGET_NAMES = ['freq-y', 'freq-x', 'speed', 'hue-shift', 'radius'];
const terminalElement = document.querySelector('#terminal');
const statusElement = document.querySelector('#status');
const plasmaWindow = document.querySelector('#plasma-window');
const controlsWindow = document.querySelector('#controls-window');
const ptInput = document.querySelector('#pt-input');
const ptPresetSelect = document.querySelector('#pt-preset');
const ptDownButton = document.querySelector('#pt-down');
const ptUpButton = document.querySelector('#pt-up');
const bgInput = document.querySelector('#bg-input');
const fpsInput = document.querySelector('#fps-input');
const fpsPresetSelect = document.querySelector('#fps-preset');
const globalResetButton = document.querySelector('#global-reset');
const visualModeButton = document.querySelector('#visual-mode');
const keyRows = [document.querySelector('#key-row-top'), document.querySelector('#key-row-home')];
const energyPanel = document.querySelector('#energy-panel');
const lutWindow = document.querySelector('#lut-window');
const lutGrid = document.querySelector('#lut-grid');
const exportLutButton = document.querySelector('#export-lut');
const randomiseLutButton = document.querySelector('#randomise-lut');
const lutRandomScaleInput = document.querySelector('#lut-random-scale');
const lutRandomScaleSlider = document.querySelector('#lut-random-scale-slider');
const keyLatchPlus = document.querySelector('#key-latch-plus');
const keyLatchPlusPlus = document.querySelector('#key-latch-plusplus');
const resetKeybedButton = document.querySelector('#reset-keybed');
const resetEnergyButton = document.querySelector('#reset-energy');
const energyPower = document.querySelector('#energy-power');
const energyInputs = {
  depth: document.querySelector('#energy-depth'),
  rate: document.querySelector('#energy-rate'),
  widthMin: document.querySelector('#energy-width-min'),
  widthMax: document.querySelector('#energy-width-max'),
  offset: document.querySelector('#energy-offset'),
};
const energyOutputs = {
  depth: document.querySelector('#energy-depth-output'),
  rate: document.querySelector('#energy-rate-output'),
  offset: document.querySelector('#energy-offset-output'),
};
const energyWidthTrack = document.querySelector('#energy-width-track');
const energyWaveSelect = document.querySelector('#energy-wave');
const targetButtons = [...document.querySelectorAll('.target-led')];
const mobileLayout = matchMedia('(max-width: 700px)');
const dec2026 = new URLSearchParams(location.search).get('sync') !== '0';
const DEFAULT_ENERGY = Object.freeze({
  enabled: false,
  depth: 25,
  rate: 0.5,
  widthMin: -1,
  widthMax: 1,
  offset: 0,
  targetMask: 1 << 2,
  wave: 'sine',
});

const keyButtons = new Map();
for (let rowIndex = 0; rowIndex < KEY_ROWS.length; rowIndex += 1) {
  for (const entry of KEY_ROWS[rowIndex]) {
    if (entry === null) {
      const placeholder = document.createElement('span');
      placeholder.className = 'key-placeholder';
      placeholder.setAttribute('aria-hidden', 'true');
      keyRows[rowIndex].append(placeholder);
      continue;
    }
    const [key, label] = entry;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'keycap';
    button.dataset.key = key;
    button.setAttribute('aria-label', `${key}: ${label}`);
    button.innerHTML = `<strong>${key}</strong><small>${label}</small>`;
    keyRows[rowIndex].append(button);
    keyButtons.set(key, button);
  }
}
const undoButton = document.createElement('button');
undoButton.type = 'button';
undoButton.id = 'undo-randomize';
undoButton.className = 'keycap undo-button';
undoButton.disabled = true;
undoButton.dataset.depth = '0';
undoButton.setAttribute('aria-label', 'Undo Randomize');
undoButton.innerHTML = '<strong>↶</strong><small>undo</small><span class="undo-dots"><i></i><i></i></span>';
keyRows[1].append(undoButton);
const undoDots = [...undoButton.querySelectorAll('.undo-dots i')];

function updateUndoDepth(value) {
  const undoDepth = Math.max(0, Math.min(2, Number(value)));
  undoButton.disabled = undoDepth === 0;
  undoButton.dataset.depth = String(undoDepth);
  undoButton.setAttribute('aria-label', `Undo Randomize (${undoDepth} of 2 available)`);
  for (const [index, dot] of undoDots.entries()) {
    dot.classList.toggle('is-filled', index < undoDepth);
  }
}

let lutState = {
  colors: Array.from({ length: 256 }, () => '000000'),
  slot: 'none',
  revision: 0,
};
const lutFields = [];
let lutRandomScale = 25;
let backgroundColor = '050509';

function normalizeLutValue(value) {
  const normalized = String(value ?? '').trim().replace(/^#/, '').toUpperCase();
  return /^[0-9A-F]{6}$/.test(normalized) ? normalized : null;
}

function readableLutForeground(hex) {
  const channels = [0, 2, 4].map((offset) => {
    const value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  const luminance = channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  return luminance > 0.46 ? '#08070c' : '#fff';
}

function hexChannels(hex) {
  return [0, 2, 4].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
}

function formatHexChannels(channels) {
  return channels.map((value) => Math.max(0, Math.min(255, Math.round(value)))
    .toString(16).padStart(2, '0')).join('').toUpperCase();
}

function randomiseLutColors(colors, scalePercent, random = Math.random) {
  const scale = Math.max(0, Math.min(100, Number(scalePercent) || 0)) / 100;
  if (scale === 0) return [...colors];
  const anchorCount = 8;
  const anchors = Array.from({ length: anchorCount }, () => [0, 0, 0].map(
    () => Math.min(255, Math.floor(random() * 256))));
  return colors.map((color, index) => {
    const position = index * anchorCount / colors.length;
    const anchorIndex = Math.floor(position) % anchorCount;
    const nextIndex = (anchorIndex + 1) % anchorCount;
    const fraction = position - Math.floor(position);
    const blend = (1 - Math.cos(Math.PI * fraction)) / 2;
    const target = anchors[anchorIndex].map((channel, channelIndex) => (
      channel + (anchors[nextIndex][channelIndex] - channel) * blend));
    const current = hexChannels(normalizeLutValue(color) ?? '000000');
    return formatHexChannels(current.map((channel, channelIndex) => (
      channel + (target[channelIndex] - channel) * scale)));
  });
}

function paintLutField(field, color) {
  field.style.backgroundColor = `#${color}`;
  field.style.color = readableLutForeground(color);
  field.classList.remove('is-invalid');
}

function updateLutFields(state = lutState, preserveFocused = true) {
  if (!Array.isArray(state.colors) || state.colors.length !== 256) return;
  lutState = {
    colors: state.colors.map((color) => normalizeLutValue(color) ?? '000000'),
    slot: String(state.slot ?? 'none'),
    revision: Number(state.revision) || 0,
  };
  for (let index = 0; index < lutFields.length; index += 1) {
    const field = lutFields[index];
    const color = lutState.colors[index];
    if (!preserveFocused || document.activeElement !== field) field.value = color;
    paintLutField(field, color);
  }
  lutWindow.dataset.lutSlot = lutState.slot;
  lutWindow.dataset.lutRevision = String(lutState.revision);
  exportLutButton.disabled = false;
  randomiseLutButton.disabled = false;
}

function parseBulkLut(text) {
  const stripped = String(text)
    .replace(/[\[\]{}()"']/g, ' ')
    .trim();
  const tokens = stripped.split(/[\s,;]+/).filter(Boolean);
  if (tokens.length !== 256) return null;
  const colors = tokens.map(normalizeLutValue);
  return colors.every(Boolean) ? colors : null;
}

function sendLutColors(colors) {
  if (!runtimeReady) return false;
  worker.postMessage({ type: 'setLut', colors });
  return true;
}

function commitLutField(index) {
  const field = lutFields[index];
  const color = normalizeLutValue(field.value);
  if (!color) {
    field.value = lutState.colors[index];
    paintLutField(field, lutState.colors[index]);
    return false;
  }
  if (color === lutState.colors[index]) {
    field.value = color;
    paintLutField(field, color);
    return true;
  }
  const colors = [...lutState.colors];
  colors[index] = color;
  field.value = color;
  paintLutField(field, color);
  if (!sendLutColors(colors)) {
    field.value = lutState.colors[index];
    paintLutField(field, lutState.colors[index]);
    return false;
  }
  lutState = { ...lutState, colors };
  return true;
}

for (let index = 0; index < 256; index += 1) {
  const field = document.createElement('input');
  field.type = 'text';
  field.className = 'lut-field';
  field.maxLength = 7;
  field.value = lutState.colors[index];
  field.autocomplete = 'off';
  field.spellcheck = false;
  field.inputMode = 'text';
  field.setAttribute('aria-label', `LUT colour ${index}`);
  field.addEventListener('input', () => {
    const color = normalizeLutValue(field.value);
    field.classList.toggle('is-invalid', !color);
    if (color) paintLutField(field, color);
  });
  field.addEventListener('change', () => commitLutField(index));
  field.addEventListener('blur', () => commitLutField(index));
  field.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    if (commitLutField(index)) lutFields[(index + 1) % lutFields.length].focus();
  });
  if (index === 0) {
    field.addEventListener('paste', (event) => {
      const text = event.clipboardData?.getData('text') ?? '';
      const looksBulk = /[\s,;\[\]]/.test(text.trim());
      if (!looksBulk) return;
      event.preventDefault();
      const colors = parseBulkLut(text);
      if (!colors) {
        statusElement.hidden = false;
        statusElement.classList.add('error');
        statusElement.textContent = 'LUT paste needs exactly 256 valid RRGGBB values.';
        return;
      }
      if (!sendLutColors(colors)) {
        statusElement.hidden = false;
        statusElement.classList.add('error');
        statusElement.textContent = 'LUT editing is available after PlasmaTerm finishes loading.';
        return;
      }
      updateLutFields({ ...lutState, colors }, false);
    });
  }
  paintLutField(field, lutState.colors[index]);
  lutGrid.append(field);
  lutFields.push(field);
}

exportLutButton.addEventListener('click', async () => {
  const rows = [];
  for (let index = 0; index < lutState.colors.length; index += 8) {
    rows.push(lutState.colors.slice(index, index + 8).join(', '));
  }
  try {
    await navigator.clipboard.writeText(rows.join('\n'));
    exportLutButton.dataset.copied = 'true';
    setTimeout(() => { delete exportLutButton.dataset.copied; }, 1200);
  } catch (error) {
    statusElement.hidden = false;
    statusElement.classList.add('error');
    statusElement.textContent = `Could not copy the LUT: ${error.message}`;
  }
});

function setLutRandomScale(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    lutRandomScaleInput.value = String(lutRandomScale);
    return false;
  }
  lutRandomScale = Math.max(0, Math.min(100, Math.round(numeric)));
  lutRandomScaleInput.value = String(lutRandomScale);
  lutRandomScaleSlider.value = String(lutRandomScale);
  lutWindow.dataset.randomScale = String(lutRandomScale);
  return true;
}

const commitLutRandomScale = () => {
  if (lutRandomScaleInput.value === '') {
    lutRandomScaleInput.value = String(lutRandomScale);
    return;
  }
  setLutRandomScale(lutRandomScaleInput.value);
};
lutRandomScaleInput.addEventListener('change', commitLutRandomScale);
lutRandomScaleInput.addEventListener('blur', commitLutRandomScale);
lutRandomScaleInput.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  commitLutRandomScale();
  lutRandomScaleInput.blur();
});
lutRandomScaleSlider.addEventListener('input', () => {
  setLutRandomScale(lutRandomScaleSlider.value);
});
randomiseLutButton.addEventListener('click', () => {
  if (!runtimeReady || randomiseLutButton.disabled) return;
  const colors = randomiseLutColors(lutState.colors, lutRandomScale);
  if (!sendLutColors(colors)) return;
  updateLutFields({ ...lutState, colors }, false);
  lutWindow.dataset.randomiseCount = String(
    Number(lutWindow.dataset.randomiseCount ?? 0) + 1);
});
setLutRandomScale(lutRandomScale);

let displayWasStored = false;
function loadDisplay() {
  try {
    const serialized = localStorage.getItem(DISPLAY_STORAGE_KEY);
    if (!serialized) return { ...DEFAULT_DISPLAY };
    const stored = JSON.parse(serialized);
    if (stored.version !== DISPLAY_SCHEMA_VERSION) {
      return { ...DEFAULT_DISPLAY };
    }
    displayWasStored = true;
    return { ...DEFAULT_DISPLAY, ...stored };
  } catch {
    return { ...DEFAULT_DISPLAY };
  }
}

let display = loadDisplay();
const firstDisplayLoad = !displayWasStored;
display.width = Math.max(480, Math.min(1600, Number(display.width) || DEFAULT_DISPLAY.width));
display.height = Math.max(320, Math.min(1000, Number(display.height) || DEFAULT_DISPLAY.height));
display.fontSize = Math.max(6, Math.min(200, Number(display.fontSize) || DEFAULT_DISPLAY.fontSize));
document.documentElement.style.setProperty('--plasma-width', `${display.width}px`);
document.documentElement.style.setProperty('--plasma-height', `${display.height}px`);
ptInput.value = String(display.fontSize);

function saveDisplay() {
  try { localStorage.setItem(DISPLAY_STORAGE_KEY, JSON.stringify(display)); } catch { /* best effort */ }
}
let Terminal;
let FitAddon;
try {
  ({ Terminal } = await import(
    'https://cdn.jsdelivr.net/npm/@xterm/xterm@6.0.0/+esm'));
  ({ FitAddon } = await import(
    'https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.11.0/+esm'));
} catch (error) {
  statusElement.classList.add('error');
  statusElement.textContent = `PlasmaTerm could not load its terminal: ${error.message}`;
  throw error;
}

const terminal = new Terminal({
  allowTransparency: false,
  cursorBlink: false,
  disableStdin: true,
  fontFamily: 'Cascadia Mono, Cascadia Code, Consolas, monospace',
  fontSize: display.fontSize,
  lineHeight: 1,
  letterSpacing: 0,
  scrollback: 0,
  theme: { background: '#050509', foreground: '#d8d5df' },
});
const fitAddon = new FitAddon();
terminal.loadAddon(fitAddon);
terminal.open(terminalElement);
fitAddon.fit();
if (firstDisplayLoad) terminal.resize(DEFAULT_GRID.columns, DEFAULT_GRID.lines);

function paintBackgroundField(color) {
  bgInput.value = color;
  bgInput.style.backgroundColor = `#${color}`;
  bgInput.style.color = readableLutForeground(color);
  bgInput.classList.remove('is-invalid');
}

function applyBackgroundColor(value) {
  const color = normalizeLutValue(value);
  if (!color) return false;
  backgroundColor = color;
  const [red, green, blue] = hexChannels(color);
  const contrast = readableLutForeground(color);
  const rootStyle = document.documentElement.style;
  rootStyle.setProperty('--display-bg', `#${color}`);
  rootStyle.setProperty('--display-bg-rgb', `${red} ${green} ${blue}`);
  rootStyle.setProperty('--display-contrast', contrast);
  rootStyle.setProperty('--energy-highlight', `#${color}`);
  rootStyle.setProperty('--energy-highlight-rgb', `${red} ${green} ${blue}`);
  rootStyle.setProperty('--energy-contrast', contrast);
  rootStyle.setProperty('--dock-colour', `#${color}`);
  rootStyle.setProperty('--dock-foreground', contrast);
  document.body.classList.add('has-custom-background');
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', `#${color}`);
  terminal.options.theme = { ...terminal.options.theme, background: `#${color}` };
  terminalElement.dataset.backgroundColor = color;
  energyPanel.dataset.highlightColor = color;
  paintBackgroundField(color);
  return true;
}

const commitBackgroundField = () => {
  if (!applyBackgroundColor(bgInput.value)) paintBackgroundField(backgroundColor);
};
bgInput.addEventListener('input', () => {
  const color = normalizeLutValue(bgInput.value);
  bgInput.classList.toggle('is-invalid', !color);
  if (color) {
    bgInput.style.backgroundColor = `#${color}`;
    bgInput.style.color = readableLutForeground(color);
  }
});
bgInput.addEventListener('change', commitBackgroundField);
bgInput.addEventListener('blur', commitBackgroundField);
bgInput.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  commitBackgroundField();
  bgInput.blur();
});
paintBackgroundField(backgroundColor);

let latestFrame = null;
let presentationScheduled = false;
let terminalWriting = false;
let ownsKeyboard = document.hasFocus() && document.visibilityState === 'visible';
const heldKeys = new Set();
const suppressedUntilRelease = new Set();
const activeKeySources = new Map();
let runtimeReady = false;
const energyState = { ...DEFAULT_ENERGY };
const metrics = {
  receivedFrames: 0,
  presentedFrames: 0,
  droppedFrames: 0,
  terminalWriteMs: 0,
  worker: null,
  lastRandomSlot: null,
  dimensions: { columns: terminal.cols, lines: terminal.rows },
};
window.__plasmaMetrics = metrics;

function showError(message) {
  statusElement.hidden = false;
  statusElement.classList.add('error');
  statusElement.textContent = `PlasmaTerm could not start: ${message}`;
}

function schedulePresentation() {
  if (presentationScheduled || terminalWriting || latestFrame === null) return;
  presentationScheduled = true;
  requestAnimationFrame(() => {
    presentationScheduled = false;
    if (terminalWriting || latestFrame === null) return;
    const frame = latestFrame;
    latestFrame = null;
    terminalWriting = true;
    const writeStarted = performance.now();
    terminal.write(frame, () => {
      metrics.terminalWriteMs = performance.now() - writeStarted;
      metrics.presentedFrames += 1;
      terminalElement.dataset.terminalWriteMs = metrics.terminalWriteMs.toFixed(2);
      terminalElement.dataset.presentedFrames = String(metrics.presentedFrames);
      terminalWriting = false;
      statusElement.hidden = true;
      worker.postMessage({ type: 'framePresented' });
      schedulePresentation();
    });
  });
}

function receiveFrame(frame) {
  metrics.receivedFrames += 1;
  if (liveResizing) {
    metrics.droppedFrames += 1;
    worker.postMessage({ type: 'framePresented' });
    return;
  }
  if (latestFrame !== null) metrics.droppedFrames += 1;
  latestFrame = frame;
  terminalElement.dataset.receivedFrames = String(metrics.receivedFrames);
  terminalElement.dataset.droppedFrames = String(metrics.droppedFrames);
  schedulePresentation();
}

const worker = new Worker('./plasma-worker.js', { type: 'module' });

function energyTargets(targetMask = energyState.targetMask) {
  return ENERGY_TARGET_NAMES.filter((_, index) => targetMask & (1 << index));
}

function updateEnergyTargets(targets = energyTargets()) {
  for (const led of document.querySelectorAll('[data-energy-target]')) {
    led.setAttribute('aria-pressed', String(targets.includes(led.dataset.energyTarget)));
  }
}

function updateEnergyControls() {
  energyOutputs.depth.value = String(energyState.depth);
  energyOutputs.rate.value = String(Number(energyState.rate.toFixed(2)));
  energyOutputs.offset.value = String(energyState.offset);
  energyInputs.depth.value = String(energyState.depth);
  energyInputs.rate.value = String(Math.max(-3, Math.min(3, energyState.rate)));
  energyInputs.offset.value = String(energyState.offset);
  energyInputs.widthMin.value = String(Math.round(energyState.widthMin * 100));
  energyInputs.widthMax.value = String(Math.round(energyState.widthMax * 100));
  energyWidthTrack.style.setProperty('--width-min', `${(energyState.widthMin + 1) * 50}%`);
  energyWidthTrack.style.setProperty('--width-max', `${(energyState.widthMax + 1) * 50}%`);
  energyWaveSelect.value = energyState.wave;
  energyPower.setAttribute('aria-pressed', String(energyState.enabled));
  energyPower.querySelector('.power-label').textContent = energyState.enabled ? 'On' : 'Off';
  energyPanel.classList.toggle('energy-on', energyState.enabled);
  updateEnergyTargets();
}

function energyConfig() {
  return { ...energyState };
}

function sendEnergyConfig() {
  if (runtimeReady) worker.postMessage({ type: 'energy', config: energyConfig() });
}

function readEnergySlider(changedInput) {
  if (changedInput === energyInputs.widthMin
      && Number(energyInputs.widthMin.value) > Number(energyInputs.widthMax.value)) {
    energyInputs.widthMax.value = energyInputs.widthMin.value;
  } else if (changedInput === energyInputs.widthMax
      && Number(energyInputs.widthMax.value) < Number(energyInputs.widthMin.value)) {
    energyInputs.widthMin.value = energyInputs.widthMax.value;
  }
  if (changedInput === energyInputs.depth) {
    energyState.depth = Number(changedInput.value);
  } else if (changedInput === energyInputs.rate) {
    energyState.rate = Number(changedInput.value);
  } else if (changedInput === energyInputs.offset) {
    energyState.offset = Number(changedInput.value);
  } else {
    energyState.widthMin = Number(energyInputs.widthMin.value) / 100;
    energyState.widthMax = Number(energyInputs.widthMax.value) / 100;
  }
  updateEnergyControls();
  sendEnergyConfig();
}

for (const input of Object.values(energyInputs)) {
  input.addEventListener('input', () => readEnergySlider(input));
  input.addEventListener('change', () => readEnergySlider(input));
}

function installEnergyField(field, stateKey, minimum, maximum) {
  const commit = () => {
    const value = Number(field.value);
    if (!Number.isFinite(value)) {
      updateEnergyControls();
      return;
    }
    energyState[stateKey] = Math.max(minimum, Math.min(maximum, value));
    updateEnergyControls();
    sendEnergyConfig();
  };
  field.addEventListener('change', commit);
  field.addEventListener('blur', commit);
  field.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    commit();
    field.blur();
  });
}
installEnergyField(energyOutputs.depth, 'depth', 0, 100);
installEnergyField(energyOutputs.rate, 'rate', -6, 6);
installEnergyField(energyOutputs.offset, 'offset', -100, 100);

for (const button of targetButtons) {
  button.addEventListener('click', () => {
    energyState.targetMask ^= 1 << Number(button.dataset.targetBit);
    updateEnergyControls();
    sendEnergyConfig();
  });
}
energyWaveSelect.addEventListener('change', () => {
  energyState.wave = energyWaveSelect.value;
  sendEnergyConfig();
});
energyPower.addEventListener('click', () => {
  energyState.enabled = !energyState.enabled;
  updateEnergyControls();
  sendEnergyConfig();
});
resetEnergyButton.addEventListener('click', () => {
  Object.assign(energyState, DEFAULT_ENERGY);
  updateEnergyControls();
  sendEnergyConfig();
});
updateEnergyControls();

let fitScheduled = false;
let liveResizing = false;
let pendingResizeMessage = 'resize';
let pendingExactDimensions = null;

function fitTerminal(messageType = 'resize', exactDimensions = null) {
  if (messageType === 'resizeCommit') pendingResizeMessage = 'resizeCommit';
  if (exactDimensions) {
    pendingExactDimensions = {
      columns: Math.max(2, Math.round(exactDimensions.columns)),
      lines: Math.max(2, Math.round(exactDimensions.lines)),
    };
  }
  if (liveResizing || fitScheduled) return;
  fitScheduled = true;
  requestAnimationFrame(() => {
    fitScheduled = false;
    if (liveResizing) return;
    const committedMessage = pendingResizeMessage;
    pendingResizeMessage = 'resize';
    const fixed = pendingExactDimensions;
    pendingExactDimensions = null;
    if (fixed) {
      terminal.resize(fixed.columns, fixed.lines);
    } else {
      fitAddon.fit();
    }
    metrics.dimensions = { columns: terminal.cols, lines: terminal.rows };
    terminalElement.dataset.columns = String(terminal.cols);
    terminalElement.dataset.lines = String(terminal.rows);
    worker.postMessage({ type: committedMessage, columns: terminal.cols, lines: terminal.rows });
  });
}

function syncPresetSelect(select, value) {
  const normalized = String(Number(value));
  select.value = [...select.options].some((option) => option.value === normalized)
    ? normalized : '';
}

function setCharacterSize(value, persist = true, refit = true) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    ptInput.value = String(display.fontSize);
    return;
  }
  const fontSize = Math.max(6, Math.min(200, Math.round(numericValue)));
  display.fontSize = fontSize;
  terminal.options.fontSize = fontSize;
  ptInput.value = String(fontSize);
  syncPresetSelect(ptPresetSelect, fontSize);
  terminalElement.dataset.fontSize = String(fontSize);
  if (persist) saveDisplay();
  if (refit) fitTerminal();
}

function pointSizeForFixedResolution(dimensions) {
  if (visualRestoreGeometry?.terminalWidth && visualRestoreGeometry?.terminalHeight) {
    const scale = Math.min(
      Math.max(1, terminalElement.clientWidth - 8) / visualRestoreGeometry.terminalWidth,
      Math.max(1, terminalElement.clientHeight - 8) / visualRestoreGeometry.terminalHeight,
    );
    return Math.max(6, Math.min(200, Math.floor(
      visualRestoreGeometry.fontSize * scale)));
  }
  const screen = terminalElement.querySelector('.xterm-screen')?.getBoundingClientRect();
  const currentPt = Math.max(1, display.fontSize);
  const cellWidthPerPt = screen?.width && terminal.cols
    ? screen.width / terminal.cols / currentPt : 0.62;
  const cellHeightPerPt = screen?.height && terminal.rows
    ? screen.height / terminal.rows / currentPt : 1;
  const width = Math.max(1, terminalElement.clientWidth - 8);
  const height = Math.max(1, terminalElement.clientHeight - 8);
  return Math.max(6, Math.min(200, Math.floor(Math.min(
    width / (dimensions.columns * cellWidthPerPt),
    height / (dimensions.lines * cellHeightPerPt),
  ))));
}

const commitCharacterField = () => {
  if (ptInput.value === '') {
    ptInput.value = String(display.fontSize);
    return;
  }
  setCharacterSize(ptInput.value);
};
ptInput.addEventListener('change', commitCharacterField);
ptInput.addEventListener('blur', commitCharacterField);
ptInput.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  commitCharacterField();
  ptInput.blur();
});
ptDownButton.addEventListener('click', () => setCharacterSize(display.fontSize - 1));
ptUpButton.addEventListener('click', () => setCharacterSize(display.fontSize + 1));
ptPresetSelect.addEventListener('change', () => {
  if (ptPresetSelect.value !== '') setCharacterSize(ptPresetSelect.value);
});

let selectedFps = DEFAULT_FPS;
function setFpsField(value, send = true) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    fpsInput.value = String(selectedFps);
    return;
  }
  selectedFps = Math.max(1, Math.min(1000, numeric));
  fpsInput.value = String(selectedFps);
  syncPresetSelect(fpsPresetSelect, selectedFps);
  if (send && runtimeReady) worker.postMessage({ type: 'fps', fps: selectedFps });
}
const commitFpsField = () => {
  if (fpsInput.value === '') {
    fpsInput.value = String(selectedFps);
    return;
  }
  setFpsField(fpsInput.value);
};
fpsInput.addEventListener('change', commitFpsField);
fpsInput.addEventListener('blur', commitFpsField);
fpsInput.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  commitFpsField();
  fpsInput.blur();
});
fpsPresetSelect.addEventListener('change', () => {
  if (fpsPresetSelect.value !== '') setFpsField(fpsPresetSelect.value);
});

undoButton.addEventListener('click', () => {
  if (!runtimeReady || undoButton.disabled) return;
  worker.postMessage({ type: 'undoRandomize' });
});

let keybedLatchMask = 0;
function updateKeybedLatches(mask = keybedLatchMask, send = false) {
  keybedLatchMask = Math.max(0, Math.min(3, Number(mask) | 0));
  keyLatchPlus.setAttribute('aria-pressed', String(Boolean(keybedLatchMask & 1)));
  keyLatchPlusPlus.setAttribute('aria-pressed', String(Boolean(keybedLatchMask & 2)));
  controlsWindow.dataset.latchMask = String(keybedLatchMask);
  if (send && runtimeReady) {
    worker.postMessage({ type: 'keybedLatches', mask: keybedLatchMask });
  }
}
keyLatchPlus.addEventListener('click', () => updateKeybedLatches(keybedLatchMask ^ 1, true));
keyLatchPlusPlus.addEventListener('click', () => updateKeybedLatches(keybedLatchMask ^ 2, true));
resetKeybedButton.addEventListener('click', () => {
  releaseAllActiveKeys();
  updateKeybedLatches(0, true);
  if (runtimeReady) worker.postMessage({ type: 'resetParameters' });
});
updateKeybedLatches();

const floatingWindows = {
  plasma: plasmaWindow,
  controls: controlsWindow,
  energy: energyPanel,
  lut: lutWindow,
};
const windowPositions = new Map();
let topWindowZ = 50;
let cancelActiveInteraction = null;
let visualMaximized = false;
let visualRestoreGeometry = null;
let visualFixedDimensions = null;
let mobileVisualFront = false;

function setWindowCenter(element, x, y) {
  const position = { x: Math.round(x), y: Math.round(y) };
  windowPositions.set(element, position);
  element.style.left = `${position.x}px`;
  element.style.top = `${position.y}px`;
}

function clampWindowCenter(element, x, y) {
  const rect = element.getBoundingClientRect();
  const halfWidth = rect.width / 2;
  const halfHeight = rect.height / 2;
  return {
    x: Math.max(80 - halfWidth, Math.min(innerWidth - 80 + halfWidth, x)),
    y: Math.max(halfHeight, Math.min(innerHeight - 24 + halfHeight, y)),
  };
}

function measureWindow(element) {
  if (!element.hidden) return element.getBoundingClientRect();
  element.style.visibility = 'hidden';
  element.hidden = false;
  const rect = element.getBoundingClientRect();
  element.hidden = true;
  element.style.removeProperty('visibility');
  return rect;
}

function defaultWindowCenters() {
  const controlsRect = measureWindow(controlsWindow);
  const energyRect = measureWindow(energyPanel);
  const lutRect = measureWindow(lutWindow);
  if (mobileLayout.matches && innerWidth > innerHeight) {
    return {
      plasma: { x: innerWidth / 2, y: innerHeight / 2 },
      controls: { x: controlsRect.width / 2 + 6, y: innerHeight / 2 },
      energy: { x: innerWidth - energyRect.width / 2 - 6, y: innerHeight / 2 },
      lut: { x: innerWidth / 2, y: innerHeight / 2 },
    };
  }
  if (mobileLayout.matches) {
    return {
      plasma: { x: innerWidth / 2, y: innerHeight / 2 },
      controls: { x: innerWidth / 2, y: 48 + controlsRect.height / 2 },
      energy: { x: innerWidth / 2, y: innerHeight - energyRect.height / 2 - 6 },
      lut: { x: innerWidth / 2, y: innerHeight / 2 },
    };
  }
  return {
    plasma: { x: innerWidth / 2, y: innerHeight / 2 - 30 },
    controls: {
      x: Math.max(controlsRect.width / 2 + 8, innerWidth / 2 - 240),
      y: innerHeight - controlsRect.height / 2 - 8,
    },
    energy: {
      x: Math.min(innerWidth - energyRect.width / 2 - 8, innerWidth / 2 + 280),
      y: innerHeight - energyRect.height / 2 - 8,
    },
    lut: {
      x: Math.min(innerWidth - lutRect.width / 2 - 8, innerWidth / 2 + 330),
      y: Math.max(lutRect.height / 2 + 8, innerHeight / 2 - 170),
    },
  };
}

function resetWindowPositions() {
  const defaults = defaultWindowCenters();
  for (const [name, element] of Object.entries(floatingWindows)) {
    const target = element === plasmaWindow && mobileLayout.matches
      ? defaults[name]
      : clampWindowCenter(element, defaults[name].x, defaults[name].y);
    setWindowCenter(element, target.x, target.y);
  }
}

const dockButtons = {
  controls: document.querySelector('#dock-controls'),
  energy: document.querySelector('#dock-energy'),
  lut: document.querySelector('#dock-lut'),
};
const restoreButtons = {
  controls: document.querySelector('#restore-controls'),
  energy: document.querySelector('#restore-energy'),
  lut: document.querySelector('#restore-lut'),
};
const dockedWindows = new Set();

function setWindowDocked(name, docked, bringForward = true) {
  const element = floatingWindows[name];
  const dockButton = dockButtons[name];
  const restoreButton = restoreButtons[name];
  if (!element || !restoreButton) return;
  if (docked) {
    dockedWindows.add(name);
    element.hidden = true;
    restoreButton.hidden = false;
    restoreButton.setAttribute('aria-expanded', 'false');
    dockButton?.setAttribute('aria-expanded', 'false');
    return;
  }
  dockedWindows.delete(name);
  element.hidden = false;
  restoreButton.hidden = true;
  restoreButton.setAttribute('aria-expanded', 'true');
  dockButton?.setAttribute('aria-expanded', 'true');
  const defaults = defaultWindowCenters();
  const current = windowPositions.get(element) ?? defaults[name];
  const recovered = clampWindowCenter(element, current.x, current.y);
  setWindowCenter(element, recovered.x, recovered.y);
  if (bringForward) bringToFront(element);
}

for (const name of Object.keys(dockButtons)) {
  dockButtons[name].addEventListener('click', () => setWindowDocked(name, true));
  restoreButtons[name].addEventListener('click', () => setWindowDocked(name, false));
}

function resetStackingOrder() {
  plasmaWindow.style.zIndex = '50';
  controlsWindow.style.zIndex = '51';
  energyPanel.style.zIndex = '52';
  lutWindow.style.zIndex = '53';
  topWindowZ = 53;
  document.documentElement.dataset.mobileVisualFront = 'false';
}

function bringToFront(element) {
  topWindowZ += 1;
  element.style.zIndex = String(topWindowZ);
}

for (const [name, element] of Object.entries(floatingWindows)) {
  const toolbar = element.querySelector(`[data-drag-handle="${name}"]`);
  element.addEventListener('pointerdown', () => {
    if (element !== plasmaWindow || !mobileLayout.matches) bringToFront(element);
  }, { capture: true });
  toolbar.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 || (element === plasmaWindow && (mobileLayout.matches || visualMaximized))
        || event.target.closest('input, select, button, label')) return;
    event.preventDefault();
    cancelActiveInteraction?.();
    bringToFront(element);
    const current = windowPositions.get(element)
      ?? { x: element.getBoundingClientRect().left + element.offsetWidth / 2,
        y: element.getBoundingClientRect().top + element.offsetHeight / 2 };
    const start = { pointerX: event.clientX, pointerY: event.clientY, ...current };
    let pending = null;
    let frame = null;
    let finished = false;
    toolbar.setPointerCapture(event.pointerId);
    element.classList.add('is-dragging');
    const move = (moveEvent) => {
      if (moveEvent.pointerType === 'mouse' && (moveEvent.buttons & 1) === 0) {
        finish();
        return;
      }
      pending = clampWindowCenter(element,
        start.x + moveEvent.clientX - start.pointerX,
        start.y + moveEvent.clientY - start.pointerY);
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        if (pending) setWindowCenter(element, pending.x, pending.y);
      });
    };
    const finish = () => {
      if (finished) return;
      finished = true;
      window.removeEventListener('pointermove', move, true);
      window.removeEventListener('pointerup', finish, true);
      window.removeEventListener('pointercancel', finish, true);
      window.removeEventListener('blur', finish);
      element.classList.remove('is-dragging');
      if (pending) setWindowCenter(element, pending.x, pending.y);
      if (cancelActiveInteraction === finish) cancelActiveInteraction = null;
    };
    cancelActiveInteraction = finish;
    window.addEventListener('pointermove', move, { capture: true });
    window.addEventListener('pointerup', finish, { once: true, capture: true });
    window.addEventListener('pointercancel', finish, { once: true, capture: true });
    window.addEventListener('blur', finish, { once: true });
    toolbar.addEventListener('lostpointercapture', finish, { once: true });
  });
}

function setWindowSize(width, height, persist = true) {
  display.width = Math.max(480, Math.min(1600, Math.round(width)));
  display.height = Math.max(320, Math.min(1000, Math.round(height)));
  document.documentElement.style.setProperty('--plasma-width', `${display.width}px`);
  document.documentElement.style.setProperty('--plasma-height', `${display.height}px`);
  plasmaWindow.dataset.windowWidth = String(display.width);
  plasmaWindow.dataset.windowHeight = String(display.height);
  if (persist) saveDisplay();
}

for (const handle of document.querySelectorAll('.resize-handle')) {
  handle.addEventListener('pointerdown', (event) => {
    if (mobileLayout.matches || visualMaximized || event.button !== 0) return;
    event.preventDefault();
    cancelActiveInteraction?.();
    const rect = plasmaWindow.getBoundingClientRect();
    const centreX = rect.left + rect.width / 2;
    const centreY = rect.top + rect.height / 2;
    const startDistanceX = Math.abs(event.clientX - centreX);
    const startDistanceY = Math.abs(event.clientY - centreY);
    handle.setPointerCapture(event.pointerId);
    liveResizing = true;
    plasmaWindow.classList.add('is-resizing');
    worker.postMessage({ type: 'resizePause' });
    let pendingSize = null;
    let visualFrame = null;
    let finished = false;

    const move = (moveEvent) => {
      if ((moveEvent.buttons & 1) === 0) {
        finish();
        return;
      }
      pendingSize = {
        width: rect.width
          + (Math.abs(moveEvent.clientX - centreX) - startDistanceX) * 2,
        height: rect.height
          + (Math.abs(moveEvent.clientY - centreY) - startDistanceY) * 2,
      };
      if (visualFrame !== null) return;
      visualFrame = requestAnimationFrame(() => {
        visualFrame = null;
        if (pendingSize) setWindowSize(pendingSize.width, pendingSize.height, false);
      });
    };
    const finish = () => {
      if (finished) return;
      finished = true;
      handle.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', finish, true);
      window.removeEventListener('pointercancel', finish, true);
      window.removeEventListener('blur', finish);
      if (pendingSize) setWindowSize(pendingSize.width, pendingSize.height, false);
      const current = windowPositions.get(plasmaWindow);
      if (current) {
        const recovered = clampWindowCenter(plasmaWindow, current.x, current.y);
        setWindowCenter(plasmaWindow, recovered.x, recovered.y);
      }
      plasmaWindow.classList.remove('is-resizing');
      liveResizing = false;
      saveDisplay();
      latestFrame = null;
      fitTerminal('resizeCommit');
      if (cancelActiveInteraction === finish) cancelActiveInteraction = null;
    };
    cancelActiveInteraction = finish;
    handle.addEventListener('pointermove', move);
    window.addEventListener('pointerup', finish, { once: true, capture: true });
    window.addEventListener('pointercancel', finish, { once: true, capture: true });
    window.addEventListener('blur', finish, { once: true });
    handle.addEventListener('lostpointercapture', finish, { once: true });
  });

  handle.addEventListener('keydown', (event) => {
    if (visualMaximized || mobileLayout.matches) return;
    if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const amount = event.shiftKey ? 40 : 10;
    const widthDelta = event.key === 'ArrowLeft' ? -amount : event.key === 'ArrowRight' ? amount : 0;
    const heightDelta = event.key === 'ArrowUp' ? -amount : event.key === 'ArrowDown' ? amount : 0;
    setWindowSize(display.width + widthDelta * 2, display.height + heightDelta * 2);
    fitTerminal();
  });
}

function beginVisualGeometryChange() {
  cancelActiveInteraction?.();
  liveResizing = true;
  latestFrame = null;
  plasmaWindow.classList.add('is-resizing');
  if (runtimeReady) worker.postMessage({ type: 'resizePause' });
}

function finishVisualGeometryChange(exactDimensions = null, scalePointSize = false) {
  requestAnimationFrame(() => {
    if (exactDimensions && scalePointSize) {
      setCharacterSize(pointSizeForFixedResolution(exactDimensions), false, false);
    }
    plasmaWindow.classList.remove('is-resizing');
    liveResizing = false;
    fitTerminal('resizeCommit', exactDimensions);
  });
}

function updateVisualModeLabel() {
  const label = mobileLayout.matches
    ? (mobileVisualFront ? 'Send visualization behind controls' : 'Bring visualization in front of controls')
    : (visualMaximized ? 'Restore visualization window' : 'Fill browser with visualization');
  visualModeButton.setAttribute('aria-label', label);
  visualModeButton.title = label;
}

function toggleVisualMode() {
  if (mobileLayout.matches) {
    mobileVisualFront = !mobileVisualFront;
    document.documentElement.dataset.mobileVisualFront = String(mobileVisualFront);
    visualModeButton.setAttribute('aria-pressed', String(mobileVisualFront));
    if (mobileVisualFront) {
      bringToFront(plasmaWindow);
    } else {
      plasmaWindow.style.zIndex = '50';
      controlsWindow.style.zIndex = '51';
      energyPanel.style.zIndex = '52';
      lutWindow.style.zIndex = '53';
      topWindowZ = Math.max(topWindowZ, 53);
    }
    updateVisualModeLabel();
    return;
  }
  beginVisualGeometryChange();
  let fixedDimensions;
  let scalePointSize = false;
  if (!visualMaximized) {
    const current = windowPositions.get(plasmaWindow)
      ?? { x: innerWidth / 2, y: innerHeight / 2 };
    visualRestoreGeometry = {
      width: display.width,
      height: display.height,
      fontSize: display.fontSize,
      columns: terminal.cols,
      lines: terminal.rows,
      terminalWidth: Math.max(1, terminalElement.clientWidth - 8),
      terminalHeight: Math.max(1, terminalElement.clientHeight - 8),
      x: current.x,
      y: current.y,
    };
    fixedDimensions = { columns: terminal.cols, lines: terminal.rows };
    visualFixedDimensions = fixedDimensions;
    scalePointSize = true;
    visualMaximized = true;
    plasmaWindow.classList.add('is-maximized');
  } else {
    visualMaximized = false;
    plasmaWindow.classList.remove('is-maximized');
    const restore = visualRestoreGeometry ?? {
      width: display.width,
      height: display.height,
      fontSize: display.fontSize,
      columns: terminal.cols,
      lines: terminal.rows,
      x: innerWidth / 2,
      y: innerHeight / 2,
    };
    fixedDimensions = { columns: restore.columns, lines: restore.lines };
    visualFixedDimensions = null;
    setWindowSize(restore.width, restore.height, false);
    setCharacterSize(restore.fontSize, false, false);
    const recovered = clampWindowCenter(plasmaWindow, restore.x, restore.y);
    setWindowCenter(plasmaWindow, recovered.x, recovered.y);
  }
  visualModeButton.setAttribute('aria-pressed', String(visualMaximized));
  updateVisualModeLabel();
  finishVisualGeometryChange(fixedDimensions, scalePointSize);
}

function resetWorkspaceLayout() {
  releaseAllActiveKeys();
  beginVisualGeometryChange();
  visualMaximized = false;
  mobileVisualFront = false;
  visualRestoreGeometry = null;
  visualFixedDimensions = null;
  plasmaWindow.classList.remove('is-maximized');
  visualModeButton.setAttribute('aria-pressed', 'false');
  updateVisualModeLabel();
  display = { ...DEFAULT_DISPLAY };
  setWindowSize(display.width, display.height, false);
  setCharacterSize(display.fontSize, false, false);
  saveDisplay();
  setWindowDocked('controls', false, false);
  setWindowDocked('energy', false, false);
  setWindowDocked('lut', true, false);
  resetWindowPositions();
  resetStackingOrder();
  finishVisualGeometryChange(DEFAULT_GRID);
  requestAnimationFrame(() => {
    terminal.focus();
    setKeyboardOwnership(true);
  });
}

globalResetButton.addEventListener('click', resetWorkspaceLayout);
visualModeButton.addEventListener('click', toggleVisualMode);
window.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  event.preventDefault();
  resetWorkspaceLayout();
}, { capture: true });

let pinch = null;
const touchDistance = (touches) => Math.hypot(
  touches[0].clientX - touches[1].clientX,
  touches[0].clientY - touches[1].clientY,
);
terminalElement.addEventListener('touchstart', (event) => {
  if (event.touches.length !== 2) return;
  pinch = { distance: touchDistance(event.touches), fontSize: display.fontSize };
}, { passive: true });
terminalElement.addEventListener('touchmove', (event) => {
  if (!pinch || event.touches.length !== 2) return;
  event.preventDefault();
  setCharacterSize(pinch.fontSize * touchDistance(event.touches) / pinch.distance, false);
}, { passive: false });
terminalElement.addEventListener('touchend', (event) => {
  if (event.touches.length >= 2) return;
  if (pinch) saveDisplay();
  pinch = null;
}, { passive: true });
terminalElement.addEventListener('touchcancel', () => { pinch = null; }, { passive: true });

mobileLayout.addEventListener('change', () => {
  if (mobileLayout.matches) {
    visualMaximized = false;
    plasmaWindow.classList.remove('is-maximized');
    visualModeButton.setAttribute('aria-pressed', 'false');
  }
  mobileVisualFront = false;
  resetStackingOrder();
  updateVisualModeLabel();
  resetWindowPositions();
  fitTerminal();
});
window.addEventListener('resize', () => {
  for (const element of Object.values(floatingWindows)) {
    if (element === plasmaWindow && (mobileLayout.matches || visualMaximized)) continue;
    const current = windowPositions.get(element);
    if (!current) continue;
    const recovered = clampWindowCenter(element, current.x, current.y);
    setWindowCenter(element, recovered.x, recovered.y);
  }
  if (visualMaximized && visualFixedDimensions) {
    setCharacterSize(pointSizeForFixedResolution(visualFixedDimensions), false, false);
    fitTerminal('resize', visualFixedDimensions);
  } else {
    fitTerminal();
  }
});

function exposeConfig(contents) {
  const configValue = (key) => contents.match(
    new RegExp(`^${key}\\s*=\\s*(.+)$`, 'm'))?.[1] ?? '';
  terminalElement.dataset.configLength = String(contents.length);
  terminalElement.dataset.baseSlot = contents.match(
    /^# base-slot = (\d+)$/m)?.[1] ?? '';
  terminalElement.dataset.freqY = configValue('freq-y');
  terminalElement.dataset.activeLut = configValue('active-lut');
  if (crypto.subtle) {
    crypto.subtle.digest('SHA-256', new TextEncoder().encode(contents))
      .then((digest) => {
        terminalElement.dataset.configSha256 = Array.from(
          new Uint8Array(digest),
          (byte) => byte.toString(16).padStart(2, '0')).join('');
      })
      .catch(() => { /* Observability must never affect the animation. */ });
  }
}

worker.addEventListener('message', ({ data }) => {
  if (data.type === 'frame') {
    receiveFrame(data.frame);
  } else if (data.type === 'ready') {
    runtimeReady = true;
    sendEnergyConfig();
    worker.postMessage({ type: 'keybedLatches', mask: keybedLatchMask });
  } else if (data.type === 'status') {
    statusElement.textContent = data.message;
  } else if (data.type === 'config') {
    exposeConfig(data.contents);
    try {
      localStorage.setItem(CONFIG_STORAGE_KEY, data.contents);
    } catch {
      // Persistence is best-effort; the in-worker session remains functional.
    }
  } else if (data.type === 'metrics') {
    metrics.worker = data.metrics;
    metrics.lastRandomSlot = data.metrics.lastRandomSlot;
    terminalElement.dataset.producedFps = data.metrics.producedFps.toFixed(2);
    terminalElement.dataset.computeMs = data.metrics.averageComputeMs.toFixed(2);
    terminalElement.dataset.lastRandomSlot = data.metrics.lastRandomSlot ?? '';
    terminalElement.dataset.freqY = String(data.metrics.freqY);
    terminalElement.dataset.activeLut = data.metrics.activeLut;
    terminalElement.dataset.workerKeyboardOwned = String(data.metrics.keyboardOwned);
    terminalElement.dataset.keyUpdates = String(data.metrics.keyUpdates);
    terminalElement.dataset.pressedPolls = String(data.metrics.pressedPolls);
    terminalElement.dataset.lastAction = data.metrics.lastAction;
    terminalElement.dataset.coalescedFrames = String(data.metrics.coalescedFrames);
    terminalElement.dataset.energyEnabled = String(data.metrics.energyEnabled);
    terminalElement.dataset.energyOutput = Number(data.metrics.energyOutput).toFixed(3);
    terminalElement.dataset.energyPosition = Number(data.metrics.energyPosition).toFixed(4);
    terminalElement.dataset.energyWave = data.metrics.energyWave;
    terminalElement.dataset.energyTargets = data.metrics.energyTargets.join(',');
    terminalElement.dataset.energyTargetMask = String(data.metrics.energyTargetMask);
    terminalElement.dataset.resizeCommits = String(data.metrics.resizeCommits);
    terminalElement.dataset.undoDepth = String(data.metrics.undoDepth);
    terminalElement.dataset.fps = String(data.metrics.fps);
    terminalElement.dataset.keybedLatchMask = String(data.metrics.keybedLatchMask ?? 0);
    terminalElement.dataset.lutSlot = String(data.metrics.lutSlot ?? 'none');
    terminalElement.dataset.lutRevision = String(data.metrics.lutRevision ?? 0);
    if (document.activeElement === fpsInput || document.activeElement === fpsPresetSelect) {
      selectedFps = Number(data.metrics.fps);
    } else {
      setFpsField(data.metrics.fps, false);
    }
    updateKeybedLatches(data.metrics.keybedLatchMask ?? keybedLatchMask, false);
    updateUndoDepth(data.metrics.undoDepth);
    energyPanel.style.setProperty('--energy-pulse', String(
      Math.min(1, Math.abs(Number(data.metrics.energyOutput)) / 100)));
    updateEnergyTargets(data.metrics.energyTargets);
    if (performance.memory) {
      terminalElement.dataset.heapUsedBytes = String(performance.memory.usedJSHeapSize);
    }
  } else if (data.type === 'keyAck') {
    terminalElement.dataset.workerLastKey = `${data.action}:${data.key}`;
  } else if (data.type === 'energyAck') {
    energyPanel.dataset.workerEnergyAck = String(data.config.enabled);
  } else if (data.type === 'resizePaused') {
    terminalElement.dataset.resizePaused = 'true';
  } else if (data.type === 'resizeCommitted') {
    terminalElement.dataset.resizePaused = 'false';
    terminalElement.dataset.columns = String(data.columns);
    terminalElement.dataset.lines = String(data.lines);
  } else if (data.type === 'fpsAck') {
    setFpsField(data.fps, false);
  } else if (data.type === 'undoAck') {
    terminalElement.dataset.lastUndoRestored = String(data.restored);
    updateUndoDepth(data.undoDepth);
  } else if (data.type === 'keybedLatchesAck') {
    updateKeybedLatches(data.mask, false);
  } else if (data.type === 'parametersResetAck') {
    updateKeybedLatches(0, false);
    terminalElement.dataset.parametersReset = String(
      Number(terminalElement.dataset.parametersReset ?? 0) + 1);
  } else if (data.type === 'lutState') {
    updateLutFields(data.state);
  } else if (data.type === 'lutAck') {
    lutWindow.dataset.lastLutWriteCount = String(data.count);
  } else if (data.type === 'lutError') {
    statusElement.hidden = false;
    statusElement.classList.add('error');
    statusElement.textContent = `LUT update was rejected: ${data.message}`;
  } else if (data.type === 'controlError') {
    statusElement.hidden = false;
    statusElement.classList.add('error');
    statusElement.textContent = `Control was rejected: ${data.message}`;
  } else if (data.type === 'energyError') {
    statusElement.hidden = false;
    statusElement.classList.add('error');
    statusElement.textContent = `Energy controls were rejected: ${data.message}`;
  } else if (data.type === 'error') {
    showError(data.message);
  }
});
worker.addEventListener('error', (event) => showError(event.message));

function setKeyboardOwnership(owned) {
  owned = Boolean(owned) && document.visibilityState === 'visible';
  if (owned === ownsKeyboard) return;
  if (!owned) {
    for (const key of heldKeys) suppressedUntilRelease.add(key);
    heldKeys.clear();
    activeKeySources.clear();
    for (const button of keyButtons.values()) button.classList.remove('is-active');
  }
  ownsKeyboard = owned;
  worker.postMessage({ type: 'focus', owned });
}

function canonicalKey(event) {
  return event.key.length === 1 ? event.key.toUpperCase() : event.key;
}

function editingControlActive(eventTarget = null) {
  return Boolean(eventTarget?.matches?.('input, select, textarea')
    || document.activeElement?.matches?.('input, select, textarea'));
}

function isConsumedCommand(event, key) {
  if (DIGIT_KEYS.has(key)) return !event.altKey && !event.shiftKey;
  if (key === 'S' && event.altKey && !event.ctrlKey && !event.shiftKey) return true;
  if (PARAMETER_KEYS.has(key)) return !event.altKey;
  return key === 'P' && !event.altKey && !event.ctrlKey && !event.shiftKey;
}

function modifiersFrom(event = {}) {
  return {
    shift: Boolean(event.shiftKey),
    ctrl: Boolean(event.ctrlKey),
    alt: Boolean(event.altKey),
  };
}

function sendKeyDown(key, modifiers = {}, source = 'programmatic') {
  if (!ownsKeyboard || !COMMAND_KEYS.has(key)) return false;
  let sources = activeKeySources.get(key);
  if (!sources) {
    sources = new Set();
    activeKeySources.set(key, sources);
  }
  if (sources.has(source)) return false;
  const firstSource = sources.size === 0;
  sources.add(source);
  heldKeys.add(key);
  keyButtons.get(key)?.classList.add('is-active');
  if (firstSource) {
    terminalElement.dataset.keydownCount = String(
      Number(terminalElement.dataset.keydownCount ?? 0) + 1);
    worker.postMessage({ type: 'key', action: 'down', key, ...modifiers });
  }
  return true;
}

function sendKeyUp(key, modifiers = {}, source = 'programmatic') {
  const sources = activeKeySources.get(key);
  if (!sources?.has(source)) return false;
  sources.delete(source);
  if (sources.size > 0) return true;
  activeKeySources.delete(key);
  heldKeys.delete(key);
  keyButtons.get(key)?.classList.remove('is-active');
  worker.postMessage({ type: 'key', action: 'up', key, ...modifiers });
  return true;
}

function releaseAllActiveKeys() {
  for (const [key, sources] of [...activeKeySources.entries()]) {
    for (const source of [...sources]) sendKeyUp(key, {}, source);
  }
}

window.__plasmaInput = { keyDown: sendKeyDown, keyUp: sendKeyUp };

for (const [key, button] of keyButtons) {
  let pointerSource = null;
  const finishPointer = (event) => {
    if (!pointerSource) return;
    sendKeyUp(key, modifiersFrom(event), pointerSource);
    if (button.hasPointerCapture(event.pointerId)) button.releasePointerCapture(event.pointerId);
    pointerSource = null;
  };
  button.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    setKeyboardOwnership(true);
    pointerSource = `pointer:${event.pointerId}:${key}`;
    button.setPointerCapture(event.pointerId);
    sendKeyDown(key, modifiersFrom(event), pointerSource);
  });
  button.addEventListener('pointerup', finishPointer);
  button.addEventListener('pointercancel', finishPointer);
  button.addEventListener('pointermove', (event) => {
    if (!pointerSource) return;
    const rect = button.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right
        || event.clientY < rect.top || event.clientY > rect.bottom) finishPointer(event);
  });
  button.addEventListener('keydown', (event) => {
    if (![' ', 'Enter'].includes(event.key) || event.repeat) return;
    event.preventDefault();
    sendKeyDown(key, modifiersFrom(event), `accessible:${key}`);
  });
  button.addEventListener('keyup', (event) => {
    if (![' ', 'Enter'].includes(event.key)) return;
    event.preventDefault();
    sendKeyUp(key, modifiersFrom(event), `accessible:${key}`);
  });
  button.addEventListener('contextmenu', (event) => event.preventDefault());
}

window.addEventListener('keydown', (event) => {
  const key = canonicalKey(event);
  terminalElement.dataset.lastKey = key;
  terminalElement.dataset.keyboardOwned = String(ownsKeyboard);
  if (editingControlActive(event.target)) return;
  if (!ownsKeyboard || !COMMAND_KEYS.has(key)) return;
  if (suppressedUntilRelease.has(key)) {
    if (isConsumedCommand(event, key)) event.preventDefault();
    return;
  }
  if (isConsumedCommand(event, key)) event.preventDefault();
  sendKeyDown(key, modifiersFrom(event), 'keyboard');
}, { capture: true });

window.addEventListener('keyup', (event) => {
  const key = canonicalKey(event);
  suppressedUntilRelease.delete(key);
  if (editingControlActive(event.target)) return;
  if (!COMMAND_KEYS.has(key)) return;
  sendKeyUp(key, modifiersFrom(event), 'keyboard');
}, { capture: true });

window.addEventListener('blur', () => setKeyboardOwnership(false));
window.addEventListener('focus', () => {
  setKeyboardOwnership(true);
  terminal.focus();
});
document.addEventListener('visibilitychange', () => {
  setKeyboardOwnership(document.visibilityState === 'visible' && document.hasFocus());
});
document.addEventListener('focusin', (event) => {
  if (event.target.matches?.('input, select, textarea')) setKeyboardOwnership(false);
});
document.addEventListener('focusout', () => {
  requestAnimationFrame(() => {
    if (!document.activeElement?.matches?.('input, select, textarea')) {
      setKeyboardOwnership(document.visibilityState === 'visible' && document.hasFocus());
    }
  });
});
terminalElement.addEventListener('pointerdown', () => {
  terminal.focus();
  setKeyboardOwnership(true);
});
terminalElement.addEventListener('focusin', () => setKeyboardOwnership(true));

new ResizeObserver(() => {
  fitTerminal();
}).observe(terminalElement);

let restoredConfig = null;
try {
  restoredConfig = localStorage.getItem(CONFIG_STORAGE_KEY)
    ?? LEGACY_CONFIG_STORAGE_KEYS
      .map((key) => localStorage.getItem(key))
      .find((contents) => contents !== null);
  if (localStorage.getItem(FPS_DEFAULT_MIGRATION_KEY) !== '1') {
    restoredConfig = restoredConfig?.replace(
      /^fps\s*=\s*24(?:\.0+)?\s*$/m, `fps = ${DEFAULT_FPS}`) ?? null;
    localStorage.setItem(FPS_DEFAULT_MIGRATION_KEY, '1');
  }
} catch { /* noop */ }
if (restoredConfig) exposeConfig(restoredConfig);
worker.postMessage({
  type: 'start',
  columns: terminal.cols,
  lines: terminal.rows,
  synchronizedOutput: dec2026,
  config: restoredConfig,
});
terminal.focus();
setWindowSize(display.width, display.height, false);
setCharacterSize(display.fontSize, false, false);
updateVisualModeLabel();
if (firstDisplayLoad) {
  terminal.resize(DEFAULT_GRID.columns, DEFAULT_GRID.lines);
  fitTerminal('resize', DEFAULT_GRID);
}
requestAnimationFrame(() => {
  setWindowDocked('controls', true, false);
  setWindowDocked('energy', true, false);
  setWindowDocked('lut', true, false);
  resetWindowPositions();
  resetStackingOrder();
});
