import os
root = "uploads/farmbuzz"
for dp, dn, fn in os.walk(root):
    for f in fn[:30]:
        fp = os.path.join(dp, f)
        print(fp, os.path.getsize(fp))
    if len(fn) > 0:
        break
# list one level
for dp, dn, fn in os.walk(root):
    print(dp, len(fn), "files")
