// Compiles static_src/input.css -> static/css/app.css with Tailwind CSS v4.
//
// Uses only the `tailwindcss` package (its public `compile()` API). Class-name
// candidates are collected by scanning the Django templates, the JavaScript
// file and the form widgets, so no extra native binaries are required.
//
//   npm install
//   npm run build:css          # one-off build
//   npm run watch:css          # rebuild when a source file changes
import { compile } from "tailwindcss";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, readdirSync, statSync, mkdirSync, watch } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(join(root, "package.json"));
const INPUT = join(root, "static_src", "input.css");
const OUTPUT = join(root, "static", "css", "app.css");
const SCAN_DIRS = ["templates", "static/js"];
const SCAN_FILES = ["accounts/forms.py", "courses/forms.py", "materials/forms.py", "assignments/forms.py"];
const SCAN_EXT = new Set([".html", ".js", ".py"]);

function walk(dir, files = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, files);
    else if (SCAN_EXT.has(path.slice(path.lastIndexOf(".")))) files.push(path);
  }
  return files;
}

function collectCandidates() {
  const files = SCAN_DIRS.flatMap((d) => walk(join(root, d))).concat(SCAN_FILES.map((f) => join(root, f)));
  const candidates = new Set();
  for (const file of files) {
    const text = readFileSync(file, "utf8");
    // Split on whitespace and on characters that cannot be part of a class name.
    for (const token of text.split(/[\s"'`<>=,;{}]+/)) {
      if (token && token.length < 200) candidates.add(token);
    }
  }
  return [...candidates];
}

async function loadStylesheet(id, base) {
  let path;
  if (id === "tailwindcss") path = require.resolve("tailwindcss/index.css");
  else if (id.startsWith("tailwindcss/")) path = require.resolve(id.endsWith(".css") ? id : `${id}.css`);
  else path = resolve(base, id);
  return { path, base: dirname(path), content: readFileSync(path, "utf8") };
}

async function build() {
  const css = readFileSync(INPUT, "utf8");
  const compiler = await compile(css, { base: dirname(INPUT), loadStylesheet });
  const output = compiler.build(collectCandidates());
  mkdirSync(dirname(OUTPUT), { recursive: true });
  writeFileSync(OUTPUT, output);
  console.log(`Built ${OUTPUT} (${(output.length / 1024).toFixed(1)} KiB)`);
}

await build();

if (process.argv.includes("--watch")) {
  let timer;
  const rebuild = () => {
    clearTimeout(timer);
    timer = setTimeout(() => build().catch((e) => console.error(e)), 150);
  };
  for (const dir of SCAN_DIRS) watch(join(root, dir), { recursive: true }, rebuild);
  watch(INPUT, rebuild);
  console.log("Watching for changes...");
}
