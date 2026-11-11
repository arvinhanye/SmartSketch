"""Repository-level test accounts with a format-valid placeholder password hash.

These accounts are not for password verification or login tests."""

import uuid

from app.repositories.accounts import insert_account

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


def make_account(url: str, username: str, role: str):
    return insert_account(
        url,
        account_id=uuid.uuid4().hex,
        username=username,
        password_hash=VALID_HASH,
        role=role,
    )
