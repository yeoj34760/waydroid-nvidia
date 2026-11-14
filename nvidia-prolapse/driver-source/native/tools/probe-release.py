#!/usr/bin/env python3
"""Measure one exact OGKM release, including DRM/NVKMS, without running GPU code.

Usage: probe-release.py OGKM_CHECKOUT TAG OUTPUT_DIRECTORY
Then: generate-compat.py --extend TAG OUTPUT_DIRECTORY
Requires cc, objcopy, Linux UAPI and libdrm headers (including 32-bit headers).
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

TOOLS = Path(__file__).resolve().parent
INCLUDES = [
    'src/common/sdk/nvidia/inc', 'src/common/inc',
    'src/nvidia/arch/nvalloc/unix/include', 'kernel-open/common/inc',
    'src/nvidia-modeset/kapi/interface', 'src/nvidia-modeset/interface',
    'src/common/unix/common/inc',
]


def main():
    checkout, tag, output = sys.argv[1:]
    repo, out = Path(checkout).resolve(), Path(output).resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    commit = git('rev-parse', tag + '^{commit}')
    if git('rev-parse', 'HEAD') != commit or git('status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('checkout must be clean and at the exact requested tag')
    source = TOOLS / 'probe-release.c'
    keys = []
    for line in source.read_text().splitlines():
        if line.startswith('S('):
            keys.append((line[2:-2].removeprefix('struct '), 'size'))
        elif line.startswith('F('):
            typ, field = line[2:-2].split(', ')
            keys.extend([(typ.removeprefix('struct ') + '.' + field, 'off'), ('', 'len')])
        elif line.startswith('K('):
            keys.append((line[2:].split(',', 1)[0], 'constant'))
    out.mkdir(parents=True, exist_ok=True)
    measurements, headers, commands = {}, {}, []
    with tempfile.TemporaryDirectory(prefix='rm-release-') as scratch:
        tmp = Path(scratch)
        (tmp / 'drm').symlink_to('/usr/include/libdrm', target_is_directory=True)
        for abi in ['m32', 'm64']:
            obj, binary, deps = tmp / (abi + '.o'), tmp / (abi + '.bin'), tmp / (abi + '.d')
            cmd = ['cc', '-' + abi, '-std=c11', '-Wall', '-Werror', '-ffreestanding',
                   '-I' + str(repo), '-I' + str(tmp),
                   *['-I' + str(repo / p) for p in INCLUDES],
                   '-MD', '-MF', str(deps), '-c', str(source), '-o', str(obj)]
            subprocess.run(cmd, check=True)
            subprocess.run(['objcopy', '--dump-section', '.abi=' + str(binary), str(obj)], check=True)
            values = struct.unpack('<' + 'Q' * len(keys), binary.read_bytes())
            measurements[abi] = values
            lines = []
            for (name, kind), value in zip(keys, values):
                if kind == 'len':
                    lines[-1] += ' len=' + str(value)
                elif kind == 'constant':
                    lines.append(name + '\t' + hex(value))
                else:
                    lines.append(name + '\t' + kind + '=' + str(value))
            (out / ('probe-' + abi + '.tsv')).write_text('\n'.join(lines) + '\n')
            for path in deps.read_text().replace('\\\n', '').split()[1:]:
                header = Path(path).resolve()
                if header.is_relative_to(repo):
                    headers[str(header.relative_to(repo))] = hashlib.sha256(header.read_bytes()).hexdigest()
            commands.append([a.replace(str(tmp), '$TMP').replace(str(repo), '$OGKM')
                             .replace(str(TOOLS), '$TOOLS') for a in cmd])
    if measurements['m32'] != measurements['m64']:
        raise SystemExit('m32/m64 wire mismatch; do not register this release')
    proof = {'tag': tag, 'commit': commit, 'headers': headers, 'commands': commands,
             'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'compiler': subprocess.check_output(['cc', '--version'], text=True).splitlines()[0],
             'values_per_abi': len(keys), 'method': 'Exact public headers; m32/m64 ELF data, no GPU execution'}
    (out / 'provenance.json').write_text(json.dumps(proof, indent=1) + '\n')
    print(f'PASS {tag}: {len(keys)} values agree across m32/m64; {len(headers)} public headers')


if __name__ == '__main__':
    main()
