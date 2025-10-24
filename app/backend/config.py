import os
from dotenv import load_dotenv


load_dotenv()


class Config:
    MONGO_URI = os.getenv("MONGO_URI")
    SECRET_KEY = os.getenv("FLASK_SECRET")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ACCESS_EXPIRES = int(os.getenv("JWT_ACCESS_EXPIRES", "3600"))
