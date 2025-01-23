from fastapi import APIRouter, status
from pydantic import BaseModel

from api.DB.models import Order
from api.DB.deps import db_dependency, user_dependency
from api.routers.http_handlers import default_http_answer, default_http_error

from sqlalchemy.orm import joinedload

orders_router = APIRouter(
    prefix='/orders',
    tags=['orders']
)

class OrderBase(BaseModel, Order):
    pass

class OrderCreateList(OrderBase):
    orders: list[Order] = []

@orders_router.get('/')
async def get_order(db:db_dependency, user: user_dependency, order_id: int):
    order = db.query(Order).filter(Order.id == order_id).first()
    return default_http_answer(order)

# Joinedload
# @orders_router.get('/')
# async def get_orderjoin(db:db_dependency, user: user_dependency, order_id: int):
#     orders = db.query(Order).options(joinedload(Order.trades)).filter(Order.user_id == user.get('id')).all()
#     return default_http_answer(orders)

# Post joined
# @orders_router.post('/', status_code=status.HTTP_201_CREATED)
# async def create_orders(db:db_dependency, user: user_dependency, orders: OrderCreateList):
#     db_routine = Routine(name=routine.name, user_id= user.get('id'))

#     for workout in routine.workouts:
#         workout = db.query(workout).filter(workout.id == workout.id).first()
#         if workout:
#             db_routine.workout.appends(workout)

#     db.add(db_routine)
#     db.commit()
#     db.refresh()
#     db_routine = db.query(Routine).options(joinedload(Routine.workouts)).filter(Routine.id == db_routine.id).first()
#     return workout

@orders_router.get('/allOrders')
async def get_orders(db:db_dependency, user: user_dependency):
    orders = db.query(Order).filter(Order.user_id == user['id']).all()
    return default_http_answer(orders)

@orders_router.post('/', status_code=status.HTTP_201_CREATED)
async def create_orders(db:db_dependency, user: user_dependency, orders: OrderCreateList):
    for oder in orders:
        new_order = Order(**oder.model_dump(), user_id=user.get('id'))
        db.add(new_order)
    db.commit()
    db.refresh(new_order)
    # return default_http_answer(new_order)

@orders_router.delete('/', status_code=status.HTTP_200_OK)
async def delete_orders(db:db_dependency, user: user_dependency, order_id: int):
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        db.delete(order)
        db.commit()
        # return default_http_answer(order,'Order has been deleted sucessfully')
