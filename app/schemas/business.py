from pydantic import BaseModel, Field


class BusinessCreate(BaseModel):
    business_client_id: str = Field(..., example="acme")
    name: str = Field(..., example="Acme Health")


class BusinessUpdate(BaseModel):
    name: str = Field(..., min_length=1, example="Acme Health")


class BusinessOut(BaseModel):
    business_client_id: str
    name: str

    class Config:
        from_attributes = True
