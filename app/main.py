from fastapi import FastAPI
from app.api import router, admin_router

app = FastAPI()
app.include_router(router)
app.include_router(admin_router)