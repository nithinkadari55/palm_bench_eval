// Product grid: <template> cloning, querySelector inside fragments, sort, filter, closest.
const products = [
  { name: 'Desk Lamp', price: 39, stock: 12, tags: ['home', 'light'] },
  { name: 'Notebook', price: 4.5, stock: 0, tags: ['office'] },
  { name: 'Monitor Arm', price: 89.99, stock: 3, tags: ['office', 'ergonomic'] },
  { name: 'Plant Pot', price: 15, stock: 40, tags: ['home'] },
  { name: 'Headphones', price: 129, stock: 7, tags: ['audio'] }
];
const tpl = document.getElementById('product-tpl');
const list = document.getElementById('products');
products
  .filter((p) => p.price < 100)
  .sort((a, b) => a.price - b.price)
  .forEach((p) => {
    const frag = tpl.content.cloneNode(true);
    frag.querySelector('.name').textContent = p.name;
    frag.querySelector('.price').textContent = `$${p.price.toFixed(2)}`;
    const tags = frag.querySelector('.tags');
    p.tags.forEach((t) => {
      const span = document.createElement('span');
      span.className = 'tag tag-' + t;
      span.textContent = t;
      tags.appendChild(span);
    });
    if (p.stock === 0) frag.querySelector('.card').classList.add('sold-out');
    list.appendChild(frag);
  });
list.querySelectorAll('.tag-office').forEach((t) => t.closest('.card').setAttribute('data-office', 'yes'));
document.getElementById('count').textContent = `${list.querySelectorAll('.card').length} of ${products.length} products`;
