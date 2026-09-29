# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Generator of the six Exocortex Lab infographics (PL and EN, light and dark).

One layout, two text tables. Output: inline SVG strings (for the page, styled by
the page's CSS) and standalone SVG files (self-contained style, follows the OS theme).
Every text carries data-x0/data-x1 (allowed horizontal extent) so a headless render
can check that nothing overflows its card.
"""
from __future__ import annotations

from html import escape

W = 520
M = 16  # outer margin

# ---------------------------------------------------------------- style ----
TOKENS_LIGHT = {
    "bg": "#F3F5F8", "surface": "#FFFFFF", "ink": "#172033", "muted": "#566079", "line": "#CBD3E0",
    "priv": "#3B4A78", "priv-t": "#E3E8F6", "priv-x": "#2F3D68",
    "pub": "#0B8A78", "pub-t": "#DAF2EE", "pub-x": "#06695B",
    "gate": "#C77700", "gate-t": "#FCEFD2", "gate-x": "#8A5200",
    "ok": "#2B8A4B", "ok-t": "#DDF2E4", "ok-x": "#1E6B38",
    "on": "#FFFFFF",
}
TOKENS_DARK = {
    "bg": "#0E1320", "surface": "#161D2E", "ink": "#E9EDF6", "muted": "#A4AEC6", "line": "#2E3852",
    "priv": "#93A6E8", "priv-t": "#1E2746", "priv-x": "#B3C0F0",
    "pub": "#3CC7B1", "pub-t": "#12393A", "pub-x": "#5ED8C4",
    "gate": "#F0B429", "gate-t": "#3A2F10", "gate-x": "#F5C65A",
    "ok": "#55C17C", "ok-t": "#163A25", "ok-x": "#7BD69A",
    "on": "#0E1320",
}

KINDS = ["priv", "pub", "gate", "ok"]


def class_rules() -> str:
    r = [".ig .f-bg{fill:var(--bg)}.ig .f-surf{fill:var(--surface)}.ig .f-ink{fill:var(--ink)}",
         ".ig .f-mut{fill:var(--muted)}.ig .f-on{fill:var(--on)}.ig .f-line{fill:var(--line)}",
         ".ig .s-line{stroke:var(--line)}.ig .s-mut{stroke:var(--muted)}.ig .s-ink{stroke:var(--ink)}.ig .s-on{stroke:var(--on)}",
         ".ig .nf{fill:none}",
         ".ig .tb{font-family:var(--font-body,'Instrument Sans',system-ui,-apple-system,'Segoe UI',sans-serif)}",
         ".ig .td{font-family:var(--font-display,'Bricolage Grotesque','Instrument Sans',system-ui,sans-serif)}",
         ".ig .tm{font-family:var(--font-mono,'JetBrains Mono',ui-monospace,Menlo,monospace)}"]
    for k in KINDS:
        r.append(f".ig .f-{k}{{fill:var(--{k})}}.ig .f-{k}t{{fill:var(--{k}-t)}}.ig .f-{k}x{{fill:var(--{k}-x)}}"
                 f".ig .s-{k}{{stroke:var(--{k})}}.ig .s-{k}x{{stroke:var(--{k}-x)}}")
    return "\n".join(r)


def token_block(tokens: dict) -> str:
    return ";".join(f"--{k}:{v}" for k, v in tokens.items())


def standalone_style() -> str:
    return (f".ig{{{token_block(TOKENS_LIGHT)}}}\n"
            f"@media (prefers-color-scheme: dark){{.ig{{{token_block(TOKENS_DARK)}}}}}\n" + class_rules())


# ---------------------------------------------------------------- canvas ---
class Canvas:
    def __init__(self, fig: str, h: int):
        self.fig, self.h, self.parts = fig, h, []

    def add(self, s: str) -> None:
        self.parts.append(s)

    # shapes
    def rect(self, x, y, w, h, fill="f-surf", stroke="s-line", rx=14, sw=1.5, dash=None, extra=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        st = f' class="{fill} {stroke}" stroke-width="{sw}"' if stroke else f' class="{fill}"'
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"{st}{d}{extra}/>')

    def card(self, kind, x, y, w, h):
        if kind == "plain":
            self.rect(x, y, w, h)
        else:
            self.rect(x, y, w, h, fill=f"f-{kind}t", stroke=f"s-{kind}")

    def text(self, x, y, lines, size=15, weight=400, cls="f-ink", anchor="start", lh=1.36, font="tb", box=None):
        if isinstance(lines, str):
            lines = [lines]
        if box is None:
            box = (x, x + 400) if anchor == "start" else (x - 200, x + 200)
        tsp = "".join(f'<tspan x="{x}" dy="{0 if i == 0 else round(size * lh, 1)}">{escape(t)}</tspan>'
                      for i, t in enumerate(lines))
        self.add(f'<text x="{x}" y="{y}" class="{cls} {font}" font-size="{size}" font-weight="{weight}" '
                 f'text-anchor="{anchor}" data-x0="{box[0]}" data-x1="{box[1]}" data-y1="{self.h}">{tsp}</text>')

    def icon(self, name, x, y, s, cls):
        self.add(f'<g transform="translate({x} {y}) scale({round(s / 24, 4)})" class="nf {cls}" stroke-width="1.9" '
                 f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')

    def badge(self, kind, cx, cy, r, icon):
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" class="f-{kind}"/>')
        self.icon(icon, cx - r * 0.55, cy - r * 0.55, r * 1.1, "s-on")

    def chip(self, x, y, w, label, kind="plain", icon=None, size=13.5, h=30):
        if w is None:
            w = round(32 + len(label) * size * 0.68 + 16)
        if kind == "plain":
            self.rect(x, y, w, h, rx=h / 2, sw=1.2)
            fill_cls = "f-ink"
        else:
            self.rect(x, y, w, h, fill=f"f-{kind}t", stroke=f"s-{kind}", rx=h / 2, sw=1.2)
            fill_cls = f"f-{kind}x"
        tx = x + 12
        if icon:
            self.icon(icon, x + 10, y + (h - 16) / 2, 16, f"s-{kind}x" if kind != "plain" else "s-ink")
            tx = x + 32
        self.text(tx, y + h / 2 + size * 0.34, label, size=size, weight=600, cls=fill_cls, box=(tx, x + w - 6))

    def arrow(self, x1, y1, x2, y2, dash=None, cls="s-mut"):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}" stroke-width="2" '
                 f'stroke-linecap="round" marker-end="url(#{self.fig}-ar)"{d}/>')

    def path(self, d, cls="s-mut", dash=None, marker=True):
        m = f' marker-end="url(#{self.fig}-ar)"' if marker else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<path d="{d}" class="nf {cls}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"{m}{da}/>')

    def wall(self, x, y, w, h):
        self.rect(x, y, w, h, fill="f-surf", stroke="s-line", rx=6, sw=1.2)
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="url(#{self.fig}-hatch)" class="s-line"/>')

    def render(self, title: str, standalone: bool) -> str:
        defs = (f'<defs><marker id="{self.fig}-ar" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" '
                f'markerHeight="7" orient="auto-start-reverse"><path d="M1 1.2L9 5L1 8.8z" class="f-mut"/></marker>'
                f'<pattern id="{self.fig}-hatch" width="9" height="9" patternUnits="userSpaceOnUse" '
                f'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="9" stroke="currentColor" '
                f'stroke-width="2.4" class="s-line"/></pattern></defs>')
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {self.h}" class="ig" role="img" '
                f'aria-label="{escape(title, quote=True)}" width="{W}" height="{self.h}">')
        style = f"<style>{standalone_style()}</style>" if standalone else ""
        ttl = f"<title>{escape(title)}</title>" if standalone else ""
        bg = f'<rect width="{W}" height="{self.h}" class="f-bg"/>' if standalone else ""
        return head + ttl + style + defs + bg + "".join(self.parts) + "</svg>"


ICONS = {
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2.2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "doc": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
    "docs": '<path d="M4 5h8l3 3v11H4z"/><path d="M12 5v3h3"/><path d="M9 3h8l3 3v11"/>',
    "shield": '<path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/><path d="M9 12l2.2 2.2L15.5 10"/>',
    "person": '<circle cx="12" cy="8" r="3.6"/><path d="M5 20c0-4 3-6 7-6s7 2 7 6"/>',
    "db": '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3.2 3.2 3.2 14.8 0 18M12 3c-3.2 3.2-3.2 14.8 0 18"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5"/>',
    "flask": '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3"/><path d="M7.5 15h9"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "pause": '<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "seal": '<circle cx="12" cy="10" r="6.5"/><path d="M9.3 10l2 2 3.6-4"/><path d="M8.5 15.5L7 21l5-2.5 5 2.5-1.5-5.5"/>',
    "server": '<rect x="4" y="4" width="16" height="7" rx="2"/><rect x="4" y="13" width="16" height="7" rx="2"/><path d="M8 7.5h.01M8 16.5h.01"/>',
    "net": '<circle cx="12" cy="12" r="3"/><path d="M12 3v6M12 15v6M3 12h6M15 12h6"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "eye": '<path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.8"/>',
    "repeat": '<path d="M4 11V9a3 3 0 0 1 3-3h11M15 3l3 3-3 3M20 13v2a3 3 0 0 1-3 3H6M9 21l-3-3 3-3"/>',
}


# ---------------------------------------------------------------- texts ----
T = {
    "pl": {
        "f1": dict(
            alt="Schemat: laboratorium czyta tylko źródła publiczne, wyniki przechodzą przez bramkę publikacji do publicznego repozytorium, a dane prywatne i klienckie są za murem, poza laboratorium.",
            src_t="Źródła publiczne", src_s=["Prace naukowe, otwarte dane", "i nasze własne teksty."],
            src_arrow="Tylko z listy dozwolonych",
            lab_t="Laboratorium", lab_s=["Testuje pomysły dotyczące AI.", "Każdy krok zapisuje na widoku."],
            gate="Bramka publikacji", arrow=["Co 15 minut, po sprawdzeniu", "każdego pliku"],
            repo_t="Publiczne repozytorium", repo_s=["Hipotezy, wyniki, plan.", "Każdy może zajrzeć."],
            out_t="Poza laboratorium", out_s=["Dane prywatne i klienckie.", "Osobny świat, bez połączenia."]),
        "f2": dict(
            alt="Schemat: nowy dokument przechodzi pięć kontroli. Jeśli wszystkie się powiodą, trafia do repozytorium, jeśli nie, czeka na decyzję człowieka.",
            doc_t="Nowy dokument", doc_s="po polsku i po angielsku",
            checks=[("Zakazane nazwy i dane osobowe", "Skaner zagląda też w ukryte dane plików."),
                    ("Podobieństwo do prywatnych notatek", "Odpowiedź brzmi tylko: podobne albo nie."),
                    ("Wersje PL i EN się zgadzają", "Te same liczby, nagłówki, linki i tabele."),
                    ("Poprawna budowa pliku", "Nagłówek zgodny ze schematem."),
                    ("Tekst pisany po ludzku", "Bez nawyków typowych dla modeli AI.")],
            ok_t="Wszystko przeszło", ok_s=["Plik trafia do repozytorium.", "Publikacja co 15 minut."],
            hold_t="Coś zatrzymało", hold_s=["Plik czeka, autor dostaje", "powiadomienie z powodem.", "Decyduje człowiek."],
            test_t="Co noc: test samej bramki",
            test_s=["Podrzucamy celowe wycieki. Każdy musi zostać", "zatrzymany, inaczej publikacja staje."]),
        "f3": dict(
            alt="Schemat: droga hipotezy w siedmiu krokach, od sygnału, przez kartę hipotezy zamrożoną przed pomiarem i dwie bramki, do planu dla dużej organizacji.",
            legend="człowiek decyduje",
            nodes=[("Sygnał", ["Co tydzień: nowe prace, modele i dane", "publiczne. Powstaje lista kandydatów."], False, None),
                   ("Wybór", ["Pięć pytań odrzucających: po co, czy są dane,", "czy to legalne, czy da się zmierzyć, czy nie", "da się prościej bez AI."], True, None),
                   ("Karta hipotezy", ["Co sprawdzamy i co by nas obaliło.", "Zamrożona i opublikowana przed pierwszym", "pomiarem, żeby nikt nie dopasował metody."], True, "seal"),
                   ("Szybki test", ["Lokalne modele, mała próba, od kilku godzin", "do dwóch dni. Część próby zostaje zamknięta", "do samego końca."], False, "S"),
                   ("Bramka", ["Wynik kontra próg z karty. Idziemy dalej,", "kończymy, zmieniamy hipotezę albo odkładamy.", "Wynik negatywny też publikujemy."], True, None),
                   ("Pilot", ["Większa próba, ocena na ślepo przez ludzi,", "spis typowych błędów, koszt i czas.", "Na końcu druga bramka."], True, "M"),
                   ("Plan dla dużej organizacji", ["Tylko dokument, bez wdrożenia. Liczby w nim", "pochodzą z pomiarów pilota."], False, "L")],
            foot=["Każdy krok zostawia plik w repozytorium. Z tych plików", "powstają strony wynikowe i karta projektu."]),
        "f4": dict(
            alt="Schemat: cztery hipotezy i ich etap na drodze od kandydata do raportu. Jedna jest w przygotowaniu, trzy są planowane.",
            stages=["Kandydat", "Karta", "Test", "Bramka", "Pilot", "Raport"],
            status={"prep": "Przygotowanie", "run": "W toku", "done": "Rozstrzygnięta", "plan": "Planowana"},
            rows=[("F3", "Zamiar czy fakt", "Korpus gotowy. Karta hipotezy przed nami.", "prep", 1),
                  ("F5.5", "Graf a wyszukiwanie", "Czy powiązania poprawiają wyniki.", "plan", 0),
                  ("F5.6", "Model lokalny czy chmurowy", "Czy lokalny nie ustępuje chmurowemu.", "plan", 0),
                  ("F5.7", "Wymuszony format odpowiedzi", "Czy struktura eliminuje odpowiedzi prozą.", "plan", 0)],
            foot=["Zielona kropka: etap za nami. Bursztynowa: etap przed nami.", "Pusta: jeszcze nie rozpoczęty."]),
        "f5": dict(
            alt="Schemat: architektura w pięciu warstwach. Źródła publiczne wchodzą przez listę dozwolonych do laboratorium z czterema modułami, wyniki przechodzą przez bramkę publikacji do publicznego repozytorium.",
            src_t="Źródła publiczne", src_s="Prace naukowe, otwarte dane, nasze dokumenty.",
            allow="Lista dozwolonych źródeł",
            lab_t="Laboratorium",
            mods=[("Graf wiedzy", ["Twierdzenia i powiązania", "wyciągnięte z tekstów"], "net"),
                  ("Modele lokalne", ["Działają lokalnie,", "bez chmury"], "server"),
                  ("Pomiary", ["Ta sama próba,", "wiele konfiguracji"], "flask"),
                  ("Zapis cyklu", ["Karty, przebiegi,", "decyzje z bramek"], "doc")],
            every="Co 15 minut",
            gate_t="Bramka publikacji", gate_s="Pięć kontroli i test co noc.",
            repo_t="Publiczne repozytorium",
            outs=[("Dokumentacja i stan prac", "ok"), ("Karty hipotez i wyniki", "plain"),
                  ("Strona projektu", "plain"), ("Karta projektu referencyjnego", "plain")],
            foot=["Zielone działa, pozostałe planujemy. Pełny stan", "prac pokazuje ostatni rysunek."]),
        "f6": dict(
            alt="Schemat: dwa oddzielone światy, prywatny i laboratorium. Do laboratorium wchodzą tylko źródła z listy dozwolonych, a co noc test sprawdza izolację.",
            server="Dwa osobne światy",
            priv_t=["Świat", "prywatny"], priv_s=["Dane prywatne", "i klienckie."],
            lab_t="Laboratorium", chips=["Własna baza danych", "Osobna, zamknięta sieć", "Dokumenty, tylko odczyt"],
            note=["Między nimi nie ma", "żadnej drogi, nawet", "po pomyłce w", "ustawieniach."],
            src_t="Lista dozwolonych źródeł", src_s="Nowe źródło to wpis z uzasadnieniem i podstawą prawną.",
            allowed=["Nasze dokumenty", "Abstrakty z arXiv (CC0)"], denied=["Poczta", "Notatki klientów"],
            test_t="Co noc: test izolacji",
            test_s=["Z wnętrza laboratorium próbujemy dotrzeć do prywatnej", "bazy każdym znanym adresem. Wszystkie próby muszą", "się nie udać, a prywatnych folderów nie widać."]),
        "f7": dict(
            alt="Schemat: czterostopniowa ścieżka dowodowa, od zapowiedzi, przez dane i wynik, do raportu. Każdy może powtórzyć kroki drugi i trzeci.",
            steps=[("Zapowiedź", ["Karta hipotezy z datą i sumą kontrolną,", "opublikowana przed pomiarem."]),
                   ("Dane", ["Lista artykułów z sumami kontrolnymi.", "Każdy może pobrać te same teksty."]),
                   ("Wynik", ["Surowe liczby i skrypt, który je wylicza."]),
                   ("Raport", ["Każde zdanie wskazuje plik albo wiersz danych.", "Liczba bez źródła nie wchodzi do raportu."])],
            you_t="Sprawdzasz sam", you_s=["Pobierasz dane (2), uruchamiasz skrypt (3)", "i porównujesz liczby z raportem (4)."]),
        "f8": dict(
            alt="Schemat: sześć faz roadmapy. Laboratorium i pierwszy eksperyment są w budowie, cztery pozostałe fazy są planowane.",
            date="Stan na 28 września 2026",
            status={"live": "Działa", "wip": "W budowie", "plan": "Planowane"},
            rows=[("F2", "Laboratorium", "Baza, izolacja, lista źródeł gotowe.", "wip", 3, 8),
                  ("F3", "Pierwszy eksperyment", "Korpus gotowy, pomiary jeszcze nie.", "wip", 1, 10),
                  ("F4", "Karta projektu referencyjnego", "Składana z zapisanych wyników.", "plan", 0, 4),
                  ("F5", "Radar i kolejne eksperymenty", "Cotygodniowy przegląd źródeł.", "plan", 0, 7),
                  ("F6", "Skala i współpraca", "Drugi ekspert, strona, archiwum z DOI.", "plan", 0, 6),
                  ("F7", "Publiczne demo", "Baza wiedzy zasilana badaniami.", "plan", 0, 6)],
            foot=["Pasek pokazuje, ile zadań fazy jest gotowych."]),
    },
    "en": {
        "f1": dict(
            alt="Diagram: the lab reads only public sources, results pass through the publishing gate into the public repository, and private and client data sit behind a wall, outside the lab.",
            src_t="Public sources", src_s=["Papers, open data", "and our own texts."],
            src_arrow="Only from the allowlist",
            lab_t="The lab", lab_s=["Tests ideas about AI.", "Every step is recorded in the open."],
            gate="Publishing gate", arrow=["Every 15 minutes, after every", "file has been checked"],
            repo_t="Public repository", repo_s=["Hypotheses, results, plan.", "Anyone can look."],
            out_t="Outside the lab", out_s=["Private and client data.", "A separate world, no link."]),
        "f2": dict(
            alt="Diagram: a new document passes five checks. If all pass, it goes into the repository; if not, it waits for a person to decide.",
            doc_t="New document", doc_s="in Polish and in English",
            checks=[("Banned names and personal data", "The scanner also looks in hidden file data."),
                    ("Similarity to private notes", "The answer is only: similar or not."),
                    ("Polish and English versions agree", "Same numbers, headings, links and tables."),
                    ("Valid file structure", "The header matches its schema."),
                    ("Text written like a person", "None of the habits typical of AI models.")],
            ok_t="All clear", ok_s=["Goes into the repository.", "Published every 15 minutes."],
            hold_t="Held back", hold_s=["The file waits, the author gets", "a notice with the reason.", "A person decides."],
            test_t="Every night: a test of the gate itself",
            test_s=["We plant deliberate leaks. Every one must be", "stopped, or publishing stops."]),
        "f3": dict(
            alt="Diagram: the path of a hypothesis in seven steps, from a signal, through a hypothesis card frozen before measurement and two gates, to a plan for a large organisation.",
            legend="a person decides",
            nodes=[("Signal", ["Every week: new papers, models and public", "data. A list of candidates comes out."], False, None),
                   ("Selection", ["Five screening questions: why, is there data,", "is it legal, can it be measured, is there", "a simpler way without AI."], True, None),
                   ("Hypothesis card", ["What we test and what would prove us wrong.", "Frozen and published before the first", "measurement, so nobody can tune the method."], True, "seal"),
                   ("Quick test", ["Local models, a small sample, a few hours", "to two days. Part of the sample stays sealed", "until the very end."], False, "S"),
                   ("Gate", ["The result against the threshold in the card.", "Continue, stop, change the hypothesis or park it.", "Negative results are published too."], True, None),
                   ("Pilot", ["A larger sample, blind rating by people,", "a list of typical errors, cost and time.", "A second gate at the end."], True, "M"),
                   ("Plan for a large organisation", ["A document only, no rollout. The numbers in it", "come from the pilot measurements."], False, "L")],
            foot=["Every step leaves a file in the repository. Result pages", "and the project card are built from those files."]),
        "f4": dict(
            alt="Diagram: four hypotheses and their stage on the path from candidate to report. One is in preparation, three are planned.",
            stages=["Candidate", "Card", "Test", "Gate", "Pilot", "Report"],
            status={"prep": "In preparation", "run": "Running", "done": "Decided", "plan": "Planned"},
            rows=[("F3", "Intent or fact", "Corpus ready. Hypothesis card is next.", "prep", 1),
                  ("F5.5", "Graph and search", "Do connections improve results.", "plan", 0),
                  ("F5.6", "Local or cloud model", "Is local as good as cloud.", "plan", 0),
                  ("F5.7", "Enforced answer format", "Does structure end prose answers.", "plan", 0)],
            foot=["Green dot: stage behind us. Amber: stage ahead of us.", "Empty: not started yet."]),
        "f5": dict(
            alt="Diagram: the architecture in five layers. Public sources enter the lab, which has four modules, through the allowlist, and results pass through the publishing gate into the public repository.",
            src_t="Public sources", src_s="Papers, open data, our own documents.",
            allow="Allowlist of sources",
            lab_t="The lab",
            mods=[("Knowledge graph", ["Claims and connections", "extracted from texts"], "net"),
                  ("Local models", ["Run locally,", "no cloud"], "server"),
                  ("Measurement", ["The same sample,", "many configurations"], "flask"),
                  ("Cycle record", ["Cards, runs,", "gate decisions"], "doc")],
            every="Every 15 minutes",
            gate_t="Publishing gate", gate_s="Five checks and a test every night.",
            repo_t="Public repository",
            outs=[("Documentation and progress", "ok"), ("Hypothesis cards and results", "plain"),
                  ("Project site", "plain"), ("Reference project card", "plain")],
            foot=["Green works, the rest is planned. The full state", "of the work is in the last diagram."]),
        "f6": dict(
            alt="Diagram: two separate worlds, private and the lab. Only sources from the allowlist enter the lab, and a nightly test checks the isolation.",
            server="Two separate worlds",
            priv_t=["The private", "world"], priv_s=["Private and client", "data."],
            lab_t="The lab", chips=["Its own database", "Its own closed network", "Documents, read-only"],
            note=["There is no road", "between them, even", "after a slip in", "the settings."],
            src_t="Allowlist of sources", src_s="A new source is an entry with a reason and a legal basis.",
            allowed=["Our own documents", "arXiv abstracts (CC0)"], denied=["Email", "Client notes"],
            test_t="Every night: an isolation test",
            test_s=["From inside the lab we try to reach the private", "database at every known address. Every attempt must", "fail, and no private folder may be visible."]),
        "f7": dict(
            alt="Diagram: a four-step evidence trail, from the announcement, through data and result, to the report. Anyone can repeat steps two and three.",
            steps=[("Announcement", ["The hypothesis card with a date and a checksum,", "published before the measurement."]),
                   ("Data", ["A list of papers with checksums.", "Anyone can download the same texts."]),
                   ("Result", ["Raw numbers and the script that computes them."]),
                   ("Report", ["Every sentence points to a file or a data row.", "A number without a source stays out."])],
            you_t="Check it yourself", you_s=["Download the data (2), run the script (3)", "and compare the numbers with the report (4)."]),
        "f8": dict(
            alt="Diagram: six roadmap phases. The lab and the first experiment are being built, and the other four phases are planned.",
            date="As of 28 September 2026",
            status={"live": "Working", "wip": "In progress", "plan": "Planned"},
            rows=[("F2", "The lab", "Database, isolation, source list ready.", "wip", 3, 8),
                  ("F3", "First experiment", "Corpus ready, measurements not yet.", "wip", 1, 10),
                  ("F4", "Reference project card", "Assembled from recorded results.", "plan", 0, 4),
                  ("F5", "Radar and more experiments", "A weekly look at public sources.", "plan", 0, 7),
                  ("F6", "Scale and collaboration", "Second expert, a site, DOI archive.", "plan", 0, 6),
                  ("F7", "Public demo", "A knowledge base fed by research.", "plan", 0, 6)],
            foot=["The bar shows how many tasks of the phase are done."]),
    },
}


# ------------------------------------------------------------- figures ----
def fig1(lang):
    t = T[lang]["f1"]
    c = Canvas("f1", 632)
    c.card("plain", M, 16, W - 2 * M, 92)
    c.badge("priv", 56, 62, 22, "globe")
    c.text(94, 58, t["src_t"], 20, 700, "f-ink", font="td", box=(94, 500))
    c.text(94, 82, t["src_s"], 14.5, 400, "f-mut", box=(94, 500))
    c.arrow(96, 108, 96, 154)
    c.text(114, 136, t["src_arrow"], 13.5, 500, "f-mut", box=(114, 504))
    c.card("pub", M, 158, W - 2 * M, 112)
    c.badge("pub", 56, 214, 22, "flask")
    c.text(94, 208, t["lab_t"], 21, 700, "f-pubx", font="td", box=(94, 500))
    c.text(94, 233, t["lab_s"], 14.5, 400, "f-ink", box=(94, 500))
    c.arrow(96, 270, 96, 372)
    c.chip(114, 282, None, t["gate"], "gate", "shield", size=13.5, h=32)
    c.text(114, 338, t["arrow"], 13.5, 500, "f-mut", box=(114, 504), lh=1.3)
    c.card("plain", M, 376, W - 2 * M, 92)
    c.badge("pub", 56, 422, 22, "globe")
    c.text(94, 416, t["repo_t"], 20, 700, "f-ink", font="td", box=(94, 500))
    c.text(94, 440, t["repo_s"], 14.5, 400, "f-mut", box=(94, 500))
    c.wall(M, 490, W - 2 * M, 22)
    c.card("priv", M, 524, W - 2 * M, 96)
    c.badge("priv", 56, 572, 20, "lock")
    c.text(94, 567, t["out_t"], 18, 700, "f-privx", font="td", box=(94, 500))
    c.text(94, 589, t["out_s"], 14, 400, "f-ink", box=(94, 500))
    return c, t["alt"]


def fig2(lang):
    t = T[lang]["f2"]
    c = Canvas("f2", 748)
    c.card("plain", M, M, W - 2 * M, 66)
    c.badge("pub", 52, 49, 20, "doc")
    c.text(84, 45, t["doc_t"], 19, 700, "f-ink", font="td", box=(84, 500))
    c.text(84, 66, t["doc_s"], 14, 400, "f-mut", box=(84, 500))
    c.arrow(W / 2, 82, W / 2, 106)
    icons = ["shield", "search", "docs", "doc", "person"]
    y = 110
    for (ti, su), ic in zip(t["checks"], icons):
        c.card("plain", M, y, W - 2 * M, 62)
        c.badge("priv", 50, y + 31, 18, ic)
        c.text(80, y + 27, ti, 16, 700, "f-ink", box=(80, 504))
        c.text(80, y + 47, su, 14, 400, "f-mut", box=(80, 504))
        y += 72
    # y == 470
    c.path(f"M{W/2} 466 V486 H134 V503", "s-mut")
    c.path(f"M{W/2} 486 H386 V503", "s-mut")
    c.card("ok", M, 508, 236, 116)
    c.badge("ok", 44, 538, 15, "check")
    c.text(68, 544, t["ok_t"], 16, 700, "f-okx", font="td", box=(68, 244))
    c.text(30, 578, t["ok_s"], 14, 400, "f-ink", box=(30, 244))
    c.card("gate", 268, 508, 236, 116)
    c.badge("gate", 296, 538, 15, "pause")
    c.text(320, 544, t["hold_t"], 16, 700, "f-gatex", font="td", box=(320, 496))
    c.text(282, 578, t["hold_s"], 14, 400, "f-ink", box=(282, 496))
    c.card("plain", M, 648, W - 2 * M, 84)
    c.icon("repeat", 30, 668, 22, "s-priv")
    c.text(64, 678, t["test_t"], 15.5, 700, "f-ink", box=(64, 504))
    c.text(64, 700, t["test_s"], 14, 400, "f-mut", box=(64, 504))
    return c, t["alt"]


def fig3(lang):
    t = T[lang]["f3"]
    nodes = t["nodes"]
    heights = [66 + 19 * (len(n[1]) - 1) for n in nodes]
    total = 46 + sum(heights) + 14 * (len(nodes) - 1) + 24 + 66 + 16
    c = Canvas("f3", total)
    # legend
    c.icon("person", W - M - 18, 12, 18, "s-gatex")
    c.text(W - M - 24, 27, t["legend"], 13.5, 600, "f-gatex", "end", box=(W - 250, W - M - 22))
    y = 46
    centers = []
    for i, ((title, lines, human, tag), h) in enumerate(zip(nodes, heights), 1):
        c.card("plain", 84, y, W - 84 - M, h)
        centers.append(y + 30)
        c.text(100, y + 29, title, 17, 700, "f-ink", font="td", box=(100, 414))
        rx = W - M - 14
        if human:
            c.icon("person", rx - 20, y + 12, 20, "s-gatex")
            rx -= 30
        if tag == "seal":
            c.icon("seal", rx - 20, y + 11, 22, "s-pubx")
        elif tag:
            c.rect(rx - 26, y + 11, 26, 22, "f-pubt", "s-pub", rx=11, sw=1.2)
            c.text(rx - 13, y + 27, tag, 13, 700, "f-pubx", "middle", font="tm", box=(rx - 26, rx))
        c.text(100, y + 53, lines, 14, 400, "f-mut", box=(100, W - M - 10), lh=1.36)
        y += h + 14
    # rail + numbers
    c.add(f'<line x1="44" y1="{centers[0]}" x2="44" y2="{centers[-1]}" class="s-line" stroke-width="3"/>')
    for i, cy in enumerate(centers, 1):
        kind = "gate" if nodes[i - 1][2] and i in (5, 6) else "priv"
        c.add(f'<circle cx="44" cy="{cy}" r="17" class="f-priv"/>')
        c.text(44, cy + 5.5, str(i), 15.5, 700, "f-on", "middle", font="tm", box=(28, 60))
        c.add(f'<line x1="61" y1="{cy}" x2="84" y2="{cy}" class="s-line" stroke-width="2"/>')
    fy = y + 10
    c.card("pub", M, fy, W - 2 * M, 66)
    c.text(32, fy + 28, t["foot"], 14.5, 500, "f-pubx", box=(32, W - 30), lh=1.36)
    return c, t["alt"]


def fig4(lang):
    t = T[lang]["f4"]
    n = len(t["rows"])
    rh, gap, top = 104, 12, 46
    H = top + n * (rh + gap) + 46
    c = Canvas("f4", H)
    xs = [44 + i * (W - 88) / 5 for i in range(6)]
    for x, lab in zip(xs, t["stages"]):
        c.text(round(x, 1), 30, lab, 12, 600, "f-mut", "middle", font="tm", box=(round(x - 41, 1), round(x + 41, 1)))
    y = top
    for code, name, sub, st, done in t["rows"]:
        c.card("plain", M, y, W - 2 * M, rh)
        c.rect(28, y + 14, 50, 32, "f-priv", None, rx=9)
        c.text(53, y + 35, code, 14, 700, "f-on", "middle", font="tm", box=(28, 78))
        c.text(92, y + 28, name, 16, 700, "f-ink", font="td", box=(92, 384))
        c.text(92, y + 48, sub, 13, 400, "f-mut", box=(92, 384))
        kind = {"prep": "gate", "run": "gate", "done": "ok"}.get(st, "plain")
        px, pw = 392, 104
        if kind == "plain":
            c.rect(px, y + 12, pw, 24, "f-surf", "s-mut", rx=12, sw=1.2, dash="4 3")
            c.text(px + pw / 2, y + 28.5, t["status"][st], 12.5, 600, "f-mut", "middle", box=(px, px + pw))
        else:
            c.rect(px, y + 12, pw, 24, f"f-{kind}t", f"s-{kind}", rx=12, sw=1.2)
            c.text(px + pw / 2, y + 28.5, t["status"][st], 12.5, 700, f"f-{kind}x", "middle", box=(px, px + pw))
        ty = y + 80
        c.rect(round(xs[0], 1), ty - 1.5, round(xs[-1] - xs[0], 1), 3, "f-line", None, rx=1.5)
        if done:
            c.rect(round(xs[0], 1), ty - 1.5, round(xs[done] - xs[0], 1), 3, "f-ok", None, rx=1.5)
        for i, x in enumerate(xs):
            x = round(x, 1)
            if i < done:
                c.add(f'<circle cx="{x}" cy="{ty}" r="9" class="f-ok"/>')
                c.icon("check", x - 5, ty - 5, 10, "s-on")
            elif i == done and st in ("prep", "run"):
                c.add(f'<circle cx="{x}" cy="{ty}" r="9" class="f-gatet s-gate" stroke-width="2.6"/>')
            else:
                c.add(f'<circle cx="{x}" cy="{ty}" r="7" class="f-surf s-line" stroke-width="2"/>')
        y += rh + gap
    c.text(M, y + 12, t["foot"], 13, 400, "f-mut", box=(M, W - M), lh=1.35)
    return c, t["alt"]


def fig5(lang):
    t = T[lang]["f5"]
    c = Canvas("f5", 800)
    c.card("plain", M, 16, W - 2 * M, 76)
    c.badge("priv", 52, 54, 18, "globe")
    c.text(82, 50, t["src_t"], 18, 700, "f-ink", font="td", box=(82, 500))
    c.text(82, 72, t["src_s"], 13.5, 400, "f-mut", box=(82, 500))
    c.arrow(96, 92, 96, 154)
    c.chip(114, 107, None, t["allow"], "gate", "shield", size=13, h=30)
    c.card("pub", M, 158, W - 2 * M, 250)
    c.badge("pub", 46, 186, 15, "flask")
    c.text(70, 192, t["lab_t"], 19, 700, "f-pubx", font="td", box=(70, 500))
    for k, (title, sub, ic) in enumerate(t["mods"]):
        x = 28 + (k % 2) * 238
        y = 214 + (k // 2) * 96
        c.card("plain", x, y, 226, 84)
        c.badge("pub", x + 26, y + 26, 14, ic)
        c.text(x + 50, y + 31, title, 15, 700, "f-ink", font="td", box=(x + 50, x + 220))
        c.text(x + 16, y + 56, sub, 12.5, 400, "f-mut", box=(x + 16, x + 220), lh=1.3)
    c.arrow(96, 408, 96, 452)
    c.text(114, 434, t["every"], 13.5, 500, "f-mut", box=(114, 504))
    c.card("gate", M, 456, W - 2 * M, 72)
    c.badge("gate", 52, 492, 19, "shield")
    c.text(84, 488, t["gate_t"], 17, 700, "f-gatex", font="td", box=(84, 500))
    c.text(84, 510, t["gate_s"], 13.5, 400, "f-ink", box=(84, 500))
    c.arrow(96, 528, 96, 566)
    c.card("plain", M, 570, W - 2 * M, 176)
    c.badge("pub", 52, 602, 18, "globe")
    c.text(82, 608, t["repo_t"], 18, 700, "f-ink", font="td", box=(82, 500))
    widths = []
    for label, kind in t["outs"]:
        widths.append(round(32 + len(label) * 13 * 0.68 + 16))
    # rows: 0 alone, 1+2 together, 3 alone
    c.chip(32, 630, widths[0], t["outs"][0][0], "ok", "check", size=13, h=30)
    c.chip(32, 666, widths[1], t["outs"][1][0], "plain", "clock", size=13, h=30)
    c.chip(32 + widths[1] + 10, 666, widths[2], t["outs"][2][0], "plain", "clock", size=13, h=30)
    c.chip(32, 702, widths[3], t["outs"][3][0], "plain", "clock", size=13, h=30)
    c.text(M, 776, t["foot"], 13, 400, "f-mut", box=(M, W - M), lh=1.35)
    return c, t["alt"]


def fig6(lang):
    t = T[lang]["f6"]
    c = Canvas("f6", 664)
    c.rect(M, M, W - 2 * M, 338, "f-surf", "s-line", rx=18, sw=1.5, dash="7 6")
    c.icon("server", 32, 30, 20, "s-mut")
    c.text(58, 46, t["server"], 14, 600, "f-mut", font="tm", box=(58, 300))
    c.card("priv", 32, 68, 168, 178)
    c.badge("priv", 64, 106, 19, "lock")
    c.text(44, 154, t["priv_t"], 17, 700, "f-privx", font="td", lh=1.15, box=(44, 196))
    c.text(44, 204, t["priv_s"], 14, 400, "f-ink", box=(44, 196))
    c.text(32, 276, t["note"], 13.5, 500, "f-mut", box=(32, 206), lh=1.34)
    c.wall(208, 68, 28, 258)
    c.add('<circle cx="222" cy="197" r="14" class="f-gate"/>')
    c.icon("x", 215, 190, 14, "s-on")
    c.card("pub", 244, 68, 244, 258)
    c.badge("pub", 278, 106, 19, "flask")
    c.text(304, 112, t["lab_t"], 17, 700, "f-pubx", font="td", box=(304, 482))
    icons = ["db", "net", "folder"]
    y = 150
    for label, ic in zip(t["chips"], icons):
        c.chip(254, y, 226, label, "pub", ic, size=13, h=36)
        y += 50
    c.arrow(366, 392, 366, 330)
    c.card("plain", M, 392, W - 2 * M, 152)
    c.text(32, 420, t["src_t"], 17, 700, "f-ink", font="td", box=(32, 504))
    c.text(32, 441, t["src_s"], 13.5, 400, "f-mut", box=(32, 504))
    x = 32
    for lab in t["allowed"]:
        w = round(32 + len(lab) * 13 * 0.68 + 16)
        c.chip(x, 456, w, lab, "ok", "check", size=13, h=30)
        x += w + 10
    x = 32
    for lab in t["denied"]:
        w = round(32 + len(lab) * 13 * 0.68 + 16)
        c.chip(x, 496, w, lab, "gate", "x", size=13, h=30)
        x += w + 10
    c.card("plain", M, 560, W - 2 * M, 88)
    c.icon("repeat", 30, 578, 22, "s-priv")
    c.text(64, 588, t["test_t"], 15.5, 700, "f-ink", box=(64, 504))
    c.text(64, 608, t["test_s"], 13.5, 400, "f-mut", box=(64, 504), lh=1.32)
    return c, t["alt"]


def fig7(lang):
    t = T[lang]["f7"]
    c = Canvas("f7", 0)
    heights = [64 + 19 * (len(s[1]) - 1) - 0 for s in t["steps"]]
    heights = [50 + 19 * len(s[1]) + 8 for s in t["steps"]]
    gap = 26
    total = 16 + sum(heights) + gap * 3 + 26 + 100 + 16
    c = Canvas("f7", total)
    icons = ["seal", "db", "flask", "doc"]
    y = 16
    mids = []
    for i, ((title, lines), h, ic) in enumerate(zip(t["steps"], heights, icons), 1):
        c.card("plain", M, y, 456, h)
        c.badge("priv", 50, y + 30, 18, ic)
        c.text(80, y + 33, f"{i}", 13, 700, "f-mut", font="tm", box=(80, 100))
        c.text(96, y + 34, title, 18, 700, "f-ink", font="td", box=(96, 460))
        c.text(80, y + 58, lines, 14, 400, "f-mut", box=(80, 468), lh=1.36)
        mids.append(y + h / 2)
        if i < 4:
            c.arrow(W / 2 - 20, y + h, W / 2 - 20, y + h + gap - 2)
        y += h + gap
    y += 0
    py = y - gap + 26
    c.card("gate", M, py, W - 2 * M, 100)
    c.icon("person", 30, py + 16, 24, "s-gatex")
    c.text(64, py + 34, t["you_t"], 18, 700, "f-gatex", font="td", box=(64, 490))
    c.text(64, py + 58, t["you_s"], 14, 400, "f-ink", box=(64, 490), lh=1.36)
    # dashed returns from the panel to steps 2 and 3
    for m in (mids[1], mids[2]):
        c.path(f"M{W - M} {py + 50} H{W - 6} V{m} H{M + 456 + 3}", "s-gatex", dash="5 5")
    c.h = total
    return c, t["alt"]


def fig8(lang):
    t = T[lang]["f8"]
    c = Canvas("f8", 40 + 80 * len(t["rows"]) + 26)  # 706 for eight rows
    c.text(W - M, 22, t["date"], 13, 500, "f-mut", "end", font="tm", box=(W - 250, W - M))
    y = 40
    for code, name, sub, st, done, total in t["rows"]:
        c.card("plain", M, y, W - 2 * M, 72)
        kind = {"live": "ok", "wip": "gate", "plan": "plain"}[st]
        c.rect(28, y + 18, 42, 36, "f-priv", None, rx=10)
        c.text(49, y + 41.5, code, 15, 700, "f-on", "middle", font="tm", box=(28, 70))
        c.text(84, y + 32, name, 16, 700, "f-ink", font="td", box=(84, 380))
        c.text(84, y + 53, sub, 13.5, 400, "f-mut", box=(84, 386))
        px, pw = 392, 104
        if kind == "plain":
            c.rect(px, y + 12, pw, 24, "f-surf", "s-mut", rx=12, sw=1.2, dash="4 3")
            c.text(px + pw / 2, y + 28.5, t["status"][st], 12.5, 600, "f-mut", "middle", box=(px, px + pw))
        else:
            c.rect(px, y + 12, pw, 24, f"f-{kind}t", f"s-{kind}", rx=12, sw=1.2)
            c.text(px + pw / 2, y + 28.5, t["status"][st], 12.5, 700, f"f-{kind}x", "middle", box=(px, px + pw))
        c.rect(px, y + 44, pw, 7, "f-line", None, rx=3.5)
        if done:
            c.rect(px, y + 44, max(7, pw * done / total), 7, "f-ok" if st == "live" else "f-gate", None, rx=3.5)
        c.text(px + pw, y + 64, f"{done}/{total}", 11, 500, "f-mut", "end", font="tm", box=(px, px + pw))
        y += 80
    c.text(M, y + 8, t["foot"], 13.5, 400, "f-mut", box=(M, W - M))
    return c, t["alt"]


FIGS = [("f1", "overview", fig1), ("f2", "gate", fig2), ("f3", "path", fig3),
        ("f4", "hypotheses", fig4), ("f5", "architecture", fig5), ("f6", "isolation", fig6), ("f7", "evidence", fig7), ("f8", "status", fig8)]


def build_all():
    out = {}
    for lang in ("pl", "en"):
        for fid, slug, fn in FIGS:
            cv, alt = fn(lang)
            out[(lang, fid)] = dict(slug=slug, alt=alt,
                                    inline=cv.render(alt, False), standalone=cv.render(alt, True))
    return out


if __name__ == "__main__":
    import pathlib

    res = build_all()
    root = pathlib.Path("out")
    for (lang, fid), d in res.items():
        p = root / lang / f"{fid[1]}-{d['slug']}.svg"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(d["standalone"], encoding="utf-8")
    print(len(res), "svgs")
