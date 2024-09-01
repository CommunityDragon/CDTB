import os
import pytest
from tools import count_calls, mock_response
from cdtb.rads import (
    RadsVersion,
    RadsStorage,
    RadsProject, RadsProjectVersion,
    RadsSolution, RadsSolutionVersion,
)

@pytest.fixture
def storage(tmpdir):
    storage = RadsStorage(os.path.join(tmpdir, 'RADS'))
    storage.s = None  # prevent requests
    return storage

RV = RadsVersion  # helper for readability


def test_project_operators(storage):
    s = storage
    assert RadsProject(s, 'name') < RadsProject(s, 'z')
    assert not RadsProject(s, 'name') < RadsProject(s, 'nam')
    assert RadsProject(s, 'abc') == RadsProject(s, 'abc')
    assert RadsProject(s, 'abc') != RadsProject(s, 'def')
    p_a = RadsProject(s, 'a')
    p_b = RadsProject(s, 'b')
    p_c = RadsProject(s, 'c')
    assert p_a < p_b < p_c
    assert not p_b < p_a
    assert sorted([p_c, p_a, p_b]) == [p_a, p_b, p_c]
    assert {RadsProject(s, 'name')}  # hashable

def test_project_version_operators(storage):
    s = storage
    assert RadsProjectVersion(RadsProject(s, 'abc'), RV('0.1.2.3')) == RadsProjectVersion(RadsProject(s, 'abc'), RV('0.1.2.3'))
    assert RadsProjectVersion(RadsProject(s, 'abc'), RV('0.1.2.3')) != RadsProjectVersion(RadsProject(s, 'abc'), RV('0.1.2.0'))
    assert RadsProjectVersion(RadsProject(s, 'abc'), RV('0.1.2.3')) != RadsProjectVersion(RadsProject(s, 'def'), RV('0.1.2.3'))
    assert RadsProjectVersion(RadsProject(s, 'abc'), RV('0.1.2.3')) != RadsProjectVersion(RadsProject(s, 'def'), RV('0.1.2.0'))
    p_a_1 = RadsProjectVersion(RadsProject(s, 'a'), RV('0.0.0.1'))
    p_a_0 = RadsProjectVersion(RadsProject(s, 'a'), RV('0.0.0.0'))
    p_b_1 = RadsProjectVersion(RadsProject(s, 'b'), RV('0.0.0.1'))
    p_b_0 = RadsProjectVersion(RadsProject(s, 'b'), RV('0.0.0.0'))
    assert p_a_1 < p_a_0 < p_b_1 < p_b_0
    assert not p_a_0 < p_a_1
    assert not p_b_0 < p_a_0
    assert sorted([p_b_1, p_a_0, p_b_0, p_a_1]) == [p_a_1, p_a_0, p_b_1, p_b_0]
    assert {RadsProjectVersion(RadsProject(s, 'name'), RV('0.1.2.3'))}  # hashable

def test_solution_operators(storage):
    s = storage
    assert RadsSolution(s, 'name') < RadsSolution(s, 'z')
    assert not RadsSolution(s, 'name') < RadsSolution(s, 'nam')
    assert RadsSolution(s, 'abc') == RadsSolution(s, 'abc')
    assert RadsSolution(s, 'abc') != RadsSolution(s, 'def')
    s_a = RadsSolution(s, 'a')
    s_b = RadsSolution(s, 'b')
    s_c = RadsSolution(s, 'c')
    assert s_a < s_b < s_c
    assert not s_b < s_a
    assert sorted([s_c, s_a, s_b]) == [s_a, s_b, s_c]
    assert {RadsSolution(s, 'name')}  # hashable

def test_solution_version_operators(storage):
    s = storage
    assert RadsSolutionVersion(RadsSolution(s, 'abc_sln'), RV('0.1.2.3')) == RadsSolutionVersion(RadsSolution(s, 'abc_sln'), RV('0.1.2.3'))
    assert RadsSolutionVersion(RadsSolution(s, 'abc_sln'), RV('0.1.2.3')) != RadsSolutionVersion(RadsSolution(s, 'abc_sln'), RV('0.1.2.0'))
    assert RadsSolutionVersion(RadsSolution(s, 'abc_sln'), RV('0.1.2.3')) != RadsSolutionVersion(RadsSolution(s, 'def_sln'), RV('0.1.2.3'))
    assert RadsSolutionVersion(RadsSolution(s, 'abc_sln'), RV('0.1.2.3')) != RadsSolutionVersion(RadsSolution(s, 'def_sln'), RV('0.1.2.0'))
    s_a_1 = RadsSolutionVersion(RadsSolution(s, 'a_sln'), RV('0.0.0.1'))
    s_a_0 = RadsSolutionVersion(RadsSolution(s, 'a_sln'), RV('0.0.0.0'))
    s_b_1 = RadsSolutionVersion(RadsSolution(s, 'b_sln'), RV('0.0.0.1'))
    s_b_0 = RadsSolutionVersion(RadsSolution(s, 'b_sln'), RV('0.0.0.0'))
    assert s_a_1 < s_a_0 < s_b_1 < s_b_0
    assert not s_a_0 < s_a_1
    assert not s_b_0 < s_a_0
    assert sorted([s_b_1, s_a_0, s_b_0, s_a_1]) == [s_a_1, s_a_0, s_b_1, s_b_0]
    assert {RadsSolutionVersion(RadsSolution(s, 'name_sln'), RV('0.1.2.3'))}  # hashable
    assert RadsProjectVersion(RadsProject(s, 'name_sln'), RV('0.1.2.3')) != RadsSolutionVersion(RadsSolution(s, 'name_sln'), RV('0.1.2.3'))

def test_mixing_project_solution(storage):
    s = storage
    assert RadsProject(s, 'name') != RadsSolution(s, 'name')
    assert RadsProjectVersion(RadsProject(s, 'name'), RV('0.1.2.3')) != RadsSolutionVersion(RadsSolution(s, 'name_sln'), RV('0.1.2.3'))


def test_project_get_versions(storage, monkeypatch):
    project = RadsProject(storage, 'name')

    @count_calls
    def request_get(path):
        assert path == "projects/name/releases/releaselisting"
        return mock_response(b'0.0.1.7\r\n0.0.1.6\r\n0.0.1.5\r\n')
    monkeypatch.setattr(storage, 'request_get', request_get)

    versions = [
        RadsProjectVersion(project, RV('0.0.1.7')),
        RadsProjectVersion(project, RV('0.0.1.6')),
        RadsProjectVersion(project, RV('0.0.1.5')),
    ]
    assert project.versions() == versions
    assert request_get.ncalls == 1

def test_solution_get_versions(storage, monkeypatch):
    solution = RadsSolution(storage, 'name_sln')

    @count_calls
    def request_get(path):
        assert path == "solutions/name_sln/releases/releaselisting"
        return mock_response(b'0.0.1.7\r\n0.0.1.6\r\n0.0.1.5\r\n')
    monkeypatch.setattr(storage, 'request_get', request_get)

    versions = [
        RadsSolutionVersion(solution, RV('0.0.1.7')),
        RadsSolutionVersion(solution, RV('0.0.1.6')),
        RadsSolutionVersion(solution, RV('0.0.1.5')),
    ]
    assert solution.versions() == versions
    assert request_get.ncalls == 1


def test_project_versions_package_files(storage, monkeypatch):
    project_version = RadsProjectVersion(RadsProject(storage, 'name'), RV('1.2.3.4'))

    @count_calls
    def request_get(path):
        assert path == "projects/name/releases/1.2.3.4/packages/files/packagemanifest"
        data = '\r\n'.join([
            'PKG1',
            '/some/path/to/file.json,BIN_0001,1234,56,0',
            '/another/path.compressed,BIN_0002,567,89,0',
            '/test3,BIN_0003,1300,100,0',
            '/test1,BIN_0003,0,100,0',
            '/test2,BIN_0003,100,1200,0',
            '',
        ])
        return mock_response(data.encode())
    monkeypatch.setattr(storage, 'request_get', request_get)

    exp_package_files = [
        ('some/path/to/file.json', 'BIN_0001', 1234, 56),
        ('another/path', 'BIN_0002', 567, 89),
        ('test3', 'BIN_0003', 1300, 100),
        ('test1', 'BIN_0003', 0, 100),
        ('test2', 'BIN_0003', 100, 1200),
    ]

    package_files = project_version._get_package_files()
    assert request_get.ncalls == 1
    assert os.path.isfile(storage.fspath("projects/name/releases/1.2.3.4/packagemanifest"))

    got_package_files = [(f.extract_path, f.package, f.offset, f.size) for f in package_files.values()]
    assert got_package_files == exp_package_files


def test_solution_storage_versions(storage):
    s_name = RadsSolution(storage, 'name_sln')
    s_other = RadsSolution(storage, 'other_sln')
    s_empty = RadsSolution(storage, 'empty_sln')

    os.makedirs(f"{storage.path}/solutions/name_sln/releases/0.0.1.0")
    os.makedirs(f"{storage.path}/solutions/name_sln/releases/0.0.1.1")
    os.makedirs(f"{storage.path}/solutions/other_sln/releases/0.0.1.2")

    assert s_name.versions(stored=True) == [RadsSolutionVersion(s_name, RV('0.0.1.1')), RadsSolutionVersion(s_name, RV('0.0.1.0'))]
    assert s_other.versions(stored=True) == [RadsSolutionVersion(s_other, RV('0.0.1.2'))]
    assert s_empty.versions(stored=True) == []

