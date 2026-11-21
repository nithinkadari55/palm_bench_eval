// KPI dashboard: createElement, textContent, dataset, append, arrow functions, destructuring.
const kpis = [
  { label: 'Revenue', value: 1284000, delta: 0.124, unit: '$' },
  { label: 'Customers', value: 8421, delta: -0.031, unit: '' },
  { label: 'Churn', value: 0.027, delta: 0.002, unit: '%' },
  { label: 'NPS', value: 61, delta: 0.05, unit: '' }
];
const grid = document.getElementById('kpis');
const pct = (x) => (x * 100).toFixed(1) + '%';
for (const { label, value, delta, unit } of kpis) {
  const card = document.createElement('section');
  card.className = 'card';
  card.dataset.metric = label.toLowerCase();
  const h = document.createElement('h3');
  h.textContent = label;
  const v = document.createElement('p');
  v.className = 'value';
  v.textContent = unit === '%' ? pct(value) : unit + String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const d = document.createElement('span');
  d.classList.add('delta', delta >= 0 ? 'up' : 'down');
  d.textContent = (delta >= 0 ? '▲ ' : '▼ ') + pct(Math.abs(delta));
  card.append(h, v, d);
  grid.appendChild(card);
}
const best = kpis.reduce((a, b) => (b.delta > a.delta ? b : a));
grid.querySelector(`[data-metric="${best.label.toLowerCase()}"]`).classList.add('highlight');
document.body.setAttribute('data-cards', String(grid.children.length));
