// Render smoke test of the review desk page script, run with: node --test tools/tests/js/desk-render.test.cjs
// A strict stand-in for the DOM: appendChild refuses anything that is not a node, like a browser does.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const STATIC = path.join(__dirname, "../../gate/desk_static");

class FakeNode {
  static byId = {};
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
  setAttribute(k, v) { this.attrs[k] = v; if (k === "id") FakeNode.byId[v] = this; }
  addEventListener(type, fn) { (this.listeners = this.listeners || {})[type] = fn; }
  fire(type) { return this.listeners && this.listeners[type] && this.listeners[type]({ key: "", target: this }); }
  set innerHTML(v) { this.html = String(v); this._text = this.html.replace(/<[^>]*>/g, ""); this.children = []; }
  set textContent(v) { this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  find(tag) {
    const out = [];
    const walk = (n) => { n.children.forEach((c) => { if (c.tagName === tag.toUpperCase()) out.push(c); walk(c); }); };
    walk(this);
    return out;
  }
}

function load(routes, startHash) {
  FakeNode.byId = {};
  const nodes = { app: new FakeNode("main"), hdr: new FakeNode("header") };
  const document = {
    createElement: (t) => new FakeNode(t),
    createTextNode: (t) => { const n = new FakeNode("#text", 3); n._text = String(t); return n; },
    getElementById: (id) => nodes[id] || FakeNode.byId[id] || null,
    querySelector: () => ({ content: "csrf" }),
    addEventListener() {},
  };
  const fetch = (p) => {
    const key = String(p).split("?")[0];
    const body = routes[key];
    return Promise.resolve({ status: body ? 200 : 404, ok: !!body, json: () => Promise.resolve(body || { error: "not found" }) });
  };
  const calls = { parse: [], sanitize: [] };
  // stand-ins for the two vendored libraries (the real ones are checked in desk-md.test.cjs)
  const marked = { parse: (t) => { calls.parse.push(t); return "<p>PARSED " + t + "</p>"; } };
  const DOMPurify = { sanitize: (h, o) => { calls.sanitize.push(o); return h.replace("<script>", ""); } };
  const listeners = {};
  // an address bar that tells the page when the part after # changes, like a browser does (also for back)
  const location = { _h: startHash || "", reload() {},
    get hash() { return this._h; },
    set hash(v) { this._h = v; queueMicrotask(() => listeners.hashchange && listeners.hashchange()); } };
  const box = { self: {}, document, fetch, marked, DOMPurify, location, addEventListener: (t, f) => { listeners[t] = f; } };
  box.window = box;
  vm.runInNewContext(fs.readFileSync(path.join(STATIC, "logic.js"), "utf8"), box);
  box.DeskLogic = box.self.DeskLogic;
  vm.runInNewContext(fs.readFileSync(path.join(STATIC, "desk.js"), "utf8"), box);
  nodes.calls = calls;
  nodes.location = location;
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

test("a card shows a paragraph through marked and DOMPurify, and never as a raw node", async () => {
  const table = "| Role | Metric |\n|---|---|\n| deciding | swap_rate |";
  const nodes = load({
    "/api/units": { units: [{ id: 1, key: "intent-vs-fact", cls: "experiment", findings: 1, counts: { open: 1, to_edit: 0 }, state: "open", age_days: 0 }] },
    "/api/units/1": { unit: { id: 1, key: "intent-vs-fact", cls: "experiment", state: "open" },
                      findings: [{ id: 7, state: "open", path: "en/experiments/intent-vs-fact/hypothesis.md", rule: "semantic", score: 0.88, literal: false }],
                      bulk: { unit: { disabled: false }, folders: {} } },
    "/api/findings/7/card": { public: table, hint: "close to a protected note",
                              neighbours: [{ score: 0.88, source: "_source/x/a.md", text: "<script>x</script> **bold**", note_path: "_source/x/a.md", folder_path: "_source/x/" }] },
  });
  await settle();
  nodes.app.find("tr").find((r) => r.className === "row").fire("click");
  await settle();
  assert.equal(nodes.calls.parse.length, 2);
  assert.equal(nodes.calls.parse[0], table);
  assert.equal(nodes.calls.sanitize.length, 2);
  for (const o of nodes.calls.sanitize) {
    assert.ok(o.FORBID_TAGS.includes("img") && o.FORBID_TAGS.includes("iframe"));
    assert.ok(o.FORBID_ATTR.includes("href") && o.FORBID_ATTR.includes("style"));
  }
  const boxes = nodes.app.find("div").filter((d) => d.className === "md");
  assert.equal(boxes.length, 2);
  assert.match(boxes[0].html, /PARSED \| Role/);
  assert.doesNotMatch(boxes[1].html, /<script>/);
});

const UNIT_ROUTES = {
  "/api/units": { units: [{ id: 1, key: "intent-vs-fact", cls: "experiment", findings: 1, counts: { open: 1, to_edit: 0 }, state: "open", age_days: 0 }] },
  "/api/units/1": { unit: { id: 1, key: "intent-vs-fact", cls: "experiment", state: "open" },
                    findings: [{ id: 7, state: "open", path: "en/experiments/intent-vs-fact/hypothesis.md", rule: "semantic", score: 0.88, literal: false }],
                    bulk: { unit: { disabled: false }, folders: {} } },
  "/api/findings/7/card": { public: "text", hint: "h", neighbours: [] },
};

test("opening a unit gives it its own address and back returns to the queue", async () => {
  const nodes = load(UNIT_ROUTES);
  await settle();
  assert.equal(nodes.location.hash, "");
  nodes.app.find("tr").find((r) => r.className === "row").fire("click");
  await settle();
  assert.equal(nodes.location.hash, "#/unit/1");
  assert.equal(nodes.app.find("div").filter((d) => d.className === "md").length, 1);
  nodes.location.hash = "#/"; // the back button
  await settle();
  assert.equal(nodes.app.find("tr").filter((r) => r.className === "row").length, 1);
});

test("an address of a unit opens that unit directly, and the screens have addresses too", async () => {
  const nodes = load(Object.assign({ "/api/rules": { standing: [], exclusions: [], hard_list: { available: true, entries: 2 } },
                                     "/api/history": { history: [] } }, UNIT_ROUTES), "#/unit/1");
  await settle();
  assert.equal(nodes.app.find("div").filter((d) => d.className === "md").length, 1);
  nodes.hdr.find("button").find((b) => b.textContent === "Rules").fire("click");
  await settle();
  assert.equal(nodes.location.hash, "#/rules");
  assert.match(nodes.app.textContent, /hard list/);
});
