// Table of contents: querySelectorAll over headings, slug ids, nested lists, anchors.
const slug = (s) => s.toLowerCase().trim().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-');
const nav = document.querySelector('nav#toc');
const root = document.createElement('ol');
let current = null;
const used = new Set();
document.querySelectorAll('main h2, main h3').forEach((h) => {
  let id = slug(h.textContent);
  while (used.has(id)) id += '-x';
  used.add(id);
  h.id = id;
  const li = document.createElement('li');
  const a = document.createElement('a');
  a.href = '#' + id;
  a.textContent = h.textContent;
  li.appendChild(a);
  if (h.tagName === 'H2') {
    root.appendChild(li);
    current = li;
  } else {
    if (!current) { root.appendChild(li); return; }
    let sub = current.querySelector('ol');
    if (!sub) { sub = document.createElement('ol'); current.appendChild(sub); }
    sub.appendChild(li);
  }
});
nav.appendChild(root);
nav.insertAdjacentHTML('afterbegin', `<h2 class="toc-title">Contents (${used.size})</h2>`);
