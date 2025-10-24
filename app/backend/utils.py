import hashlib
from werkzeug.utils import secure_filename
from io import BytesIO
import base64


def sha256_bytes(content: bytes) -> str:
    h = hashlib.sha256()
    h.update(content)
    return h.hexdigest()


def allowed_filename(filename: str) -> str:
    return secure_filename(filename)


def to_base64(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")
