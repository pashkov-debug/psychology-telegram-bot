from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from peewee import (
    Model,
    DatabaseProxy,
    SqliteDatabase,
    AutoField,
    IntegerField,
    TextField,
    BooleanField,
    DateTimeField,
    ForeignKeyField,
)

db_proxy: DatabaseProxy = DatabaseProxy()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaseModel(Model):
    class Meta:
        database = db_proxy


class User(BaseModel):
    id = AutoField()
    tg_user_id = IntegerField(unique=True, index=True)
    username = TextField(null=True)
    full_name = TextField(null=True)
    history_enabled = BooleanField(default=True)
    created_at = DateTimeField(default=utcnow)
    updated_at = DateTimeField(default=utcnow)


class SearchHistory(BaseModel):
    id = AutoField()
    user = ForeignKeyField(User, backref="history", on_delete="CASCADE")
    command = TextField()  # /find, /author, /doi
    query = TextField()
    result_title = TextField(null=True)
    result_url = TextField(null=True)
    created_at = DateTimeField(default=utcnow)

    class Meta:
        indexes = (
            (("user", "created_at"), False),
        )


def init_db(db_path: str) -> SqliteDatabase:
    db = SqliteDatabase(
        db_path,
        pragmas={
            "foreign_keys": 1,
            "journal_mode": "wal",
        },
    )
    db_proxy.initialize(db)
    db.connect(reuse_if_open=True)
    db.create_tables([User, SearchHistory])
    return db


def close_db() -> None:
    db = db_proxy.obj
    if db and not db.is_closed():
        db.close()


def upsert_user(tg_user_id: int, username: Optional[str], full_name: Optional[str]) -> User:
    user, created = User.get_or_create(
        tg_user_id=tg_user_id,
        defaults={"username": username, "full_name": full_name},
    )
    if not created:
        changed = False
        if username is not None and user.username != username:
            user.username = username
            changed = True
        if full_name is not None and user.full_name != full_name:
            user.full_name = full_name
            changed = True
        user.updated_at = utcnow()
        user.save()
    return user


def set_history_enabled(tg_user_id: int, enabled: bool) -> None:
    q = User.update(history_enabled=enabled, updated_at=utcnow()).where(User.tg_user_id == tg_user_id)
    updated = q.execute()
    if updated == 0:
        User.create(tg_user_id=tg_user_id, history_enabled=enabled, updated_at=utcnow(), created_at=utcnow())


def is_history_enabled(tg_user_id: int) -> bool:
    user = User.get_or_none(User.tg_user_id == tg_user_id)
    return bool(user and user.history_enabled)


def add_history(
    tg_user_id: int,
    username: Optional[str],
    full_name: Optional[str],
    command: str,
    query: str,
    result_title: Optional[str] = None,
    result_url: Optional[str] = None,
) -> None:
    user = upsert_user(tg_user_id=tg_user_id, username=username, full_name=full_name)
    if not user.history_enabled:
        return

    SearchHistory.create(
        user=user,
        command=command,
        query=query,
        result_title=result_title,
        result_url=result_url,
        created_at=utcnow(),
    )


def get_history_rows(tg_user_id: int, limit: int = 10) -> list[dict]:
    user = User.get_or_none(User.tg_user_id == tg_user_id)
    if not user:
        return []

    items = (
        SearchHistory.select()
        .where(SearchHistory.user == user)
        .order_by(SearchHistory.created_at.desc())
        .limit(limit)
    )

    out: list[dict] = []
    for it in items:
        out.append(
            {
                "command": it.command,
                "query": it.query,
                "result_title": it.result_title,
                "result_url": it.result_url,
                "created_at": it.created_at,
            }
        )
    return out


def clear_history(tg_user_id: int) -> int:
    user = User.get_or_none(User.tg_user_id == tg_user_id)
    if not user:
        return 0
    return SearchHistory.delete().where(SearchHistory.user == user).execute()
