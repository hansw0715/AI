"""
ybot 의 Alpha_Surface 메쉬에서 팔/손 부분 vertex 들만 따로 떼서
Alpha_Surface_Arms 라는 별도 메쉬로 분리. Valorant 스타일 1인칭 (몸·다리·머리·
어깨 hidden, 위팔부터 손까지만 visible) 을 위한 mesh split.

각 vertex 의 dominant 가중치 본이 ARM_VG_PREFIXES (LeftArm/Right- 계열, **Shoulder
제외**) 중 하나이면 arms 로, 나머지 (Shoulder / Neck / Head / Spine / Hips / Legs)는
body 에 둠. → 어깨가 body 에 들어가서 hidden, 카메라에 안 보임.

idempotent: 이미 *_Arms 가 있으면 base 로 join back 한 뒤 다시 split.

사용:
    blender --background --python scripts/blender_split_arms.py -- IN_BLEND
"""
import sys

import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
in_blend = argv[0]

ARM_VG_PREFIXES = (
    # Shoulder 는 빼서 body 쪽으로 → 어깨 ball 안 보임
    'mixamorig:LeftArm', 'mixamorig:LeftForeArm', 'mixamorig:LeftHand',
    'mixamorig:RightArm', 'mixamorig:RightForeArm', 'mixamorig:RightHand',
)


def is_arm_vg(name):
    return any(name.startswith(p) for p in ARM_VG_PREFIXES)


bpy.ops.wm.open_mainfile(filepath=in_blend)

# 0) Join back — 이전에 split 된 *_Arms 가 있으면 base 메쉬로 합쳐서 idempotent.
join_count = 0
for ob_name in [o.name for o in bpy.data.objects if o.type == 'MESH']:
    ob = bpy.data.objects.get(ob_name)
    if ob is None or not ob.name.endswith('_Arms'):
        continue
    base_name = ob.name[: -len('_Arms')]
    base = bpy.data.objects.get(base_name)
    if base is None:
        continue
    bpy.context.view_layer.objects.active = base
    for o in bpy.data.objects:
        o.select_set(False)
    base.select_set(True)
    ob.select_set(True)
    # join 후 ob 는 삭제되므로 이름은 미리 캡처
    print(f'[join-back] {ob_name} → {base_name}', flush=True)
    bpy.ops.object.join()
    join_count += 1
print(f'[join-back] total: {join_count}', flush=True)

# 1) Split — Alpha_Surface / Alpha_Joints 둘 다 처리
processed = 0
for ob_name in [o.name for o in bpy.data.objects if o.type == 'MESH']:
    ob = bpy.data.objects.get(ob_name)
    if ob is None or ob.name.endswith('_Arms'):
        continue
    print(f'Processing: {ob.name}', flush=True)

    bpy.context.view_layer.objects.active = ob
    for o in bpy.data.objects:
        o.select_set(False)
    ob.select_set(True)

    arm_vg_indices = {vg.index for vg in ob.vertex_groups if is_arm_vg(vg.name)}
    print(f'  arm vg count: {len(arm_vg_indices)}', flush=True)
    if not arm_vg_indices:
        continue

    bpy.ops.object.mode_set(mode='OBJECT')
    arm_count = 0
    for v in ob.data.vertices:
        v.select = False
    for v in ob.data.vertices:
        if not v.groups:
            continue
        max_g = max(v.groups, key=lambda g: g.weight)
        if max_g.group in arm_vg_indices:
            v.select = True
            arm_count += 1
    print(f'  arm verts: {arm_count} / {len(ob.data.vertices)}', flush=True)
    if arm_count == 0:
        continue

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='SELECTED')
    bpy.ops.object.mode_set(mode='OBJECT')

    new_name = None
    for o in bpy.data.objects:
        if o.name.startswith(ob.name) and o.name != ob.name and o.name not in (
                ob.name + '_Arms',):
            new_name = o.name
            break
    if new_name:
        target_name = ob.name + '_Arms'
        bpy.data.objects[new_name].name = target_name
        print(f'  → created: {target_name}', flush=True)
        processed += 1

print(f'TOTAL split: {processed} meshes', flush=True)
bpy.ops.wm.save_mainfile()
print('SAVED', flush=True)
