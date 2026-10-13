import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.models import Business, Plan
from app.schemas.plan import PlanStatusOut
from app.services.plan_service import get_active_plan_limits
from app.services.system_config_service import get_active_plan_code, set_active_plan_code

router = APIRouter(prefix="/payments", tags=["Payments"])


class CreateIntentRequest(BaseModel):
    plan: str


class ConfirmPlanRequest(BaseModel):
    plan: str
    payment_intent_id: str


async def _get_plan_or_404(session: AsyncSession, code: str) -> Plan:
    plan = (await session.execute(select(Plan).where(Plan.code == code))).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {code}")
    return plan


@router.post("/create-intent")
async def create_payment_intent(
    body: CreateIntentRequest,
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured on this server")

    plan = await _get_plan_or_404(session, body.plan)

    stripe.api_key = settings.stripe_secret_key

    try:
        intent = stripe.PaymentIntent.create(
            amount=plan.price_cents,
            currency="usd",
            payment_method_types=["card"],
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

    plan = await _get_plan_or_404(session, body.plan)

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
        "max_businesses": plan.max_businesses,
        "message": f"Plan '{body.plan}' activated",
    }


@router.get("/my-plan", response_model=PlanStatusOut)
async def get_my_plan(session: AsyncSession = Depends(get_session)) -> PlanStatusOut:
    plan_code = await get_active_plan_code(session)
    limits = await get_active_plan_limits(session)

    businesses_used = (
        await session.execute(select(func.count()).select_from(Business))
    ).scalar_one()

    return PlanStatusOut(
        plan_code=plan_code,
        max_businesses=limits["max_businesses"],
        businesses_used=businesses_used,
    )
