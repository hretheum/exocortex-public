// Render smoke test of the review desk page script, run with: node --test tools/tests/js/desk-render.test.cjs
// A strict stand-in for the DOM: appendChild refuses anything that is not a node, like a browser does.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const STATIC = path.join(__dirname, "../../gate/desk_static");

class FakeNode {
  constructor(tag, nodeType) {
    this.nodeType = nodeType || 1;
    this.tagName = (tag || "").toUpperCase();
    this.children = [];
    this.className = "";
    this.attrs = {};
    this._text = "";
  }
  appendChild(child) {
    if (!child || typeof child.nodeType !== "number") {
      throw new TypeError("Failed to execute 'appendChild' on 'Node': parameter 1 is not of type 'Node'.");
    }
    this.children.push(child);
    return child;
  }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener() {}
  set textContent(v) { this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  find(tag) {
    const out = [];
    const walk = (n) => { n.children.forEach((c) => { if (c.tagName === tag.toUpperCase()) out.push(c); walk(c); }); };
    walk(this);
    return out;
  }
}

function load(routes) {
  const nodes = { app: new FakeNode("main"), hdr: new FakeNode("header") };
  const document = {
    createElement: (t) => new FakeNode(t),
    createTextNode: (t) => { const n = new FakeNode("#text", 3); n._text = String(t); return n; },
    getElementById: (id) => nodes[id] || null,
    querySelector: () => ({ content: "csrf" }),
    addEventListener() {},
  };
  const fetch = (p) => {
    const key = String(p).split("?")[0];
    const body = routes[key];
    return Promise.resolve({ status: body ? 200 : 404, ok: !!body, json: () => Promise.resolve(body || { error: "not found" }) });
  };
  const box = { self: {}, document, fetch, location: { reload() {} } };
  box.window = box;
  vm.runInNewContext(fs.readFileSync(path.join(STATIC, "logic.js"), "utf8"), box);
  box.DeskLogic = box.self.DeskLogic;
  vm.runInNewContext(fs.readFileSync(path.join(STATIC, "desk.js"), "utf8"), box);
  return nodes;
}

const settle = () => new Promise((r) => setTimeout(r, 30));

test("the queue renders a row for every unit", async () => {
  const unit = (id) => ({ id, key: "graph-vs-search", cls: "experiment", findings: 3, counts: { open: 2, to_edit: 1 }, state: "open", age_days: 1 });
  const nodes = load({ "/api/units": { units: [unit(1), unit(2)] } });
  await settle();
  assert.equal(nodes.app.find("table").length, 1);
  assert.equal(nodes.app.find("tr").filter((r) => r.className === "row").length, 2);
  assert.match(nodes.app.textContent, /graph-vs-search/);
  assert.equal(nodes.hdr.find("button").length, 3);
});

test("an empty queue says so", async () => {
  const nodes = load({ "/api/units": { units: [] } });
  await settle();
  assert.match(nodes.app.textContent, /quarantine is empty/i);
});

test("the queue does not crash when a table has no rows", async () => {
  const nodes = load({ "/api/units": { units: [{ id: 1, key: "k", cls: "docs", findings: 0, counts: { open: 0, to_edit: 0 }, state: "released", age_days: 0 }] } });
  await settle();
  assert.equal(nodes.app.find("tr").length, 2); // header row and one unit
});
