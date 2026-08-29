import { loadPyodide } from 'https://cdn.jsdelivr.net/pyodide/v0.28.2/full/pyodide.mjs';

let runtime = null;
let running = false;
let producedFrames = 0;
let metricsWindowStarted = performance.now();
let computeTotal = 0;
let hostReady = true;
let pendingFrame = null;
let coalescedFrames = 0;

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

async function frameLoop() {
  while (running) {
    const frameStarted = performance.now();
    const frame = runtime.step(frameStarted / 1000);
    const computedAt = performance.now();
    computeTotal += computedAt - frameStarted;
    producedFrames += 1;
    offerFrame(frame);

    const config = runtime.consume_persistence_text();
    if (typeof config === 'string') {
      self.postMessage({ type: 'config', contents: config });
    }
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
  } else if (data.type === 'focus' && runtime) {
    runtime.set_keyboard_ownership(data.owned);
  } else if (data.type === 'key' && runtime) {
    runtime.handle_key_event(data.action, data.key, data.shift, data.ctrl, data.alt);
    self.postMessage({ type: 'keyAck', action: data.action, key: data.key });
  } else if (data.type === 'framePresented') {
    flushPendingFrame();
  }
});
