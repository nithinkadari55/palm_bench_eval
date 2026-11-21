// Report with inline styles, progress bars, Date and toLocaleString: the locale-dependent
// calls are typical of LLM output and expose the missing-Intl gap of QuickJS-NG.
const rows = [
  { region: 'EMEA', target: 2500000, actual: 2712345.5 },
  { region: 'APAC', target: 1800000, actual: 1234567.891 },
  { region: 'AMER', target: 3200000, actual: 3010000 }
];
const table = document.querySelector('#report');
rows.forEach((r) => {
  const ratio = Math.min(r.actual / r.target, 1.5);
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${r.region}</td><td class="num">${r.actual.toLocaleString('en-US')}</td><td><div class="bar"><div class="fill"></div></div></td>`;
  const fill = tr.querySelector('.fill');
  fill.style.width = (ratio * 100).toFixed(1) + '%';
  fill.style.backgroundColor = ratio >= 1 ? '#2e7d32' : '#c62828';
  table.appendChild(tr);
});
const generated = new Date();
document.querySelector('#generated').textContent = 'Generated ' + generated.toISOString().slice(0, 10) +
  ' (' + generated.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' }) + ')';
const total = rows.reduce((s, r) => s + r.actual, 0);
document.querySelector('#total').textContent = total.toLocaleString('en-US', { maximumFractionDigits: 0 });
document.querySelector('#total').setAttribute('title', new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(total));
