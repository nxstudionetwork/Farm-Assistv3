import json, urllib.request, urllib.error

BASE = 'http://127.0.0.1:8000/api/v1'

def call(method, path, body=None, token=None):
    url = BASE + path
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8')
        try: return e.code, json.loads(raw)
        except Exception: return e.code, raw

# 1. Login
st, body = call('POST', '/auth/login', {'phone_number':'+919876543210','pin':'1234'})
print('LOGIN status:', st)
if st != 200:
    print(body); raise SystemExit
data = body.get('data', body)
token = data.get('access_token')
user = data.get('user', {})
print('  farmer_id:', user.get('farmer_id'))
print('  user id:', user.get('id'), 'name:', user.get('full_name'))

# 2. Categories
st, body = call('GET', '/services/categories')
print('CATEGORIES status:', st, '| data:', body.get('data'))

# 3. Catalog
st, body = call('GET', '/services')
d = body.get('data', {})
items = d.get('items', [])
print('CATALOG status:', st, '| total:', d.get('total'))
if items:
    s = items[0]
    print('  first service:', s.get('service_id'), '|', s.get('name'), '| id:', s.get('id'))

# 4. Farms
st, body = call('GET', '/farms', token=token)
farms = body.get('data', body)
print('FARMS status:', st, '| count:', len(farms) if isinstance(farms, list) else farms)
if not (isinstance(farms, list) and len(farms)):
    print('  NO FARMS - trying existing request or creating without farm')

# 5. Create request
svc = items[0] if items else None
farm = farms[0] if isinstance(farms, list) and len(farms) else None
payload = {
    'service_id': svc['id'] if svc else None,
    'service_name': svc['name'] if svc else 'Test Service',
    'service_category': svc['category'] if svc else None,
    'contact_name': user.get('full_name'),
    'contact_phone': '9876543210',
    'farm_id': farm['id'] if farm else None,
    'preferred_date': '2026-09-10',
    'preferred_time': '10:30',
    'description': 'E2E test of service request flow',
    'is_custom': False
}
st, body = call('POST', '/service-requests', payload, token)
print('CREATE REQUEST status:', st)
print('  message:', body.get('message'))
created = body.get('data', {})
req_id = created.get('service_request_id')
print('  request id:', req_id, '| status:', created.get('status'))

# 6. List requests
st, body = call('GET', '/service-requests?limit=50', token=token)
lst = body.get('data', {})
print('LIST REQUESTS status:', st, '| total:', lst.get('total'))

# 7. Get single request
st, body = call('GET', '/service-requests/' + req_id, token=token)
print('GET REQUEST status:', st)

# 8. Update status -> accepted
st, body = call('PUT', '/service-requests/' + req_id + '/status', {'status':'accepted'}, token)
print('UPDATE STATUS status:', st, '->', body.get('data',{}).get('status'))

# 9. Complete + rate
st, body = call('PUT', '/service-requests/' + req_id + '/status', {'status':'completed'}, token)
print('COMPLETE status:', st)
st, body = call('POST', '/service-requests/' + req_id + '/rate', {'rating':5,'rating_feedback':'Great service!'}, token)
print('RATE status:', st)

# 10. Notifications
st, body = call('GET', '/notifications', token=token)
nots = body.get('data', {})
items_list = nots.get('items', nots) if isinstance(nots, dict) else nots
print('NOTIFICATIONS status:', st, '| count:', len(items_list) if isinstance(items_list, list) else 'n/a')
if isinstance(items_list, list) and items_list:
    n = items_list[0]
    print('  latest:', n.get('notification_id'), '|', n.get('title'), '| ref:', n.get('reference_id'))

# 11. Completed
st, body = call('GET', '/services/completed', token=token)
comp = body.get('data', [])
print('COMPLETED status:', st, '| count:', len(comp) if isinstance(comp, list) else comp)
if isinstance(comp, list) and comp:
    print('  first completed:', comp[0].get('service_name'), '|', comp[0].get('service_request_id'))
