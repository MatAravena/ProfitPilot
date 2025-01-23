from pydantic import BaseModel

# Schema for user creation
class UserCreate(BaseModel):
    name: str
    email: str

# Schema for user response
class UserResponse(BaseModel):
    id: int
    name: str
    email: str

    class Config:
        orm_mode = True

