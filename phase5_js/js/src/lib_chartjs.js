// Chart.js 4 on a recording Canvas2D (BasicPlatform: no window/document).
// input: { config, width, height }  ->  JSON { op_count, counts, ops }
import { Chart, registerables } from 'chart.js';
import { createRecordingCanvas, makeBackend } from './canvas_adapter.js';

Chart.register(...registerables);
Chart.defaults.animation = false;
Chart.defaults.responsive = false;
Chart.defaults.devicePixelRatio = 1;
Chart.defaults.events = [];

const backend = makeBackend();
globalThis.__p5.info.canvas_backend = backend.native ? 'rust-host' : 'js';

globalThis.__p5.register({
  name: 'chartjs',
  run(input) {
    backend.reset();
    const canvas = createRecordingCanvas(input.width || 600, input.height || 400, backend);
    const config = JSON.parse(JSON.stringify(input.config));
    config.options = Object.assign({ animation: false, responsive: false, devicePixelRatio: 1, events: [] }, config.options || {});
    const chart = new Chart(canvas, config);
    chart.destroy();
    const ops = backend.ops();
    const counts = {};
    for (const op of ops) counts[op[0]] = (counts[op[0]] || 0) + 1;
    return JSON.stringify({ op_count: ops.length, counts, ops });
  }
});
