/* Pure logic of the review desk: key handling, which finding is next, progress.
 * No DOM access here, so it runs unchanged in Node (node --test) and in the page. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DeskLogic = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var TYPING = { INPUT: 1, TEXTAREA: 1, SELECT: 1 };

  /* Which action a key press asks for, or null. Nothing happens while a person
   * types in a field, while a confirmation is open, or with a modifier key. */
  function keyAction(ev, ctx) {
    ctx = ctx || {};
    if (!ev || ev.ctrlKey || ev.metaKey || ev.altKey) return null;
    if (ctx.modal) return null;
    if (ev.target && ev.target.tagName && TYPING[String(ev.target.tagName).toUpperCase()]) return null;
    switch (ev.key) {
      case "1": return "keep";
      case "2": return "to_edit";
      case "Backspace": return "undo";
      case "ArrowDown": return "skip";
      default: return null;
    }
  }

  /* Whether an action may run on a finding; a literal finding can only be edited. */
  function canAct(action, finding) {
    if (action === "keep" && finding && finding.literal) {
      return { ok: false, reason: "A literal finding cannot be kept. Mark it to edit." };
    }
    if ((action === "keep" || action === "to_edit") && (!finding || finding.state === "outdated")) {
      return { ok: false, reason: "There is no finding to decide." };
    }
    return { ok: true, reason: null };
  }

  /* The next finding to look at: an open one after the current, else before it,
   * never a skipped one. When only skipped ones are left they come back. */
  function nextFocus(findings, skipped, currentId) {
    var open = findings.filter(function (f) { return f.state === "open"; });
    var skip = {};
    (skipped || []).forEach(function (id) { skip[id] = true; });
    var fresh = open.filter(function (f) { return !skip[f.id]; });
    var pos = findings.findIndex(function (f) { return f.id === currentId; });
    var after = fresh.filter(function (f) { return findings.indexOf(f) > pos; });
    var pick = after[0] || fresh[0];
    if (pick) return { id: pick.id, skipped: (skipped || []).slice() };
    if (open.length) return { id: open[0].id, skipped: [] };
    return { id: null, skipped: [] };
  }

  function skip(findings, skipped, currentId) {
    var list = (skipped || []).slice();
    if (currentId != null && list.indexOf(currentId) < 0) list.push(currentId);
    return nextFocus(findings, list, currentId);
  }

  /* Header progress: "14 of 60, 3 to edit". */
  function progress(findings) {
    var live = findings.filter(function (f) { return f.state !== "outdated"; });
    var toEdit = live.filter(function (f) { return f.state === "to_edit"; }).length;
    var done = live.filter(function (f) { return f.state === "kept" || f.state === "to_edit"; }).length;
    return { done: done, total: live.length, toEdit: toEdit,
             text: done + " of " + live.length + ", " + toEdit + " to edit" };
  }

  /* Folder of a path, with a trailing slash; "" for a path at the top. */
  function folderOf(path) {
    var i = String(path).lastIndexOf("/");
    return i < 0 ? "" : path.slice(0, i + 1);
  }

  /* One line for a decided finding. */
  function collapsedLine(f) {
    var mark = f.state === "kept" ? "kept" : f.state === "to_edit" ? "to edit" : f.state;
    return mark + " · " + f.path + " · " + f.rule + " · " + Number(f.score).toFixed(3);
  }

  /* Label and reason for a bulk button from a server preview. */
  function bulkButton(kind, preview) {
    var label = kind === "unit" ? "Keep the whole experiment" : "Keep the whole folder";
    if (!preview) return { label: label, disabled: true, reason: "" };
    return { label: label, disabled: !!preview.disabled, reason: preview.reason || "" };
  }

  function bulkSummary(p) {
    return p.files + " file(s), " + p.paragraphs + " paragraph(s), highest similarity " + Number(p.max_score).toFixed(3);
  }

  /* Drafts that wait for the owner's decision: a draft pair not approved yet, or changed after the approval.
   * The same rule as the server's Queue counter (tools/publisher/approvals.py, waits_for_owner). */
  function waitingDrafts(drafts) {
    return (drafts || []).filter(function (d) { return d.state === "draft" && d.approval !== "waiting"; });
  }

  /* The text of a menu counter, or null when nothing waits (the counter is hidden then). */
  function badge(n) {
    n = Number(n) || 0;
    if (n <= 0) return null;
    return n > 999 ? "999+" : String(n);
  }

  return { badge: badge, waitingDrafts: waitingDrafts, keyAction: keyAction, canAct: canAct, nextFocus: nextFocus, skip: skip, progress: progress,
           folderOf: folderOf, collapsedLine: collapsedLine, bulkButton: bulkButton, bulkSummary: bulkSummary };
});
