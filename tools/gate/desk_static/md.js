/* Markdown for the review desk: the marked library with one setting, the way tables are drawn.
 * A table with three or more columns becomes one tile per row, every cell under its column heading,
 * because a wide table squeezed into half a screen is unreadable. A table with two columns
 * (field and content) becomes a single tile with one line per row. The result is HTML text; the page
 * cleans it with DOMPurify before use. No DOM access here, so it runs unchanged in Node (node --test). */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DeskMd = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function field(label, value) {
    return '<div class="f"><dt>' + label + "</dt><dd>" + value + "</dd></div>";
  }

  function tile(fields, cls) {
    return '<dl class="tile' + (cls ? " " + cls : "") + '">' + fields.join("") + "</dl>";
  }

  /* lib is the marked library (window.marked); returns a function from Markdown text to HTML text. */
  function create(lib) {
    var md = new lib.Marked({
      gfm: true,
      async: false,
      renderer: {
        table: function (token) {
          var self = this;
          var inline = function (cell) { return self.parser.parseInline(cell.tokens); };
          var heads = token.header.map(inline);
          var rows = token.rows.map(function (r) { return r.map(inline); });
          if (heads.length === 2) {
            return '<div class="tiles">' + tile(rows.map(function (r) { return field(r[0], r[1]); })) + "</div>";
          }
          return '<div class="tiles">' + rows.map(function (r) {
            return tile(r.map(function (v, i) { return field(heads[i] || "", v); }), "row");
          }).join("") + "</div>";
        }
      }
    });
    return function (text) { return md.parse(String(text == null ? "" : text)); };
  }

  return { create: create };
});
