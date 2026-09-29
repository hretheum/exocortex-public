/* Exocortex R&D lab site. One reading column, lab-notebook sheets for figures.
   Palette: ink on cool grey, indigo (private), teal (public), amber (gate). Both themes are token-driven. */
:root{/*@@TOKENS_LIGHT@@*/;--font-display:'Bricolage Grotesque','Instrument Sans',system-ui,sans-serif;--font-body:'Instrument Sans',system-ui,-apple-system,'Segoe UI',sans-serif;--font-mono:'JetBrains Mono',ui-monospace,Menlo,monospace;--link:#06695B;--shadow:0 1px 0 rgba(23,32,51,.04);color-scheme:light}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){/*@@TOKENS_DARK@@*/;--link:#5ED8C4;--shadow:none;color-scheme:dark}}
:root[data-theme="dark"]{/*@@TOKENS_DARK@@*/;--link:#5ED8C4;--shadow:none;color-scheme:dark}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font-body);font-size:17px;line-height:1.65}
.wrap.wide{max-width:1080px}
.wrap{max-width:820px;margin-inline:auto;padding-inline:clamp(16px,4vw,32px)}
main.wrap{padding-block:12px 64px}
a{color:var(--link);text-underline-offset:3px}
a:focus-visible,button:focus-visible,summary:focus-visible{outline:3px solid var(--gate);outline-offset:2px;border-radius:4px}
.skip{position:absolute;left:-999px;top:8px;background:var(--surface);color:var(--ink);padding:8px 12px;border-radius:8px;z-index:20}
.skip:focus{left:8px}
.mono{font-family:var(--font-mono);font-size:.86em}
/* header */
.site-h{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.bar{display:flex;flex-wrap:wrap;align-items:center;gap:6px 18px;padding-block:10px}
.brand{font:800 1.05rem/1 var(--font-display);letter-spacing:-.01em;color:var(--ink);text-decoration:none}
.nav{display:flex;flex-wrap:wrap;gap:4px 4px;flex:1 1 auto}
.nav a{font-size:14.5px;color:var(--muted);text-decoration:none;padding:6px 10px;border-radius:999px}
.nav a:hover{color:var(--ink);background:var(--surface)}
.nav a[aria-current="page"]{color:var(--ink);background:var(--surface);box-shadow:inset 0 0 0 1px var(--line)}
.tools{display:flex;align-items:center;gap:10px;margin-left:auto}
.exo{font:600 12.5px/1 var(--font-mono);text-decoration:none;color:var(--muted)}
.exo:hover{color:var(--link)}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:999px;background:var(--surface);padding:3px}
.seg a{font:600 12px/1 var(--font-mono);letter-spacing:.05em;color:var(--muted);text-decoration:none;border-radius:999px;padding:7px 11px}
.seg a[aria-current="true"]{background:var(--priv);color:var(--on)}
.theme{background:var(--surface);border:1px solid var(--line);color:var(--ink);border-radius:999px;width:34px;height:34px;cursor:pointer;font-size:16px;line-height:1}
/* type */
h1{font-family:var(--font-display);font-weight:800;font-size:clamp(2.3rem,8vw,3.6rem);line-height:1.04;letter-spacing:-.02em;margin:34px 0 16px;text-wrap:balance}
h2{font-family:var(--font-display);font-weight:700;font-size:clamp(1.5rem,4.6vw,1.95rem);line-height:1.15;letter-spacing:-.01em;margin:0 0 14px;text-wrap:balance}
h3{font-family:var(--font-display);font-weight:700;font-size:1.08rem;line-height:1.25;margin:22px 0 8px}
p{margin:0 0 1em;max-width:42em}
.lead{font-size:1.2rem;line-height:1.5;max-width:36em;margin:0 0 18px}
.eyebrow{font:500 12.5px/1.4 var(--font-mono);letter-spacing:.08em;text-transform:uppercase;color:var(--pub-x);margin:30px 0 -14px}
.note{font-size:14.5px;color:var(--muted)}
.nerd{margin-block:24px 8px;padding:4px 20px 8px;border:1px dashed var(--line);border-radius:12px;background:var(--surface);font-size:15.5px}
.nerd h3{font:600 12px/1.4 var(--font-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-block:14px 6px}
.more{margin-top:12px}
.more a,.hyp .more a{font-weight:600;text-decoration:none}
section{padding-block:30px 4px;scroll-margin-top:70px}
.hero{padding-block:8px 6px}
.cta{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0 0}
.btn{display:inline-block;font:600 15px/1 var(--font-body);text-decoration:none;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:13px 18px}
.btn:hover{border-color:var(--pub)}
.btn.primary{background:var(--priv);border-color:var(--priv);color:var(--on)}
.principles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;padding-block:26px 0}
.pr{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:16px 18px}
.pr h3{margin:0 0 6px}
.pr p{margin:0;font-size:15.5px;color:var(--muted)}
.origin p{color:var(--muted)}
/* figures */
.fig{margin:24px 0 28px}
.sheet{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:clamp(10px,3vw,20px);box-shadow:var(--shadow)}
svg.ig{display:block;width:100%;max-width:520px;height:auto;margin-inline:auto}
figcaption{font-size:13.5px;line-height:1.5;color:var(--muted);margin-top:10px;max-width:40em}
/* hypothesis cards, pills */
.hyps{display:grid;gap:12px;margin:12px 0 18px}
.hyp{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:16px 18px}
.hyp-h{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin-bottom:8px}
.hyp-h h3{flex:1 1 12em;min-width:0;margin:0}
.hyp-h h3 a{color:var(--ink);text-decoration:none}
.hyp-h h3 a:hover{color:var(--link)}
.hyp p{margin:0 0 10px;font-size:15.5px;line-height:1.55}
.hyp .more{margin:12px 0 0}
.code{font:700 13px/1 var(--font-mono);color:var(--on);background:var(--priv);border-radius:8px;padding:7px 9px}
.pill{display:inline-block;font:600 12px/1 var(--font-mono);border-radius:999px;padding:7px 12px;white-space:nowrap}
.pill.prep{background:var(--gate-t);color:var(--gate-x);border:1.2px solid var(--gate)}
.pill.ok{background:var(--ok-t);color:var(--ok-x);border:1.2px solid var(--ok)}
.pill.plan{color:var(--muted);border:1.2px dashed var(--muted)}
.track{list-style:none;display:flex;gap:0;margin:8px 0 6px;padding:0}
.track li{flex:1 1 0;min-width:0;position:relative;text-align:center;font:500 11px/1.3 var(--font-mono);color:var(--muted);padding-top:22px}
.track li::before{content:"";position:absolute;left:0;right:0;top:8px;height:3px;background:var(--line)}
.track li:first-child::before{left:50%}
.track li:last-child::before{right:50%}
.track .dot{position:absolute;left:50%;top:1px;width:16px;height:16px;margin-left:-8px;border-radius:50%;background:var(--surface);border:2px solid var(--line);z-index:1}
.track li.done::before{background:var(--ok)}
.track li.done .dot{background:var(--ok);border-color:var(--ok)}
.track li.cur .dot{background:var(--gate-t);border-color:var(--gate);border-width:3px}
.track li.cur{color:var(--gate-x);font-weight:700}
.track li.done{color:var(--ok-x)}
@media (max-width:520px){.track li{font-size:9.5px;letter-spacing:-.01em}}
/* tables */
.tw{overflow-x:auto;margin:14px 0 20px;border:1px solid var(--line);border-radius:14px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:15px;line-height:1.5}
th,td{text-align:left;vertical-align:top;padding:10px 14px;border-bottom:1px solid var(--line)}
thead th{font:600 12px/1.3 var(--font-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);white-space:nowrap}
tbody tr:last-child td,tbody tr:last-child th{border-bottom:0}
td.r{text-align:right;white-space:nowrap}
table.files td.sha{font-size:11.5px;word-break:break-all;min-width:16rem;color:var(--muted)}
.tw table{min-width:30rem}
/* details / faq */
details.faqi{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:0 16px;margin-bottom:8px}
details.faqi[open]{border-color:var(--pub)}
details summary{cursor:pointer;font-weight:600;padding-block:13px}
details.faqi p{font-size:16px;margin:0 0 14px}
/* toc */
.toc{display:flex;flex-wrap:wrap;gap:8px;margin:22px 0 6px;padding-top:16px;border-top:1px solid var(--line)}
.toc a{font-size:13.5px;line-height:1;text-decoration:none;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:9px 13px}
.toc a:hover{border-color:var(--pub);color:var(--link)}
/* dossier */
.dh .lead{margin-bottom:10px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px 18px;margin:18px 0 8px;padding:16px 18px;background:var(--surface);border:1px solid var(--line);border-radius:16px}
.facts dt{font:500 11px/1.3 var(--font-mono);letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin-bottom:3px}
.facts dd{margin:0;font-size:15px;font-weight:600}
.dgrid{display:grid;grid-template-columns:minmax(0,1fr);gap:8px 32px;margin-top:8px}
.dtoc{order:-1}
.dtoc ol{margin:6px 0 0;padding-left:1.2em;font-size:14.5px}
.dtoc li{margin:3px 0}
.dtoc a{text-decoration:none;color:var(--ink)}
.dtoc a:hover{color:var(--link)}
.tocd{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:0 16px 10px}
.dsec h2 .n{display:inline-block;min-width:1.7em;font:600 .7em/1 var(--font-mono);color:var(--muted);vertical-align:.12em}
.dsec{padding-block:26px 2px;border-top:1px solid var(--line);margin-top:6px}
.dsec:first-of-type{border-top:0}
.dsec ul,.dsec ol{max-width:42em;padding-left:1.3em}
.dsec li{margin:.3em 0}
code{font-family:var(--font-mono);font-size:.86em;background:color-mix(in srgb,var(--line) 45%,transparent);border-radius:5px;padding:.1em .35em;word-break:break-word}
pre{font-family:var(--font-mono);font-size:13px;line-height:1.55;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;overflow-x:auto;margin:0 0 14px;white-space:pre-wrap;word-break:break-word}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 18px;margin:14px 0}
.items{display:grid;gap:8px}
.panel h1,.panel h2,.items h1,.items h2{font-size:1.1rem;margin:14px 0 8px}
td.mono{white-space:nowrap}
details.item{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:0 16px 8px}
.bib-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.copy{font:600 12px/1 var(--font-mono);background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 12px;cursor:pointer}
@media (min-width:1000px){
  .dgrid{grid-template-columns:220px minmax(0,1fr)}
  .dtoc{order:0;position:sticky;top:76px;align-self:start}
  .tocd{padding:0 0 6px;border:0;background:transparent}
  .tocd summary{pointer-events:none;list-style:none;font:500 11px/1.3 var(--font-mono);letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
  .tocd summary::-webkit-details-marker{display:none}
}
/* status */
.phases{display:grid;gap:10px;margin-top:14px}
details.phase{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:0 16px 6px}
details.phase>summary{display:grid;grid-template-columns:auto 1fr auto;gap:8px 12px;align-items:center;list-style:none;padding-block:14px}
details.phase>summary::-webkit-details-marker{display:none}
details.phase .pt{font:700 1rem/1.25 var(--font-display)}
details.phase .pbar{grid-column:1 / 3;height:7px;border-radius:4px;background:var(--line);overflow:hidden;display:block}
details.phase .pbar i{display:block;height:100%;background:var(--ok)}
details.phase .cnt{grid-column:3;justify-self:end;color:var(--muted)}
details.phase p{font-size:15px}
.repo-pending{border-bottom:1px dashed var(--muted);cursor:help}
/* footer */
.site-f{border-top:1px solid var(--line);padding-block:22px 34px;color:var(--muted);font-size:14px}
.site-f p{margin:0 0 6px}
.site-f .meta{font:500 12.5px/1.6 var(--font-mono)}
@media (max-width:640px){.tools{margin-left:0;width:100%;justify-content:space-between}.exo{order:3}}
/*@@IG@@*/
