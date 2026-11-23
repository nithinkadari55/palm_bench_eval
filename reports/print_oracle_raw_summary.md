# Print oracle: engines vs Chrome print output

Oracle: `Google Chrome 157.0.8103.78` · flags `--headless=new --disable-gpu --no-sandbox --no-pdf-header-footer --virtual-time-budget=5000 --host-resolver-rules=MAP * ~NOTFOUND --no-first-run --no-default-browser-check --disable-extensions` · 456/456 docs rendered · probe true backgrounds, page [594.96, 841.92] pt
Corpus: 456 docs · by source {"generated": 300, "weasyprint": 5, "pagedjs": 43, "vivliostyle": 8, "websight-v0.1": 100} · injected default `@page{size:A4;margin:15mm}`

## Leaderboard (all docs with an oracle; failures score 0)

| # | engine | score | ok | pages exact | mean abs Δpages | page-agree (matched) | page-agree (strict) | recall | precision | seq recall | dx med/p90 | dy med/p90 | within 2px | SSIM mean | SSIM p1 | t p50/p95 s | RSS p95 MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **takumi** | 0.940 | 456/456 | 89.7% | 0.12 | 95.7% | 92.8% | 96.8% | 98.7% | 93.3% | 0.5/0.7 | 0.5/0.8 | 67.5% | 0.878 | 0.900 | 0.14/0.25 | 184 |
| 2 | **rkhead** | 0.929 | 456/456 | 90.3% | 0.14 | 94.9% | 92.2% | 96.6% | 96.8% | 93.0% | 0.4/0.8 | 0.7/1.5 | 64.9% | 0.860 | 0.885 | 0.06/0.32 | 68 |
| 3 | **fulraikiri** | 0.920 | 456/456 | 89.2% | 0.19 | 93.8% | 91.1% | 96.6% | 96.8% | 92.6% | 0.5/0.9 | 0.9/7.9 | 58.4% | 0.835 | 0.878 | 0.06/0.32 | 74 |
| 4 | **fulgur** | 0.873 | 456/456 | 79.6% | 0.32 | 87.9% | 83.7% | 94.5% | 96.0% | 88.9% | 0.6/8.6 | 3.7/28.0 | 37.7% | 0.749 | 0.819 | 0.05/0.60 | 58 |
| 5 | **ironpress** | 0.846 | 456/456 | 75.0% | 0.56 | 84.3% | 81.2% | 95.5% | 93.8% | 89.7% | 6.5/20.2 | 20.0/62.0 | 15.6% | 0.676 | 0.732 | 0.23/2.80 | 97 |

## Score by category

| category | n | takumi | rkhead | fulraikiri | fulgur | ironpress |
|---|---|---|---|---|---|---|
| brochure | 10 | 0.988 | 0.907 | 0.873 | 0.874 | 0.744 |
| certificate | 12 | 0.959 | 0.994 | 0.994 | 0.946 | 0.945 |
| contract | 16 | 0.969 | 0.960 | 0.954 | 0.882 | 0.845 |
| dashboard | 14 | 0.845 | 0.967 | 0.924 | 0.739 | 0.811 |
| datatable | 20 | 0.977 | 0.860 | 0.855 | 0.839 | 0.797 |
| i18n | 28 | 0.933 | 0.870 | 0.867 | 0.838 | 0.833 |
| invoice | 26 | 0.994 | 0.982 | 0.980 | 0.948 | 0.878 |
| letter | 16 | 0.995 | 0.992 | 0.989 | 0.967 | 0.934 |
| longform | 10 | 0.987 | 0.979 | 0.943 | 0.607 | 0.732 |
| menu | 10 | 0.933 | 0.939 | 0.934 | 0.820 | 0.857 |
| minutes | 10 | 0.986 | 0.972 | 0.972 | 0.932 | 0.918 |
| newsletter | 12 | 0.764 | 0.814 | 0.823 | 0.724 | 0.711 |
| paper | 16 | 0.779 | 0.740 | 0.764 | 0.668 | 0.681 |
| public-pagedjs | 43 | 0.883 | 0.864 | 0.834 | 0.805 | 0.806 |
| public-vivliostyle | 8 | 0.822 | 0.617 | 0.609 | 0.570 | 0.545 |
| public-weasyprint | 5 | 0.848 | 0.854 | 0.804 | 0.757 | 0.827 |
| quote | 12 | 0.996 | 0.989 | 0.984 | 0.945 | 0.865 |
| receipt | 14 | 0.978 | 0.978 | 0.978 | 0.973 | 0.791 |
| report | 26 | 0.929 | 0.967 | 0.933 | 0.881 | 0.777 |
| resume | 18 | 0.997 | 0.986 | 0.984 | 0.940 | 0.905 |
| specsheet | 10 | 0.973 | 0.957 | 0.957 | 0.946 | 0.850 |
| ticket | 12 | 0.985 | 0.995 | 0.995 | 0.987 | 0.940 |
| timetable | 8 | 0.997 | 0.992 | 0.966 | 0.937 | 0.946 |
| websight | 100 | 0.960 | 0.960 | 0.959 | 0.937 | 0.919 |

## Page count exact by category

| category | n | takumi | rkhead | fulraikiri | fulgur | ironpress |
|---|---|---|---|---|---|---|
| brochure | 10 | 100.0% | 90.0% | 80.0% | 70.0% | 40.0% |
| certificate | 12 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| contract | 16 | 100.0% | 100.0% | 100.0% | 93.8% | 68.8% |
| dashboard | 14 | 100.0% | 100.0% | 100.0% | 78.6% | 92.9% |
| datatable | 20 | 95.0% | 55.0% | 60.0% | 70.0% | 60.0% |
| i18n | 28 | 100.0% | 100.0% | 100.0% | 89.3% | 100.0% |
| invoice | 26 | 100.0% | 96.2% | 96.2% | 88.5% | 73.1% |
| letter | 16 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| longform | 10 | 100.0% | 100.0% | 100.0% | 10.0% | 30.0% |
| menu | 10 | 90.0% | 100.0% | 100.0% | 70.0% | 100.0% |
| minutes | 10 | 100.0% | 100.0% | 100.0% | 80.0% | 100.0% |
| newsletter | 12 | 50.0% | 66.7% | 83.3% | 58.3% | 41.7% |
| paper | 16 | 31.2% | 87.5% | 62.5% | 62.5% | 43.8% |
| public-pagedjs | 43 | 65.1% | 62.8% | 58.1% | 60.5% | 62.8% |
| public-vivliostyle | 8 | 75.0% | 50.0% | 62.5% | 12.5% | 12.5% |
| public-weasyprint | 5 | 60.0% | 60.0% | 60.0% | 60.0% | 80.0% |
| quote | 12 | 100.0% | 100.0% | 100.0% | 91.7% | 66.7% |
| receipt | 14 | 100.0% | 100.0% | 100.0% | 100.0% | 35.7% |
| report | 26 | 84.6% | 88.5% | 80.8% | 65.4% | 46.2% |
| resume | 18 | 100.0% | 100.0% | 100.0% | 72.2% | 88.9% |
| specsheet | 10 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| ticket | 12 | 100.0% | 100.0% | 100.0% | 100.0% | 91.7% |
| timetable | 8 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| websight | 100 | 95.0% | 98.0% | 98.0% | 92.0% | 90.0% |

## Page-break agreement (strict) by category

| category | n | takumi | rkhead | fulraikiri | fulgur | ironpress |
|---|---|---|---|---|---|---|
| brochure | 10 | 99.8% | 87.2% | 77.7% | 78.8% | 70.2% |
| certificate | 12 | 94.2% | 100.0% | 100.0% | 93.9% | 100.0% |
| contract | 16 | 97.9% | 98.1% | 98.0% | 92.3% | 87.3% |
| dashboard | 14 | 70.5% | 92.9% | 81.4% | 59.9% | 85.4% |
| datatable | 20 | 98.4% | 82.2% | 84.7% | 84.6% | 73.9% |
| i18n | 28 | 93.0% | 89.5% | 89.4% | 86.2% | 88.3% |
| invoice | 26 | 99.7% | 99.7% | 99.6% | 98.6% | 89.0% |
| letter | 16 | 99.8% | 100.0% | 99.8% | 96.6% | 94.7% |
| longform | 10 | 99.2% | 99.7% | 98.9% | 3.5% | 42.8% |
| menu | 10 | 92.2% | 93.6% | 93.5% | 79.4% | 84.1% |
| minutes | 10 | 100.0% | 100.0% | 100.0% | 97.7% | 95.0% |
| newsletter | 12 | 60.3% | 76.5% | 78.0% | 57.9% | 62.1% |
| paper | 16 | 77.2% | 72.9% | 78.4% | 58.0% | 67.5% |
| public-pagedjs | 43 | 87.6% | 84.0% | 78.5% | 67.7% | 68.7% |
| public-vivliostyle | 8 | 83.8% | 42.5% | 40.4% | 36.5% | 28.1% |
| public-weasyprint | 5 | 75.0% | 71.7% | 60.2% | 58.9% | 74.7% |
| quote | 12 | 99.7% | 100.0% | 99.9% | 97.6% | 81.3% |
| receipt | 14 | 99.0% | 100.0% | 100.0% | 98.8% | 79.4% |
| report | 26 | 87.3% | 98.1% | 96.1% | 89.5% | 57.3% |
| resume | 18 | 100.0% | 99.2% | 99.0% | 97.5% | 95.8% |
| specsheet | 10 | 96.1% | 97.4% | 97.4% | 95.5% | 78.3% |
| ticket | 12 | 98.9% | 100.0% | 100.0% | 98.9% | 98.7% |
| timetable | 8 | 100.0% | 100.0% | 100.0% | 99.6% | 100.0% |
| websight | 100 | 96.0% | 95.0% | 95.0% | 92.0% | 90.9% |

## SSIM mean by category

| category | n | takumi | rkhead | fulraikiri | fulgur | ironpress |
|---|---|---|---|---|---|---|
| brochure | 10 | 0.957 | 0.817 | 0.761 | 0.772 | 0.551 |
| certificate | 12 | 0.951 | 0.974 | 0.974 | 0.910 | 0.779 |
| contract | 16 | 0.895 | 0.860 | 0.837 | 0.638 | 0.559 |
| dashboard | 14 | 0.969 | 0.941 | 0.900 | 0.713 | 0.738 |
| datatable | 20 | 0.946 | 0.749 | 0.703 | 0.630 | 0.650 |
| i18n | 28 | 0.953 | 0.900 | 0.889 | 0.803 | 0.754 |
| invoice | 26 | 0.980 | 0.930 | 0.925 | 0.820 | 0.655 |
| letter | 16 | 0.984 | 0.969 | 0.957 | 0.917 | 0.793 |
| longform | 10 | 0.963 | 0.921 | 0.786 | 0.429 | 0.511 |
| menu | 10 | 0.835 | 0.861 | 0.846 | 0.683 | 0.695 |
| minutes | 10 | 0.945 | 0.889 | 0.889 | 0.786 | 0.746 |
| newsletter | 12 | 0.631 | 0.650 | 0.668 | 0.620 | 0.496 |
| paper | 16 | 0.444 | 0.519 | 0.462 | 0.451 | 0.359 |
| public-pagedjs | 43 | 0.663 | 0.637 | 0.597 | 0.586 | 0.573 |
| public-vivliostyle | 8 | 0.567 | 0.492 | 0.481 | 0.251 | 0.245 |
| public-weasyprint | 5 | 0.670 | 0.732 | 0.703 | 0.621 | 0.693 |
| quote | 12 | 0.989 | 0.957 | 0.939 | 0.831 | 0.658 |
| receipt | 14 | 0.931 | 0.910 | 0.910 | 0.917 | 0.514 |
| report | 26 | 0.884 | 0.891 | 0.781 | 0.680 | 0.617 |
| resume | 18 | 0.989 | 0.952 | 0.949 | 0.803 | 0.667 |
| specsheet | 10 | 0.970 | 0.891 | 0.891 | 0.878 | 0.699 |
| ticket | 12 | 0.964 | 0.980 | 0.980 | 0.972 | 0.857 |
| timetable | 8 | 0.988 | 0.969 | 0.865 | 0.760 | 0.785 |
| websight | 100 | 0.915 | 0.946 | 0.944 | 0.863 | 0.826 |

## Status counts

| engine | status | skipped (no oracle) | blank p1 | wall s |
|---|---|---|---|---|
| takumi | {"OK": 456} | 0 | 1 | 140.4 |
| rkhead | {"OK": 456} | 0 | 0 | 135.7 |
| fulraikiri | {"OK": 456} | 0 | 0 | 145.9 |
| fulgur | {"OK": 456} | 0 | 1 | 137.5 |
| ironpress | {"OK": 456} | 0 | 1 | 233.4 |

## 10 worst docs per engine (first-page PNGs in the `print-oracle-<engine>` artifact, worst/)

**takumi**: `ws_0020937` (0.54, 1/2p), `gen_newsletter_006` (0.55, 5/6p), `gen_newsletter_003` (0.58, 5/3p), `gen_newsletter_001` (0.58, 5/3p), `gen_newsletter_011` (0.60, 4/3p), `pub_pagedjs_bleed` (0.60, 9/7p), `gen_report_015` (0.61, 11/12p), `gen_newsletter_002` (0.62, 4/3p), `gen_report_022` (0.62, 5/7p), `pub_weasyprint_poster` (0.62, 5/3p)

**rkhead**: `gen_i18n_011` (0.25, 1/1p), `ws_0048853` (0.25, 1/1p), `pub_vivliostyle_shirouma_index` (0.25, 10/10p), `pub_vivliostyle_gon_index` (0.32, 15/14p), `gen_i18n_004` (0.35, 3/3p), `pub_vivliostyle_fixed_page_size_ja_horizontal_Takasebune_main` (0.41, 25/12p), `gen_newsletter_006` (0.49, 4/6p), `gen_i18n_018` (0.53, 1/1p), `gen_paper_008` (0.54, 5/4p), `ws_0020937` (0.55, 1/2p)

**fulraikiri**: `gen_i18n_011` (0.25, 1/1p), `ws_0048853` (0.25, 1/1p), `pub_vivliostyle_shirouma_index` (0.25, 10/10p), `pub_vivliostyle_gon_index` (0.34, 14/14p), `gen_i18n_004` (0.35, 3/3p), `pub_vivliostyle_fixed_page_size_ja_horizontal_Takasebune_main` (0.41, 25/12p), `gen_newsletter_006` (0.49, 4/6p), `pub_weasyprint_report` (0.50, 12/7p), `pub_pagedjs_breaks_break_before_right` (0.51, 25/31p), `gen_i18n_018` (0.53, 1/1p)

**fulgur**: `gen_i18n_004` (0.26, 2/3p), `pub_vivliostyle_gon_index` (0.29, 4/14p), `gen_i18n_011` (0.40, 1/1p), `gen_menu_009` (0.41, 3/2p), `gen_newsletter_008` (0.42, 3/2p), `pub_vivliostyle_fixed_page_size_ja_horizontal_Takasebune_main` (0.42, 6/12p), `gen_paper_003` (0.44, 5/4p), `pub_weasyprint_report` (0.46, 9/7p), `gen_paper_014` (0.49, 7/6p), `gen_paper_002` (0.51, 5/4p)

**ironpress**: `gen_datatable_002` (0.14, 2/20p), `gen_newsletter_006` (0.25, 2/6p), `gen_paper_003` (0.31, 1/4p), `gen_i18n_011` (0.31, 1/1p), `gen_newsletter_009` (0.34, 2/4p), `gen_paper_002` (0.35, 1/4p), `gen_i18n_004` (0.35, 3/3p), `pub_vivliostyle_gon_index` (0.36, 6/14p), `gen_datatable_007` (0.36, 2/30p), `gen_paper_008` (0.38, 1/4p)

## Metric definitions

- Words: pdfminer layout (LAParams all_texts) reading order; NFKC+casefold; split at spaces/punctuation; CJK/Thai = one token per char; Arabic/Hebrew/Indic tokens canonicalised by sorting their code points (robust to visual-order / reordered-matra extraction).
- Alignment: difflib SequenceMatcher on Chrome vs engine word sequences, plus multiset matching inside each replace gap (local re-ordering).
- recall = matched/Chrome words · precision = matched/engine words (duplicates and junk lower it) · seq recall = in-order (LCS) matches/Chrome words.
- page-agree (matched) = matched words on the same page index / matched · page-agree (strict) = same-page matches / Chrome words.
- dx/dy: |Δ| of word top-left (CSS px) for same-page matches; per-doc median and p90, then median across docs. within 2px = share with |dx|≤2 and |dy|≤2.
- SSIM: per page, 96 dpi pdftoppm, engine page padded/cropped to the Chrome page raster, grayscale, downscaled to 320 px width; missing/extra pages count 0. SSIM mean = mean over max(pages). SSIM p1 = first page.
- score (per doc) = mean(page-agree strict, recall, precision, SSIM mean); failed docs 0; leaderboard score = mean over all docs with an oracle.
