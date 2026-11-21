// Invoice table: template literals, innerHTML, toFixed, classList, querySelector.
const items = [
  { sku: 'A-100', name: 'Widget', qty: 3, price: 19.99 },
  { sku: 'B-220', name: 'Gadget & Co. <Pro>', qty: 1, price: 249.5 },
  { sku: 'C-310', name: 'Cable "USB-C"', qty: 5, price: 4.25 },
  { sku: 'D-404', name: 'Adapter', qty: 0, price: 12 }
];
const fmt = (n) => '$' + n.toFixed(2);
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const tbody = document.querySelector('#items tbody');
tbody.innerHTML = items.map((it, i) => `
  <tr class="row ${i % 2 ? 'odd' : 'even'}" data-sku="${it.sku}">
    <td>${esc(it.name)}</td><td class="num">${it.qty}</td>
    <td class="num">${fmt(it.price)}</td><td class="num total">${fmt(it.qty * it.price)}</td>
  </tr>`).join('');
let subtotal = 0;
items.forEach((it) => { subtotal += it.qty * it.price; });
const tax = Math.round(subtotal * 0.0825 * 100) / 100;
document.querySelector('#subtotal').textContent = fmt(subtotal);
document.querySelector('#tax').textContent = fmt(tax);
document.querySelector('#grand').textContent = fmt(subtotal + tax);
document.querySelectorAll('tr.row').forEach((tr) => {
  if (tr.querySelector('td:nth-child(2)').textContent === '0') tr.classList.add('empty');
});
document.querySelector('.invoice').classList.toggle('paid', subtotal > 100);
document.title = `Invoice ${document.querySelector('[data-invoice]').getAttribute('data-invoice')}`;
