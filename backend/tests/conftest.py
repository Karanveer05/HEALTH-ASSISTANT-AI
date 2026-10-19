"""Tests run on a throwaway database, offline (rule-based) LLM mode and no live price lookups."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="hc-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["LLM_PROVIDER"] = "offline"
os.environ["LIVE_PRICES"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
