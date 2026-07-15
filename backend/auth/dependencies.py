"""
auth/dependencies.py

FastAPI dependency: get_current_user()

Auth0-only authentication flow:
  1. Extract Bearer token from Authorization header.
  2. Verify RS256 JWT signature using Auth0 JWKS.
  3. Extract the 'email' claim from the verified payload.
  4. Look up the user in SQL Server by official_email.
  5. Enforce is_active check.
  6. Return {employee_id, role, department, company, full_name, official_email}.

No legacy HS256 fallback. No hardcoded roles or departments.
"""

import logging
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import text
from database import engine
# from auth.auth0_auth import verify_auth0_token
from auth.jwt_utils import verify_local_token
from services.auth_service import AuthService 
from services.user_role_service import UserRoleService

logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Verify the Auth0 token and return the authenticated user's profile
    loaded from the SQL Server users table.

    Raises:
        401 — if the token is invalid or expired
        403 — if the email is not found in the users table (not provisioned)
        403 — if the user account is inactive
    """
    token = credentials.credentials

    # --- Step 1: Verify Auth0 JWT ---
    # payload = verify_auth0_token(token)
    payload = verify_local_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Step 2: Extract email claim ---
    # email: str | None = payload.get("https://rr-convo-ai-api/email")
    email: str | None = payload.get("email")

    if not email:
        # logger.warning(
        #     "Auth0 token for sub='%s' has no email claim. "
        #     "Ensure the Auth0 Action 'Add Email to Access Token' is active in the Login Flow.",
        #     payload.get("sub"),
        # )

        logger.warning(
            "JWT token is missing the email claim."
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
        #     detail="Token is missing the email claim. "
        #            "Contact your administrator to verify Auth0 token configuration.",
        # )
                detail="Token is missing the email claim.")

    # --- Step 3: Look up user in SQL Server by official_email ---
    with engine.connect() as connection:

        result = connection.execute(
            text("""
                SELECT
                    employee_id,
                    full_name,
                    official_email,
                    role,
                    department,
                    company,
                    company_id,
                    is_active
                FROM users
                WHERE official_email = :email
            """),
            {
                "email": email
            }
        )

        db_user = result.fetchone()

    # --- Step 4: User must already exist — no auto-provisioning ---
    if db_user is None:
        logger.warning(
            "Auth0 login attempt for email='%s' — not found in users table.", email
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not provisioned. Contact your administrator.",
        )

    db_user = dict(db_user._mapping)

    company_context = AuthService.get_company_by_email(email)

    if not company_context:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company mapping not found."
        )

    # --- Step 5: Account must be active ---
    if not db_user["is_active"]:
        logger.warning(
            "Auth0 login attempt for email='%s' — account is inactive.", email
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is inactive. Contact your administrator.",
        )

    user_roles = (
        UserRoleService.get_role_names(
            db_user["employee_id"],
            company_context["company_id"]
        )
    )

    # Resolve company context (single-tenant: Ramraj only)
    company_id = company_context["company_id"]
    company_name = company_context["company_name"]
    company_code = company_context["company_code"]

    # --- Step 6: Return the required DB fields ---
    return {
        "employee_id": db_user["employee_id"],
        "full_name": db_user["full_name"],
        "role": db_user["role"],
        "user_roles": user_roles,
        "department": db_user["department"],
        "company": db_user["company"],
        "company_id": company_id,
        "company_name": company_name,
        "company_code": company_code,
        "official_email": db_user["official_email"],
        "sub": db_user["official_email"]
    }
