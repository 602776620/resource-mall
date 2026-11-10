"""用户路由（04 §3）：me / me/password。均需登录（get_current_user）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.models import User
from app.schemas.auth import ChangePasswordIn, UserOut
from app.services import auth_service

router = APIRouter()


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)) -> User:
    return current


@router.put("/me/password")
def change_password(
    data: ChangePasswordIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    auth_service.change_password(db, current, data)
    return {}
