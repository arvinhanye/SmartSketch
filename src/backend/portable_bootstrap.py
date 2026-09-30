"""Ensure embedded Python executes this distribution, not its bundled source."""
import os
import runpy
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    arguments = sys.argv[1:]
    if arguments[0] == "-m":
        sys.argv = arguments[1:]
        runpy.run_module(arguments[1], run_name="__main__", alter_sys=True)
    else:
        sys.argv = arguments
        runpy.run_path(arguments[0], run_name="__main__")
