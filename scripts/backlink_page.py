"""Übersicht der Sendungen von Backlink Broadcast – backlink.html im Zweig gh-pages (seit 16.11.2026).

Quelle: data/backlink_blocks.csv (aus scrape.py: jede Sendung, die auf der Andon-Seite läuft oder angekündigt ist)
und data/backlink_plays.csv (Titel mit Sendungsname).
Je Sendungsname: zuerst gesehen, zuletzt gelaufen, Anzahl Stunden, übliche Uhrzeit (MEZ und PT), Anzahl Titel,
neueste Beschreibung. Namen, die nach dem ersten Mitschnitt-Tag zum ersten Mal auftauchen, sind als „neu“ markiert.
Env: DATA_DIR (Datenordner), OUT_DIR (Ausgabeordner = Webseite)
"""
import csv, html, os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DE, PT = ZoneInfo("Europe/Berlin"), ZoneInfo("America/Los_Angeles")
DATA = Path(os.environ.get("DATA_DIR", "pages/data"))
OUT = Path(os.environ.get("OUT_DIR", "pages"))


def rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def main():
    blocks, plays = rows(DATA / "backlink_blocks.csv"), rows(DATA / "backlink_plays.csv")
    if not blocks:
        return
    now = datetime.now(timezone.utc)
    by_start = {}
    for b in blocks:                         # pro Startzeit gilt die zuletzt gesehene Ankündigung
        by_start[b["start_utc"]] = b
    first_day = min(t(b["first_seen_utc"]) for b in blocks).astimezone(DE).date()
    info = defaultdict(lambda: {"first": None, "last": None, "hours": 0, "de": Counter(), "pt": Counter(), "desc": ""})
    for st, b in sorted(by_start.items()):
        i, s = info[b["show"]], t(st)
        f = t(b["first_seen_utc"])
        i["first"] = min(i["first"] or f, f)
        if s <= now:
            i["hours"] += 1
            i["last"] = s
            i["de"][s.astimezone(DE).strftime("%H:%M")] += 1
            i["pt"][s.astimezone(PT).strftime("%H:%M")] += 1
        i["desc"] = b["description"]
    n_titles = Counter(p["show"] for p in plays)
    fmt = lambda d: d.astimezone(DE).strftime("%d.%m. %H:%M") if d else "noch nicht"
    top = lambda c: ", ".join(k for k, _ in c.most_common(2)) or "–"
    items = sorted(info.items(), key=lambda kv: kv[1]["first"], reverse=True)
    trs = []
    for name, i in items:
        new = i["first"].astimezone(DE).date() > first_day
        trs.append(f"<tr{' class=new' if new else ''}><td>{html.escape(name)}{' <b>neu</b>' if new else ''}</td>"
                   f"<td>{fmt(i['first'])}</td><td>{fmt(i['last'])}</td><td>{i['hours']}</td>"
                   f"<td>{top(i['de'])}</td><td>{top(i['pt'])}</td><td>{n_titles.get(name, 0)}</td>"
                   f"<td class=d>{html.escape(i['desc'])}</td></tr>")
    page = f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Backlink Broadcast – Sendungen</title><style>
body{{font-family:system-ui,sans-serif;margin:1rem;color:#222}} table{{border-collapse:collapse;width:100%;font-size:.9rem}}
th,td{{border-bottom:1px solid #ddd;padding:.35rem .5rem;text-align:left;vertical-align:top}} th{{background:#f4f4f4;position:sticky;top:0}}
td.d{{color:#555;font-size:.82rem}} tr.new td{{background:#fff7e0}} b{{color:#b45309;font-size:.75rem}} .hint{{color:#666;font-size:.85rem}}
</style></head><body><h1>Backlink Broadcast: Sendungen</h1>
<p class=hint>Mitschnitt seit {first_day.strftime('%d.%m.%Y')}. Stand {fmt(now)} (deutsche Zeit). „neu“ = Name zum ersten Mal nach dem ersten Mitschnitt-Tag gesehen.
Uhrzeit = häufigste Startzeit. {len(plays)} Titel mitgeschnitten. <a href="index.html">Zum Plattenregal</a></p>
<table><tr><th>Sendung</th><th>zuerst gesehen</th><th>zuletzt gelaufen</th><th>Stunden</th><th>MEZ</th><th>PT</th><th>Titel</th><th>Beschreibung (neueste)</th></tr>
{''.join(trs)}</table></body></html>"""
    (OUT / "backlink.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
