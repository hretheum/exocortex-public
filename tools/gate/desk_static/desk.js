/* Review desk page script. Every piece of text goes into the page with textContent,
 * never as markup. Nothing is loaded from another origin. */
(function () {
  "use strict";
  var L = window.DeskLogic;
  var B = window.DeskBlind;
  var meta = document.querySelector('meta[name="csrf-token"]');
  var CSRF = meta ? meta.content : "";

  function h(tag, attrs) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "class") el.className = attrs[k];
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] === true) el.setAttribute(k, "");
      else if (attrs[k] !== false && attrs[k] != null) el.setAttribute(k, attrs[k]);
    });
    function add(c) {
      if (c == null || c === false) return;
      if (Array.isArray(c)) { c.forEach(add); return; }
      el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    }
    for (var i = 2; i < arguments.length; i++) add(arguments[i]);
    return el;
  }

  /* A paragraph shown as formatted text. marked turns the Markdown into HTML and DOMPurify cleans it
   * (no scripts, images, forms or styles, and links lose their address) before it goes into the page. */
  var FORBID_TAGS = ["img", "picture", "source", "style", "form", "input", "button", "textarea", "select",
                     "iframe", "object", "embed", "link", "meta", "svg", "math"];
  var FORBID_ATTR = ["style", "href", "src", "srcset", "target", "action"];
  var toHtml = null;  // built on first use: the sign-in page loads this script without the libraries
  function mdView(text) {
    var box = h("div", { class: "md" });
    if (!toHtml) toHtml = window.DeskMd.create(window.marked);
    var html = toHtml(text);
    box.innerHTML = window.DOMPurify.sanitize(html, { FORBID_TAGS: FORBID_TAGS, FORBID_ATTR: FORBID_ATTR });
    return box;
  }

  function api(method, path, body) {
    var opt = { method: method, credentials: "same-origin", headers: { "X-CSRF-Token": CSRF } };
    if (body !== undefined) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(body);
    }
    return fetch(path, opt).then(function (r) {
      if (r.status === 401) { location.reload(); throw new Error("unauthorised"); }
      return r.json().then(function (j) {
        if (!r.ok) { var e = new Error(j.message || j.error || "error"); e.status = r.status; throw e; }
        if (method === "POST") refreshCounts();  // every action can change what waits
        return j;
      });
    });
  }

  /* Menu counters: how many queue units and how many blind rating items wait for the owner. The server
   * counts them (/api/counts); the page only puts the numbers next to the menu entries, in place, so
   * nothing else on the screen is redrawn. A zero hides the counter. */
  var counts = { queue: 0, blind: 0 };
  function paintCounts() {
    [["queue", "nav-queue"], ["blind", "nav-blind"]].forEach(function (k) {
      var btn = document.getElementById(k[1]);
      if (!btn) return;
      var old = btn.badgeNode;
      if (old) { old.hidden = true; old.textContent = ""; }
      var text = L.badge(counts[k[0]]);
      if (!text) return;
      if (!old) { old = h("span", { class: "badge" }); btn.appendChild(old); btn.badgeNode = old; }
      old.hidden = false;
      old.textContent = text;
      old.setAttribute("aria-label", text + (k[0] === "queue" ? " jednostek czeka" : " twierdzeń czeka"));
    });
  }
  function refreshCounts() {
    return fetch("/api/counts", { credentials: "same-origin", headers: { "X-CSRF-Token": CSRF } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j) { counts = { queue: j.queue || 0, blind: j.blind || 0 }; paintCounts(); } })
      .catch(function () {});
  }

  var app = document.getElementById("app");
  var hdr = document.getElementById("hdr");
  var state = { view: "queue", unit: null, findings: [], skipped: [], current: null, card: null, modal: false, msg: "", compareOpen: false, doneOpen: false, want: null };

  function say(text) { state.msg = text || ""; var m = document.getElementById("msg"); if (m) m.textContent = state.msg; }
  function fail(e) { say(e.message); }

  /* A short notice at the bottom of the screen. It survives a change of screen, goes away by itself
   * and can carry an Undo button. Text goes in with textContent only. */
  var later = typeof setTimeout === "function" ? setTimeout : function () { return 0; };
  var unlater = typeof clearTimeout === "function" ? clearTimeout : function () {};
  var toastTimer = 0, lastToast = "";
  function hideToast() {
    var el = document.getElementById("toast");
    if (el) { el.hidden = true; el.textContent = ""; }
  }
  function toast(text, undoFn) {
    var el = document.getElementById("toast");
    if (!el) return;
    unlater(toastTimer);
    lastToast = text;
    el.textContent = "";
    el.hidden = false;
    el.appendChild(h("span", {}, text));
    if (undoFn) el.appendChild(h("button", { class: "small", onclick: function () { hideToast(); undoFn(); } }, "Undo"));
    toastTimer = later(hideToast, 8000);
  }

  function nav() {
    hdr.textContent = "";
    hdr.appendChild(h("strong", {}, "Review desk"));
    [["queue", "Queue"], ["blind", "Ocena na ślepo"], ["rules", "Rules"], ["history", "History"]].forEach(function (v) {
      var on = state.view === v[0] || (v[0] === "blind" && state.view === "blind-rate") || (v[0] === "queue" && state.view === "focus");
      hdr.appendChild(h("button", { class: "nav" + (on ? " on" : ""), id: "nav-" + v[0], onclick: function () { go(v[0]); } }, v[1]));
    });
    paintCounts();
    hdr.appendChild(h("button", { class: "nav publish", id: "publish", title: "Switch on the approved drafts and run the publisher now", onclick: publishNow }, "Publish now"));
    if (state.view === "focus") {
      var p = L.progress(state.findings);
      hdr.appendChild(h("span", { class: "progress", id: "progress" }, state.unit.cls + ":" + state.unit.key + " · " + p.text));
    }
    if (state.view === "blind-rate" && state.blind && state.blind.data) {
      hdr.appendChild(h("span", { class: "progress", id: "progress" }, state.blind.data.sample + " · " + B.progressText(state.blind.data.progress)));
    }
    hdr.appendChild(h("span", { id: "msg", class: "msg", role: "status" }, state.msg));
  }

  /* Every screen has its own address (the part after #), so the browser's back and forward
   * buttons, reload and a copied link all work: #/ queue, #/unit/12 one unit, #/rules, #/history. */
  function navigate(hash) {
    if (location.hash === hash) route(); else location.hash = hash;
  }

  function go(view) { navigate(view === "queue" ? "#/" : "#/" + view); }

  function route() {
    state.modal = false; say("");
    refreshCounts();
    var m = /^#\/unit\/(\d+)$/.exec(location.hash || "");
    if (m) return showUnit(Number(m[1]));
    if (location.hash === "#/rules") { state.view = "rules"; return rules(); }
    if (location.hash === "#/history") { state.view = "history"; return history(); }
    var b = /^#\/blind\/([a-z0-9-]+)\/([a-z0-9-]+)$/.exec(location.hash || "");
    if (b) { state.view = "blind-rate"; return blindOpen(b[1], b[2]); }
    if (location.hash === "#/blind") { state.view = "blind"; return blindList(); }
    state.view = "queue";
    return queue();
  }

  /* "Publish now" writes a request on the server, which starts the publisher within a minute. The publisher
   * still applies every gate. The desk then watches the run log until a newer run shows up. */
  function publishSummary(last) {
    return last ? "Last publish " + String(last.time).slice(0, 16).replace("T", " ") + " UTC: " + last.published +
      " published, " + last.held + " held" + (last.status === "ok" ? "" : " (" + last.status + ")") : "No publish run yet.";
  }

  function publishNow() {
    var btn = document.getElementById("publish");
    if (btn) btn.disabled = true;
    api("GET", "/api/publish").then(function (before) {
      var seen = before.last ? before.last.time : null;
      return api("POST", "/api/publish", {}).then(function (r) {
        toast(r.already ? "A publish is already requested. It runs within a minute." : "Publish requested. Approved drafts are switched on first. It runs within a minute.");
        watchPublish(seen, 0);
      });
    }).catch(function (e) { if (btn) btn.disabled = false; fail(e); });
  }

  function watchPublish(seen, tries) {
    later(function () {
      api("GET", "/api/publish").then(function (r) {
        var newer = r.last && r.last.time !== seen && !r.pending;
        if (newer || tries >= 30) {
          var btn = document.getElementById("publish");
          if (btn) btn.disabled = false;
          toast(newer ? publishSummary(r.last) : "No new publish run yet. It may still be waiting; check again later.");
          if (state.view === "queue") queue();
          return;
        }
        watchPublish(seen, tries + 1);
      }).catch(function (e) { fail(e); });
    }, 5000);
  }

  function table(head, rows) {
    return h("table", {}, h("thead", {}, h("tr", {}, head.map(function (t) { return h("th", {}, t); }))),
             h("tbody", {}, rows));
  }

  function unitTable(units) {
    return table(["Unit", "Class", "Findings", "State", "Age (days)"], units.map(function (u) {
      return h("tr", { class: "row", tabindex: "0", onclick: function (e) { if (!(e && e.target && e.target.tagName === "A")) openUnit(u.id); },
                       onkeydown: function (e) { if (e.key === "Enter") openUnit(u.id); } },
        h("td", {}, h("a", { href: "#/unit/" + u.id }, u.key)), h("td", {}, u.cls), h("td", {}, u.findings + " (" + u.counts.open + " open, " + u.counts.to_edit + " to edit)"),
        h("td", {}, u.state), h("td", {}, u.age_days));
    }));
  }

  /* The queue lists what still waits for a decision. Units with nothing open (released, or held only
   * for an edit) move to a folded "Processed" part, still one click away to open and take back. */
  function queue() {
    Promise.all([api("GET", "/api/units"), api("GET", "/api/drafts").catch(function () { return { drafts: [] }; })]).then(function (both) {
      var r = both[0];
      nav(); app.textContent = "";
      var box = draftsBox(both[1].drafts || []);
      if (box) app.appendChild(box);
      if (!r.units.length) { app.appendChild(h("p", {}, "The quarantine is empty.")); return; }
      var todo = r.units.filter(function (u) { return u.counts.open > 0; });
      var rest = r.units.filter(function (u) { return !(u.counts.open > 0); });
      if (todo.length) app.appendChild(unitTable(todo));
      else app.appendChild(h("p", { class: "done" }, "Nothing left to check."));
      if (rest.length) {
        app.appendChild(h("details", { class: "processed" }, h("summary", {}, "Processed (" + rest.length + ")"), unitTable(rest)));
      }
      api("GET", "/api/publish").then(function (p) {
        if (p.configured) app.appendChild(h("p", { class: "meta", id: "lastpublish" }, publishSummary(p.last)));
      }).catch(function () {});
    }).catch(fail);
  }

  /* Drafts wait for the owner's approval. Approving records the decision only; the flags in the files
   * (publish and human_validated) are set on the server when "Publish now" runs, and only if the texts
   * are still the ones shown here. */
  function stripFront(text) { return String(text || "").replace(/^---\n[\s\S]*?\n---\n/, ""); }

  function draftRow(d) {
    var title = d.title.pl || d.title.en || d.slug;
    var status = d.approval === "waiting" ? "Zatwierdzony. Trafi na stronę po naciśnięciu Publish now." :
      d.approval === "changed" ? "Zmieniony po zatwierdzeniu. Przeczytaj go i zatwierdź jeszcze raz." : "Czeka na zatwierdzenie.";
    if (d.origin === "lab") {
      status = "Nowy szkic z laboratorium" + (d.replaces ? ", zastąpi sekcję w vaulcie" : "") + ". " + status;
    }
    var buttons = [];
    if (d.approval === "waiting") {
      buttons.push(h("button", { class: "small withdraw", onclick: function () { withdrawDraft(d, false); } }, "Wycofaj zatwierdzenie"));
    } else {
      buttons.push(h("button", { class: "keep approve", onclick: function () { approveDraft(d); } }, "Zatwierdź"));
    }
    return h("div", { class: "draft " + d.approval },
      h("div", { class: "draft-h" }, h("strong", {}, title), " ", h("span", { class: "meta" }, d.slug + " \u00b7 " + status)),
      h("details", { class: "compare" }, h("summary", {}, "Przeczytaj tekst (po polsku i po angielsku)"),
        ["pl", "en"].filter(function (l) { return d.text[l]; }).map(function (l) {
          return h("section", { class: "pane" }, h("h3", {}, l === "pl" ? "Po polsku" : "Po angielsku"), mdView(stripFront(d.text[l])));
        })),
      h("div", { class: "actions" }, buttons));
  }

  function draftsBox(drafts) {
    var open = drafts.filter(function (d) { return d.state === "draft"; });
    var broken = drafts.filter(function (d) { return d.state === "broken"; });
    if (!open.length && !broken.length) return null;
    // the heading counts what waits for a decision, like the Queue counter; approved drafts stay listed
    var box = h("section", { id: "drafts", class: "drafts" },
      h("h2", {}, "Szkice do zatwierdzenia (" + L.waitingDrafts(drafts).length + ")"));
    open.forEach(function (d) { box.appendChild(draftRow(d)); });
    broken.forEach(function (d) {
      box.appendChild(h("p", { class: "meta why" }, d.slug + ": wersja polska i angielska nie są parą (brakuje jednej albo tylko jedna jest zatwierdzona). Popraw pliki; tu nie da się tego zatwierdzić."));
    });
    return box;
  }

  function approveDraft(d) {
    api("POST", "/api/drafts/" + d.slug + "/approve", { sha: d.sha, origin: d.origin }).then(function () {
      toast("Zatwierdzono: " + (d.title.pl || d.slug) + ". Trafi na stronę po naciśnięciu Publish now.", function () { withdrawDraft(d, true); });
      if (state.view === "queue") queue();
    }).catch(fail);
  }

  function withdrawDraft(d, quiet) {
    api("POST", "/api/drafts/" + d.slug + "/withdraw", { origin: d.origin }).then(function () {
      if (!quiet) toast("Zatwierdzenie wycofane");
      if (state.view === "queue") queue();
    }).catch(fail);
  }

  function openUnit(id) { navigate("#/unit/" + id); }

  function showUnit(id) {
    api("GET", "/api/units/" + id).then(function (r) {
      state.view = "focus"; state.unit = r.unit; state.findings = r.findings; state.bulk = r.bulk; state.skipped = [];
      state.current = wanted(r.findings) || L.nextFocus(r.findings, [], null).id;
      focus();
    }).catch(fail);
  }

  /* The finding a caller asked to see next (a reopened one), if it is open in this list. */
  function wanted(findings) {
    var id = state.want; state.want = null;
    return id != null && findings.some(function (f) { return f.id === id && f.state === "open"; }) ? id : null;
  }

  /* Reload the unit and show the next finding. When nothing is left here and `moveOn` is set, go to the
   * next unit that waits for a decision, or back to the queue when none does. */
  function reload(keepFocus, moveOn) {
    return api("GET", "/api/units/" + state.unit.id).then(function (r) {
      state.unit = r.unit; state.findings = r.findings; state.bulk = r.bulk;
      var cur = keepFocus ? state.current : null;
      state.current = wanted(r.findings) || L.nextFocus(r.findings, state.skipped, cur).id;
      if (state.current == null && moveOn) return nextUnit(r.unit);
      focus();
    });
  }

  function nextUnit(done) {
    return api("GET", "/api/units").then(function (r) {
      var next = r.units.filter(function (u) { return u.id !== done.id && u.counts.open > 0; })[0];
      if (next) { toast(lastToast + " Unit " + done.key + " is done, next: " + next.key + ".", undoLast); return openUnit(next.id); }
      toast(lastToast + " Nothing left to check.", undoLast);
      return go("queue");
    });
  }

  function focus() {
    state.card = null; nav(); app.textContent = "";
    var done = state.findings.filter(function (f) { return f.state === "kept" || f.state === "to_edit"; });
    var cur = state.findings.find(function (f) { return f.id === state.current; });
    if (!cur) {
      app.appendChild(h("p", { class: "done" }, state.unit.state === "released" ? "Nothing left to decide: the unit is released." :
        "Nothing left to decide here. Findings marked to edit keep the unit held until the source changes."));
      app.appendChild(bulkBar(null));
      app.appendChild(processedBox(done, true));
      return;
    }
    app.appendChild(h("div", { id: "card", class: "card" }, "Loading…"));
    app.appendChild(bulkBar(cur));
    app.appendChild(processedBox(done, false));
    api("GET", "/api/findings/" + cur.id + "/card").then(function (c) { state.card = c; renderCard(cur, c); }).catch(fail);
  }

  /* What was decided in this unit, folded under the card. A finding kept by hand or marked to edit can
   * be put back in the queue from here; one kept by an old approval or a standing rule cannot. */
  function processedBox(done, forceOpen) {
    if (!done.length) return h("span", {});
    var open = forceOpen || state.doneOpen;
    return h("details", { class: "processed", open: open, ontoggle: function (e) { if (!forceOpen) state.doneOpen = !!(e && e.target && e.target.open); } },
      h("summary", {}, "Processed in this unit (" + done.length + ")"),
      h("ul", { class: "decided" }, done.map(function (f) {
        var back = f.state === "to_edit" || f.kept_via === "manual";
        return h("li", { class: "line " + f.state }, L.collapsedLine(f), " ",
          back ? h("button", { class: "small", onclick: function () { reopen(f.id); } }, "Reopen") : h("span", { class: "why" }, "kept by a rule"));
      })));
  }

  function reopen(id) {
    api("POST", "/api/findings/" + id + "/reopen", {}).then(function () {
      state.want = id; toast("Back in the queue"); return reload(false);
    }).catch(fail);
  }

  function noteBox(id) {
    var a = { rows: "2", maxlength: "500", placeholder: "Note for the edit (do not quote protected text)" };
    if (id) a.id = id;
    return h("textarea", a);
  }

  /* The note field and the decision buttons. The card shows this block twice, above the paragraphs and
   * below them, so a long paragraph never hides the buttons; the two note fields mirror each other. */
  function actionsBlock(f, note) {
    return h("div", { class: "actionblock" }, note, h("div", { class: "actions" },
      h("button", { class: "keep", disabled: f.literal, title: f.literal ? "A literal finding cannot be kept" : "", onclick: function () { act("keep"); } }, "Keep (1)"),
      h("button", { onclick: function () { act("to_edit"); } }, "To edit (2)"),
      h("button", { onclick: function () { act("skip"); } }, "Skip (\u2193)"),
      h("button", { onclick: function () { act("undo"); } }, "Undo (Backspace)"),
      f.literal ? h("span", { class: "why" }, "Literal finding: it can only be edited.") : standingForm(f)));
  }

  function renderCard(f, c) {
    var el = document.getElementById("card");
    if (!el || state.current !== f.id) return;
    el.textContent = "";
    var noteTop = noteBox("note"), noteBottom = noteBox(null);
    noteTop.addEventListener("input", function () { noteBottom.value = noteTop.value; });
    noteBottom.addEventListener("input", function () { noteTop.value = noteBottom.value; });
    var pub = h("section", { class: "pane primary" }, h("h3", {}, "Public paragraph"),
      h("div", { class: "meta" }, f.path + " \u00b7 " + f.rule + " \u00b7 " + f.score.toFixed(3)),
      c.public === null ? h("p", { class: "meta" }, "(the paragraph is no longer in the source)") : mdView(c.public));
    var top = c.neighbours.reduce(function (m, n) { return Math.max(m, n.score); }, 0);
    var comparison = c.neighbours.length
      ? h("details", { class: "compare", open: state.compareOpen, ontoggle: function (e) { state.compareOpen = !!(e && e.target && e.target.open); } },
          h("summary", {}, "Compare with protected paragraphs (" + c.neighbours.length + ") \u00b7 highest similarity " + top.toFixed(3)),
          c.neighbours.map(function (n) { return neighbour(n); }))
      : h("p", { class: "meta" }, "No protected paragraph to compare with.");
    el.appendChild(h("div", { class: "topbar" }, actionsBlock(f, noteTop), bulkBar(f)));
    el.appendChild(pub);
    el.appendChild(h("p", { class: "hint" }, "Hint: " + c.hint));
    el.appendChild(actionsBlock(f, noteBottom));
    el.appendChild(comparison);
  }

  function neighbour(n) {
    var box = h("div", { class: "near" }, h("div", { class: "meta" }, (n.source || "unknown source") + " · similarity " + n.score.toFixed(3)),
      mdView(n.text));
    if (n.note_path) {
      var row = h("div", { class: "excl" });
      row.appendChild(h("button", { class: "small", onclick: function () { exclForm(row, n.note_path, "note"); } }, "Exclude note"));
      row.appendChild(h("button", { class: "small", onclick: function () { exclForm(row, n.folder_path, "folder"); } }, "Exclude folder"));
      box.appendChild(row);
    } else {
      box.appendChild(h("div", { class: "why" }, "Not a file: it cannot be excluded."));
    }
    return box;
  }

  function reasonForm(row, label, defaultDays, submit) {
    state.modal = true;
    row.textContent = "";
    var reason = h("input", { type: "text", placeholder: "Reason (required)", maxlength: "300", size: "34" });
    var days = h("input", { type: "number", min: "1", max: "3650", value: defaultDays || "", placeholder: "days", class: "days" });
    row.appendChild(h("span", {}, label + " "));
    row.appendChild(reason); row.appendChild(days);
    row.appendChild(h("button", { class: "small", onclick: function () { submit(reason.value, days.value ? Number(days.value) : null); } }, "Confirm"));
    row.appendChild(h("button", { class: "small", onclick: function () { state.modal = false; focus(); } }, "Cancel"));
    reason.focus();
  }

  function exclForm(row, path, scope) {
    reasonForm(row, "Exclude " + scope + " " + path + " (days optional):", "", function (reason, days) {
      api("POST", "/api/exclusions", { path: path, scope: scope, reason: reason, days: days }).then(function () {
        state.modal = false; say("Excluded " + path); focus();
      }).catch(fail);
    });
  }

  function standingForm(f) {
    var row = h("span", { class: "excl" });
    row.appendChild(h("button", { class: "small", onclick: function () {
      var folder = L.folderOf(f.path);
      if (!folder) { say("A file at the top level has no folder."); return; }
      reasonForm(row, "Always keep folder " + folder + " for (days):", "90", function (reason, days) {
        api("POST", "/api/rules/standing", { folder: folder, reason: reason, days: days }).then(function (r) {
          state.modal = false; say("Rule saved; applied to " + r.applied + " finding(s)"); reload(false);
        }).catch(fail);
      });
    } }, "Always keep this folder…"));
    return row;
  }

  /* Take back the newest decision. It may belong to another unit than the one on screen (after the
   * desk moved on by itself); then that unit opens with the restored finding first. */
  function undoLast() {
    return api("POST", "/api/undo", {}).then(function (r) {
      if (!r.undone) { toast("Nothing to undo"); return; }
      toast("Undone");
      var uid = r.undone.unit_id;
      state.want = r.undone.findings.length ? r.undone.findings[0] : null;
      if (state.view === "focus" && state.unit && uid === state.unit.id) return reload(false);
      if (uid != null) return openUnit(uid);
    }).catch(fail);
  }

  function act(action) {
    var f = state.findings.find(function (x) { return x.id === state.current; });
    if (action === "skip") { var n = L.skip(state.findings, state.skipped, state.current); state.skipped = n.skipped; state.current = n.id; return focus(); }
    if (action === "undo") return undoLast();
    var ok = L.canAct(action, f);
    if (!ok.ok) return say(ok.reason);
    var noteEl = document.getElementById("note");
    api("POST", "/api/findings/" + f.id + "/decide", { decision: action, note: action === "to_edit" && noteEl && noteEl.value ? noteEl.value : null })
      .then(function () {
        var name = f.path.split("/").pop();
        toast(action === "keep" ? "Kept and moved to accepted: " + name : "Marked to edit: " + name, undoLast);
        return reload(true, true);
      }).catch(fail);
  }

  function bulkBar(cur) {
    var bar = h("div", { class: "bulk" });
    var scopes = [];
    if (state.unit.cls === "experiment") scopes.push(["unit", null, state.bulk.unit]);
    var folder = cur ? L.folderOf(cur.path) : "";
    if (folder && state.bulk.folders[folder]) scopes.push(["folder", folder, state.bulk.folders[folder]]);
    scopes.forEach(function (s) {
      var b = L.bulkButton(s[0], s[2]);
      bar.appendChild(h("button", { class: "bulkbtn", disabled: b.disabled, onclick: function () { confirmBulk(bar, s[1], b.label); } }, b.label));
      if (b.disabled && b.reason) bar.appendChild(h("span", { class: "why" }, b.reason));
    });
    return bar;
  }

  function confirmBulk(bar, folder, label) {
    var q = folder ? "?folder=" + encodeURIComponent(folder) : "";
    api("GET", "/api/units/" + state.unit.id + "/bulk" + q).then(function (p) {
      state.modal = true; bar.textContent = "";
      bar.appendChild(h("span", {}, label + ": " + L.bulkSummary(p) + ". "));
      bar.appendChild(h("button", { id: "confirm", onclick: function () {
        api("POST", "/api/units/" + state.unit.id + "/bulk", { folder: folder, digest: p.digest, confirm: true })
          .then(function () { state.modal = false; toast("Kept and moved to accepted: " + label.replace("Keep ", ""), undoLast); return reload(false, true); }).catch(fail);
      } }, "Confirm"));
      bar.appendChild(h("button", { onclick: function () { state.modal = false; focus(); } }, "Cancel"));
    }).catch(fail);
  }

  function rules() {
    api("GET", "/api/rules").then(function (r) {
      nav(); app.textContent = "";
      app.appendChild(h("h2", {}, "Standing rules (always keep a folder)"));
      app.appendChild(r.standing.length ? table(["Folder", "Reason", "Expires", "By", "State", ""], r.standing.map(function (x) {
        return h("tr", {}, h("td", {}, x.folder), h("td", {}, x.reason), h("td", {}, x.expires_at), h("td", {}, x.who),
          h("td", {}, x.active ? "active" : "ended"),
          h("td", {}, x.active ? h("button", { class: "small", onclick: function () { api("POST", "/api/rules/standing/" + x.id + "/revoke", {}).then(rules).catch(fail); } }, "Revoke") : ""));
      })) : h("p", {}, "None."));
      app.appendChild(h("h2", {}, "Sources switched off from protection"));
      app.appendChild(h("p", { class: "meta" }, r.hard_list.available ? r.hard_list.entries + " path(s) on the hard list can never be switched off." :
        "The hard list is not available: nothing can be switched off."));
      app.appendChild(r.exclusions.length ? table(["Path", "Reason", "Expires", "By", "State", ""], r.exclusions.map(function (x) {
        return h("tr", {}, h("td", {}, x.path), h("td", {}, x.reason), h("td", {}, x.expires_at || "never"), h("td", {}, x.who),
          h("td", {}, x.active ? "active" : "ended"),
          h("td", {}, x.active ? h("button", { class: "small", onclick: function () { api("POST", "/api/exclusions/" + x.id + "/revoke", {}).then(rules).catch(fail); } }, "Revoke") : ""));
      })) : h("p", {}, "None."));
    }).catch(fail);
  }

  function history() {
    api("GET", "/api/history?limit=200").then(function (r) {
      nav(); app.textContent = "";
      app.appendChild(table(["When", "Who", "Decision", "Unit", "Path", "Detail"], r.history.map(function (x) {
        return h("tr", { class: x.undone ? "undone" : "" }, h("td", {}, x.at), h("td", {}, x.who), h("td", {}, x.decision),
          h("td", {}, x.unit || ""), h("td", {}, x.path || ""), h("td", {}, x.detail || ""));
      })));
    }).catch(fail);
  }

  /* -- Blind rating (F2.10). The server sends the item's text and the owner's own ratings only: no
   * configuration, no document name, no share or count per category. One item at a time, in the random
   * order of the draw; a rating is saved at once, so a break loses nothing. */
  function blindList() {
    api("GET", "/api/blind").then(function (r) {
      nav(); app.textContent = "";
      app.appendChild(h("h2", {}, "Ocena na ślepo"));
      if (!r.configured) { app.appendChild(h("p", { class: "meta" }, "Biurko nie ma folderu laboratorium albo folderu stanu.")); return; }
      if (!r.samples.length) {
        app.appendChild(h("p", {}, "Nie ma stron do oceny. Laboratorium tworzy je poleceniem exocortex-lab-blind@draw_<eksperyment>_<próba>."));
        return;
      }
      app.appendChild(h("p", { class: "meta" }, "Widać tylko postęp. Wyniki pojawią się dopiero po wczytaniu ocen do laboratorium."));
      app.appendChild(table(["Eksperyment", "Próba", "Ocenione", "Czeka", "Stan"], r.samples.map(function (x) {
        var open = function () { navigate("#/blind/" + x.experiment + "/" + x.sample); };
        var waiting = x.status === "by_hand" || x.status === "finished" || x.status === "written" ? 0 : x.progress.left;
        return h("tr", { class: "row", tabindex: "0", onclick: open, onkeydown: function (e) { if (e.key === "Enter") open(); } },
          h("td", {}, x.experiment), h("td", {}, x.sample), h("td", {}, x.progress.rated + " z " + x.progress.total),
          h("td", {}, String(waiting)), h("td", {}, B.statusText(x.status)));
      })));
    }).catch(fail);
  }

  function blindOpen(experiment, sample) {
    api("GET", "/api/blind/" + experiment + "/" + sample).then(function (d) {
      var start = B.nextUnrated(d.items, d.ratings, 0);
      state.blind = { data: d, pos: start == null ? d.items[0].position : start };
      blindShow();
    }).catch(fail);
  }

  function blindSelect(pos) {
    var bl = state.blind, r = bl.data.ratings[String(pos)];
    bl.pos = pos;
    bl.sel = r ? r.verdicts.slice() : [];
    bl.mode = r ? r.source_mode : null;
    bl.comment = r ? r.comment : "";
  }

  /* The context with the quote marked, built from text nodes only. */
  function contextView(context, quote) {
    var box = h("p", { class: "ctx" });
    var at = quote ? context.indexOf(quote) : -1;
    if (at < 0) { box.appendChild(document.createTextNode(context)); return box; }
    box.appendChild(document.createTextNode(context.slice(0, at)));
    box.appendChild(h("mark", {}, quote));
    box.appendChild(document.createTextNode(context.slice(at + quote.length)));
    return box;
  }

  function blindShow(keepSelection) {
    var bl = state.blind, d = bl.data;
    if (!keepSelection) blindSelect(bl.pos);
    nav(); app.textContent = "";
    var it = d.items.find(function (x) { return x.position === bl.pos; });
    var rated = !!d.ratings[String(bl.pos)];
    app.appendChild(h("p", { class: "meta" }, "Pozycja " + bl.pos + " z " + d.items.length + (rated ? " · oceniona, możesz zmienić ocenę" : "") +
      (d.status === "changed" ? " · strona została wylosowana ponownie, oceny zaczynają się od nowa" : "")));
    var card = h("div", { class: "card blind", id: "blindcard" });
    card.appendChild(h("section", { class: "pane primary" }, h("h3", {}, "Twierdzenie"), h("p", { class: "claim" }, it.claim)));
    card.appendChild(h("section", { class: "pane" }, h("h3", {}, "Cytat"), h("blockquote", { class: "quote" }, it.quote)));
    card.appendChild(h("section", { class: "pane" }, h("h3", {}, "Fragment wokół cytatu"), contextView(it.context, it.quote)));
    var cats = h("div", { class: "actions cats", role: "group", "aria-label": "Kategoria" }, B.VERDICTS.map(function (v, i) {
      var on = bl.sel.indexOf(v) >= 0;
      return h("button", { class: "cat" + (on ? " on" : "") + (v === "correct" ? " keep" : ""), "aria-pressed": on ? "true" : "false",
                           onclick: function () { blindKey({ verdict: v }); } }, (i + 1) + " " + B.LABELS[v]);
    }));
    var modes = h("div", { class: "actions modes", role: "group", "aria-label": "Tryb w źródle" },
      h("span", { class: "meta" }, "Tryb w źródle (niewymagany):"),
      B.MODES.map(function (m, i) {
        var on = bl.mode === m;
        return h("button", { class: "small" + (on ? " on" : ""), "aria-pressed": on ? "true" : "false", onclick: function () { blindKey({ mode: on ? null : m }); } }, (i + 5) + " " + B.LABELS[m]);
      }),
      h("button", { class: "small" + (bl.mode == null ? " on" : ""), onclick: function () { blindKey({ mode: null }); } }, "0 bez trybu"));
    var comment = h("input", { type: "text", id: "blindcomment", maxlength: "1000", placeholder: "Komentarz (niewymagany)", value: bl.comment || "" });
    comment.addEventListener("input", function () { bl.comment = comment.value; });
    comment.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); blindKey({ save: true }); }
      if (e.key === "Escape" && comment.blur) comment.blur();
    });
    var check = B.canSave(bl.sel);
    card.appendChild(cats);
    card.appendChild(modes);
    card.appendChild(h("div", { class: "actions" }, comment));
    card.appendChild(h("div", { class: "actions" },
      h("button", { onclick: function () { blindKey({ move: -1 }); } }, "\u2190 Poprzednia"),
      h("button", { class: "keep", id: "blindsave", disabled: !check.ok, onclick: function () { blindKey({ save: true }); } }, "Zapisz i dalej (Enter)"),
      h("button", { onclick: function () { blindKey({ move: 1 }); } }, "Następna \u2192"),
      check.ok ? null : h("span", { class: "why" }, check.reason)));
    app.appendChild(card);
    app.appendChild(h("p", { class: "meta" }, "Klawisze: 1–4 kategoria, 5–8 tryb w źródle, 0 bez trybu, Enter zapisz i dalej, \u2190 \u2192 poprzednia i następna."));
    if (d.progress.left === 0) app.appendChild(finishBox());
    app.appendChild(ratedBox());
  }

  /* Rated items fold into a list under the card, like "Processed" in the queue. Opening one shows it with
   * the owner's own rating, which can be changed. The list shows no verdicts, so it cannot be tallied. */
  function ratedBox() {
    var bl = state.blind, parts = B.split(bl.data.items, bl.data.ratings);
    if (!parts.rated.length) return h("span", {});
    return h("details", { class: "processed", id: "blindrated", open: !!bl.ratedOpen,
                          ontoggle: function (e) { bl.ratedOpen = !!(e && e.target && e.target.open); } },
      h("summary", {}, "Ocenione (" + parts.rated.length + ")"),
      h("ul", { class: "decided" }, parts.rated.map(function (it) {
        return h("li", { class: "line rated" + (it.position === bl.pos ? " cur" : "") },
          "Pozycja " + it.position + " \u00b7 " + B.shortText(it.claim), " ",
          h("button", { class: "small", onclick: function () { blindSelect(it.position); blindShow(true); } }, "Zmień ocenę"));
      })));
  }

  function finishBox() {
    var d = state.blind.data;
    var box = h("section", { class: "drafts", id: "blindfinish" }, h("h2", {}, "Wszystkie pozycje są ocenione"));
    if (d.status === "written") {
      box.appendChild(h("p", {}, "Strona z ocenami jest w vaulcie. Wczytaj ją do laboratorium: systemctl --user start exocortex-lab-blind@" + "import_" + d.experiment + "_" + d.sample));
    } else if (d.status === "finished") {
      box.appendChild(h("p", {}, "Ocenianie zakończone. Strona z ocenami trafi do vaulta w ciągu minuty."));
    } else {
      box.appendChild(h("p", {}, "Zakończenie zapisuje oceny na stronie w vaulcie. Do tego czasu możesz zmienić każdą ocenę."));
      box.appendChild(h("button", { class: "keep", id: "blinddone", onclick: blindFinish }, "Zakończ ocenianie"));
    }
    return box;
  }

  function blindFinish() {
    var d = state.blind.data;
    api("POST", "/api/blind/" + d.experiment + "/" + d.sample + "/finish", { page_sha: d.page_sha }).then(function (r) {
      d.status = r.status;
      toast("Ocenianie zakończone. Strona z ocenami trafi do vaulta w ciągu minuty.");
      blindShow(true);
    }).catch(fail);
  }

  function blindKey(a) {
    var bl = state.blind;
    if (!bl || !bl.data) return;
    if (a.verdict) { bl.sel = B.toggle(bl.sel, a.verdict); return blindShow(true); }
    if (a.mode !== undefined) { bl.mode = a.mode; return blindShow(true); }
    if (a.move) { blindSelect(B.move(bl.data.items, bl.pos, a.move)); return blindShow(true); }
    if (a.save) {
      var check = B.canSave(bl.sel);
      if (!check.ok) return say(check.reason);
      var d = bl.data, pos = bl.pos;
      var rating = { verdicts: bl.sel.slice(), source_mode: bl.mode, comment: bl.comment || "" };
      return api("POST", "/api/blind/" + d.experiment + "/" + d.sample + "/rate",
                 { position: pos, verdicts: rating.verdicts, source_mode: rating.source_mode, comment: rating.comment, page_sha: d.page_sha })
        .then(function (r) {
          d.ratings[String(pos)] = rating; d.progress = r.progress; d.status = r.status;
          var next = B.nextUnrated(d.items, d.ratings, pos);
          blindSelect(next == null ? pos : next);
          blindShow(true);
        }).catch(fail);
    }
  }

  document.addEventListener("keydown", function (ev) {
    if (state.view === "blind-rate") {
      var a = B.keyAction(ev);
      if (!a) return;
      ev.preventDefault();
      return blindKey(a);
    }
    if (state.view !== "focus") return;
    var action = L.keyAction(ev, { modal: state.modal });
    if (!action) return;
    ev.preventDefault();
    act(action);
  });

  if (app && !document.getElementById("login-form")) {
    window.addEventListener("focus", refreshCounts);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) refreshCounts(); });
  }

  var login = document.getElementById("login-form");
  if (login) {
    login.addEventListener("submit", function (ev) {
      ev.preventDefault();
      fetch("/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ token: document.getElementById("token").value }) })
        .then(function (r) { if (r.ok) location.reload(); else document.getElementById("login-msg").textContent = "Refused."; });
    });
  } else if (app) {
    window.addEventListener("hashchange", route);
    route();
  }
})();
