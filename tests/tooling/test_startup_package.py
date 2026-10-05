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


def run_macos_entry(tmp_path, code):
    import os
    import subprocess
    bundle = tmp_path / '中文 空格 bundle'
    (bundle / 'bin').mkdir(parents=True)
    (bundle / 'start-macos.command').write_bytes((ROOT / 'packaging/start-macos.command').read_bytes())
    (bundle / 'target.txt').write_text('darwin-amd64\n')
    launcher = bundle / 'bin/smartsketch-launcher'
    launcher.write_text('#!/bin/bash\nexit ' + str(code) + '\n')
    launcher.chmod(0o755)
    tools = tmp_path / 'tools'
    tools.mkdir()
    uname = tools / 'uname'
    uname.write_text('#!/bin/bash\necho x86_64\n')
    uname.chmod(0o755)
    env = {'PATH': str(tools) + ':/usr/bin:/bin', 'HOME': str(tmp_path), 'LANG': 'en_US.UTF-8'}
    result = subprocess.run(['/bin/bash', str(bundle / 'start-macos.command')], input='\n', env=env, capture_output=True, text=True, timeout=10)
    return result, bundle


def test_macos_sigkill_explains_possible_gatekeeper_without_bypassing_it(tmp_path):
    result, bundle = run_macos_entry(tmp_path, 137)
    assert result.returncode == 137
    assert 'SIGKILL' in result.stdout and '137' in result.stdout
    assert '隐私与安全性' in result.stdout and '仍要打开' in result.stdout
    assert '可能' in result.stdout  # Signal alone does not establish Gatekeeper.
    assert '内存' in result.stdout  # Retain a non-Gatekeeper investigation route.
    assert '签名' in result.stdout and '公证' in result.stdout
    assert '不要关闭' in result.stdout
    source = (ROOT / 'packaging/start-macos.command').read_text()
    assert 'xattr' not in source and 'spctl' not in source and 'sudo' not in source
    assert not (bundle / '.env').exists()


def test_macos_success_does_not_show_security_error(tmp_path):
    result, _ = run_macos_entry(tmp_path, 0)
    assert result.returncode == 0
    assert 'SIGKILL' not in result.stdout and '仍要打开' not in result.stdout


def test_macos_other_failure_preserves_code_without_gatekeeper_claim(tmp_path):
    result, _ = run_macos_entry(tmp_path, 2)
    assert result.returncode == 2
    assert '启动未完成' in result.stdout
    assert 'SIGKILL' not in result.stdout and '仍要打开' not in result.stdout
