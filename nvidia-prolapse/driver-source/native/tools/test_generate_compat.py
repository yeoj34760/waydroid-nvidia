#!/usr/bin/env python3
"""Check incremental generation without the private historical probe archive."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

TOOLS = Path(__file__).resolve().parent
NATIVE = TOOLS.parent


def main():
    with tempfile.TemporaryDirectory(prefix='compat-generation-') as scratch:
        root = Path(scratch)
        native = root / 'nvidia-prolapse/driver-source/native'
        (native / 'tools').mkdir(parents=True)
        (native / 'src').mkdir()
        for path in ['tools/generate-compat.py', 'tools/compat-provenance.json', 'src/compat_data.rs']:
            shutil.copyfile(NATIVE / path, native / path)
        # An existing small exact profile exercises the round trip without GPU,
        # toolchain, network or archived measurement dependencies.
        probe = root / 'probe'
        probe.mkdir()
        text = 'NvNotification\tsize=16\n'
        for field, offset, width in [('timeStamp', 0, 8), ('info32', 8, 4), ('info16', 12, 2), ('status', 14, 2)]:
            text += f'NvNotification.{field}\toff={offset} len={width}\n'
        # Use a fresh tag so a changed exact profile can never replace an old one.
        for abi in ['m32', 'm64']:
            (probe / f'probe-{abi}.tsv').write_text(text)
        (probe / 'provenance.json').write_text(json.dumps({'tag': '999.1'}))
        cmd = [sys.executable, str(native / 'tools/generate-compat.py'), '--extend', '999.1', str(probe)]
        def run(ok):
            result = subprocess.run(cmd, capture_output=True, text=True)
            assert (result.returncode == 0) == ok, result.stdout + result.stderr
        run(True)
        outputs = [native / 'src/compat_data.rs', native / 'tools/compat-provenance.json']
        hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs]
        run(True)
        assert hashes == [hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs]
        assert '("620.70.06", &P21)' in outputs[0].read_text()
        (probe / 'probe-m32.tsv').write_text(text.replace('size=16', 'size=24'))
        run(False)
        assert hashes == [hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs]
        (probe / 'probe-m32.tsv').write_text(text)
        (probe / 'provenance.json').write_text(json.dumps({'tag': '999.2'}))
        run(False)
        assert hashes == [hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs]
    print('PASS incremental census preservation, idempotence, ABI mismatch and wrong-tag refusal')


if __name__ == '__main__':
    main()
