// D3 v7 on linkedom: ten visualizations rendered into an SVG element, serialized.
// input: { viz, width, height, data }
import { parseHTML } from 'linkedom';
import * as d3 from 'd3';

function frame(input) {
  const { document } = parseHTML('<!doctype html><html><head></head><body><div id="chart"></div></body></html>');
  const w = input.width || 480;
  const h = input.height || 300;
  const svg = d3.select(document.querySelector('#chart')).append('svg')
    .attr('xmlns', 'http://www.w3.org/2000/svg')
    .attr('width', w).attr('height', h).attr('viewBox', `0 0 ${w} ${h}`);
  return { document, svg, w, h, m: { top: 20, right: 20, bottom: 30, left: 40 } };
}

const VIZ = {
  bar(input) {
    const { svg, w, h, m } = frame(input);
    const data = input.data;
    const x = d3.scaleBand().domain(data.map((d) => d.name)).range([m.left, w - m.right]).padding(0.1);
    const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.value)]).nice().range([h - m.bottom, m.top]);
    svg.append('g').attr('fill', 'steelblue').selectAll('rect').data(data).join('rect')
      .attr('x', (d) => x(d.name)).attr('y', (d) => y(d.value)).attr('height', (d) => y(0) - y(d.value)).attr('width', x.bandwidth());
    svg.append('g').attr('transform', `translate(0,${h - m.bottom})`).call(d3.axisBottom(x));
    svg.append('g').attr('transform', `translate(${m.left},0)`).call(d3.axisLeft(y).ticks(5, 's'));
    return svg.node().outerHTML;
  },
  line(input) {
    const { svg, w, h, m } = frame(input);
    const parse = d3.utcParse('%Y-%m-%d');
    const data = input.data.map((d) => ({ date: parse(d.date), value: d.value }));
    const x = d3.scaleUtc().domain(d3.extent(data, (d) => d.date)).range([m.left, w - m.right]);
    const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.value)]).nice().range([h - m.bottom, m.top]);
    const line = d3.line().curve(d3.curveMonotoneX).x((d) => x(d.date)).y((d) => y(d.value));
    svg.append('g').attr('transform', `translate(0,${h - m.bottom})`).call(d3.axisBottom(x).ticks(6).tickFormat(d3.utcFormat('%b %d')));
    svg.append('g').attr('transform', `translate(${m.left},0)`).call(d3.axisLeft(y).tickFormat(d3.format('$.2s')));
    svg.append('path').datum(data).attr('fill', 'none').attr('stroke', 'currentColor').attr('stroke-width', 1.5).attr('d', line);
    return svg.node().outerHTML;
  },
  stackedArea(input) {
    const { svg, w, h, m } = frame(input);
    const keys = input.keys;
    const series = d3.stack().keys(keys).offset(d3.stackOffsetNone)(input.data);
    const x = d3.scaleLinear().domain(d3.extent(input.data, (d) => d.t)).range([m.left, w - m.right]);
    const y = d3.scaleLinear().domain([0, d3.max(series, (s) => d3.max(s, (d) => d[1]))]).nice().range([h - m.bottom, m.top]);
    const color = d3.scaleOrdinal().domain(keys).range(d3.schemeTableau10);
    const area = d3.area().x((d) => x(d.data.t)).y0((d) => y(d[0])).y1((d) => y(d[1])).curve(d3.curveBasis);
    svg.append('g').selectAll('path').data(series).join('path').attr('fill', (d) => color(d.key)).attr('d', area)
      .append('title').text((d) => d.key);
    svg.append('g').attr('transform', `translate(0,${h - m.bottom})`).call(d3.axisBottom(x).ticks(8));
    svg.append('g').attr('transform', `translate(${m.left},0)`).call(d3.axisLeft(y).ticks(5, '%'));
    return svg.node().outerHTML;
  },
  donut(input) {
    const { svg, w, h } = frame(input);
    const r = Math.min(w, h) / 2 - 10;
    const pie = d3.pie().sort(null).value((d) => d.value);
    const arc = d3.arc().innerRadius(r * 0.55).outerRadius(r).cornerRadius(3).padAngle(0.01);
    const label = d3.arc().innerRadius(r * 0.8).outerRadius(r * 0.8);
    const color = d3.scaleOrdinal().domain(input.data.map((d) => d.name)).range(d3.quantize((t) => d3.interpolateSpectral(t * 0.8 + 0.1), input.data.length).reverse());
    const g = svg.append('g').attr('transform', `translate(${w / 2},${h / 2})`);
    const arcs = pie(input.data);
    g.selectAll('path').data(arcs).join('path').attr('fill', (d) => color(d.data.name)).attr('d', arc);
    g.selectAll('text').data(arcs).join('text').attr('transform', (d) => `translate(${label.centroid(d)})`)
      .attr('text-anchor', 'middle').text((d) => `${d.data.name} ${d3.format('.1%')(d.data.value / d3.sum(input.data, (x) => x.value))}`);
    return svg.node().outerHTML;
  },
  scatterLog(input) {
    const { svg, w, h, m } = frame(input);
    const x = d3.scaleLog().domain(d3.extent(input.data, (d) => d.x)).range([m.left, w - m.right]).nice();
    const y = d3.scaleLinear().domain(d3.extent(input.data, (d) => d.y)).range([h - m.bottom, m.top]).nice();
    const shape = d3.scaleOrdinal(input.data.map((d) => d.cat), d3.symbols.map((s) => d3.symbol().type(s).size(40)()));
    svg.append('g').attr('transform', `translate(0,${h - m.bottom})`).call(d3.axisBottom(x).ticks(5, '~s'));
    svg.append('g').attr('transform', `translate(${m.left},0)`).call(d3.axisLeft(y));
    svg.append('g').attr('fill', 'none').attr('stroke', 'black').selectAll('path').data(input.data).join('path')
      .attr('transform', (d) => `translate(${x(d.x)},${y(d.y)})`).attr('d', (d) => shape(d.cat));
    return svg.node().outerHTML;
  },
  treemap(input) {
    const { svg, w, h } = frame(input);
    const root = d3.treemap().tile(d3.treemapSquarify).size([w, h]).padding(1).round(true)(
      d3.hierarchy(input.data).sum((d) => d.value).sort((a, b) => b.value - a.value));
    const color = d3.scaleOrdinal(d3.schemeCategory10);
    const leaf = svg.selectAll('g').data(root.leaves()).join('g').attr('transform', (d) => `translate(${d.x0},${d.y0})`);
    leaf.append('rect').attr('fill', (d) => { let p = d; while (p.depth > 1) p = p.parent; return color(p.data.name); })
      .attr('width', (d) => d.x1 - d.x0).attr('height', (d) => d.y1 - d.y0);
    leaf.append('text').attr('x', 3).attr('y', 12).text((d) => d.data.name);
    return svg.node().outerHTML;
  },
  pack(input) {
    const { svg, w, h } = frame(input);
    const root = d3.pack().size([w - 2, h - 2]).padding(3)(d3.hierarchy(input.data).sum((d) => d.value).sort((a, b) => b.value - a.value));
    const color = d3.scaleLinear().domain([0, 5]).range(['hsl(152,80%,80%)', 'hsl(228,30%,40%)']).interpolate(d3.interpolateHcl);
    svg.append('g').selectAll('circle').data(root.descendants()).join('circle')
      .attr('cx', (d) => d.x + 1).attr('cy', (d) => d.y + 1).attr('r', (d) => d.r).attr('fill', (d) => (d.children ? color(d.depth) : 'white'));
    return svg.node().outerHTML;
  },
  tree(input) {
    const { svg, w, h } = frame(input);
    const root = d3.hierarchy(input.data);
    d3.tree().size([h - 20, w - 160])(root);
    const g = svg.append('g').attr('transform', 'translate(80,10)');
    g.append('g').attr('fill', 'none').attr('stroke', '#555').selectAll('path').data(root.links()).join('path')
      .attr('d', d3.linkHorizontal().x((d) => d.y).y((d) => d.x));
    const node = g.append('g').selectAll('g').data(root.descendants()).join('g').attr('transform', (d) => `translate(${d.y},${d.x})`);
    node.append('circle').attr('r', 2.5).attr('fill', (d) => (d.children ? '#555' : '#999'));
    node.append('text').attr('dy', '0.31em').attr('x', (d) => (d.children ? -6 : 6)).attr('text-anchor', (d) => (d.children ? 'end' : 'start')).text((d) => d.data.name);
    return svg.node().outerHTML;
  },
  chord(input) {
    const { svg, w, h } = frame(input);
    const outer = Math.min(w, h) * 0.5 - 30;
    const inner = outer - 10;
    const chords = d3.chord().padAngle(0.05).sortSubgroups(d3.descending)(input.matrix);
    const color = d3.scaleOrdinal(d3.schemeSet2);
    const g = svg.append('g').attr('transform', `translate(${w / 2},${h / 2})`);
    g.append('g').selectAll('path').data(chords.groups).join('path').attr('fill', (d) => color(d.index))
      .attr('d', d3.arc().innerRadius(inner).outerRadius(outer));
    g.append('g').attr('fill-opacity', 0.75).selectAll('path').data(chords).join('path')
      .attr('fill', (d) => color(d.source.index)).attr('d', d3.ribbon().radius(inner));
    return svg.node().outerHTML;
  },
  force(input) {
    const { svg, w, h } = frame(input);
    const nodes = input.nodes.map((d) => Object.assign({}, d));
    const links = input.links.map((d) => Object.assign({}, d));
    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((d) => d.id).distance(30))
      .force('charge', d3.forceManyBody().strength(-60))
      .force('center', d3.forceCenter(w / 2, h / 2))
      .stop();
    for (let i = 0; i < 300; i++) sim.tick();
    const r2 = (v) => Math.round(v * 100) / 100;
    svg.append('g').attr('stroke', '#999').selectAll('line').data(links).join('line')
      .attr('x1', (d) => r2(d.source.x)).attr('y1', (d) => r2(d.source.y)).attr('x2', (d) => r2(d.target.x)).attr('y2', (d) => r2(d.target.y));
    svg.append('g').selectAll('circle').data(nodes).join('circle').attr('r', 4).attr('cx', (d) => r2(d.x)).attr('cy', (d) => r2(d.y))
      .attr('fill', (d) => d3.schemeCategory10[d.group % 10]);
    return svg.node().outerHTML;
  }
};

globalThis.__p5.register({
  name: 'd3',
  run(input) {
    const f = VIZ[input.viz];
    if (!f) throw new Error('unknown viz ' + input.viz);
    return f(input);
  }
});
