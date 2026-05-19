"""좀비 적 — 2단계: 사람 형태 + 추적 AI + 워킹 애니메이션.

부품 트리 (zombie_root, 키 1.75m):
  zombie_root (render의 자식)
    ├── body / head           — 몸통, 머리 (회전 안 함)
    ├── leg_left_pivot        — 엉덩이 (Z≈0.80) — 회전 노드
    │     └── leg_left        — 다리 wrapper (박스 중심이 wrapper 원점)
    ├── leg_right_pivot ...
    ├── arm_left_pivot        — 어깨 (Z≈1.40) — 회전 노드
    │     └── arm_left ...
    └── arm_right_pivot ...
    + (CollisionNode)         — into-mask ZOMBIE_MASK, PythonTag로 self 역참조

핵심 패턴:
  1) _make_box: models/box(corner-origin)에 자식 박스로 offset을 줘서
     wrapper 원점 = 박스 기하학적 중심이 되게 정규화. 이후 모든 부품 pos/회전을
     "중심 기준"으로 다룰 수 있음.
  2) _setup_pivots: 팔다리는 어깨/엉덩이에서 흔들려야 자연스러우므로
     pivot NodePath를 박스 상단에 두고 wrapper를 wrtReparentTo로 자식 편입.
     pivot.setP(angle)이 자연스러운 흔들기.
  3) flash hit: wrapper에 priority=1로 setColor → 자식 박스의 priority=0 색을
     덮어씌움. clearColor로 다시 원색 복원 (자식 박스의 setColor는 그대로).
  4) 워킹 애니메이션은 sin 기반 매 프레임 계산 (Sequence 안 씀) — idle 복귀가 즉시.
"""

import math

from direct.interval.IntervalGlobal import (
    Func,
    LerpFunc,
    LerpHprInterval,
    LerpPosInterval,
    Parallel,
    Sequence,
    Wait,
)
from panda3d.core import (
    BillboardEffect,
    BitMask32,
    CardMaker,
    ClockObject,
    CollisionNode,
    CollisionSphere,
    TransparencyAttrib,
    Vec3,
)

from .physics import ZOMBIE_MASK


_clock = ClockObject.getGlobalClock()


# 색 ---------------------------------------------------------------
_BODY_COLOR = (0.30, 0.35, 0.25, 1)   # 어두운 녹색
_HEAD_COLOR = (0.40, 0.45, 0.30, 1)   # 약간 더 밝은 녹색
_ARM_COLOR  = (0.30, 0.35, 0.25, 1)
_LEG_COLOR  = (0.20, 0.20, 0.15, 1)   # 진한 색 (바지)
_HIT_COLOR  = (1.0, 0.2, 0.2, 1)

# 피격/사망 -------------------------------------------------------
_FLASH_DURATION = 0.1

# 사망 시퀀스 ----------------------------------------------------
DEATH_FALL_SEC = 0.5       # 뒤로 넘어가는 데 걸리는 시간
DEATH_LINGER_SEC = 0.0     # 쓰러진 채 머무는 시간 (0이면 즉시 페이드)
DEATH_FADE_SEC = 0.6       # 알파 페이드 시간
ZOMBIE_FALL_DROP = 0.4     # 쓰러질 때 살짝 내려앉는 높이 (m)
DEATH_FALL_PITCH = 90      # 뒤로 넘어가는 pitch (어색하면 -90)

# AI 튜닝 ---------------------------------------------------------
WALK_SPEED = 1.2           # m/s — 좀비답게 느림
TURN_SPEED_DEG = 180.0     # 초당 회전 각도
ATTACK_RANGE = 1.6         # m — 이 안에 들어오면 멈추고 공격 windup 시작

# 공격 상태머신 / 데미지 --------------------------------------------
ATTACK_HIT_RANGE = 1.8       # strike 시점에 이 거리 안이면 명중 (RANGE보다 약간 큼)
ATTACK_WINDUP_SEC = 0.45     # 팔 들어올리는 시간
ATTACK_STRIKE_SEC = 0.15     # 휘두름 시간
ATTACK_RECOVER_SEC = 0.35    # 복귀 시간
ATTACK_COOLDOWN_SEC = 0.8    # 다음 공격까지 대기
ATTACK_DAMAGE = 10           # 한 방 피해량

# 비틀비틀 워킹 애니메이션 튜닝 ---------------------------------
WALK_FREQ = 1.4            # Hz — 다리 사이클 (느릿)
LEG_SWING_DEG = 18.0       # 보폭 좁게 (좀비스럽게)
LEG_LIMP_BIAS_DEG = 6.0    # 왼다리가 항상 뒤로 빠지는 절뚝 bias

# 팔: 어깨에서 항상 앞으로 뻗은 자세 + 가벼운 흔들림
ARM_FORWARD_BASE_DEG = -90.0  # 팔 앞으로 뻗은 기본 각도 (P)
ARM_SWAY_DEG = 8.0            # 좌우 (R) 흔들림 폭
ARM_VERTICAL_BOB_DEG = 5.0    # 위아래 (P 보정) 흔들림 폭

# 몸통/머리 비틀거림
BODY_SWAY_DEG = 6.0        # 몸통 좌우 흔들림 (R)
HEAD_TILT_DEG = 12.0       # 머리 기본 기울기 (R, 고정)
HEAD_BOB_DEG = 3.0         # 머리 흔들림 폭 (P)

# 부품 Z 크기 (pivot 계산에 사용) ---------------------------------
_LEG_SIZE_Z = 0.80
_ARM_SIZE_Z = 0.60

# 부위별 데미지 배율 ---------------------------------------------
# raycast hit 부위명 → 데미지 배율 (발로란트식).
DAMAGE_MULTIPLIER = {
    "head": 1.5,
    "body": 1.0,
    "left_arm": 0.5,
    "right_arm": 0.5,
    "left_leg": 0.5,
    "right_leg": 0.5,
}

# 부위별 충돌 sphere 반지름 (m). 좀비 모델 부품 크기에 맞춘 값 — 튜닝 노브.
HIT_SPHERE_RADIUS = {
    "head": 0.20,
    "body": 0.35,
    "left_arm": 0.12,
    "right_arm": 0.12,
    "left_leg": 0.15,
    "right_leg": 0.15,
}

# 공격 모션 ------------------------------------------------------
# 어깨 pivot pitch 좌표: 0 = 팔 아래로 늘어뜨림, -90 = 앞으로 뻗음, +-180 = 위로.
# REST 를 워킹 sway 의 중심 (ARM_FORWARD_BASE_DEG = -90) 에 맞춰야
# recover → chasing 복귀 시 톡 튀지 않음.
# (이전 시도에서 WINDUP/STRIKE 부호가 반대였음 — 사용자가 "반대방향" 지적 후 뒤집음.)
ATTACK_ARM_REST_PITCH = ARM_FORWARD_BASE_DEG   # -90, 워킹 sway 중심과 일치
ATTACK_ARM_WINDUP_PITCH = -30                   # 앞→뒤/위로 60도 들어올림
ATTACK_ARM_STRIKE_PITCH = -120                  # 앞→아래로 30도 휘두름

# 체력바 ---------------------------------------------------------
# 프롬프트는 Y_OFFSET이라고 부르지만 Panda3D는 Z가 위라 Z_OFFSET이 맞다.
HEALTHBAR_WIDTH = 1.0
HEALTHBAR_HEIGHT = 0.12
HEALTHBAR_Z_OFFSET = 2.0           # 좀비 root(발 Z=0) 기준 머리(1.75) 위 25cm
HEALTHBAR_BG_COLOR = (0, 0, 0, 1)
HEALTHBAR_FILL_COLOR = (0.9, 0.1, 0.1, 1)
HEALTHBAR_HOLD_SEC = 2.5           # 마지막 피격 후 풀 알파 유지 시간
HEALTHBAR_FADE_SEC = 1.0           # 페이드 아웃 길이


class Zombie:
    # 부위별 데미지 도입 — BASE_DAMAGE=10 기준: head=15(2발), body=10(3발), limb=5(6발).
    MAX_HP = 30

    def __init__(self, game, position):
        self.game = game
        self.base = game
        self.hp = Zombie.MAX_HP
        # state: "alive" → "dying" (쓰러짐 + 페이드 진행 중) → "dead" (제거됨).
        self.state = "alive"
        # 공격 서브 상태머신 (alive 안에서만 의미 있음).
        # "chasing" → "windup" → "strike" → "recover" → "chasing"...
        self.attack_state = "chasing"
        self.attack_timer = 0.0       # 현재 attack_state에서 흐른 시간
        self.attack_cooldown = 0.0    # 0 이하면 새 공격 시작 가능
        # 매니저가 좀비 제거 시점에 호출되도록 콜백 연결 (set by ZombieManager).
        self.on_removed = None
        self.death_seq = None
        self._restore_task_name = f"zombie_flash_restore_{id(self)}"
        self._moving = False
        self._walk_time = 0.0

        self.np = game.render.attachNewNode("zombie_root")
        self.np.setPos(position)

        self._build_model()
        self._setup_pivots()
        self._setup_hit_parts()
        self._create_healthbar()

    # ---------- 모델 빌드 ----------

    def _make_box(self, name, parent, size, center, color):
        """models/box(corner-origin)를 박스 중심 = wrapper 원점이 되도록 정규화한 부품.

        size: 박스 실제 크기 (m). center: wrapper가 부모 안에 놓일 좌표 (박스 중심).
        반환 wrapper 노드는 곧 박스 기하학적 중심의 위치/회전.
        """
        wrapper = parent.attachNewNode(name)
        wrapper.setPos(center)
        box = self.base.loader.loadModel("models/box")
        box.reparentTo(wrapper)
        box.setScale(size[0], size[1], size[2])
        # 박스 origin이 corner라 wrapper 원점에 박스 중심을 맞추려면 -size/2 offset.
        box.setPos(-size[0] / 2.0, -size[1] / 2.0, -size[2] / 2.0)
        box.setColor(*color)
        return wrapper

    def _build_model(self):
        # 키 1.75m. 발 Z=0, 머리 꼭대기 Z=1.75.
        # 다리는 Z=0~0.80 (다리 중심 0.40), 몸통 Z=0.80~1.45 (중심 1.125),
        # 머리 Z=1.45~1.75 (중심 1.60), 팔은 어깨(1.40)에서 손(0.85)까지 (중심 1.10).
        self.leg_left  = self._make_box(
            "leg_left",  self.np,
            (0.16, 0.16, _LEG_SIZE_Z), Vec3(-0.10, 0, 0.40), _LEG_COLOR,
        )
        self.leg_right = self._make_box(
            "leg_right", self.np,
            (0.16, 0.16, _LEG_SIZE_Z), Vec3( 0.10, 0, 0.40), _LEG_COLOR,
        )
        self.body = self._make_box(
            "body", self.np,
            (0.45, 0.25, 0.65), Vec3(0, 0, 1.125), _BODY_COLOR,
        )
        self.head = self._make_box(
            "head", self.np,
            (0.25, 0.25, 0.30), Vec3(0, 0, 1.60), _HEAD_COLOR,
        )
        self.arm_left = self._make_box(
            "arm_left", self.np,
            (0.13, 0.13, _ARM_SIZE_Z), Vec3(-0.30, 0, 1.10), _ARM_COLOR,
        )
        self.arm_right = self._make_box(
            "arm_right", self.np,
            (0.13, 0.13, _ARM_SIZE_Z), Vec3( 0.30, 0, 1.10), _ARM_COLOR,
        )

    def _setup_pivots(self):
        """팔다리 회전 중심을 박스 중심이 아닌 상단(어깨/엉덩이)으로 옮긴다.

        각 부품 wrapper를 pivot NodePath로 한 번 더 감싸고, wrtReparentTo로
        월드 좌표를 유지한 채 pivot 자식으로 편입. pivot의 원점이 어깨/엉덩이라서
        pivot.setP(angle)이 자연스러운 흔들기 회전이 됨.
        """
        self.leg_left_pivot  = self._wrap_with_pivot(self.leg_left,  _LEG_SIZE_Z)
        self.leg_right_pivot = self._wrap_with_pivot(self.leg_right, _LEG_SIZE_Z)
        self.arm_left_pivot  = self._wrap_with_pivot(self.arm_left,  _ARM_SIZE_Z)
        self.arm_right_pivot = self._wrap_with_pivot(self.arm_right, _ARM_SIZE_Z)

        # 초기 자세 — 좀비 spawn 직후 첫 프레임 전에도 자연스럽게 보이도록
        # 팔은 앞으로 뻗고, 머리는 한쪽으로 살짝 기울임.
        self.arm_left_pivot.setP(ARM_FORWARD_BASE_DEG)
        self.arm_right_pivot.setP(ARM_FORWARD_BASE_DEG)
        self.head.setR(HEAD_TILT_DEG)

    def _wrap_with_pivot(self, part, size_z):
        # pivot 위치 = wrapper 중심 + (0, 0, size_z/2) → 박스 상단(어깨/엉덩이).
        original_pos = part.getPos()
        pivot = self.np.attachNewNode(part.getName() + "_pivot")
        pivot.setPos(original_pos.x, original_pos.y, original_pos.z + size_z / 2.0)
        # wrtReparentTo가 월드 위치 유지하므로 부품 시각 위치는 그대로,
        # 좌표계만 pivot 기준으로 표시됨 → pivot.setP가 어깨/엉덩이 축 회전.
        part.wrtReparentTo(pivot)
        return pivot

    def _setup_hit_parts(self):
        """부위별 충돌 sphere 6개를 각 부품(head/body/팔/다리) 자식으로 부착.

        부품 wrapper의 원점이 박스 기하학적 중심이라 sphere center=(0,0,0)이면
        부품 중심에 맞춰진다. 부품이 워킹/공격 모션으로 회전/이동하면 sphere도 같이 따라감.

        각 sphere 노드에 두 PythonTag:
          - "zombie": Zombie 인스턴스 (raycast 역참조)
          - "hit_part": 부위 이름 ("head"/"body"/"left_arm" 등) — 데미지 배율 키
        """
        part_map = {
            "head": self.head,
            "body": self.body,
            "left_arm": self.arm_left,
            "right_arm": self.arm_right,
            "left_leg": self.leg_left,
            "right_leg": self.leg_right,
        }
        self.hit_part_nodes = {}
        for part_name, part_np in part_map.items():
            if part_np is None or part_np.isEmpty():
                continue
            cn = CollisionNode(f"zombie_hit_{part_name}")
            cn.addSolid(CollisionSphere(0, 0, 0, HIT_SPHERE_RADIUS[part_name]))
            cn.setIntoCollideMask(ZOMBIE_MASK)
            cn.setFromCollideMask(BitMask32.allOff())
            cn_np = part_np.attachNewNode(cn)
            cn_np.setPythonTag("zombie", self)
            cn_np.setPythonTag("hit_part", part_name)
            self.hit_part_nodes[part_name] = cn_np

    # ---------- 체력바 ----------

    def _create_healthbar(self):
        """좀비 머리 위 체력바 — 빌보드 + 라이팅 무시 + 알파 페이드.

        배경(검정) + 채우기(빨강) 두 카드 중첩. 채우기는 pivot으로 감싸
        pivot.setSx만 변경해도 왼쪽 끝 고정 상태로 폭이 줄어든다.
        """
        self.healthbar_root = self.np.attachNewNode("healthbar_root")
        self.healthbar_root.setZ(HEALTHBAR_Z_OFFSET)
        # 항상 카메라를 향함 (point billboard).
        self.healthbar_root.setEffect(BillboardEffect.makePointEye())
        # UI 성격이라 씬 라이팅 영향 X. priority=1로 부모 setLight를 덮어쓴다.
        self.healthbar_root.setLightOff(1)
        # setAlphaScale 페이드를 위해 알파 블렌딩 활성화.
        self.healthbar_root.setTransparency(TransparencyAttrib.MAlpha)

        # 배경 카드 (검정) — XZ 평면에 중앙 정렬.
        bg_cm = CardMaker("healthbar_bg")
        bg_cm.setFrame(
            -HEALTHBAR_WIDTH / 2, HEALTHBAR_WIDTH / 2,
            -HEALTHBAR_HEIGHT / 2, HEALTHBAR_HEIGHT / 2,
        )
        bg_card = self.healthbar_root.attachNewNode(bg_cm.generate())
        bg_card.setColor(*HEALTHBAR_BG_COLOR)

        # 채우기 pivot — 원점을 바의 왼쪽 끝으로 이동.
        # 이후 pivot.setSx(ratio)만 호출하면 왼쪽 끝 고정으로 폭이 변함.
        self.healthbar_fill_pivot = self.healthbar_root.attachNewNode(
            "healthbar_fill_pivot"
        )
        self.healthbar_fill_pivot.setX(-HEALTHBAR_WIDTH / 2)

        # 채우기 카드 (빨강) — pivot 원점에서 +X로 W만큼.
        fill_cm = CardMaker("healthbar_fill")
        fill_cm.setFrame(
            0, HEALTHBAR_WIDTH,
            -HEALTHBAR_HEIGHT / 2, HEALTHBAR_HEIGHT / 2,
        )
        fill_card = self.healthbar_fill_pivot.attachNewNode(fill_cm.generate())
        fill_card.setColor(*HEALTHBAR_FILL_COLOR)
        # 같은 평면에 두 카드가 겹쳐 z-fighting 가능 → 채우기를 살짝 카메라 쪽으로.
        fill_card.setY(-0.001)

        # 초기 상태 — 숨김. 첫 피격 때 표시.
        self.healthbar_root.hide()
        self.last_hit_time = None

    def _update_healthbar_fill(self):
        """현재 hp 비율로 채우기 X 스케일 조정 (왼쪽 정렬).

        setSx(0)은 스케일 행렬을 특이행렬로 만들어 일부 드라이버에서
        "Tried to invert singular LMatrix4" 경고를 띄움 → 0.001로 클램프.
        시각적으로 0.001 폭은 사실상 보이지 않음 (배경 검정이 그대로 보임).
        """
        ratio = max(0.001, self.hp / Zombie.MAX_HP)
        self.healthbar_fill_pivot.setSx(ratio)

    def _update_healthbar_alpha(self):
        """피격 후 HOLD_SEC만큼 풀 알파, 이후 FADE_SEC 동안 선형 페이드 → 숨김."""
        if self.last_hit_time is None:
            return
        elapsed = _clock.getFrameTime() - self.last_hit_time
        if elapsed < HEALTHBAR_HOLD_SEC:
            alpha = 1.0
        elif elapsed < HEALTHBAR_HOLD_SEC + HEALTHBAR_FADE_SEC:
            t = (elapsed - HEALTHBAR_HOLD_SEC) / HEALTHBAR_FADE_SEC
            alpha = 1.0 - t
        else:
            self.healthbar_root.hide()
            # 다음 update 호출에서 또 hide 안 부르도록 타이머 클리어.
            self.last_hit_time = None
            return
        self.healthbar_root.setAlphaScale(alpha)

    # ---------- 공격 상태머신 ----------

    def _dist_to_player(self):
        player_pos = self.game.player.node.getPos(self.game.render)
        my_pos = self.np.getPos(self.game.render)
        return (player_pos - my_pos).length()

    def _face_player_instant(self):
        """수평(H)만 회전해서 즉시 플레이어를 바라봄. windup 진입 시 1회 호출."""
        player_pos = self.game.player.node.getPos(self.game.render)
        my_pos = self.np.getPos(self.game.render)
        to_player = player_pos - my_pos
        self.np.setH(math.degrees(math.atan2(-to_player.x, to_player.y)))

    def _enter_windup(self):
        self.attack_state = "windup"
        self.attack_timer = 0.0
        # 한 번만 플레이어 쪽으로 회전 — 이후엔 안 따라감 (피하기 가능, 의도적).
        self._face_player_instant()

    def _enter_strike(self):
        self.attack_state = "strike"
        self.attack_timer = 0.0
        # 데미지 판정 1회. windup 도중 플레이어가 빠지면 빗나감.
        if self._dist_to_player() < ATTACK_HIT_RANGE:
            self.game.player.take_damage(ATTACK_DAMAGE, source=self)

    def _enter_recover(self):
        self.attack_state = "recover"
        self.attack_timer = 0.0

    def _apply_arm_pose(self, start_pitch, end_pitch, t):
        """오른팔 어깨 pivot pitch를 start→end로 선형 보간. t는 0..1."""
        t = min(1.0, max(0.0, t))
        pitch = start_pitch + (end_pitch - start_pitch) * t
        self.arm_right_pivot.setHpr(0, pitch, 0)

    def _update_attack(self, dt):
        self.attack_timer += dt
        if self.attack_state == "windup":
            self._apply_arm_pose(
                ATTACK_ARM_REST_PITCH, ATTACK_ARM_WINDUP_PITCH,
                self.attack_timer / ATTACK_WINDUP_SEC,
            )
            if self.attack_timer >= ATTACK_WINDUP_SEC:
                self._enter_strike()
        elif self.attack_state == "strike":
            self._apply_arm_pose(
                ATTACK_ARM_WINDUP_PITCH, ATTACK_ARM_STRIKE_PITCH,
                self.attack_timer / ATTACK_STRIKE_SEC,
            )
            if self.attack_timer >= ATTACK_STRIKE_SEC:
                self._enter_recover()
        elif self.attack_state == "recover":
            self._apply_arm_pose(
                ATTACK_ARM_STRIKE_PITCH, ATTACK_ARM_REST_PITCH,
                self.attack_timer / ATTACK_RECOVER_SEC,
            )
            if self.attack_timer >= ATTACK_RECOVER_SEC:
                self.attack_state = "chasing"
                self.attack_cooldown = ATTACK_COOLDOWN_SEC

    # ---------- 매 프레임 업데이트 ----------

    def update(self, dt):
        # dying/dead 는 Sequence 가 알아서 처리. AI/모션/체력바 알파 모두 정지.
        if self.state != "alive":
            return
        self._update_healthbar_alpha()

        if self.attack_state == "chasing":
            self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
            dist = self._dist_to_player()
            if dist < ATTACK_RANGE and self.attack_cooldown <= 0.0:
                self._enter_windup()
                return
            self._update_chase(dt)
            self._update_walk_anim(dt)
        else:
            # windup/strike/recover — 공격 포즈만 갱신. 이동/워킹은 정지.
            self._update_attack(dt)

    def _update_chase(self, dt):
        player_pos = self.game.player.node.getPos(self.game.render)
        my_pos = self.np.getPos(self.game.render)
        to_player = player_pos - my_pos
        to_player.z = 0  # 수평 거리만 — 머리 위/아래로는 안 봄
        dist = to_player.length()

        if dist < 0.01:
            self._moving = False
            return

        # 1) 플레이어를 향하도록 yaw 회전 — TURN_SPEED_DEG/s 제한.
        # Panda3D는 +Y가 전방, +H가 시계 반대. atan2(-x, y)로 +Y 기준 좌우 각도.
        target_yaw = math.degrees(math.atan2(-to_player.x, to_player.y))
        current_yaw = self.np.getH()
        # 짧은 쪽으로 회전하도록 -180~+180 정규화.
        delta = ((target_yaw - current_yaw + 180.0) % 360.0) - 180.0
        max_turn = TURN_SPEED_DEG * dt
        if abs(delta) <= max_turn:
            self.np.setH(target_yaw)
        else:
            self.np.setH(current_yaw + math.copysign(max_turn, delta))

        # 2) ATTACK_RANGE 밖이면 좀비 자신의 forward(+Y) 방향으로 전진.
        if dist > ATTACK_RANGE:
            forward = self.game.render.getRelativeVector(self.np, Vec3(0, 1, 0))
            forward.z = 0
            forward.normalize()
            new_pos = my_pos + forward * (WALK_SPEED * dt)
            new_pos.z = my_pos.z  # Z 고정 — ground snap은 다음 단계
            self.np.setPos(new_pos)
            self._moving = True
        else:
            self._moving = False

    def _update_walk_anim(self, dt):
        """비틀비틀 좀비 워킹 — 매 프레임 절댓값 setHpr/setR/setP (누적 X).

        - 다리: 좁은 보폭 + LIMP_BIAS로 왼다리가 항상 뒤로 빠진 채 흔들림.
        - 팔: 어깨에서 ARM_FORWARD_BASE_DEG(=-90)로 앞을 향한 채 좌우/상하 가벼운 흔들림.
        - 몸통: 좌우(R) sway. 머리: 한쪽으로 기울인 채 약한 떨림.

        idle 시 intensity=0.3으로 줄이고 _walk_time을 멈춰서 마지막 흔들림에서
        잔잔히 멈춤 (완전 정지보다 좀비답게 보임).
        """
        if self._moving:
            self._walk_time += dt
        intensity = 1.0 if self._moving else 0.3

        cycle = self._walk_time * WALK_FREQ * 2.0 * math.pi
        s = math.sin(cycle)
        s_half = math.sin(cycle * 0.5)

        # 다리 — LIMP_BIAS는 왼다리에만 (오른다리는 mirror).
        leg_angle = s * LEG_SWING_DEG * intensity
        self.leg_left_pivot.setP(leg_angle - LEG_LIMP_BIAS_DEG * intensity)
        self.leg_right_pivot.setP(-leg_angle)

        # 팔 — 앞으로 뻗은 기본 자세에 상하(P 보정) + 좌우(R) 흔들림 추가.
        # 양팔은 좌우 대칭으로 흔들림 (왼팔과 오른팔이 반대 위상).
        arm_bob = s * ARM_VERTICAL_BOB_DEG * intensity
        arm_sway = s_half * ARM_SWAY_DEG * intensity
        self.arm_left_pivot.setHpr(0, ARM_FORWARD_BASE_DEG + arm_bob, +arm_sway)
        self.arm_right_pivot.setHpr(0, ARM_FORWARD_BASE_DEG - arm_bob, -arm_sway)

        # 몸통 sway.
        body_roll = s_half * BODY_SWAY_DEG * intensity
        self.body.setR(body_roll)

        # 머리 — HEAD_TILT_DEG 고정 기울기 + body_roll의 절반만큼 따라 흔들림 + 약한 P 떨림.
        head_bob = s * HEAD_BOB_DEG * intensity
        self.head.setHpr(0, head_bob, HEAD_TILT_DEG + body_roll * 0.5)

    # ---------- 피격 / 사망 ----------

    def take_damage(self, amount=1, hit_part=None):
        """hit_part 가 DAMAGE_MULTIPLIER 키면 배율 적용, 아니면 amount 그대로."""
        if self.state != "alive":
            return
        if hit_part is not None and hit_part in DAMAGE_MULTIPLIER:
            final_damage = int(round(amount * DAMAGE_MULTIPLIER[hit_part]))
        else:
            final_damage = int(round(amount))
        self.hp -= final_damage
        self._flash_hit()

        # 체력바를 항상 갱신 — hp=0 도 빈 바로 보여야 한다 (사용자 요청).
        # 페이드 중이었어도 즉시 풀 알파로 복귀.
        if self.hp <= 0:
            self.hp = 0
        self.last_hit_time = _clock.getFrameTime()
        self.healthbar_root.show()
        self.healthbar_root.setAlphaScale(1.0)
        self._update_healthbar_fill()

        if self.hp <= 0:
            self._start_death()

    def _flash_hit(self):
        # 연사로 hit 받을 때 색 복원이 먼저 발동해 깜빡이 끊기지 않도록 이전 task 제거.
        self.base.taskMgr.remove(self._restore_task_name)
        # wrapper에 priority=1로 색을 덮어 자식 박스의 priority=0 색을 override.
        self.body.setColor(*_HIT_COLOR, 1)
        self.head.setColor(*_HIT_COLOR, 1)
        self.base.taskMgr.doMethodLater(
            _FLASH_DURATION, self._restore_color, self._restore_task_name
        )

    def _restore_color(self, task):
        if self.state == "alive":
            # wrapper의 color attrib만 제거 → 자식 박스의 원색이 다시 보임.
            self.body.clearColor()
            self.head.clearColor()
        return task.done

    def _start_death(self):
        """뒤로 쓰러짐 → 페이드 → 제거 시퀀스 시작. 추적/공격/충돌은 즉시 중단."""
        self.state = "dying"
        # 공격 중에 죽으면 어깨 pivot이 windup/strike 자세로 박제됨 → 리셋.
        self.attack_state = "chasing"
        self.arm_right_pivot.setHpr(0, ATTACK_ARM_REST_PITCH, 0)

        # 부위별 충돌 마스크 + PythonTag 모두 해제 — raycast 가 죽은 좀비를 더 안 잡음.
        # pythonTag 는 강참조라 명시적으로 끊어야 좀비 인스턴스 GC 가능.
        for cn_np in self.hit_part_nodes.values():
            cn_np.node().setIntoCollideMask(BitMask32.allOff())
            cn_np.node().setFromCollideMask(BitMask32.allOff())
            cn_np.clearPythonTag("zombie")
            cn_np.clearPythonTag("hit_part")

        # 진행 중인 flash 복원 task 도 정리 (사망 후 색 변경 의미 없음).
        self.base.taskMgr.remove(self._restore_task_name)

        # 알파 페이드를 위해 root 에 transparency 활성화.
        # 체력바도 자식이라 root.setAlphaScale 페이드에 함께 사라진다
        # (prompt_02 는 즉시 hide/removeNode 지시했지만, 사용자가 "체력 0 상태도 보고 싶다"
        #  고 했으므로 체력바를 남겨두고 페이드와 함께 자연 소실시킴).
        self.np.setTransparency(TransparencyAttrib.MAlpha)

        # 쓰러짐 시작/종착 HPR/POS 미리 캐싱 (LerpInterval 은 절댓값).
        start_hpr = self.np.getHpr()
        end_hpr = Vec3(start_hpr.x, start_hpr.y + DEATH_FALL_PITCH, start_hpr.z)
        start_pos = self.np.getPos()
        end_pos = Vec3(start_pos.x, start_pos.y, start_pos.z - ZOMBIE_FALL_DROP)

        self.death_seq = Sequence(
            Parallel(
                LerpHprInterval(self.np, DEATH_FALL_SEC, end_hpr),
                LerpPosInterval(self.np, DEATH_FALL_SEC, end_pos),
            ),
            Wait(DEATH_LINGER_SEC),
            LerpFunc(
                self._set_corpse_alpha,
                fromData=1.0, toData=0.0,
                duration=DEATH_FADE_SEC,
            ),
            Func(self._remove_corpse),
        )
        self.death_seq.start()

    def _set_corpse_alpha(self, alpha):
        # root 가 이미 제거됐을 수 있으니 방어적 체크.
        if not self.np.isEmpty():
            self.np.setAlphaScale(alpha)

    def _remove_corpse(self):
        self.state = "dead"
        self.death_seq = None
        if not self.np.isEmpty():
            self.np.removeNode()
        # 매니저가 리스트에서 자기 자신을 빼도록 콜백 호출.
        if self.on_removed is not None:
            self.on_removed(self)


class ZombieManager:
    def __init__(self, game):
        self.game = game
        self.zombies = []

    def spawn(self, position):
        z = Zombie(self.game, position)
        # 좀비 사망 시퀀스 끝에서 매니저 리스트에서 자동 제거되도록 콜백 연결.
        z.on_removed = self._on_zombie_removed
        self.zombies.append(z)
        return z

    def _on_zombie_removed(self, zombie):
        if zombie in self.zombies:
            self.zombies.remove(zombie)

    def spawn_initial_wave(self):
        """플레이어 스폰(0,0,2) 주변 4-10m에 5마리 배치.

        Ground 범위 X(-11~10), Y(-10~11) 안. Z=0 고정.
        """
        positions = [
            Vec3( 4,  6, 0),
            Vec3(-3,  7, 0),
            Vec3( 6, -4, 0),
            Vec3(-5, -5, 0),
            Vec3( 0, 10, 0),
        ]
        for pos in positions:
            self.spawn(pos)

    def update(self, dt):
        for z in self.zombies:
            z.update(dt)
