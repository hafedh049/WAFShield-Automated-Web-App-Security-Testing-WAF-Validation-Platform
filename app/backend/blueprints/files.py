from flask import Blueprint, request, jsonify, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson.objectid import ObjectId
from utils import sha256_bytes, allowed_filename, to_base64
import datetime
import io
import mimetypes


files_bp = Blueprint("files", __name__)


@files_bp.route("", methods=["GET"])
@jwt_required()
def list_files():
    user_id = get_jwt_identity()
    db = current_app.db

    # query params
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 12))
    search = request.args.get("search", "").strip()
    extension = request.args.get("extension")
    sort_by = request.args.get("sortBy", "uploadDate")
    sort_order = int(request.args.get("sortOrder", -1))
    min_size = request.args.get("minSize")
    max_size = request.args.get("maxSize")

    q = {"userId": ObjectId(user_id)}
    if search:
        q["name"] = {"$regex": search, "$options": "i"}
    if extension:
        q["extension"] = extension
    if min_size:
        q["size"] = q.get("size", {})
        q["size"]["$gte"] = int(min_size)
    if max_size:
        q["size"] = q.get("size", {})
        q["size"]["$lte"] = int(max_size)

    total = db.files.count_documents(q)
    skip = (page - 1) * limit
    cursor = db.files.find(q).sort(sort_by, sort_order).skip(skip).limit(limit)
    files = []

    for f in cursor:
        f["_id"] = str(f["_id"])
        f["userId"] = str(f["userId"])
        files.append(f)

    return jsonify(
        {
            "files": files,
            "total": total,
            "page": page,
            "totalPages": (total + limit - 1) // limit,
        }
    )


@files_bp.route("/upload", methods=["POST"])
@jwt_required()
def upload_files():
    user_id = get_jwt_identity()
    db = current_app.db
    fs = current_app.fs

    if "files" not in request.files:
        # allow any field names: collect all files
        uploaded_files = list(request.files.values())
    else:
        uploaded_files = request.files.getlist("files")

    saved = []
    duplicates = []

    for up in uploaded_files:
        raw = up.read()
        up.seek(0)
        file_hash = sha256_bytes(raw)
        existing = db.files.find_one({"hash": file_hash, "userId": ObjectId(user_id)})
        if existing:
            duplicates.append(str(existing["_id"]))
        continue

    return jsonify
