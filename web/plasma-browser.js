const CONFIG_STORAGE_KEY = 'plasmaterm.web-v0.1a.config';
const PARAMETER_KEYS = new Set('QAWSEDRFTGYHUJIKOL');
const DIGIT_KEYS = new Set('0123456789');
const MODIFIER_KEYS = new Set(['Shift', 'Control', 'Alt']);
const terminalElement = document.querySelector('#terminal');
const statusElement = document.querySelector('#status');
const dec2026 = new URLSearchParams(location.search).get('sync') === '1';
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
  fontSize: 14,
  lineHeight: 1,
  letterSpacing: 0,
  scrollback: 0,
  theme: { background: '#050509', foreground: '#d8d5df' },
});
const fitAddon = new FitAddon();
terminal.loadAddon(fitAddon);
terminal.open(terminalElement);
fitAddon.fit();

let latestFrame = null;
let presentationScheduled = false;
let terminalWriting = false;
let ownsKeyboard = document.hasFocus() && document.visibilityState === 'visible';
const heldKeys = new Set();
const suppressedUntilRelease = new Set();
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
  if (latestFrame !== null) metrics.droppedFrames += 1;
  latestFrame = frame;
  terminalElement.dataset.receivedFrames = String(metrics.receivedFrames);
  terminalElement.dataset.droppedFrames = String(metrics.droppedFrames);
  schedulePresentation();
}

const worker = new Worker('./plasma-worker.js', { type: 'module' });

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
    if (performance.memory) {
      terminalElement.dataset.heapUsedBytes = String(performance.memory.usedJSHeapSize);
    }
  } else if (data.type === 'keyAck') {
    terminalElement.dataset.workerLastKey = `${data.action}:${data.key}`;
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
  }
  ownsKeyboard = owned;
  worker.postMessage({ type: 'focus', owned });
}

function canonicalKey(event) {
  return event.key.length === 1 ? event.key.toUpperCase() : event.key;
}

function isConsumedCommand(event, key) {
  if (DIGIT_KEYS.has(key)) return !event.altKey && !event.shiftKey;
  if (key === 'S' && event.altKey && !event.ctrlKey && !event.shiftKey) return true;
  if (PARAMETER_KEYS.has(key)) return !event.altKey;
  return key === 'P' && !event.altKey && !event.ctrlKey && !event.shiftKey;
}

window.addEventListener('keydown', (event) => {
  const key = canonicalKey(event);
  terminalElement.dataset.lastKey = key;
  terminalElement.dataset.keyboardOwned = String(ownsKeyboard);
  if (!ownsKeyboard || (!MODIFIER_KEYS.has(key)
      && !DIGIT_KEYS.has(key) && !PARAMETER_KEYS.has(key) && key !== 'P')) return;
  if (suppressedUntilRelease.has(key)) {
    if (isConsumedCommand(event, key)) event.preventDefault();
    return;
  }
  if (isConsumedCommand(event, key)) event.preventDefault();
  heldKeys.add(key);
  terminalElement.dataset.keydownCount = String(
    Number(terminalElement.dataset.keydownCount ?? 0) + 1);
  worker.postMessage({
    type: 'key', action: 'down', key,
    shift: event.shiftKey, ctrl: event.ctrlKey, alt: event.altKey,
  });
}, { capture: true });

window.addEventListener('keyup', (event) => {
  const key = canonicalKey(event);
  suppressedUntilRelease.delete(key);
  heldKeys.delete(key);
  if (!MODIFIER_KEYS.has(key)
      && !DIGIT_KEYS.has(key) && !PARAMETER_KEYS.has(key) && key !== 'P') return;
  worker.postMessage({
    type: 'key', action: 'up', key,
    shift: event.shiftKey, ctrl: event.ctrlKey, alt: event.altKey,
  });
}, { capture: true });

window.addEventListener('blur', () => setKeyboardOwnership(false));
window.addEventListener('focus', () => {
  setKeyboardOwnership(true);
  terminal.focus();
});
document.addEventListener('visibilitychange', () => {
  setKeyboardOwnership(document.visibilityState === 'visible' && document.hasFocus());
});
terminalElement.addEventListener('pointerdown', () => {
  terminal.focus();
  setKeyboardOwnership(true);
});
terminalElement.addEventListener('focusin', () => setKeyboardOwnership(true));

let resizeScheduled = false;
new ResizeObserver(() => {
  if (resizeScheduled) return;
  resizeScheduled = true;
  requestAnimationFrame(() => {
    resizeScheduled = false;
    fitAddon.fit();
    metrics.dimensions = { columns: terminal.cols, lines: terminal.rows };
    terminalElement.dataset.columns = String(terminal.cols);
    terminalElement.dataset.lines = String(terminal.rows);
    worker.postMessage({ type: 'resize', columns: terminal.cols, lines: terminal.rows });
  });
}).observe(terminalElement);

let restoredConfig = null;
try { restoredConfig = localStorage.getItem(CONFIG_STORAGE_KEY); } catch { /* noop */ }
if (restoredConfig) exposeConfig(restoredConfig);
worker.postMessage({
  type: 'start',
  columns: terminal.cols,
  lines: terminal.rows,
  synchronizedOutput: dec2026,
  config: restoredConfig,
});
terminal.focus();
