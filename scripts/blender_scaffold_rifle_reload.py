"""
scene.blend 에 'RifleReload' 액션을 스캐폴딩 (헤드리스 Blender) — 소총 재장전.

시퀀스 (왼손 위주, 오른손은 그립 유지):
  그립(RifleIdle) → 왼손 탄창으로 → 빈 탄창 빼기(아래) → 새 탄창 집기 → 탄창 삽입(위)
  → 왼손 노리쇠(장전손잡이)로 → 뒤로 당김 → 앞으로 밀기 → 왼손 그립 복귀

- 북엔드(f0 / END)는 RifleIdle 그립 포즈 → 소총 locomotion 과 이음새 없음.
- 각 페이즈는 명시한 본만 그립 포즈에 로컬 추가 회전, 나머지는 그립 유지.
- FK only (IK 없음). 방향/크기 어색하면 PHASES 의 axis/deg 만 튜닝 후 재실행.

사용:
  blender --background --python scripts/blender_scaffold_rifle_reload.py -- \
      assets/ybot/scene.blend assets/ybot/scene.blend [GRIP_SOURCE_ANIM]
"""
import sys
from math import radians

import bpy
from mathutils import Quaternion, Vector

FPS = 30
END_FRAME = 72          # 2.4초
PREFIX = 'mixamorig:'

R_HAND = 'RightHand'
L_ARM, L_FORE, L_HAND = 'LeftArm', 'LeftForeArm', 'LeftHand'

# 페이즈 키프레임. (frame, { 본접미사: ((axis), deg), ... })
# 명시 안 된 본 = 그립 포즈 유지. deg = 그립 포즈에 누적할 로컬 추가 회전.
PHASES = [
    (0,  {}),                                                       # 그립 (북엔드)
    (12, {L_ARM: ((1, 0, 0), -8),  L_FORE: ((1, 0, 0), 35)}),       # 1) 왼손 탄창으로 (뒤/아래)
    (22, {L_ARM: ((1, 0, 0), -25), L_FORE: ((1, 0, 0), 30),
          L_HAND: ((1, 0, 0), -22)}),                              # 2) 빈 탄창 빼기 (아래)
    (30, {L_ARM: ((1, 0, 0), -32), L_FORE: ((1, 0, 0), 24)}),       # 3) 새 탄창 집기 (최저)
    (40, {L_ARM: ((1, 0, 0), -14), L_FORE: ((1, 0, 0), 44),
          L_HAND: ((1, 0, 0), 18)}),                               # 4) 탄창 삽입 (위)
    (50, {L_ARM: ((1, 0, 0), -16), L_FORE: ((1, 0, 0), 46)}),       # 5) 왼손 노리쇠로 (수용부)
    (56, {L_ARM: ((1, 0, 0), -22), L_FORE: ((1, 0, 0), 52),
          L_HAND: ((0, 0, 1), -15)}),                              # 6) 노리쇠 당김 (뒤로 살짝)
    (63, {L_ARM: ((1, 0, 0), -12), L_FORE: ((1, 0, 0), 40)}),       # 7) 노리쇠 앞으로
    (72, {}),                                                       # 그립 복귀 (북엔드)
]

argv = sys.argv
if '--' not in argv:
    raise SystemExit('args required after --')
argv = argv[argv.index('--') + 1:]
in_blend = argv[0]
out_blend = argv[1]
grip_anim = argv[2] if len(argv) > 2 else 'RifleIdle'

bpy.ops.wm.open_mainfile(filepath=in_blend)

scene = bpy.context.scene
scene.render.fps = FPS
scene.frame_start = 0
scene.frame_end = END_FRAME

arm = bpy.data.objects.get('YBot') or next(
    (o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
if arm is None:
    raise SystemExit('No armature found')

bpy.context.view_layer.objects.active = arm
arm.select_set(True)
if not arm.animation_data:
    arm.animation_data_create()
ad = arm.animation_data
for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'


def bind_slot(action):
    if hasattr(ad, 'action_slot') and ad.action_slot is None and len(action.slots):
        ad.action_slot = action.slots[0]


# --- 1) 그립 포즈 캡처 (RifleIdle) ------------------------------------------
grip_action = bpy.data.actions.get(grip_anim)
if grip_action is None:
    raise SystemExit(f'grip source action {grip_anim!r} not found')
ad.action = grip_action
bind_slot(grip_action)
scene.frame_set(int(grip_action.frame_range[0]))
bpy.context.view_layer.update()

grip = {}
for pb in arm.pose.bones:
    grip[pb.name] = (pb.rotation_quaternion.copy(), pb.location.copy())

# --- 2) RifleReload 액션 생성 ------------------------------------------------
old = bpy.data.actions.get('RifleReload')
if old is not None:
    old.use_fake_user = False
    bpy.data.actions.remove(old)
reload_action = bpy.data.actions.new('RifleReload')
reload_action.use_fake_user = True
ad.action = reload_action
bind_slot(reload_action)


def apply_grip(pb):
    q, loc = grip[pb.name]
    pb.rotation_quaternion = q
    pb.location = loc


def key_bone(pb, frame):
    pb.keyframe_insert(data_path='rotation_quaternion', frame=frame)
    pb.keyframe_insert(data_path='location', frame=frame)


# --- 3) 페이즈 키프레임 ------------------------------------------------------
for frame, overrides in PHASES:
    for pb in arm.pose.bones:
        apply_grip(pb)
    for suffix, (axis, deg) in overrides.items():
        pb = arm.pose.bones.get(PREFIX + suffix)
        if pb is None:
            print(f'[scaffold] WARN bone not found: {PREFIX + suffix}', flush=True)
            continue
        q_grip, _ = grip[pb.name]
        pb.rotation_quaternion = q_grip @ Quaternion(Vector(axis), radians(deg))
    for pb in arm.pose.bones:
        key_bone(pb, frame)

# --- 4) NLA push down --------------------------------------------------------
for t in list(ad.nla_tracks):
    if t.name == 'RifleReload':
        ad.nla_tracks.remove(t)
track = ad.nla_tracks.new()
track.name = 'RifleReload'
track.strips.new('RifleReload', 0, reload_action)
ad.action = None

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print('[scaffold] RifleReload action written OK', flush=True)
