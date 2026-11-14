import re
from urllib.parse import urlsplit

def normalize_url(value: str) -> str:
    try:
        u = urlsplit(value.strip())
        if u.scheme != 'https' or u.hostname not in ('instagram.com', 'www.instagram.com') or u.username or u.password or u.port is not None:
            raise ValueError()
        m = re.fullmatch(r'/(p|reel)/([A-Za-z0-9_-]{1,100})/?', u.path)
        if not m: raise ValueError()
        return f'https://www.instagram.com/{m[1]}/{m[2]}/'
    except ValueError:
        raise ValueError('Use an HTTPS Instagram /p/ or /reel/ post link.') from None

async def resolve(client, account_id: str, url: str):
    normalized = normalize_url(url)
    async for media in client.pages(f'{account_id}/media', 'id,permalink,media_type'):
        try:
            match = normalize_url(media.get('permalink', '')) == normalized
        except ValueError:
            continue
        if match and media.get('media_type') in ('IMAGE', 'VIDEO', 'CAROUSEL_ALBUM'):
            return {'eligible': True, 'media_id': media['id'], 'normalized_url': normalized, 'reason': None}
    return {'eligible': False, 'media_id': None, 'normalized_url': normalized,
            'reason': 'This post is not accessible in the connected account’s media. Open Instagram to comment manually.'}
