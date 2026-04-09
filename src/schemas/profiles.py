from datetime import date

from fastapi import UploadFile, Form, File
from pydantic import BaseModel, field_validator, HttpUrl
import validation


class ProfileSchema(BaseModel):
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str


class ProfileCreateSchema(ProfileSchema):
    avatar: UploadFile

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        validation.validate_name(v)
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        validation.validate_gender(v)
        return v

    @field_validator("date_of_birth")
    @classmethod
    def validate_date(cls, v: date) -> date:
        validation.validate_birth_date(v)
        return v

    @field_validator("info")
    @classmethod
    def validate_info(cls, v: str) -> str:
        trimmed_value = v.replace(" ", "")
        if len(trimmed_value) == 0:
            raise ValueError("Info field cannot be empty or contain only spaces.")
        return v

    @field_validator("avatar")
    @classmethod
    def validate_file(cls, v: UploadFile) -> UploadFile:
        validation.validate_image(v)
        return v


class ProfileResponseSchema(ProfileSchema):
    id: int
    user_id: int
    avatar: HttpUrl

    model_config = {
        "from_attributes": True
    }
