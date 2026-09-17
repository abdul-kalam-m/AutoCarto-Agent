"""Shared SQL persistence for identities, sessions, projects and AI budgets.

PostgreSQL is required in production. SQLite is supported for local tests.
Quota increments and optimistic project writes are conditional SQL updates,
so correctness does not depend on a Python lock or a single web replica.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
import os
from threading import BoundedSemaphore
from contextlib import contextmanager

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, Text, create_engine, delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

metadata = MetaData()
version = Table("schema_version", metadata, Column("id", Integer, primary_key=True), Column("version", Integer, nullable=False))
users = Table("users", metadata, Column("id", String(36), primary_key=True), Column("email", String(254), nullable=False, unique=True), Column("password_hash", Text, nullable=False), Column("created_at", BigInteger, nullable=False))
invitations = Table("invitations", metadata, Column("token_hash", String(64), primary_key=True), Column("email", String(254), nullable=False), Column("expires_at", BigInteger, nullable=False), Column("used", Integer, nullable=False, default=0))
sessions = Table("sessions", metadata, Column("token_hash", String(64), primary_key=True), Column("user_id", String(36), nullable=False, index=True), Column("expires_at", BigInteger, nullable=False))
projects = Table("projects", metadata, Column("id", String(36), primary_key=True), Column("user_id", String(36), nullable=False, index=True), Column("name", String(120), nullable=False), Column("document", Text, nullable=False), Column("revision", Integer, nullable=False), Column("updated_at", BigInteger, nullable=False))
budgets = Table("ai_budgets", metadata, Column("user_id", String(36), primary_key=True), Column("day", String(10), primary_key=True), Column("used", Integer, nullable=False))
attempts = Table("auth_attempts", metadata, Column("key", String(64), primary_key=True), Column("window", BigInteger, primary_key=True), Column("used", Integer, nullable=False))
hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = hasher.hash("not-an-account-" + secrets.token_hex(16))
PASSWORD_SLOTS = BoundedSemaphore(2)


@contextmanager
def password_slot():
    if not PASSWORD_SLOTS.acquire(blocking=False):
        raise StoreError(429, "Sign-in is busy. Try again shortly.")
    try:
        yield
    finally:
        PASSWORD_SLOTS.release()


class StoreError(ValueError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def production():
    return os.getenv("AUTOCARTO_DEPLOYMENT", "local") == "production"


def auth_required():
    return production() or os.getenv("AUTOCARTO_AUTH_REQUIRED", "0") == "1"


class Store:
    def __init__(self, url):
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        if production() and not url.startswith("postgresql+psycopg://"):
            raise RuntimeError("Production requires shared PostgreSQL DATABASE_URL")
        self.engine = create_engine(url, pool_pre_ping=True, connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite:") else {})

    def migrate(self):
        with self.engine.begin() as conn:
            if self.engine.dialect.name == "postgresql":
                from sqlalchemy import text
                conn.execute(text("SELECT pg_advisory_xact_lock(713624091)"))
            metadata.create_all(conn)
            self._ensure(conn, version, {"id": 1, "version": 1}, ["id"])
            if conn.execute(select(version.c.version).where(version.c.id == 1)).scalar_one() != 1:
                raise RuntimeError("Unsupported database schema version")

    def ready(self):
        with self.engine.connect() as conn:
            if conn.execute(select(version.c.version).where(version.c.id == 1)).scalar_one() != 1:
                raise RuntimeError("Run the database migration before starting this release")

    def _ensure(self, conn, table, values, keys):
        constructor = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
        conn.execute(constructor(table).values(**values).on_conflict_do_nothing(index_elements=keys))

    def throttle(self, identifier):
        # Shared brute-force budget, including nonexistent accounts. No emails
        # or raw IPs enter the counter table. 10 attempts / 15 minute window.
        window = int(time.time()) // 900
        key = digest(identifier)
        with self.engine.begin() as conn:
            self._ensure(conn, attempts, {"key": key, "window": window, "used": 0}, ["key", "window"])
            count = conn.execute(update(attempts).where(attempts.c.key == key, attempts.c.window == window, attempts.c.used < 10).values(used=attempts.c.used + 1)).rowcount
        if not count:
            raise StoreError(429, "Too many login attempts. Try again in 15 minutes.")

    def invite(self, email, lifetime=86400):
        token = secrets.token_urlsafe(32)
        with self.engine.begin() as conn:
            conn.execute(insert(invitations).values(token_hash=digest(token), email=email.lower().strip(), expires_at=int(time.time()) + lifetime, used=0))
        return token

    def register(self, email, password, token):
        email = email.lower().strip()
        self.throttle("register:" + email)
        with self.engine.connect() as conn:
            valid = conn.execute(select(invitations.c.token_hash).where(invitations.c.token_hash == digest(token), invitations.c.email == email, invitations.c.expires_at > int(time.time()), invitations.c.used == 0)).first()
        if not valid:
            raise StoreError(400, "Invitation is invalid, expired, or already used.")
        with password_slot():
            password_hash = hasher.hash(password)
        user_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            used = conn.execute(update(invitations).where(invitations.c.token_hash == digest(token), invitations.c.email == email, invitations.c.expires_at > int(time.time()), invitations.c.used == 0).values(used=1)).rowcount
            if not used or conn.execute(select(users.c.id).where(users.c.email == email)).first():
                raise StoreError(400, "Invitation is invalid, expired, or already used.")
            conn.execute(insert(users).values(id=user_id, email=email, password_hash=password_hash, created_at=int(time.time())))
        return self.new_session(user_id)

    def login(self, email, password):
        email = email.lower().strip()
        self.throttle("login:" + email)
        with self.engine.connect() as conn:
            user = conn.execute(select(users).where(users.c.email == email)).mappings().first()
        try:
            with password_slot():
                hasher.verify(user["password_hash"] if user else DUMMY_HASH, password)
        except VerificationError:
            raise StoreError(401, "Email or password is incorrect.") from None
        if not user:
            raise StoreError(401, "Email or password is incorrect.")
        return self.new_session(user["id"])

    def new_session(self, user_id):
        token = secrets.token_urlsafe(32)
        with self.engine.begin() as conn:
            conn.execute(insert(sessions).values(token_hash=digest(token), user_id=user_id, expires_at=int(time.time()) + 7 * 86400))
        return token

    def user(self, token):
        if not token:
            return None
        with self.engine.connect() as conn:
            row = conn.execute(select(users.c.id, users.c.email).join(sessions, sessions.c.user_id == users.c.id).where(sessions.c.token_hash == digest(token), sessions.c.expires_at > int(time.time()))).mappings().first()
            return dict(row) if row else None

    def logout(self, token):
        with self.engine.begin() as conn:
            conn.execute(delete(sessions).where(sessions.c.token_hash == digest(token or "")))

    def quota(self, user_id, limit):
        day = datetime.now(timezone.utc).date().isoformat()
        with self.engine.connect() as conn:
            used = conn.execute(select(budgets.c.used).where(budgets.c.user_id == user_id, budgets.c.day == day)).scalar_one_or_none() or 0
        return {"day": day, "used": used, "limit": limit, "remaining": max(0, limit - used)}

    def consume_ai(self, user_id, limit):
        day = datetime.now(timezone.utc).date().isoformat()
        with self.engine.begin() as conn:
            self._ensure(conn, budgets, {"user_id": user_id, "day": day, "used": 0}, ["user_id", "day"])
            changed = conn.execute(update(budgets).where(budgets.c.user_id == user_id, budgets.c.day == day, budgets.c.used < limit).values(used=budgets.c.used + 1)).rowcount
        if not changed:
            raise StoreError(429, "Your daily AI request quota is exhausted. Guided maps remain available; the quota resets at 00:00 UTC.")

    def list_projects(self, user_id):
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(select(projects.c.id, projects.c.name, projects.c.revision, projects.c.updated_at).where(projects.c.user_id == user_id).order_by(projects.c.updated_at.desc())).mappings()]

    def project(self, user_id, project_id):
        with self.engine.connect() as conn:
            row = conn.execute(select(projects).where(projects.c.id == project_id, projects.c.user_id == user_id)).mappings().first()
        if not row:
            raise StoreError(404, "Project not found")
        return {"id": row["id"], "name": row["name"], "revision": row["revision"], "workspace": json.loads(row["document"])}

    def save(self, user_id, project_id, name, document, revision):
        raw = json.dumps(document, allow_nan=False, separators=(",", ":"))
        now = int(time.time())
        with self.engine.begin() as conn:
            if project_id is None:
                project_id = str(uuid.uuid4())
                conn.execute(insert(projects).values(id=project_id, user_id=user_id, name=name, document=raw, revision=1, updated_at=now))
                next_revision = 1
            else:
                changed = conn.execute(update(projects).where(projects.c.id == project_id, projects.c.user_id == user_id, projects.c.revision == revision).values(name=name, document=raw, revision=projects.c.revision + 1, updated_at=now)).rowcount
                if not changed:
                    raise StoreError(409, "Project changed in another tab or is unavailable. Reopen it before saving; your local changes have not been discarded.")
                next_revision = revision + 1
        return {"id": project_id, "name": name, "revision": next_revision}


@lru_cache(maxsize=4)
def _store(url):
    return Store(url)


def get_store():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required for accounts and persistence")
    return _store(url)


def ai_limit():
    return max(0, int(os.getenv("AUTOCARTO_AI_DAILY_LIMIT", "20")))
