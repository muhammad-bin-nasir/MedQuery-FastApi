import uuid

from pydantic import BaseModel, ConfigDict, Field


class PlanStatusOut(BaseModel):
    plan_code: str | None
    max_businesses: int
    businesses_used: int


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    price_cents: int
    max_businesses: int
    max_workspaces: int
    max_rag_documents: int
    max_users: int
    sort_order: int
    is_active: bool


class PlanCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    price_cents: int = Field(ge=0)
    max_businesses: int = Field(ge=0)
    max_workspaces: int = Field(ge=0)
    max_rag_documents: int = Field(ge=0)
    max_users: int = Field(ge=0)
    sort_order: int = 0
    is_active: bool = True


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    price_cents: int | None = Field(default=None, ge=0)
    max_businesses: int | None = Field(default=None, ge=0)
    max_workspaces: int | None = Field(default=None, ge=0)
    max_rag_documents: int | None = Field(default=None, ge=0)
    max_users: int | None = Field(default=None, ge=0)
    sort_order: int | None = None
    is_active: bool | None = None
