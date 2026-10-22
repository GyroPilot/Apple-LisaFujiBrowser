#!/usr/bin/env python3
"""LisaWeb gateway, prototype REV A (13 Oct 2026).

Turns web pages into small plain-text pages an Apple Lisa can show through a FujiNet,
the same way the FujiNet news service does.  The Lisa only ever sends short requests:

  /w/home                          the start page
  /w/open?u=<address>[&ps=76x14]   fetch a page; the reply starts a new document
  /w/page?d=<doc>&p=<n>            page n of a document already fetched
  /w/link?d=<doc>&n=<link>         follow link n of a document; a new document
  /w/find?q=<words>                search (Wikipedia, for this prototype)
  /w/links?d=<doc>&p=<n>           the addresses of the links on page n

Every reply is plain ASCII, lines ending in LF:
  line 1  D<doc> <page>/<pages>
  line 2  the title
  line 3  the site and the number of links
  then up to <rows> lines of text, at most <cols> wide; links marked [n]
A problem is one line starting "ERROR:".

GATEWAY REV F (22-Oct-2026): picture icons on the page for Browser 1.1: tv=1 adds "~T n 96 48" slot lines after
  picture links; /w/thumb?d=&n=&tw=&th= sends the icon like /w/pic.  See patch_gw_revf.py.
GATEWAY REV E1 (20-Oct-2026 23:50): a picture that is not shown and has no alt text of its own gets no line
  (the Wikipedia infobox logo borrowed the photo's caption: a second, unnumbered [picture: ...] line).
GATEWAY REV E (20-Oct-2026): self-registering keys for Browser 0.2.1 (ids.txt, ids_banned.txt, gw_ids.py); see
  patch_gw_reve.py.
GATEWAY REV D (pictures) (17-Oct-2026): described pictures as links for Browser 0.2 (pv=1), dithered and sent row by row; see patch_gw_pics.py.
GATEWAY REV C (15-Oct-2026): access keys, a rate limit, pages cached on disk, a request log.
  keys.txt beside this file: one "key  name" per line; blank lines and # comments ignored; reloaded when it changes.
  A key (k=...) is required for requests that arrive through a proxy (Tailscale Funnel sets X-Forwarded-For) or from
  a public address; requests straight from the LAN or the tailnet need none, so the FujiNet at home keeps working.
  Rate limit: 60 requests a minute and 3000 a day per key (per address when keyless).
  docs.json beside this file keeps fetched pages across restarts (24 h); requests.log records every request.
Private and local addresses are refused already.
"""
import http.server, ipaddress, re, socket, sys, textwrap, threading, time, urllib.parse
import requests
from PIL import Image
import io
from bs4 import BeautifulSoup, NavigableString, Tag
from readability import Document
from unidecode import unidecode

UA = "LisaWeb-gateway/0.1 (Apple Lisa text browser via FujiNet; contact bmwcyclist on lisalist2.com)"
MAX_BYTES = 8_000_000   # was 2 MB; the Apple Inc. article tripped it (2026-10-15)
TIMEOUT = 15
DOC_TTL = 24 * 3600
COLS, ROWS = 76, 14
import os, json
HERE = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(HERE, "keys.txt")
DOC_FILE = os.path.join(HERE, "docs.json")
LOG_FILE = os.path.join(HERE, "requests.log")
RATE_MINUTE, RATE_DAY = 60, 3000
IDS_FILE = os.path.join(HERE, "ids.txt")              # REV E: self-made keys, "key  first-seen-UTC  ip-hash"
BANNED_FILE = os.path.join(HERE, "ids_banned.txt")   # REV E: self-made keys Tim switched off
NEW_PER_HOUR, NEW_PER_DAY = 3, 40                     # REV E: new self-made keys per address an hour; overall a day

HOME_LINKS = [
    ("The weather in your town (wttr.in)", "lisaweb:weather"),
    ("Where is the International Space Station right now", "lisaweb:iss"),
    ("Wikipedia: Apple Lisa", "https://en.wikipedia.org/wiki/Apple_Lisa"),
    ("LisaList2 forum", "https://lisalist2.com/"),
    ("Hacker News (text)", "https://news.ycombinator.com/"),
    ("Computer History Museum: the Lisa source code", "https://computerhistory.org/blog/the-lisa-apples-most-influential-failure/"),
    ("GyroPilot on GitHub (Tim's Lisa software)", "https://github.com/GyroPilot"),
    ("Who is aboard the space stations now", "lisaweb:crew"),
]
CREW_URL = "https://corquaid.github.io/international-space-station-APIs/JSON/people-in-space.json"

docs = {}          # doc id -> dict(title, host, url, lines, links, made)
docs_lock = threading.Lock()
next_id = [1000]


def load_docs():
    """Pages from the last run, so a restart does not strand the Lisa's document numbers."""
    try:
        with open(DOC_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        now = time.time()
        for k, v in saved.get("docs", {}).items():
            if now - v["made"] <= DOC_TTL:
                docs[int(k)] = v
        next_id[0] = max(saved.get("next_id", 1000), max(docs) if docs else 1000)
        print("loaded %d cached pages, next id %d" % (len(docs), next_id[0] + 1), flush=True)
    except (OSError, ValueError, KeyError):
        pass


def save_docs():
    """Called with docs_lock held."""
    tmp = DOC_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"next_id": next_id[0], "docs": docs}, f)
        os.replace(tmp, DOC_FILE)
    except OSError as e:
        print("could not save docs:", e, flush=True)


load_docs()

# ---- access keys and the rate limit ----------------------------------------------------------------
keys = {}            # key -> name
places = {}          # key -> the tester's town, for the weather and space-station pages
DEFAULT_PLACE = "Cincinnati, Ohio"      # Tim's home; LAN requests and keys without a place
current = threading.local()             # the place of the request being served
keys_mtime = [0]
counts = {}          # who -> [minute_start, n_minute, day_start, n_day]
counts_lock = threading.Lock()


def load_keys():
    try:
        m = os.path.getmtime(KEY_FILE)
    except OSError:
        keys.clear()
        return
    if m == keys_mtime[0]:
        return
    keys_mtime[0] = m
    keys.clear()
    with open(KEY_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                parts = line.split(None, 1)
                rest = parts[1] if len(parts) > 1 else parts[0][:4]
                name, _, where = rest.partition("|")
                keys[parts[0]] = name.strip()
                places[parts[0]] = where.strip() or DEFAULT_PLACE


# ---- REV E: self-made keys ------------------------------------------------------------------------
import re, hashlib
SELF_KEY = re.compile(r"^u[a-z2-9]{11}$")
ids_lock = threading.Lock()
new_times = []          # (time, ip-hash) of registrations, for the limits


def read_set(path):
    try:
        with open(path, encoding="utf-8") as f:
            return {l.split()[0] for l in f if l.split("#", 1)[0].strip()}
    except OSError:
        return set()


def self_key(key, client_ip):
    """A self-made key: let it in, register it, or raise Refused."""
    if key in read_set(BANNED_FILE):
        raise Refused("this copy has been switched off by the gateway's owner")
    with ids_lock:
        if key in read_set(IDS_FILE):
            return
        now = time.time()
        iph = hashlib.sha256(("lisaweb:" + client_ip).encode()).hexdigest()[:10]
        new_times[:] = [t for t in new_times if now - t[0] < 86400]
        if sum(1 for t in new_times if t[1] == iph and now - t[0] < 3600) >= NEW_PER_HOUR:
            raise Refused("too many new copies from here this hour; try again later")
        if len(new_times) >= NEW_PER_DAY:
            raise Refused("too many new copies today; try again tomorrow")
        new_times.append((now, iph))
        with open(IDS_FILE, "a", encoding="utf-8") as f:
            f.write("%s  %s  %s\n" % (key, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), iph))


def is_private(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private or a.is_loopback or a in ipaddress.ip_network("100.64.0.0/10")


def identify(handler, qs):
    """Who is asking, and are they allowed: returns a name for the log, or raises Refused."""
    load_keys()
    ip = handler.client_address[0]
    forwarded = handler.headers.get("X-Forwarded-For")
    key = qs.get("k", [""])[0].strip()
    current.place = places.get(key, DEFAULT_PLACE) if key else DEFAULT_PLACE
    # A town sent by the Lisa itself (&t=Paris, France) wins over the key's: this works on any
    # gateway, keyed or not (planned for Browser 0.2 / LisaFuji 0.6).
    current.pics = qs.get("pv", [""])[0] == "1"     # REV D (pictures): a Browser that can show them
    current.thumbs = current.pics and qs.get("tv", [""])[0] == "1"   # REV F: and icons on the page
    town = qs.get("t", [""])[0].strip()
    if town:
        if town == town.lower():                  # typed all in lower case: Cincinnati, Ohio
            town = " ".join(w[:1].upper() + w[1:] for w in town.split(" "))
        current.place = town[:60]
    if key:
        if key in keys:
            who = "key:" + keys[key]
        elif SELF_KEY.match(key):                  # REV E: a copy's own key
            client = (forwarded or ip).split(",")[0].strip()
            self_key(key, client)
            who = "id:" + key
        else:
            raise Refused("that access key is not known to this gateway")
    elif forwarded or not is_private(ip):
        raise Refused("needs an access key: Gateway menu (ask bmwcyclist)")
    else:
        who = "lan:" + ip
    now = time.time()
    with counts_lock:
        c = counts.setdefault(who, [now, 0, now, 0])
        if now - c[0] >= 60:
            c[0], c[1] = now, 0
        if now - c[2] >= 86400:
            c[2], c[3] = now, 0
        c[1] += 1
        c[3] += 1
        if c[1] > RATE_MINUTE:
            raise Refused("too many requests this minute; wait a little")
        if c[3] > RATE_DAY:
            raise Refused("this key has used its %d requests for today" % RATE_DAY)
    return who


def log_request(who, path, out):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("%s %-22s %-50s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), who, path[:50],
                                             out.split("\n", 1)[0][:60]))
    except OSError:
        pass


class Refused(Exception):
    pass


def ascii_text(s):
    s = unidecode(s or "")
    return "".join(ch if 32 <= ord(ch) < 127 or ch == "\n" else " " for ch in s)


def check_address(url):
    """Refuse anything that is not plain http/https to a public address."""
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise Refused("only http and https addresses")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror:
        raise Refused("no such site: " + p.hostname)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise Refused("that address is not on the public internet")


def fetch(url):
    check_address(url)
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"},
                     timeout=TIMEOUT, stream=True, allow_redirects=True)
    check_address(r.url)                      # redirects must stay public too
    body = b""
    for chunk in r.iter_content(65536):
        body += chunk
        if len(body) > MAX_BYTES:
            raise Refused("page too big (over 2 MB)")
    ctype = r.headers.get("Content-Type", "")
    r.encoding = r.encoding or "utf-8"
    text = body.decode(r.encoding, errors="replace")
    if r.status_code >= 400:
        raise Refused("the site answered %d" % r.status_code)
    return r.url, ctype, text


# ---------------------------------------------------------------- HTML to Lisa text

BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "blockquote", "pre", "table", "tr",
         "ul", "ol", "dl", "figure", "form", "center", "aside", "nav"}
HEAD = {"h1", "h2", "h3", "h4", "h5", "h6"}
SKIP = {"script", "style", "noscript", "svg", "canvas", "iframe", "button", "select", "option", "template", "head"}
# page furniture that only wastes a Lisa's screen (footnote markers, edit links, navigation boxes, reference lists)
SKIP_CLASSES = {"reference", "mw-editsection", "navbox", "reflist", "references", "noprint", "mw-jump-link",
                "sistersitebox", "metadata", "ambox", "mw-cite-backlink", "printfooter", "catlinks", "authority-control",
                "cookie-banner", "skip-link", "visually-hidden", "sr-only"}


# ---------------------------------------------------------------- pictures (REV D (pictures), 17-Oct-2026)
PIC_W, PIC_H, PIC_PAR = 576, 240, 1.45     # most of the Browser window, in Lisa pixels; their height/width
PIC_MAX_BYTES = 8 * 1024 * 1024
PIC_SKIP = ("logo", "icon", "sprite", "spacer", "pixel", "badge", "avatar", "emoji", "button", "1x1",
            "blank.gif", "tracking", "rss", "advert", "banner")


def pic_name(img):
    """What a picture is called: its alt text, else a caption, else its title.  Empty = decorative: skip it."""
    alt = (img.get("alt") or "").strip()
    if alt:
        return alt
    fig = img.find_parent("figure")
    if fig is not None:
        fc = fig.find("figcaption")
        if fc is not None and fc.get_text(strip=True):
            return fc.get_text(" ", strip=True)
    for cls in ("thumbcaption", "infobox-caption", "wp-caption-text", "caption"):
        box = img.find_parent(class_=("thumb", "thumbinner", "infobox", "wp-caption", "figure"))
        if box is not None:
            c = box.find(class_=cls)
            if c is not None and c.get_text(strip=True):
                return c.get_text(" ", strip=True)
    return (img.get("title") or "").strip()


def pic_src(img, base):
    """The picture's address; from a srcset, the smallest one at least PIC_W wide (or the largest)."""
    src = img.get("src") or img.get("data-src") or ""
    best = None
    for part in (img.get("srcset") or "").split(","):
        bits = part.split()
        if len(bits) == 2 and bits[1].endswith("w") and bits[1][:-1].isdigit():
            w = int(bits[1][:-1])
            if best is None or (best[0] < PIC_W and w > best[0]) or (PIC_W <= w < best[0]):
                best = (w, bits[0])
    if best:
        src = best[1]
    return urllib.parse.urljoin(base, src) if src else ""


def pic_useful(img, url):
    """Real pictures only: no data: or SVG, nothing tiny, no logos, icons, spacers or trackers."""
    if not url.startswith(("http://", "https://")):
        return False
    path = url.split("?")[0].lower()
    if path.endswith((".svg", ".ico")):
        return False
    for attr in ("width", "height"):
        v = str(img.get(attr) or "").strip()
        if v.isdigit() and int(v) < 48:
            return False
    if img.get("role") == "presentation" or img.get("aria-hidden") == "true":
        return False
    name = path.rsplit("/", 1)[-1] + " " + " ".join(img.get("class") or []).lower() + " " + (img.get("id") or "").lower()
    return not any(w in name for w in PIC_SKIP)


def atkinson_rows(im):
    """A grey PIL image -> list of rows of bytes, 1 = black, MSB = leftmost pixel, Atkinson-dithered."""
    w, h = im.size
    buf = [float(v) for v in im.getdata()]
    rows = []
    for y in range(h):
        row = bytearray(w // 8)
        base = y * w
        for x in range(w):
            i = base + x
            old = buf[i]
            black = old < 128
            err = (old - (0.0 if black else 255.0)) / 8.0
            if black:
                row[x >> 3] |= 0x80 >> (x & 7)
            if err:
                for dx, dy in ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and ny < h:
                        buf[ny * w + nx] += err
        rows.append(bytes(row))
    return rows


def enc_row(row):
    """One picture row as text: trailing white bytes dropped, then 6 bits a character, chr(48 + v)."""
    row = row.rstrip(b"\0")
    out = []
    for i in range(0, len(row), 3):
        g = row[i:i + 3].ljust(3, b"\0")
        v = (g[0] << 16) | (g[1] << 8) | g[2]
        out.append("".join(chr(48 + ((v >> s) & 63)) for s in (18, 12, 6, 0)))
    return "".join(out)


def pic_doc(link, cols, rows):
    url, _, label = link[4:].partition("\t")
    now = time.time()
    with docs_lock:
        for did, d in sorted(docs.items(), reverse=True):
            if d.get("kind") == "pic" and d.get("url") == url and not d.get("thumb") and now - d["made"] < 900:
                return did
    check_address(url)
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "image/*"}, timeout=TIMEOUT, stream=True)
    check_address(r.url)
    body = b""
    for chunk in r.iter_content(65536):
        body += chunk
        if len(body) > PIC_MAX_BYTES:
            raise Refused("that picture is too big (over 8 MB)")
    if r.status_code >= 400:
        raise Refused("the site answered %d for the picture" % r.status_code)
    try:
        im = Image.open(io.BytesIO(body))
        im.seek(0)
        im.load()
    except Exception:
        raise Refused("that is not a picture the gateway can read")
    if im.mode in ("RGBA", "LA", "P", "PA"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    im = im.convert("L")
    w, h = im.size
    sc = min(PIC_W / w, PIC_H * PIC_PAR / h, 2.0)
    nw, nh = max(8, int(w * sc)), max(1, int(round(h * sc / PIC_PAR)))
    im = im.resize((nw, nh), Image.LANCZOS)
    pw = (nw + 7) // 8 * 8
    canvas = Image.new("L", (pw, nh), 255)
    canvas.paste(im, (0, 0))
    data = [enc_row(rw) for rw in atkinson_rows(canvas)]
    host = urllib.parse.urlparse(r.url).hostname or ""
    title = ascii_text(label).strip()[:cols] or url.rsplit("/", 1)[-1][:cols]
    with docs_lock:
        next_id[0] += 1
        did = next_id[0]
        docs[did] = dict(kind="pic", title=title, host=host, url=url, w=pw, h=nh, data=data, lines=[], links=[],
                         cols=cols, rows=rows, made=time.time())
        save_docs()
    return did


def html_to_blocks(html, base):
    """-> (list of (kind, text) blocks, list of link URLs).  kind: 'p', 'h', 'li', 'pre'."""
    soup = BeautifulSoup(html, "lxml")
    page = base.split("#")[0]
    links, seen = [], {}
    blocks, cur = [], []

    def flush(kind="p"):
        t = re.sub(r"[ \t\r\n]+", " ", "".join(cur)).strip()
        cur.clear()
        if t:
            blocks.append((kind, t))

    def walk(node, kind="p"):
        for ch in node.children:
            if isinstance(ch, NavigableString):
                if ch.__class__.__name__ in ("Comment", "Doctype", "ProcessingInstruction"):
                    continue
                cur.append(str(ch))
                continue
            if not isinstance(ch, Tag):
                continue
            name = ch.name.lower()
            if name in SKIP:
                continue
            if SKIP_CLASSES.intersection(ch.get("class") or []) or ch.get("role") == "navigation" or ch.get("aria-hidden") == "true":
                continue
            if name == "br":
                cur.append(" ")
                continue
            if name == "img":
                label = re.sub(r"\s+", " ", pic_name(ch))[:56]   # REV E1: 56 so "[picture: ...] [nn]" fits a 76-column line
                if label:
                    src = pic_src(ch, base)
                    if getattr(current, "pics", False) and pic_useful(ch, src):
                        key = "pic:" + src
                        if key not in seen:
                            links.append(key + "\t" + label)
                            seen[key] = len(links)
                        cur.append(" [picture: %s] [%d] " % (label, seen[key]))
                    elif (ch.get("alt") or "").strip() or not getattr(current, "pics", False):
                        cur.append(" [picture: %s] " % label)   # REV E1: a logo or icon that only borrowed a
                continue                                        # caption gets no line (the infobox logo did)
            if name == "a" and ch.get("href"):
                href = urllib.parse.urljoin(base, ch["href"])
                label = ch.get_text(" ", strip=True)
                if href.startswith(("http://", "https://")) and label and href.split("#")[0] != page:
                    href = href.split("#")[0] or href
                    if href not in seen:
                        links.append(href)
                        seen[href] = len(links)
                    walk(ch, kind)
                    cur.append(" [%d]" % seen[href])
                    continue
            if name in HEAD:
                flush(kind); walk(ch, "h"); flush("h"); continue
            if name == "li":
                flush(kind); walk(ch, "li"); flush("li"); continue
            if name == "tr":
                flush(kind)
                cells = []
                for cell in ch.find_all(["th", "td"], recursive=False):
                    walk(cell, "row")
                    t = re.sub(r"\s+", " ", "".join(cur)).strip(); cur.clear()
                    if t: cells.append(t)
                if cells:
                    blocks.append(("row", (": " if len(cells) == 2 else "  ").join(cells)))
                continue
            if name in ("td", "th"):
                walk(ch, kind); cur.append("  "); continue
            if name in BLOCK:
                flush(kind); walk(ch, kind); flush(kind); continue
            walk(ch, kind)

    walk(soup.body or soup)
    flush()
    return blocks, links


def layout(blocks, cols):
    lines = []
    for kind, t in blocks:
        t = ascii_text(t).strip()
        if not t:
            continue
        if kind == "h":
            if lines and lines[-1] != "":
                lines.append("")
            for w in textwrap.wrap(t.upper(), cols):
                lines.append(w)
            lines.append("")
        elif kind == "row":
            ws = textwrap.wrap(t, cols - 2)
            for i, w in enumerate(ws):
                lines.append(w if i == 0 else "  " + w)
        elif kind == "li":
            ws = textwrap.wrap(t, cols - 2)
            for i, w in enumerate(ws):
                lines.append(("- " if i == 0 else "  ") + w)
        else:
            lines.extend(textwrap.wrap(t, cols))
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    # never two blank lines in a row
    out = []
    for l in lines:
        if l == "" and out and out[-1] == "":
            continue
        out.append(l)
    return out or ["(this page has no text)"]


# ---------------------------------------------------------------- gateway-made pages
_coords = {"Cincinnati, Ohio": (39.1031, -84.5120)}


def here():
    return getattr(current, "place", DEFAULT_PLACE) or DEFAULT_PLACE


def place_coords(place):
    """Latitude and longitude of a town, from wttr.in's own lookup; cached."""
    if place not in _coords:
        j = requests.get("https://wttr.in/" + urllib.parse.quote(place) + "?format=j1",
                         headers={"User-Agent": "curl"}, timeout=TIMEOUT).json()
        a = j["nearest_area"][0]
        _coords[place] = (float(a["latitude"]), float(a["longitude"]))
    return _coords[place]


def iss_page(cols, rows):
    import json, math, datetime
    r = requests.get("https://api.wheretheiss.at/v1/satellites/25544", headers={"User-Agent": UA}, timeout=TIMEOUT)
    j = r.json()
    lat, lon, alt, vel = j["latitude"], j["longitude"], j["altitude"], j["velocity"]
    when = datetime.datetime.utcfromtimestamp(j["timestamp"]).strftime("%H:%M:%S UTC, %d %B %Y")
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    # great-circle distance from home
    HOME_NAME = here()
    HOME_LAT, HOME_LON = place_coords(HOME_NAME)
    p1, p2 = math.radians(HOME_LAT), math.radians(lat)
    dl = math.radians(lon - HOME_LON)
    d = 6371 * math.acos(max(-1, min(1, math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl))))
    horizon = j.get("footprint", 4500) / 2
    lines = ["The International Space Station, right now (wheretheiss.at)", "",
             "Time       %s" % when,
             "Position   %.2f %s, %.2f %s" % (abs(lat), ns, abs(lon), ew),
             "Altitude   %.0f km  (%.0f miles)" % (alt, alt * 0.6214),
             "Speed      %s km/h  (%s mph)" % (format(int(vel), ","), format(int(vel * 0.6214), ",")),
             "Sunlight   %s" % ("in daylight" if j.get("visibility") == "daylight" else "in the Earth's shadow"),
             "",
             "From %s it is %s km away: %s." % (HOME_NAME, format(int(d), ","),
                                                "ABOVE the horizon now" if d < horizon else "below the horizon"),
             "The station circles the Earth every 93 minutes; R fetches a fresh position.",
             "",
             "Who is aboard the space stations now [1]"]
    return store("Where is the ISS", "wheretheiss.at", "lisaweb:iss", lines, ["lisaweb:crew"], cols, rows)


def crew_page(cols, rows):
    """Who is in orbit, station by station (REV D.1, 17-Oct-2026)."""
    j = requests.get(CREW_URL, headers={"User-Agent": UA}, timeout=TIMEOUT).json()
    people = j.get("people", [])
    lines = ["%d people are in orbit right now." % j.get("number", len(people)), ""]
    iss = [q for q in people if q.get("iss")]
    other = {}
    for q in people:
        if not q.get("iss"):
            other.setdefault(q.get("spacecraft") or "another spacecraft", []).append(q)
    if iss:
        exp = j.get("iss_expedition")
        lines.append(("THE INTERNATIONAL SPACE STATION" + (", EXPEDITION %s" % exp if exp else "")).upper())
        for q in iss:
            lines.append("  %s, %s  (%s; came on %s)" % (ascii_text(q.get("name", "")), ascii_text(q.get("position", "")),
                                                        ascii_text(q.get("country", "")), ascii_text(q.get("spacecraft", ""))))
        lines.append("")
    for craft, qs in other.items():
        name = ascii_text(craft)
        if name.lower().startswith("shenzhou"):
            name = "Tiangong (%s)" % name        # China's crews live on their station
        lines.append(("ON " + name).upper())
        for q in qs:
            lines.append("  %s, %s  (%s)" % (ascii_text(q.get("name", "")), ascii_text(q.get("position", "")),
                                            ascii_text(q.get("country", ""))))
        lines.append("")
    lines.append("From the people-in-space list at corquaid.github.io.")
    wrapped = []
    for l in lines:
        wrapped.extend(textwrap.wrap(l, cols, subsequent_indent="    ") or [""])
    return store("Who is aboard the space stations", "corquaid.github.io", "lisaweb:crew", wrapped, [], cols, rows)


def weather_page(cols, rows):
    fmt = ("%l%0A%C, %t (feels like %f)%0AHumidity %h, wind %w, precipitation %p, pressure %P"
           "%0ASunrise %S, sunset %s, moon day %M, UV index %u")
    town = urllib.parse.quote(here())
    r = requests.get("https://wttr.in/" + town + "?format=" + fmt, headers={"User-Agent": "curl"}, timeout=TIMEOUT)
    try:
        j = requests.get("https://wttr.in/" + town + "?format=j1", headers={"User-Agent": "curl"}, timeout=TIMEOUT).json()
    except Exception:
        j = None
    text = r.text.strip()
    # 17-Oct-2026: wttr.in shows the wind as an arrow, which the Lisa cannot draw ("|11mph"): say it in words,
    # from the j1 data (the compass point the wind blows FROM).
    m = re.search(r"wind ([←-⇿])\s*([0-9]+\s*[a-z/]+)", text)
    if m:
        frm = ""
        try:
            frm = " from the " + j["current_condition"][0]["winddir16Point"]
        except Exception:
            pass
        text = text.replace(m.group(0), "wind " + m.group(2).replace("mph", " mph").replace("km/h", " km/h") + frm)
    lines = ["The weather now (wttr.in)", ""] + [ascii_text(l) for l in text.splitlines()]
    try:
        lines += ["", "The next three days (noon):"]
        for day in j["weather"][:3]:
            noon = day["hourly"][4] if len(day["hourly"]) > 4 else day["hourly"][-1]
            lines.append("  %s  %s to %s F, %s, rain %s%%" % (
                day["date"], day["mintempF"], day["maxtempF"], ascii_text(noon["weatherDesc"][0]["value"]), noon["chanceofrain"]))
    except Exception:
        lines += ["", "(The forecast could not be read.)"]
    return store(("The weather in " + here().split(",")[0])[:cols], "wttr.in", "lisaweb:weather", lines, [], cols, rows)


def make_doc(url, cols, rows):
    if url == "lisaweb:iss":
        return iss_page(cols, rows)
    if url == "lisaweb:weather":
        return weather_page(cols, rows)
    if url == "lisaweb:crew":
        return crew_page(cols, rows)
    # REV C.3 (2026-10-16): the same address asked again within 15 minutes is answered from the
    # cache at once.  A FujiNet gives the first STATUS after an OPEN about 5 s; a cold fetch of a
    # big page through the Pi takes about that long, so a retry (R) must not fetch again.
    now = time.time()
    with docs_lock:
        for did, d in sorted(docs.items(), reverse=True):
            if d.get("url") in (url, url.rstrip("/")) and d["cols"] == cols and d["rows"] == rows and d.get("pics", False) == getattr(current, "pics", False) and d.get("thumbs", False) == getattr(current, "thumbs", False) and now - d["made"] < 900:
                return did
    return fetch_doc(url, cols, rows)


THUMB_W, THUMB_H = 96, 48        # REV F: the icon, Lisa pixels (three 16-pixel text rows high)
SLOT_RE = re.compile(r"\[picture: [^\]]*\] \[(\d+)\]")


def add_thumb_slots(lines, rows):
    """REV F: after each line with a picture link put "~T n 96 48" and empty lines for the icon's other rows,
    and keep the block on one page (pad with empty lines when fewer rows are left than the block needs)."""
    extra = (THUMB_H + 15) // 16 - 1            # empty lines after the slot line
    block = 2 + extra                             # the text line, the slot line, the extra lines
    out = []
    for line in lines:
        m = SLOT_RE.search(line)
        if not m:
            out.append(line)
            continue
        while len(out) % rows > rows - block:
            out.append("")
        out.append(line)
        out.append("~T %s %d %d" % (m.group(1), THUMB_W, THUMB_H))
        out.extend([""] * extra)
    return out


def thumb_doc(link, tw, th, cols, rows):
    """REV F: the icon of a picture link, as a pic document tw x th (white field, top left)."""
    url = link[4:].partition("\t")[0]
    now = time.time()
    with docs_lock:
        for did, d in sorted(docs.items(), reverse=True):
            if d.get("kind") == "pic" and d.get("url") == url and d.get("w") == tw and d.get("h") == th \
                    and d.get("thumb") and now - d["made"] < 900:
                return did
    big = pic_doc(link, cols, rows)                       # fetched and cached at full size once
    d = docs[big]
    im = Image.new("L", (d["w"], d["h"]), 255)
    rowsb = [dec_row(r, d["w"]) for r in d["data"]]
    for y, rb in enumerate(rowsb):
        for x in range(d["w"]):
            if rb[x // 8] & (128 >> (x % 8)):
                im.putpixel((x, y), 0)
    sc = min(tw / d["w"], th / d["h"])
    nw, nh = max(1, int(d["w"] * sc)), max(1, int(d["h"] * sc))
    small = im.resize((nw, nh), Image.LANCZOS)
    field = Image.new("L", (tw, th), 255)
    field.paste(small, (0, 0))
    data = [enc_row(rw) for rw in atkinson_rows(field)]
    with docs_lock:
        next_id[0] += 1
        did = next_id[0]
        docs[did] = dict(kind="pic", thumb=True, title=d["title"], host=d["host"], url=url, w=tw, h=th, data=data,
                         lines=[], links=[], cols=cols, rows=rows, made=time.time())
        save_docs()
    return did


def dec_row(text, w):
    """REV F: the inverse of enc_row: 4 characters -> 3 bytes, padded to w/8 bytes."""
    out = bytearray()
    for i in range(0, len(text), 4):
        g = text[i:i + 4].ljust(4, "0")
        v = 0
        for ch in g:
            v = v * 64 + max(0, min(63, ord(ch) - 48))
        out += bytes(((v >> 16) & 255, (v >> 8) & 255, v & 255))
    return bytes(out[:w // 8].ljust(w // 8, b"\0"))


def fetch_doc(url, cols, rows):
    final, ctype, text = fetch(url)
    host = urllib.parse.urlparse(final).hostname or ""
    if "html" not in ctype and "<html" not in text[:2000].lower():
        title = final.rsplit("/", 1)[-1] or host
        lines = []
        for para in text.splitlines():
            lines.extend(textwrap.wrap(ascii_text(para), cols) or [""])
        links = []
    else:
        try:
            d = Document(text)
            title = d.short_title() or ""
            main = d.summary(html_partial=True)
            blocks, links = html_to_blocks(main, final)
            if sum(len(t) for _, t in blocks) < 400:          # extraction lost the page: use all of it
                blocks, links = html_to_blocks(text, final)
        except Exception:
            title = ""
            blocks, links = html_to_blocks(text, final)
        if not title:
            t = BeautifulSoup(text, "lxml").title
            title = t.get_text(strip=True) if t else host
        lines = layout(blocks, cols)
        if getattr(current, "thumbs", False):                 # REV F
            lines = add_thumb_slots(lines, rows)
    return store(ascii_text(title).strip()[:cols], host, final, lines, links, cols, rows)


def store(title, host, url, lines, links, cols, rows):
    with docs_lock:
        now = time.time()
        for k in [k for k, v in docs.items() if now - v["made"] > DOC_TTL]:
            del docs[k]
        next_id[0] += 1
        did = next_id[0]
        docs[did] = dict(title=title, host=host, url=url, lines=lines, links=links, cols=cols, rows=rows, made=now,
                         pics=getattr(current, "pics", False), thumbs=getattr(current, "thumbs", False))
        save_docs()
    return did


def render(did, page):
    d = docs.get(did)
    if not d:
        raise Refused("that page has expired; open it again")
    if d.get("kind") == "pic":
        head = ["P%d %d %d" % (did, d["w"], d["h"]), d["title"],
                ("%s   picture %d x %d" % (d["host"], d["w"], d["h"]))[:d["cols"]]]
        return "\n".join(head + d["data"]) + "\n"
    rows = d["rows"]
    pages = max(1, (len(d["lines"]) + rows - 1) // rows)
    if page < 1 or page > pages:
        raise Refused("page %d of %d is out of range" % (page, pages))
    body = d["lines"][(page - 1) * rows: page * rows]
    head = ["D%d %d/%d" % (did, page, pages), d["title"],
            ("%s   %d links" % (d["host"], len(d["links"])))[:d["cols"]]]
    return "\n".join(head + body) + "\n"


def home(cols, rows):
    lines = ["Welcome to LisaWeb.  Type a link's number and press RETURN.", ""]
    for i, (name, _) in enumerate(HOME_LINKS, 1):
        name = name.replace("Columbus", here().split(",")[0])
        lines.append("%s [%d]" % (name, i))
    lines += ["", "G = go to an address    S = search Wikipedia"]
    return store("LisaWeb start page", "lisaweb gateway", "home", lines, [u for _, u in HOME_LINKS], cols, rows)


def find(q, cols, rows):
    r = requests.get("https://en.wikipedia.org/w/api.php",
                     params={"action": "opensearch", "search": q, "limit": 12, "namespace": 0, "format": "json"},
                     headers={"User-Agent": UA}, timeout=TIMEOUT)
    data = r.json()
    names, urls = data[1], data[3]
    lines = ["Wikipedia articles for: " + ascii_text(q)[:cols - 25], ""]
    for i, name in enumerate(names, 1):
        lines.append("%s [%d]" % (ascii_text(name)[:cols - 6], i))
    if not names:
        lines.append("Nothing found.")
    return store("Search: " + ascii_text(q)[:cols - 8], "en.wikipedia.org", "search", lines, list(urls), cols, rows)


# ---------------------------------------------------------------- the web service

def size(qs):
    m = re.fullmatch(r"(\d+)x(\d+)", (qs.get("ps", ["%dx%d" % (COLS, ROWS)])[0]))
    if not m:
        return COLS, ROWS
    c, r = int(m.group(1)), int(m.group(2))
    return max(20, min(c, 132)), max(4, min(r, 40))


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        # Query parameters glued to the path with '&' (a client that forgot the '?', possibly
        # percent-encoded on the way) are taken as the query (REV C.1, 2026-10-16).
        path = urllib.parse.unquote(u.path)
        if "&" in path:
            path, extra = path.split("&", 1)
            for k, v in urllib.parse.parse_qs(extra).items():
                qs.setdefault(k, v)
        u = u._replace(path=path)
        cols, rows = size(qs)
        who = "?"
        try:
            who = identify(self, qs)
            if u.path == "/w/home":
                out = render(home(cols, rows), 1)
            elif u.path == "/w/open":
                addr = qs.get("u", [""])[0].strip()
                guessed = not re.match(r"^https?://", addr, re.I)
                if guessed:
                    addr = "https://" + addr
                try:
                    out = render(make_doc(addr, cols, rows), 1)
                except requests.exceptions.SSLError:
                    # a site whose certificate is wrong for its name (68k.news, 2026-10-16):
                    # when we chose https ourselves, try plain http before giving up
                    if not guessed:
                        raise
                    out = render(make_doc("http://" + addr[8:], cols, rows), 1)
            elif u.path == "/w/page":
                out = render(int(qs["d"][0]), int(qs.get("p", ["1"])[0]))
            elif u.path == "/w/link":
                d = docs.get(int(qs["d"][0]))
                if not d:
                    raise Refused("that page has expired; open it again")
                n = int(qs["n"][0])
                if n < 1 or n > len(d["links"]):
                    raise Refused("there is no link %d on that page" % n)
                target = d["links"][n - 1]
                if target.startswith("pic:"):
                    out = render(pic_doc(target, d["cols"], d["rows"]), 1)
                else:
                    out = render(make_doc(target, d["cols"], d["rows"]), 1)
            elif u.path == "/w/thumb":                              # REV F: the icon of picture link n
                d = docs.get(int(qs["d"][0]))
                if not d:
                    raise Refused("that page has expired; open it again")
                n = int(qs["n"][0])
                if n < 1 or n > len(d["links"]) or not d["links"][n - 1].startswith("pic:"):
                    raise Refused("there is no picture %d on that page" % n)
                tw = max(8, min(int(qs.get("tw", [str(THUMB_W)])[0]) // 8 * 8, 576))
                th = max(1, min(int(qs.get("th", [str(THUMB_H)])[0]), 240))
                out = render(thumb_doc(d["links"][n - 1], tw, th, d["cols"], d["rows"]), 1)
            elif u.path == "/w/find":
                out = render(find(qs.get("q", [""])[0], cols, rows), 1)
            elif u.path == "/w/links":
                d = docs.get(int(qs["d"][0]))
                if not d:
                    raise Refused("that page has expired; open it again")
                p = int(qs.get("p", ["1"])[0])
                body = "\n".join(d["lines"][(p - 1) * d["rows"]: p * d["rows"]])
                nums = sorted({int(x) for x in re.findall(r"\[(\d+)\]", body)})
                def lname(t):
                    return ("picture: " + t[4:].partition("\t")[2]) if t.startswith("pic:") else t
                lines = ["[%d] %s" % (n, lname(d["links"][n - 1])[:d["cols"] - 6]) for n in nums if 0 < n <= len(d["links"])]
                # the same three header lines as every other reply, so the Lisa parses it the same way
                pages = max(1, (len(d["lines"]) + d["rows"] - 1) // d["rows"])
                head = ["D%d %d/%d" % (int(qs["d"][0]), p, pages), ("Links on page %d: %s" % (p, d["title"]))[:d["cols"]],
                        ("%s   %d links" % (d["host"], len(d["links"])))[:d["cols"]]]
                out = "\n".join(head + (lines or ["No links on this page."])) + "\n"
            else:
                raise Refused("unknown request")
        except Refused as e:
            out = "ERROR: %s\n" % e
        except requests.Timeout:
            out = "ERROR: the site did not answer in %d seconds\n" % TIMEOUT
        except (KeyError, ValueError):
            out = "ERROR: a number is missing or wrong in the request\n"
        except Exception as e:
            out = "ERROR: could not read that page (%s)\n" % type(e).__name__
        log_request(who, u.path + ("?" + u.query if u.query else ""), out)
        data = ascii_text(out).encode("ascii", "replace")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=us-ascii")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print("LisaWeb gateway REV C on port %d (%d keys)" % (port, (load_keys() or len(keys))), flush=True)
    http.server.ThreadingHTTPServer((sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1", port), Handler).serve_forever()
