# spike-js-dom: rquickjs <-> raikiri DOM binding

## Build
| crate | status | seconds | binary MB |
|---|---|---|---|
| spike-rkboa | OK | 122 | 58 |
| spike-rkjs | OK | 120 | 43 |

## Pass/fail per case
| group | case | rkboa | rkjs |
|---|---|---|---|
| spike | 01_templating | PASS 12/12 | PASS 12/12 |
| spike | 02_innerhtml | PASS 9/9 | PASS 9/9 |
| spike | 03_echarts_svg | FAIL 0/3 | PASS 3/3 |
| spike | 04_layout_query | PASS 4/4 | PASS 4/4 |
| spike | 05_script_error | PASS 9/9 | PASS 9/9 |
| phase5_dom | invoice | PASS 3/3 | PASS 3/3 |
| phase5_dom | kpi-cards | FAIL 0/3 | PASS 3/3 |
| phase5_dom | toc | FAIL 2/3 | PASS 3/3 |
| phase5_dom | product-grid | FAIL 0/3 | PASS 3/3 |
| phase5_dom | report-locale | PASS 3/3 | PASS 3/3 |
| phase5_dom | layout-feedback | PASS 2/2 | PASS 2/2 |

Totals: rkboa 7/11, rkjs 11/11

## Time and memory per case
| engine | case | JS ms (incl. relayout) | relayouts | relayout ms total | final render ms | final layout ms | total ms | peak RSS MB | QuickJS malloc MB |
|---|---|---|---|---|---|---|---|---|---|
| rkboa | 01_templating | 1.5 | 0 | -0.0 | 24.8 | 3.3 | 32.4 | 46.6 | - |
| rkboa | 02_innerhtml | 0.9 | 0 | -0.0 | 21.9 | 1.6 | 27.4 | 45.2 | - |
| rkboa | 03_echarts_svg | 1654.3 | 0 | -0.0 | 21.5 | 1.0 | 1680.2 | 213.8 | - |
| rkboa | 04_layout_query | 23.4 | 3 | 22.7 | 2.0 | 1.0 | 29.5 | 43.1 | - |
| rkboa | 05_script_error | 0.5 | 0 | -0.0 | 21.6 | 1.0 | 25.8 | 44.9 | - |
| rkboa | invoice | 1.4 | 0 | -0.0 | 23.2 | 2.3 | 30.0 | 45.9 | - |
| rkboa | kpi-cards | 0.7 | 0 | -0.0 | 20.5 | 0.6 | 24.4 | 44.3 | - |
| rkboa | toc | 1.0 | 0 | -0.0 | 23.5 | 2.2 | 29.3 | 45.3 | - |
| rkboa | product-grid | 0.7 | 0 | -0.0 | 19.0 | 0.6 | 23.0 | 40.9 | - |
| rkboa | report-locale | 1.2 | 0 | -0.0 | 23.4 | 2.0 | 29.4 | 45.6 | - |
| rkboa | layout-feedback | 23.9 | 3 | 23.0 | 2.6 | 1.2 | 30.4 | 45.1 | - |
| rkjs | 01_templating | 0.8 | 0 | -0.0 | 26.2 | 3.5 | 34.5 | 34.4 | 0.3 |
| rkjs | 02_innerhtml | 0.4 | 0 | -0.0 | 23.0 | 1.7 | 29.1 | 34.5 | 0.3 |
| rkjs | 03_echarts_svg | 162.2 | 0 | -0.0 | 23.7 | 1.7 | 197.8 | 51.2 | 9.7 |
| rkjs | 04_layout_query | 22.5 | 3 | 22.1 | 2.0 | 1.0 | 29.2 | 33.1 | 0.3 |
| rkjs | 05_script_error | 0.2 | 0 | -0.0 | 20.6 | 0.9 | 25.4 | 34.1 | 0.3 |
| rkjs | invoice | 0.6 | 0 | -0.0 | 21.7 | 2.1 | 27.9 | 35.1 | 0.3 |
| rkjs | kpi-cards | 0.4 | 0 | -0.0 | 21.8 | 1.4 | 27.1 | 34.7 | 0.3 |
| rkjs | toc | 0.4 | 0 | -0.0 | 21.9 | 2.1 | 27.6 | 34.7 | 0.3 |
| rkjs | product-grid | 0.4 | 0 | -0.0 | 22.3 | 1.6 | 27.8 | 34.7 | 0.3 |
| rkjs | report-locale | 0.6 | 0 | -0.0 | 22.0 | 1.8 | 28.2 | 34.8 | 0.3 |
| rkjs | layout-feedback | 23.0 | 3 | 22.6 | 2.4 | 1.2 | 29.9 | 34.6 | 0.3 |

## Failed checks
- rkboa 03_echarts_svg: FAIL regex /chart source:\s*(bundle|fallback)/ -- 
- rkboa 03_echarts_svg: info regex /chart source:\s*bundle/ -- 
- rkboa 03_echarts_svg: FAIL regex /svg paths\s*=\s*[1-9]/ -- 
- rkboa 03_echarts_svg: FAIL series bars (#d62728) painted -- 0 px (min 3000)
- rkboa 03_echarts_svg: info text 'Revenue by quarter' -- 
- rkboa kpi-cards: FAIL text 'Revenue' -- 
- rkboa kpi-cards: FAIL text '$1,284,000' -- 
- rkboa kpi-cards: FAIL text '12.4%' -- 
- rkboa kpi-cards: info no uncaught script errors -- TypeError: cannot convert 'null' or 'undefined' to object (unknown at :14:3)
- rkboa toc: FAIL text 'Contents (7)' -- 
- rkboa toc: info no uncaught script errors -- TypeError: not a callable function (unknown at :29:23)
- rkboa product-grid: FAIL text '4 of 5 products' -- 
- rkboa product-grid: FAIL text '$4.50' -- 
- rkboa product-grid: FAIL text 'Plant Pot' -- 
- rkboa product-grid: info no uncaught script errors -- TypeError: cannot convert 'null' or 'undefined' to object (unknown at :15:11)
- rkboa report-locale: info no uncaught script errors -- ReferenceError: Intl is not defined (unknown at :24:65)
- rkjs report-locale: info no uncaught script errors -- inline-script-0: ReferenceError: Intl is not defined [at <eval> (inline-script-0:24:60)]

## Prototype binding size (lines / code lines)
| part | lines | code lines |
|---|---|---|
| rquickjs natives (spike-rkjs/src/dom.rs) | 598 | 543 |
| JS DOM facade (spike-rkjs/src/prelude.js) | 788 | 748 |
| script runner + event loop host (spike-rkjs/src/main.rs) | 376 | 347 |
| relayout + PDF pipeline, shared (spike-common/pipeline.rs) | 532 | 450 |
| Boa DocumentHost driver (spike-rkboa/src/main.rs) | 270 | 242 |

## DOM API usage in LLM-written HTML (document frequency)
WebSight sample: 4600 docs, 18 with inline JS. Phase 5 DOM cases: 6 scripts.

| API | phase 5 cases | WebSight | spike prelude | raikiri-js |
|---|---|---|---|---|
| document.getElementById | 3 | 2 | yes | yes |
| querySelector | 5 | 0 | yes | yes |
| querySelectorAll | 4 | 0 | yes | yes |
| createElement | 4 | 0 | yes | yes |
| appendChild | 4 | 0 | yes | yes |
| append/prepend (ParentNode) | 1 | 0 | yes | yes |
| cloneNode | 1 | 0 | yes | yes |
| innerHTML | 2 | 0 | yes | yes |
| insertAdjacentHTML | 1 | 0 | yes | no |
| textContent | 6 | 0 | yes | yes |
| setAttribute/getAttribute | 5 | 0 | yes | yes |
| dataset | 1 | 0 | yes | no |
| classList | 4 | 1 | yes | yes |
| className | 2 | 0 | yes | yes |
| element.style.x / setProperty | 2 | 0 | yes | yes |
| element.id / value / checked | 0 | 1 | no | no |
| addEventListener | 0 | 2 | yes | yes |
| event handlers (click/submit/input) | 0 | 2 | no | no |
| getBoundingClientRect | 1 | 0 | yes | yes |
| offset*/client*/scroll* metrics | 1 | 0 | yes | yes |
| toLocaleString/Intl | 1 | 0 | no | no |
| Date | 1 | 0 | yes | yes |
| JSON.parse/stringify | 1 | 0 | yes | yes |
| alert/confirm/prompt | 0 | 1 | no | no |
| location/history | 0 | 9 | no | yes |

