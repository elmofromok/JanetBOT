"""Puts the repo root on `sys.path` so `tests/` can import the flat modules.

The modules sit at the root rather than in a package (#3), and pytest only
adds a rootdir it finds a conftest in. This file exists for that and nothing
else.
"""
