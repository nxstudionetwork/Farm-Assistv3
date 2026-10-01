import json, urllib.request, urllib.error, sys
BASE = 'http://127.0.0.1:8000/api/v1'
TOKEN = sys.argv[1]

def req(path, method='GET', b=None):
    data = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header('Authorization', 'Bearer ' + TOKEN)
    if b is not None: r.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except: return e.code, {'detail': e.reason}

# buy-mode filtered browse (matches frontend query building)
s, d = req('/tools-equipment/browse?mode=buy&limit=3&price_min=100&price_max=10000')
print('buy browse filt', s, (d.get('data') or {}).get('total'))
items = (d.get('data') or {}).get('items') or []
for it in items[:2]:
    print('  buy item', it.get('name'), 'price', it.get('price'))

# rent-mode filtered browse
s, d = req('/tools-equipment/browse?mode=rent&limit=3&min_price=100&max_price=5000')
print('rent browse filt', s, (d.get('data') or {}).get('total'))
items = (d.get('data') or {}).get('items') or []
for it in items[:2]:
    print('  rent item', it.get('name'), 'rate', it.get('daily_rate'))

# my-listings buy (frontend loadMyListings)
s, d = req('/tools-equipment/my-listings/buy')
print('my-listings buy', s, type(d).__name__, (list(d.keys()) if isinstance(d, dict) else d)[:6] if isinstance(d, dict) else d)
items = (d.get('data') or {}).get('items') or [] if isinstance(d, dict) else []
print('  count', len(items))