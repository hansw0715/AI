"""
지정된 액션들에서 mixamorig:Hips 본의 location 키프레임을 모두 제거 — root motion
제거 후 in-place 애니메이션으로 만든다. 캐릭터는 제자리에서 동작하고, 실제 이동은
런타임 코드가 player_pos 로 처리.

원본 위치 키프레임을 그대로 두면 사이클 끝에서 Hips Y 가 갑자기 0 으로 리셋되며,
런타임의 hips anchor 코드가 1 프레임 동안 actor 를 큰 거리만큼 점프시키게 됨 →
카메라가 머리 뒤로 빠지면서 자기 몸이 화면을 덮어 깜빡이는 현상.

사용:
    blender --background --python scripts/blender_strip_root.py -- \
        IN_BLEND action1 action2 ...

Blender 5.1 의 slotted action API 에 대응 (action.fcurves 직접 접근 X,
layers / strips / channelbag 경유).
"""
import sys

import bpy

argv = sys.argv
if '--' not in argv:
    raise SystemExit('args required after --')
argv = argv[argv.index('--') + 1:]
in_blend = argv[0]
target_anims = argv[1:]

print(f'IN_BLEND: {in_blend}', flush=True)
print(f'TARGETS : {target_anims}', flush=True)


def iter_action_fcurves(action):
    """Yield (container, fcurve) for any action format (legacy/slotted)."""
    if hasattr(action, 'fcurves'):
        try:
            for fcu in action.fcurves:
                yield action.fcurves, fcu
            return
        except Exception:
            pass
    # Blender 4.4+ slotted
    for layer in action.layers:
        for strip in layer.strips:
            for slot in action.slots:
                cbag = strip.channelbag(slot)
                if cbag is None:
                    continue
                for fcu in cbag.fcurves:
                    yield cbag.fcurves, fcu


bpy.ops.wm.open_mainfile(filepath=in_blend)

for anim_name in target_anims:
    action = bpy.data.actions.get(anim_name)
    if action is None:
        print(f'WARN: action {anim_name} not found', flush=True)
        continue
    targets = [
        (container, fcu)
        for container, fcu in iter_action_fcurves(action)
        if fcu.data_path == 'pose.bones["mixamorig:Hips"].location'
    ]
    for container, fcu in targets:
        container.remove(fcu)
    print(f'STRIPPED {anim_name}: removed {len(targets)} Hips.location fcurves', flush=True)

bpy.ops.wm.save_mainfile()
print('SAVED', flush=True)
