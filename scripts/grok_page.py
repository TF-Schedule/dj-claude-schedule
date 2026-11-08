"""Einfache Übersicht für DJ Grok (Station GNR) – grok.html im Zweig gh-pages.

Spalten: Künstler, Titel, zuletzt gelaufen (deutsche Zeit), Anzahl in den letzten 24 h, Gesamtanzahl.
Spalte „Neu hinzugefügt“ ist vorbereitet, aber AUS (SHOW_NEW = False): Kurts Liste kennt nur Titel,
die schon gelaufen sind, ein Kaufdatum gibt es dort nicht. Einschalten erst mit eigenen Daten.

Datenquelle vorerst: Kurt Woloch, gnr_only.csv (mit Dank). Bei Fehler wird die letzte Kopie genommen.
Env: DATA_DIR (Datenordner, Kopie von Kurts Liste), OUT_DIR (Ausgabeordner = Webseite)
"""
import csv, html, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DE = ZoneInfo("Europe/Berlin")
DATA = Path(os.environ.get("DATA_DIR", "pages/data"))
OUT = Path(os.environ.get("OUT_DIR", "pages"))
KURT_URL = "https://kurtwoloch.github.io/andon-fm-library/gnr_only.csv"
KURT_PAGE = "https://kurtwoloch.github.io/andon-fm-library/gnr_only.html"
KURT = DATA / "kurt_gnr_only.csv"
UA = {"User-Agent": "TF-Schedule listener tool (github.com/TF-Schedule/dj-claude-schedule)"}
SHOW_NEW = False                   # „Neu hinzugefügt“ – erst mit eigenen (Nicht-Kurt-)Daten einschalten


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


def de(t):
    if not t:
        return "", ""
    d = t.astimezone(DE)
    return d.strftime("%Y-%m-%d %H:%M"), {"CET": "MEZ", "CEST": "MESZ"}.get(d.tzname(), d.tzname())


def page(rows):
    rows.sort(key=lambda r: r["last"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    newest = rows[0]["last"] if rows else None
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
</style></head><body>
<h1>DJ Grok – Titelübersicht</h1>
<p class="meta">Neuester Eintrag: <b>{stand} {tz}</b> · erzeugt {now} ·
{len(rows)} Titel · in den letzten 24 h: {played24} Titel, {plays24} Läufe, davon {twice} Titel mehrfach</p>
<div class="bar"><input type="search" id="q" placeholder="Künstler oder Titel suchen …">
<label><input type="checkbox" id="only"> nur letzte 24 h</label>
<label><input type="checkbox" id="multi"> nur mehrfach in 24 h</label>
<span id="cnt"></span></div>
<table id="t"><thead><tr>{head}</tr></thead><tbody>
{chr(10).join(body)}
</tbody></table>
<footer>Ein privates Fan-Projekt, nicht von Andon Labs betrieben. Daten vorerst aus
<a href="{KURT_PAGE}">Kurt Wolochs Andon-FM-Bibliothek</a> (Verzug bis zu einigen Stunden) – mit Dank.
„24 h“ = Kurts Zählung der letzten 24 Stunden. Blau = 1× in 24 h, orange = mehrfach.</footer>
<script>
const tb=document.querySelector('#t tbody'),rows=[...tb.rows],q=document.getElementById('q'),
only=document.getElementById('only'),multi=document.getElementById('multi'),cnt=document.getElementById('cnt');
function f(){{const s=q.value.toLowerCase();let n=0;for(const r of rows){{const h=+r.cells[3].textContent||0;
const ok=(!s||(r.cells[0].textContent+' '+r.cells[1].textContent).toLowerCase().includes(s))&&(!only.checked||h>0)&&(!multi.checked||h>1);
r.style.display=ok?'':'none';if(ok)n++;}}cnt.textContent=n+' angezeigt';}}
[q,only,multi].forEach(x=>x.addEventListener('input',f));
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
    rows = load()
    if not rows:
        print("Keine Grok-Daten – Seite nicht erzeugt.")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "grok.html").write_text(page(rows), encoding="utf-8")
    print(f"grok.html: {len(rows)} Titel")


if __name__ == "__main__":
    main()
