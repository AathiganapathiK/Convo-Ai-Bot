"""
auth/auth0_auth.py

Auth0 RS256 JWT verification with JWKS caching and automatic key rotation.
All config is read from environment variables — no hardcoded values.
"""
import core.config
import os
import time
import logging
# pyrefly: ignore [untyped-import]
import requests
# pyrefly: ignore [untyped-import]
from jose import jwt, JWTError


logger = logging.getLogger(__name__)

AUTH0_DOMAIN   = os.getenv("AUTH0_DOMAIN")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE")

if not AUTH0_DOMAIN or not AUTH0_AUDIENCE:
    raise RuntimeError(
        "AUTH0_DOMAIN and AUTH0_AUDIENCE must be set in environment variables."
    )

JWKS_URI = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"

# ---------------------------------------------------------------------------
# JWKS Cache — refreshed automatically on key-not-found (key rotation safe)
# ---------------------------------------------------------------------------
_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SECONDS: int = 3600  # re-fetch JWKS at most once per hour


def _fetch_jwks(force: bool = False) -> dict:
    """Return cached JWKS, re-fetching if the cache has expired or forced."""
    global _jwks_cache, _jwks_fetched_at

    if force or (time.time() - _jwks_fetched_at > _JWKS_TTL_SECONDS):
        try:
            response = requests.get(JWKS_URI, timeout=5)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_fetched_at = time.time()
            logger.info("JWKS refreshed from Auth0.")
        except requests.RequestException as exc:
            logger.error("Failed to fetch JWKS: %s", exc)
            if not _jwks_cache:
                raise RuntimeError("Could not fetch Auth0 JWKS and no cache available.")

    return _jwks_cache


def _get_rsa_key(kid: str, allow_refresh: bool = True) -> dict | None:
    """Look up an RSA key by kid. Refreshes cache once on miss (rotation)."""
    jwks = _fetch_jwks()

    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n":   key["n"],
                "e":   key["e"],
            }

    # Key not in cache — Auth0 may have rotated; try a forced refresh once.
    if allow_refresh:
        logger.warning("kid '%s' not in JWKS cache. Refreshing...", kid)
        jwks = _fetch_jwks(force=True)
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n":   key["n"],
                    "e":   key["e"],
                }

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_auth0_token(token: str) -> dict | None:
    """
    Verify an Auth0 RS256 JWT.

    Returns the decoded payload dict on success, or None on any failure.
    The caller (dependencies.py) is responsible for raising HTTP exceptions.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        logger.warning("Could not parse JWT header.")
        return None

    kid = unverified_header.get("kid")
    if not kid:
        logger.warning("JWT header missing 'kid' claim.")
        return None

    rsa_key = _get_rsa_key(kid)
    if not rsa_key:
        logger.error("No matching RSA key found for kid '%s'.", kid)
        return None

    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=AUTH0_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/",
        )
        return payload

    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        return None
