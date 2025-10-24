from flask import Flask
from config import Config
from pymongo import MongoClient
import gridfs
from flask_jwt_extended import JWTManager


from blueprints.auth import auth_bp
from blueprints.files import files_bp


app = Flask(__name__)
app.config.from_object(Config)


# Mongo
client = MongoClient(app.config['MONGO_URI'])
db = client.get_default_database()
fs = gridfs.GridFS(db)


# JWT
jwt = JWTManager(app)


# Attach to app for blueprints
app.mongo_client = client
app.db = db
app.fs = fs


# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(files_bp, url_prefix='/api/files')


if __name__ == '__main__':
app.run(debug=True, host='0.0.0.0')