"""지정 액션에서 LeftHand 를 구간별 가중치(envelope)로 world -Z 하강 → bake.
그립 잡는 구간은 팔을 푹 내려 화면 밖으로(숨김), 기능 동작(탄창/슬라이드) 구간은
가중치 0 → 원본 키 그대로 유지(미변경). 경계는 smoothstep 으로 부드럽게.

LeftArm+LeftForeArm 2본 IK 로 손 위치만 내리고 손목/손가락 회전은 유지.
가중치 0 인 프레임은 re-key 하지 않아 원본 동작이 100% 보존됨.

ENVELOPE: (frame, weight) 제어점. weight 1=완전히 내림(숨김), 0=원본.
사용:
  blender --background --python scripts/blender_hide_lefthand_grip.py -- \
      IN_BLEND OUT_BLEND DROP_M ACTION
"""
import sys
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
in_blend, out_blend = argv[0], argv[1]
DROP = float(argv[2]) if len(argv) > 2 else 0.55      # 양수 = 내릴 거리(m)
ACTION = argv[3] if len(argv) > 3 else 'RifleReload'

# 그립=1(숨김), 기능 동작 구간=0(원본). 사이는 smoothstep 보간.
ENVELOPE = [(1, 1.0), (10, 1.0), (24, 0.0), (88, 0.0), (104, 1.0), (124, 1.0)]
PREFIX = 'mixamorig:'
LARM, LFORE, LHAND = PREFIX + 'LeftArm', PREFIX + 'LeftForeArm', PREFIX + 'LeftHand'


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def weight(f):
    pts = ENVELOPE
    if f <= pts[0][0]:
        return pts[0][1]
    if f >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        f0, w0 = pts[i]
        f1, w1 = pts[i + 1]
        if f0 <= f <= f1:
            if f1 == f0:
                return w1
            return w0 + (w1 - w0) * smoothstep((f - f0) / (f1 - f0))
    return 0.0


bpy.ops.wm.open_mainfile(filepath=in_blend)
scene = bpy.context.scene
arm = bpy.data.objects.get('YBot') or next(
    (o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)

act = bpy.data.actions.get(ACTION)
if act is None:
    raise SystemExit('action not found: ' + ACTION)
ad = arm.animation_data or arm.animation_data_create()
ad.action = act
if hasattr(ad, 'action_slot') and ad.action_slot is None and len(act.slots):
    ad.action_slot = act.slots[0]
for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'

f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])

# Pass 1: IK 로 LeftHand 를 -Z (DROP*weight) 한 LARM/LFORE matrix 수집 (w>0 만)
tgt = bpy.data.objects.new('LHHideTgt', None)
scene.collection.objects.link(tgt)
lfore = arm.pose.bones[LFORE]
ik = lfore.constraints.new('IK')
ik.target = tgt
ik.chain_count = 2
ik.use_tail = True

collected = {}
for f in range(f0, f1 + 1):
    w = weight(f)
    if w <= 0.001:
        continue                                  # 원본 보존 — re-key 안 함
    scene.frame_set(f)
    bpy.context.view_layer.update()
    hand_w = arm.matrix_world @ arm.pose.bones[LHAND].matrix.translation
    tgt.location = hand_w + Vector((0.0, 0.0, -DROP * w))
    bpy.context.view_layer.update()
    collected[f] = (arm.pose.bones[LARM].matrix.copy(),
                    arm.pose.bones[LFORE].matrix.copy())

lfore.constraints.remove(ik)
bpy.data.objects.remove(tgt, do_unlink=True)
bpy.context.view_layer.update()

# Pass 2: 수집한 matrix bake (부모 LARM 먼저)
for f, (mA, mF) in collected.items():
    scene.frame_set(f)
    pbA = arm.pose.bones[LARM]
    pbA.matrix = mA
    pbA.keyframe_insert('rotation_quaternion', frame=f)
    pbA.keyframe_insert('location', frame=f)
    bpy.context.view_layer.update()
    pbF = arm.pose.bones[LFORE]
    pbF.matrix = mF
    pbF.keyframe_insert('rotation_quaternion', frame=f)
    pbF.keyframe_insert('location', frame=f)
    bpy.context.view_layer.update()

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print('[hide-grip] %s: drop %.2fm, re-keyed %d frames (envelope %s)'
      % (ACTION, DROP, len(collected), ENVELOPE), flush=True)
