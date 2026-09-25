"""D-11：上传单文件上限 UPLOAD_MAX_BYTES 与资料存储根目录 STORAGE_DIR 的配置落地。"""

import pytest

from app.config import SettingsError, load_settings
from app.services.file_storage import FileStorage, FileTooLargeError


def test_defaults_follow_d11_and_storage_plan():
    settings = load_settings({})

    assert settings.UPLOAD_MAX_BYTES == 52_428_800  # 50 MiB（D-11）
    assert settings.STORAGE_DIR == "./storage"


def test_explicit_values_are_typed():
    settings = load_settings({"UPLOAD_MAX_BYTES": "1024", "STORAGE_DIR": "/srv/smartsketch"})

    assert settings.UPLOAD_MAX_BYTES == 1024
    assert settings.STORAGE_DIR == "/srv/smartsketch"


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "50MiB", ""])
def test_invalid_upload_limit_names_the_variable(value):
    with pytest.raises(SettingsError, match="UPLOAD_MAX_BYTES"):
        load_settings({"UPLOAD_MAX_BYTES": value})


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_storage_dir_names_the_variable(value):
    with pytest.raises(SettingsError, match="STORAGE_DIR"):
        load_settings({"STORAGE_DIR": value})


def test_file_storage_accepts_settings_and_enforces_the_limit(tmp_path):
    settings = load_settings({"UPLOAD_MAX_BYTES": "8", "STORAGE_DIR": str(tmp_path / "materials")})
    storage = FileStorage(settings.STORAGE_DIR, max_bytes=settings.UPLOAD_MAX_BYTES)

    with pytest.raises(FileTooLargeError) as excinfo:
        storage.save("notes.txt", "text/plain", [b"12345", b"6789"])

    assert excinfo.value.details == {"limit_bytes": 8}
    assert list((tmp_path / "materials").iterdir()) == []
