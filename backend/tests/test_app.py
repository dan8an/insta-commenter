import asyncio, time
import pytest, httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.main import app, database, connected
from app.db import Base, Operation, Account
from app.schemas import Publish
from app.services.post_resolver import normalize_url, resolve
from app.services.instagram_client import InstagramClient, ProviderError
from pydantic import ValidationError

@pytest.fixture
def client(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path}/test.db',connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    def override():
        with factory() as db: yield db
    app.dependency_overrides[database]=override
    with TestClient(app) as client:
        status=client.get('/api/auth/status').json()
        client.headers.update({'origin':'http://localhost:5173','x-csrf-token':status['csrf_token']})
        yield client, factory
    app.dependency_overrides.clear()

@pytest.mark.parametrize('url',['https://instagram.com/p/abc/?igsh=x#foo','https://www.instagram.com/p/abc'])
def test_normalize(url): assert normalize_url(url)=='https://www.instagram.com/p/abc/'
@pytest.mark.parametrize('url',['https://instagram.com.evil.test/p/a/','https://instagram.com@evil.test/p/a/','https://evil@instagram.com/p/a/','http://instagram.com/p/a/','https://instagram.com:443/p/a/','https://instagram.com/stories/a/','https://127.0.0.1/p/a/','https://instagram.com/p/a/extra','https://instagram.com/p/%2F/'])
def test_bad_urls(url):
    with pytest.raises(ValueError): normalize_url(url)
@pytest.mark.parametrize('text',['',' ','x'*2201])
def test_text(text):
    with pytest.raises(ValidationError): Publish(url='https://instagram.com/p/a/',message=text)
def test_unicode(): assert Publish(url='https://instagram.com/reel/a/',message='Hello 🌿\nこんにちは').message.endswith('こんにちは')

def body(slug='demo'): return {'url':f'https://instagram.com/p/{slug}/','message':'A thoughtful note 🌿'}
@pytest.mark.parametrize('slug,status,category',[('demo','published',None),('external','unsupported',None),('permission','failed','permissions'),('expired','failed','expired'),('rate-limit','failed','rate_limit'),('failure','failed','provider'),('timeout','unknown','unknown')])
def test_demo(client,slug,status,category):
    c, factory=client
    result=c.post('/api/comments/publish',json=body(slug)).json()
    assert result['status']==status and result['error_category']==category and result['demo']
    assert bool(result['comment_id'])==(status=='published')
    assert c.get('/api/activity').json()[0]['id']==result['id']
    with factory() as db: assert db.scalar(select(Operation)).status==status

def test_repeat_publish_creates_another_attempt(client):
    c,_=client; data=body()
    a=c.post('/api/comments/publish',json=data).json()
    second=c.post('/api/comments/publish',json=data).json()
    assert second['id']!=a['id'] and second['status']=='published'
    data['message']='changed'
    third=c.post('/api/comments/publish',json=data).json()
    assert third['id']!=second['id']
    assert len(c.get('/api/activity').json())==3

def test_session_isolation_and_csrf(client):
    c,_=client;c.post('/api/comments/publish',json=body())
    c.cookies.clear()
    assert c.get('/api/activity').json()==[]
    assert c.post('/api/comments/publish',json=body()).status_code==403

def test_reply_explicit(client):
    c,_=client; data=body();data['parent_comment_id']='123'
    assert c.post('/api/comments/publish',json=data).status_code==422
    data['operation']='reply'
    assert c.post('/api/comments/publish',json=data).json()['status']=='published'

def test_bad_oauth_state(client):
    assert client[0].get('/api/auth/instagram/callback?state=bad&code=x').status_code==410

def test_resolver():
    class Fake:
        async def pages(self,path,fields):
            yield {'id':'1','permalink':'https://instagram.com/p/other/','media_type':'IMAGE'}
            yield {'id':'2','permalink':'https://instagram.com/reel/yes/?x=1','media_type':'VIDEO'}
    assert asyncio.run(resolve(Fake(),'owner','https://instagram.com/reel/yes/'))['media_id']=='2'
    assert not asyncio.run(resolve(Fake(),'owner','https://instagram.com/p/no/'))['eligible']

def test_pagination_and_publish():
    class Fake(InstagramClient):
        calls=[]
        async def request(self,method,path,**kwargs):
            self.calls.append((method,path,kwargs))
            if method=='POST': return {'id':'confirmed'}
            if kwargs['params'].get('after'): return {'data':[{'id':'parent'}]}
            return {'data':[{'id':'first'}], 'paging':{'next':'https://evil.test/token','cursors':{'after':'cursor'}}}
    c=Fake('secret')
    assert asyncio.run(c.publish('media','hello','parent'))=='confirmed'
    assert c.calls[1][1]=='media/comments' and c.calls[-1][1]=='parent/replies'

def test_no_confirmation():
    class Fake(InstagramClient):
        async def request(self,*args,**kwargs): return {'success':True}
    with pytest.raises(ProviderError,match='did not return'): asyncio.run(Fake('secret').publish('media','hi'))

def test_parent_ownership():
    class Fake(InstagramClient):
        async def pages(self,*args):
            yield {'id':'different'}
    with pytest.raises(ProviderError,match='not an authorized'): asyncio.run(Fake('secret').publish('media','hi','123'))

@pytest.mark.parametrize('code,category',[(190,'expired'),(200,'permissions'),(4,'rate_limit'),(999,'provider')])
def test_provider_error(monkeypatch,code,category):
    async def request(self,method,url,**kwargs):
        return httpx.Response(400,json={'error':{'code':code}},request=httpx.Request(method,url))
    monkeypatch.setattr(httpx.AsyncClient,'request',request)
    with pytest.raises(ProviderError) as exc: asyncio.run(InstagramClient('secret').publish('id','hello'))
    assert exc.value.category==category

def test_timeout_no_retry(monkeypatch):
    calls=[]
    async def request(self,*args,**kwargs):
        calls.append(1);raise httpx.ReadTimeout('timeout')
    monkeypatch.setattr(httpx.AsyncClient,'request',request)
    with pytest.raises(ProviderError) as exc: asyncio.run(InstagramClient('secret').publish('id','hello'))
    assert exc.value.category=='unknown' and len(calls)==1

def test_expired_and_missing_permissions(client):
    from types import SimpleNamespace
    c, factory = client
    with factory() as db:
        request=SimpleNamespace(state=SimpleNamespace(uid='test-user'))
        db.add(Account(user_id='test-user',instagram_id='123',username='tester',token='encrypted-placeholder',expires=time.time()-1,permissions='instagram_business_manage_comments'))
        db.commit()
        with pytest.raises(ProviderError) as exc: connected(request, db)
        assert exc.value.category=='expired'
        account=db.get(Account,'test-user');account.expires=time.time()+3600;account.permissions='instagram_business_basic';db.commit()
        with pytest.raises(ProviderError) as exc: connected(request, db)
        assert exc.value.category=='permissions'

def test_success_uses_bearer_and_body(monkeypatch):
    async def request(self,method,url,**kwargs):
        assert method=='POST' and url.endswith('/123/comments')
        assert 'secret' not in url
        assert kwargs['headers']['Authorization']=='Bearer secret'
        assert kwargs['data']=={'message':'Hello 🌿'}
        return httpx.Response(200,json={'id':'987'},request=httpx.Request(method,url))
    monkeypatch.setattr(httpx.AsyncClient,'request',request)
    assert asyncio.run(InstagramClient('secret').publish('123','Hello 🌿'))=='987'
