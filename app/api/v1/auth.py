"""认证路由（04 §3）：register / login / refresh / logout。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.schemas.auth import AuthResult, LoginIn, LogoutIn, RefreshIn, RefreshOut, RegisterIn
from app.services import auth_service

router = APIRouter()


@router.post("/register", response_model=AuthResult)
def register(data: RegisterIn, db: Session = Depends(get_db)) -> AuthResult:
    return auth_service.register(db, data)


@router.post("/login", response_model=AuthResult)
def login(data: LoginIn, db: Session = Depends(get_db)) -> AuthResult:
    return auth_service.login(db, data)


@router.post("/refresh", response_model=RefreshOut)
def refresh(data: RefreshIn, db: Session = Depends(get_db)) -> RefreshOut:
    return auth_service.refresh(db, data)


@router.post("/logout")
def logout(data: LogoutIn, db: Session = Depends(get_db)) -> dict:
    auth_service.logout(db, data.refresh_token)
    return {}
