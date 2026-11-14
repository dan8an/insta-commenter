import httpx
from ..core import settings

class ProviderError(Exception):
    def __init__(self, category, message):
        self.category, self.message = category, message
        super().__init__(message)

class InstagramClient:
    def __init__(self, token): self.token = token
    async def request(self, method, path, **kwargs):
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                response = await client.request(method, f'https://graph.instagram.com/{settings.instagram_api_version}/{path}', headers={'Authorization': f'Bearer {self.token}'}, **kwargs)
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise ProviderError('unknown' if method == 'POST' else 'network', 'Provider response unavailable. Check Instagram before submitting again.' if method == 'POST' else 'Could not reach Instagram. Try again later.') from None
        if response.is_error or 'error' in data:
            code = data.get('error', {}).get('code')
            category = 'expired' if code == 190 else 'permissions' if code in (10, 200) else 'rate_limit' if code in (4, 17, 32, 613) or response.status_code == 429 else 'provider'
            messages = {'expired': 'Instagram authorization expired. Reconnect your account.', 'permissions': 'Instagram denied permission. Check app access and reconnect.', 'rate_limit': 'Instagram rate limit reached. Wait before trying again.', 'provider': 'Instagram rejected the operation. Check that comments are enabled and the account has access.'}
            raise ProviderError(category, messages[category])
        return data
    async def pages(self, path, fields):
        after, seen = None, set()
        for _ in range(1000):
            data = await self.request('GET', path, params={'fields': fields, 'limit': 50, **({'after': after} if after else {})})
            for item in data.get('data', []): yield item
            paging = data.get('paging', {})
            if not paging.get('next'): return
            after = paging.get('cursors', {}).get('after')
            if not after or after in seen: raise ProviderError('pagination', 'Instagram returned incomplete pagination. Try later.')
            seen.add(after)
        raise ProviderError('pagination', 'Media discovery limit reached; target eligibility could not be established.')
    async def publish(self, media_id, message, parent=None):
        if parent:
            found = False
            async for item in self.pages(f'{media_id}/comments', 'id'):
                if item['id'] == parent:
                    found = True
                    break
            if not found: raise ProviderError('permissions', 'The reply parent is not an authorized comment on this post.')
        result = await self.request('POST', f'{parent}/replies' if parent else f'{media_id}/comments', data={'message': message})
        if not isinstance(result.get('id'), str) or not result['id']:
            raise ProviderError('unknown', 'Instagram did not return a comment ID. Check the post before submitting again.')
        return result['id']
