"""gw_ids.py  20-Oct-2026: the self-made Browser keys the LisaWeb gateway has seen (REV E).  Run beside gateway.py.
    python3 gw_ids.py              list them: key, first seen, requests in the log, banned or not
    python3 gw_ids.py ban KEY      switch that copy off (written to ids_banned.txt; takes effect at once)
    python3 gw_ids.py unban KEY    switch it on again
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
IDS, BANNED, LOG = (os.path.join(HERE, f) for f in ("ids.txt", "ids_banned.txt", "requests.log"))


def lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [l.rstrip("\n") for l in f if l.split("#", 1)[0].strip()]
    except OSError:
        return []


banned = {l.split()[0] for l in lines(BANNED)}
if len(sys.argv) == 3 and sys.argv[1] in ("ban", "unban"):
    key = sys.argv[2].strip()
    if sys.argv[1] == "ban":
        banned.add(key)
    else:
        banned.discard(key)
    with open(BANNED, "w", encoding="utf-8") as f:
        f.writelines(k + "\n" for k in sorted(banned))
    print(sys.argv[1] + "ned", key)
    sys.exit(0)
counts = {}
for l in lines(LOG):
    for part in l.split():
        if part.startswith("id:"):
            counts[part[3:]] = counts.get(part[3:], 0) + 1
rows = lines(IDS)
print("%d self-made keys (%d banned)" % (len(rows), len(banned)))
for l in rows:
    k, first = (l.split() + ["", ""])[:2]
    print("  %-14s first %-22s requests %-6d %s" % (k, first, counts.get(k, 0), "BANNED" if k in banned else ""))
