"""Request/response models for customer registration and profile management.

Validation lives here rather than in the router so that a malformed customer
signup is rejected before any row is written, and so the rules are stated once.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator


class CustomerRegisterRequest(BaseModel):
    """Customer signup.

    Deliberately narrow: name, contact channels and a delivery address. Nothing
    about land, soil, crops or documents is collected, because a customer is not
    a farmer and there is no existing requirement for any of it.

    ``phone_number`` is required rather than optional, because the application
    verifies account ownership over exactly one channel and the PIN/OTP flow is
    the existing mechanism for it. ``email`` stays optional, as it is for
    farmers.
    """

    full_name: str
    phone_number: str
    email: Optional[str] = None
    password: Optional[str] = None
    pin: Optional[str] = None
    preferred_language: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None

    # Delivery address. Optional at signup: a customer may add and manage
    # addresses later from their profile.
    address_line: Optional[str] = None
    village: Optional[str] = None
    mandal: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

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

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        pincode = v.strip()
        if not pincode.isdigit() or len(pincode) != 6:
            raise ValueError("PIN code must be 6 digits")
        return pincode

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < -90 or v > 90):
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < -180 or v > 180):
            raise ValueError("Longitude must be between -180 and 180")
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


class CustomerLoginRequest(BaseModel):
    """Customer login by Customer ID.

    The Customer ID is the primary credential; ``phone_number`` and ``email``
    are accepted as the alternative the login page offers, and are resolved
    against the authenticated role the same way the ID is.
    """

    customer_id: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    pin: Optional[str] = None
    password: Optional[str] = None
    # Which login form the person used. Cross-checked against the account that
    # was actually found so a Farmer ID cannot be used to sign in as a customer.
    role: Optional[str] = "customer"
    device: Optional[str] = None


class CustomerProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    bio: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        name = v.strip()
        if len(name) < 2:
            raise ValueError("Name must be at least 2 characters long")
        if not all(ch.isalpha() or ch.isspace() or ch in ".'-" for ch in name):
            raise ValueError("Name can only contain letters, spaces, dots and hyphens")
        return name

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


class CustomerAddressRequest(BaseModel):
    address_line: Optional[str] = None
    village: Optional[str] = None
    mandal: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_primary: bool = True

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        pincode = v.strip()
        if not pincode.isdigit() or len(pincode) != 6:
            raise ValueError("PIN code must be 6 digits")
        return pincode

    @field_validator("address_line")
    @classmethod
    def validate_address_line(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        line = v.strip()
        if len(line) < 5:
            raise ValueError("Please enter a complete address")
        return line


class CustomerSettingsUpdate(BaseModel):
    """Partial update of the customer preference sheet.

    Every field is optional and only the ones present are applied, so the UI can
    send a single toggle without having to read and write the whole sheet.
    """

    notifications: Optional[Dict[str, bool]] = None
    shopping: Optional[Dict[str, Any]] = None
    grow: Optional[Dict[str, bool]] = None
    community: Optional[Dict[str, Any]] = None
    app: Optional[Dict[str, Any]] = None


class CustomerOTPRequest(BaseModel):
    customer_id: str
    channel: str = "phone"


class CustomerOTPVerifyRequest(BaseModel):
    customer_id: str
    channel: str = "phone"
    otp_code: str
