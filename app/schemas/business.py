import uuid

from pydantic import BaseModel, Field


class BusinessCreate(BaseModel):
    business_client_id: str = Field(..., example="acme")
    name: str = Field(..., example="Acme Health")


class BusinessOut(BaseModel):
    business_client_id: str
    name: str
    admin_id: uuid.UUID | None = None

    class Config:
        from_attributes = True
