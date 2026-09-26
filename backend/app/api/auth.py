import hashlib
import hmac
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

from ..database.db import get_connection

router = APIRouter(prefix="/api/auth", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)
SESSION_DAYS = 30
SCRYPT_N = 2**14


class RegistrationRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=60)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def _public_user(row) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
    }


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=8,
        p=1,
        dklen=64,
    )
    return f"{salt.hex()}:{digest.hex()}"


def _password_matches(password: str, encoded_hash: str) -> bool:
    salt_hex, expected_hex = encoded_hash.split(":", maxsplit=1)
    actual_hash = _password_hash(password, bytes.fromhex(salt_hex)).split(":", maxsplit=1)[1]
    return hmac.compare_digest(actual_hash, expected_hex)


def _create_session(conn, user) -> dict:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=SESSION_DAYS)
    conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now.isoformat(),))
    conn.execute(
        "INSERT INTO auth_sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (token_hash, user["id"], expires_at.isoformat()),
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "user": _public_user(user),
    }


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    if not credentials:
        return None

    token_hash = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT users.id, users.email, users.display_name
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ?
              AND auth_sessions.expires_at > ?
            """,
            (token_hash, datetime.now(timezone.utc).isoformat()),
        ).fetchone()
        return _public_user(row) if row else None
    finally:
        conn.close()


def require_user(user=Depends(get_optional_user)):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to like or comment",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegistrationRequest):
    email = str(payload.email).strip().lower()
    display_name = payload.display_name.strip()

    if not display_name:
        raise HTTPException(status_code=422, detail="Display name cannot be empty")

    conn = get_connection()
    user_id = uuid.uuid4().hex

    try:
        conn.execute(
            """
            INSERT INTO users(id, email, display_name, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, email, display_name, _password_hash(payload.password)),
        )
        user = conn.execute(
            "SELECT id, email, display_name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        response = _create_session(conn, user)
        conn.commit()
        return response
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists") from exc
    finally:
        conn.close()


@router.post("/login")
def login(payload: LoginRequest):
    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
            (str(payload.email).strip(),),
        ).fetchone()

        if not row or not _password_matches(payload.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Email or password is incorrect")

        response = _create_session(conn, row)
        conn.commit()
        return response
    finally:
        conn.close()


@router.get("/me")
def current_user(user=Depends(require_user)):
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user=Depends(require_user),
):
    token_hash = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
    conn = get_connection()

    try:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))
        conn.commit()
    finally:
        conn.close()