from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    business_client_id: str = Field(..., example="acme")
    email: EmailStr = Field(..., example="admin@acme.com")
    password: str = Field(..., example="secret")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CreateAdminRequest(BaseModel):
    business_client_id: str = Field("default", example="acme")
    email: EmailStr = Field(..., example="admin@acme.com")
    password: str = Field(..., example="secret")
    role: str = Field("admin", example="admin")
    username: str | None = Field(None, example="admin")


class CreateUserRequest(BaseModel):
    email: EmailStr = Field(..., example="user@acme.com")
    password: str = Field(..., example="secret")
    business_client_id: str = Field(..., example="acme")
    workspace_id: str = Field(..., example="default")


class UserSignupRequest(BaseModel):
    """Public self-service signup. Falls back to the default business/workspace."""

    email: EmailStr = Field(..., example="user@acme.com")
    password: str = Field(..., example="secret")
    username: str | None = Field(None, example="jane")
    business_client_id: str = Field("default", example="default")
    workspace_id: str = Field("default", example="default")
