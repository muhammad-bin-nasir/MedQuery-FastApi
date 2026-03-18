from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., example="admin@acme.com")
    password: str = Field(..., example="secret")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    business_client_id: str | None = None
    workspace_id: str | None = None
    role: str | None = None


class CreateAdminRequest(BaseModel):
    email: EmailStr = Field(..., example="admin@acme.com")
    password: str = Field(..., example="secret")


class CreateUserRequest(BaseModel):
    business_client_id: str = Field(..., example="acme")
    workspace_id: str = Field(..., example="main")
    email: EmailStr = Field(..., example="user@acme.com")
    password: str = Field(..., example="secret")
