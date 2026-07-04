# auth.py — RETIRED
#
# This module has been decommissioned as part of the Auth0-only migration.
# Legacy HS256 JWT signing, password verification, and credential-based
# authentication have been removed.
#
# All authentication is now handled exclusively by:
#   auth/auth0_auth.py  — JWKS-based RS256 token verification
#   auth/dependencies.py — get_current_user() with DB user lookup
#
# Do NOT re-introduce HS256 or password-based flows here.
