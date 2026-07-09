from pydantic import BaseModel


class PlanStatusOut(BaseModel):
    plan_code: str | None
    max_businesses: int
    businesses_used: int
