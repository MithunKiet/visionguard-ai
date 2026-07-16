from abc import ABC, abstractmethod

from src.modules.identity.domain.entities import UserEntity


class IUserRepository(ABC):

    @abstractmethod
    async def get_by_email(self, email: str) -> UserEntity | None: ...

    @abstractmethod
    async def get_by_id(self, user_id: str) -> UserEntity | None: ...

    @abstractmethod
    async def update_last_login(self, user_id: str) -> None: ...

    @abstractmethod
    async def update_password(self, user_id: str, new_hash: str) -> None: ...

    @abstractmethod
    async def get_internal_id(self, user_id: str) -> int | None: ...
