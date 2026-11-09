"""Bibliothek nach Genres für DJ Claude (Englisch, statisches HTML, kein JavaScript).

shelf.html            – Übersicht: 17 Hauptgenres mit Anzahl
shelf/<genre>.html    – alle Titel des Genres, am längsten nicht gelaufen zuerst (Künstler, Titel, zuletzt gelaufen, Anzahl)

Bewusst OHNE Arrlys Notizen, ohne Playlists und ohne Sendungsnamen (nur das Genre).
Genre-Zuordnung wie im Regal (site/index.html, MAIN/RULES): zuerst Arrlys Genre, dann Stil, dann Apple, dann Playlists.
Env: DATA_DIR (Daten des Plattenregals), OUT_DIR (Ausgabeordner = Webseite)

Regal-Zähler (seit 09.11.): data/shelf_rank.json merkt sich bei jedem Lauf, an welcher Stelle jeder Titel
auf seiner Genre-Seite stand. Beim nächsten Lauf bekommen alle neuen Läufe aus plays.csv den Platz, den der Titel
VOR dem Spielen hatte → data/shelf_hits.csv (start_utc,artist,title,genre,rank,genre_size). Auswertung: claude_metrics.py.
"""
import csv, html, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrape import norm_key                                       # gleiche Titelzuordnung wie Regal

PT = ZoneInfo("America/Los_Angeles")
DATA = Path(os.environ.get("DATA_DIR", "pages/data"))
OUT = Path(os.environ.get("OUT_DIR", "pages"))
PAGE_SIZE = 100                    # lange Seiten werden beim Abruf zusammengefasst → höchstens 100 Titel pro Seite

MAIN = ["Soul / R&B", "Jazz", "Electronic", "Rock", "Alternative / Indie", "Pop", "Folk / Singer-Songwriter",
        "Hip-Hop / Rap", "Country / Americana", "Latin / Brasil", "World / Global", "Metal", "Classical / Neo-Classical",
        "Blues", "Soundtrack / Score", "Reggae / Dub", "Disco / Dance"]
RULES = [(g, re.compile(p)) for g, p in [   # wörtlich aus site/index.html – Reihenfolge zählt
    ("Soundtrack / Score", r"soundtrack|score|filmmusik|videospiel|video game|musicals|game music"),
    ("Reggae / Dub", r"reggae|\bdub\b|\bska\b|dancehall|rocksteady"),
    ("Hip-Hop / Rap", r"hip.?hop|\brap\b|trap\b|grime|boom.?bap"),
    ("Metal", r"metal"),
    ("Latin / Brasil", r"bossa|samba|\bmpb\b|tango|rock en espa|rock y alternativo|rumba|bolero|latin|salsa|cumbia|reggaet|brasil|brazil|tropical|mexican|raíces|raices|flamenco|south america|nueva canci"),
    ("Disco / Dance", r"disco|eurodance|^dance$|dance.?pop|italo"),
    ("Blues", r"blues"),
    ("Jazz", r"jazz|swing|bebop|big.?band|^vocal$|fusion|crooner|scat"),
    ("Soul / R&B", r"soul|r&b|rnb|funk|motown|gospel|doo.?wop|quiet storm|christian"),
    ("Classical / Neo-Classical", r"classical|klassik|klassisch|neoklass|neo-class|minimal music|minimalis|oper|baroque|barock|orchest|romantik|requiem|kammermusik|chamber music"),
    ("Country / Americana", r"country|americana|bluegrass|outlaw|heartland|roots rock"),
    ("World / Global", r"world|afro|african|amapiano|desert|ethio|fado|duduk|j-?pop|k-?pop|mandopop|cantopop|asia|indian|bollywood|tamil|arab|klezmer|balkan|celtic|hawaii|turkish|türk|portugal|armen|gamelan|qawwali|highlife|mbalax|rai\b"),
    ("Folk / Singer-Songwriter", r"folk|singer|songwriter|liedermacher|chanson|acoustic|akustik|ballad|murder"),
    ("Electronic", r"electro|elektron|ambient|trip.?hop|downtempo|techno|house|trance|drum.?n.?bass|jungle|idm|drone|chiptune|glitch|new age|synthwave|darkwave|coldwave|breakbeat|lo.?fi|klangkunst|sound collage|experiment"),
    ("Alternative / Indie", r"indie|alternative|alt-|post-punk|punk|grunge|shoegaze|dream.?pop|goth|new wave|slowcore|emo\b|hardcore|art.?pop|britpop|post-rock|chamber.?pop"),
    ("Rock", r"rock|prog|psychedel|glam|british invasion|guitar"),
    ("Pop", r"pop|schlager|easy listening|adult contemporary|holiday|christmas|comedy|karaoke|kwela|vocal"),
]]
OTHER = "Other"


def read(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main_from(text):
    x = (text or "").lower()
    if not x:
        return ""
    for g, r in RULES:
        if r.search(x):
            return g
    return ""


def main_of(t, n):
    if n.get("genre") in MAIN:
        return n["genre"]
    return (main_from(n.get("genre")) or main_from(n.get("style")) or main_from(t.get("genre"))
            or main_from(n.get("lists")) or OTHER)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def aired(iso):
    if not iso:
        return "not aired yet"
    t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PT)
    return f"last aired {t:%b} {t.day}, {t.year}" if t.year != datetime.now(PT).year else f"last aired {t:%b} {t.day}"


def head(title):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title></head><body>')


def count_hits(by):
    """Neue Läufe mit ihrem Regalplatz aus dem vorigen Lauf versehen, dann neuen Stand merken."""
    snap_path, hits_path = DATA / "shelf_rank.json", DATA / "shelf_hits.csv"
    plays = read(DATA / "plays.csv")
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else None
    if snap and len(plays) > snap["plays_seen"]:
        new = not hits_path.exists()
        with open(hits_path, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["start_utc", "artist", "title", "genre", "rank", "genre_size"])
            for p in plays[snap["plays_seen"]:]:
                g, r = snap["rank"].get(norm_key(p["artist"], p["title"]), ["", ""])
                w.writerow([p["start_utc"], p["artist"], p["title"], g, r, snap["sizes"].get(g, "")])
    rank, sizes = {}, {}
    for g, items in by.items():
        sizes[g] = len(items)
        for i, t in enumerate(items, 1):
            rank.setdefault(norm_key(t["artist"], t["title"]), [g, i])
    snap_path.write_text(json.dumps({"plays_seen": len(plays), "sizes": sizes, "rank": rank},
                                    ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    tracks = read(DATA / "tracks.csv")
    if not tracks:
        print("Keine tracks.csv – Shelf übersprungen.")
        return
    notes = {norm_key(n["artist"], n["title"]): n for n in read(DATA / "notes.csv")}
    by = {}
    for t in tracks:
        g = main_of(t, notes.get(norm_key(t["artist"], t["title"]), {}))
        by.setdefault(g, []).append(t)
    now = datetime.now(PT)
    stamp = f"{now:%b} {now.day}, {now.hour % 12 or 12}:{now.minute:02d}{'am' if now.hour < 12 else 'pm'} PT"
    e = html.escape
    order = [g for g in MAIN if g in by] + ([OTHER] if OTHER in by else [])
    for g in by:                                                  # Reihenfolge wie auf den Seiten
        by[g].sort(key=lambda t: (t["last_played_utc"] or "", t["artist"].lower(), t["title"].lower()))
    (OUT / "shelf").mkdir(parents=True, exist_ok=True)
    index = []
    for g in order:
        items = by[g]
        parts = [items[i:i + PAGE_SIZE] for i in range(0, len(items), PAGE_SIZE)]
        links = []
        for no, part in enumerate(parts, 1):
            name = f"{slug(g)}.html" if no == 1 else f"{slug(g)}-{no}.html"
            links.append(name)
        for no, part in enumerate(parts, 1):
            nav = ""
            if len(parts) > 1:
                nav = "<p>Part " + " · ".join(
                    (f"<b>{i}</b>" if i == no else f'<a href="{links[i - 1]}">{i}</a>') for i in range(1, len(parts) + 1)) + "</p>"
            li = "".join(
                f"<li>{e(t['artist'])} – {e(t['title'])} <small>({aired(t['last_played_utc'])}"
                f"{', ' + t['plays'] + '×' if t.get('plays') and t['plays'] != '0' else ''})</small></li>" for t in part)
            first = (no - 1) * PAGE_SIZE + 1
            (OUT / "shelf" / links[no - 1]).write_text(
                head(f"{g} – shelf") + f"<h1>{e(g)}</h1>"
                f"<p>{len(items)} titles in your library. Longest unplayed first"
                f"{f' – titles {first}–{first + len(part) - 1}' if len(parts) > 1 else ''}. ({stamp})</p>{nav}"
                f"<ul>{li}</ul>{nav}<p><a href=\"../shelf.html\">all genres</a></p></body></html>", encoding="utf-8")
        index.append(f'<li><a href="shelf/{links[0]}">{e(g)}</a> – {len(items)}</li>')
    (OUT / "shelf.html").write_text(
        head("Your library by genre") +
        "<h1>Your library by genre</h1>"
        "<p>Everything that has aired on Thinking Frequencies, sorted by genre. Inside each genre: longest unplayed first, "
        "with the date it last aired. Just a shelf to browse when you choose freely – nothing to follow. "
        f"Made by listeners as a fan project; not run by Andon Labs. Updated every 15 minutes ({stamp}).</p>"
        f"<ul>{''.join(index)}</ul>"
        '<p><small>What aired in the last 24 hours: <a href="dj.html">dj.html</a></small></p></body></html>', encoding="utf-8")
    try:
        count_hits(by)
    except Exception as ex:                                       # Zähler darf das Regal nie stören
        print("Regal-Zähler übersprungen:", ex)
    print("shelf.html: " + ", ".join(f"{g} {len(by[g])}" for g in order))


if __name__ == "__main__":
    main()
