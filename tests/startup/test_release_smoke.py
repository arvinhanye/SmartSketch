"""Explicit local-image scenario, distinct from immutable GHCR/platform release acceptance."""
import os
from pathlib import Path
import subprocess
import pytest
ROOT=Path(__file__).resolve().parents[2]
@pytest.mark.parametrize('case',['TestLocalReleaseLoginStopRestart','TestLocalTwoInstallationsRemainIndependent','TestLocalOwnedBackupRestore'])
def test_isolated_release_lifecycle(case):
    assert os.environ.get('SMARTSKETCH_STARTUP_SMOKE')=='1', 'Explicit owned test images required; missing setup is not PASS.'
    for key in ('STARTUP_TEST_BACKEND','STARTUP_TEST_FRONTEND'):
        assert os.environ.get(key,'').startswith('smartsketch-startup-test-'), 'Only this run synthetic image tags permitted.'
    result=subprocess.run(['go','test','./internal/launch','-run','^'+case+'$','-count=1','-timeout=20m','-v'],cwd=ROOT/'launcher',env=dict(os.environ,TMPDIR='/private/tmp',GOTOOLCHAIN='local'),capture_output=True,text=True,timeout=1250)
    assert result.returncode==0,result.stdout+result.stderr
