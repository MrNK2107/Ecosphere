from fastapi.testclient import TestClient
import json, sys, pathlib
sys.path.insert(0, 'apps/api')
sys.path.insert(0, 'packages/shared/python')
from main import app

client = TestClient(app)
r=client.get('/health')
print('health', r.status_code, r.json(), flush=True)
r=client.post('/incidents', json={'id':'payment-001','title':'Payment checkout outage','severity':'SEV1','description':'test'})
print('create incident', r.status_code, r.json().get('id'), flush=True)
for p in [{'name':'Priya','role':'SRE'},{'name':'Alex','role':'Backend'},{'name':'Jordan','role':'Support'},{'name':'Maya','role':'Comms'}]:
    r=client.post('/incidents/payment-001/participants', json=p)
    print('participant', r.status_code, r.json()['name'], flush=True)
fixture=json.loads(pathlib.Path('demo/payment_outage.json').read_text(encoding='utf-8'))
for u in fixture['utterances']:
    seg={'id':u['id'],'incidentId':'payment-001','speakerId':u['speakerId'],'speakerName':u['speakerName'],'role':u['role'],'text':u['text'],'isFinal':True,'startMs':u['startMs'],'endMs':u['endMs'],'confidence':0.92,'createdAt':'2026-09-02T14:00:00+00:00'}
    r=client.post('/incidents/payment-001/transcript', json={'segment':seg})
    if r.status_code!=200:
        print('transcript fail', u['id'], r.status_code, r.text[:500], flush=True)
        sys.exit(1)
print('replay done', flush=True)
r=client.get('/incidents/payment-001/snapshot')
snap=r.json()
print('facts', len(snap['facts']), [f['statement'][:45] for f in snap['facts']], flush=True)
print('hyps', len(snap['hypotheses']), flush=True)
print('decisions', len(snap['decisions']), [d['statement'][:45] for d in snap['decisions']], flush=True)
print('actions', len(snap['actions']), [(a['title'][:30], a['requiresConfirmation']) for a in snap['actions']], flush=True)
print('gaps', len(snap['gaps']), [(g['kind'], g['severity'], g['message'][:50]) for g in snap['gaps']], flush=True)
print('timeline', len(snap['timeline']), flush=True)
print('toolEvents', len(snap['toolEvents']), flush=True)
exp=fixture['expectedExtractions']
if len(snap['facts']) < exp['facts']:
    print(f"FAIL facts {len(snap['facts'])} < {exp['facts']}", flush=True)
    sys.exit(1)
if len(snap['hypotheses']) != exp['hypotheses']:
    print(f"FAIL hyps {len(snap['hypotheses'])} != {exp['hypotheses']}", flush=True)
    sys.exit(1)
if len(snap['decisions']) != exp['decisions']:
    print(f"FAIL decisions {len(snap['decisions'])} != {exp['decisions']}", flush=True)
    sys.exit(1)
if len(snap['actions']) != exp['actionItems']:
    print(f"FAIL actions {len(snap['actions'])} != {exp['actionItems']}", flush=True)
    sys.exit(1)
if len([g for g in snap['gaps'] if g['kind']=='ConflictingInfo']) < 1:
    print('FAIL ConflictingInfo gap missing', flush=True)
    sys.exit(1)
if len([g for g in snap['gaps'] if g['kind']=='MissingOwner']) < 1:
    print('FAIL MissingOwner gap missing', flush=True)
    sys.exit(1)
if not any(a['requiresConfirmation'] for a in snap['actions']):
    print('FAIL requiresConfirmation missing', flush=True)
    sys.exit(1)
print('ALL ASSERTIONS PASS', flush=True)
aid=[a for a in snap['actions'] if a['requiresConfirmation']][0]['id']
r=client.post(f"/incidents/payment-001/actions/{aid}/approve")
print('approve', r.status_code, r.json(), flush=True)
r=client.post('/incidents/payment-001/summary')
print('summary', r.status_code, flush=True)
print(r.json()['markdown'][:2000], flush=True)
print('E2E OK', flush=True)
