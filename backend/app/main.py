import csv, io
from datetime import datetime, timezone
from fastapi import Query
from fastapi.responses import StreamingResponse
import hashlib, secrets, time, uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy import select, delete, update, func, or_, case, and_
from .core import settings, signer_secret, cipher
from .db import Base, engine, database, Account, Operation, Session, Confirmation
from .schemas import Target, Publish
from .services.instagram_client import InstagramClient, ProviderError
from .services.browser_service import browser

signer = URLSafeTimedSerializer(signer_secret)
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with Session() as db:
        db.execute(update(Operation).where(Operation.status == 'publishing').values(status='unknown', reason='The app restarted during this attempt. Check Instagram before submitting again.', error_category='unknown'))
        db.commit()
    yield
    await browser.close()
app = FastAPI(title='InstaComment', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True, allow_methods=['GET','POST'], allow_headers=['Content-Type','X-CSRF-Token'])

@app.middleware('http')
async def session_middleware(request, call_next):
    if settings.mode == 'browser' and (request.url.hostname not in ('localhost', '127.0.0.1') or request.client.host not in ('127.0.0.1', '::1', 'testclient')):
        return JSONResponse({'detail':'Browser mode accepts localhost connections only.'}, status_code=403)
    try:
        uid = signer.loads(request.cookies.get('ic_session', ''), max_age=86400 * 7)
    except BadSignature:
        uid = secrets.token_urlsafe(32)
    request.state.uid = 'local-owner' if settings.mode == 'browser' else uid
    request.state.csrf = signer.dumps(uid, salt='csrf')
    if request.method == 'POST':
        try:
            if request.headers.get('origin') != settings.frontend_origin:
                raise ValueError('Invalid origin')
            if signer.loads(request.headers.get('x-csrf-token',''), salt='csrf', max_age=86400 * 7) != uid:
                raise ValueError('Invalid CSRF token')
        except (BadSignature, ValueError):
            return JSONResponse({'detail':'Session verification failed. Reload the page.'}, status_code=403)
    response = await call_next(request)
    response.set_cookie('ic_session', signer.dumps(uid), httponly=True, secure=settings.cookie_secure, samesite='lax', max_age=86400 * 7)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response

@app.exception_handler(ProviderError)
async def provider_error(request, exc):
    return JSONResponse({'detail': exc.message, 'category': exc.category}, status_code=502)

@app.get('/api/health')
def health(): return {'status':'ok', 'mode':settings.mode}

@app.get('/api/auth/status')
async def status(request: Request):
    if settings.mode == 'demo':
        state = {'connected':True, 'username':'campus.studio', 'reason':None}
    elif browser.lock.locked():
        state = {'connected':False, 'username':None, 'reason':'Browser operation in progress.'}
    else:
        state = await browser.command('status')
    return {**state, 'mode':settings.mode, 'csrf_token':request.state.csrf}

@app.post('/api/auth/browser/open')
async def open_browser():
    if settings.mode != 'browser': raise HTTPException(409, 'Start the app in browser mode first.')
    return await browser.command('connect')

@app.get('/api/auth/instagram/start')
@app.get('/api/auth/instagram/callback')
def legacy_oauth():
    raise HTTPException(410, 'Meta OAuth has been replaced. Use Open Instagram browser in the local app.')

@app.post('/api/auth/disconnect')
async def disconnect(request: Request, db=Depends(database)):
    if settings.mode == 'browser': await browser.command('disconnect')
    db.execute(delete(Account).where(Account.user_id == request.state.uid)); db.commit()
    return {'disconnected':True}

def connected(request, db):
    account = db.get(Account, request.state.uid)
    if not account: raise ProviderError('authentication','Connect your Instagram professional account first.')
    if account.expires <= time.time(): raise ProviderError('expired','Instagram authorization expired. Reconnect your account.')
    if 'instagram_business_manage_comments' not in account.permissions.split(','):
        raise ProviderError('permissions','Comment permission was not granted. Reconnect and grant comment access.')
    return account, InstagramClient(cipher.decrypt(account.token.encode()).decode())

async def target_result(body, request, db):
    if settings.mode == 'demo':
        supported = body.url.split('/')[-2] != 'external'
        return {'eligible':supported, 'media_id':'demo-media' if supported else None, 'normalized_url':body.url, 'reason':None if supported else 'This simulated external post is not accessible to the connected account.'}
    return {'eligible':False, 'media_id':None, 'normalized_url':body.url, 'reason':'Browser mode checks the visible comment controls when publishing; URL validation alone cannot establish eligibility.'}

@app.post('/api/posts/resolve')
async def target(body: Target, request: Request, db=Depends(database)):
    return await target_result(body, request, db)

def serialize(op):
    return {key:getattr(op,key) for key in ('id','post_url','message','media_id','comment_id','status','reason','error_category','created_at','demo')}

@app.post('/api/comments/publish')
async def publish(body: Publish, request: Request, db=Depends(database)):
    if settings.mode == 'browser' and body.operation != 'comment':
        raise HTTPException(422, 'Browser mode publishes top-level comments only. Reply directly in Instagram.')
    if (body.operation == 'reply') != bool(body.parent_comment_id):
        raise HTTPException(422, 'Replies require an explicit parent comment ID; top-level comments must not include one.')
    fingerprint = hashlib.sha256(f'{body.url}\0{body.message}\0{body.operation}\0{body.parent_comment_id}'.encode()).hexdigest()
    if settings.mode == 'browser':
        unresolved = db.scalar(select(Operation).where(Operation.user_id == request.state.uid, Operation.status.in_(['publishing','unknown'])).order_by(Operation.created_at.desc()))
        if unresolved:
            raise HTTPException(409, 'An earlier attempt is pending or unconfirmed. Check Instagram and acknowledge it in Recent activity before submitting again.')
    op = Operation(id=str(uuid.uuid4()), user_id=request.state.uid, fingerprint=fingerprint, post_url=body.url, message=body.message, demo=settings.mode=='demo')
    db.add(op)
    db.commit()
    try:
        if settings.mode == 'browser':
            result = await browser.command('publish', url=body.url, message=body.message)
            op.comment_id = result.get('comment_id')
            db.add(Confirmation(operation_id=op.id, username=result.get('username')))
            op.reason = result['reason']
            op.status = 'published'
            db.commit()
            return serialize(op)
        result = await target_result(body, request, db)
        op.media_id = result['media_id']
        if not result['eligible']:
            op.status, op.reason = 'unsupported', result['reason']
        else:
            if settings.mode == 'demo':
                scenario = body.url.split('/')[-2]
                errors = {'permission':('permissions','Simulated missing permission. Reconnect with comment access.'), 'expired':('expired','Simulated expired authorization. Reconnect your account.'), 'rate-limit':('rate_limit','Simulated rate limit. Wait before trying again.'), 'failure':('provider','Simulated Instagram API failure.'), 'timeout':('unknown','Simulated ambiguous timeout. Check the post before retrying.')}
                if scenario in errors: raise ProviderError(*errors[scenario])
                op.comment_id = 'demo-' + uuid.uuid4().hex[:12]
            op.status = 'published'
    except ProviderError as exc:
        op.status = 'unknown' if exc.category == 'unknown' else 'unsupported' if exc.category == 'unsupported' else 'failed'
        op.error_category, op.reason = exc.category, exc.message
    db.commit()
    return serialize(op)

@app.get('/api/activity')
def activity(request: Request, db=Depends(database)):
    return [serialize(x) for x in db.scalars(select(Operation).where(Operation.user_id==request.state.uid).order_by(Operation.created_at.desc()).limit(10))]

@app.post('/api/activity/{operation_id}/acknowledge')
def acknowledge(operation_id: str, request: Request, db=Depends(database)):
    op = db.get(Operation, operation_id)
    if not op or op.user_id != request.state.uid: raise HTTPException(404, 'Attempt not found.')
    if op.status != 'unknown': raise HTTPException(409, 'Only an unknown result can be acknowledged.')
    op.status = 'reviewed'
    op.reason = 'User acknowledged checking Instagram. Publishing outcome was not automatically confirmed.'
    db.commit()
    return serialize(op)

def posting_account():
    # Older workers recorded the verified author in one of these fixed messages.
    reason = Operation.reason
    formats = [
        ('Confirmed from the save response as @', '. The post stayed open for the next comment.'),
        ('Confirmed on the comment link as @', '. This is browser verification, not an API receipt.'),
        ('Confirmed on the reloaded Instagram page as @', '. This is browser verification, not an API receipt.'),
    ]
    matches = []
    for prefix, suffix in formats:
        handle_length = func.length(reason) - len(prefix) - len(suffix)
        matches.append((and_(reason.startswith(prefix), reason.endswith(suffix), handle_length.between(1, 30)),
                        func.substr(reason, len(prefix) + 1, handle_length)))
    return func.coalesce(Confirmation.username, case(*matches))

def posted_comments(uid):
    return (select(Operation, Confirmation, posting_account())
            .outerjoin(Confirmation, Confirmation.operation_id == Operation.id)
            .where(Operation.user_id == uid, Operation.status == 'published', Operation.demo.is_(False)))

@app.get('/api/comments/history')
def comment_history(request: Request, q: str = '', offset: int = Query(0, ge=0), account: list[str] = Query(default=[]), db=Depends(database)):
    base = posted_comments(request.state.uid)
    handle = func.lower(posting_account()).label('handle')
    counts = db.execute(base.with_only_columns(handle, func.count()).group_by('handle').order_by('handle')).all()
    total = sum(count for _, count in counts)
    if account:
        base = base.where(handle.in_([name.lower() for name in account]))
    if q.strip():
        base = base.where(or_(*(field.icontains(q.strip(), autoescape=True)
                                for field in (Operation.message, Operation.post_url, posting_account()))))
    rows = db.execute(base.order_by(Operation.created_at.desc(), Operation.id.desc()).offset(offset).limit(26)).all()
    matched = db.scalar(select(func.count()).select_from(base.subquery())) if account or q.strip() else total
    return {'total': total, 'matched': matched,
            'accounts': [{'username': name, 'count': count} for name, count in counts if name],
            'more': len(rows) > 25,
            'items': [dict(serialize(op), username=account,
                           confirmed_at=meta.confirmed_at if meta else None) for op, meta, account in rows[:25]]}

@app.get('/api/comments/history.csv')
def export_comments(request: Request, db=Depends(database)):
    uid = request.state.uid
    factory = db.get_bind()
    def records():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        def row(values):
            buffer.seek(0)
            buffer.truncate()
            writer.writerow(["'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for v in values])
            return buffer.getvalue()
        def utc(timestamp):
            return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        yield row(['operation_id','account','comment','post_url','submitted_at_utc','confirmed_at_utc','comment_id','media_id'])
        with Session(bind=factory) as reader:
            stmt = posted_comments(uid).order_by(Operation.created_at.desc(), Operation.id.desc())
            for op, meta, account in reader.execute(stmt.execution_options(yield_per=256)):
                yield row([op.id, account, op.message, op.post_url, utc(op.created_at),
                           utc(meta.confirmed_at) if meta else None, op.comment_id, op.media_id])
    return StreamingResponse(records(), media_type='text/csv', headers={'Content-Disposition':'attachment; filename="posted-comments.csv"'})
