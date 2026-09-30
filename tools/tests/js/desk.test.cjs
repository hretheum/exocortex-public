// Keyboard and focus logic of the review desk, run with: node --test tools/tests/js/desk.test.cjs
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// logic.js is a plain browser script; the repository's package.json makes .js files ES modules,
// so it is evaluated the way a page would load it.
const box = { self: {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../../gate/desk_static/logic.js"), "utf8"), box);
const L = box.self.DeskLogic;
const plain = (x) => JSON.parse(JSON.stringify(x)); // objects made in the vm have another prototype

const key = (k, tag, extra) => Object.assign({ key: k, target: { tagName: tag || "BODY" } }, extra || {});
const f = (id, state, extra) => Object.assign({ id, state, path: "en/x/a.md", rule: "semantic", score: 0.9, literal: false }, extra || {});

test("keys map to actions", () => {
  assert.equal(L.keyAction(key("1")), "keep");
  assert.equal(L.keyAction(key("2")), "to_edit");
  assert.equal(L.keyAction(key("Backspace")), "undo");
  assert.equal(L.keyAction(key("ArrowDown")), "skip");
  assert.equal(L.keyAction(key("3")), null);
  assert.equal(L.keyAction(key("a")), null);
});

test("no action while typing in a field, with a modifier, or during a confirmation", () => {
  for (const tag of ["INPUT", "TEXTAREA", "SELECT", "input"]) assert.equal(L.keyAction(key("Backspace", tag)), null);
  assert.equal(L.keyAction(key("1", "BODY", { ctrlKey: true })), null);
  assert.equal(L.keyAction(key("2", "BODY", { metaKey: true })), null);
  assert.equal(L.keyAction(key("1"), { modal: true }), null);
  assert.equal(L.keyAction(null), null);
});

test("a literal finding cannot be kept, only edited", () => {
  const lit = f(1, "open", { literal: true });
  assert.equal(L.canAct("keep", lit).ok, false);
  assert.match(L.canAct("keep", lit).reason, /literal/i);
  assert.equal(L.canAct("to_edit", lit).ok, true);
  assert.equal(L.canAct("keep", f(2, "open")).ok, true);
  assert.equal(L.canAct("keep", f(3, "outdated")).ok, false);
  assert.equal(L.canAct("keep", undefined).ok, false);
});

test("after a decision the desk moves to the next open finding", () => {
  const list = [f(1, "kept"), f(2, "open"), f(3, "open")];
  assert.equal(L.nextFocus(list, [], 1).id, 2);
  const list2 = [f(1, "kept"), f(2, "to_edit"), f(3, "open")];
  assert.equal(L.nextFocus(list2, [], 2).id, 3);
  assert.equal(L.nextFocus([f(1, "kept"), f(2, "kept")], [], 2).id, null);
  assert.equal(L.nextFocus([f(1, "open"), f(2, "kept")], [], 2).id, 1); // wraps to an earlier open one
});

test("skip leaves the finding open, moves on and comes back at the end", () => {
  const list = [f(1, "open"), f(2, "open"), f(3, "open")];
  let s = L.skip(list, [], 1);
  assert.deepEqual(plain(s), { id: 2, skipped: [1] });
  s = L.skip(list, s.skipped, 2);
  assert.deepEqual(plain(s), { id: 3, skipped: [1, 2] });
  s = L.skip(list, s.skipped, 3); // only skipped ones are left: they return
  assert.deepEqual(plain(s), { id: 1, skipped: [] });
  assert.equal(list.every((x) => x.state === "open"), true);
});

test("skipped findings are passed over after a decision", () => {
  const list = [f(1, "open"), f(2, "kept"), f(3, "open")];
  assert.equal(L.nextFocus(list, [1], 2).id, 3);
});

test("undo puts the reverted finding back in play", () => {
  const before = [f(1, "kept"), f(2, "open")];
  const after = [f(1, "open"), f(2, "open")];
  assert.equal(L.nextFocus(before, [], 1).id, 2);
  assert.equal(L.nextFocus(after, [], null).id, 1);
});

test("progress text shows decided of total and how many are to edit", () => {
  const list = [];
  for (let i = 1; i <= 60; i++) list.push(f(i, i <= 14 ? (i % 5 === 0 ? "to_edit" : "kept") : "open"));
  list.push(f(99, "outdated"));
  const p = L.progress(list);
  assert.equal(p.done, 14);
  assert.equal(p.total, 60);
  assert.equal(p.toEdit, 2);
  assert.equal(p.text, "14 of 60, 2 to edit");
});

test("collapsed line is one line without any paragraph text", () => {
  const line = L.collapsedLine(f(1, "to_edit", { path: "en/x/a.md", rule: "semantic", score: 0.91234 }));
  assert.equal(line, "to edit · en/x/a.md · semantic · 0.912");
  assert.equal(line.includes("\n"), false);
});

test("bulk buttons are disabled with the reason from the server", () => {
  const off = L.bulkButton("folder", { disabled: true, reason: "1 literal finding(s) in scope" });
  assert.deepEqual(plain(off), { label: "Keep the whole folder", disabled: true, reason: "1 literal finding(s) in scope" });
  const on = L.bulkButton("unit", { disabled: false, reason: null });
  assert.equal(on.disabled, false);
  assert.equal(on.label, "Keep the whole experiment");
  assert.equal(L.bulkButton("unit", null).disabled, true);
  assert.equal(L.bulkSummary({ files: 3, paragraphs: 7, max_score: 0.9312 }), "3 file(s), 7 paragraph(s), highest similarity 0.931");
});

test("folder of a path", () => {
  assert.equal(L.folderOf("en/experiments/x/a.md"), "en/experiments/x/");
  assert.equal(L.folderOf("a.md"), "");
});

test("a menu counter is hidden at zero and short above 999", () => {
  assert.equal(L.badge(0), null);
  assert.equal(L.badge(undefined), null);
  assert.equal(L.badge(-2), null);
  assert.equal(L.badge(7), "7");
  assert.equal(L.badge(1200), "999+");
});

test("a draft waits for the owner until it is approved; live and broken pairs never wait", () => {
  const drafts = [
    { slug: "a", state: "draft", approval: "none" },
    { slug: "b", state: "draft", approval: "changed" },
    { slug: "c", state: "draft", approval: "waiting" },
    { slug: "d", state: "live", approval: "none" },
    { slug: "e", state: "broken", approval: "none" },
  ];
  assert.deepEqual(plain(L.waitingDrafts(drafts)).map((d) => d.slug), ["a", "b"]);
  assert.deepEqual(plain(L.waitingDrafts(undefined)), []);
});
