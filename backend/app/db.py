import time
from sqlalchemy import create_engine, String, Text, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .core import settings

class Base(DeclarativeBase): pass
class Account(Base):
    __tablename__ = 'accounts'
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    instagram_id: Mapped[str] = mapped_column(String(64))
    username: Mapped[str] = mapped_column(String(128))
    token: Mapped[str] = mapped_column(Text)
    expires: Mapped[float] = mapped_column(Float)
    permissions: Mapped[str] = mapped_column(Text, default='')
class Operation(Base):
    __tablename__ = 'operations'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    post_url: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    media_id: Mapped[str | None] = mapped_column(String(64))
    comment_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default='publishing')
    reason: Mapped[str | None] = mapped_column(Text)
    error_category: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    demo: Mapped[bool]

engine = create_engine(settings.database_url, connect_args={'check_same_thread': False} if settings.database_url.startswith('sqlite') else {})
Session = sessionmaker(engine, expire_on_commit=False)
def database():
    with Session() as session:
        yield session

class Confirmation(Base):
    __tablename__ = 'confirmations'
    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(128))
    confirmed_at: Mapped[float] = mapped_column(Float, default=time.time)
