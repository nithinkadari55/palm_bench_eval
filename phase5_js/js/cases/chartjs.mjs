// 10 Chart.js chart types. Animation, responsiveness and events are off (BasicPlatform).
const labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
const ds = (label, data, extra) => Object.assign({ label, data }, extra || {});
const palette = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948'];

export default [
  { id: 'bar', config: { type: 'bar', data: { labels, datasets: [ds('2025', [12, 19, 3, 5, 2, 3], { backgroundColor: palette[0] }), ds('2026', [8, 11, 7, 9, 13, 4], { backgroundColor: palette[1] })] }, options: { plugins: { title: { display: true, text: 'Grouped bars' } } } } },
  { id: 'bar-horizontal-stacked', config: { type: 'bar', data: { labels, datasets: [ds('A', [5, 6, 7, 8, 9, 10]), ds('B', [3, 2, 4, 1, 5, 2])] }, options: { indexAxis: 'y', scales: { x: { stacked: true }, y: { stacked: true } } } } },
  { id: 'line', config: { type: 'line', data: { labels, datasets: [ds('Visitors', [65, 59, 80, 81, 56, 55], { borderColor: palette[2], tension: 0.3, borderDash: [5, 5] })] }, options: { plugins: { legend: { position: 'bottom' } } } } },
  { id: 'area-filled', config: { type: 'line', data: { labels, datasets: [ds('Fill', [3, 7, 4, 9, 6, 8], { fill: true, backgroundColor: 'rgba(78,121,167,0.3)', borderColor: palette[0] }), ds('Origin', [1, 2, 3, 2, 1, 2], { fill: 'origin' })] }, options: { scales: { y: { beginAtZero: true, ticks: { stepSize: 2 } } } } } },
  { id: 'pie', config: { type: 'pie', data: { labels: ['Red', 'Blue', 'Yellow'], datasets: [ds('Votes', [300, 50, 100], { backgroundColor: palette.slice(0, 3) })] } } },
  { id: 'doughnut', config: { type: 'doughnut', data: { labels: labels.slice(0, 4), datasets: [ds('Share', [10, 20, 30, 40], { backgroundColor: palette.slice(0, 4), borderWidth: 2 })] }, options: { cutout: '60%', plugins: { title: { display: true, text: 'Doughnut' } } } } },
  { id: 'polarArea', config: { type: 'polarArea', data: { labels: labels.slice(0, 5), datasets: [ds('Polar', [11, 16, 7, 3, 14], { backgroundColor: palette.slice(0, 5) })] } } },
  { id: 'radar', config: { type: 'radar', data: { labels: ['Eating', 'Drinking', 'Sleeping', 'Designing', 'Coding', 'Cycling'], datasets: [ds('Me', [65, 59, 90, 81, 56, 55], { fill: true }), ds('You', [28, 48, 40, 19, 96, 27])] } } },
  { id: 'scatter', config: { type: 'scatter', data: { datasets: [ds('Points', Array.from({ length: 20 }, (_, i) => ({ x: i - 10, y: Math.round(100 * Math.sin(i / 3)) / 10 })), { pointRadius: 4 })] }, options: { scales: { x: { type: 'linear', position: 'bottom' }, y: { type: 'logarithmic', min: 0.1, max: 100 } } } } },
  { id: 'bubble', config: { type: 'bubble', data: { datasets: [ds('Bubbles', [{ x: 20, y: 30, r: 15 }, { x: 40, y: 10, r: 10 }, { x: 25, y: 22, r: 6 }, { x: 33, y: 41, r: 12 }], { backgroundColor: 'rgba(225,87,89,0.5)' })] }, options: { plugins: { legend: { display: false } } } } }
].map((c) => ({ id: c.id, input: { config: c.config, width: 600, height: 400 } }));
