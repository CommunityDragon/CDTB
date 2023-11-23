import os
import argparse
import pytest
import cdragontoolbox
from cdragontoolbox.storage import (
    Storage,
    PatchVersion,
    Patch,
    PatchElement,
)
import cdragontoolbox.__main__ as cdtb_main
from cdragontoolbox.__main__ import (
    create_parser,
    parse_storage_args,
)


@pytest.fixture
def storage(tmpdir):
    storage = Storage(os.path.join(tmpdir, 'storage'), None)
    storage.s = None  # prevent requests
    return storage

@pytest.fixture
def runner(storage):
    def _runner(input_args):
        if isinstance(input_args, str):
            input_args = input_args.split()
        parser = create_parser()
        args = parser.parse_args(input_args)

        if hasattr(args, 'storage'):
            args.storage = storage

        getattr(cdtb_main, "command_%s" % args.command.replace('-', '_'))(parser, args)

    return _runner


@pytest.mark.parametrize("args, version, previous_version", [
    ("7.24", '7.24', '7.23'),
    ("7.24 --previous 7.22", '7.24', '7.22'),
    ("7.24 --full", '7.24', None),
])
def test_cli_export_versions(runner, storage, monkeypatch, mocker, args, version, previous_version):
    def fake_patch(version):
        return Patch._create([PatchElement('game', PatchVersion(version))])

    with mocker.patch('cdragontoolbox.__main__.CdragonRawPatchExporter'):
        mock = cdragontoolbox.__main__.CdragonRawPatchExporter
        mock.return_value = mock_instance = mocker.Mock()
        mock.storage = storage

        def storage_patches(stored=False):
            for v in ('7.25', '7.24', '7.23', '7.22'):
                yield PatchElement('game', PatchVersion(v))
        monkeypatch.setattr(storage, 'patch_elements', storage_patches)

        runner("export " + args)

        patch = fake_patch(version)
        previous_patch = None if previous_version is None else fake_patch(previous_version)
        mock.assert_called_once_with(os.path.join('export', '7.24'), patch, previous_patch, symlinks=False)

        mock_instance.process.assert_called_once_with(overwrite=True)

