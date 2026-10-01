import sys, sqlite3, struct

path = sys.argv[1]

# Try opening with various recovery pragmas / modes
modes = [
    ("default", lambda: sqlite3.connect(path)),
    ("immutable", lambda: sqlite3.connect(f"file:{path}?immutable=1", uri=True)),
    ("readonly", lambda: sqlite3.connect(f"file:{path}?mode=ro", uri=True)),
]
for name, factory in modes:
    try:
        con = factory()
        con.execute("PRAGMA writable_schema=ON")
        rows = con.execute("SELECT type,name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"[{name}] tables:", len(rows))
        if rows:
            for r in rows[:10]:
                print("   ", r)
        con.close()
    except Exception as e:
        print(f"[{name}] ERR:", e)

# Raw page-1 parse: try to read the sqlite_master b-tree manually
print("\n--- raw page 1 scan ---")
with open(path, "rb") as f:
    page = f.read(4096)
ptype = page[0]
print("page1 type (0x0d=leaf table):", hex(ptype))
hdr_off = 100
ncell = struct.unpack(">H", page[hdr_off + 3:hdr_off + 5])[0]
print("cell count:", ncell)
cell_ptrs = [struct.unpack(">H", page[hdr_off + 8 + 2 * i:hdr_off + 10 + 2 * i])[0] for i in range(min(ncell, 200))]

def varint(buf, off):
    val = 0
    for i in range(9):
        b = buf[off + i]
        if i == 8:
            val = (val << 8) | b
            return val, off + 9
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, off + i + 1
    return val, off + 9

count = 0
for cp in cell_ptrs:
    try:
        off = cp
        plen, off = varint(page, off)
        rowid, off = varint(page, off)
        rec = page[off:off + plen]
        # parse record header
        rec_hdr_len, p = varint(rec, 0)
        serials = []
        while p < rec_hdr_len:
            s, p = varint(rec, p)
            serials.append(s)
        # first column is type, second is name
        # serial types: text >=13 odd, etc. Decode loosely
        idx = rec_hdr_len
        vals = []
        for s in serials:
            if s == 0:
                vals.append(None)
            elif 1 <= s <= 6:
                widths = {1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 6: 8}
                w = widths[s]
                vals.append(int.from_bytes(rec[idx:idx + w], "big", signed=(s % 2 == 1)))
                idx += w
            elif s == 7:
                vals.append(struct.unpack(">d", rec[idx:idx + 8])[0]); idx += 8
            elif s == 8:
                vals.append(0); idx += 1
            elif s == 9:
                vals.append(1); idx += 1
            elif s >= 12:
                n = (s - 12) // 2
                vals.append(rec[idx:idx + n].decode("utf-8", "replace")); idx += n
            else:
                vals.append(None)
        if len(vals) >= 2:
            print("  ", vals[0], "|", str(vals[1])[:60])
            count += 1
    except Exception as e:
        pass
print("decoded rows:", count)