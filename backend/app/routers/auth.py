"""Signing in and out of the demo workspace. See app/auth/login.py for how it works."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.auth import login

router = APIRouter(prefix="/api/auth", tags=["Sign in"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=160)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class SessionOut(BaseModel):
    email: str
    expires_at: int          # Unix time (seconds)
    login_required: bool


class LoginOut(SessionOut):
    token: str


@router.post("/login", response_model=LoginOut)
def sign_in(data: LoginRequest, request: Request):
    try:
        token, expires, email = login.check_login(request, data.email, data.password)
    except login.LoginError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)
    return {"token": token, "email": email, "expires_at": expires, "login_required": login.login_required()}


@router.get("/session", response_model=SessionOut)
def current_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(login.bearer_scheme)],
    _signed_in: Annotated[dict | None, Depends(login.require_login)],
):
    """Is the saved token still valid? Used when the website opens."""
    data = login.read_token(credentials.credentials if credentials else None)
    if data is None:  # only possible when REQUIRE_LOGIN=false
        return {"email": login.login_email(), "expires_at": 0, "login_required": False}
    return {"email": data["sub"], "expires_at": data["exp"], "login_required": True}


@router.post("/logout", status_code=204)
def sign_out(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(login.bearer_scheme)]):
    """Ends the session on the server too: the token stops working immediately."""
    login.revoke(credentials.credentials if credentials else None)
    return None
