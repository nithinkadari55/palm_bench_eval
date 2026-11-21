import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { getDocument, VerbosityLevel } from "pdfjs-dist/legacy/build/pdf.mjs";

const require = createRequire(import.meta.url);
const pkgDir = path.dirname(require.resolve("pdfjs-dist/package.json"));

// pdf.js requires factory URLs to end with "/"; fs.readFile accepts forward slashes on every OS.
const dir = (name) => path.join(pkgDir, name).split(path.sep).join("/") + "/";

export async function openPdf(file) {
  const data = new Uint8Array(fs.readFileSync(file));
  return getDocument({
    data,
    cMapUrl: dir("cmaps"),
    cMapPacked: true,
    standardFontDataUrl: dir("standard_fonts"),
    wasmUrl: dir("wasm"),
    iccUrl: dir("iccs"),
    useSystemFonts: false,
    disableFontFace: true,
    verbosity: VerbosityLevel.ERRORS,
  }).promise;
}

export function pdfjsVersion() {
  return JSON.parse(fs.readFileSync(path.join(pkgDir, "package.json"), "utf8")).version;
}
