// Chart option for case 03 (shared by the page and scripts/gen_echarts_fallback.mjs).
globalThis.__CHART_OPTION = {
  animation: false,
  title: { text: 'Revenue by quarter' },
  color: ['#d62728'],
  xAxis: { type: 'category', data: ['Q1', 'Q2', 'Q3', 'Q4'] },
  yAxis: { type: 'value' },
  series: [{ type: 'bar', data: [120, 200, 150, 80], label: { show: true, position: 'top' } }]
};
