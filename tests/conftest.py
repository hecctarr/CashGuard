"""Tests run on their own temporary data folder, so they never overwrite the app's demo data."""
import os
import tempfile

os.environ.setdefault("CASHGUARD_DATA_DIR", tempfile.mkdtemp(prefix="cashguard_test_"))
