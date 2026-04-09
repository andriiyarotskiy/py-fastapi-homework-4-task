from typing import Annotated

from botocore.exceptions import HTTPClientError, NoCredentialsError, ConnectionError
from fastapi import APIRouter, Depends, Request, HTTPException, status, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config import get_s3_storage_client, get_jwt_auth_manager
from database.models.accounts import GenderEnum
from exceptions import BaseSecurityError, S3FileUploadError, S3ConnectionError
from schemas.profiles import ProfileResponseSchema, ProfileCreateSchema
from database import get_db, UserProfileModel, UserModel, UserGroupEnum
from security.http import get_token
from security.interfaces import JWTAuthManagerInterface
from storages import S3StorageInterface

router = APIRouter()


async def get_current_user(
        request: Request,
        jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
        db: AsyncSession = Depends(get_db),
) -> UserModel:
    token = get_token(request)
    try:
        payload = jwt_manager.decode_access_token(token)
        user_id = int(payload.get("user_id"))
    except BaseSecurityError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        )
    result = await db.execute(
        select(UserModel)
        .options(
            joinedload(UserModel.group),
            joinedload(UserModel.profile)
        )
        .filter(UserModel.id == user_id))

    current_user = result.scalars().first()
    if not current_user or not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active."
        )
    return current_user


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_profile(
        user_id: int,
        profile_data: Annotated[ProfileCreateSchema, Form()],
        current_user: UserModel = Depends(get_current_user),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
        db: AsyncSession = Depends(get_db)
) -> ProfileResponseSchema:

    if current_user.group.name != UserGroupEnum.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this profile."
        )

    result = await db.execute(
        select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    )
    existing_profile = result.scalars().first()

    if existing_profile is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile."
        )

    filename = f"avatars/{user_id}_avatar.jpg"
    contents = await profile_data.avatar.read()
    await profile_data.avatar.seek(0)

    try:
        await s3_client.upload_file(file_name=filename, file_data=contents)
    except S3FileUploadError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later."
        )

    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=profile_data.first_name.lower(),
        last_name=profile_data.last_name.lower(),
        gender=GenderEnum(profile_data.gender),
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=filename,
    )

    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    try:
        avatar_url = await s3_client.get_file_url(file_name=filename)
    except (ConnectionError, HTTPClientError, NoCredentialsError) as e:
        raise S3ConnectionError(f"Failed to connect to S3 storage: {str(e)}") from e

    new_profile.avatar = avatar_url
    return ProfileResponseSchema.model_validate(new_profile)
