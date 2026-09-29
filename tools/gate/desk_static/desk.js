/* Review desk page script. Every piece of text goes into the page with textContent,
 * never as markup. Nothing is loaded from another origin. */
(function () {
  "use strict";
  var L = window.DeskLogic;
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
  function mdView(text) {
    var box = h("div", { class: "md" });
    var html = window.marked.parse(String(text == null ? "" : text), { gfm: true, async: false });
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
        return j;
      });
    });
  }

  var app = document.getElementById("app");
  var hdr = document.getElementById("hdr");
  var state = { view: "queue", unit: null, findings: [], skipped: [], current: null, card: null, modal: false, msg: "" };

  function say(text) { state.msg = text || ""; var m = document.getElementById("msg"); if (m) m.textContent = state.msg; }
  function fail(e) { say(e.message); }

  function nav() {
    hdr.textContent = "";
    hdr.appendChild(h("strong", {}, "Review desk"));
    [["queue", "Queue"], ["rules", "Rules"], ["history", "History"]].forEach(function (v) {
      hdr.appendChild(h("button", { class: "nav" + (state.view === v[0] ? " on" : ""), onclick: function () { go(v[0]); } }, v[1]));
    });
    if (state.view === "focus") {
      var p = L.progress(state.findings);
      hdr.appendChild(h("span", { class: "progress", id: "progress" }, state.unit.cls + ":" + state.unit.key + " · " + p.text));
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
    var m = /^#\/unit\/(\d+)$/.exec(location.hash || "");
    if (m) return showUnit(Number(m[1]));
    if (location.hash === "#/rules") { state.view = "rules"; return rules(); }
    if (location.hash === "#/history") { state.view = "history"; return history(); }
    state.view = "queue";
    return queue();
  }

  function table(head, rows) {
    return h("table", {}, h("thead", {}, h("tr", {}, head.map(function (t) { return h("th", {}, t); }))),
             h("tbody", {}, rows));
  }

  function queue() {
    api("GET", "/api/units").then(function (r) {
      nav(); app.textContent = "";
      if (!r.units.length) { app.appendChild(h("p", {}, "The quarantine is empty.")); return; }
      app.appendChild(table(["Unit", "Class", "Findings", "State", "Age (days)"], r.units.map(function (u) {
        return h("tr", { class: "row", tabindex: "0", onclick: function (e) { if (!(e && e.target && e.target.tagName === "A")) openUnit(u.id); },
                         onkeydown: function (e) { if (e.key === "Enter") openUnit(u.id); } },
          h("td", {}, h("a", { href: "#/unit/" + u.id }, u.key)), h("td", {}, u.cls), h("td", {}, u.findings + " (" + u.counts.open + " open, " + u.counts.to_edit + " to edit)"),
          h("td", {}, u.state), h("td", {}, u.age_days));
      })));
    }).catch(fail);
  }

  function openUnit(id) { navigate("#/unit/" + id); }

  function showUnit(id) {
    api("GET", "/api/units/" + id).then(function (r) {
      state.view = "focus"; state.unit = r.unit; state.findings = r.findings; state.bulk = r.bulk; state.skipped = [];
      state.current = L.nextFocus(r.findings, [], null).id;
      focus();
    }).catch(fail);
  }

  function reload(keepFocus) {
    return api("GET", "/api/units/" + state.unit.id).then(function (r) {
      state.unit = r.unit; state.findings = r.findings; state.bulk = r.bulk;
      var cur = keepFocus ? state.current : null;
      state.current = L.nextFocus(r.findings, state.skipped, cur).id;
      focus();
    });
  }

  function focus() {
    state.card = null; nav(); app.textContent = "";
    var done = state.findings.filter(function (f) { return f.state === "kept" || f.state === "to_edit"; });
    var list = h("ul", { class: "decided" }, done.map(function (f) { return h("li", { class: "line " + f.state }, L.collapsedLine(f)); }));
    app.appendChild(list);
    var cur = state.findings.find(function (f) { return f.id === state.current; });
    if (!cur) {
      app.appendChild(h("p", { class: "done" }, state.unit.state === "released" ? "Nothing left to decide: the unit is released." :
        "Nothing left to decide here. Findings marked to edit keep the unit held until the source changes."));
      app.appendChild(bulkBar(null));
      return;
    }
    app.appendChild(h("div", { id: "card", class: "card" }, "Loading…"));
    app.appendChild(bulkBar(cur));
    api("GET", "/api/findings/" + cur.id + "/card").then(function (c) { state.card = c; renderCard(cur, c); }).catch(fail);
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
    var left = h("section", { class: "pane" }, h("h3", {}, "Public paragraph"), h("div", { class: "meta" }, f.path + " \u00b7 " + f.rule + " \u00b7 " + f.score.toFixed(3)),
      c.public === null ? h("p", { class: "meta" }, "(the paragraph is no longer in the source)") : mdView(c.public));
    var right = h("section", { class: "pane" }, h("h3", {}, "Nearest protected paragraphs"),
      c.neighbours.length ? c.neighbours.map(function (n) { return neighbour(n); }) : h("p", {}, "No neighbour to show."));
    el.appendChild(h("div", { class: "topbar" }, actionsBlock(f, noteTop), bulkBar(f)));
    el.appendChild(h("div", { class: "cols" }, left, right));
    el.appendChild(h("p", { class: "hint" }, "Hint: " + c.hint));
    el.appendChild(actionsBlock(f, noteBottom));
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

  function act(action) {
    var f = state.findings.find(function (x) { return x.id === state.current; });
    if (action === "skip") { var n = L.skip(state.findings, state.skipped, state.current); state.skipped = n.skipped; state.current = n.id; return focus(); }
    if (action === "undo") {
      return api("POST", "/api/undo", {}).then(function (r) {
        say(r.undone ? "Undone" : "Nothing to undo"); if (r.undone && r.undone.findings.length) state.current = r.undone.findings[0];
        return api("GET", "/api/units/" + state.unit.id).then(function (u) {
          state.unit = u.unit; state.findings = u.findings; state.bulk = u.bulk; focus();
        });
      }).catch(fail);
    }
    var ok = L.canAct(action, f);
    if (!ok.ok) return say(ok.reason);
    var noteEl = document.getElementById("note");
    api("POST", "/api/findings/" + f.id + "/decide", { decision: action, note: action === "to_edit" && noteEl && noteEl.value ? noteEl.value : null })
      .then(function () { say(""); return reload(true); }).catch(fail);
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
          .then(function () { state.modal = false; say("Kept"); return reload(false); }).catch(fail);
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

  document.addEventListener("keydown", function (ev) {
    if (state.view !== "focus") return;
    var action = L.keyAction(ev, { modal: state.modal });
    if (!action) return;
    ev.preventDefault();
    act(action);
  });

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
