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
Dead Air (seit 11.11.2026): Stille zwischen zwei Titeln = Abstand der Starts minus Liedlänge
(Live365 > iTunes-Suche, Cache data/grok_durations.csv > eigene Abstände), ab DEAD_MIN Minuten.
Env: DATA_DIR (Datenordner), OUT_DIR (Ausgabeordner = Webseite)
"""
import csv, html, json, os, re, statistics, time, urllib.parse, urllib.request
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
PLAY_COLS = ["start_utc", "artist", "title", "duration_s"]   # duration_s seit 11.11.2026 (Live365 liefert sie nicht immer)
DUR = DATA / "grok_durations.csv"  # Liedlängen aus der iTunes-Suche (Cache)
DUR_COLS = ["key", "artist", "title", "itunes_s", "checked_utc"]
ITUNES = "https://itunes.apple.com/search"
DEAD_MIN = 4                        # Dead Air: Stille ab so vielen Minuten zählen
XACT = DATA / "x_activity.csv"     # X-Aktivität aller Stationen (ohne Namen/Text), aus scrape.py
X_BEFORE = 30                      # Hörer-Posts bis so viele Minuten vor einer Pause zählen
DEAD_GAP_HINT = 30                  # ab so vielen Minuten: evtl. Lücke im Mitschnitt
SEEN_COLS = ["key", "artist", "title", "first_utc", "source"]   # source: kurt = schon vorher bekannt, eigen = von uns zuerst gesehen
UA = {"User-Agent": "TF-Schedule listener tool (github.com/TF-Schedule/dj-claude-schedule)"}
STATS = DATA / "stats.csv"         # Kontostand aller Stationen (Spalte balance, seit 08.11.2026)
STATION = "Grok and Roll"
SHOW_NEW = True
# „sauber“ nach Groks bekannten Sperren: kein feat./zweiter Name, keine Klammer, kein Komma, keine Jahreszeit
DIRTY = re.compile(r"\bfeat\b|\bfeat\.|\bft\.|featuring|\bwith\b|[()\[\],/]|\bx\b|\b(spring|summer|autumn|winter)\b", re.I)
GONE_MIN, GONE_DAYS = 50, 7         # „verschwundene Lieblinge“: mind. 50 Läufe, seit 7 Tagen nicht gelaufen
REST_DAYS = 2                      # Vorschlags-Filter: mindestens so viele Tage nicht gelaufen                    # „Neu hinzugefügt“ – nur aus eigenen (Nicht-Kurt-)Daten


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
    known = {(p["start_utc"], p["artist"], p["title"]): p for p in plays}
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
            try:
                d = round(float(t.get("duration") or 0))
            except (TypeError, ValueError):
                d = 0
            p = {"start_utc": fmt(st), "artist": ws(t.get("artist")), "title": ws(t.get("title")), "duration_s": str(d) if d > 0 else ""}
            k = (p["start_utc"], p["artist"], p["title"])
            if k not in known:
                plays.append(p)
                known[k] = p
            elif d > 0 and not known[k].get("duration_s"):
                known[k]["duration_s"] = str(d)
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
    own = [(t, p) for t, p in own if t
           and p["artist"].strip() and p["title"].strip().lower() != "unknown"]   # Live365-Leermeldung („Unknown“, ohne Künstler) = kein Titel
    full24 = bool(own) and own[0][0] <= now - timedelta(hours=24)   # Mitschnitt deckt schon 24 h ab?
    for r in by.values():
        # Kurts 24-h-Zahl ist veraltet, sobald sein letzter Lauf aus dem Fenster gefallen ist
        if full24 or not r["kurt_last"] or r["kurt_last"] < now - timedelta(hours=24):
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
        r.setdefault("times", []).append(t)
    # Abstand zwischen letztem und vorletztem Lauf: eigene Läufe + Kurts letzter Lauf davor (falls nicht derselbe)
    for r in by.values():
        ts = list(r.get("times", []))
        kl = r.get("kurt_last")
        if kl and all(abs((kl - t).total_seconds()) > 60 for t in ts):
            ts.append(kl)
        ts.sort()
        r["prev"] = ts[-2] if len(ts) > 1 else None
        r["gap"] = (ts[-1] - ts[-2]) if len(ts) > 1 else None
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


def itunes_lengths(plays, limit=40):
    """Liedlängen per iTunes-Suche nachschlagen (nur neue Titel, höchstens `limit` pro Lauf) → Cache grok_durations.csv."""
    cache = {c["key"]: c for c in read_csv(DUR, DUR_COLS)}
    todo = []
    for p in reversed(plays):                               # neueste zuerst (wichtig für „läuft gerade / Stille“)
        if not p["artist"].strip() or p["title"].strip().lower() == "unknown":
            continue
        k = key(p["artist"], p["title"])
        if k not in cache and k not in {x[0] for x in todo}:
            todo.append((k, p["artist"], p["title"]))
    for k, artist, title in todo[:limit]:
        secs = ""
        try:
            q = urllib.parse.urlencode({"term": f"{artist} {title}", "entity": "song", "limit": 10, "country": "US"})
            req = urllib.request.Request(f"{ITUNES}?{q}", headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                res = json.loads(r.read().decode("utf-8", "replace")).get("results") or []
            a0, t0 = ws(artist).casefold(), ws(title).casefold()
            def score(x):
                an, tn = ws(x.get("artistName")).casefold(), ws(x.get("trackName")).casefold()
                return (an == a0 or a0 in an or an in a0) * 2 + (tn == t0) * 2 + (t0 in tn)
            best = max(res, key=score) if res else None
            if best and score(best) >= 3 and best.get("trackTimeMillis"):
                secs = str(round(best["trackTimeMillis"] / 1000))
        except Exception as e:
            print("iTunes-Suche nicht möglich:", e)
            break                                           # nicht erreichbar → nächster Lauf
        cache[k] = {"key": k, "artist": artist, "title": title, "itunes_s": secs, "checked_utc": fmt(datetime.now(timezone.utc))}
        time.sleep(0.4)
    if cache:
        DATA.mkdir(parents=True, exist_ok=True)
        write_csv(DUR, DUR_COLS, sorted(cache.values(), key=lambda c: c["key"]))
    return {k: int(c["itunes_s"]) for k, c in cache.items() if c["itunes_s"]}


def dead_air(plays, itunes):
    """Stille zwischen zwei Titeln: Abstand der Starts minus Länge des ersten Titels.
    Länge: Live365-Angabe > iTunes > eigene Abstände (Median ab 3, sonst Minimum von 2).
    Spielt er nachweislich eine kürzere Fassung (Median der eigenen Abstände ≥ 1 Min. kürzer), gilt die."""
    seq = [(utc(p["start_utc"]), p) for p in plays]
    seq = [(t, p) for t, p in seq if t]
    seq.sort(key=lambda x: x[0])
    real = lambda p: p["artist"].strip() and p["title"].strip().lower() != "unknown"
    obs, live = {}, {}
    for (t0, a), (t1, b) in zip(seq, seq[1:]):
        if real(a) and real(b):
            obs.setdefault(key(a["artist"], a["title"]), []).append((t1 - t0).total_seconds())
    for t, p in seq:
        if real(p) and (p.get("duration_s") or "").isdigit() and int(p["duration_s"]) > 0:
            live.setdefault(key(p["artist"], p["title"]), []).append(int(p["duration_s"]))
    def length(k):
        o = obs.get(k, [])
        if k in live:
            d, src = statistics.median(live[k]), "Live365"
        elif k in itunes:
            d, src = itunes[k], "iTunes"
        elif len(o) >= 3:
            return statistics.median(o), "eigene Läufe"
        elif len(o) == 2:
            return min(o), "eigene Läufe"
        else:
            return None, ""
        if len(o) >= 3 and statistics.median(o) < d - 60:
            return statistics.median(o), "eigene Läufe"
        return d, src
    reals = [(t, p) for t, p in seq if real(p)]
    out = []
    for (t0, a), (t1, b) in zip(reals, reals[1:]):
        d, src = length(key(a["artist"], a["title"]))
        if d is None:
            continue
        silent = (t1 - t0).total_seconds() - d
        if silent >= DEAD_MIN * 60:
            out.append({"from": t0 + timedelta(seconds=d), "to": t1, "secs": silent, "after": a, "next": b, "src": src})
    # jetzt: läuft der letzte Titel noch, oder ist es seit seinem Ende still?
    cur = None
    if reals:
        t0, a = reals[-1]
        d, src = length(key(a["artist"], a["title"]))
        cur = {"start": t0, "play": a, "end": t0 + timedelta(seconds=d) if d is not None else None}
    return out, cur


def now_html(cur, xact=()):
    """Zeile oben: läuft gerade etwas laut Mitschnitt, oder ist es still? Hilft bei der Frage „Browser oder DJ?“."""
    if not cur:
        return ""
    e = html.escape
    now = datetime.now(timezone.utc)
    hm = lambda t: t.astimezone(DE).strftime("%H:%M")
    what = f"{e(cur['play']['artist'])} – {e(cur['play']['title'])}"
    stand = f"<span class='hint'>(Stand {hm(now)}, wird alle 15 Min. erneuert)</span>"
    near = x_near(xact, cur["end"] or cur["start"], now) if xact else ""
    if near:
        stand = f"· X: {e(near)} " + stand
    if cur["end"] is None:
        if now - cur["start"] > timedelta(minutes=12):
            return f"<p class='now quiet'>■ Seit {hm(cur['start'])} kein neuer Titel (zuletzt {what}, Länge unbekannt) – vermutlich Stille {stand}</p>"
        return f"<p class='now'>▶ Läuft: {what} (seit {hm(cur['start'])}) {stand}</p>"
    if now - cur["end"] >= timedelta(minutes=2):
        mins = int((now - cur["end"]).total_seconds() // 60)
        return (f"<p class='now quiet'>■ <b>Stille</b> seit ca. {hm(cur['end'])} (gut {mins} Min.) – der DJ pausiert, nicht dein Browser. "
                f"Zuletzt: {what} {stand}</p>")
    return f"<p class='now'>▶ Läuft: {what} (seit {hm(cur['start'])}, bis ca. {hm(cur['end'])}) {stand}</p>"


def x_grok():
    rows = [r for r in read_csv(XACT, ["station", "posted_utc", "who", "kind"]) if r["station"] == STATION]
    return [(utc(r["posted_utc"]), r["who"]) for r in rows if utc(r["posted_utc"])]


def x_near(x, a, b):
    """X-Aktivität um eine Pause: Hörer-Posts ab X_BEFORE Min. vor Beginn, DJ-Posts während der Pause (+5 Min.)."""
    hm = lambda t: t.astimezone(DE).strftime("%H:%M")
    h = [t for t, w in x if w == "hoerer" and a - timedelta(minutes=X_BEFORE) <= t <= b]
    d = [t for t, w in x if w == "dj" and a <= t <= b + timedelta(minutes=5)]
    parts = (["Hörer " + ", ".join(hm(t) for t in h)] if h else []) + (["DJ " + ", ".join(hm(t) for t in d)] if d else [])
    return " · ".join(parts)


def dead_html(ev, since, xact=()):
    if not ev and not since:
        return ""
    e = html.escape
    now = datetime.now(timezone.utc)
    last24 = [x for x in ev if x["to"] >= now - timedelta(hours=24)]
    days = {}
    for x in ev:
        d = x["from"].astimezone(DE).strftime("%d.%m.")
        n, s, m = days.get(d, (0, 0, 0))
        days[d] = (n + 1, s + x["secs"], max(m, x["secs"]))
    mins = lambda s: f"{round(s / 60)} Min."
    xday = {}
    for t, w in xact:
        d = t.astimezone(DE).strftime("%d.%m.")
        hh, dd = xday.get(d, (0, 0))
        xday[d] = (hh + (w == "hoerer"), dd + (w == "dj"))
    for d in xday:
        days.setdefault(d, (0, 0, 0))
    xd = lambda d: (f"{xday[d][0]} / {xday[d][1]}" if d in xday else "")
    drows = "".join(f"<tr><td>{d}</td><td class='n'>{n}</td><td class='n'>{mins(s)}</td><td class='n'>{mins(m) if n else ''}</td><td class='n'>{xd(d)}</td></tr>"
                    for d, (n, s, m) in sorted(days.items(), key=lambda kv: kv[0][3:5] + kv[0][:2], reverse=True))
    rows = []
    for x in sorted(ev, key=lambda x: x["from"], reverse=True):
        f = x["from"].astimezone(DE)
        note = "evtl. Lücke im Mitschnitt" if x["secs"] >= DEAD_GAP_HINT * 60 else ""
        cls = " class='hot'" if x["secs"] >= 15 * 60 else ""
        rows.append(f"<tr{cls}><td>{f:%d.%m.}</td><td>{f:%H:%M}</td><td class='n' data-v='{int(x['secs'])}'>{mins(x['secs'])}</td>"
                    f"<td>{e(x['after']['artist'])} – {e(x['after']['title'])}</td><td>{x['to'].astimezone(DE):%H:%M} "
                    f"{e(x['next']['artist'])} – {e(x['next']['title'])}</td><td>{e(x_near(xact, x['from'], x['to']))}</td><td>{e(x['src'])}</td><td>{note}</td></tr>")
    since_txt = " ".join(de(since)) if since else "–"
    return (f"<details class='dead'><summary><b>Dead Air</b> – letzte 24 h: <b>{len(last24)}×</b>, zusammen ca. {mins(sum(x['secs'] for x in last24))}"
            f" · seit Aufzeichnungsbeginn {len(ev)}×</summary>"
            f"<table class='bal'><tr><th>Tag (MEZ)</th><th class='n'>Pausen</th><th class='n'>Stille gesamt</th><th class='n'>längste</th><th class='n' title='laut Andon-Seite, seit 11.11.2026'>X: Hörer / DJ</th></tr>{drows}</table>"
            f"<table class='bal'><tr><th>Datum</th><th>Stille ab ca.</th><th class='n'>Dauer ca.</th><th>nach dem Stück</th><th>weiter mit</th><th title='Hörer-Posts bis 30 Min. vor der Pause, DJ-Posts während der Pause'>X dabei</th><th>Liedlänge laut</th><th></th></tr>{''.join(rows)}</table>"
            f"<p class='hint'>Erkannt wird Stille ab ca. {DEAD_MIN} Minuten: Abstand bis zum nächsten Start minus Länge des Stücks. "
            f"Die Länge kommt von Live365, sonst aus der iTunes-Suche, sonst aus seinen eigenen früheren Läufen; spielt er nachweislich eine kürzere Fassung, gilt die. "
            f"Kürzere Pausen und Pausen nach Stücken ohne bekannte Länge fehlen. Ab {DEAD_GAP_HINT} Min. kann auch unser Mitschnitt eine Lücke haben. "
            f"Dunkelorange = 15 Min. oder länger. Mitschnitt seit {since_txt}. "
            f"„X dabei“: Hörer-Posts an ihn bis {X_BEFORE} Min. vor der Pause und seine eigenen Posts während der Pause – laut Andon-Seite "
            f"(dort nur seine letzten ~10 Posts, ohne Namen erfasst, seit 11.11.2026).</p></details>")


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


def dur(td):
    if td is None:
        return ""
    m = int(td.total_seconds() // 60)
    if m < 60:
        return f"{m} Min."
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} h {m:02d} Min."
    d, h = divmod(h, 24)
    return f"{d} T {h} h"


def page(rows, full24=False, since=None, bal=None, dead=""):
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
           "<th data-k='d' class='n'>Abstand zum vorletzten</th><th data-k='h' class='n'>24 h</th><th data-k='g' class='n'>Gesamt</th>"
    if SHOW_NEW:
        head += "<th data-k='x'>Neu hinzugefügt</th>"
    body = []
    for r in rows:
        l, z = de(r["last"])
        cls = " class='hot'" if r["h24"] >= 3 else " class='twice'" if r["h24"] > 1 else (" class='recent'" if r["h24"] else "")
        gap = r.get("gap")
        tip = f" title='vorletzter Lauf: {' '.join(de(r['prev']))}'" if r.get("prev") else ""
        gv = int(gap.total_seconds()) if gap else 10**9
        cells = (f"<td>{e(r['artist'])}</td><td>{e(r['title'])}</td><td>{l} {z}</td>"
                 f"<td class='n' data-v='{gv}'{tip}>{dur(gap)}</td>"
                 f"<td class='n' data-v='{r['h24']}'>{r['h24'] or ''}</td><td class='n' data-v='{r['total']}'>{r['total']}</td>")
        if SHOW_NEW:
            cells += f"<td>{e(r['new'])}</td>"
        clean = not DIRTY.search(r["artist"] + " " + r["title"])
        rest = r["last"] is None or r["last"] <= datetime.now(timezone.utc) - timedelta(days=REST_DAYS)
        sug = " data-s='1'" if clean and rest else ""
        if r["total"] >= GONE_MIN and (r["last"] is None or r["last"] <= datetime.now(timezone.utc) - timedelta(days=GONE_DAYS)):
            sug += " data-g='c'" if clean else " data-g='d'"     # c = ohne erkennbaren Grund, d = vermutlich Filter
        body.append(f"<tr{cls}{sug}>{cells}</tr>")
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
td{{-webkit-user-select:text;user-select:text}} td:nth-child(2){{cursor:copy}}
table.gone tr[data-g='c'] td:first-child::after{{content:" ●";color:#b42318}}
td.ok{{outline:2px solid #1a7f37}} #toast{{position:fixed;bottom:1rem;left:50%;transform:translateX(-50%);background:#1a7f37;color:#fff;padding:.4rem .8rem;border-radius:.4rem;display:none}}
tr.recent td{{background:#f3f8ff}} tr.twice td{{background:#fff1e6}} tr.hot td{{background:#ffc999}}
footer{{color:#666;font-size:.85rem;margin:1.2rem 0}}
p.now{{margin:.3rem 0;padding:.35rem .6rem;background:#eef6ee;border-left:4px solid #1a7f37}} p.now.quiet{{background:#fff1e6;border-left-color:#b42318}}
details{{margin:.2rem 0 .8rem}} details.dead table td{{white-space:normal}} table.bal{{width:auto;margin:.4rem 0}} .plus{{color:#1a7f37}} .minus{{color:#b42318}} .hint{{color:#666;font-size:.85rem}}
</style></head><body>
<h1>DJ Grok – Titelübersicht</h1>
<p class="meta">Neuester Eintrag: <b>{stand} {tz}</b> · erzeugt {now} ·
{len(rows)} Titel · in den letzten 24 h: {played24} Titel, {plays24} Läufe, davon {twice} Titel mehrfach · neu hinzugefügt: {n_new}</p>
{bal_html(bal)}
{dead}
<div class="bar"><input type="search" id="q" placeholder="Künstler oder Titel suchen …">
<label><input type="checkbox" id="only"> nur letzte 24 h</label>
<label><input type="checkbox" id="multi"> nur mehrfach in 24 h</label>
<label><input type="checkbox" id="neu"> nur neu hinzugefügte</label>
<label title="kein feat./zweiter Name, keine Klammer, kein Komma, kein Schrägstrich, keine Jahreszeit; seit mindestens 2 Tagen nicht gelaufen; längste Pause zuerst"><input type="checkbox" id="sug"> Vorschläge (sauber &amp; ≥ 2 Tage Pause)</label>
<label title="mindestens 50× gespielt, aber seit 7 Tagen nicht mehr; ● = ohne erkennbaren Grund (kein feat., keine Klammer …)"><input type="checkbox" id="gone"> verschwundene Lieblinge</label>
<span id="cnt"></span></div>
<p class="hint">Tipp: Auf einen <b>Titel</b> tippen kopiert „Künstler – Titel“ zum Einfügen (z. B. auf X).</p>
<table id="t"><thead><tr>{head}</tr></thead><tbody>
{chr(10).join(body)}
</tbody></table>
<footer>Ein privates Fan-Projekt, nicht von Andon Labs betrieben. Aktuelle Titel aus dem eigenen Mitschnitt (Live365, alle 15 Min., seit {since_txt});
Verlauf davor und Gesamtzahlen aus <a href="{KURT_PAGE}">Kurt Wolochs Andon-FM-Bibliothek</a> – mit Dank.
„24 h“: {src24}. „Neu hinzugefügt“: erstmals in unserem Mitschnitt gesehen und vorher nicht in Kurts Liste.
„Vorschläge“: Titel ohne feat./zweiten Namen, Klammer, Komma, Schrägstrich oder Jahreszeit (seine bekannten Sperren), seit mindestens 2 Tagen nicht gelaufen – längste Pause zuerst; ob sie in seiner Spielbar-Liste stehen, weiß nur er. „Verschwundene Lieblinge“: mindestens 50× gespielt, aber seit 7 Tagen nicht mehr; ● = kein Filter-Grund erkennbar (vielleicht aus seiner Spielbar-Liste gefallen). „Abstand zum vorletzten“: Zeit zwischen den beiden letzten Läufen (Maus auf den Wert: Zeitpunkt des vorletzten Laufs); leer, wenn nur ein Lauf bekannt ist. Blau = 1× in 24 h, hellorange = 2×, dunkelorange = 3× oder öfter.</footer>
<script>
const tb=document.querySelector('#t tbody'),rows=[...tb.rows],q=document.getElementById('q'),
only=document.getElementById('only'),multi=document.getElementById('multi'),neu=document.getElementById('neu'),sug=document.getElementById('sug'),gone=document.getElementById('gone'),cnt=document.getElementById('cnt');
function f(){{const s=q.value.toLowerCase();let n=0;for(const r of rows){{const h=+r.cells[4].textContent||0;
const ok=(!s||(r.cells[0].textContent+' '+r.cells[1].textContent).toLowerCase().includes(s))&&(!only.checked||h>0)&&(!multi.checked||h>1)&&(!neu.checked||(r.cells[6]&&r.cells[6].textContent.trim()))&&(!sug.checked||r.dataset.s)&&(!gone.checked||r.dataset.g);
r.style.display=ok?'':'none';if(ok)n++;}}cnt.textContent=n+' angezeigt';}}
const a0=i=>rows[0].cells[i].dataset;
[q,only,multi,neu].forEach(x=>x.addEventListener('input',f));
gone.addEventListener('input',()=>{{document.getElementById('t').classList.toggle('gone',gone.checked);
if(gone.checked){{rows.sort((a,b)=>(+b.cells[5].dataset.v)-(+a.cells[5].dataset.v));rows.forEach(r=>tb.appendChild(r));
document.querySelectorAll('th').forEach(x=>x.classList.remove('asc','desc'));document.querySelectorAll('th')[5].classList.add('desc');}}f();}});
sug.addEventListener('input',()=>{{if(sug.checked){{rows.sort((a,b)=>a.cells[2].textContent.localeCompare(b.cells[2].textContent));rows.forEach(r=>tb.appendChild(r));
document.querySelectorAll('th').forEach(x=>x.classList.remove('asc','desc'));document.querySelectorAll('th')[2].classList.add('asc');}}f();}});
document.querySelectorAll('th').forEach((th,i)=>th.addEventListener('click',()=>{{
const big=['h','g'].includes(th.dataset.k);   // 24 h und Gesamt: erst die größten
const d=th.classList.contains('asc')?-1:th.classList.contains('desc')?1:(big?-1:1);document.querySelectorAll('th').forEach(x=>x.classList.remove('asc','desc'));
th.classList.add(d>0?'asc':'desc');const num='v' in a0(i);
rows.sort((a,b)=>{{let x=num?+a.cells[i].dataset.v:a.cells[i].textContent,y=num?+b.cells[i].dataset.v:b.cells[i].textContent;
return (num?(x-y):x.localeCompare(y,'de'))*d;}});rows.forEach(r=>tb.appendChild(r));}}));
f();
const toast=document.createElement('div');toast.id='toast';document.body.appendChild(toast);
function copy(txt){{if(navigator.clipboard&&window.isSecureContext)return navigator.clipboard.writeText(txt);
const t=document.createElement('textarea');t.value=txt;t.setAttribute('readonly','');t.style.position='fixed';t.style.opacity='0';
document.body.appendChild(t);t.select();t.setSelectionRange(0,txt.length);const ok=document.execCommand('copy');t.remove();
return ok?Promise.resolve():Promise.reject();}}
tb.addEventListener('click',ev=>{{const td=ev.target.closest('td');if(!td||td.cellIndex!==1)return;
const r=td.parentElement,txt=r.cells[0].textContent+' – '+r.cells[1].textContent;
copy(txt).then(()=>{{toast.textContent='kopiert: '+txt;}},()=>{{toast.textContent='Kopieren ging nicht';}}).finally(()=>{{
td.classList.add('ok');toast.style.display='block';setTimeout(()=>{{td.classList.remove('ok');toast.style.display='none';}},1500);}});}});
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
    try:
        ev, cur = dead_air(plays, itunes_lengths(plays))
        xact = x_grok()
        dead = now_html(cur, xact) + dead_html(ev, since, xact)
    except Exception as e:                                  # Dead Air darf die Seite nie verhindern
        print("Dead Air nicht berechnet:", e)
        dead = ""
    (OUT / "grok.html").write_text(page(rows, full24, since, balance(), dead), encoding="utf-8")
    print(f"grok.html: {len(rows)} Titel")


if __name__ == "__main__":
    main()
