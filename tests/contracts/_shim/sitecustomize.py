"""按 BLOCK_MODULES 环境变量屏蔽指定模块的导入。

用于测试「缺依赖时门禁必须失败」：不依赖本机恰好有没有装某个包，
也不真的卸载任何东西。
"""
import os
import sys


class _Blocker:
    def __init__(self, blocked):
        self.blocked = blocked

    def find_module(self, fullname, path=None):        # py2 兼容签名，py3 忽略
        return self.find_spec(fullname, path)

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in self.blocked:
            raise ImportError(f"blocked by test shim: {fullname}")
        return None


_blocked = {m for m in os.environ.get("BLOCK_MODULES", "").split(",") if m}
if _blocked:
    sys.meta_path.insert(0, _Blocker(_blocked))
