"""
Auth request/response schemas.

These define exactly what the API accepts and returns for authentication
endpoints. Keeping them thin — validation lives in the service layer.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator


def _strip_str(v: str) -> str:
    """Strip leading/trailing whitespace from a name field."""
    return v.strip() if isinstance(v, str) else v


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)

    _strip_names = field_validator("display_name", "first_name", "last_name", mode="before")(
        _strip_str
    )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    """The Google ID token received by the frontend after the user signs in."""

    id_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    """
    Returned after successful login/register.

    The refresh token is NOT included here — it is sent as an httpOnly cookie
    so JavaScript cannot read it, which prevents XSS token theft.
    """

    access_token: str
    token_type: str = "bearer"
