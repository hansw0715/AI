"""
.glb 파일을 Blender 로 import → 모든 action / animation_data 제거 → 이름 패턴으로
지정된 오브젝트 제거 → .blend 저장.

panda3d-gltf 0.X 가 일부 권총 .glb 의 anim buffer 를 파싱하다 BufferError
("memoryview: underlying buffer is not C-contiguous") 를 던지는 경우의 우회용.
무기 anim (슬라이드 후퇴 같은) 은 어차피 게임에 안 쓰니까 통째로 제거하고,
결과 .blend 를 blend2bam 으로 .bam 변환해서 panda3d 가 직접 로드하게 한다.

Sketchfab 의 1인칭 weapon 모델은 자체 손/장갑 메쉬가 같이 들어있는 경우가 많은데
Y Bot 의 손과 겹쳐 보이므로 --remove NAME[,NAME...] 으로 제외 가능.

사용:
    blender --background --python scripts/blender_glb_to_blend.py -- \
        IN_GLB OUT_BLEND [--remove pattern1,pattern2,...]
"""
import sys

import bpy

argv = sys.argv
if '--' not in argv:
    raise SystemExit('args required after --')
argv = argv[argv.index('--') + 1:]
in_glb = argv[0]
out_blend = argv[1]
remove_patterns = []
keep_anims = False
i = 2
while i < len(argv):
    if argv[i] == '--remove' and i + 1 < len(argv):
        remove_patterns = [s.strip() for s in argv[i + 1].split(',') if s.strip()]
        i += 2
    elif argv[i] == '--keep-anims':
        keep_anims = True
        i += 1
    else:
        i += 1

print(f'IN     : {in_glb}', flush=True)
print(f'OUT    : {out_blend}', flush=True)
print(f'REMOVE : {remove_patterns}', flush=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=in_glb)

if not keep_anims:
    # 모든 anim action 제거
    for a in list(bpy.data.actions):
        a.use_fake_user = False
        bpy.data.actions.remove(a)

    # 오브젝트별 animation_data 도 제거 (빈 NLA 트랙이 남으면 export 시 또 문제)
    for o in bpy.data.objects:
        if o.animation_data:
            o.animation_data_clear()
else:
    # anim 유지하되 use_fake_user 켜서 export 시 보존되게.
    for a in bpy.data.actions:
        a.use_fake_user = True
    # armature 의 anim 들을 NLA 트랙으로 push (blend2bam 이 안정적으로 export).
    for o in bpy.data.objects:
        if o.type != 'ARMATURE' or not o.animation_data:
            continue
        # 이미 NLA 가 있으면 그대로 두고, 없으면 현재 action 을 NLA strip 으로.
        if not o.animation_data.nla_tracks and o.animation_data.action:
            track = o.animation_data.nla_tracks.new()
            track.strips.new(o.animation_data.action.name,
                             int(o.animation_data.action.frame_range[0]),
                             o.animation_data.action)
            o.animation_data.action = None
        # 모든 action 을 새 NLA 트랙으로 push (이름별 1개씩)
        existing = {t.name for t in o.animation_data.nla_tracks}
        for a in bpy.data.actions:
            if a.name in existing:
                continue
            track = o.animation_data.nla_tracks.new()
            track.name = a.name
            track.strips.new(a.name, int(a.frame_range[0]), a)

# 이름 패턴 매치되는 오브젝트 + 자손 제거 (자체 손/장갑 메쉬 등 빼낼 때 사용)
def matches(name, patterns):
    n = name.lower()
    return any(p.lower() in n for p in patterns)

if remove_patterns:
    to_remove = set()
    for o in bpy.data.objects:
        if matches(o.name, remove_patterns):
            to_remove.add(o)
            for c in o.children_recursive:
                to_remove.add(c)
    for o in to_remove:
        print(f'  remove: {o.name}', flush=True)
        bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print(f'SAVED: {out_blend}', flush=True)
print(f'OBJECTS_LEFT: {sorted(o.name for o in bpy.data.objects)}', flush=True)
print(f'ACTIONS_LEFT: {[a.name for a in bpy.data.actions]}', flush=True)
