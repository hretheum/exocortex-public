/* Markdown for the review desk: the marked library with one setting, the way tables are drawn.
 * The same rule as the public lab site (lab-site/build.py, table_mode):
 * - "table": at most three columns with short cells stays a table;
 * - "pairs": two columns with longer cells (field and content) become one tile with a line per row;
 * - "tiles": anything wider becomes one tile per row, the first cell as the tile's title (with its column
 *   heading as hidden text for screen readers) and the other cells as "heading: value" pairs in a grid
 *   that folds into one column on a narrow screen.
 * The result is HTML text; the page cleans it with DOMPurify before use. No DOM access here, so it runs
 * unchanged in Node (node --test). */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DeskMd = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var SHORT_CELL = 32;  // characters of plain text; longer cells do not fit a narrow column

  /* "table", "pairs" or "tiles" for a table with these column headings and rows (plain text). */
  function tableMode(heads, rows) {
    var cols = heads.length;
    var cells = heads.concat.apply(heads, rows || []);
    var short = cells.every(function (c) { return String(c == null ? "" : c).trim().length <= SHORT_CELL; });
    if (cols <= 3 && short) return "table";
    if (cols === 2) return "pairs";
    return "tiles";
  }

  function field(label, value) {
    return '<div class="f"><dt>' + label + "</dt><dd>" + value + "</dd></div>";
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
          var plain = function (cell) { return cell.text; };
          var mode = tableMode(token.header.map(plain), token.rows.map(function (r) { return r.map(plain); }));
          if (mode === "table") return false;  // marked draws its own table
          var heads = token.header.map(inline);
          var rows = token.rows.map(function (r) { return r.map(inline); });
          if (mode === "pairs") {
            return '<div class="tiles"><dl class="tile">' + rows.map(function (r) { return field(r[0], r[1]); }).join("") +
              "</dl></div>";
          }
          return '<div class="tiles" role="list">' + rows.map(function (r) {
            var title = '<p class="tile-t">' + (heads[0] ? '<span class="sr">' + heads[0] + ": </span>" : "") + (r[0] || "") + "</p>";
            var rest = r.slice(1).map(function (v, i) { return field(heads[i + 1] || "", v); }).join("");
            return '<section class="tile row" role="listitem">' + title + '<dl class="tile-f">' + rest + "</dl></section>";
          }).join("") + "</div>";
        }
      }
    });
    return function (text) { return md.parse(String(text == null ? "" : text)); };
  }

  return { create: create, tableMode: tableMode, SHORT_CELL: SHORT_CELL };
});
