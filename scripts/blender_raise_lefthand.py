"""
지정 액션에서 왼손(LeftHand)을 world +Z 로 RAISE(m) 만큼 올림 — 2본 IK 로 풀어 bake.
LeftArm+LeftForeArm 회전만 바꿔 손 위치를 올림. 손목/손가락 회전은 유지.
암맥 world transform 은 절대 건드리지 않음 (읽기 전용).

RAISE 음수면 내림 (예: -0.05 = 5cm 아래로).
FRAMES(선택) 콤마 구분 목록을 주면 그 프레임만 보정 (예: 0,72 = 그립 북엔드만).
나머지 프레임은 기존 키로 자연 보간됨.

사용:
  blender --background --python scripts/blender_raise_lefthand.py -- \
      IN_BLEND OUT_BLEND RAISE_M ACTION [FRAMES]
"""
import sys
import bpy
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:]
in_blend, out_blend = argv[0], argv[1]
RAISE = float(argv[2]) if len(argv) > 2 else 0.10
ACTION = argv[3] if len(argv) > 3 else 'RifleIdle'
ONLY_FRAMES = ([int(x) for x in argv[4].split(',') if x.strip() != '']
               if len(argv) > 4 and argv[4].strip() != '' else None)
PREFIX = 'mixamorig:'
LARM, LFORE, LHAND = PREFIX + 'LeftArm', PREFIX + 'LeftForeArm', PREFIX + 'LeftHand'

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
frames = ONLY_FRAMES if ONLY_FRAMES is not None else list(range(f0, f1 + 1))

# Pass 1: IK 로 LeftHand 를 +Z RAISE 한 LARM/LFORE visual matrix 수집
tgt = bpy.data.objects.new('LHRaiseTgt', None)
scene.collection.objects.link(tgt)
lfore = arm.pose.bones[LFORE]
ik = lfore.constraints.new('IK')
ik.target = tgt
ik.chain_count = 2
ik.use_tail = True

collected = {}
for f in frames:
    scene.frame_set(f)
    bpy.context.view_layer.update()
    hand_w = arm.matrix_world @ arm.pose.bones[LHAND].matrix.translation
    tgt.location = hand_w + Vector((0.0, 0.0, RAISE))
    bpy.context.view_layer.update()
    collected[f] = (arm.pose.bones[LARM].matrix.copy(),
                    arm.pose.bones[LFORE].matrix.copy())

lfore.constraints.remove(ik)
bpy.data.objects.remove(tgt, do_unlink=True)
bpy.context.view_layer.update()

# Pass 2: 수집한 matrix 를 액션에 bake (부모 LARM 먼저)
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
print('[raise] %s: LeftHand %+.3fm, frames %s' % (
    ACTION, RAISE, (ONLY_FRAMES if ONLY_FRAMES is not None else '%d-%d' % (f0, f1))),
    flush=True)
