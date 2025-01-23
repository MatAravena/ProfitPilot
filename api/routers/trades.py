from fastapi import APIRouter, status
from pydantic import BaseModel

from api.DB.models import Trade, TradeType
from api.DB.deps import db_dependency, user_dependency
from api.routers.http_handlers import default_http_answer, default_http_error

trades_router = APIRouter(
    prefix='/trades',
    tags=['trades']
)

class TradeBase(BaseModel):
    user_id: int
    quantity: int
    trade_action: TradeType

class TradeCreate(TradeBase):
    pass

@trades_router.get('/')
async def get_trade(db:db_dependency, user: user_dependency, trade_id: int ):
    trade = db.query(Trade).filter(Trade.user_id == trade_id).first()
    return default_http_answer(trade)

@trades_router.get('/allTradesByUser')
async def get_trades(db:db_dependency, user: user_dependency):
    trades = db.query(Trade.user_id == user.id).all()
    return default_http_answer(trades)

@trades_router.get('/allTrades')
async def get_trades(db:db_dependency, user: user_dependency):
    trades = db.query(Trade).filter(Trade.user_id == user['id']).all()
    return default_http_answer(trades)

@trades_router.post('/', status_code=status.HTTP_201_CREATED)
async def create_trades(db:db_dependency, user: user_dependency, trade: TradeCreate):
    new_trade = Trade(**trade.model_dump(), user_id=user.get('id'))
    db.add(new_trade)
    db.commit()
    db.refresh(new_trade)
    # return default_http_answer(new_trade)

@trades_router.delete('/', status_code=status.HTTP_200_OK)
async def delete_trades(db:db_dependency, user: user_dependency, trade_id: int):
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if trade:
        db.delete(trade)
        db.commit()
        # return default_http_answer(trade,'Trade has been deleted sucessfully')
