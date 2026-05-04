#!/usr/bin/env python3
"""Smoke tests for the Docker sandbox runner.

Prerequisites: build the sandbox image first:
    docker build -f Dockerfile.sandbox -t ga4-sandbox .
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sandbox.runner import run_code


def test_basic_exec():
    result = run_code('print("hello sandbox")')
    assert result["exit_code"] == 0, f"Expected exit 0: {result}"
    assert "hello sandbox" in result["stdout"], f"Expected output: {result}"
    print("PASS basic exec")


def test_pandas():
    code = """
import pandas as pd
df = pd.DataFrame({"a": [1, 2, 3]})
print(int(df["a"].sum()))
"""
    result = run_code(code)
    assert result["exit_code"] == 0, f"Pandas failed: {result}"
    assert "6" in result["stdout"], f"Expected sum=6: {result}"
    print("PASS pandas")


def test_network_blocked():
    code = """
import urllib.request
try:
    urllib.request.urlopen("http://example.com", timeout=3)
    print("NETWORK_OPEN")
except Exception:
    print("NETWORK_BLOCKED")
"""
    result = run_code(code)
    assert "NETWORK_BLOCKED" in result["stdout"], f"Network should be blocked: {result}"
    print("PASS network blocked")


def test_exit_nonzero():
    result = run_code("raise RuntimeError('deliberate error')")
    assert result["exit_code"] != 0, f"Expected non-zero exit: {result}"
    assert result["stderr"] != "", f"Expected stderr: {result}"
    print("PASS non-zero exit captured")


if __name__ == "__main__":
    print("Running sandbox verification...\n")
    test_basic_exec()
    test_pandas()
    test_network_blocked()
    test_exit_nonzero()
    print("\nAll sandbox checks passed.")
