import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
from downloader import Storage


@pytest.fixture
def storage(tmpdir):
    storage = Storage(os.path.join(tmpdir, 'RADS'))
    storage.s = None  # prevent requests
    return storage

