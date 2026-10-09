"""Network evidence and baseline experiments must also work in a fresh CI checkout."""
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_network_evidence_uses_owned_portable_path(tmp_path, monkeypatch):
    integration = ROOT / 'tests/integration'
    monkeypatch.syspath_prepend(str(integration))
    spec = importlib.util.spec_from_file_location(
        '_worker_network_ci_regression', integration / 'test_worker_persist_transport.py')
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    # Reproduce a host where the old macOS-only parent directory does not exist.
    legacy_path = tmp_path / 'missing-macos-private-tmp' / 'evidence.jsonl'
    monkeypatch.setattr(module, 'EVIDENCE', legacy_path, raising=False)
    owned_path = tmp_path / 'owned-ci-run' / 'network.jsonl'
    module.record_evidence({'id': 'owned-ci-run', 'evidence_path': owned_path,
                            'auth': ('neo4j', 'credential-not-in-evidence')},
                           mode='healthy', repeat=0)
    record = json.loads(owned_path.read_text())
    assert record['run_id'] == 'owned-ci-run'
    assert record['mode'] == 'healthy'
    assert len(record['product_sha256']) == len(record['test_sha256']) == 64
    assert 'credential-not-in-evidence' not in owned_path.read_text()
    assert not legacy_path.exists()


def test_integration_checkout_contains_history_for_real_baseline():
    workflow = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())
    checkouts = [step for step in workflow['jobs']['integration']['steps']
                 if step.get('uses', '').startswith('actions/checkout@')]
    assert len(checkouts) == 1
    assert checkouts[0].get('with', {}).get('fetch-depth') == 0, (
        'The real historical git-archive baseline is absent in a shallow checkout')
    assert checkouts[0]['with']['persist-credentials'] is False


def test_decision_identifiers_are_unique_after_main_integration():
    numbers = re.findall(r'^## (ADR-\d+)[：:]', (ROOT / 'docs/decisions.md').read_text(), re.M)
    duplicates = [number for number, count in Counter(numbers).items() if count > 1]
    assert not duplicates, f'Conflicting decision identifiers: {duplicates}'
