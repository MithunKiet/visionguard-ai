from abc import ABC, abstractmethod
from uuid import UUID

from src.modules.identity.domain.entities import UserEntity


class IUserRepository(ABC):

    @abstractmethod
    async def get_by_email(self, email: str) -> UserEntity | None: ...

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> UserEntity | None: ...

    @abstractmethod
    async def update_last_login(self, user_id: UUID) -> None: ...

    @abstractmethod
    async def update_password(self, user_id: UUID, new_hash: str) -> None: ...
