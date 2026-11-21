// 10 D3 visualizations (see src/lib_d3.js). Data from fixed formulas.
const letters = 'ABCDEFGHIJKL'.split('');
const hierarchy = { name: 'flare', children: [
  { name: 'analytics', children: [{ name: 'cluster', children: [{ name: 'Agglomerative', value: 3938 }, { name: 'Community', value: 3812 }, { name: 'Hierarchical', value: 6714 }] }, { name: 'graph', children: [{ name: 'BetweennessCentrality', value: 3534 }, { name: 'LinkDistance', value: 5731 }, { name: 'ShortestPaths', value: 5914 }] }] },
  { name: 'animate', children: [{ name: 'Easing', value: 17010 }, { name: 'FunctionSequence', value: 5842 }, { name: 'Tween', value: 6006 }] },
  { name: 'data', children: [{ name: 'DataField', value: 1759 }, { name: 'DataSchema', value: 2165 }, { name: 'DataSet', value: 586 }, { name: 'DataSource', value: 3331 }] },
  { name: 'display', children: [{ name: 'DirtySprite', value: 8833 }, { name: 'LineSprite', value: 1732 }, { name: 'RectSprite', value: 3623 }] }
] };

export default [
  { id: 'bar', input: { viz: 'bar', data: letters.map((name, i) => ({ name, value: Math.round(1000 * (0.02 + 0.1 * Math.abs(Math.sin(i * 1.3)))) / 1000 })) } },
  { id: 'line-time', input: { viz: 'line', data: Array.from({ length: 40 }, (_, i) => ({ date: `2026-${String(1 + Math.floor(i / 28)).padStart(2, '0')}-${String(1 + (i % 28)).padStart(2, '0')}`, value: 1000 + Math.round(400 * Math.sin(i / 5) + 15 * i) })) } },
  { id: 'stacked-area', input: { viz: 'stackedArea', keys: ['apples', 'bananas', 'cherries'], data: Array.from({ length: 24 }, (_, t) => ({ t, apples: 10 + (t % 5) * 3, bananas: 20 + Math.round(10 * Math.cos(t / 4)), cherries: 5 + t })) } },
  { id: 'donut', input: { viz: 'donut', width: 400, height: 400, data: ['<5', '5-9', '10-14', '15-19', '20-24', '25-29', '30+'].map((name, i) => ({ name, value: 1000 + i * 250 + (i % 3) * 300 })) } },
  { id: 'scatter-log-symbols', input: { viz: 'scatterLog', data: Array.from({ length: 50 }, (_, i) => ({ x: Math.round(10 ** (1 + (i % 10) / 3) * 10) / 10, y: Math.round(100 * Math.sin(i)) / 10, cat: 'c' + (i % 5) })) } },
  { id: 'treemap', input: { viz: 'treemap', width: 600, height: 360, data: hierarchy } },
  { id: 'pack', input: { viz: 'pack', width: 400, height: 400, data: hierarchy } },
  { id: 'tree', input: { viz: 'tree', width: 640, height: 420, data: hierarchy } },
  { id: 'chord', input: { viz: 'chord', width: 420, height: 420, matrix: [[11975, 5871, 8916, 2868], [1951, 10048, 2060, 6171], [8010, 16145, 8090, 8045], [1013, 990, 940, 6907]] } },
  { id: 'force', input: { viz: 'force', width: 400, height: 400, nodes: Array.from({ length: 30 }, (_, i) => ({ id: 'n' + i, group: i % 4 })), links: Array.from({ length: 40 }, (_, i) => ({ source: 'n' + (i % 30), target: 'n' + ((i * 7 + 3) % 30) })) } }
];
