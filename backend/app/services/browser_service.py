"""One visible browser worker for this machine. No credentials cross this protocol."""
import asyncio
import json
import os
from ..core import settings
from pathlib import Path
from .instagram_client import ProviderError

class BrowserService:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.process = None

    async def command(self, action, **payload):
        async with self.lock:
            if not self.process or self.process.returncode is not None:
                if action == 'status':
                    return {'connected': False, 'username': None, 'reason': 'Open the Instagram browser to connect.'}
                if action == 'publish':
                    raise ProviderError('authentication', 'Open the Instagram browser and check connection first.')
                try:
                    self.process = await asyncio.create_subprocess_exec(
                        'node', str(Path(__file__).resolve().parents[2] / 'browser' / 'worker.cjs'),
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        env={**os.environ, "BROWSER_CHANNEL": settings.browser_channel},
                    )
                except OSError:
                    raise ProviderError('browser_setup', 'Node.js is required. Install frontend dependencies with npm install.') from None
            try:
                self.process.stdin.write((json.dumps({'action': action, **payload})+'\n').encode())
                await self.process.stdin.drain()
                raw = await asyncio.wait_for(self.process.stdout.readline(), timeout=90)
                if not raw:
                    raise ValueError('Worker stopped')
                data = json.loads(raw)
                if not data['ok']:
                    raise ProviderError(data['category'], data['message'])
                return data['result']
            except (asyncio.TimeoutError, OSError, ValueError, KeyError):
                await self.close()
                raise ProviderError('unknown' if action == 'publish' else 'browser_setup',
                    'Browser confirmation unavailable. Check Instagram before submitting again.' if action == 'publish' else
                    'Browser worker unavailable. Run npm install in frontend and install Google Chrome. Then open the browser again.') from None

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

browser = BrowserService()
