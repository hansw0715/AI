"""
scene.blend 에 'Reload' 액션을 스캐폴딩 (헤드리스 Blender) — 멀티페이즈 버전.

시퀀스:
  그립 → 오른손으로 총 살짝 기울임 + 왼손 탄창으로 → 빈 탄창 빼서 아래로
       → 왼손 최저(새 탄창 집기) → 탄창 삽입 → 왼손 슬라이드로 → 슬라이드 당김 → 그립 복귀

- 북엔드(f0 / END)는 GRIP_SOURCE_ANIM(기본 Idle) 그립 포즈 → locomotion 과 이음새 없음
- 각 페이즈에서 명시한 본만 그립 포즈에 추가 회전, 나머지 본은 그립 유지
- 오른손(총) tilt 는 '살짝'만 + 끝에서 그립 복귀 → 총이 화면에서 안정적
- 슬라이드 래킹은 게임 코드의 slide_recoil 가 담당 (이 스크립트는 손 모션만)

각 추가 회전은 Mixamo 로컬 축 기준이라 방향이 어긋날 수 있음 → PHASES 의 axis / deg 튜닝.

사용:
  blender --background --python scripts/blender_scaffold_reload.py -- \
      assets/ybot/scene.blend assets/ybot/scene.blend [GRIP_SOURCE_ANIM]
"""
import sys
from math import radians

import bpy
from mathutils import Quaternion, Vector

# --- 튜닝 상수 ---------------------------------------------------------------
FPS = 30
END_FRAME = 60          # 2.0초
PREFIX = 'mixamorig:'

R_HAND = 'RightHand'
L_ARM, L_FORE, L_HAND = 'LeftArm', 'LeftForeArm', 'LeftHand'

LARM_J  = PREFIX + 'LeftArm'
LFORE_J = PREFIX + 'LeftForeArm'
LHAND_J = PREFIX + 'LeftHand'
RHAND_J = PREFIX + 'RightHand'

# 슬라이드 IK target = 그립 RightHand 위치 + 오프셋 (armature cm 단위).
# 게임 안에서 P-marker 로 잡은 RightHand-local 좌표 (10, 16, 4).
SLIDE_RIGHT = 8.0     # X
SLIDE_FWD   = 20.0    # Y
SLIDE_UP    = 15.0    # Z
SLIDE_PULL  = 6.0     # 슬라이드 당길 때 -Y 로 뒤로
SLIDE_WRIST = ((1, 0, 0), 20)        # 손목은 작은 회전만 (이전 좋은 값)
SLIDE_FOREARM_ROLL = 90              # LeftForeArm 길이축 (Y) — 손등 위 향하게

# 페이즈 키프레임. (frame, { 본접미사: ((axis), deg), ... })
# 명시 안 된 본 = 그립 포즈 유지. deg = 그립 포즈에 누적할 로컬 추가 회전.
# 방향/크기가 이상하면 해당 항목의 axis 벡터 / deg 부호·값만 바꾸면 됨.
PHASES = [
    (0,  {}),                                                    # 그립 (북엔드)
    (12, {R_HAND: ((0, 1, 0), 14),
          L_ARM:  ((1, 0, 0), -20), L_FORE: ((1, 0, 0), 38)}),   # 1) 총 기울임 + 왼손 탄창으로
    (22, {R_HAND: ((0, 1, 0), 14),
          L_ARM:  ((1, 0, 0), -32), L_FORE: ((1, 0, 0), 30),
          L_HAND: ((1, 0, 0), -25)}),                            # 2) 탄창 빼기
    (34, {R_HAND: ((0, 1, 0), 14),
          L_ARM:  ((1, 0, 0), -22), L_FORE: ((1, 0, 0), 42),
          L_HAND: ((1, 0, 0), 15)}),                             # 3) 탄창 넣기
    (42, {R_HAND: ((0, 1, 0), 0),
          L_ARM:  ((1, 0, 0), -18), L_FORE: ((1, 0, 0), 44)}),   # 4) 오른손 원위치
    (60, {}),                                                    # 그립 복귀 (북엔드)
    # 5) 슬라이드 페이즈는 build_slide_ik() 가 f48/f53/f57 에 IK 결과로 키 박음
]
# ----------------------------------------------------------------------------

argv = sys.argv
if '--' not in argv:
    raise SystemExit('args required after --')
argv = argv[argv.index('--') + 1:]
in_blend = argv[0]
out_blend = argv[1]
grip_anim = argv[2] if len(argv) > 2 else 'Idle'

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
    """slotted action(Blender 4.4+) 이면 첫 slot 을 active 로 bind."""
    if hasattr(ad, 'action_slot') and ad.action_slot is None and len(action.slots):
        ad.action_slot = action.slots[0]


# --- 1) 그립 포즈 캡처 -------------------------------------------------------
grip_action = bpy.data.actions.get(grip_anim)
if grip_action is None:
    raise SystemExit(f'grip source action {grip_anim!r} not found')

ad.action = grip_action
bind_slot(grip_action)
scene.frame_set(int(grip_action.frame_range[0]))
bpy.context.view_layer.update()

grip = {}
grip_pos = {}                      # armature-space 위치 (IK target 계산용)
for pb in arm.pose.bones:
    grip[pb.name] = (pb.rotation_quaternion.copy(), pb.location.copy())
    grip_pos[pb.name] = pb.matrix.translation.copy()

# --- 2) Reload 액션 생성 -----------------------------------------------------
old = bpy.data.actions.get('Reload')
if old is not None:
    old.use_fake_user = False
    bpy.data.actions.remove(old)

reload_action = bpy.data.actions.new('Reload')
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


def build_slide_ik(scene):
    """슬라이드 페이즈(f48/f53/f57)를 2본 IK 로 풀어 visual rotation 으로 bake."""
    from mathutils import Vector

    # 진단: grip 포즈에서 LeftHand 본 armature-space 로컬축
    for pb in arm.pose.bones:
        apply_grip(pb)
    bpy.context.view_layer.update()
    lh = arm.pose.bones[LHAND_J]
    print('[axis] LHAND x=', lh.bone.x_axis, ' y=', lh.bone.y_axis,
          ' z=', lh.bone.z_axis, flush=True)

    rhand_p = grip_pos[RHAND_J]
    lhand_p = grip_pos[LHAND_J]
    base = rhand_p + Vector((SLIDE_RIGHT, SLIDE_FWD, SLIDE_UP))   # 슬라이드 잡는 위치
    targets = {
        48: base,                                            # 잡음
        53: base + Vector((0.0, -SLIDE_PULL, -7.0)),         # 뒤로 + 아래로 7cm
        57: base * 0.5 + lhand_p * 0.5,                      # 놓고 그립으로 중간
    }

    tgt = bpy.data.objects.new('SlideIKTarget', None)
    scene.collection.objects.link(tgt)

    lfore = arm.pose.bones[LFORE_J]
    ik = lfore.constraints.new('IK')
    ik.target = tgt
    ik.chain_count = 2
    ik.use_tail = True

    # Pass 1: IK 평가된 visual matrix 수집
    collected = {}
    for f, tpos in targets.items():
        scene.frame_set(f)
        tgt.location = arm.matrix_world @ tpos
        bpy.context.view_layer.update()
        collected[f] = {
            LARM_J:  arm.pose.bones[LARM_J].matrix.copy(),
            LFORE_J: arm.pose.bones[LFORE_J].matrix.copy(),
        }
        lh = arm.pose.bones[LHAND_J].matrix.translation
        print(f'[ik] f{f} target={tpos} -> LeftHand={lh}', flush=True)

    lfore.constraints.remove(ik)
    bpy.data.objects.remove(tgt, do_unlink=True)
    bpy.context.view_layer.update()

    # Pass 2: 전체 본 그립 + 왼팔 IK visual 로 덮어쓰기
    from mathutils import Quaternion, Vector as V
    wrist_axis, wrist_deg = SLIDE_WRIST
    for f, mats in collected.items():
        scene.frame_set(f)
        for pb in arm.pose.bones:
            apply_grip(pb)
        bpy.context.view_layer.update()
        for pb in arm.pose.bones:
            key_bone(pb, f)
        # 부모(LARM) 먼저, update, 그 다음 LFORE
        pb = arm.pose.bones[LARM_J]
        pb.matrix = mats[LARM_J]
        key_bone(pb, f)
        bpy.context.view_layer.update()
        pb = arm.pose.bones[LFORE_J]
        pb.matrix = mats[LFORE_J]
        bpy.context.view_layer.update()
        # forearm 길이축(local Y) 기준 roll 추가 — position 은 유지, 손 회전됨
        roll_q = Quaternion(V((0, 1, 0)), radians(SLIDE_FOREARM_ROLL))
        pb.rotation_quaternion = pb.rotation_quaternion @ roll_q
        key_bone(pb, f)
        bpy.context.view_layer.update()
        # 손목은 IK 체인 밖 → 작은 회전만
        pb = arm.pose.bones[LHAND_J]
        q_grip, _ = grip[LHAND_J]
        pb.rotation_quaternion = q_grip @ Quaternion(V(wrist_axis), radians(wrist_deg))
        key_bone(pb, f)


# --- 3) 페이즈 키프레임 ------------------------------------------------------
for frame, overrides in PHASES:
    # 먼저 전체 본을 그립 포즈로
    for pb in arm.pose.bones:
        apply_grip(pb)
    # 이 페이즈에서 지정된 본만 추가 회전
    for suffix, (axis, deg) in overrides.items():
        pb = arm.pose.bones.get(PREFIX + suffix)
        if pb is None:
            print(f'[scaffold] WARN bone not found: {PREFIX + suffix}', flush=True)
            continue
        q_grip, _ = grip[pb.name]
        pb.rotation_quaternion = q_grip @ Quaternion(Vector(axis), radians(deg))
    # 전체 본 키 (지정 안 된 본은 그립값으로 고정 → 정지)
    for pb in arm.pose.bones:
        key_bone(pb, frame)

# --- 3') 슬라이드 페이즈: 2본 IK 로 풀어서 visual rotation 키 박음 -----------
build_slide_ik(scene)

# --- 4) NLA push down --------------------------------------------------------
for t in list(ad.nla_tracks):
    if t.name == 'Reload':
        ad.nla_tracks.remove(t)
track = ad.nla_tracks.new()
track.name = 'Reload'
track.strips.new('Reload', 0, reload_action)
ad.action = None

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print('[scaffold] Reload action (multiphase) written OK', flush=True)
