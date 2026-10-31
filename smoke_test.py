import json, uuid, httpx
BASE='http://127.0.0.1:8000/a2a'
H={'Authorization':'Bearer smoke-owner','A2A-Version':'1.0','Content-Type':'application/a2a+json'}
other={'Authorization':'Bearer smoke-outsider','A2A-Version':'1.0'}
with httpx.Client(timeout=40) as c:
    r=c.get(BASE+'/tasks',headers=H);print('OWNER LIST',r.status_code,r.text[:300]);assert r.status_code==200
    r=c.get(BASE+'/tasks',headers=other);print('OUTSIDER LIST',r.status_code,r.text[:300]);assert r.status_code==200
    r=c.get(BASE+'/tasks');print('NO AUTH',r.status_code);assert r.status_code in (401,403)
    r=c.get(BASE+'/tasks',headers={'Authorization':'Bearer smoke-owner','A2A-Version':'2.0'});print('BAD VERSION',r.status_code);assert r.status_code==400
    r=c.post(BASE+'/message:send',headers=H,json={'message':{'messageId':str(uuid.uuid4()),'role':'ROLE_USER','parts':[{'mediaType':'text/plain','data':{}}]}});print('BAD INPUT',r.status_code,r.text[:300]);assert r.status_code==400
print('Protocol smoke tests passed. Full proposal/receipt lifecycle still needs a representative invoice fixture.')
