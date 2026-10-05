import hashlib
import io
from pathlib import Path
import sqlite3
import tarfile
import pytest
from app.tools.install_backup import backup_volumes, restore_volumes, BackupError

def fixtures(tmp_path):
    volumes = {name: tmp_path/name for name in ('app','neo4j','neo4j-logs')}
    for path in volumes.values(): path.mkdir()
    db = sqlite3.connect(volumes['app']/'smartsketch.sqlite3'); db.execute('CREATE TABLE fixture(value TEXT)'); db.execute("INSERT INTO fixture VALUES ('synthetic')"); db.commit(); db.close()
    (volumes['neo4j']/'graph-fixture').write_bytes(b'synthetic graph')
    return volumes

def test_backup_restores_sqlite_and_graph_as_one_set(tmp_path):
    volumes = fixtures(tmp_path); export=tmp_path/'backup'; export.mkdir()
    backup_volumes(volumes,export)
    target={name:tmp_path/('stage-'+name) for name in volumes}
    for path in target.values(): path.mkdir()
    restore_volumes(target,export)
    for name in volumes:
        for path in volumes[name].rglob('*'):
            if path.is_file(): assert path.read_bytes()==(target[name]/path.relative_to(volumes[name])).read_bytes()

@pytest.mark.parametrize('kind',['traversal','absolute','symlink','truncated','missing'])
def test_restore_rejects_traversal_links_and_partial_archives(tmp_path,kind):
    volumes=fixtures(tmp_path); export=tmp_path/'backup';export.mkdir();backup_volumes(volumes,export)
    bad=export/'neo4j.tar.gz'
    if kind=='truncated': bad.write_bytes(bad.read_bytes()[:15])
    elif kind=='missing': bad.unlink()
    else:
        with tarfile.open(bad,'w:gz') as archive:
            item=tarfile.TarInfo({'traversal':'../outside','absolute':'/outside','symlink':'link'}[kind]);item.size=1
            if kind=='symlink': item.type=tarfile.SYMTYPE;item.linkname='../outside';item.size=0
            archive.addfile(item,io.BytesIO(b'x'))
    target={name:tmp_path/('stage-'+name) for name in volumes}
    for path in target.values(): path.mkdir()
    with pytest.raises(BackupError): restore_volumes(target,export)
    assert all(not list(path.iterdir()) for path in target.values())

def test_restore_preserves_volume_root_permissions(tmp_path):
    import os
    volumes=fixtures(tmp_path);os.chmod(volumes['app'],0o700)
    export=tmp_path/'backup';export.mkdir();backup_volumes(volumes,export)
    targets={name:tmp_path/('stage-'+name) for name in volumes}
    for root in targets.values():root.mkdir(mode=0o755)
    restore_volumes(targets,export)
    assert targets['app'].stat().st_mode & 0o777==0o700
    assert targets['app'].stat().st_uid==volumes['app'].stat().st_uid
