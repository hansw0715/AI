"""
.glb 파일의 JSON 헤더만 파싱해서 구조 요약 출력 — Blender 띄울 필요 없이 빠른 진단.

사용:
    python scripts/peek_glb.py PATH/TO/FILE.glb
"""
import json
import struct
import sys


def peek(path):
    with open(path, 'rb') as f:
        magic = f.read(4)
        if magic != b'glTF':
            raise SystemExit(f'not a glb: {path} (magic={magic!r})')
        struct.unpack('<I', f.read(4))[0]   # version
        struct.unpack('<I', f.read(4))[0]   # total length
        chunk_len = struct.unpack('<I', f.read(4))[0]
        f.read(4)                            # chunk_type 'JSON'
        data = json.loads(f.read(chunk_len))

    nodes = data.get('nodes', [])
    meshes = data.get('meshes', [])
    anims = data.get('animations', [])

    print(f'\n=== {path} ===')
    print(f'nodes   : {len(nodes)}')
    print(f'meshes  : {len(meshes)}')
    print(f'anims   : {len(anims)}')

    # 흥미로운 노드 이름 — 권총 부품 추정 키워드
    keys = ('mag', 'magazine', 'slide', 'trigger', 'barrel', 'hammer',
            'hand', 'arm', 'glove', 'finger')
    print('\nnodes (name + children)::')
    for i, n in enumerate(nodes):
        name = n.get('name', f'<node_{i}>')
        nc = len(n.get('children', []))
        flag = ''
        ln = name.lower()
        for k in keys:
            if k in ln:
                flag = f'  ← {k}'
                break
        has_mesh = 'mesh' in n
        print(f'  [{i:2d}] {name!r:40s}  children={nc}  mesh={has_mesh}{flag}')

    if anims:
        print('\nanimations:')
        for a in anims:
            name = a.get('name', '<unnamed>')
            chans = a.get('channels', [])
            targets = {nodes[c['target']['node']].get('name', '?')
                       for c in chans if 'target' in c and 'node' in c['target']}
            paths = {c['target']['path'] for c in chans
                     if 'target' in c and 'path' in c['target']}
            print(f'  - {name!r:30s}  channels={len(chans)}  '
                  f'paths={sorted(paths)}  targets={sorted(targets)}')
    else:
        print('\nanimations: 없음')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('usage: peek_glb.py PATH/TO/FILE.glb [more.glb ...]')
    for p in sys.argv[1:]:
        peek(p)
