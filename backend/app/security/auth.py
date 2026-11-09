import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.tables import User
from app.core.config import settings

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return f'scrypt${salt}${key}'


def check_password(password: str, stored: str) -> bool:
    try:
        _,salt,key = stored.split('$')
        candidate = hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
        return hmac.compare_digest(candidate,key)
    except (ValueError,TypeError):
        return False


def token_for(user: User) -> str:
    secret = settings().jwt_secret
    if len(secret) < 32:
        raise HTTPException(503,'JWT_SECRET must be configured with at least 32 characters')
    return jwt.encode({'sub':user.id,'exp':datetime.now(timezone.utc)+timedelta(minutes=settings().token_minutes),'iss':'risk-lab'},secret,algorithm='HS256')


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials or len(settings().jwt_secret)<32:
        raise HTTPException(401,'Authentication required')
    try:
        claims = jwt.decode(credentials.credentials,settings().jwt_secret,algorithms=['HS256'],issuer='risk-lab',options={'require':['sub','exp','iss']})
        user = db.get(User,claims['sub'])
        if not user:
            raise ValueError('Unknown user')
        return user
    except (jwt.InvalidTokenError,ValueError):
        raise HTTPException(401,'Invalid or expired token') from None


def analyst(user: User = Depends(current_user)) -> User:
    if user.role not in {'analyst','admin'}:
        raise HTTPException(403,'Analyst role required')
    return user
