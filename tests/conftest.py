import os
import pytest
from downloader import Storage


@pytest.fixture
def storage(tmpdir):
    storage = Storage(os.path.join(tmpdir, 'RADS'))
    storage.s = None  # prevent requests
    return storage

