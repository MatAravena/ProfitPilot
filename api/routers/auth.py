from datetime import timedelta, datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from dotenv import load_dotenv
import os

import sqlalchemy

from api.DB.models import User
from api.DB.deps import db_dependency, bcrypt_context
from api.routers.users import UseCreateRequest

load_dotenv(dotenv_path="./api/.env")
SECRET_KEY = os.getenv('AUTH_SECRET_KEY')
ALGORITHM = os.getenv('AUTH_ALGORITHM')

auth_router = APIRouter(
    prefix='/auth',
    tags=['auth'],
)

class Token(BaseModel):
    access_token: str
    token_type: str

def authenticate_user(username: str, password:str, db):
    print('authenticate_user', username, password)
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False
    if not bcrypt_context.verify(password, user.password):
        return False
    return user

def create_access_token(username: str, user_id:int, expires_delta: timedelta):
    print('create_access_token')
    encode = {'sub':username, 'id': user_id}
    expires = datetime.now(timezone.utc) + expires_delta
    encode.update({'exp': expires})
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)

@auth_router.post('/', status_code=status.HTTP_201_CREATED)
async def create_user(db: db_dependency, user_request:UseCreateRequest):
    new_user = User(
        username = user_request.username,
        password = bcrypt_context.hash(user_request.password)
    )

    try:
        db.add(new_user)
        db.commit()
    except sqlalchemy.exc.IntegrityError as duplicate:
        print("User is already register, pls try with another username")
        return { 
            'value': False, 
            'status': status.HTTP_409_CONFLICT, 
            'message':"User is already register, pls try with another username"
            }
    except Exception as err:
        print("Something else went wrong: ", err.__cause__)


@auth_router.post('/token', response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                                 db:db_dependency):
    print('login_for_access_token')
    user = authenticate_user(form_data.username, form_data.password, db)
    print('login_for_access_token', user)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Could not validate user')

    print( 'user' ,user.username)
    print( 'user', user.id)
    token = create_access_token(user.username, user.id, timedelta(minutes=20))
    return {'access_token': token, 'token_type': 'bearer'}
