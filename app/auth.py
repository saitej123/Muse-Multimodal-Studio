"""The studio has no accounts and no login screen.

Every request runs as a single local identity. ``User`` is kept because jobs
record an owner id and the admin tabs check the role.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class User:
    id: str
    email: str
    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def public(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "role": self.role,
        }
