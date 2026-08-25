from __future__ import annotations

from typing import Iterator, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from abu_alia.auth.sessions import user_id_from_request
from abu_alia.db.models import User
from abu_alia.db.session import get_session_factory


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    uid = user_id_from_request(request)
    if uid is None:
        return None
    return db.get(User, uid)


def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="يلزم تسجيل الدخول")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="غير مصرح")
    return user
