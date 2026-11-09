"""Tageswerte für DJ Claude aus data/plays.csv (deutsche Tage).

- ausgeruht: Anteil der Läufe, deren Titel in den 7 Tagen davor NICHT lief (zuverlässig ab 7 Tage nach Mitschnittbeginn 28.10.)
- ABC-Kette: Anteil aufeinanderfolgender Läufe verschiedener Künstler mit gleichem Anfangsbuchstaben („The“ ignoriert)
- Zufallswert ABC: was bei zufälliger Reihenfolge der Tageskünstler zu erwarten wäre (Summe der quadrierten Buchstabenanteile)
- Regal-Top 10 (ab 09.11.): Anteil der Läufe, deren Titel zu dem Zeitpunkt unter den ersten 10 seiner Genre-Seite
  auf shelf.html stand (aus shelf_hits.csv); Zufall = Anteil der Top-10-Plätze an der ganzen Bibliothek
Aufruf: python3 scripts/claude_metrics.py pages/data/plays.csv
"""
import csv, json, re, sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DE = ZoneInfo("Europe/Berlin")


def key(a, t):
    return (a.strip().lower(), re.sub(r"\s*[\(\[].*$", "", t.strip().lower()))


def initial(a):
    a = re.sub(r"^(the|die|der|la|le|los|les)\s+", "", a.strip(), flags=re.I)
    m = re.search(r"[A-Za-zÀ-ÿ0-9]", a)
    return m.group(0).upper() if m else "?"


def main(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    plays = sorted((datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00")), r["artist"], r["title"]) for r in rows)
    start = plays[0][0]
    last = {}
    days = defaultdict(lambda: {"n": 0, "rest": 0, "pairs": 0, "abc": 0, "letters": Counter()})
    prev = None
    for t, a, ti in plays:
        d = t.astimezone(DE).date()
        D = days[d]
        D["n"] += 1
        k = key(a, ti)
        if k not in last or t - last[k] > timedelta(days=7):
            D["rest"] += 1
        last[k] = t
        D["letters"][initial(a)] += 1
        if prev and prev[0].astimezone(DE).date() == d and prev[1].lower() != a.lower():
            D["pairs"] += 1
            D["abc"] += initial(prev[1]) == initial(a)
        prev = (t, a)
    print("Tag        Läufe  ausgeruht(7T)  ABC-Kette  Zufall")
    for d in sorted(days):
        D = days[d]
        ok = datetime.combine(d, datetime.min.time(), DE) >= start + timedelta(days=7)
        tot = sum(D["letters"].values())
        rnd = sum((c / tot) ** 2 for c in D["letters"].values()) if tot else 0
        rest = f"{100 * D['rest'] / D['n']:5.1f} %" if ok else "   (–)  "
        abc = 100 * D["abc"] / D["pairs"] if D["pairs"] else 0
        print(f"{d}  {D['n']:5d}  {rest:>13}  {abc:7.1f} %  {100 * rnd:4.1f} %")

    hits_path = Path(path).parent / "shelf_hits.csv"
    snap_path = Path(path).parent / "shelf_rank.json"
    if hits_path.exists() and snap_path.exists():
        sizes = json.loads(snap_path.read_text(encoding="utf-8"))["sizes"]
        chance = sum(min(10, n) for n in sizes.values()) / sum(sizes.values())
        hd = defaultdict(lambda: [0, 0, 0])            # Läufe, Top 10, Top 100 (erste Seite)
        for r in csv.DictReader(open(hits_path, encoding="utf-8")):
            d = datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00")).astimezone(DE).date()
            hd[d][0] += 1
            if r["rank"]:
                hd[d][1] += int(r["rank"]) <= 10
                hd[d][2] += int(r["rank"]) <= 100
        print(f"\nRegal (Platz vor dem Spielen)  Zufall Top 10: {100 * chance:.1f} %")
        print("Tag        Läufe  Top 10   Top 100")
        for d in sorted(hd):
            n, t10, t100 = hd[d]
            print(f"{d}  {n:5d}  {100 * t10 / n:5.1f} %  {100 * t100 / n:5.1f} %")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pages/data/plays.csv")
