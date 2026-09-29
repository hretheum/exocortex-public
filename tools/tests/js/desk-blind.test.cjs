// Logic of the blind rating screen (F2.10), run with: node --test tools/tests/js/desk-blind.test.cjs
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// blind.js is a plain browser script (the repository's package.json makes .js files ES modules)
const box = { self: {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../../gate/desk_static/blind.js"), "utf8"), box);
const B = box.self.DeskBlind;
const plain = (x) => JSON.parse(JSON.stringify(x)); // objects made in the vm have another prototype

test("keys choose categories, modes, save and move, but not while typing or with a modifier", () => {
  assert.deepEqual(plain(B.keyAction({ key: "1" })), { verdict: "correct" });
  assert.deepEqual(plain(B.keyAction({ key: "4" })), { verdict: "other_error" });
  assert.deepEqual(plain(B.keyAction({ key: "5" })), { mode: "fact" });
  assert.deepEqual(plain(B.keyAction({ key: "8" })), { mode: "hypothesis" });
  assert.deepEqual(plain(B.keyAction({ key: "0" })), { mode: null });
  assert.deepEqual(plain(B.keyAction({ key: "Enter" })), { save: true });
  assert.deepEqual(plain(B.keyAction({ key: "ArrowLeft" })), { move: -1 });
  assert.equal(B.keyAction({ key: "9" }), null);
  assert.equal(B.keyAction({ key: "1", target: { tagName: "input" } }), null);
  assert.equal(B.keyAction({ key: "1", ctrlKey: true }), null);
});

test("correct stands alone, errors go together, a second press takes a category back", () => {
  let sel = B.toggle([], "mode_swap");
  sel = B.toggle(sel, "other_error");
  assert.deepEqual(plain(sel), ["mode_swap", "other_error"]);
  assert.deepEqual(plain(B.toggle(sel, "correct")), ["correct"]);
  assert.deepEqual(plain(B.toggle(["correct"], "number_or_name")), ["number_or_name"]);
  assert.deepEqual(plain(B.toggle(sel, "mode_swap")), ["other_error"]);
  assert.deepEqual(plain(B.toggle(sel, "bogus")), plain(sel));
  assert.equal(B.canSave([]).ok, false);
  assert.equal(B.canSave(["correct", "mode_swap"]).ok, false);
  assert.equal(B.canSave(["mode_swap", "other_error"]).ok, true);
});

test("the next item is the first unrated one after the current, then from the start", () => {
  const items = [1, 2, 3, 4].map((position) => ({ position }));
  assert.equal(B.nextUnrated(items, {}, 0), 1);
  assert.equal(B.nextUnrated(items, { 1: {}, 2: {} }, 0), 3);
  assert.equal(B.nextUnrated(items, { 3: {}, 4: {} }, 3), 1);
  assert.equal(B.nextUnrated(items, { 1: {}, 2: {}, 3: {}, 4: {} }, 2), null);
  assert.equal(B.move(items, 1, -1), 1);
  assert.equal(B.move(items, 4, 1), 4);
  assert.equal(B.move(items, 2, 1), 3);
});

test("progress is counts only", () => {
  assert.equal(B.progressText({ rated: 12, total: 26, left: 14 }), "12 z 26 ocenionych, zostało 14");
  assert.match(B.statusText("written"), /vaulcie/);
});
