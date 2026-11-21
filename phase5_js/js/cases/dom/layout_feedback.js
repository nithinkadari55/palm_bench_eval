// Layout feedback: decisions taken from measured geometry (equal-height cards, wide/narrow
// classes, overflow detection, progress label placement).
const cards = Array.from(document.querySelectorAll('.card'));
const heights = cards.map((c) => c.offsetHeight);
const maxH = Math.max.apply(null, heights.map((h) => (typeof h === 'number' && h === h ? h : 0)));
cards.forEach((c) => { c.style.minHeight = maxH + 'px'; });
const box = document.getElementById('main').getBoundingClientRect();
document.body.classList.add(box && box.width > 600 ? 'wide' : 'narrow');
const title = document.getElementById('title');
if (title.scrollWidth > title.clientWidth) title.classList.add('truncated');
const bar = document.getElementById('bar');
const w = bar.getBoundingClientRect().width;
document.getElementById('bar-label').textContent = w > 0 ? Math.round(w) + 'px' : 'no layout';
document.body.setAttribute('data-measured', JSON.stringify({ maxH, mainWidth: box ? box.width : null, barWidth: w }));
