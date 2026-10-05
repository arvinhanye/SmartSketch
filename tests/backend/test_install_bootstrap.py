import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.repositories.sqlite import migrate
from app.repositories.accounts import find_by_username
from app.services.auth import create_account
from app.services.install_bootstrap import create_first_teacher, BootstrapError
from app.tools.bootstrap_teacher import run

@pytest.fixture
def migrated_sqlite_url(tmp_path):
    url='sqlite:///'+str(tmp_path/'fixture.sqlite3')
    migrate(url)
    return url

def test_bootstrap_teacher_is_idempotent_and_preserves_password_hash(migrated_sqlite_url):
    first=create_first_teacher(migrated_sqlite_url,'first_teacher','fixture-pass-one')
    before=find_by_username(migrated_sqlite_url,'first_teacher').password_hash
    again=create_first_teacher(migrated_sqlite_url,'first_teacher','fixture-pass-two')
    assert first.created and not again.created
    assert first.user_id==again.user_id
    assert find_by_username(migrated_sqlite_url,'first_teacher').password_hash==before

@pytest.mark.parametrize('role,name',[('student','first_teacher'),('teacher','other_teacher')])
def test_bootstrap_rejects_nonempty_unrecognized_database(migrated_sqlite_url,role,name):
    create_account(migrated_sqlite_url,name,'fixture-pass-one',role)
    with pytest.raises(BootstrapError): create_first_teacher(migrated_sqlite_url,'first_teacher','fixture-pass-two')
    with sqlite3.connect(migrated_sqlite_url.removeprefix('sqlite:///')) as c:
        assert c.execute('SELECT count(*) FROM users').fetchone()[0]==1

def test_concurrent_bootstrap_creates_one_teacher(migrated_sqlite_url):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:create_first_teacher(migrated_sqlite_url,'first_teacher','fixture-pass-one'),range(2)))
    assert sum(x.created for x in results)==1
    assert results[0].user_id==results[1].user_id

@pytest.mark.parametrize('text',['{"username":"teacher_one","password":"fixture-secret","extra":1}', '{"username":"teacher_one","password":123}', 'x'*17000])
def test_cli_stdin_never_echoes_secret(migrated_sqlite_url,text):
    out=io.StringIO()
    with pytest.raises(BootstrapError) as error: run(migrated_sqlite_url,io.StringIO(text),out)
    assert 'fixture-secret' not in str(error.value)
    assert out.getvalue()==''
