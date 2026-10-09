"""Offline, all-volume archive tool. Fixed container paths; no network clients."""
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import sys
import tarfile
import tempfile

NAMES = ('app','neo4j','neo4j-logs')
class BackupError(ValueError): pass

def _db_gate(root):
    db=root/'smartsketch.sqlite3'
    if db.is_symlink() or not db.is_file(): raise BackupError('SQLite snapshot missing')
    # Source mounts stay physically read-only. Even an offline WAL-mode database
    # may need a writable -shm file for a mode=ro reader; validate a private copy
    # including WAL instead of writing source metadata or ignoring WAL with immutable.
    try:
        with tempfile.TemporaryDirectory(prefix='smartsketch-db-check-') as temp:
            copied=Path(temp)/db.name
            shutil.copyfile(db,copied)
            wal=Path(str(db)+'-wal')
            if wal.is_symlink(): raise BackupError('Unsupported volume entry')
            if wal.exists(): shutil.copyfile(wal,Path(str(copied)+'-wal'))
            with sqlite3.connect(copied.as_uri()+'?mode=ro',uri=True) as conn:
                conn.execute('PRAGMA query_only=ON')
                if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise BackupError('SQLite snapshot invalid')
                from app.repositories.sqlite import _check_no_live_leases, MigrationError
                try: _check_no_live_leases(conn)
                except MigrationError: raise BackupError('Live task lease blocks backup') from None
    except (OSError,sqlite3.Error): raise BackupError('SQLite snapshot invalid') from None

def _source_files(root):
    if root.is_symlink() or not root.is_dir(): raise BackupError('Invalid volume source')
    files=[]
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not (path.is_file() or path.is_dir()): raise BackupError('Unsupported volume entry')
        files.append(path)
    return files

def backup_volumes(volumes,export):
    if set(volumes)!=set(NAMES) or export.is_symlink(): raise BackupError('Invalid snapshot set')
    _db_gate(volumes['app'])
    all_files={name:_source_files(volumes[name]) for name in NAMES}
    size=sum(p.stat().st_size for paths in all_files.values() for p in paths if p.is_file())
    if shutil.disk_usage(export).free < size*2+16*1024*1024: raise BackupError('Insufficient backup space')
    try:
        for name in NAMES:
            dest=export/(name+'.tar.gz')
            if dest.exists(): raise BackupError('Snapshot already exists')
            temporary=export/(name+'.partial')
            with tarfile.open(temporary,'w:gz',format=tarfile.PAX_FORMAT) as archive:
                archive.add(volumes[name],arcname=".",recursive=False)
                for path in all_files[name]: archive.add(path,arcname=path.relative_to(volumes[name]).as_posix(),recursive=False)
            os.chmod(temporary,0o600);os.replace(temporary,dest)
    except (OSError,tarfile.TarError): raise BackupError('Snapshot export failed') from None

def _members(archive):
    seen=set(); total=0
    for item in archive.getmembers():
        path=PurePosixPath(item.name)
        if path.is_absolute() or (not path.parts and not (item.name=='.' and item.isdir())) or any(x in ('..','') for x in path.parts) or '\\' in item.name or ':' in item.name or item.name in seen or not (item.isfile() or item.isdir()): raise BackupError('Unsupported archive entry')
        seen.add(item.name);total+=item.size
        if item.size<0 or total>2**40: raise BackupError('Archive size limit')
    return total

def restore_volumes(volumes,export):
    if set(volumes)!=set(NAMES) or export.is_symlink(): raise BackupError('Invalid snapshot set')
    for root in volumes.values():
        if root.is_symlink() or not root.is_dir() or list(root.iterdir()): raise BackupError('Restore target must be empty staging volume')
    # Validate and fully extract all archives before writing ANY staging volume.
    handles=[]
    try:
        with tempfile.TemporaryDirectory(prefix='smartsketch-restore-') as temp:
            staging=Path(temp)
            for name in NAMES:
                path=export/(name+'.tar.gz')
                if path.is_symlink() or not path.is_file(): raise BackupError('Snapshot incomplete')
                archive=tarfile.open(path,'r:gz');handles.append(archive)
                size=_members(archive)
                if shutil.disk_usage(staging).free<size+16*1024*1024 or shutil.disk_usage(volumes[name]).free<size+16*1024*1024: raise BackupError('Insufficient restore space')
                target=staging/name;target.mkdir()
                for item in archive.getmembers():
                    dest=target/item.name
                    if item.isdir(): dest.mkdir(parents=True,exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True,exist_ok=True)
                        src=archive.extractfile(item)
                        with dest.open('xb') as output: shutil.copyfileobj(src,output)
                        if dest.stat().st_size!=item.size: raise BackupError('Truncated snapshot')
                    os.chmod(dest,item.mode&0o777)
            _db_gate(staging/'app')
            for name,archive in zip(NAMES,handles):
                target=volumes[name];shutil.copytree(staging/name,target,dirs_exist_ok=True)
                if os.geteuid()==0:
                    for item in archive.getmembers(): os.chown(target/item.name,item.uid,item.gid)
    except (OSError,tarfile.TarError,EOFError): raise BackupError('Snapshot restore failed') from None
    finally:
        for archive in handles: archive.close()

def main():
    try:
        if len(sys.argv)!=2 or sys.argv[1] not in ('backup','restore'): raise BackupError('Invalid operation')
        mode=sys.argv[1]; roots={name:Path('/source' if mode=='backup' else '/stage')/name for name in NAMES}
        (backup_volumes if mode=='backup' else restore_volumes)(roots,Path('/backup'))
        print(json.dumps({'complete':True}));return 0
    except Exception:
        print('Offline snapshot operation failed; original volumes were preserved.',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
