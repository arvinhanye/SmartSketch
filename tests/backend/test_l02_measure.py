"""L02：测量脚本的纯函数——multipart 编码与任务终态判定。脚本本身的联网部分不在单测内。"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("measure_web_flow", ROOT / "evaluation/measure_web_flow.py")
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)


def test_multipart_body_contains_filename_and_bytes():
    content_type, body = measure.encode_multipart("ch3.md", b"# title\n", boundary="BOUND")
    assert content_type == "multipart/form-data; boundary=BOUND"
    assert b'name="file"; filename="ch3.md"' in body
    assert b"\r\n\r\n# title\n\r\n--BOUND--\r\n" in body


def test_terminal_stages():
    assert measure.is_terminal("awaiting_review")
    assert measure.is_terminal("failed")
    assert measure.is_terminal("cancelled")
    assert not measure.is_terminal("extracting")
