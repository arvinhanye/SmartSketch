import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile
import zipfile
import pytest
ROOT=Path(__file__).resolve().parents[2]

def module():
    spec=importlib.util.spec_from_file_location('package_launcher',ROOT/'scripts/package-launcher.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def inputs(tmp_path):
    manifest={'version':'fixture-1','backend_image':'ghcr.io/arvinhanye/smartsketch-backend@sha256:'+'0'*64,'frontend_image':'ghcr.io/arvinhanye/smartsketch-frontend@sha256:'+'1'*64,'neo4j_image':'neo4j@sha256:'+'2'*64,'compose_sha256':hashlib.sha256((ROOT/'packaging/compose.release.yaml').read_bytes()).hexdigest(),'targets':['darwin-arm64','darwin-amd64','windows-amd64']}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest));binaries=tmp_path/'binaries';binaries.mkdir()
    for target in manifest['targets']:(binaries/('smartsketch-launcher-'+target+('.exe' if target.startswith('windows') else ''))).write_bytes(b'synthetic binary fixture')
    return path,binaries,tmp_path/'dist'

def test_macos_archive_preserves_executable_entry(tmp_path):
    files=module().package_release(*inputs(tmp_path))
    for file in files:
        if file.suffix=='.gz':
            with tarfile.open(file) as archive:
                entries={Path(x.name).name:x for x in archive.getmembers()}
                assert entries['start-macos.command'].mode==0o755
                assert entries['smartsketch-launcher'].mode==0o755

def test_windows_cmd_uses_quoted_bundle_path(tmp_path):
    files=module().package_release(*inputs(tmp_path))
    with zipfile.ZipFile(next(x for x in files if x.suffix=='.zip')) as archive:
        name=next(x for x in archive.namelist() if x.endswith('start-windows.cmd'));text=archive.read(name).decode('utf-8')
        assert '"%~dp0bin\\smartsketch-launcher.exe"' in text

def test_packages_have_manifest_hashes_and_no_credentials(tmp_path):
    manifest,binaries,dest=inputs(tmp_path);files=module().package_release(manifest,binaries,dest)
    sums=(dest/'SHA256SUMS').read_text()
    for file in files:
        assert hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.name in sums
        if file.suffix=='.zip':
            with zipfile.ZipFile(file) as archive:names=archive.namelist()
        else:
            with tarfile.open(file) as archive:names=archive.getnames()
        assert not any(Path(name).name=='.env' or name.endswith(('.sqlite3','.db')) for name in names)
        assert any(name.endswith('release-manifest.json') for name in names)

def test_mutable_or_incomplete_manifest_is_rejected(tmp_path):
    path,binaries,dest=inputs(tmp_path);data=json.loads(path.read_text());data['backend_image']='image:latest';path.write_text(json.dumps(data))
    with pytest.raises(ValueError):module().package_release(path,binaries,dest)
    assert not dest.exists()
