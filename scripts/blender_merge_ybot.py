"""
Y Bot 베이스 FBX + 여러 anim FBX 를 단일 .blend 로 머지.

사용:
    blender --background --python scripts/blender_merge_ybot.py -- \
        BASE_FBX OUT_BLEND name1=path1 name2=path2 ...

각 anim FBX 에서 추출한 액션은 name 으로 rename 되고, main_arm 의 NLA 트랙에
strip 으로 푸시되어 blend2bam 이 안정적으로 export 할 수 있게 됨.

Mixamo 의 머지 .bam 은 각 액션의 Hips 시작 위치가 미묘하게 달라서 액션 전환 시
캐릭터 전체가 평행이동하는 문제가 있는데, 그건 blender_strip_root.py 로 추가
처리한다 (Hips location 키프레임 통째로 제거).
"""
import sys

import bpy

argv = sys.argv
if '--' not in argv:
    raise SystemExit('args required after --')
argv = argv[argv.index('--') + 1:]
base_fbx = argv[0]
out_blend = argv[1]
anim_pairs = []
for token in argv[2:]:
    if '=' not in token:
        raise SystemExit(f'bad pair: {token}')
    name, path = token.split('=', 1)
    anim_pairs.append((name, path))

print(f'BASE : {base_fbx}', flush=True)
print(f'OUT  : {out_blend}', flush=True)
for n, p in anim_pairs:
    print(f'ANIM : {n:14s} <- {p}', flush=True)

bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.import_scene.fbx(filepath=base_fbx)
main_arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
if main_arm is None:
    raise SystemExit('No armature in base FBX')
main_arm.name = 'YBot'
if main_arm.animation_data and main_arm.animation_data.action:
    main_arm.animation_data.action = None


def import_anim(fbx_path, new_name):
    pre = set(o.name for o in bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=fbx_path)
    new_objs = [o for o in bpy.data.objects if o.name not in pre]
    new_arm = next((o for o in new_objs if o.type == 'ARMATURE'), None)
    action = None
    if new_arm and new_arm.animation_data and new_arm.animation_data.action:
        action = new_arm.animation_data.action
        action.name = new_name
        action.use_fake_user = True
    # 임시 armature/mesh 는 제거. action 은 fake_user 로 보존됨.
    for o in new_objs:
        bpy.data.objects.remove(o, do_unlink=True)
    return action


actions = []
for name, path in anim_pairs:
    a = import_anim(path, name)
    if a is None:
        print(f'WARN: failed to extract action from {path}', flush=True)
    else:
        actions.append(a)

# main_arm 에 NLA 트랙으로 명시적으로 등록 → blend2bam 이 안정적으로 export.
if not main_arm.animation_data:
    main_arm.animation_data_create()
for track in list(main_arm.animation_data.nla_tracks):
    main_arm.animation_data.nla_tracks.remove(track)
for action in actions:
    track = main_arm.animation_data.nla_tracks.new()
    track.name = action.name
    start = int(action.frame_range[0])
    track.strips.new(action.name, start, action)

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print(f'SAVED: {out_blend}', flush=True)
print(f'ACTIONS: {[a.name for a in bpy.data.actions]}', flush=True)
