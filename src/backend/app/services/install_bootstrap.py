"""Local bootstrap service; not an API or teacher self-registration route."""
import uuid
from app.services.auth import normalize_username, USERNAME_PATTERN, PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH, hash_password
from app.repositories.install_bootstrap import initialize_teacher, BootstrapConflict, BootstrapOutcome

class BootstrapError(ValueError):
    pass

def create_first_teacher(sqlite_url: str, username: str, password: str) -> BootstrapOutcome:
    if not isinstance(username,str) or not isinstance(password,str):
        raise BootstrapError('invalid bootstrap input')
    normalized=normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(normalized) or not PASSWORD_MIN_LENGTH<=len(password)<=PASSWORD_MAX_LENGTH:
        raise BootstrapError('invalid bootstrap input')
    try:
        return initialize_teacher(sqlite_url,account_id=uuid.uuid4().hex,username=normalized,password_hash=hash_password(password))
    except BootstrapConflict:
        raise BootstrapError('existing installation accounts were preserved') from None
