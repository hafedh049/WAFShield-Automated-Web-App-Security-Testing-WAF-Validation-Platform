from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from bson.objectid import ObjectId
import bcrypt
import datetime


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    if not name or not email or not password:
        return jsonify({"message": "name, email and password required"}), 400

    db = current_app.db
    if db.users.find_one({"email": email}):
        return jsonify({"message": "email already exists"}), 400

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = {
        "name": name,
        "email": email,
        "password": hashed.decode("utf-8"),
        "createdAt": datetime.datetime.utcnow(),
        "updatedAt": datetime.datetime.utcnow(),
    }
    res = db.users.insert_one(user)
    user_out = {"id": str(res.inserted_id), "name": name, "email": email}
    token = create_access_token(identity=str(res.inserted_id))
    return jsonify({"user": user_out, "token": token}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"message": "email and password required"}), 400

    db = current_app.db
    user = db.users.find_one({"email": email})
    if not user:
        return jsonify({"message": "invalid credentials"}), 401

    stored = user.get("password")
    if not stored:
        return jsonify({"message": "invalid credentials"}), 401

    if not bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8")):
        return jsonify({"message": "invalid credentials"}), 401

    token = create_access_token(identity=str(user["_id"]))
    user_out = {"id": str(user["_id"]), "name": user["name"], "email": user["email"]}
    return jsonify({"user": user_out, "token": token}), 200


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email = data.get("email")
    if not email:
        return jsonify({"message": "email required"}), 400

    # In production you'd generate a reset token and send email. Here we mock:
    return jsonify({"message": "If the email exists, a reset link was sent."}), 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    # For JWT stateless approach, you can implement token revocation/blacklist.
    return jsonify({"message": "logged out (stateless JWT)"}), 200
