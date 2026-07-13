from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class RequestIdentity:
    user_id: int
    workspace_id: int
    role: str = "user"
    admin_target_workspace_id: int | None = None

    @property
    def effective_workspace_id(self) -> int:
        return self.admin_target_workspace_id or self.workspace_id


_identity: ContextVar[RequestIdentity | None] = ContextVar("request_identity", default=None)


def current_identity() -> RequestIdentity | None:
    return _identity.get()


def current_workspace_id() -> int | None:
    identity = current_identity()
    return identity.effective_workspace_id if identity is not None else None


def set_identity(identity: RequestIdentity | None) -> Token[RequestIdentity | None]:
    return _identity.set(identity)


def reset_identity(token: Token[RequestIdentity | None]) -> None:
    _identity.reset(token)


@contextmanager
def workspace_context(identity: RequestIdentity) -> Iterator[None]:
    token = set_identity(identity)
    try:
        yield
    finally:
        reset_identity(token)
