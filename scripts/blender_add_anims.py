"""
기존 .blend 에 새 anim FBX 들만 추가 (Y Bot 베이스는 이미 .blend 안에 있다고 가정).

사용:
    blender --background --python scripts/blender_add_anims.py -- \
        IN_BLEND OUT_BLEND name1=path1 name2=path2 ...

blender_merge_ybot.py 와 동일한 import 규칙. 차이점은 빈 scene 으로 시작하지 않고
기존 .blend 를 열어서 거기 있는 YBot armature 의 NLA 에 anim 만 추가 등록한다.
같은 이름 action 이 이미 있으면 새 데이터로 교체하고 해당 NLA 트랙을 갈아끼움.
"""
import sys

import bpy

argv = sys.argv
if '--' not in argv:
    raise SystemExit('args required after --')
argv = argv[argv.index('--') + 1:]
in_blend = argv[0]
out_blend = argv[1]
anim_pairs = []
for token in argv[2:]:
    if '=' not in token:
        raise SystemExit(f'bad pair: {token}')
    name, path = token.split('=', 1)
    anim_pairs.append((name, path))

print(f'IN  : {in_blend}', flush=True)
print(f'OUT : {out_blend}', flush=True)
for n, p in anim_pairs:
    print(f'ADD : {n:14s} <- {p}', flush=True)

bpy.ops.wm.open_mainfile(filepath=in_blend)

main_arm = bpy.data.objects.get('YBot')
if main_arm is None:
    main_arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
if main_arm is None:
    raise SystemExit('No armature in input blend')
print(f'BASE ARMATURE: {main_arm.name}', flush=True)


def import_anim(fbx_path, new_name):
    # 기존에 동일 이름 action 이 있으면 제거 — 새로 import 한 action 이 이름 충돌
    # 시 'Idle.001' 로 떨어지는 걸 방지.
    old = bpy.data.actions.get(new_name)
    if old is not None:
        old.use_fake_user = False
        bpy.data.actions.remove(old)
    pre = set(o.name for o in bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=fbx_path)
    new_objs = [o for o in bpy.data.objects if o.name not in pre]
    new_arm = next((o for o in new_objs if o.type == 'ARMATURE'), None)
    action = None
    if new_arm and new_arm.animation_data and new_arm.animation_data.action:
        action = new_arm.animation_data.action
        action.name = new_name
        action.use_fake_user = True
    for o in new_objs:
        bpy.data.objects.remove(o, do_unlink=True)
    return action


added = []
for name, path in anim_pairs:
    a = import_anim(path, name)
    if a is None:
        print(f'WARN: failed to extract action from {path}', flush=True)
    else:
        added.append(a)

if not main_arm.animation_data:
    main_arm.animation_data_create()

# 같은 이름의 기존 NLA 트랙은 제거 후 새로 추가 — 이전 strip 이 사라진 action 을
# 가리키지 않게.
added_names = {a.name for a in added}
for t in list(main_arm.animation_data.nla_tracks):
    if t.name in added_names:
        main_arm.animation_data.nla_tracks.remove(t)

for action in added:
    track = main_arm.animation_data.nla_tracks.new()
    track.name = action.name
    start = int(action.frame_range[0])
    track.strips.new(action.name, start, action)

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print(f'SAVED: {out_blend}', flush=True)
print(f'ACTIONS: {sorted(a.name for a in bpy.data.actions)}', flush=True)
