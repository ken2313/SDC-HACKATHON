"""Sign-in for the demo workspace (one shared demo account).

What this protects: the whole module. Without a valid sign-in token every /api route
(except signing in and the health check) answers 401.

What it is NOT: per-person accounts. After signing in, the simulated Orbyte user switcher
still decides WHO you are (owner or employee) through the X-User-Id header, as before.
In a real Orbyte integration both would come from Orbyte's own login.

How it works (standard library only, no extra packages):
  * The password is never stored as text. We keep a salted PBKDF2-SHA256 hash and compare
    with a constant-time check.
  * Signing in returns a token: base64(payload) + "." + HMAC-SHA256 signature. The payload
    holds the email, an expiry time and a random id. Changing any character breaks the
    signature, so a token cannot be forged or extended without the server's secret.
  * Signing out puts the token's id on a revoked list (kept in memory).
  * After 5 wrong passwords from one address within 5 minutes, further tries get 429.

Settings (.env, all optional):
  DEMO_LOGIN_EMAIL     default business123@gmail.com
  DEMO_LOGIN_PASSWORD  set this to use a different password than the built-in demo one
  SESSION_SECRET       keep sessions valid across server restarts (otherwise a random one
                       is made at start-up, and a restart signs everyone out)
  SESSION_HOURS        default 12
  REQUIRE_LOGIN        default true (the automated tests switch it off)
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

PBKDF2_ITERATIONS = 200_000
# Salted hash of the demo password. The password itself is not in the code.
_DEFAULT_SALT = bytes.fromhex("863ac7476a7ca3cf0a93c6240a97420d")
_DEFAULT_HASH = bytes.fromhex("c2aecd826f8956b837ca6aefb9beafd59a6868f210e45218b9eed2d3811d296e")

MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 300

_SECRET = (os.getenv("SESSION_SECRET") or secrets.token_hex(32)).encode()
_revoked: set[str] = set()
_failures: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()

bearer_scheme = HTTPBearer(auto_error=False, description="Token from POST /api/auth/login")


class LoginError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def login_email() -> str:
    return os.getenv("DEMO_LOGIN_EMAIL", "business123@gmail.com").strip().lower()


def session_seconds() -> int:
    try:
        hours = float(os.getenv("SESSION_HOURS", "12"))
    except ValueError:
        hours = 12
    return int(max(0.1, min(hours, 24 * 7)) * 3600)


def login_required() -> bool:
    return os.getenv("REQUIRE_LOGIN", "true").lower() != "false"


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)


def password_matches(password: str) -> bool:
    custom = os.getenv("DEMO_LOGIN_PASSWORD")
    if custom:
        return hmac.compare_digest(password.encode(), custom.encode())
    return hmac.compare_digest(_hash(password, _DEFAULT_SALT), _DEFAULT_HASH)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())


def create_token(email: str, lifetime_seconds: int | None = None) -> tuple[str, int]:
    """Returns (token, expiry as a Unix timestamp)."""
    expires = int(time.time()) + (session_seconds() if lifetime_seconds is None else lifetime_seconds)
    payload = _b64(json.dumps({"sub": email, "exp": expires, "jti": secrets.token_hex(8)}).encode())
    return f"{payload}.{_sign(payload)}", expires


def read_token(token: str | None) -> dict | None:
    """The token's contents if it is genuine, not expired and not signed out; otherwise None."""
    if not token or token.count(".") != 1:
        return None
    payload, signature = token.split(".")
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("exp", 0) < time.time() or data.get("jti") in _revoked:
        return None
    return data


def revoke(token: str | None) -> None:
    data = read_token(token)
    if data:
        with _lock:
            _revoked.add(data["jti"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def check_login(request: Request, email: str, password: str) -> tuple[str, int, str]:
    """Validate the demo account. Returns (token, expiry, email). Raises LoginError."""
    key = _client_key(request)
    now = time.time()
    with _lock:
        recent = _failures[key]
        while recent and now - recent[0] > FAILURE_WINDOW_SECONDS:
            recent.popleft()
        if len(recent) >= MAX_FAILURES:
            wait = int(FAILURE_WINDOW_SECONDS - (now - recent[0])) + 1
            raise LoginError(f"Too many wrong attempts. Try again in {max(wait // 60, 1)} minute(s).", 429)

    clean_email = email.strip().lower()
    # Check the password even when the email is wrong, so both take the same time
    good_password = password_matches(password)
    if clean_email != login_email() or not good_password:
        with _lock:
            _failures[key].append(now)
        raise LoginError("Wrong email or password.", 401)

    with _lock:
        _failures.pop(key, None)
    token, expires = create_token(clean_email)
    return token, expires, clean_email


def reset_login_state() -> None:
    """For the tests: forget failed attempts and signed-out tokens."""
    with _lock:
        _failures.clear()
        _revoked.clear()


def require_login(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict | None:
    """Attached to every protected router in main.py."""
    if not login_required():
        return None
    data = read_token(credentials.credentials if credentials else None)
    if data is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},  # tells the website to show the sign-in page
        )
    return data
