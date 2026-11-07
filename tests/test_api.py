import json
from fastapi.testclient import TestClient
from pmsm_lab.app import app


def test_browser_workflow_and_exports():
    with TestClient(app) as client:
        assert client.get('/').status_code==200
        assert client.get('/api/health').json()['status']=='ok'
        d=client.get('/api/defaults').json()
        c=d['config'];c.update(duration=.002,speed=[{'time':0,'value':1000}],load=[{'time':0,'value':0}])
        response=client.post('/api/simulate',json=c)
        assert response.status_code==200,response.text
        result=response.json();rid=result['id']
        signals=client.get(f'/api/results/{rid}/signals',params={'names':'sah,ia,speed_rpm','limit':300}).json()
        assert signals['raw_count']==8001
        assert signals['returned_count']<=302
        assert client.get(f'/api/results/{rid}/signals?names=missing').status_code==422
        assert client.get(f'/api/results/{rid}/signals?start=.001&end=.0001').status_code==422
        assert client.get(f'/api/results/{rid}/signals?start=NaN').status_code==422
        assert client.get('/api/results/absent/config').status_code==404
        exported=client.get(f'/api/results/{rid}/config').json()
        assert exported==c
        assert client.post('/api/validate',json=exported).status_code==200
        csv=client.get(f'/api/results/{rid}/csv')
        assert len(csv.text.splitlines())==8002
        assert 'time_s' in csv.text.splitlines()[0]
        assert client.get(f'/api/results/{rid}/npz').content.startswith(b'PK')
        assert client.get('/api/model').status_code==200
        assert client.get('/api/catalog').headers['content-type']=='application/pdf'
        bad={**c,'speed':[{'time':.001,'value':1000}]}
        assert client.post('/api/simulate',json=bad).status_code==422
