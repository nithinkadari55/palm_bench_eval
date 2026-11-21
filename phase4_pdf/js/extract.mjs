// Usage: node extract.mjs out.json file1.pdf [file2.pdf ...]
// Writes {"pdfjs_version": v, "files": {path: {"pages": [text, ...]} | {"error": msg}}}
import fs from "node:fs";
import { openPdf, pdfjsVersion } from "./common.mjs";

const [out, ...files] = process.argv.slice(2);
const result = { pdfjs_version: pdfjsVersion(), files: {} };
for (const file of files) {
  try {
    const doc = await openPdf(file);
    const pages = [];
    for (let i = 1; i <= doc.numPages; i++) {
      const page = await doc.getPage(i);
      const tc = await page.getTextContent();
      pages.push(tc.items.map((it) => (it.str ?? "") + (it.hasEOL ? "\n" : "")).join(""));
      page.cleanup();
    }
    result.files[file] = { pages };
    await doc.loadingTask.destroy();
  } catch (e) {
    result.files[file] = { error: String(e && e.stack ? e.stack : e) };
  }
}
fs.writeFileSync(out, JSON.stringify(result));
