import asyncio
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.main import app, database, browser
from app.core import settings
from app.db import Base, Operation
from app.services.browser_service import BrowserService
from app.services.instagram_client import ProviderError

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'mode','browser')
    engine=create_engine(f'sqlite:///{tmp_path}/browser.db',connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine,expire_on_commit=False)
    def override():
        with factory() as db: yield db
    app.dependency_overrides[database]=override
    mock=AsyncMock(return_value={'connected':True,'username':'tester','reason':None})
    monkeypatch.setattr(browser,'command',mock)
    with TestClient(app,base_url='http://localhost') as c:
        state=c.get('/api/auth/status').json()
        c.headers.update({'origin':'http://localhost:5173','x-csrf-token':state['csrf_token']})
        yield c,mock,factory
    app.dependency_overrides.clear()

def payload(): return {'url':'https://instagram.com/p/example/','message':'Hi 🌿'}

def test_browser_publish_submits_again(client):
    c,mock,factory=client;mock.reset_mock();mock.return_value={'comment_id':None,'reason':'Confirmed on reloaded page as @tester.'}
    body=payload();a=c.post('/api/comments/publish',json=body)
    assert a.status_code==200 and a.json()['status']=='published'
    assert a.json()['comment_id'] is None and not a.json()['demo']
    second=c.post('/api/comments/publish',json=body).json()
    assert second['id']!=a.json()['id'] and second['status']=='published'
    assert mock.await_count==2
    with factory() as db: assert db.scalar(select(Operation)).status=='published'

def test_unknown_blocks_until_manual_acknowledgement(client):
    c,mock,_=client;mock.side_effect=ProviderError('unknown','Check Instagram before retrying.')
    first=c.post('/api/comments/publish',json=payload()).json()
    assert first['status']=='unknown'
    assert c.post('/api/comments/publish',json=payload()).status_code==409
    reviewed=c.post('/api/activity/'+first['id']+'/acknowledge',json={})
    assert reviewed.json()['status']=='reviewed'
    assert reviewed.json()['comment_id'] is None

def test_localhost_only_and_csrf(client):
    c,mock,_=client
    assert c.get('/api/auth/status',headers={'host':'evil.test'}).status_code==403
    assert c.post('/api/auth/browser/open',json={},headers={'origin':'https://evil.test'}).status_code==403
    assert c.post('/api/auth/browser/open',json={}).status_code==200

def test_replies_are_not_silently_posted_as_comments(client):
    c,mock,_=client;data=payload();data.update(operation='reply',parent_comment_id='123')
    assert c.post('/api/comments/publish',json=data).status_code==422

def test_browser_service_does_not_launch_on_publish():
    async def run():
        service=BrowserService()
        with pytest.raises(ProviderError) as exc: await service.command('publish')
        assert exc.value.category=='authentication' and service.process is None
    asyncio.run(run())

def test_worker_loss_after_dispatch_is_unknown_and_not_retried(monkeypatch):
    class Input:
        writes=[]
        def write(self,data): self.writes.append(data)
        async def drain(self): pass
    class Output:
        async def readline(self): return b''
    class Process:
        returncode=None
        stdin=Input()
        stdout=Output()
    async def run():
        service=BrowserService();process=Process();service.process=process
        service.close=AsyncMock()
        with pytest.raises(ProviderError) as exc:
            await service.command('publish',url='https://instagram.com/p/a/',message='hello')
        assert exc.value.category=='unknown'
        assert len(process.stdin.writes)==1
        service.close.assert_awaited_once()
    asyncio.run(run())

def test_review_acknowledgement_allows_a_new_attempt(client):
    c,mock,_=client
    mock.side_effect=ProviderError('unknown','Check the post.')
    body=payload();first=c.post('/api/comments/publish',json=body).json()
    assert c.post('/api/activity/'+first['id']+'/acknowledge',json={}).status_code==200
    mock.side_effect=None;mock.return_value={'comment_id':None,'reason':'Confirmed on reloaded page.'}
    next_attempt=c.post('/api/comments/publish',json=body).json()
    assert next_attempt['id']!=first['id'] and next_attempt['status']=='published'

def test_history_and_export(client):
    import csv
    import io
    c, mock, factory = client
    mock.return_value = {'username': 'tester', 'comment_id': '123', 'reason': 'Confirmed'}
    body = dict(payload(), message='Hello, "garden" 🌿')
    c.post('/api/comments/publish', json=body).raise_for_status()
    with factory() as db:
        for i, (uid, status, demo) in enumerate([
            ('local-owner','published',False), ('local-owner','published',True),
            ('local-owner','unknown',False), ('other','published',False)
        ]):
            db.add(Operation(id=str(i), user_id=uid, fingerprint='a', post_url=body['url'],
                             message='Older comment', status=status, demo=demo))
        db.commit()
    history = c.get('/api/comments/history?q=tester').json()
    assert history['total'] == 2 and len(history['items']) == 1
    assert history['items'][0]['confirmed_at']
    rows = list(csv.DictReader(io.StringIO(c.get('/api/comments/history.csv').text)))
    assert len(rows) == 2
    assert {(r['account'], r['comment']) for r in rows} == {('tester', body['message']), ('', 'Older comment')}
