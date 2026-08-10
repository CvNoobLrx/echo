"""存储后端抽象接口。"""

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """按 user_id 组织对象路径的统一文件存储接口。"""

    @abstractmethod
    async def save(self, file_key: str, content: bytes) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get(self, file_key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, file_key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, file_key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_url(self, file_key: str, expires: int = 3600) -> str:
        raise NotImplementedError
