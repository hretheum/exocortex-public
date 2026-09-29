# Vendored libraries of the review desk

Served by the desk from its own origin (the page loads nothing from another origin). Files are copied
unchanged from the npm packages; the integrity values are those the npm registry publishes for the tarballs.

| File | Package | Version | Licence | Tarball integrity |
|---|---|---|---|---|
| `marked.umd.js` | marked, `lib/marked.umd.js` | 18.0.14 | MIT (`MARKED-LICENSE`) | `sha512-mBHK6FBHuBAlhgRe88w9F0O1AbwwXJUcQibUbC/QcdTbVGAD7aWza+xt3N6oT/jCZx3/OMeS+8rnuiHZcQ9s7A==` |
| `purify.min.js` | dompurify, `dist/purify.min.js` | 3.4.16 | MPL-2.0 or Apache-2.0 (`DOMPURIFY-LICENSE`) | `sha512-sqo+pNp3qRhCIpbgRi1y8Tgk27Bo2Ry7w0dC1NBeNTdZChWjz9Xb/KOoZbRP/R6pQZ80Qw8YhXw13hWWBbMRnQ==` |

marked turns the Markdown of a paragraph into HTML and DOMPurify cleans that HTML before it goes into the
page (see `mdView` in `desk.js`). To update: `npm pack marked dompurify`, compare the integrity, copy the two files.
