import os
import argparse
import pytest
import cdragontoolbox
from cdragontoolbox.storage import (
    Version,
    Storage,
    PatchVersion,
)
import cdragontoolbox.__main__ as cdtb_main
from cdragontoolbox.__main__ import (
    create_parser,
    parse_storage_args,
)


@pytest.fixture
def runner(tmpdir):
    def _runner(input_args):
        if isinstance(input_args, str):
            input_args = input_args.split()
        parser = create_parser()
        args = parser.parse_args(input_args)

        if hasattr(args, 'storage'):
            storage = Storage(os.path.join(tmpdir, "storage"))
            storage.s = None  # prevent requests
            args.storage = storage

        getattr(cdtb_main, "command_%s" % args.command.replace('-', '_'))(parser, args)

    return _runner


@pytest.mark.parametrize("args, version, previous_version", [
    ("7.24", '7.24', '7.23'),
    ("7.24 --previous 7.22", '7.24', '7.22'),
    ("7.24 --full", '7.24', None),
])
def test_cli_export_versions(runner, monkeypatch, mocker, args, version, previous_version):
    def patch_versions(storage, stored=False):
        for v in ('7.25', '7.24', '7.23', '7.22'):
            yield PatchVersion._create(storage, Version(v), [])
    monkeypatch.setattr(PatchVersion, 'versions', patch_versions)

    with mocker.patch('cdragontoolbox.__main__.PatchExporter'):
        mock = cdragontoolbox.__main__.PatchExporter
        mock.return_value = mock_instance = mocker.Mock()
        runner("export " + args)

        patch = PatchVersion._create(None, version, [])
        previous_patch = None if previous_version is None else PatchVersion._create(None, previous_version, [])
        mock.assert_called_once_with(os.path.join('export', '7.24'), patch, previous_patch)

        mock_instance.export.assert_called_once_with()
        mock_instance.write_links.assert_called_once_with()

@pytest.mark.parametrize("arg_storage, arg_cdn, env_storage, env_cdn, path, url", [
    # basic cases
    (None, None, None, None, 'RADS', Storage.URL_DEFAULT),
    ('other', None, None, None, 'other', Storage.URL_DEFAULT),
    (None, 'pbe', None, None, 'RADS.pbe', Storage.URL_PBE),
    # environment variables, no --cdn
    (None, None, 'envdir', None, 'envdir', Storage.URL_DEFAULT),
    ('other', None, 'envdir', None, 'other', Storage.URL_DEFAULT),
    (None, None, 'envdir', 'pbe', 'envdir', Storage.URL_PBE),
    # --cdn and --storage
    ('other', 'default', None, None, 'other', Storage.URL_DEFAULT),
    ('other', 'pbe', None, None, 'other', Storage.URL_PBE),
    ('other', 'kr', None, None, 'other', Storage.URL_KR),
    # mixing all values
    (None, 'default', None, None, 'RADS', Storage.URL_DEFAULT),
    (None, 'pbe', None, 'pbe', 'RADS.pbe', Storage.URL_PBE),
    (None, 'pbe', 'subdir', 'pbe', 'subdir', Storage.URL_PBE),
    ('other', 'kr', 'subdir', 'pbe', 'other', Storage.URL_KR),
    # --cdn without --storage
    (None, 'kr', None, 'default', 'RADS.kr', Storage.URL_KR),
    (None, 'kr', 'envdir', 'default', None, None),
])
def test_parse_storage_args(monkeypatch, mocker, arg_storage, arg_cdn, env_storage, env_cdn, path, url):
    if env_storage is None:
        monkeypatch.delenv('CDRAGONTOOLBOX_STORAGE', raising=False)
    else:
        monkeypatch.setenv('CDRAGONTOOLBOX_STORAGE', env_storage)
    if env_cdn is None:
        monkeypatch.delenv('CDRAGONTOOLBOX_CDN', raising=False)
    else:
        monkeypatch.setenv('CDRAGONTOOLBOX_CDN', env_cdn)

    parser = mocker.Mock()
    parser.error.side_effect = Exception("parser.error()")
    args = argparse.Namespace(storage=arg_storage, cdn=arg_cdn)

    if path is None:
        with pytest.raises(Exception, message="parser.error()"):
            parse_storage_args(parser, args)
    else:
        storage = parse_storage_args(parser, args)
        assert storage.path == path
        assert storage.url == url

