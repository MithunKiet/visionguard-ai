from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.app import create_app

app: FastAPI = create_app()
