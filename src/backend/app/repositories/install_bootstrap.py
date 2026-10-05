"""One transaction for an empty installation's first teacher; never reset accounts."""
from dataclasses import dataclass
from app.repositories.sqlite import connect

class BootstrapConflict(ValueError):
    pass

@dataclass(frozen=True)
class BootstrapOutcome:
    user_id: str
    username: str
    created: bool

def initialize_teacher(sqlite_url: str, *, account_id: str, username: str, password_hash: str) -> BootstrapOutcome:
    with connect(sqlite_url) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            rows=db.execute('SELECT id,username,role,disabled_at FROM users').fetchall()
            if rows:
                if len(rows)!=1 or rows[0][1:]!=(username,'teacher',None):
                    raise BootstrapConflict('installation account state is not empty or recognized')
                result=BootstrapOutcome(rows[0][0],username,False)
            else:
                db.execute('INSERT INTO users(id,username,password_hash,role) VALUES (?,?,?,?)',(account_id,username,password_hash,'teacher'))
                result=BootstrapOutcome(account_id,username,True)
            db.execute('COMMIT')
            return result
        except BaseException:
            db.execute('ROLLBACK')
            raise
