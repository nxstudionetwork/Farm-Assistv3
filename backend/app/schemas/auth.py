from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class RegisterRequest(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[str] = None
    preferred_language: Optional[str] = None
    password: Optional[str] = None
    pin: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    farming_experience: Optional[str] = None
    preferred_crops: Optional[str] = None
    aadhaar_number: Optional[str] = None
    pan_number: Optional[str] = None
    irrigation_type: Optional[str] = None
    address_line: Optional[str] = None
    pincode: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    mandal: Optional[str] = None
    village: Optional[str] = None
    farm_name: Optional[str] = None
    farm_type: Optional[str] = None
    total_area: Optional[float] = None
    area_unit: Optional[str] = None
    soil_type: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        name = (v or "").strip()
        if len(name) < 2:
            raise ValueError("Name must be at least 2 characters long")
        if not all(ch.isalpha() or ch.isspace() or ch in ".'-" for ch in name):
            raise ValueError("Name can only contain letters, spaces, dots and hyphens")
        return name

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        phone = (v or "").strip()
        if not phone.isdigit() or len(phone) != 10 or phone[0] not in "6789":
            raise ValueError("Phone number must be a valid 10-digit Indian mobile number")
        return phone

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        email = v.strip()
        if "@" not in email or email.count("@") != 1:
            raise ValueError("Please enter a valid email address")
        local, domain = email.split("@", 1)
        if not local or "." not in domain:
            raise ValueError("Please enter a valid email address")
        return email

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        aadhaar = v.replace(" ", "")
        if not aadhaar.isdigit() or len(aadhaar) != 12:
            raise ValueError("Aadhaar must be exactly 12 digits")
        return aadhaar

    @field_validator("pan_number")
    @classmethod
    def validate_pan(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        pan = v.strip().upper()
        import re
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
            raise ValueError("PAN must match format ABCDE1234F")
        return pan

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        pincode = v.strip()
        if not pincode.isdigit() or len(pincode) != 6:
            raise ValueError("PIN code must be 6 digits")
        return pincode

    @field_validator("total_area")
    @classmethod
    def validate_total_area(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("Farm area must be greater than 0")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        try:
            dob = datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date of birth must be in YYYY-MM-DD format")
        if dob.date() >= datetime.now().date():
            raise ValueError("Date of birth cannot be in the future")
        return v


class LoginRequest(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None
    pin: Optional[str] = None
    password: Optional[str] = None
    farmer_id: Optional[str] = None


class OTPRequest(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None


class OTPVerifyRequest(BaseModel):
    phone_number: Optional[str] = None
    email: Optional[str] = None
    otp_code: str


class UserResponse(BaseModel):
    id: str
    farmer_id: Optional[str] = None
    full_name: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    profile_image: Optional[str] = None
    preferred_language: Optional[str] = None
    role: Optional[str] = None
    is_verified: Optional[bool] = None
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class ChangePinRequest(BaseModel):
    old_pin: str
    new_pin: str
