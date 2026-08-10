"""文件存储抽象层。"""

from app.core.storage.base import StorageBackend
from app.core.storage.factory import build_file_key, get_storage

__all__ = ["StorageBackend", "get_storage", "build_file_key"]
