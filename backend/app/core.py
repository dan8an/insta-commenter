from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet
import secrets
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    mode: str = 'demo'
    browser_channel: str = 'chrome'
    database_url: str = 'sqlite:///./instacomment.db'
    frontend_origin: str = 'http://localhost:5173'
    session_secret: str = ''
    token_key: str = ''
    cookie_secure: bool = False
    instagram_app_id: str = ''
    instagram_app_secret: str = ''
    instagram_redirect_uri: str = 'http://localhost:8000/api/auth/instagram/callback'
    instagram_api_version: str = 'v27.0'

settings = Settings()
# Old MODE=live configurations now use the local browser, without Meta secrets.
if settings.mode == 'live': settings.mode = 'browser'
if settings.mode not in ('demo', 'browser'):
    raise RuntimeError('MODE must be demo or browser')
if settings.mode == 'browser' and settings.frontend_origin != 'http://localhost:5173':
    raise RuntimeError('Browser mode is local-only. Set FRONTEND_ORIGIN=http://localhost:5173 and do not use a tunnel.')
local_dir = Path(__file__).resolve().parents[1] / '.local'
local_dir.mkdir(mode=0o700, exist_ok=True)
local_dir.chmod(0o700)
secret_file = local_dir / 'session-secret'
if not secret_file.exists():
    import os
    try:
        with os.fdopen(os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as f:
            f.write(secrets.token_urlsafe(48))
    except FileExistsError:
        pass
signer_secret = settings.session_secret or secret_file.read_text().strip()
cipher = Fernet(settings.token_key.encode() if settings.token_key else Fernet.generate_key())
