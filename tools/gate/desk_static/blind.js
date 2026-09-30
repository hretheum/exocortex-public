/* Pure logic of the blind rating screen (roadmap task F2.10): keys, the selection of one item, which item
 * comes next, progress. No DOM access here, so it runs unchanged in Node (node --test) and in the page.
 * The screen never gets a configuration or a result from the server, only the item's text and the owner's
 * own ratings, so nothing here can show one. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DeskBlind = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var VERDICTS = ["correct", "mode_swap", "number_or_name", "other_error"];
  var MODES = ["fact", "plan", "requirement", "hypothesis"];
  var LABELS = {
    correct: "Poprawne", mode_swap: "Zamiana trybu", number_or_name: "Przekręcona liczba lub nazwa",
    other_error: "Inny błąd", fact: "fakt", plan: "plan", requirement: "wymóg", hypothesis: "hipoteza"
  };
  var TYPING = { INPUT: 1, TEXTAREA: 1, SELECT: 1 };

  /* The action a key press asks for, or null. Nothing happens while the owner types a comment
   * or with a modifier key. 1 to 4: categories, 5 to 8: mode in the source, 0: no mode,
   * Enter: save and go on, arrows: previous and next item. */
  function keyAction(ev) {
    if (!ev || ev.ctrlKey || ev.metaKey || ev.altKey) return null;
    if (ev.target && ev.target.tagName && TYPING[String(ev.target.tagName).toUpperCase()]) return null;
    var k = ev.key;
    if (k >= "1" && k <= "4" && k.length === 1) return { verdict: VERDICTS[Number(k) - 1] };
    if (k >= "5" && k <= "8" && k.length === 1) return { mode: MODES[Number(k) - 5] };
    if (k === "0") return { mode: null };
    if (k === "Enter") return { save: true };
    if (k === "ArrowLeft") return { move: -1 };
    if (k === "ArrowRight") return { move: 1 };
    return null;
  }

  /* A new selection after a category is switched: "correct" stands alone, errors can go together. */
  function toggle(selected, verdict) {
    if (VERDICTS.indexOf(verdict) < 0) return (selected || []).slice();
    var sel = (selected || []).filter(function (v) { return VERDICTS.indexOf(v) >= 0; });
    if (sel.indexOf(verdict) >= 0) return sel.filter(function (v) { return v !== verdict; });
    if (verdict === "correct") return ["correct"];
    sel = sel.filter(function (v) { return v !== "correct"; });
    sel.push(verdict);
    return VERDICTS.filter(function (v) { return sel.indexOf(v) >= 0; });
  }

  /* Whether a selection can be saved, with the reason when it cannot (the server checks the same). */
  function canSave(selected) {
    if (!selected || !selected.length) return { ok: false, reason: "Wybierz co najmniej jedną kategorię." };
    if (selected.indexOf("correct") >= 0 && selected.length > 1) return { ok: false, reason: "„Poprawne” nie idzie w parze z błędem." };
    return { ok: true, reason: null };
  }

  /* The first item without a rating after ``from`` (a position), else the first one before it, else null. */
  function nextUnrated(items, ratings, from) {
    var rated = ratings || {};
    var open = items.filter(function (it) { return !rated[String(it.position)]; });
    var after = open.filter(function (it) { return it.position > (from || 0); });
    var pick = after[0] || open[0];
    return pick ? pick.position : null;
  }

  /* Where to go after a move of ``step`` from ``position``, staying inside the sample. */
  function move(items, position, step) {
    var i = items.findIndex(function (it) { return it.position === position; });
    var j = Math.min(items.length - 1, Math.max(0, (i < 0 ? 0 : i) + step));
    return items.length ? items[j].position : null;
  }

  /* The items still waiting and the ones already rated, both in the order of the draw. */
  function split(items, ratings) {
    var rated = ratings || {};
    var out = { waiting: [], rated: [] };
    (items || []).forEach(function (it) { (rated[String(it.position)] ? out.rated : out.waiting).push(it); });
    return out;
  }

  /* A claim cut to one line for the folded list of rated items. */
  function shortText(text, max) {
    var t = String(text || "").replace(/\s+/g, " ").trim();
    max = max || 90;
    return t.length > max ? t.slice(0, max - 1) + "\u2026" : t;
  }

  /* "12 z 26 ocenionych, zostało 14": counts only, never a share or a category. */
  function progressText(p) {
    return p.rated + " z " + p.total + " ocenionych, zostało " + p.left;
  }

  var STATUS = {
    "new": "nieoceniona", rating: "w trakcie", finished: "zakończona, strona czeka na zapis",
    written: "strona zapisana w vaulcie", changed: "strona wylosowana ponownie, oceny zaczynają się od nowa",
    by_hand: "oceniona ręcznie na stronie"
  };
  function statusText(s) { return STATUS[s] || s; }

  return { VERDICTS: VERDICTS, MODES: MODES, LABELS: LABELS, keyAction: keyAction, toggle: toggle, canSave: canSave,
           nextUnrated: nextUnrated, move: move, progressText: progressText, statusText: statusText,
           split: split, shortText: shortText };
});
