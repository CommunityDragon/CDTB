import os
import pytest
import cdragontoolbox
from cdragontoolbox.storage import (
    Version,
    Storage,
    PatchVersion,
)
from cdragontoolbox.__main__ import create_parser
import cdragontoolbox.__main__ as cdtb_main


@pytest.fixture
def runner(tmpdir):
    def _runner(input_args):
        if isinstance(input_args, str):
            input_args = input_args.split()
        parser = create_parser()
        args = parser.parse_args(input_args)

        if hasattr(args, 'storage'):
            storage = Storage(os.path.join(tmpdir, args.storage))
            storage.s = None  # prevent requests
            args.storage = storage

        getattr(cdtb_main, "command_%s" % args.command.replace('-', '_'))(parser, args)

    return _runner


@pytest.mark.parametrize("args, version, previous_version, overwrite", [
    ("7.24", '7.24', '7.23', True),
    ("7.24 --previous 7.22", '7.24', '7.22', True),
    ("7.24 --full", '7.24', None, True),
    ("7.24 -u", '7.24', '7.23', False),
])
def test_cli_export_versions(runner, monkeypatch, mocker, args, version, previous_version, overwrite):
    def patch_versions(storage, stored=False):
        for v in ('7.25', '7.24', '7.23', '7.22'):
            yield PatchVersion(storage, Version(v), [])
    monkeypatch.setattr(PatchVersion, 'versions', patch_versions)

    with mocker.patch('cdragontoolbox.__main__.PatchExporter'):
        mock = cdragontoolbox.__main__.PatchExporter
        mock.return_value = mock_instance = mocker.Mock()
        runner("export " + args)

        patch = PatchVersion(None, version, [])
        previous_patch = None if previous_version is None else PatchVersion(None, previous_version, [])
        mock.assert_called_once_with(os.path.join('export', '7.24'), patch, previous_patch)

        mock_instance.export.assert_called_once_with(overwrite=overwrite)
        mock_instance.write_links.assert_called_once_with()

