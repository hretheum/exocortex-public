// The vendored Markdown library of the review desk (marked), run with: node --test tools/tests/js/desk-md.test.cjs
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// marked.umd.js is a plain browser script; the repository's package.json makes .js files ES modules,
// so it is evaluated the way a page would load it.
const box = { self: {} };
box.window = box;
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../../gate/desk_static/vendor/marked.umd.js"), "utf8"), box);
const marked = box.marked || box.self.marked;
const html = (t) => marked.parse(t, { gfm: true, async: false });

test("a table with a header row becomes a table", () => {
  const out = html("| Role | Metric |\n|---|---|\n| deciding | swap_rate |\n| **guard** | failed_share |");
  assert.match(out, /<table>/);
  assert.match(out, /<th>Role<\/th>/);
  assert.match(out, /<strong>guard<\/strong>/);
  assert.match(out, /swap_rate/);
});

test("lists, headings and code", () => {
  const out = html("# Title\n\n- one\n- two\n\n`code`");
  assert.match(out, /<h1>Title<\/h1>/);
  assert.equal((out.match(/<li>/g) || []).length, 2);
  assert.match(out, /<code>code<\/code>/);
});

test("snake_case is not turned into emphasis", () => {
  assert.doesNotMatch(html("the swap_rate and failed_share fields"), /<em>/);
});
