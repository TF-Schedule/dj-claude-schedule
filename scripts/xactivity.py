"""X-Aktivität der Andon-Stationen aus dem Seitencode von andonlabs.com/radio (seit 11.11.2026).

Andon zeigt je Station die letzten ~10 Posts (eigene Posts des DJs + Antworten darunter). Wir lesen sie alle 15 Min.
und hängen neue an data/x_activity.csv an. Bewusst OHNE Namen, Text oder Link – nur wann, welche Station, wer (DJ/Hörer).
Der Schlüssel ist ein kurzer Hash der Post-ID (nur zum Erkennen von Doppelten).
"""
import csv, hashlib, json, re
from pathlib import Path

COLS = ["key", "station", "posted_utc", "who", "kind", "to_dj"]
# who: dj | hoerer · kind: post (neuer Post) | antwort · to_dj: 1 = Antwort direkt auf einen Post des DJs


def _js_array(s, i):
    """s[i] == '[' – JS-Objektliteral bis zur passenden Klammer in JSON umwandeln und laden."""
    out, depth, j, n = [], 0, i, len(s)
    while j < n:
        c = s[j]
        if c == '"':
            k = j + 1
            while s[k] != '"':
                k += 2 if s[k] == "\\" else 1
            out.append(s[j:k + 1]); j = k + 1; continue
        if c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                out.append(c); break
        m = re.match(r"[A-Za-z_$][\w$]*", s[j:j + 60]) if (c.isalpha() or c in "_$") else None
        if m:
            w = m.group(0)
            out.append(f'"{w}"' if s[j + len(w):j + len(w) + 1] == ":" else w if w in ("true", "false", "null") else "null")
            j += len(w); continue
        out.append(c); j += 1
    return json.loads("".join(out))


def station_tweets(html):
    starts = [(m.start(), json.loads('"' + m.group(1) + '"')) for m in re.finditer(r'name:"((?:[^"\\]|\\.)*)",subtitle:', html)]
    res = {}
    for (a, name), nxt in zip(starts, starts[1:] + [(len(html), None)]):
        seg = html[a:nxt[0]]
        k = seg.find("tweets:[")
        if k >= 0:
            res[name] = _js_array(seg, k + len("tweets:"))
    return res


def utc(s):
    s = (s or "").strip()
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", s)
    return m.group(1) + "Z" if m else ""


def rows_from(html):
    rows = []
    for station, threads in station_tweets(html).items():
        own = set()
        def walk(t):
            yield t
            for r in t.get("replies") or []:
                yield from walk(r)
        posts = [p for t in threads for p in walk(t)]
        for p in posts:
            if p.get("is_own_tweet"):
                own.add(str(p.get("id")))
        for p in posts:
            if not p.get("id") or not p.get("posted_at"):
                continue
            parent = p.get("parent_tweet_id")
            rows.append({"key": hashlib.sha1(str(p["id"]).encode()).hexdigest()[:12], "station": station,
                         "posted_utc": utc(p["posted_at"]), "who": "dj" if p.get("is_own_tweet") else "hoerer",
                         "kind": "antwort" if parent else "post", "to_dj": "1" if parent and str(parent) in own else ""})
    return rows


def record(html, path):
    path = Path(path)
    old = []
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            old = list(csv.DictReader(f))
    known = {r["key"] for r in old}
    new = [r for r in rows_from(html) if r["key"] not in known]
    allr = sorted(old + new, key=lambda r: (r["posted_utc"], r["station"]))
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader(); w.writerows({c: r.get(c, "") for c in COLS} for r in allr)
    return len(new)
