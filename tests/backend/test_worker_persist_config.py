import pytest

from app.config import SettingsError, load_settings


def test_persist_defaults_and_caps():
    settings = load_settings({})
    assert (settings.TASK_PERSIST_COMMIT_TIMEOUT_SECONDS,
            settings.TASK_PERSIST_CLEANUP_TIMEOUT_SECONDS) == (2.0, 1.0)
    settings = load_settings({'TASK_PERSIST_COMMIT_TIMEOUT_SECONDS': '3',
                              'TASK_PERSIST_CLEANUP_TIMEOUT_SECONDS': '5'})
    assert (settings.TASK_PERSIST_COMMIT_TIMEOUT_SECONDS,
            settings.TASK_PERSIST_CLEANUP_TIMEOUT_SECONDS) == (3.0, 5.0)


@pytest.mark.parametrize('name,cap', [('TASK_PERSIST_COMMIT_TIMEOUT_SECONDS', 3),
                                     ('TASK_PERSIST_CLEANUP_TIMEOUT_SECONDS', 5)])
@pytest.mark.parametrize('value', ['0', '-1', 'NaN', 'Inf', 'over', 'private-token'])
def test_persist_bad_budget_is_redacted(name, cap, value):
    supplied = str(cap + .01) if value == 'over' else value
    with pytest.raises(SettingsError) as caught:
        load_settings({name: supplied})
    assert name in str(caught.value)
    assert supplied not in str(caught.value)
