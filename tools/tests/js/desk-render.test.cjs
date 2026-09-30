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
  const nodes = { app: new FakeNode("main"), hdr: new FakeNode("header"), toast: new FakeNode("div") };
  const document = {
    createElement: (t) => new FakeNode(t),
    createTextNode: (t) => { const n = new FakeNode("#text", 3); n._text = String(t); return n; },
    getElementById: (id) => nodes[id] || FakeNode.byId[id] || null,
    querySelector: () => ({ content: "csrf" }),
    addEventListener(t, f) { docListeners[t] = f; },
  };
  const docListeners = {};
  const fetch = (p, o) => {
    const key = String(p).split("?")[0];
    const raw = routes[key];
    const body = typeof raw === "function" ? raw(o || {}) : raw;
    return Promise.resolve({ status: body ? 200 : 404, ok: !!body, json: () => Promise.resolve(body || { error: "not found" }) });
  };
  const calls = { parse: [], sanitize: [] };
  // stand-ins for the two vendored libraries (the real ones are checked in desk-md.test.cjs)
  const marked = { Marked: class { parse(t) { calls.parse.push(t); return "<p>PARSED " + t + "</p>"; } } };
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
  vm.runInNewContext(fs.readFileSync(path.join(STATIC, "blind.js"), "utf8"), box);
  box.DeskBlind = box.self.DeskBlind;
  vm.runInNewContext(fs.readFileSync(path.join(STATIC, "md.js"), "utf8"), box);
  box.DeskMd = box.self.DeskMd;
  vm.runInNewContext(fs.readFileSync(path.join(STATIC, "desk.js"), "utf8"), box);
  nodes.calls = calls;
  nodes.location = location;
  // a key press on the page, outside any field
  nodes.focus = () => listeners.focus && listeners.focus();
  nodes.key = (k) => docListeners.keydown && docListeners.keydown({ key: k, target: { tagName: "BODY" }, preventDefault() {} });
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
  assert.equal(nodes.hdr.find("button").length, 5, "Queue, Ocena na ślepo, Rules, History and Publish now");
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

test("the actions of a card are shown above the paragraphs and again below them", async () => {
  const nodes = load(UNIT_ROUTES, "#/unit/1");
  await settle();
  const actions = nodes.app.find("div").filter((d) => d.className === "actions");
  assert.equal(actions.length, 2);
  const keep = nodes.app.find("button").filter((b) => b.textContent === "Keep (1)");
  assert.equal(keep.length, 2);
  const top = nodes.app.find("div").find((d) => d.className === "topbar");
  assert.ok(top, "there is a bar above the paragraphs");
  assert.ok(top.find("div").some((d) => d.className === "actions"), "the first actions are inside that bar");
  assert.equal(nodes.app.find("textarea").length, 2);
  assert.equal(nodes.app.find("textarea").filter((t) => t.attrs.id === "note").length, 1);
  assert.ok(top.find("button").some((b) => /whole experiment/.test(b.textContent)), "the whole-experiment button is in the top bar too");
});

test("the public paragraph comes first and the comparison is folded under it", async () => {
  const nodes = load(Object.assign({}, UNIT_ROUTES, {
    "/api/findings/7/card": { public: "the public text", hint: "h",
      neighbours: [{ score: 0.5, source: "_source/a.md", text: "n1", note_path: "_source/a.md", folder_path: "_source/" },
                   { score: 0.88, source: "_source/b.md", text: "n2", note_path: "_source/b.md", folder_path: "_source/" }] } }), "#/unit/1");
  await settle();
  const boxes = nodes.app.find("div").filter((d) => d.className === "md");
  assert.equal(boxes.length, 3);
  assert.match(boxes[0].html, /the public text/);
  const details = nodes.app.find("details");
  assert.equal(details.length, 1);
  assert.match(details[0].find("summary")[0].textContent, /\(2\).*0\.880/);
  assert.equal(details[0].find("div").filter((d) => d.className === "md").length, 2, "both neighbours are inside the folded part");
  assert.equal(details[0].attrs.open, undefined, "folded by default");
});


// -- the desk moves on by itself after a decision --------------------------------------------------
function twoUnits() {
  const decided = {};  // finding id -> state
  const fnd = (id, unit, path) => ({ id, state: decided[id] || "open", kept_via: decided[id] === "kept" ? "manual" : null,
                                     path, rule: "semantic", score: 0.9, literal: false, unit });
  const list = () => ([
    { id: 1, key: "graph-vs-search", cls: "experiment", counts: { open: [7, 8].filter((i) => !decided[i]).length, to_edit: 0 }, state: "open", findings: 2, age_days: 1 },
    { id: 2, key: "next-one", cls: "experiment", counts: { open: 1, to_edit: 0 }, state: "open", findings: 1, age_days: 2 },
  ]);
  const unitBody = (id, ids) => () => ({ unit: { id, key: id === 1 ? "graph-vs-search" : "next-one", cls: "experiment", state: "open" },
    findings: ids.map((i) => fnd(i, id, "en/experiments/x/f" + i + ".md")), bulk: { unit: { disabled: false }, folders: {} } });
  const routes = {
    "/api/units": () => ({ units: list() }),
    "/api/units/1": unitBody(1, [7, 8]),
    "/api/units/2": unitBody(2, [9]),
    "/api/undo": () => { const last = Object.keys(decided).pop(); if (!last) return { undone: null };
                         delete decided[last]; return { undone: { findings: [Number(last)], unit_id: Number(last) === 9 ? 2 : 1 } }; },
  };
  [7, 8, 9].forEach((i) => {
    routes["/api/findings/" + i + "/card"] = { public: "text " + i, hint: "h", neighbours: [] };
    routes["/api/findings/" + i + "/decide"] = (o) => { decided[i] = JSON.parse(o.body).decision === "keep" ? "kept" : "to_edit"; return { finding: {}, progress: {} }; };
    routes["/api/findings/" + i + "/reopen"] = () => { delete decided[i]; return { finding: {}, progress: {} }; };
  });
  return { routes, decided };
}

const button = (nodes, text) => nodes.app.find("button").find((b) => b.textContent === text);

test("keeping a finding shows a toast with Undo and moves to the next finding, not back to a list", async () => {
  const { routes } = twoUnits();
  const nodes = load(routes, "#/unit/1");
  await settle();
  assert.match(nodes.app.textContent, /text 7/);
  button(nodes, "Keep (1)").fire("click");
  await settle();
  assert.match(nodes.app.textContent, /text 8/, "the next finding is on screen");
  assert.doesNotMatch(nodes.app.textContent, /text 7/);
  assert.equal(nodes.toast.hidden, false);
  assert.match(nodes.toast.textContent, /Kept and moved to accepted: f7\.md/);
  assert.ok(nodes.toast.find("button").some((b) => b.textContent === "Undo"));
  const folded = nodes.app.find("details").filter((d) => d.className === "processed");
  assert.equal(folded.length, 1);
  assert.match(folded[0].find("summary")[0].textContent, /Processed in this unit \(1\)/);
  assert.equal(folded[0].attrs.open, undefined, "the processed part is folded");
});

test("the Undo in the toast brings the finding back", async () => {
  const { routes, decided } = twoUnits();
  const nodes = load(routes, "#/unit/1");
  await settle();
  button(nodes, "Keep (1)").fire("click");
  await settle();
  nodes.toast.find("button").find((b) => b.textContent === "Undo").fire("click");
  await settle();
  assert.deepEqual(decided, {});
  assert.match(nodes.app.textContent, /text 7/);
});

test("when a unit has nothing left the desk opens the next unit and says so", async () => {
  const { routes } = twoUnits();
  const nodes = load(routes, "#/unit/1");
  await settle();
  button(nodes, "Keep (1)").fire("click");
  await settle();
  button(nodes, "Keep (1)").fire("click");
  await settle();
  assert.equal(nodes.location.hash, "#/unit/2");
  assert.match(nodes.app.textContent, /text 9/);
  assert.match(nodes.toast.textContent, /Unit graph-vs-search is done, next: next-one/);
});

test("a processed finding can be reopened from the folded part", async () => {
  const { routes, decided } = twoUnits();
  const nodes = load(routes, "#/unit/1");
  await settle();
  button(nodes, "Keep (1)").fire("click");
  await settle();
  button(nodes, "Reopen").fire("click");
  await settle();
  assert.deepEqual(decided, {});
  assert.match(nodes.app.textContent, /text 7/, "the reopened finding is the one on screen");
});

test("the queue keeps units with nothing open in a folded Processed part", async () => {
  const unit = (id, key, open, state) => ({ id, key, cls: "experiment", findings: 2, counts: { open, to_edit: 0 }, state, age_days: 1 });
  const nodes = load({ "/api/units": { units: [unit(1, "waiting", 2, "open"), unit(2, "finished", 0, "released")] } });
  await settle();
  const folded = nodes.app.find("details").filter((d) => d.className === "processed");
  assert.equal(folded.length, 1);
  assert.match(folded[0].textContent, /finished/);
  assert.doesNotMatch(nodes.app.textContent.replace(folded[0].textContent, ""), /finished/, "not among the units to check");
  assert.match(folded[0].find("summary")[0].textContent, /Processed \(1\)/);
});


test("the sign-in page works: its script needs none of the libraries the desk page loads", async () => {
  FakeNode.byId = {};
  const form = new FakeNode("form");
  const token = new FakeNode("input"); token.value = "secret-token";
  const msg = new FakeNode("span");
  const byId = { "login-form": form, token, "login-msg": msg };
  const document = {
    createElement: (t) => new FakeNode(t),
    createTextNode: (t) => { const n = new FakeNode("#text", 3); n._text = String(t); return n; },
    getElementById: (id) => byId[id] || null,
    querySelector: () => null,
    addEventListener() {},
  };
  const sent = [];
  const fetch = (p, o) => { sent.push({ p, o }); return Promise.resolve({ ok: true }); };
  const location = { hash: "", reload() { sent.push("reload"); } };
  const box = { self: {}, document, fetch, location, addEventListener() {} };
  box.window = box;  // no DeskLogic, DeskMd, marked or DOMPurify here, as on the sign-in page
  vm.runInNewContext(fs.readFileSync(path.join(STATIC, "desk.js"), "utf8"), box);
  assert.ok(form.listeners && form.listeners.submit, "the submit handler is registered");
  form.listeners.submit({ preventDefault() {} });
  await settle();
  assert.equal(sent[0].p, "/login");
  assert.equal(JSON.parse(sent[0].o.body).token, "secret-token");
  assert.ok(sent.includes("reload"), "a successful sign-in reloads the page");
});


test("the header has a Publish now button, and the queue shows the last publish run", async () => {
  const nodes = load({ "/api/units": { units: [{ id: 1, key: "k", cls: "experiment", findings: 1, counts: { open: 1, to_edit: 0 }, state: "open", age_days: 0 }] },
                       "/api/publish": { configured: true, pending: false, last: { time: "2026-09-29T18:07:26+00:00", status: "ok", published: 5, held: 17, pushed: true } } });
  await settle();
  assert.ok(nodes.hdr.find("button").some((b) => b.textContent === "Publish now"));
  assert.match(nodes.app.textContent, /Last publish 2026-09-29 18:07 UTC: 5 published, 17 held/);
});

test("Publish now asks the server once and tells the person", async () => {
  const posted = [];
  const nodes = load({ "/api/units": { units: [] },
                       "/api/publish": (o) => { if (o.method === "POST") posted.push(o.method); return o.method === "POST" ? { requested: true, already: false } : { configured: true, pending: false, last: null }; } });
  await settle();
  nodes.hdr.find("button").find((b) => b.textContent === "Publish now").fire("click");
  await settle();
  assert.equal(posted.length, 1);
  assert.match(nodes.toast.textContent, /Publish requested/);
});

const DRAFT = { slug: "graph-vs-search", state: "draft", approval: "none", sha: { pl: "a".repeat(64), en: "b".repeat(64) },
  title: { pl: "Zastosowania biznesowe: Graf a wyszukiwanie", en: "Business applications: Graph and search" },
  text: { pl: "---\nid: x\npublish: false\n---\n\n# T\n\nJedno zdanie.", en: "---\nid: y\n---\n\n# T\n\nOne sentence." } };

test("the queue shows drafts to approve above the units, with the text of both versions", async () => {
  const nodes = load({ "/api/units": { units: [] }, "/api/drafts": { configured: true, drafts: [DRAFT] } });
  await settle();
  assert.match(nodes.app.textContent, /Szkice do zatwierdzenia \(1\)/);
  assert.match(nodes.app.textContent, /Zastosowania biznesowe: Graf a wyszukiwanie/);
  assert.equal(nodes.calls.parse.length, 2);
  assert.doesNotMatch(nodes.calls.parse[0], /publish: false/, "the header is not shown as text");
  assert.match(nodes.calls.parse[0], /Jedno zdanie/);
  assert.match(nodes.calls.parse[1], /One sentence/);
  assert.match(nodes.app.textContent, /quarantine is empty/i);
});

test("approving a draft sends the checksums that were shown and says when it goes live", async () => {
  const posted = [];
  const nodes = load({ "/api/units": { units: [] }, "/api/drafts": { configured: true, drafts: [DRAFT] },
                       "/api/drafts/graph-vs-search/approve": (o) => { posted.push(JSON.parse(o.body)); return { approved: true }; } });
  await settle();
  nodes.app.find("button").find((b) => b.textContent === "Zatwierdź").fire("click");
  await settle();
  assert.deepEqual(posted, [{ sha: DRAFT.sha }]); // origin is left out for a draft in the vault
  assert.match(nodes.toast.textContent, /Zatwierdzono: Zastosowania biznesowe.*Publish now/);
});

test("an approved draft waits for Publish now and can be withdrawn", async () => {
  const withdrawn = [];
  const waiting = { ...DRAFT, approval: "waiting" };
  const nodes = load({ "/api/units": { units: [] }, "/api/drafts": { configured: true, drafts: [waiting] },
                       "/api/drafts/graph-vs-search/withdraw": (o) => { withdrawn.push(o.method); return { withdrawn: true }; } });
  await settle();
  assert.match(nodes.app.textContent, /Szkice do zatwierdzenia \(0\)/, "an approved draft stays listed but waits for nothing");
  assert.match(nodes.app.textContent, /Zatwierdzony\. Trafi na stronę po naciśnięciu Publish now/);
  assert.ok(!nodes.app.find("button").some((b) => b.textContent === "Zatwierdź"));
  nodes.app.find("button").find((b) => b.textContent === "Wycofaj zatwierdzenie").fire("click");
  await settle();
  assert.deepEqual(withdrawn, ["POST"]);
});

test("a pair that does not match is reported, not approvable; a queue without drafts shows no box", async () => {
  const broken = { ...DRAFT, state: "broken" };
  let nodes = load({ "/api/units": { units: [] }, "/api/drafts": { configured: true, drafts: [broken] } });
  await settle();
  assert.match(nodes.app.textContent, /nie są parą/);
  assert.ok(!nodes.app.find("button").some((b) => b.textContent === "Zatwierdź"));
  nodes = load({ "/api/units": { units: [] }, "/api/drafts": { configured: true, drafts: [{ ...DRAFT, state: "live" }] } });
  await settle();
  assert.doesNotMatch(nodes.app.textContent, /Szkice do zatwierdzenia/);
});


// -- blind rating (F2.10) -------------------------------------------------------------------------
function blindRoutes(posts) {
  const items = [1, 2, 3].map((n) => ({ position: n, claim: "Claim " + n, quote: "Quote " + n, context: "Before. Quote " + n + ". After." }));
  const data = { experiment: "toy-length", sample: "blind-desk", page_sha: "a".repeat(64), items,
                 ratings: { "1": { verdicts: ["correct"], source_mode: "fact", comment: "" } }, status: "rating",
                 progress: { rated: 1, total: 3, left: 2 } };
  let rated = 1;
  return {
    "/api/units": { units: [] },
    "/api/blind": { configured: true, samples: [{ experiment: "toy-length", sample: "blind-desk", status: "rating", progress: data.progress }] },
    "/api/blind/toy-length/blind-desk": data,
    "/api/blind/toy-length/blind-desk/rate": (o) => {
      posts.push(JSON.parse(o.body)); rated = Math.min(3, rated + 1);
      return { progress: { rated, total: 3, left: 3 - rated }, status: "rating" };
    },
    "/api/blind/toy-length/blind-desk/finish": (o) => { posts.push({ finish: JSON.parse(o.body) }); return { status: "finished" }; },
  };
}

test("the blind list shows progress only and opens a sample at its first unrated item", async () => {
  const nodes = load(blindRoutes([]), "#/blind");
  await settle();
  const cells = nodes.app.find("td").map((c) => c.textContent);
  assert.deepEqual(cells, ["toy-length", "blind-desk", "1 z 3", "2", "w trakcie"], "rated and waiting are shown apart");
  nodes.app.find("tr").find((r) => r.className === "row").fire("click");
  await settle();
  assert.equal(nodes.location.hash, "#/blind/toy-length/blind-desk");
  assert.match(nodes.app.textContent, /Pozycja 2 z 3/);
  assert.match(nodes.app.textContent, /Claim 2/);
  const card = nodes.app.find("div").find((d) => d.attrs.id === "blindcard");
  assert.doesNotMatch(card.textContent, /Claim 1|Claim 3/, "one item at a time on the card");
  assert.equal(nodes.app.find("mark").length, 1, "the quote is marked in the text around it");
  assert.match(nodes.hdr.textContent, /1 z 3 ocenionych/);
});

test("keys rate an item, save it and move to the next unrated one", async () => {
  const posts = [];
  const nodes = load(blindRoutes(posts), "#/blind/toy-length/blind-desk");
  await settle();
  const save = () => nodes.app.find("button").find((b) => b.attrs.id === "blindsave");
  assert.equal(save().attrs.disabled, "", "nothing chosen yet, so nothing to save");
  nodes.key("2"); nodes.key("3"); nodes.key("6");
  const on = nodes.app.find("button").filter((b) => / on\b|^on\b/.test(b.className)).map((b) => b.textContent);
  assert.deepEqual(on, ["2 Zamiana trybu", "3 Przekręcona liczba lub nazwa", "6 plan"]);
  nodes.key("1"); // "correct" stands alone
  assert.deepEqual(nodes.app.find("button").filter((b) => /\bon\b/.test(b.className) && /^\d [A-Z]/.test(b.textContent)).map((b) => b.textContent),
                   ["1 Poprawne"]);
  nodes.key("Enter");
  await settle();
  assert.deepEqual(posts[0], { position: 2, verdicts: ["correct"], source_mode: "plan", comment: "", page_sha: "a".repeat(64) });
  assert.match(nodes.app.textContent, /Pozycja 3 z 3/);
  nodes.key("4"); nodes.key("Enter");
  await settle();
  assert.deepEqual(posts[1].verdicts, ["other_error"]);
  assert.match(nodes.app.textContent, /Wszystkie pozycje są ocenione/);
  nodes.app.find("button").find((b) => b.attrs.id === "blinddone").fire("click");
  await settle();
  assert.deepEqual(posts[2], { finish: { page_sha: "a".repeat(64) } });
  assert.match(nodes.app.textContent, /trafi do vaulta/);
});

test("going back shows the owner's own rating of that item", async () => {
  const nodes = load(blindRoutes([]), "#/blind/toy-length/blind-desk");
  await settle();
  nodes.key("ArrowLeft");
  assert.match(nodes.app.textContent, /Pozycja 1 z 3 · oceniona/);
  const on = nodes.app.find("button").filter((b) => /\bon\b/.test(b.className)).map((b) => b.textContent);
  assert.deepEqual(on, ["1 Poprawne", "5 fakt"]);
});

test("a draft from the lab is marked as such and its approval names its origin", async () => {
  const posted = [];
  const lab = { ...DRAFT, origin: "lab", replaces: "live" };
  const nodes = load({ "/api/units": { units: [] }, "/api/drafts": { configured: true, drafts: [lab] },
                       "/api/drafts/graph-vs-search/approve": (o) => { posted.push(JSON.parse(o.body)); return { approved: true }; } });
  await settle();
  assert.match(nodes.app.textContent, /Nowy szkic z laboratorium, zastąpi sekcję w vaulcie/);
  nodes.app.find("button").find((b) => b.textContent === "Zatwierdź").fire("click");
  await settle();
  assert.deepEqual(posted, [{ sha: DRAFT.sha, origin: "lab" }]);
});


// -- menu counters and the folded list of rated items ------------------------------------------------
function badgeOf(nodes, id) {
  const btn = nodes.hdr.find("button").find((b) => b.attrs.id === id);
  const b = btn && btn.badgeNode;
  return b && !b.hidden ? b.textContent : null;
}

test("the menu shows what waits, updates after an action and hides a zero", async () => {
  const posts = [];
  const routes = blindRoutes(posts);
  let waiting = { queue: 3, blind: 2 };
  routes["/api/counts"] = () => waiting;
  const rate = routes["/api/blind/toy-length/blind-desk/rate"];
  routes["/api/blind/toy-length/blind-desk/rate"] = (o) => { waiting = { queue: 0, blind: 1 }; return rate(o); };
  const nodes = load(routes, "#/blind/toy-length/blind-desk");
  await settle();
  assert.equal(badgeOf(nodes, "nav-queue"), "3");
  assert.equal(badgeOf(nodes, "nav-blind"), "2");
  nodes.key("1"); nodes.key("Enter");
  await settle();
  assert.equal(badgeOf(nodes, "nav-queue"), null, "a zero hides the counter");
  assert.equal(badgeOf(nodes, "nav-blind"), "1");
  waiting = { queue: 5, blind: 0 };
  nodes.focus();  // back to the tab
  await settle();
  assert.equal(badgeOf(nodes, "nav-queue"), "5");
  assert.equal(badgeOf(nodes, "nav-blind"), null);
});

test("rated items fold into a list and can be opened to change the rating", async () => {
  const posts = [];
  const nodes = load(blindRoutes(posts), "#/blind/toy-length/blind-desk");
  await settle();
  const box = () => nodes.app.find("details").find((d) => d.attrs.id === "blindrated");
  assert.match(box().find("summary")[0].textContent, /Ocenione \(1\)/);
  assert.equal(box().attrs.open, undefined, "folded by default");
  assert.doesNotMatch(box().textContent, /Poprawne|poprawne/, "no verdicts in the list");
  nodes.key("4"); nodes.key("Enter");
  await settle();
  assert.match(box().find("summary")[0].textContent, /Ocenione \(2\)/);
  box().find("li")[0].find("button")[0].fire("click");  // item 1, the first rated one
  await settle();
  assert.match(nodes.app.textContent, /Pozycja 1 z 3 · oceniona/);
  nodes.key("3"); nodes.key("Enter");
  await settle();
  assert.deepEqual(posts[posts.length - 1].position, 1);
  assert.deepEqual(posts[posts.length - 1].verdicts, ["number_or_name"]);
});

test("approving a draft and taking the approval back update the Queue counter", async () => {
  let draft = DRAFT;
  const routes = { "/api/units": { units: [] }, "/api/counts": () => ({ queue: draft.approval === "waiting" ? 0 : 1, blind: 0 }),
                   "/api/drafts": () => ({ configured: true, drafts: [draft] }),
                   "/api/drafts/graph-vs-search/approve": () => { draft = { ...DRAFT, approval: "waiting" }; return { approved: true }; },
                   "/api/drafts/graph-vs-search/withdraw": () => { draft = DRAFT; return { withdrawn: true }; } };
  const nodes = load(routes);
  await settle();
  assert.equal(badgeOf(nodes, "nav-queue"), "1");
  nodes.app.find("button").find((b) => b.textContent === "Zatwierdź").fire("click");
  await settle();
  assert.equal(badgeOf(nodes, "nav-queue"), null, "an approved draft waits for nothing: the counter hides");
  nodes.app.find("button").find((b) => b.textContent === "Wycofaj zatwierdzenie").fire("click");
  await settle();
  assert.equal(badgeOf(nodes, "nav-queue"), "1");
});
