import pytest
import cdtb.export as cdtb_export


# use an intermediate argvalues variable to avoid large pytest backtraces
_test_reduce_common_paths_arg_values = [
    (['common/a', 'common/b'],
     ['common/a', 'common/b', 'old/a', 'old/b'],
     [],
     ['common']),
    (['common/a/x', 'common/a/y', 'common/b/x', 'common/b/y'],
     ['common/a/x', 'common/a/y', 'common/b/x', 'common/b/y'],
     ['common/a/z'],
     ['common/a/x', 'common/a/y', 'common/b']),
]

@pytest.mark.parametrize("paths1, paths2, excludes, expected", _test_reduce_common_paths_arg_values)
def test_reduce_common_paths(paths1, paths2, excludes, expected):
    got = cdtb_export.reduce_common_paths(paths1, paths2, excludes)
    assert got == expected

