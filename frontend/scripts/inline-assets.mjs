import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const distDir = join(root, "..", "dist");
const indexPath = join(distDir, "index.html");

let html = await readFile(indexPath, "utf8");

html = await replaceAsync(
  html,
  /<link rel="stylesheet" crossorigin href="\/([^"]+\.css)">/g,
  async (_match, assetPath) => {
    const css = await readFile(join(distDir, assetPath), "utf8");
    return `<style>${css}</style>`;
  },
);

html = await replaceAsync(
  html,
  /<script type="module" crossorigin src="\/([^"]+\.js)"><\/script>/g,
  async (_match, assetPath) => {
    const js = await readFile(join(distDir, assetPath), "utf8");
    return `<script type="module">${js}</script>`;
  },
);

await writeFile(indexPath, html);

async function replaceAsync(value, pattern, replacer) {
  const replacements = [];
  value.replace(pattern, (...args) => {
    replacements.push(Promise.resolve(replacer(...args)));
    return "";
  });
  const resolved = await Promise.all(replacements);
  let index = 0;
  return value.replace(pattern, () => resolved[index++]);
}
