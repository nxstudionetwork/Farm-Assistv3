from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User, UserAddress, FarmerProfile
from app.schemas.auth import UserResponse
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["Users"])


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    profile_image: Optional[str] = None
    preferred_language: Optional[str] = None
    farming_experience: Optional[str] = None
    preferred_crops: Optional[str] = None
    aadhaar_number: Optional[str] = None
    pan_number: Optional[str] = None
    irrigation_type: Optional[str] = None


class AddressRequest(BaseModel):
    address_line: Optional[str] = None
    village: Optional[str] = None
    mandal: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@router.get("/users/profile", response_model=dict)
def get_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    address = db.query(UserAddress).filter(UserAddress.user_id == current_user.id, UserAddress.is_primary == True).first()
    farmer_profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == current_user.id).first()

    profile_data = UserResponse.model_validate(current_user).model_dump()

    if address:
        profile_data["address"] = {
            "address_line": address.address_line,
            "village": address.village,
            "mandal": address.mandal,
            "district": address.district,
            "state": address.state,
            "country": address.country,
            "pincode": address.pincode,
            "latitude": address.latitude,
            "longitude": address.longitude,
        }

    if farmer_profile:
        profile_data["farmer_profile"] = {
            "farmer_id": farmer_profile.farmer_id,
            "date_of_birth": farmer_profile.date_of_birth,
            "gender": farmer_profile.gender,
            "occupation": farmer_profile.occupation,
            "farming_experience": farmer_profile.farming_experience,
            "preferred_crops": farmer_profile.preferred_crops,
            "aadhaar_number": farmer_profile.aadhaar_number,
            "pan_number": farmer_profile.pan_number,
            "irrigation_type": farmer_profile.irrigation_type,
        }

    return {"status": "success", "data": profile_data}


@router.put("/users/profile", response_model=dict)
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.phone_number is not None:
        existing = db.query(User).filter(
            User.phone_number == payload.phone_number, User.id != current_user.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Phone number already in use")
        current_user.phone_number = payload.phone_number
    if payload.email is not None:
        existing = db.query(User).filter(User.email == payload.email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = payload.email
    if payload.profile_image is not None:
        current_user.profile_image = payload.profile_image
    if payload.preferred_language is not None:
        current_user.preferred_language = payload.preferred_language

    farmer_profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == current_user.id).first()
    if not farmer_profile:
        farmer_profile = FarmerProfile(user_id=current_user.id, farmer_id=current_user.farmer_id, occupation="Farmer")
        db.add(farmer_profile)
        db.flush()
    if payload.farming_experience is not None:
        farmer_profile.farming_experience = payload.farming_experience
    if payload.preferred_crops is not None:
        farmer_profile.preferred_crops = payload.preferred_crops
    if payload.aadhaar_number is not None:
        farmer_profile.aadhaar_number = payload.aadhaar_number
    if payload.pan_number is not None:
        farmer_profile.pan_number = payload.pan_number
    if payload.irrigation_type is not None:
        farmer_profile.irrigation_type = payload.irrigation_type

    db.commit()
    db.refresh(current_user)

    return {
        "status": "success",
        "message": "Profile updated successfully",
        "data": UserResponse.model_validate(current_user).model_dump(),
    }


@router.put("/users/address", response_model=dict)
def create_or_update_address(
    payload: AddressRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    address = db.query(UserAddress).filter(
        UserAddress.user_id == current_user.id, UserAddress.is_primary == True
    ).first()

    if address:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(address, field, value)
    else:
        address = UserAddress(
            user_id=current_user.id,
            is_primary=True,
            **payload.model_dump(exclude_unset=True),
        )
        db.add(address)

    db.commit()
    db.refresh(address)

    return {
        "status": "success",
        "message": "Address updated successfully",
        "data": {
            "address_line": address.address_line,
            "village": address.village,
            "mandal": address.mandal,
            "district": address.district,
            "state": address.state,
            "country": address.country,
            "pincode": address.pincode,
            "latitude": address.latitude,
            "longitude": address.longitude,
        },
    }
