import json
import subprocess
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[2]
def test_release_compose_keeps_secrets_off_web():
    data=yaml.safe_load((ROOT/'packaging/compose.release.yaml').read_text())
    web=data['services']['web']
    assert 'env_file' not in web and 'environment' not in web
    assert all('127.0.0.1:' in x for x in web['ports'])
    assert not data['services']['neo4j'].get('ports')
    for s in ('api','worker','migrate','bootstrap','probe'):
        assert data['services'][s]['env_file']==['.env']
    assert data['volumes']['neo4j-data']['labels']['io.smartsketch.installation']=='${INSTALL_ID:?}'

def test_release_preserves_nginx_sse_settings():
    # Consume effective config directives, not a snapshot of source formatting.
    lines=[x.strip() for x in (ROOT/'src/frontend/nginx.conf').read_text().splitlines()]
    assert 'proxy_buffering off;' in lines and 'proxy_read_timeout 1h;' in lines

def test_compose_environment_preserves_emitted_special_characters(tmp_path):
    import shutil
    cli=shutil.which('docker') or str(Path.home()/'.docker/bin/docker')
    val='key $HOME ${FOO} # \' " \\ ends\\'
    env=tmp_path/'fixture.env';env.write_text('KEY='+json.dumps(val,ensure_ascii=False).replace('$','$$')+'\n')
    compose=tmp_path/'compose.yml';compose.write_text('services:\n  fixture:\n    image: busybox\n    environment:\n      KEY: ${KEY}\n')
    r=subprocess.run([cli,'compose','--env-file',str(env),'-f',str(compose),'config','--environment'],capture_output=True,text=True)
    assert r.returncode==0
    assert next(x for x in r.stdout.splitlines() if x.startswith('KEY='))[4:]==val
