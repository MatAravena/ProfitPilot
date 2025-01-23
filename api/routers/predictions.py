from fastapi import APIRouter, status
from pydantic import BaseModel

from api.DB.models import Prediction, TradeType
from api.DB.deps import db_dependency, user_dependency
from api.routers.http_handlers import default_http_answer, default_http_error

predictions_router = APIRouter(
    prefix='/predictions',
    tags=['predictions']
)

class PredictionBase(BaseModel):
    user_id: int
    quantity: int
    prediction_action: TradeType

class PredictionCreate(PredictionBase):
    pass

@predictions_router.get('/')
async def get_prediction(db:db_dependency, user: user_dependency, prediction_id: int ):
    prediction = db.query(Prediction).filter(Prediction.user_id == prediction_id).first()
    return default_http_answer(prediction)

@predictions_router.get('/allPredictionsByUser')
async def get_predictions(db:db_dependency, user: user_dependency):
    predictions = db.query(Prediction.user_id == user.id).all()
    return default_http_answer(predictions)

@predictions_router.get('/allPredictions')
async def get_predictions(db:db_dependency, user: user_dependency):
    predictions = db.query(Prediction).filter(Prediction.user_id == user['id']).all()
    return default_http_answer(predictions)

@predictions_router.post('/', status_code=status.HTTP_201_CREATED)
async def create_predictions(db:db_dependency, user: user_dependency, prediction: PredictionCreate):
    new_prediction = Prediction(**prediction.model_dump(), user_id=user.get('id'))
    db.add(new_prediction)
    db.commit()
    db.refresh(new_prediction)
    # return default_http_answer(new_prediction)

@predictions_router.delete('/', status_code=status.HTTP_200_OK)
async def delete_predictions(db:db_dependency, user: user_dependency, prediction_id: int):
    prediction = db.query(Prediction).filter(Prediction.id == prediction_id).first()
    if prediction:
        db.delete(prediction)
        db.commit()
        # return default_http_answer(prediction,'Prediction has been deleted sucessfully')
