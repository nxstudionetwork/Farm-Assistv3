from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.connection import get_db
from app.models.user import User, LoginHistory
from app.models.farm import Farm
from app.models.crop import Crop, CropCycle
from app.models.finance import Transaction
from app.models.worker import WorkerBooking
from app.models.marketplace import MarketplaceOrder
from app.models.ai import AIConversation
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["Analytics"])


@router.get("/analytics/dashboard", response_model=dict)
def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_count = db.query(Farm).filter(Farm.user_id == current_user.id, Farm.is_active == True).count()
    active_crops = db.query(CropCycle).join(Farm).filter(Farm.user_id == current_user.id, CropCycle.status == "active").count()
    transaction_count = db.query(Transaction).filter(Transaction.user_id == current_user.id).count()
    booking_count = db.query(WorkerBooking).filter(WorkerBooking.farmer_id == current_user.id).count()
    order_count = db.query(MarketplaceOrder).filter(MarketplaceOrder.user_id == current_user.id).count()
    recent_ai = db.query(AIConversation).filter(AIConversation.user_id == current_user.id).count()

    return {
        "status": "success",
        "data": {
            "farms": farm_count,
            "active_crops": active_crops,
            "transactions": transaction_count,
            "worker_bookings": booking_count,
            "orders": order_count,
            "ai_conversations": recent_ai,
        },
    }


@router.get("/analytics/usage", response_model=dict)
def usage_analytics(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    logins = db.query(LoginHistory).filter(LoginHistory.user_id == current_user.id, LoginHistory.login_time >= since).count()
    transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id, Transaction.created_at >= since).count()
    ai_calls = db.query(AIConversation).filter(AIConversation.user_id == current_user.id, AIConversation.created_at >= since).count()
    return {"status": "success", "data": {"period_days": days, "logins": logins, "transactions": transactions, "ai_calls": ai_calls}}
