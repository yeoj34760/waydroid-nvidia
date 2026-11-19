#!/usr/bin/env python3
"""Exercise vendor checkout/stamps with local Git fixtures; no Android tree/network needed."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def run(*args, **kwargs):
    return subprocess.run(args, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=True, **kwargs).stdout.strip()


def git(path, *args):
    return run('git', '-C', str(path), '-c', 'user.name=Test',
               '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', *args)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / 'source'
        source.mkdir()
        git(source, 'init', '-q')
        (source / 'version').write_text('base')
        git(source, 'add', 'version')
        git(source, 'commit', '-qm', 'base')
        base = git(source, 'rev-parse', 'HEAD')
        (source / 'version').write_text('fork')
        git(source, 'commit', '-qam', 'fork')
        fork = git(source, 'rev-parse', 'HEAD')
        tree = root / 'tree'
        project = tree / 'hardware/waydroid'
        project.parent.mkdir(parents=True)
        run('git', 'clone', '-q', str(source), str(project))
        (tree / '.repo').mkdir()
        (tree / 'build').mkdir()
        (tree / 'build/envsetup.sh').write_text(
            'apply-waydroid-patches() { echo "All patches applied fine"; }\n')
        vendor = root / 'vendor-image'
        vendor.mkdir()
        for name in ('build-vendor.sh', 'tree-checkout.py'):
            shutil.copyfile(HERE / name, vendor / name)
        (vendor / 'pins.env').write_text('L20_MANIFEST=manifest.xml\n')
        (root / 'manifest.xml').write_text(
            f'<manifest><remote name="local" fetch="{root}"/>'
            '<default remote="local"/>'
            f'<project name="source" path="hardware/waydroid" revision="{base}"/></manifest>')
        (root / 'hwcomposer').mkdir()
        pins = root / 'hwcomposer/pins.env'

        def pin(sha):
            pins.write_text(f'HWC_UPSTREAM={source}\nHWC_SHA={sha}\n')

        def checkout(product):
            return run('bash', str(vendor / 'build-vendor.sh'), 'checkout',
                       env=dict(os.environ, LINEAGE_TREE=str(tree), VENDOR_PRODUCT=product))

        stamp = tree / '.ci-tree-stamp.tsv'
        pin(fork)
        checkout('prolapse')
        assert git(project, 'rev-parse', 'HEAD') == fork
        first_stamp = stamp.read_text()
        assert 'checkout skipped' in checkout('prolapse')
        checkout('stock')
        assert git(project, 'rev-parse', 'HEAD') == base
        checkout('prolapse')
        assert git(project, 'rev-parse', 'HEAD') == fork
        # A changed pin must invalidate a matching prolapse stamp.
        pin(base)
        checkout('prolapse')
        assert git(project, 'rev-parse', 'HEAD') == base
        assert stamp.read_text() != first_stamp
        # Fetch/check-out failure must not stamp an apparently successful tree.
        pin('0' * 40)
        try:
            checkout('prolapse')
        except subprocess.CalledProcessError as error:
            assert 'cannot fetch hwcomposer fork' in error.stdout
        else:
            raise AssertionError('missing fork commit was accepted')
        assert not stamp.exists()
    print('PASS: fork checkout, stock isolation, stamp reuse/invalidation and fetch failure')


if __name__ == '__main__':
    main()
