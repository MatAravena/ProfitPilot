from fastapi import APIRouter, FastAPI
from api.routers.auth import auth_router
from api.routers.users import users_router
from api.routers.trades import trades_router
# from api.routers.orders import orders_router
from api.routers.predictions import predictions_router

def addRouters(app:FastAPI):
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(trades_router)
    # app.include_router(orders_router)
    app.include_router(predictions_router)

    @app.get("/")
    async def root():
        return {"message": "Hello from Profit Pilot"}
