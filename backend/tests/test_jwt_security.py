"""JWT library migration preserves verification and rejects forged claims."""
from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.routers import auth

KEY = "jwt-regression-key-with-at-least-32-bytes"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["valid", "expired", "wrong_algorithm", "bad_signature", "missing_subject"]
)
async def test_local_token_verification(monkeypatch, kind):
    monkeypatch.setattr(auth, "SECRET_KEY", KEY)
    monkeypatch.setattr(auth, "ALGORITHM", "HS256")
    data = {} if kind == "missing_subject" else {"sub": "42"}
    token = auth.create_access_token(
        data, timedelta(seconds=-1 if kind == "expired" else 60)
    )
    if kind == "wrong_algorithm":
        token = jwt.encode({"sub": "42"}, KEY, algorithm="HS384")
    elif kind == "bad_signature":
        token = jwt.encode(
            {"sub": "42"}, "different-key-with-at-least-32-bytes", algorithm="HS256"
        )
    user = Mock(id=42)
    result = Mock()
    result.scalar_one_or_none.return_value = user
    db = Mock(execute=AsyncMock(return_value=result))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    if kind == "valid":
        assert await auth.get_current_user(credentials, db) is user
        db.execute.assert_awaited_once()
    else:
        with pytest.raises(HTTPException) as error:
            await auth.get_current_user(credentials, db)
        assert error.value.status_code == 401
        db.execute.assert_not_awaited()
