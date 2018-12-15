import os
import pytest
from cdragontoolbox.storage import (
    BaseVersion,
    PatchVersion,
)

@pytest.mark.parametrize("s, t", [
    ("1.2.3", (1, 2, 3)),
    ("10.20.30", (10, 20, 30)),
    ("10", (10,)),
])
def test_base_version_init_ok(t, s):
    assert BaseVersion(t).t == t
    assert BaseVersion(t).s == s
    assert BaseVersion(s).t == t
    assert BaseVersion(s).s == s

@pytest.mark.parametrize("arg, exc", [
    (None, TypeError),
    ("", ValueError),
    ((), ValueError),
    (("1", "2"), TypeError),
])
def test_base_version_init_bad(arg, exc):
    with pytest.raises(exc):
        BaseVersion(arg)

def test_base_version_operators():
    V = BaseVersion

    assert V("1.2.3") == V((1, 2, 3))
    assert V("1.2") != V("1.2.3")

    assert V("1.2") < V("1.2.3")
    assert V("1.2") < V("1.3")
    assert V("1.1.3") < V("1.2.3")

    assert V("1.2.3") > V("1.2")
    assert V("1.3") > V("1.2")
    assert V("1.2.3") > V("1.1.3")

def test_base_version_hashable():
    {BaseVersion("1.2.3")}


@pytest.mark.parametrize("arg, t, s", [
    ("main", "main", "main"),  # special case
    ("9.1", (9, 1), "9.1"),
    ("10.20.30", (10, 20), "10.20"),
])
def test_patch_version_init_ok(arg, t, s):
    v = PatchVersion(arg)
    assert v.t == t
    assert v.s == s

@pytest.mark.parametrize("arg, exc", [
    (None, TypeError),
    ("", ValueError),
    ("bad", ValueError),
    ("9", AssertionError),
])
def test_base_version_init_bad(arg, exc):
    with pytest.raises(exc):
        PatchVersion(arg)

