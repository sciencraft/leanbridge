import env_setup
import hashlib
import hmac
import jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings

SECRET_KEY = settings.jwt_secret
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

security = HTTPBearer()

def strengthen(raw: str, username: str = "defaultSalt") -> str:
    """
    1. SHA-256(raw)
    2. HMAC-SHA256(step 1 result, username)
    Returns a 64-char lowercase hex string.
    """
    hash_bytes = hashlib.sha256(raw.encode("utf-8")).digest()
    hmac_bytes = hmac.new(
        username.encode("utf-8"),
        hash_bytes,
        hashlib.sha256
    ).digest()
    return hmac_bytes.hex()

def create_access_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_access_token(token: str) -> str | None:
    """Returns username or None if invalid/expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    username = verify_access_token(token)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
