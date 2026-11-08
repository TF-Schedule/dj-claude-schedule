"""Tageswerte für DJ Claude aus data/plays.csv (deutsche Tage).

- ausgeruht: Anteil der Läufe, deren Titel in den 7 Tagen davor NICHT lief (zuverlässig ab 7 Tage nach Mitschnittbeginn 28.10.)
- ABC-Kette: Anteil aufeinanderfolgender Läufe verschiedener Künstler mit gleichem Anfangsbuchstaben („The“ ignoriert)
- Zufallswert ABC: was bei zufälliger Reihenfolge der Tageskünstler zu erwarten wäre (Summe der quadrierten Buchstabenanteile)
Aufruf: python3 scripts/claude_metrics.py pages/data/plays.csv
"""
import csv, re, sys
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


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pages/data/plays.csv")
