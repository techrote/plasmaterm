import { loadPyodide } from 'https://cdn.jsdelivr.net/pyodide/v0.28.2/full/pyodide.mjs';

let runtime = null;
let running = false;
let producedFrames = 0;
let metricsWindowStarted = performance.now();
let computeTotal = 0;
let hostReady = true;
let pendingFrame = null;
let coalescedFrames = 0;
let renderPaused = false;

async function fetchSource(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Unable to load ${path} (${response.status})`);
  return response.text();
}

function postMetrics(now) {
  const elapsed = now - metricsWindowStarted;
  if (elapsed < 1000) return;
  const runtimeMetrics = JSON.parse(runtime.metrics_json());
  self.postMessage({
    type: 'metrics',
    metrics: {
      producedFps: producedFrames * 1000 / elapsed,
      averageComputeMs: producedFrames ? computeTotal / producedFrames : 0,
      coalescedFrames,
      ...runtimeMetrics,
    },
  });
  producedFrames = 0;
  computeTotal = 0;
  metricsWindowStarted = now;
}

function offerFrame(frame) {
  if (hostReady) {
    hostReady = false;
    self.postMessage({ type: 'frame', frame });
    return;
  }
  if (pendingFrame !== null) coalescedFrames += 1;
  pendingFrame = frame;
}

function flushPendingFrame() {
  hostReady = true;
  if (pendingFrame === null) return;
  const frame = pendingFrame;
  pendingFrame = null;
  hostReady = false;
  self.postMessage({ type: 'frame', frame });
}

function validEnergyConfig(config) {
  const numeric = ['depth', 'rate', 'widthMin', 'widthMax', 'offset', 'targetMask'];
  return config && typeof config.enabled === 'boolean'
    && numeric.every((key) => Number.isFinite(config[key]))
    && config.depth >= 0 && config.depth <= 100
    && config.rate >= -6 && config.rate <= 6
    && config.widthMin >= -1 && config.widthMax <= 1
    && config.widthMin <= config.widthMax
    && config.offset >= -100 && config.offset <= 100
    && Number.isInteger(config.targetMask) && config.targetMask >= 0 && config.targetMask < 32
    && ['sine', 'smooth-triangle', 'loop-noise', 'wander-noise'].includes(config.wave);
}

function validFps(fps) {
  return Number.isFinite(fps) && fps >= 1 && fps <= 1000;
}

function validKeybedLatchMask(mask) {
  return Number.isInteger(mask) && mask >= 0 && mask <= 3;
}

function normalizedLutColors(colors) {
  if (!Array.isArray(colors) || colors.length !== 256) return null;
  if (!colors.every((color) => (
    typeof color === 'string' && /^[0-9a-fA-F]{6}$/.test(color)
  ))) return null;
  return colors.map((color) => color.toUpperCase());
}

function postPersistence() {
  const config = runtime.consume_persistence_text();
  if (typeof config === 'string') {
    self.postMessage({ type: 'config', contents: config });
  }
}

function postLutState() {
  const serialized = runtime.consume_lut_state_json();
  if (typeof serialized !== 'string') return;
  try {
    self.postMessage({ type: 'lutState', state: JSON.parse(serialized) });
  } catch (error) {
    self.postMessage({
      type: 'lutError',
      message: `Invalid LUT state from runtime: ${error?.message ?? String(error)}`,
    });
  }
}

function flushRuntimeState() {
  postPersistence();
  postLutState();
}

async function frameLoop() {
  while (running) {
    if (renderPaused) {
      await new Promise((resolve) => setTimeout(resolve, 16));
      continue;
    }
    const frameStarted = performance.now();
    const frame = runtime.step(frameStarted / 1000);
    const computedAt = performance.now();
    computeTotal += computedAt - frameStarted;
    producedFrames += 1;
    offerFrame(frame);

    flushRuntimeState();
    postMetrics(computedAt);

    const delay = Math.max(0, runtime.frame_interval_ms() - (performance.now() - frameStarted));
    await new Promise((resolve) => setTimeout(resolve, delay));
  }
}

async function start(data) {
  self.postMessage({ type: 'status', message: 'Starting Python/WASM…' });
  const [pyodide, plasmaSource, generatorSource] = await Promise.all([
    loadPyodide(),
    fetchSource('../plasma.py'),
    fetchSource('../plasma_config_gen.py'),
  ]);
  pyodide.FS.mkdir('/app');
  pyodide.FS.writeFile('/app/plasma.py', plasmaSource);
  pyodide.FS.writeFile('/app/plasma_config_gen.py', generatorSource);
  if (data.config) pyodide.FS.writeFile('/app/plasma.conf', data.config);
  pyodide.runPython("import sys; sys.path.insert(0, '/app'); import plasma");
  const plasma = pyodide.pyimport('plasma');
  try {
    runtime = plasma.BrowserRuntime(
      data.columns, data.lines, Boolean(data.synchronizedOutput));
  } catch (error) {
    if (!data.config) throw error;
    try { pyodide.FS.unlink('/app/plasma.conf'); } catch { /* noop */ }
    runtime = plasma.BrowserRuntime(
      data.columns, data.lines, Boolean(data.synchronizedOutput));
  }
  plasma.destroy();
  running = true;
  self.postMessage({ type: 'ready' });
  flushRuntimeState();
  await frameLoop();
}

self.addEventListener('message', ({ data }) => {
  if (data.type === 'start' && !running) {
    start(data).catch((error) => {
      running = false;
      self.postMessage({ type: 'error', message: error?.message ?? String(error) });
    });
  } else if (data.type === 'resize' && runtime) {
    runtime.set_size(data.columns, data.lines);
  } else if (data.type === 'resizePause' && runtime) {
    renderPaused = true;
    pendingFrame = null;
    hostReady = true;
    self.postMessage({ type: 'resizePaused' });
  } else if (data.type === 'resizeCommit' && runtime) {
    pendingFrame = null;
    hostReady = true;
    runtime.set_size(data.columns, data.lines, true);
    renderPaused = false;
    self.postMessage({
      type: 'resizeCommitted', columns: data.columns, lines: data.lines,
    });
  } else if (data.type === 'fps' && runtime) {
    if (!validFps(data.fps)) {
      self.postMessage({
        type: 'controlError', message: 'FPS must be a finite value from 1 to 1000.',
      });
      return;
    }
    try {
      runtime.set_fps(data.fps);
      self.postMessage({ type: 'fpsAck', fps: data.fps });
      flushRuntimeState();
    } catch (error) {
      self.postMessage({ type: 'controlError', message: error?.message ?? String(error) });
    }
  } else if (data.type === 'keybedLatches' && runtime) {
    if (!validKeybedLatchMask(data.mask)) {
      self.postMessage({
        type: 'controlError', message: 'Keybed latch mask must be an integer from 0 to 3.',
      });
      return;
    }
    try {
      runtime.set_keybed_latches(data.mask);
      self.postMessage({ type: 'keybedLatchesAck', mask: data.mask });
      flushRuntimeState();
    } catch (error) {
      self.postMessage({ type: 'controlError', message: error?.message ?? String(error) });
    }
  } else if (data.type === 'resetParameters' && runtime) {
    try {
      runtime.reset_keybed_parameters();
      self.postMessage({ type: 'parametersResetAck' });
      flushRuntimeState();
    } catch (error) {
      self.postMessage({ type: 'controlError', message: error?.message ?? String(error) });
    }
  } else if (data.type === 'setLut' && runtime) {
    const colors = normalizedLutColors(data.colors);
    if (colors === null) {
      self.postMessage({
        type: 'lutError',
        message: 'LUT must contain exactly 256 six-digit hexadecimal colours.',
      });
      return;
    }
    try {
      runtime.replace_lut_json(JSON.stringify(colors));
      self.postMessage({ type: 'lutAck', count: colors.length });
      flushRuntimeState();
    } catch (error) {
      self.postMessage({ type: 'lutError', message: error?.message ?? String(error) });
    }
  } else if (data.type === 'undoRandomize' && runtime) {
    const restored = runtime.undo_randomize();
    const undoDepth = JSON.parse(runtime.metrics_json()).undoDepth;
    self.postMessage({ type: 'undoAck', restored, undoDepth });
    flushRuntimeState();
  } else if (data.type === 'focus' && runtime) {
    runtime.set_keyboard_ownership(data.owned);
  } else if (data.type === 'key' && runtime) {
    runtime.handle_key_event(data.action, data.key, data.shift, data.ctrl, data.alt);
    self.postMessage({ type: 'keyAck', action: data.action, key: data.key });
    flushRuntimeState();
  } else if (data.type === 'energy' && runtime) {
    if (!validEnergyConfig(data.config)) {
      self.postMessage({ type: 'energyError', message: 'Invalid Energy control values.' });
      return;
    }
    const config = data.config;
    try {
      runtime.configure_energy(
        config.enabled, config.depth, config.rate,
        config.widthMin, config.widthMax, config.offset,
        config.targetMask, config.wave,
      );
      self.postMessage({ type: 'energyAck', config });
    } catch (error) {
      self.postMessage({ type: 'energyError', message: error?.message ?? String(error) });
    }
  } else if (data.type === 'framePresented') {
    flushPendingFrame();
  }
});
