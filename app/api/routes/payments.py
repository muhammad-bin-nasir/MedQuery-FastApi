import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.plans import PLANS
from app.db.session import get_session
from app.models import Business
from app.schemas.plan import PlanStatusOut
from app.services.system_config_service import get_active_plan_code, set_active_plan_code

router = APIRouter(prefix="/payments", tags=["Payments"])


class CreateIntentRequest(BaseModel):
    plan: str


class ConfirmPlanRequest(BaseModel):
    plan: str
    payment_intent_id: str


@router.post("/create-intent")
async def create_payment_intent(body: CreateIntentRequest):
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured on this server")

    plan = PLANS.get(body.plan)
    if plan is None:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan}")

    stripe.api_key = settings.stripe_secret_key

    try:
        intent = stripe.PaymentIntent.create(
            amount=plan["amount_cents"],
            currency="usd",
            metadata={"plan": body.plan},
        )
        return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e.user_message or e))


@router.post("/confirm-plan")
async def confirm_plan(
    body: ConfirmPlanRequest,
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured on this server")

    plan = PLANS.get(body.plan)
    if plan is None:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan}")

    stripe.api_key = settings.stripe_secret_key

    try:
        intent = stripe.PaymentIntent.retrieve(body.payment_intent_id)
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e.user_message or e))

    if intent.status != "succeeded":
        raise HTTPException(
            status_code=400,
            detail=f"Payment not completed (status: {intent.status})",
        )

    await set_active_plan_code(session, body.plan)

    return {
        "status": "ok",
        "plan": body.plan,
        "max_businesses": plan["max_businesses"],
        "message": f"Plan '{body.plan}' activated",
    }


@router.get("/my-plan", response_model=PlanStatusOut)
async def get_my_plan(session: AsyncSession = Depends(get_session)) -> PlanStatusOut:
    plan_code = await get_active_plan_code(session)
    max_businesses = PLANS[plan_code]["max_businesses"] if plan_code else 1

    businesses_used = (
        await session.execute(select(func.count()).select_from(Business))
    ).scalar_one()

    return PlanStatusOut(
        plan_code=plan_code,
        max_businesses=max_businesses,
        businesses_used=businesses_used,
    )
