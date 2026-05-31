"""
지정된 본의 모든 action keyframe 의 rotation_quaternion 에 quat 오프셋을
post-multiply 로 박는다 — bone-local 좌표계에서 추가 회전 누적과 같음.

armature rest pose 를 안 건드리고 (= skin 변형 위험 없음) 모든 anim 에 동일한
보정을 거는 깔끔한 방법. 예: Ch15 의 RightArm 이 anim 적용 시 위로 너무 올라가면
local 회전 오프셋을 박아서 전체 anim 에 한꺼번에 적용.

post-multiply 의미: q_new = q_anim @ q_offset.
→ 본 local 축 기준으로 q_offset 이 적용됨. 본의 길이축 (Y) / 수직축 (X, Z) 은
arm 의 경우 보통 X = forward-back swing, Z = up-down swing.

axis 부호가 모호하면 한 번 적용해 보고 반대 방향이면 부호만 뒤집어서 재실행.

사용:
    blender --background --python scripts/blender_offset_bone.py -- \
        IN_BLEND BONE_NAME AX AY AZ DEG
"""
import sys
from math import radians

import bpy
from mathutils import Quaternion, Vector

argv = sys.argv
if '--' not in argv:
    raise SystemExit('args required after --')
argv = argv[argv.index('--') + 1:]
in_blend = argv[0]
bone_name = argv[1]
axis = Vector((float(argv[2]), float(argv[3]), float(argv[4])))
deg = float(argv[5])

q_offset = Quaternion(axis, radians(deg))
data_path = f'pose.bones["{bone_name}"].rotation_quaternion'

print(f'BLEND : {in_blend}', flush=True)
print(f'BONE  : {bone_name}', flush=True)
print(f'AXIS  : {axis.x:.2f}, {axis.y:.2f}, {axis.z:.2f}', flush=True)
print(f'DEG   : {deg}', flush=True)
print(f'QUAT  : ({q_offset.w:.4f}, {q_offset.x:.4f}, {q_offset.y:.4f}, {q_offset.z:.4f})',
      flush=True)


def collect_fcurve_quad(action, dp):
    """Return [w_fc, x_fc, y_fc, z_fc] fcurve set for the data_path, or None."""
    # legacy
    if hasattr(action, 'fcurves'):
        try:
            fcus = [action.fcurves.find(dp, index=i) for i in range(4)]
            if all(f is not None for f in fcus):
                return fcus
        except Exception:
            pass
    # slotted action (Blender 4.4+)
    for layer in action.layers:
        for strip in layer.strips:
            for slot in action.slots:
                cbag = strip.channelbag(slot)
                if cbag is None:
                    continue
                fcus = [cbag.fcurves.find(dp, index=i) for i in range(4)]
                if all(f is not None for f in fcus):
                    return fcus
    return None


bpy.ops.wm.open_mainfile(filepath=in_blend)

total_actions = 0
total_keys = 0
for action in bpy.data.actions:
    fcus = collect_fcurve_quad(action, data_path)
    if fcus is None:
        continue
    # 키프레임 인덱스가 4 fcurve 간 동일하다고 가정 (Mixamo anim 의 표준)
    n_keys = len(fcus[0].keyframe_points)
    if not all(len(fc.keyframe_points) == n_keys for fc in fcus):
        print(f'  WARN {action.name}: 4 fcurve 의 keyframe count 다름 → skip',
              flush=True)
        continue
    for i in range(n_keys):
        w = fcus[0].keyframe_points[i].co[1]
        x = fcus[1].keyframe_points[i].co[1]
        y = fcus[2].keyframe_points[i].co[1]
        z = fcus[3].keyframe_points[i].co[1]
        q = Quaternion((w, x, y, z))
        q_new = q @ q_offset
        fcus[0].keyframe_points[i].co[1] = q_new.w
        fcus[1].keyframe_points[i].co[1] = q_new.x
        fcus[2].keyframe_points[i].co[1] = q_new.y
        fcus[3].keyframe_points[i].co[1] = q_new.z
    # interp handles 도 같이 갱신 (안 그러면 interpolation 이 튐)
    for fc in fcus:
        fc.update()
    print(f'  {action.name}: {n_keys} keyframes modified', flush=True)
    total_actions += 1
    total_keys += n_keys

bpy.ops.wm.save_mainfile()
print(f'TOTAL: {total_actions} actions, {total_keys} keyframes', flush=True)
print('SAVED', flush=True)
