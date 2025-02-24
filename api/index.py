import asyncio
import os
import sys
from typing import Optional, Union
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer

from api.DB.database import Base, engine
from api.routers.routers import addRouters

import uvicorn

# Including security
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# Create FastAPI instance with custom docs and openapi url
app = FastAPI(docs_url="/api/docs", 
              openapi_url="/api/openapi.json",
            )

# Configurating the middleware
origins = [ 
        "http://localhost:3000", 
        "http://localhost:3001", 
        "http://localhost:3002", 
        "http://localhost:3003", 
        "http://localhost:3004", 
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
Base.metadata.create_all(bind=engine)
addRouters(app)

# for route in app.routes:
#     print(f"Path: {route.path}, Name: {route.name}")

def run_server(app, host="0.0.0.0", port=5001):
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    if asyncio.get_event_loop().is_running():
        asyncio.create_task(server.serve())
    else:
        asyncio.run(server.serve())

# print("Current Working Directory:", os.getcwd())
# print("Python Path:", sys.path)

# Start the server
if __name__ == "api.index":
    run_server(app)
