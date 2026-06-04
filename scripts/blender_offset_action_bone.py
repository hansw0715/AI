"""
지정 액션의 모든 프레임에서 한 본에 로컬 회전 오프셋을 누적 (FK).
왼손 그립 높이 조정 등에 사용. 암맥 world transform 은 안 건드림.

사용:
  blender --background --python scripts/blender_offset_action_bone.py -- \
      IN_BLEND OUT_BLEND ACTION BONE ax ay az deg [BONE2 ax ay az deg ...]
"""
import sys
from math import radians
import bpy
from mathutils import Quaternion, Vector

argv = sys.argv[sys.argv.index('--') + 1:]
in_blend, out_blend, ACTION = argv[0], argv[1], argv[2]
rest = argv[3:]
# 5개씩: bone, ax, ay, az, deg
offsets = []
for i in range(0, len(rest), 5):
    b = rest[i]
    ax, ay, az, deg = map(float, rest[i + 1:i + 5])
    offsets.append((b, (ax, ay, az), deg))

PREFIX = 'mixamorig:'
bpy.ops.wm.open_mainfile(filepath=in_blend)
scene = bpy.context.scene
arm = bpy.data.objects.get('YBot') or next(
    (o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
bpy.context.view_layer.objects.active = arm
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
for f in range(f0, f1 + 1):
    scene.frame_set(f)
    bpy.context.view_layer.update()
    cur = {}
    for suffix, axis, deg in offsets:
        pb = arm.pose.bones.get(PREFIX + suffix)
        if pb is None:
            continue
        cur[suffix] = (pb, pb.rotation_quaternion.copy() @
                       Quaternion(Vector(axis), radians(deg)))
    for suffix, (pb, q) in cur.items():
        pb.rotation_quaternion = q
        pb.keyframe_insert('rotation_quaternion', frame=f)

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print('[offset] %s applied on %s frames %d-%d' %
      (ACTION, [o[0] for o in offsets], f0, f1), flush=True)
