from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from dotenv import load_dotenv
import os

import sqlalchemy
from api.DB.models import User
from api.DB.deps import db_dependency, bcrypt_context

load_dotenv(dotenv_path="./api/.env")
SECRET_KEY = os.getenv('AUTH_SECRET_KEY')
ALGORITHM = os.getenv('AUTH_ALGORITHM')

users_router = APIRouter(
    prefix='/user',
    tags=['user']
)

class UseCreateRequest(BaseModel):
    username: str
    password: str

class UseUserRequest(User):
    pass

# # Endpoint to create a user
# @app.post("/users/", response_model= schemas.UserResponse)
# def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
#     return crud.create_user(db=db, user=user)

# # Endpoint to get all users
# @app.get("/users/", response_model=list[schemas.UserResponse])
# def read_users(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
#     return crud.get_users(db=db, skip=skip, limit=limit)

@users_router.post('/', status_code=status.HTTP_201_CREATED)
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

@users_router.get('/')
async def get_user(db:db_dependency, user: str):
    return db.query(User).filter(User.username == user).first()
