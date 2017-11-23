import os
import pytest
from types import SimpleNamespace
from tools import *
from downloader import Version, Project, ProjectVersion, Solution, SolutionVersion, PatchVersion
from downloader import parse_component

V = Version  # for readibility


@pytest.mark.parametrize("arg,str_value", [
    ('name=0.1.2.3', 'p:name=0.1.2.3'),
    ('name_sln=0.1.2.3', 's:name_sln=0.1.2.3'),
    ('p:name=0.1.2.3', 'p:name=0.1.2.3'),
    ('s:name=0.1.2.3', 's:name=0.1.2.3'),
    ('name', 'p:name'),
    ('name_sln', 's:name_sln'),
    ('name=', 'p:name=1.2.0.0'),
    ('name_sln=', 's:name_sln=1.2.0.0'),
    # examples from --help
    ('league_client_fr_fr=0.0.0.78', 'p:league_client_fr_fr=0.0.0.78'),
    ('lol_game_client_sln', 's:lol_game_client_sln'),
    ('s:league_client_sln=0.0.1.195', 's:league_client_sln=0.0.1.195'),
    ('league_client=', 'p:league_client=1.2.0.0'),
])
def test_parse_component(storage, monkeypatch, arg, str_value):
    def request_get(path):
        return mock_response(b'1.2.0.0\r\n1.0.0.0\r\n')
    monkeypatch.setattr(storage, 'request_get', request_get)
    component = parse_component(storage, arg)
    assert str(component) == str_value


@pytest.mark.parametrize("arg", [
    'x:name',
    ':name',
    'name=.0.0.1',
    'name=0.0.0.',
    'name==',
    'name.0=0.0.0.1',
    'name ',
    ' name',
    'name= ',
    'name=0.0.0.1 ',
])
def test_parse_component_error(arg):
    with pytest.raises(ValueError):
        parse_component(None, arg)


def test_project_operators(storage):
    s = storage
    assert Project(s, 'name') < Project(s, 'z')
    assert not Project(s, 'name') < Project(s, 'nam')
    assert Project(s, 'abc') == Project(s, 'abc')
    assert Project(s, 'abc') != Project(s, 'def')
    p_a = Project(s, 'a')
    p_b = Project(s, 'b')
    p_c = Project(s, 'c')
    assert p_a < p_b < p_c
    assert not p_b < p_a
    assert sorted([p_c, p_a, p_b]) == [p_a, p_b, p_c]
    assert {Project(s, 'name')}  # hashable

def test_project_version_operators(storage):
    s = storage
    assert ProjectVersion(Project(s, 'abc'), V('0.1.2.3')) == ProjectVersion(Project(s, 'abc'), V('0.1.2.3'))
    assert ProjectVersion(Project(s, 'abc'), V('0.1.2.3')) != ProjectVersion(Project(s, 'abc'), V('0.1.2.0'))
    assert ProjectVersion(Project(s, 'abc'), V('0.1.2.3')) != ProjectVersion(Project(s, 'def'), V('0.1.2.3'))
    assert ProjectVersion(Project(s, 'abc'), V('0.1.2.3')) != ProjectVersion(Project(s, 'def'), V('0.1.2.0'))
    p_a_1 = ProjectVersion(Project(s, 'a'), V('0.0.0.1'))
    p_a_0 = ProjectVersion(Project(s, 'a'), V('0.0.0.0'))
    p_b_1 = ProjectVersion(Project(s, 'b'), V('0.0.0.1'))
    p_b_0 = ProjectVersion(Project(s, 'b'), V('0.0.0.0'))
    assert p_a_1 < p_a_0 < p_b_1 < p_b_0
    assert not p_a_0 < p_a_1
    assert not p_b_0 < p_a_0
    assert sorted([p_b_1, p_a_0, p_b_0, p_a_1]) == [p_a_1, p_a_0, p_b_1, p_b_0]
    assert {ProjectVersion(Project(s, 'name'), V('0.1.2.3'))}  # hashable

def test_solution_operators(storage):
    s = storage
    assert Solution(s, 'name') < Solution(s, 'z')
    assert not Solution(s, 'name') < Solution(s, 'nam')
    assert Solution(s, 'abc') == Solution(s, 'abc')
    assert Solution(s, 'abc') != Solution(s, 'def')
    s_a = Solution(s, 'a')
    s_b = Solution(s, 'b')
    s_c = Solution(s, 'c')
    assert s_a < s_b < s_c
    assert not s_b < s_a
    assert sorted([s_c, s_a, s_b]) == [s_a, s_b, s_c]
    assert {Solution(s, 'name')}  # hashable

def test_solution_version_operators(storage):
    s = storage
    assert SolutionVersion(Solution(s, 'abc_sln'), V('0.1.2.3')) == SolutionVersion(Solution(s, 'abc_sln'), V('0.1.2.3'))
    assert SolutionVersion(Solution(s, 'abc_sln'), V('0.1.2.3')) != SolutionVersion(Solution(s, 'abc_sln'), V('0.1.2.0'))
    assert SolutionVersion(Solution(s, 'abc_sln'), V('0.1.2.3')) != SolutionVersion(Solution(s, 'def_sln'), V('0.1.2.3'))
    assert SolutionVersion(Solution(s, 'abc_sln'), V('0.1.2.3')) != SolutionVersion(Solution(s, 'def_sln'), V('0.1.2.0'))
    s_a_1 = SolutionVersion(Solution(s, 'a_sln'), V('0.0.0.1'))
    s_a_0 = SolutionVersion(Solution(s, 'a_sln'), V('0.0.0.0'))
    s_b_1 = SolutionVersion(Solution(s, 'b_sln'), V('0.0.0.1'))
    s_b_0 = SolutionVersion(Solution(s, 'b_sln'), V('0.0.0.0'))
    assert s_a_1 < s_a_0 < s_b_1 < s_b_0
    assert not s_a_0 < s_a_1
    assert not s_b_0 < s_a_0
    assert sorted([s_b_1, s_a_0, s_b_0, s_a_1]) == [s_a_1, s_a_0, s_b_1, s_b_0]
    assert {SolutionVersion(Solution(s, 'name_sln'), V('0.1.2.3'))}  # hashable
    assert ProjectVersion(Project(s, 'name_sln'), V('0.1.2.3')) != SolutionVersion(Solution(s, 'name_sln'), V('0.1.2.3'))

def test_mixing_project_solution(storage):
    s = storage
    assert Project(s, 'name') != Solution(s, 'name')
    assert ProjectVersion(Project(s, 'name'), V('0.1.2.3')) != SolutionVersion(Solution(s, 'name_sln'), V('0.1.2.3'))


def test_project_get_versions(storage, monkeypatch):
    project = Project(storage, 'name')

    @count_calls
    def request_get(path):
        assert path == f"projects/name/releases/releaselisting"
        return mock_response(b'0.0.1.7\r\n0.0.1.6\r\n0.0.1.5\r\n')
    monkeypatch.setattr(storage, 'request_get', request_get)

    versions = [
        ProjectVersion(project, V('0.0.1.7')),
        ProjectVersion(project, V('0.0.1.6')),
        ProjectVersion(project, V('0.0.1.5')),
    ]
    assert project.versions() == versions
    assert request_get.ncalls == 1

def test_solution_get_versions(storage, monkeypatch):
    solution = Solution(storage, 'name_sln')

    @count_calls
    def request_get(path):
        assert path == "solutions/name_sln/releases/releaselisting"
        return mock_response(b'0.0.1.7\r\n0.0.1.6\r\n0.0.1.5\r\n')
    monkeypatch.setattr(storage, 'request_get', request_get)

    versions = [
        SolutionVersion(solution, V('0.0.1.7')),
        SolutionVersion(solution, V('0.0.1.6')),
        SolutionVersion(solution, V('0.0.1.5')),
    ]
    assert solution.versions() == versions
    assert request_get.ncalls == 1


def test_project_versions_packages(storage, monkeypatch):
    project_version = ProjectVersion(Project(storage, 'name'), V('1.2.3.4'))

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

    exp_packages = [
        ('projects/name/releases/1.2.3.4/packages/files/BIN_0001', [
            ('some/path/to/file.json', 1234, 56),
        ]),
        ('projects/name/releases/1.2.3.4/packages/files/BIN_0002', [
            ('another/path.compressed', 567, 89),
        ]),
        ('projects/name/releases/1.2.3.4/packages/files/BIN_0003', [
            ('test3', 1300, 100),
            ('test1', 0, 100),
            ('test2', 100, 1200),
        ]),
    ]

    packages = project_version.packages()
    assert request_get.ncalls == 1
    assert os.path.isfile(storage.fspath("projects/name/releases/1.2.3.4/packagemanifest"))

    got_packages = [(pkg.path, [(f.path, f.offset, f.size) for f in pkg.files]) for pkg in packages]
    assert got_packages == exp_packages
    for pkg in packages:
        assert pkg.storage is storage
        assert all(f.package is pkg for f in pkg.files)


def test_solution_storage_versions(storage):
    s_name = Solution(storage, 'name_sln')
    s_other = Solution(storage, 'other_sln')
    s_empty = Solution(storage, 'empty_sln')

    os.makedirs(f"{storage.path}/solutions/name_sln/releases/0.0.1.0")
    os.makedirs(f"{storage.path}/solutions/name_sln/releases/0.0.1.1")
    os.makedirs(f"{storage.path}/solutions/other_sln/releases/0.0.1.2")

    assert s_name.versions(stored=True) == [SolutionVersion(s_name, V('0.0.1.1')), SolutionVersion(s_name, V('0.0.1.0'))]
    assert s_other.versions(stored=True) == [SolutionVersion(s_other, V('0.0.1.2'))]
    assert s_empty.versions(stored=True) == []


@pytest.mark.parametrize("solution_versions,patch_versions", [
    ({
        's:league_client_sln=0.0.0.6': '1.14',
        's:league_client_sln=0.0.0.5': None,
        's:league_client_sln=0.0.0.4': '1.13',
        's:league_client_sln=0.0.0.3': '1.11',
        's:league_client_sln=0.0.0.2': '1.11',
        's:league_client_sln=0.0.0.1': '1.10',
        's:lol_game_client_sln=0.0.0.7': '1.14',
        's:lol_game_client_sln=0.0.0.6': '1.12',
        's:lol_game_client_sln=0.0.0.5': '1.11',
        's:lol_game_client_sln=0.0.0.4': '1.10',
        's:lol_game_client_sln=0.0.0.3': '1.10',
        's:lol_game_client_sln=0.0.0.2': '1.9',
        's:lol_game_client_sln=0.0.0.1': None,
    }, [
        ('1.14', ['s:league_client_sln=0.0.0.6', 's:lol_game_client_sln=0.0.0.7']),
        ('1.13', ['s:league_client_sln=0.0.0.4']),
        ('1.12', ['s:lol_game_client_sln=0.0.0.6']),
        ('1.11', ['s:league_client_sln=0.0.0.3', 's:league_client_sln=0.0.0.2', 's:lol_game_client_sln=0.0.0.5']),
        ('1.10', ['s:league_client_sln=0.0.0.1', 's:lol_game_client_sln=0.0.0.4', 's:lol_game_client_sln=0.0.0.3']),
        ('1.9', ['s:lol_game_client_sln=0.0.0.2']),
    ]),
])
def test_patch_version_versions(storage, monkeypatch, solution_versions, patch_versions):
    def patch_version(self):
        return solution_versions[str(self)]
    monkeypatch.setattr(SolutionVersion, 'patch_version', patch_version)

    for sv in solution_versions:
        sv = parse_component(storage, sv)
        os.makedirs(f"{storage.path}/{sv.path}", exist_ok=True)

    result = list(PatchVersion.versions(storage, stored=True))
    result = [(str(p.version), [str(sv) for sv in p.solutions()]) for p in result]
    assert result == patch_versions

