import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))


if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET must be configured in the environment."
    )


def create_access_token(data: dict) -> str:
    """
    Create a signed JWT access token.
    """
    payload = data.copy()

    expire = (
        datetime.now(timezone.utc)
        + timedelta(minutes=JWT_EXPIRE_MINUTES)
    )

    payload.update(
        {
            "exp": expire
        }
    )

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )


def verify_local_token(token: str) -> dict | None:
    """
    Verify a locally generated JWT.
    Returns payload if valid, otherwise None.
    """
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

    except JWTError:
        return None