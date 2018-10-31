import os
from contextlib import contextmanager

@contextmanager
def write_file_or_remove(path):
    """Open a file for writing, create its parent directory if needed

    If the writing fails, the file is removed.
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            yield f
    except:
        # remove partially written file
        try:
            os.remove(path)
        except OSError:
            pass
        raise

