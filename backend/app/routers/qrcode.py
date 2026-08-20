import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.integrations.notifications import QRCodeService
from app.models.user import User
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["QR Code"])


class QRGenerateRequest(BaseModel):
    data: str
    size: int = 200


@router.post("/qrcode/generate", response_model=dict)
def generate_qr(payload: QRGenerateRequest, current_user: User = Depends(get_current_user)):
    result = QRCodeService.generate_qr(payload.data, payload.size)
    return {"status": "success", "data": result}


@router.get("/qrcode/farmer-id", response_model=dict)
def farmer_qr(current_user: User = Depends(get_current_user)):
    qr_data = json.dumps({"farmer_id": current_user.farmer_id, "name": current_user.full_name, "phone": current_user.phone_number})
    result = QRCodeService.generate_qr(qr_data)
    return {"status": "success", "data": {"qr": result, "farmer_id": current_user.farmer_id}}


