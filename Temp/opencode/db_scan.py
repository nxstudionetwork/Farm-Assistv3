import sys, re, struct

path = sys.argv[1]
with open(path, "rb") as f:
    data = f.read()

PAGE = 4096
npages = len(data) // PAGE
print(f"size={len(data)} pages={npages}")

# Count valid b-tree page types
from collections import Counter
tcount = Counter()
valid_pages = []
for i in range(npages):
    p = data[i * PAGE:(i + 1) * PAGE]
    t = p[0]
    if t in (0x02, 0x05, 0x0a, 0x0d):
        tcount[hex(t)] += 1
        valid_pages.append(i)
    else:
        tcount[f"bad:{hex(t)}"] += 1
print("page type counts:", dict(tcount))

# Scan for date-like strings to gauge recency (2026-09-xx and 2026-1x)
text = data.decode("latin-1")
dates = re.findall(r"2026-(\d{2})-(\d{2})", text)
from collections import Counter as C2
print("date matches (by month):", dict(C2([d[0] for d in dates])))
months = sorted(set(int(d[0]) for d in dates))
print("months present:", months)

# Look for row-start sentinels of CREATE TABLE statements in page 1 area
m = re.findall(rb"CREATE TABLE [a-z_]+", data[:200000])
print("CREATE TABLE in first 200KB:", [x.decode() for x in m[:10]])

# search entire file for CREATE TABLE
allct = re.findall(rb"CREATE TABLE ([a-z_]+)", data)
print("total CREATE TABLE found in file:", len(allct))
print("sample:", sorted(set(x.decode() for x in allct))[:40])