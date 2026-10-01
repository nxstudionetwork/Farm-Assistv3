import sys

path = sys.argv[1]
with open(path, "rb") as f:
    head = f.read(100)
    f.seek(0, 2)
    size = f.tell()

print("size:", size)
print("header magic:", head[:16])
if head[:16] == b"SQLite format 3\x00":
    page_size = int.from_bytes(head[16:18], "big")
    print("page_size:", page_size)
    print("pages:", size / page_size if page_size else "?")
    print("write_version:", head[18], head[19])
    print("freelist_head:", int.from_bytes(head[32:36], "big"))
    print("schema_cookie:", int.from_bytes(head[40:44], "big"))
    print("usable_size:", int.from_bytes(head[20:22], "big"))
else:
    print("NOT a sqlite header")