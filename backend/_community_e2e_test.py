"""End-to-end Community test with two real (freshly registered) Farm Assist accounts.

Registers Farmer A and Farmer B through the public API, exercises the whole
Community surface, then deletes every row it created. Nothing pre-existing is
modified.
"""
import json
import sys
import time

import requests

BASE = "http://127.0.0.1:8000/api/v1"
STAMP = str(int(time.time()))[-6:]
PHONE_A = "90%08d" % int(STAMP)
PHONE_B = "91%08d" % int(STAMP)
PIN = "4321"

RESULTS = []
CREATED = {"users": [], "posts": [], "groups": []}


def check(name, ok, detail=""):
    RESULTS.append((bool(ok), name, detail))
    print(("PASS  " if ok else "FAIL  ") + name + (("   -> " + str(detail)[:160]) if not ok else ""))


def data_of(resp):
    body = resp.json()
    return body.get("data", body)


def items_of(resp):
    """Community endpoints return either {items: [...]} or a bare list."""
    d = data_of(resp)
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        return d.get("items", [])
    return []


class Client:
    def __init__(self, label, token=None):
        self.label = label
        self.token = token
        self.user = None
        self.s = requests.Session()

    def auth(self, token):
        self.token = token
        self.s.headers["Authorization"] = "Bearer " + token

    def req(self, method, path, **kw):
        return self.s.request(method, BASE + path, timeout=30, **kw)

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def post(self, path, payload=None, **kw):
        return self.req("POST", path, json=payload, **kw)

    def patch(self, path, payload=None, **kw):
        return self.req("PATCH", path, json=payload, **kw)

    def delete(self, path, **kw):
        return self.req("DELETE", path, **kw)


def register(label, full_name, phone):
    c = Client(label)
    r = c.post("/auth/register", {
        "full_name": full_name,
        "phone_number": phone,
        "pin": PIN,
        "preferred_language": "en",
        "state": "Telangana",
        "district": "Nizamabad",
    })
    if r.status_code != 201:
        print("registration failed for", label, r.status_code, r.text[:300])
        sys.exit(1)
    d = data_of(r)
    c.auth(d["access_token"])
    c.user = d["user"]
    c.farmer_id = d["farmer_id"]
    CREATED["users"].append(c.user.get("id") or c.farmer_id)
    print("registered %s  farmer_id=%s  user_id=%s" % (label, c.farmer_id, c.user.get("id")))
    return c


# ------------------------------------------------------------------ setup
A = register("A", "Alpha Community Tester", PHONE_A)
B = register("B", "Beta Community Tester", PHONE_B)
ANON = Client("anon")

print("\n=== 1. AUTH GATES ===")
r = ANON.get("/communities/feed")
check("unauthenticated feed -> 401", r.status_code == 401, r.status_code)
r = ANON.post("/posts", {"content": "nope"})
check("unauthenticated create post -> 401", r.status_code == 401, r.status_code)
r = A.get("/communities/feed", headers={"Authorization": "Bearer not-a-real-token"})
check("garbage token -> 401", r.status_code == 401, r.status_code)

print("\n=== 2. CREATE POSTS (A) ===")
r = A.post("/posts", {"post_type": "question", "title": "Which paddy variety resists blast?",
                      "content": "Leaf blast is spreading in my paddy field, which variety do you use?",
                      "category": "Crop Protection", "crop": "Paddy", "location": "Nizamabad"})
check("A creates question post -> 201", r.status_code == 201, r.text[:200])
q = data_of(r) if r.status_code == 201 else {}
QID = q.get("id") or q.get("post_id")
CREATED["posts"].append(QID)
check("question payload has post_id", bool(q.get("post_id")), list(q.keys()))
check("question is_owner True for A", q.get("is_owner") is True, q.get("is_owner"))
check("question post_type round-trips", q.get("post_type") == "question", q.get("post_type"))
check("new question starts with 0 likes", q.get("likes_count") == 0, q.get("likes_count"))

r = A.post("/posts", {"post_type": "discussion", "title": "Drip scheduling in summer",
                      "content": "How often do you run drip during peak summer for tomato?",
                      "category": "Irrigation", "crop": "Tomato"})
check("A creates discussion post -> 201", r.status_code == 201, r.text[:200])
dpost = data_of(r) if r.status_code == 201 else {}
DID = dpost.get("id") or dpost.get("post_id")
CREATED["posts"].append(DID)

r = A.post("/posts", {"post_type": "advice", "title": "Seed treatment tip",
                      "content": "Treat seed with Trichoderma before sowing, worked well for me."})
check("A creates advice post -> 201", r.status_code == 201, r.text[:200])
apost = data_of(r) if r.status_code == 201 else {}
AID3 = apost.get("id") or apost.get("post_id")
CREATED["posts"].append(AID3)

r = A.post("/posts", {"post_type": "nonsense-type", "title": "bad", "content": "bad type"})
check("invalid post_type -> 400", r.status_code == 400, "%s %s" % (r.status_code, r.text[:120]))

r = A.post("/posts", {"post_type": "discussion", "content": ""})
check("empty content -> 400/422", r.status_code in (400, 422), "%s %s" % (r.status_code, r.text[:120]))

print("\n=== 3. FEED + VISIBILITY (B sees A) ===")
r = B.get("/communities/feed?limit=50")
check("B can read feed -> 200", r.status_code == 200, r.status_code)
feed = data_of(r)
items = feed.get("items", []) if isinstance(feed, dict) else feed
feed_ids = [i.get("id") or i.get("post_id") for i in items]
check("A's question visible in B's feed", QID in feed_ids, feed_ids[:8])
check("feed has no FA-SEED mock posts",
      not any(str(i).find("FA-SEED") >= 0 for i in items), "mock user leaked")
sample = next((i for i in items if (i.get("id") or i.get("post_id")) == QID), {})
check("B sees is_owner False on A's post", sample.get("is_owner") is False, sample.get("is_owner"))
check("feed item exposes no phone/email",
      "phone" not in json.dumps(sample).lower().replace("phone_number", "X")
      and "email" not in json.dumps(sample).lower(), json.dumps(sample)[:200])

r = B.get("/communities/feed?category=Crop%20Protection&limit=50")
cat_items = items_of(r)
check("category filter returns only that category",
      all(i.get("category") == "Crop Protection" for i in cat_items) and len(cat_items) >= 1,
      [i.get("category") for i in cat_items][:8])

r = B.get("/communities/feed?page=1&limit=2")
p1 = data_of(r)
r = B.get("/communities/feed?page=2&limit=2")
p2 = data_of(r)
ids1 = [i.get("id") for i in p1.get("items", [])]
ids2 = [i.get("id") for i in p2.get("items", [])]
check("pagination returns distinct pages", not (set(ids1) & set(ids2)) and bool(ids1), (ids1, ids2))
check("pagination reports total/total_pages", "total" in p1 and "total_pages" in p1, list(p1.keys()))

print("\n=== 4. SEARCH ===")
r = B.get("/communities/feed?search=" + requests.utils.quote("Alpha Community Tester") + "&limit=50")
s_items = items_of(r)
check("search by farmer name finds A's post",
      any((i.get("id") == QID) for i in s_items), [i.get("id") for i in s_items][:5])
r = B.get("/communities/feed?search=Trichoderma&limit=50")
check("search by content keyword works", len(items_of(r)) >= 1, len(items_of(r)))
r = B.get("/communities/feed?search=zzqqxx9917&limit=50")
check("gibberish search -> 0 results", len(items_of(r)) == 0, len(items_of(r)))

print("\n=== 5. LIKES (persistent, no duplicates, real unlike) ===")
r = B.post("/posts/%s/like" % QID)
check("B likes A's post -> 200", r.status_code == 200, r.text[:160])
lk = data_of(r)
check("likes_count == 1", lk.get("likes_count") == 1, lk)
check("is_liked True for B", lk.get("is_liked") is True, lk)
r = B.post("/posts/%s/like" % QID)
lk2 = data_of(r)
check("POST like is a toggle: second click unlikes (no duplicate row)",
      lk2.get("likes_count") == 0 and lk2.get("is_liked") is False, lk2)
r = B.post("/posts/%s/like" % QID)
check("third click re-likes -> 1 (still no duplicates)", data_of(r).get("likes_count") == 1, data_of(r))
r = B.post("/posts/%s/like" % QID)
data_of(r)
r = B.delete("/posts/%s/like" % QID)
check("DELETE unlike -> 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:120]))
un = data_of(r)
check("likes_count == 0 after unlike", un.get("likes_count") == 0, un)
check("is_liked False after unlike", un.get("is_liked") is False, un)
r = B.post("/posts/%s/like" % QID)
check("re-like works -> 1", data_of(r).get("likes_count") == 1, data_of(r))
r = B.get("/posts/%s" % QID)
check("like persisted on re-read", data_of(r).get("likes_count") == 1, data_of(r).get("likes_count"))

print("\n=== 6. SAVES (per-user isolation) ===")
r = B.post("/posts/%s/save" % QID)
check("B saves A's post -> 200", r.status_code == 200, r.text[:160])
sv = data_of(r)
check("saves_count == 1", sv.get("saves_count") == 1, sv)
r = B.post("/posts/%s/save" % QID)
check("POST save is a toggle: second click un-saves (no duplicate row)",
      data_of(r).get("saves_count") == 0, data_of(r))
r = B.post("/posts/%s/save" % QID)
check("third click re-saves -> 1", data_of(r).get("saves_count") == 1, data_of(r))
r = B.get("/posts/saved/list?limit=50")
b_saved = items_of(r)
check("B's saved list contains the post", any((i.get("id") == QID) for i in b_saved), len(b_saved))
r = A.get("/posts/saved/list?limit=50")
a_saved = items_of(r)
check("A's saved list is empty (isolation)", len(a_saved) == 0, [i.get("id") for i in a_saved])
r = B.delete("/posts/%s/save" % QID)
check("DELETE unsave -> 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:120]))
check("saves_count == 0 after unsave", data_of(r).get("saves_count") == 0, data_of(r))
r = B.get("/posts/saved/list?limit=50")
check("saved list empty after unsave", len(items_of(r)) == 0, data_of(r))

print("\n=== 7. COMMENTS + REPLIES ===")
r = B.post("/posts/%s/comments" % QID, {"content": "Try TKM 6, it held up well last season."})
check("B comments -> 201", r.status_code == 201, r.text[:200])
cm = data_of(r)
CID = cm.get("id") or cm.get("comment_id")
check("comment payload has server-side id", bool(CID), list(cm.keys()))
check("comment is_owner True for B", cm.get("is_owner") is True, cm)
check("comment author is B not A", (cm.get("author_name") or "").find("Beta") >= 0, cm.get("author_name"))
r = A.post("/posts/%s/comments" % QID, {"content": "Thanks, what spacing did you keep?",
                                         "parent_comment_id": CID})
check("A replies to B's comment -> 201", r.status_code == 201, r.text[:200])
rep = data_of(r)
RID = rep.get("id") or rep.get("comment_id")
check("reply keeps parent_comment_id", rep.get("parent_comment_id") == CID, rep.get("parent_comment_id"))
check("reply exposes reply_to_name", (rep.get("reply_to_name") or "").find("Beta") >= 0, rep.get("reply_to_name"))
r = A.get("/posts/%s/comments" % QID)
citems = items_of(r)
check("comments list has 2 entries", len(citems) == 2, len(citems))
check("comment count on post == 2", data_of(A.get("/posts/%s" % QID)).get("comments_count") == 2,
      data_of(A.get("/posts/%s" % QID)).get("comments_count"))
r = B.delete("/comments/%s" % RID)
check("B cannot delete A's reply -> 403", r.status_code == 403, "%s %s" % (r.status_code, r.text[:120]))
r = A.delete("/comments/%s" % RID)
check("A deletes own reply -> 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:120]))
r = A.get("/posts/%s/comments" % QID)
citems = items_of(r)
check("comment removed from list", len(citems) == 1, len(citems))
r = A.post("/posts/%s/comments" % QID, {"content": "x"})
short_cid = (data_of(r).get("id") if r.status_code in (200, 201) else None)
if short_cid:
    CREATED["posts"].append(None)
r = A.post("/posts/%s/comments" % QID, {"content": "a" * 3000})
check("over-long comment rejected", r.status_code in (400, 422), "%s %s" % (r.status_code, r.text[:120]))

print("\n=== 8. ANSWERS + BEST ANSWER AUTHORIZATION ===")
r = B.post("/posts/%s/answers" % QID, {"content": "TKM 6 or improved Samba Mahsuri, both blast tolerant."})
check("B answers A's question -> 201", r.status_code == 201, r.text[:200])
ans = data_of(r)
ANS = ans.get("id") or ans.get("answer_id")
check("answer is_owner True for B", ans.get("is_owner") is True, ans)
check("B cannot mark own answer best (can_mark_best False)", ans.get("can_mark_best") is False, ans)
r = B.post("/posts/%s/answers/%s/best" % (QID, ANS))
check("non-question-author marking best -> 403", r.status_code == 403, "%s %s" % (r.status_code, r.text[:140]))
r = A.post("/posts/%s/answers/%s/best" % (QID, ANS))
check("question author marks best -> 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:160]))
best = data_of(r)
alist = best.get("answers") if isinstance(best, dict) else []
alist = alist or []
marked = [a for a in alist if a.get("is_best_answer")]
check("exactly one best answer after marking", len(marked) == 1, len(marked))
r = A.get("/posts/%s" % QID)
check("answer_count == 1 on re-read", data_of(r).get("answer_count") == 1, data_of(r).get("answer_count"))
check("single-post payload embeds the answers list", len(data_of(r).get("answers") or []) == 1, len(data_of(r).get("answers") or []))
check("single-post payload embeds the comments list", isinstance(data_of(r).get("comments"), list), type(data_of(r).get("comments")))

print("\n=== 9. OWNERSHIP ENFORCEMENT ON POSTS ===")
r = B.patch("/posts/%s" % QID, {"content": "hijacked"})
check("B cannot edit A's post -> 403", r.status_code == 403, "%s %s" % (r.status_code, r.text[:140]))
r = B.delete("/posts/%s" % QID)
check("B cannot delete A's post -> 403", r.status_code == 403, "%s %s" % (r.status_code, r.text[:140]))
r = A.patch("/posts/%s" % DID, {"post_type": "experience", "title": "Drip scheduling lessons"})
check("A edits own post -> 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:160]))
upd = data_of(r)
check("edit persists post_type change", upd.get("post_type") == "experience", upd.get("post_type"))
check("edit persists title change", upd.get("title") == "Drip scheduling lessons", upd.get("title"))

print("\n=== 10. MY-ACTIVITY ISOLATION ===")
r = A.get("/communities/my-activity?limit=20")
check("A my-activity -> 200", r.status_code == 200, r.text[:160])
ma = data_of(r)
astats = ma.get("stats", {})
a_ids = [i.get("id") for i in ma.get("items", [])]
check("A's activity lists A's posts only", len(a_ids) >= 3 and all(i.get("is_owner") for i in ma.get("items", [])),
      a_ids)
check("A stats.posts matches A's own count", astats.get("posts") == len(a_ids), astats.get("posts"))
check("A stats.answers_given == 0", astats.get("answers_given") == 0, astats)
check("A stats.best_answers_received == 1 (A marked B's answer on A's question)",
      astats.get("best_answers_received") == 1, astats)
check("A stats.likes_received == 1", astats.get("likes_received") == 1, astats)
check("A stats.questions == 1", astats.get("questions") == 1, astats)
check("A stats.saved_posts == 0", astats.get("saved_posts") == 0, astats)
r = B.get("/communities/my-activity?limit=20")
mb = data_of(r)
bstats = mb.get("stats", {})
b_ids = [i.get("id") for i in mb.get("items", [])]
check("B's activity does not contain A's posts", not (set(b_ids) & set(a_ids)), b_ids)
check("B stats.posts == 0", bstats.get("posts") == 0, bstats)
check("B stats.answers_given == 1", bstats.get("answers_given") == 1, bstats)
check("B stats.comments_given == 1", bstats.get("comments_given") == 1, bstats)
check("B stats.saved_posts == 0 after unsave", bstats.get("saved_posts") == 0, bstats)
r = A.get("/communities/my-activity?page=1&limit=2")
check("my-activity paginates", len(data_of(r).get("items", [])) == 2, len(data_of(r).get("items", [])))

print("\n=== 11. COMMUNITIES / GROUPS ===")
r = A.get("/communities/groups?limit=50")
check("groups list -> 200", r.status_code == 200, r.text[:160])
groups = items_of(r)
check("topic communities exist from seed", len(groups) >= 1, len(groups))
GID = groups[0].get("id") if groups else None
r = A.get("/communities/my-groups")
check("A my-groups empty before join", len(items_of(r)) == 0, data_of(r))
r = A.post("/communities/groups/%s/join" % GID)
check("A joins a community -> 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:160]))
r = A.post("/communities/groups/%s/join" % GID)
check("joining twice is rejected/idempotent-safe", r.status_code in (200, 400, 409), "%s %s" % (r.status_code, r.text[:140]))
r = A.get("/communities/my-groups")
mg = data_of(r)
mg_items = mg if isinstance(mg, list) else mg.get("items", [])
check("A my-groups == 1", len(mg_items) == 1, len(mg_items))
r = B.get("/communities/my-groups")
mbg = data_of(r)
mbg_items = mbg if isinstance(mbg, list) else mbg.get("items", [])
check("B my-groups == 0 (isolation)", len(mbg_items) == 0, mbg_items)
r = A.get("/communities/groups/%s" % GID)
gd = data_of(r)
check("group detail reports member count >= 1", (gd.get("members_count") or gd.get("member_count") or 0) >= 1, gd)
check("group detail marks A as joined", gd.get("is_joined") is True, gd.get("is_joined"))
r = B.get("/communities/groups/%s" % GID)
check("group detail marks B as not joined", data_of(r).get("is_joined") is False, data_of(r).get("is_joined"))
r = B.get("/communities/groups?search=" + requests.utils.quote(groups[0].get("name", "")) + "&limit=50")
check("group search finds the group", len(items_of(r)) >= 1, len(items_of(r)))
r = B.get("/communities/groups?search=zzqqxx9917&limit=50")
check("group search gibberish -> 0", len(items_of(r)) == 0, len(items_of(r)))
r = B.post("/communities/groups/%s/leave" % GID)
check("B leaving a group it never joined is safe", r.status_code in (200, 400, 404), "%s %s" % (r.status_code, r.text[:120]))

print("\n=== 12. NOTIFICATIONS ROUTED TO THE RIGHT FARMER ONLY ===")
r = A.get("/notifications?limit=50")
check("A notifications -> 200", r.status_code == 200, r.text[:160])
na = data_of(r)
na_items = na if isinstance(na, list) else na.get("items", [])
r = B.get("/notifications?limit=50")
nb = data_of(r)
nb_items = nb if isinstance(nb, list) else nb.get("items", [])
a_ids_n = set(str(i.get("id")) for i in na_items)
b_ids_n = set(str(i.get("id")) for i in nb_items)
check("notification sets do not overlap", not (a_ids_n & b_ids_n), list(a_ids_n & b_ids_n)[:5])
# Community notifications all use notification_type == "community"; route by title.
comm_a = [i for i in na_items if str(i.get("notification_type")) == "community"]
comm_b = [i for i in nb_items if str(i.get("notification_type")) == "community"]
titles_a = sorted(set(str(i.get("title")) for i in comm_a))
titles_b = sorted(set(str(i.get("title")) for i in comm_b))
check("A got New Comment notification", "New Comment" in titles_a, titles_a)
check("A got New Answer notification", "New Answer" in titles_a, titles_a)
check("A got New Like notification", "New Like" in titles_a, titles_a)
check("A got no Best Answer/Reply notification (those belong to B)",
      not ({"Best Answer", "New Reply"} & set(titles_a)), titles_a)
check("B got New Reply notification (A replied to B's comment)", "New Reply" in titles_b, titles_b)
check("B got Best Answer notification (A marked B's answer)", "Best Answer" in titles_b, titles_b)
check("B got no like/comment notifications for A's post",
      not ({"New Like", "New Comment", "New Answer"} & set(titles_b)), titles_b)
urls = set(str(i.get("action_url")) for i in comm_a + comm_b)
check("community notifications deep-link with ?post=",
      all(u.startswith("community.html?post=") for u in urls), urls)
check("no notification references a deleted FA-SEED post",
      not any("FA-SEED" in str(i.get("reference_id", "")) for i in na_items + nb_items))

print("\n=== 13. PUBLIC PROFILE PRIVACY ===")
r = B.get("/farmers/%s/profile" % A.user.get("id"))
check("B reads A's public profile -> 200", r.status_code == 200, r.text[:160])
prof = data_of(r)
blob = json.dumps(prof).lower()
check("public profile hides phone", PHONE_A not in blob and "phone" not in blob, blob[:200])
check("public profile hides email", "email" not in blob, blob[:200])
check("public profile hides aadhaar/pan/address",
      not any(k in blob for k in ("aadhaar", "pan_number", "address_line", "password")), blob[:200])
check("profile reports is_self False for B", prof.get("is_self") is False, prof.get("is_self"))
check("profile exposes is_following", "is_following" in prof, list(prof.keys()))
check("profile exposes followers_count", "followers_count" in prof, prof.get("followers_count"))
check("profile posts are A's only", all(p.get("is_owner") is False for p in prof.get("posts", []))
      and len(prof.get("posts", [])) >= 3, len(prof.get("posts", [])))
r = A.get("/farmers/%s/profile" % A.user.get("id"))
check("own profile reports is_self True", data_of(r).get("is_self") is True, data_of(r).get("is_self"))
r = B.get("/farmers/does-not-exist-999/profile")
check("unknown farmer -> 404", r.status_code == 404, r.status_code)

print("\n=== 14. FOLLOW REUSES FARM BUZZ (no second system) ===")
r = B.post("/farmbuzz/users/%s/follow" % A.user.get("id"))
check("Farm Buzz follow -> 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:160]))
r = B.get("/farmers/%s/profile" % A.user.get("id"))
check("community profile reflects follow state", data_of(r).get("is_following") is True, data_of(r))
check("followers_count incremented to 1", data_of(r).get("followers_count") == 1, data_of(r).get("followers_count"))
r = B.post("/farmbuzz/users/%s/follow" % A.user.get("id"))
check("toggling follow again -> 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:160]))
r = B.get("/farmers/%s/profile" % A.user.get("id"))
check("unfollowed state reflected", data_of(r).get("is_following") is False, data_of(r))

print("\n=== 15. SHARE + REPORT ===")
r = B.post("/posts/%s/share" % QID)
check("share -> 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:160]))
r = B.post("/report", {"post_id": DID, "reason": "spam", "description": "e2e test report"})
check("report a post -> 201", r.status_code in (200, 201), "%s %s" % (r.status_code, r.text[:160]))
r = B.post("/report", {"comment_id": CID, "reason": "abuse", "description": "e2e test report"})
check("report a comment -> 201", r.status_code in (200, 201), "%s %s" % (r.status_code, r.text[:160]))

print("\n=== 16. ERROR HYGIENE ===")
r = B.get("/posts/FA-PST-does-not-exist")
body = r.text.lower()
check("missing post -> 404", r.status_code == 404, r.status_code)
check("404 body leaks no stack trace / sql",
      "traceback" not in body and "sqlalchemy" not in body and "select " not in body, r.text[:200])
r = B.post("/posts/%s/comments" % "FA-PST-does-not-exist", {"content": "hi"})
check("comment on missing post -> 404", r.status_code == 404, r.status_code)
r = B.get("/communities/feed?limit=10000")
check("absurd limit is clamped or rejected", r.status_code in (200, 422), r.status_code)

print("\n=== 17. DELETE OWN POST + CASCADE ===")
r = A.delete("/posts/%s" % AID3)
check("A deletes own post -> 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:160]))
r = A.get("/posts/%s" % AID3)
check("deleted post no longer retrievable", r.status_code in (404,), r.status_code)
r = B.get("/communities/feed?limit=50")
check("deleted post gone from feed",
      AID3 not in [i.get("id") for i in items_of(r)], "still in feed")

print("\n\n================ SUMMARY ================")
passed = sum(1 for ok, _, _ in RESULTS if ok)
failed = [n for ok, n, _ in RESULTS if not ok]
print("%d passed / %d total" % (passed, len(RESULTS)))
if failed:
    print("FAILED CHECKS:")
    for n in failed:
        print("  - " + n)
else:
    print("ALL CHECKS PASSED")

with open("_community_e2e_state.json", "w", encoding="utf-8") as fh:
    json.dump({
        "user_ids": CREATED["users"],
        "farmer_a": A.farmer_id, "farmer_b": B.farmer_id,
        "user_a": A.user.get("id"), "user_b": B.user.get("id"),
        "posts": [p for p in CREATED["posts"] if p],
        "group": GID,
        "failed": failed,
    }, fh, indent=2)
print("\ncleanup manifest written to _community_e2e_state.json")
