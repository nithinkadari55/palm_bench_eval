// ECharts 6 server-side rendering to an SVG string, no DOM.
// input: { option, width, height }
import * as echarts from 'echarts';

globalThis.__p5.register({
  name: 'echarts',
  run(input) {
    const chart = echarts.init(null, null, {
      renderer: 'svg',
      ssr: true,
      width: input.width || 600,
      height: input.height || 400
    });
    try {
      chart.setOption(Object.assign({ animation: false }, input.option));
      return chart.renderToSVGString();
    } finally {
      chart.dispose();
    }
  }
});
