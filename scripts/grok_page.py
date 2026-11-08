"""Einfache Übersicht für DJ Grok (Grok'n Roll) – grok.html im Zweig gh-pages.

Spalten: Künstler, Titel, zuletzt gelaufen (deutsche Zeit), Anzahl in den letzten 24 h, Gesamtanzahl, neu hinzugefügt.

Quellen:
  - eigener Mitschnitt (seit 08.11.2026): Live365 api.live365.com/station/a15419 (aktueller + letzte Titel),
    alle 15 Min. → data/grok_plays.csv (wird nur ergänzt)
  - Kurt Woloch, gnr_only.csv (mit Dank): Verlauf vor unserem Start, Gesamtzahlen. Kopie data/kurt_gnr_only.csv.
Zusammenführung je Titel: Kurts Zahlen + unsere Läufe, die nach Kurts letztem Lauf kamen (die kennt er noch nicht).
24 h: sobald unser Mitschnitt 24 h abdeckt, nur noch aus dem Mitschnitt.
„Neu hinzugefügt“: nur Titel, die WIR zum ersten Mal laufen sehen und die Kurts Liste bis dahin nicht kannte
(data/grok_seen.csv merkt sich, was schon bekannt war).
Env: DATA_DIR (Datenordner), OUT_DIR (Ausgabeordner = Webseite)
"""
import csv, html, json, os, re, urllib.request
from datetime import timedelta
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DE = ZoneInfo("Europe/Berlin")
DATA = Path(os.environ.get("DATA_DIR", "pages/data"))
OUT = Path(os.environ.get("OUT_DIR", "pages"))
KURT_URL = "https://kurtwoloch.github.io/andon-fm-library/gnr_only.csv"
KURT_PAGE = "https://kurtwoloch.github.io/andon-fm-library/gnr_only.html"
KURT = DATA / "kurt_gnr_only.csv"
LIVE365 = "https://api.live365.com/station/a15419"
PLAYS = DATA / "grok_plays.csv"
SEEN = DATA / "grok_seen.csv"
PLAY_COLS = ["start_utc", "artist", "title"]
SEEN_COLS = ["key", "artist", "title", "first_utc", "source"]   # source: kurt = schon vorher bekannt, eigen = von uns zuerst gesehen
UA = {"User-Agent": "TF-Schedule listener tool (github.com/TF-Schedule/dj-claude-schedule)"}
STATS = DATA / "stats.csv"         # Kontostand aller Stationen (Spalte balance, seit 08.11.2026)
STATION = "Grok and Roll"
SHOW_NEW = True                    # „Neu hinzugefügt“ – nur aus eigenen (Nicht-Kurt-)Daten


def utc(s):
    s = (s or "").strip().replace(" ", "T").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except ValueError:
        return None


def num(s):
    try:
        return int(float(s or 0))
    except ValueError:
        return 0


def ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def key(artist, title):
    return ws(artist).casefold() + "|" + ws(title).casefold()


def fmt(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def read_csv(path, cols):
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [{c: r.get(c, "") for c in cols} for r in csv.DictReader(f)]


def write_csv(path, cols, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def record():
    """Eigener Mitschnitt: neue Titel aus Live365 an grok_plays.csv anhängen."""
    plays = read_csv(PLAYS, PLAY_COLS)
    known = {(p["start_utc"], p["artist"], p["title"]) for p in plays}
    try:
        req = urllib.request.Request(LIVE365, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        items = list(d.get("last-played") or [])
        if (d.get("current-track") or {}).get("title"):
            items.append(d["current-track"])
        for t in items:
            st = utc(t.get("start"))
            if not t.get("title") or not st:
                continue
            p = {"start_utc": fmt(st), "artist": ws(t.get("artist")), "title": ws(t.get("title"))}
            if (p["start_utc"], p["artist"], p["title"]) not in known:
                plays.append(p)
                known.add((p["start_utc"], p["artist"], p["title"]))
    except Exception as e:
        print("Live365 (Grok) nicht lesbar:", e)
    plays.sort(key=lambda p: p["start_utc"])
    DATA.mkdir(parents=True, exist_ok=True)
    write_csv(PLAYS, PLAY_COLS, plays)
    return plays


def load():
    try:
        req = urllib.request.Request(KURT_URL, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", "replace")
        if text.startswith("Artist,Title"):
            DATA.mkdir(parents=True, exist_ok=True)
            KURT.write_text(text, encoding="utf-8")
    except Exception as e:
        print("Kurts Grok-Liste nicht erreichbar, nehme Kopie:", e)
    if not KURT.exists():
        return []
    rows = []
    with open(KURT, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if not (r.get("Artist") and r.get("Title")):
                continue
            rows.append({
                "artist": r["Artist"].strip(),
                "title": r["Title"].strip(),
                "last": utc(r.get("Last Played (UTC)")),
                "h24": num(r.get("Play Count 24H")),
                "total": num(r.get("Play Count Total")),
                "new": "",          # Platzhalter für eigene Daten
            })
    return rows


def merge(kurt, plays):
    now = datetime.now(timezone.utc)
    by = {}
    for r in kurt:
        k = key(r["artist"], r["title"])
        if k in by:                                   # Doppelungen bei Kurt zusammenzählen
            o = by[k]
            o["total"] += r["total"]; o["h24"] += r["h24"]
            o["last"] = max(x for x in (o["last"], r["last"]) if x) if (o["last"] or r["last"]) else None
        else:
            by[k] = dict(r, kurt_last=r["last"])
    for r in by.values():
        r["kurt_last"] = r["last"]
    own = [(utc(p["start_utc"]), p) for p in plays]
    own = [(t, p) for t, p in own if t]
    full24 = bool(own) and own[0][0] <= now - timedelta(hours=24)   # Mitschnitt deckt schon 24 h ab?
    for r in by.values():
        if full24:
            r["h24"] = 0
    for t, p in own:
        k = key(p["artist"], p["title"])
        r = by.get(k)
        if r is None:
            r = by[k] = {"artist": p["artist"], "title": p["title"], "last": None, "kurt_last": None, "h24": 0, "total": 0, "new": ""}
        unseen_by_kurt = not r["kurt_last"] or t > r["kurt_last"] + timedelta(seconds=30)
        if unseen_by_kurt:
            r["total"] += 1
        if t >= now - timedelta(hours=24) and (full24 or unseen_by_kurt):
            r["h24"] += 1
        if not r["last"] or t > r["last"]:
            r["last"] = t
    # „neu hinzugefügt“: Kurts Titel gelten als bekannt; was wir zuerst sehen, bekommt ein Datum
    seen = {s["key"]: s for s in read_csv(SEEN, SEEN_COLS)}
    first_run = not seen
    for t, p in own:
        k = key(p["artist"], p["title"])
        if k not in seen:
            known_before = first_run and by[k]["kurt_last"] is not None
            seen[k] = {"key": k, "artist": p["artist"], "title": p["title"],
                       "first_utc": "" if known_before else fmt(t), "source": "kurt" if known_before else "eigen"}
    for r in kurt:
        k = key(r["artist"], r["title"])
        if k not in seen:
            seen[k] = {"key": k, "artist": r["artist"], "title": r["title"], "first_utc": "", "source": "kurt"}
    write_csv(SEEN, SEEN_COLS, sorted(seen.values(), key=lambda s: s["key"]))
    for k, r in by.items():
        sv = seen.get(k)
        r["new"] = de(utc(sv["first_utc"]))[0] if sv and sv["source"] == "eigen" else ""
    return list(by.values()), full24, (own[0][0] if own else None)


def balance():
    """Kontostand jetzt, vor 24 h und die letzten Änderungen (Auflösung 15 Min.)."""
    rows = [r for r in read_csv(STATS, ["utc", "station", "balance"]) if r["station"] == STATION and r["balance"]]
    pts = [(utc(r["utc"]), float(r["balance"])) for r in rows]
    pts = [p for p in pts if p[0]]
    if not pts:
        return None
    now_t, now_b = pts[-1]
    day = [b for t, b in pts if t <= now_t - timedelta(hours=24)]
    changes = []
    for (t0, b0), (t1, b1) in zip(pts, pts[1:]):
        if abs(b1 - b0) >= 0.005:
            changes.append((t0, t1, b1 - b0, b1))
    return {"now": now_b, "at": now_t, "d24": (now_b - day[-1]) if day else None, "since": pts[0][0],
            "changes": changes[-30:][::-1]}


def de(t):
    if not t:
        return "", ""
    d = t.astimezone(DE)
    return d.strftime("%Y-%m-%d %H:%M"), {"CET": "MEZ", "CEST": "MESZ"}.get(d.tzname(), d.tzname())


def bal_html(b):
    if not b:
        return ""
    e = html.escape
    eur = lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    sign = lambda x: ("+" if x > 0 else "−" if x < 0 else "±") + eur(abs(x))
    d24 = f" · 24 h: <b>{sign(b['d24'])}</b>" if b["d24"] is not None else f" · Aufzeichnung seit {' '.join(de(b['since']))}"
    span = lambda a, z: f"{de(a)[0]}–{de(z)[0][11:]} {de(z)[1]}" if de(a)[0][:10] == de(z)[0][:10] else f"{' '.join(de(a))} – {' '.join(de(z))}"
    rows = "".join(f"<tr><td>{span(a, z)}</td><td class='n {'plus' if d > 0 else 'minus'}'>{sign(d)}</td><td class='n'>{eur(v)}</td></tr>"
                   for a, z, d, v in b["changes"])
    tab = (f"<details><summary>letzte Änderungen ({len(b['changes'])})</summary><table class='bal'><tr><th>passiert zwischen</th><th class='n'>Änderung</th><th class='n'>Stand</th></tr>{rows}</table>"
           "<p class='hint'>Auflösung 15 Minuten: Die Änderung geschah irgendwann im angegebenen Zeitraum; mehrere Zahlungen/Käufe im selben Abstand erscheinen als eine Änderung. Plus = Zahlung an ihn, Minus = Kauf. Ein Kauf kostet 3 $ – −2,00 heißt meist: 1 $ kam rein und ein Titel wurde gekauft.</p></details>") if b["changes"] else ""
    return f"<p class='meta'>Kontostand: <b>{eur(b['now'])}</b> (Stand {' '.join(de(b['at']))}){d24}</p>{tab}"


def page(rows, full24=False, since=None, bal=None):
    rows.sort(key=lambda r: r["last"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    newest = rows[0]["last"] if rows else None
    since_txt = " ".join(de(since)) if since else "–"
    src24 = "eigener Mitschnitt" if full24 else "Kurts Zählung + eigener Mitschnitt (bis der Mitschnitt 24 h abdeckt)"
    n_new = sum(1 for r in rows if r["new"])
    stand, tz = de(newest)
    now, _ = de(datetime.now(timezone.utc))
    played24 = sum(1 for r in rows if r["h24"])
    plays24 = sum(r["h24"] for r in rows)
    twice = sum(1 for r in rows if r["h24"] > 1)
    e = html.escape
    head = "<th data-k='a'>Künstler</th><th data-k='t'>Titel</th><th data-k='l'>Zuletzt gelaufen</th>" \
           "<th data-k='h' class='n'>24 h</th><th data-k='g' class='n'>Gesamt</th>"
    if SHOW_NEW:
        head += "<th data-k='x'>Neu hinzugefügt</th>"
    body = []
    for r in rows:
        l, z = de(r["last"])
        cls = " class='twice'" if r["h24"] > 1 else (" class='recent'" if r["h24"] else "")
        cells = (f"<td>{e(r['artist'])}</td><td>{e(r['title'])}</td><td>{l} {z}</td>"
                 f"<td class='n'>{r['h24'] or ''}</td><td class='n'>{r['total']}</td>")
        if SHOW_NEW:
            cells += f"<td>{e(r['new'])}</td>"
        body.append(f"<tr{cls}>{cells}</tr>")
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DJ Grok – Titelübersicht</title>
<style>
body{{font:15px/1.4 system-ui,sans-serif;margin:1rem auto;max-width:1100px;padding:0 1rem;color:#222;background:#fafafa}}
h1{{font-size:1.4rem;margin:.2rem 0}} .meta{{color:#555;margin:.3rem 0 .8rem}}
.bar{{display:flex;gap:.8rem;flex-wrap:wrap;align-items:center;margin-bottom:.6rem}}
input[type=search]{{padding:.35rem .5rem;min-width:16rem;font:inherit}}
table{{border-collapse:collapse;width:100%;background:#fff}}
th,td{{padding:.3rem .5rem;border-bottom:1px solid #e5e5e5;text-align:left;vertical-align:top}}
th{{position:sticky;top:0;background:#eee;cursor:pointer;user-select:none;white-space:nowrap}}
th.asc::after{{content:" ▲"}} th.desc::after{{content:" ▼"}}
.n{{text-align:right;font-variant-numeric:tabular-nums}} td:nth-child(3){{white-space:nowrap}}
tr.recent td{{background:#f3f8ff}} tr.twice td{{background:#fff1e6}}
footer{{color:#666;font-size:.85rem;margin:1.2rem 0}}
details{{margin:.2rem 0 .8rem}} table.bal{{width:auto;margin:.4rem 0}} .plus{{color:#1a7f37}} .minus{{color:#b42318}} .hint{{color:#666;font-size:.85rem}}
</style></head><body>
<h1>DJ Grok – Titelübersicht</h1>
<p class="meta">Neuester Eintrag: <b>{stand} {tz}</b> · erzeugt {now} ·
{len(rows)} Titel · in den letzten 24 h: {played24} Titel, {plays24} Läufe, davon {twice} Titel mehrfach · neu hinzugefügt: {n_new}</p>
{bal_html(bal)}
<div class="bar"><input type="search" id="q" placeholder="Künstler oder Titel suchen …">
<label><input type="checkbox" id="only"> nur letzte 24 h</label>
<label><input type="checkbox" id="multi"> nur mehrfach in 24 h</label>
<label><input type="checkbox" id="neu"> nur neu hinzugefügte</label>
<span id="cnt"></span></div>
<table id="t"><thead><tr>{head}</tr></thead><tbody>
{chr(10).join(body)}
</tbody></table>
<footer>Ein privates Fan-Projekt, nicht von Andon Labs betrieben. Aktuelle Titel aus dem eigenen Mitschnitt (Live365, alle 15 Min., seit {since_txt});
Verlauf davor und Gesamtzahlen aus <a href="{KURT_PAGE}">Kurt Wolochs Andon-FM-Bibliothek</a> – mit Dank.
„24 h“: {src24}. „Neu hinzugefügt“: erstmals in unserem Mitschnitt gesehen und vorher nicht in Kurts Liste.
Blau = 1× in 24 h, orange = mehrfach.</footer>
<script>
const tb=document.querySelector('#t tbody'),rows=[...tb.rows],q=document.getElementById('q'),
only=document.getElementById('only'),multi=document.getElementById('multi'),neu=document.getElementById('neu'),cnt=document.getElementById('cnt');
function f(){{const s=q.value.toLowerCase();let n=0;for(const r of rows){{const h=+r.cells[3].textContent||0;
const ok=(!s||(r.cells[0].textContent+' '+r.cells[1].textContent).toLowerCase().includes(s))&&(!only.checked||h>0)&&(!multi.checked||h>1)&&(!neu.checked||(r.cells[5]&&r.cells[5].textContent.trim()));
r.style.display=ok?'':'none';if(ok)n++;}}cnt.textContent=n+' angezeigt';}}
[q,only,multi,neu].forEach(x=>x.addEventListener('input',f));
document.querySelectorAll('th').forEach((th,i)=>th.addEventListener('click',()=>{{
const d=th.classList.contains('asc')?-1:1;document.querySelectorAll('th').forEach(x=>x.classList.remove('asc','desc'));
th.classList.add(d>0?'asc':'desc');const num=i>=3&&i<=4;
rows.sort((a,b)=>{{let x=a.cells[i].textContent,y=b.cells[i].textContent;
return (num?((+x||0)-(+y||0)):x.localeCompare(y,'de'))*d;}});rows.forEach(r=>tb.appendChild(r));}}));
f();
</script>
</body></html>
"""


def main():
    plays = record()
    rows, full24, since = merge(load(), plays)
    if not rows:
        print("Keine Grok-Daten – Seite nicht erzeugt.")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "grok.html").write_text(page(rows, full24, since, balance()), encoding="utf-8")
    print(f"grok.html: {len(rows)} Titel")


if __name__ == "__main__":
    main()
