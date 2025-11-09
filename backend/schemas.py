from typing import Optional
from pydantic import BaseModel, Field, EmailStr, validator


class Review(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    rating: int = Field(..., ge=1, le=5)
    text: str = Field(..., min_length=5, max_length=2000)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    approved: bool = Field(default=False)

    @validator("phone")
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Keep digits, + and spaces only (simple sanitation)
        allowed = set("+ 0123456789")
        if any(ch not in allowed for ch in v):
            raise ValueError("Phone can only contain digits, spaces and '+'.")
        return v
