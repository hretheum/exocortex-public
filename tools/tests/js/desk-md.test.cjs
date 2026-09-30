// Markdown of the review desk: the vendored marked library and the tile renderer for tables,
// run with: node --test tools/tests/js/desk-md.test.cjs
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// The desk scripts are plain browser scripts; the repository's package.json makes .js files ES modules,
// so they are evaluated the way a page would load them.
const box = { self: {} };
box.window = box;
const STATIC = path.join(__dirname, "../../gate/desk_static");
vm.runInNewContext(fs.readFileSync(path.join(STATIC, "vendor/marked.umd.js"), "utf8"), box);
const marked = box.marked || box.self.marked;
vm.runInNewContext(fs.readFileSync(path.join(STATIC, "md.js"), "utf8"), box);
const toHtml = box.self.DeskMd.create(marked);
const count = (s, re) => (s.match(re) || []).length;

const WIDE = "| Role | Metric | Definition | Threshold |\n|---|---|---|---|\n" +
  "| deciding | swap_rate | share of usable claims | a drop of at least 5 points |\n" +
  "| **guard** | failed_share | share of documents | at most 5% |";

test("a wide table becomes one tile per row: the first cell as title, the others under their headings", () => {
  const out = toHtml(WIDE);
  assert.doesNotMatch(out, /<table/);
  assert.equal(count(out, /<section class="tile row" role="listitem">/g), 2);
  assert.match(out, /<div class="tiles" role="list">/);
  assert.match(out, /<p class="tile-t"><span class="sr">Role: <\/span>deciding<\/p>/, "the column heading stays for screen readers");
  assert.match(out, /<p class="tile-t"><span class="sr">Role: <\/span><strong>guard<\/strong><\/p>/);
  assert.equal(count(out, /<dt>/g), 6, "three fields per tile besides the title");
  assert.match(out, /<dt>Threshold<\/dt><dd>at most 5%<\/dd>/);
  assert.match(out, /swap_rate/);
});

test("a two column table with long cells becomes a single tile of field and content", () => {
  const out = toHtml("| Pole | Tre\u015b\u0107 |\n|---|---|\n| Miernik g\u0142\u00f3wny | definicja, baseline, liczona na pr\u00f3bie strojenia i kontrolnej |\n| **Kryteria** | np. czas \u2264 2,5 min |");
  assert.equal(count(out, /<dl class="tile">/g), 1);
  assert.equal(count(out, /<dt>/g), 2);
  assert.match(out, /<dt>Miernik g\u0142\u00f3wny<\/dt><dd>definicja, baseline/);
  assert.match(out, /<dt><strong>Kryteria<\/strong><\/dt>/);
});

test("two or three short columns stay a table", () => {
  const out = toHtml("| Version | Hash | Date |\n|---|---|---|\n| 1 | abc123 | 2026-09-30 |");
  assert.match(out, /<table>/);
  assert.match(out, /<th>Hash<\/th>/);
  assert.doesNotMatch(out, /tile/);
});

test("the choice between table, pairs and tiles", () => {
  const M = box.self.DeskMd.tableMode;
  assert.equal(M(["a", "b"], [["1", "2"]]), "table");
  assert.equal(M(["a", "b", "c"], [["1", "2", "3"]]), "table");
  assert.equal(M(["a", "b", "c", "d"], [["1", "2", "3", "4"]]), "tiles", "four columns never fit a phone");
  assert.equal(M(["a", "b"], [["1", "x".repeat(40)]]), "pairs");
  assert.equal(M(["a", "b", "c"], [["1", "2", "x".repeat(40)]]), "tiles");
  assert.equal(M(["Rola", "Metryka", "Definicja", "Pr\u00f3g", "Linia bazowa", "Jak liczona"], [["r", "m", "d", "p", "l", "j"]]), "tiles");
  assert.equal(M([], []), "table");
});

test("text around a table stays, and other Markdown still works", () => {
  const out = toHtml("# Title\n\nSome **bold** text\n\n- one\n- two\n\n" + WIDE + "\n\n`code`");
  assert.match(out, /<h1>Title<\/h1>/);
  assert.match(out, /<strong>bold<\/strong>/);
  assert.equal(count(out, /<li>/g), 2);
  assert.match(out, /<code>code<\/code>/);
  assert.equal(count(out, /<section class="tile row"/g), 2);
});

test("snake_case is not turned into emphasis, and odd input does not throw", () => {
  assert.doesNotMatch(toHtml("the swap_rate and failed_share fields"), /<em>/);
  for (const x of [null, undefined, "", "|", "| a |", "| a | b |\n|---|---|", "| a | b | c |\n|---|---|---|\n| 1 |"]) {
    assert.doesNotThrow(() => toHtml(x), String(x));
  }
});
