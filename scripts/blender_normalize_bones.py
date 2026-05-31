"""
mixamorig9:* / mixamorig10:* 같은 변종 prefix 를 mixamorig:* 로 정규화.

Mixamo 캐릭터를 같은 계정에서 여러 번 업로드하면 prefix 에 숫자가 붙는다
(mixamorig:, mixamorig9:, mixamorig10:...). anim FBX 들은 그냥 mixamorig: 를
쓰기 때문에 armature 와 mismatch → action 이 본을 못 찾고 빈 NLA 가 됨.

이 스크립트는 armature 의 bone 이름과 mesh 의 vertex group 이름을 동시에
정규화해서 anim 들이 정상 바인딩되게 한다. 멀티 prefix 도 지원 — endswith
matching 으로 표준 mixamorig: 본 이름과 같은 suffix 를 가진 본은 모두 변환.

사용:
    blender --background --python scripts/blender_normalize_bones.py -- IN_BLEND
"""
import re
import sys

import bpy

argv = sys.argv
if '--' not in argv:
    raise SystemExit('args required after --')
argv = argv[argv.index('--') + 1:]
in_blend = argv[0]

bpy.ops.wm.open_mainfile(filepath=in_blend)

# mixamorigN:Name → mixamorig:Name 패턴
PAT = re.compile(r'^mixamorig\d+:')


def normalize(name):
    return PAT.sub('mixamorig:', name)


arm = bpy.data.objects.get('YBot') or next(
    (o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
if arm is None:
    raise SystemExit('No armature found')

# 1) Edit mode 에서 bone 이름 변경 (pose / vertex group 자동 추종)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
renamed_bones = 0
for ebone in arm.data.edit_bones:
    new = normalize(ebone.name)
    if new != ebone.name:
        ebone.name = new
        renamed_bones += 1
bpy.ops.object.mode_set(mode='OBJECT')
print(f'[normalize] bones renamed: {renamed_bones}', flush=True)

# 2) Mesh vertex group 도 정규화 (Blender 가 일부 케이스에서 자동 추종 안 함)
for ob in bpy.data.objects:
    if ob.type != 'MESH':
        continue
    if not any(m.type == 'ARMATURE' and m.object == arm for m in ob.modifiers):
        continue
    renamed_vg = 0
    for vg in ob.vertex_groups:
        new = normalize(vg.name)
        if new != vg.name:
            vg.name = new
            renamed_vg += 1
    print(f'[normalize] {ob.name}: vertex groups renamed: {renamed_vg}', flush=True)

bpy.ops.wm.save_mainfile()
print('[normalize] SAVED', flush=True)
