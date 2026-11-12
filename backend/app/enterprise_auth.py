"""Local staff authentication and the default-deny enterprise API allowlist."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, ForeignKey, Integer, String, delete
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, SessionLocal
from .enterprise_settings import ENABLED, ORIGIN

SESSION_SECONDS = 8 * 60 * 60
COOKIE = "ad_enterprise_session"
LOGIN_LIMIT = 5
LOGIN_WINDOW = 60
router = APIRouter(prefix="/api/auth", tags=["enterprise-auth"])


class Employee(Base):
    __tablename__ = "enterprise_employees"
    employee_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class StaffSession(Base):
    __tablename__ = "enterprise_sessions"
    token_digest: Mapped[str] = mapped_column(String, primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("enterprise_employees.employee_id"), index=True)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


class LoginInput(BaseModel):
    employee_id: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


@dataclass(frozen=True)
class Identity:
    employee_id: str
    display_name: str
    role: str


def _password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024 * 1024)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"{salt.hex()}:{_password_digest(password, salt).hex()}"


def verify_password(password: str, encoded: str) -> bool:
    salt, expected = encoded.split(":", 1)
    return hmac.compare_digest(_password_digest(password, bytes.fromhex(salt)), bytes.fromhex(expected))


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# Run the same KDF even when an employee ID does not exist.
_dummy_hash = "00" * 16 + ":" + "00" * 64
_attempts: dict[str, tuple[float, int]] = {}
_attempt_lock = threading.Lock()


def _reserve_login_attempt(request: Request) -> str:
    address = request.client.host if request.client else "local"
    now = time.monotonic()
    with _attempt_lock:
        for key, (until, _) in list(_attempts.items()):
            if until <= now:
                del _attempts[key]
        until, count = _attempts.get(address, (now + LOGIN_WINDOW, 0))
        if count >= LOGIN_LIMIT:
            raise HTTPException(429, "登录尝试过多，请稍后重试", headers={"Retry-After": str(max(1, int(until - now)))})
        _attempts[address] = (until, count + 1)
    return address


WORKSPACE_ACCESS = {
    ("GET", "/api/diagnostics/template"), ("GET", "/api/diagnostics/sample-periods"),
    ("POST", "/api/diagnostics/monitor"), ("POST", "/api/diagnostics/strategy"),
    ("GET", "/api/auth/me"), ("POST", "/api/auth/logout"),
    ("GET", "/api/enterprise/dashboard"), ("GET", "/api/enterprise/policy-watch"),
    ("GET", "/api/analyses"), ("GET", "/api/prompts"), ("GET", "/api/overview"),
    ("GET", "/api/evaluations/datasets"), ("GET", "/api/evaluations/runs"),
    ("GET", "/api/evaluations/runs/{run_id}"), ("POST", "/api/evaluations/preview"),
    ("POST", "/api/evaluations/runs"),
    ("POST", "/api/analyses"),
    ("POST", "/api/analyses/image"), ("POST", "/api/analyses/{analysis_id}/reviews"),
    ("POST", "/api/agent/runs"), ("POST", "/api/agent/runs/{thread_id}/resume"),
    ("GET", "/api/agent/graph"), ("GET", "/api/batch/template"), ("POST", "/api/batch"),
    ("GET", "/api/comprehensive/template"), ("POST", "/api/comprehensive"),
    ("POST", "/api/business/reports"), ("GET", "/api/business/reports/{report_id}"),
    ("POST", "/api/business/reports/{report_id}/cases/{case_id}/review"),
    ("GET", "/api/business/reports/{report_id}/export"), ("GET", "/api/business/demo-input"),
    ("GET", "/api/business/template"), ("POST", "/api/business/reports/upload"),
}


def enforce_access(request: Request, response: Response) -> None:
    if not ENABLED:
        return
    response.headers["Cache-Control"] = "no-store"
    route = request.scope.get("route")
    action = (request.method, getattr(route, "path", ""))
    if action == ("GET", "/api/health"):
        return
    login_request = action == ("POST", "/api/auth/login")
    if not login_request:
        token = request.cookies.get(COOKIE, "")
        with SessionLocal() as db:
            session = db.get(StaffSession, token_digest(token)) if 0 < len(token) <= 128 else None
            employee = db.get(Employee, session.employee_id) if session and session.expires_at > time.time() else None
            if not employee or not employee.enabled:
                raise HTTPException(401, "请登录企业演示工作台")
            if action not in WORKSPACE_ACCESS:
                raise HTTPException(403, "企业演示工作台未开放此操作")
            request.state.employee = Identity(employee.employee_id, employee.display_name, employee.role)
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("origin") != ORIGIN:
        raise HTTPException(403, "请求来源与企业演示工作台不一致")


def reviewer_identity(request: Request, legacy_reviewer: str) -> str:
    return request.state.employee.employee_id if ENABLED else legacy_reviewer


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response):
    if not ENABLED:
        raise HTTPException(404)
    address = _reserve_login_attempt(request)
    with SessionLocal() as db:
        employee = db.get(Employee, payload.employee_id.strip().upper())
        valid = verify_password(payload.password, employee.password_hash if employee else _dummy_hash)
        if not valid or not employee or not employee.enabled:
            raise HTTPException(401, "工号或密码错误")
        token = secrets.token_urlsafe(32)
        previous = request.cookies.get(COOKIE, "")
        if 0 < len(previous) <= 128:
            db.execute(delete(StaffSession).where(StaffSession.token_digest == token_digest(previous)))
        now = int(time.time())
        db.execute(delete(StaffSession).where(StaffSession.expires_at <= now))
        db.add(StaffSession(token_digest=token_digest(token), employee_id=employee.employee_id, expires_at=now + SESSION_SECONDS))
        identity = Identity(employee.employee_id, employee.display_name, employee.role)
        db.commit()
    with _attempt_lock:
        _attempts.pop(address, None)
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=ORIGIN.startswith("https://"), samesite="lax", path="/api")
    return identity


@router.get("/me")
def me(request: Request):
    if not ENABLED:
        raise HTTPException(404)
    return request.state.employee


@router.post("/logout")
def logout(request: Request, response: Response):
    if not ENABLED:
        raise HTTPException(404)
    with SessionLocal() as db:
        db.execute(delete(StaffSession).where(StaffSession.token_digest == token_digest(request.cookies[COOKIE])))
        db.commit()
    response.delete_cookie(COOKIE, path="/api")
    return {"ok": True}
