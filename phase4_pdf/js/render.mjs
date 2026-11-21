// Usage: node render.mjs OUT_DIR SCALE MAX_PAGES file1.pdf [file2.pdf ...]
// Writes OUT_DIR/<index>-p<N>.png per page and OUT_DIR/status.json; the index is the position in the argument list.
import fs from "node:fs";
import path from "node:path";
import { openPdf, pdfjsVersion } from "./common.mjs";

const [outDir, scaleArg, maxArg, ...files] = process.argv.slice(2);
const scale = Number(scaleArg);
const maxPages = Number(maxArg);
fs.mkdirSync(outDir, { recursive: true });
const status = { pdfjs_version: pdfjsVersion(), files: {} };
for (const [idx, file] of files.entries()) {
  const st = { pages: [], errors: [] };
  try {
    const doc = await openPdf(file);
    const n = Math.min(doc.numPages, maxPages);
    for (let i = 1; i <= n; i++) {
      try {
        const page = await doc.getPage(i);
        const viewport = page.getViewport({ scale });
        const { canvas, context } = doc.canvasFactory.create(Math.ceil(viewport.width), Math.ceil(viewport.height));
        await page.render({ canvasContext: context, viewport, background: "rgb(255,255,255)" }).promise;
        const png = await canvas.encode("png");
        const name = path.join(outDir, `${idx}-p${i}.png`);
        fs.writeFileSync(name, png);
        st.pages.push(name);
        page.cleanup();
      } catch (e) {
        st.errors.push(`page ${i}: ${String(e && e.stack ? e.stack : e)}`);
      }
    }
    await doc.loadingTask.destroy();
  } catch (e) {
    st.errors.push(String(e && e.stack ? e.stack : e));
  }
  status.files[file] = st;
}
fs.writeFileSync(path.join(outDir, "status.json"), JSON.stringify(status));
