import stripe
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/payments", tags=["Payments"])

PLAN_AMOUNTS = {
    "basic": 900,   # $9.00 in cents
    "plus": 1900,   # $19.00 in cents
    "pro": 4900,    # $49.00 in cents
}


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

    amount = PLAN_AMOUNTS.get(body.plan)
    if amount is None:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {body.plan}")

    stripe.api_key = settings.stripe_secret_key

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            metadata={"plan": body.plan},
        )
        return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e.user_message or e))


@router.post("/confirm-plan")
async def confirm_plan(body: ConfirmPlanRequest):
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured on this server")

    if body.plan not in PLAN_AMOUNTS:
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

    # TODO: persist the activated plan to the user record in your DB
    return {"status": "ok", "plan": body.plan, "message": f"Plan '{body.plan}' activated"}
