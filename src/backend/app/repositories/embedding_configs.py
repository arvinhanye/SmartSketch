"""Encrypted teacher embedding rows; course ownership chooses the credential."""
from dataclasses import dataclass, field
from app.repositories.sqlite import connect
from app.repositories.model_configs import SealedKey

@dataclass(frozen=True)
class EmbeddingConfigRow:
    user_id: str
    base_url: str
    model: str
    dimensions: int
    sealed: SealedKey = field(repr=False)
    key_hint: str
    space: str
    revision: str
    version: int
    updated_at: str

def get_config(sqlite_url: str, user_id: str) -> EmbeddingConfigRow | None:
    with connect(sqlite_url) as db:
        row = db.execute('SELECT user_id,base_url,model,dimensions,key_ciphertext,key_nonce,key_hint,space,revision,version,updated_at FROM teacher_embedding_configs WHERE user_id=?', (user_id,)).fetchone()
    if row is None:
        return None
    return EmbeddingConfigRow(*row[:4], SealedKey(bytes(row[4]),bytes(row[5])), *row[6:])

def for_course(sqlite_url: str, course_id: str) -> EmbeddingConfigRow | None:
    with connect(sqlite_url) as db:
        row = db.execute('SELECT teacher_id FROM courses WHERE id=?',(course_id,)).fetchone()
    return get_config(sqlite_url,row[0]) if row else None

def owned_courses(sqlite_url: str, user_id: str) -> list[str]:
    with connect(sqlite_url) as db:
        return [r[0] for r in db.execute('SELECT id FROM courses WHERE teacher_id=? ORDER BY id',(user_id,))]
