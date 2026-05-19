"""1인칭 무기 시스템 — 권총 + 양손 + 현실적 재장전 안무.

부품 트리:
  self.np (pistol_root, 카메라 자식)
  ├── self.grip       — 손잡이. 안 움직임.
  ├── self.frame      — 그립↔슬라이드 이음 몸체. 안 움직임.
  ├── self.slide      — 발사 시 뒤로, 재장전 마지막에 뒤로. anchor 노드.
  │   ├── slide_mesh  — 보이는 슬라이드 박스
  │   └── self.barrel — 총신
  │       └── self._muzzle_flash
  ├── self.magazine   — 재장전 시 빠졌다 돌아옴.
  ├── self.right_hand — 그립을 잡은 오른손. 항상 pistol 자식.
  └── self.left_hand  — 슬라이드 옆을 받치는 왼손.
                         재장전 중에만 camera 자식으로 reparent돼 권총 회전과 독립적으로 움직임.

self.slide가 scale 없는 anchor인 이유:
  Panda3D는 부모의 scale을 자식 좌표/크기에 곱해 전파한다. self.slide에
  setScale을 직접 두면 자식인 self.barrel/self._muzzle_flash가 함께 축소되어
  위치도 의도와 다르게 이동한다. 따라서 anchor 노드(no-scale) + 자식 메시
  분리 패턴을 사용해 슬라이드 모션이 자식에 전파되되 스케일은 전파되지 않게 한다.

레이캐스트용 CollisionTraverser를 별도로 둠 — 이유:
  플레이어의 ground traverser는 매 프레임 traverse되어야 하지만,
  권총 사격은 mouse1 클릭 시점에만 1회 traverse하면 충분하므로
  역할을 분리해 traverse 비용을 절약하고 의도를 명확히 한다.
"""

import math

from direct.interval.IntervalGlobal import (
    Func,
    LerpHprInterval,
    LerpPosInterval,
    Parallel,
    Sequence,
    Wait,
)
from panda3d.core import (
    BitMask32,
    CollisionHandlerQueue,
    CollisionNode,
    CollisionRay,
    CollisionTraverser,
    LineSegs,
    Vec3,
)

from .effects import spawn_hit_particles
from .hands import Hand
from .physics import HITTABLE_MASK, ZOMBIE_MASK


def _find_zombie_and_part(entry):
    """raycast entry 에서 (Zombie, hit_part) 추출. 부위별 충돌 노드에
    "zombie"/"hit_part" 두 태그가 같이 박혀 있어서 getNetPythonTag 한 번에 잡힘.
    """
    hit_np = entry.getIntoNodePath()
    zombie = hit_np.getNetPythonTag("zombie")
    hit_part = hit_np.getNetPythonTag("hit_part")
    return zombie, hit_part


MAG_SIZE = 12
COOLDOWN = 0.2
RELOAD_TIME = 2.0  # 검사 자세(inspect) 안무가 충분히 보이도록 1.8 → 2.0
MAX_RANGE = 100.0
BASE_DAMAGE = 10   # 권총 한 발 기본 데미지. 부위 배율 적용 전 값.

# 화면 우중하단에 권총 배치. Z를 살짝 올려(-0.20 → -0.12) 가만히 있을 때
# 양손이 화면 안에 잘 보이도록 함. (모든 자식 — 권총 부품/양손 — 같이 올라감)
PISTOL_REST_POS = Vec3(0.25, 0.9, -0.12)

# ADS (Aim Down Sights) — 우클릭 시 권총을 화면 중앙으로 옮겨 가늠쇠 조준 자세.
# REST 는 우측 hip-fire 자세, ADS 는 화면 중심선(X=0)에 정렬.
# Y 는 약간 앞으로(0.85), Z 는 살짝 위로(-0.10) — 가늠쇠가 카메라 광축 부근에 오도록.
ADS_GUN_POS = Vec3(0.0, 0.85, -0.10)
ADS_LERP_TIME = 0.12          # 권총 위치 전환 시간 (초) — FOV lerp 와 같은 값

# 보행 sway — ADS / 달리기 분기 ----------------------------------
# 설계 원칙: ADS 중에는 권총(조준선)은 거의 안 움직이고 팔만 적당히 움직임.
# 그래서 권총용 진폭과 팔용 진폭을 분리해 둠. 권총 sway 는 np_sway 노드에 setPos,
# 팔 sway 는 right_hand/left_hand 의 HPR delta 로 적용 (REST_HPR + sway).
WALK_SWAY_AMPLITUDE = 1.0     # 걷기 기본 진폭 배수
WALK_SWAY_FREQ = 4.0          # Hz (걷기 사이클)
ADS_GUN_SWAY_MULT = 0.08      # ADS 중 권총 진폭 8% (조준선 안정)
ADS_ARM_SWAY_MULT = 0.42      # ADS 중 팔 진폭 42% (자연스러운 보행감)
RUN_AMPLITUDE_MULT = 1.7      # 달리기 시 진폭 1.7배
RUN_FREQ_MULT = 1.5           # 달리기 시 주파수 1.5배
GUN_SWAY_X_SCALE = 0.020      # 권총 좌우 sway 최대 변위 (m, amp=1.0 기준)
GUN_SWAY_Z_SCALE = 0.012      # 권총 상하 sway 최대 변위 (m)
ARM_SWAY_P_DEG = 3.0          # 팔 피치 sway 최대 (도, amp=1.0 기준)
ARM_SWAY_R_DEG = 1.5          # 팔 롤 sway 최대 (도)
SWAY_BLEND_RATE = 8.0         # 정지/움직임 전환 시 0 으로 수렴 속도 (높을수록 빠름)

# 부품별 모션 상수
SLIDE_RECOIL_OFFSET = Vec3(0, -0.04, 0)
# 탄창 낙하 거리. 0.12로는 짧아 잘 안 보여서 -0.30로 키움 (확실히 보임)
MAG_DROP_OFFSET = Vec3(0, 0, -0.30)
RECOIL_PITCH_DEG = 2.0

# 양손 휴식 자세 (pistol-local 좌표/HPR):
#  - 오른손: 그립 위치와 동일 좌표 (그립을 감싼 자세).
#  - 왼손: 오른손 바로 옆/아래에서 받치는 양손 그립 자세 (Weaver/Isosceles 스탠스).
#    오른손 (-0.026, -0.091, -0.13) 기준 살짝 왼쪽/아래로 두고, HPR은 좌우 미러.
RIGHT_HAND_REST_POS = Vec3(-0.026, -0.091, -0.13)
RIGHT_HAND_REST_HPR = (15, -25, 0)
# 왼손을 오른손 (-0.026, -0.091, -0.13) 바로 밑에 배치 — X/Y 거의 일치, Z만 7cm 아래.
# HPR도 완화해 팔이 화면을 가리는 정도 줄임.
LEFT_HAND_REST_POS = Vec3(-0.03, -0.09, -0.20)
LEFT_HAND_REST_HPR = (-10, -10, 10)

HIT_MARKER_LIFETIME = 0.5
HIT_MARKER_SCALE = 0.05

# 총신 앞쪽 끝점 (barrel 노드 로컬 좌표 = unit-cube 0..1 기준).
BARREL_TIP_LOCAL = Vec3(0, 0.6, 0)

MUZZLE_FLASH_DURATION = 0.04
MUZZLE_FLASH_SCALE = 0.05
MUZZLE_FLASH_COLOR = (1.0, 0.9, 0.3, 1)

TRACER_DURATION = 0.05
TRACER_THICKNESS = 2.0
TRACER_COLOR = (1.0, 0.9, 0.3, 1)


class Pistol:
    def __init__(self, game):
        self.game = game
        self.base = game

        self.ammo = MAG_SIZE
        self.cooldown = 0.0
        self.reloading = False

        # 진행 중인 모션 핸들 — 새 모션 시작 시 .finish()로 정리해 점프/충돌 방지
        self._current_recoil = None
        self._current_reload = None
        # ADS 진입/해제 시 권총 위치 lerp 핸들. set_ads/reload 둘 다 finish 로 정리.
        self._current_ads = None

        # 보행 sway state — 누적 위상 + 현재 출력값(목표값을 부드럽게 추종).
        # 절댓값 setPos/setHpr 만 쓰므로 누적 회전 폭주 위험 없음.
        self._sway_time = 0.0
        self._gun_sway_x = 0.0
        self._gun_sway_z = 0.0
        self._arm_sway_p = 0.0
        self._arm_sway_r = 0.0

        self._build_model()
        self._setup_raycast()

    def _build_model(self):
        # 카메라 자식 계층 3단:
        #   np_anchor — player 의 view bob 이 매 프레임 setPos (걷기 시 카메라 카운터-bob).
        #   np_sway   — 본 클래스의 _update_sway 가 ADS-aware 보행 sway 적용 (신규).
        #               별도 노드라 ADS lerp / reload Sequence (self.np 를 조작) 과
        #               충돌하지 않음.
        #   self.np   — 권총 루트. ADS lerp / recoil / reload 가 pos/hpr 을 점유.
        self.np_anchor = self.base.camera.attachNewNode("pistol_bob_anchor")
        self.np_sway = self.np_anchor.attachNewNode("pistol_sway")
        self.np = self.np_sway.attachNewNode("pistol_root")
        self.np.setPos(PISTOL_REST_POS)
        self._rest_pos = Vec3(PISTOL_REST_POS)
        # 카메라 회전에 따라 directional light가 권총을 거의 검정에 가깝게 만드는
        # 경우를 막기 위해 권총만 라이팅을 끄고 setColor 그대로 보이게 한다.
        self.np.setLightOff()

        # 그립 — 안 움직임 (Doom 구도용 1.3배 확대)
        self.grip = self.base.loader.loadModel("models/box")
        self.grip.reparentTo(self.np)
        self.grip.setScale(0.052, 0.065, 0.13)
        self.grip.setPos(-0.026, -0.091, -0.13)
        self.grip.setColor(0.30, 0.30, 0.30, 1)

        # 프레임 — 그립과 슬라이드 이음새, 안 움직임
        self.frame = self.base.loader.loadModel("models/box")
        self.frame.reparentTo(self.np)
        self.frame.setScale(0.058, 0.21, 0.032)
        self.frame.setPos(-0.0293, -0.078, -0.0325)
        self.frame.setColor(0.35, 0.35, 0.35, 1)

        # 슬라이드 — anchor 노드. scale 없음. 보이는 박스는 자식 slide_mesh가 담당.
        self.slide = self.np.attachNewNode("slide")
        self._slide_rest_pos = Vec3(0, 0, 0)
        self.slide.setPos(self._slide_rest_pos)

        slide_mesh = self.base.loader.loadModel("models/box")
        slide_mesh.reparentTo(self.slide)
        slide_mesh.setScale(0.065, 0.26, 0.052)
        slide_mesh.setPos(-0.0325, -0.13, 0.0)
        slide_mesh.setColor(0.55, 0.55, 0.55, 1)

        # 총신 — slide anchor의 자식. 슬라이드 모션과 함께 움직임.
        self.barrel = self.base.loader.loadModel("models/box")
        self.barrel.reparentTo(self.slide)
        self.barrel.setScale(0.026, 0.052, 0.026)
        self.barrel.setPos(0.0195, 0.26, 0.013)
        self.barrel.setColor(0.45, 0.45, 0.45, 1)

        # 머즐 플래시 — barrel의 자식. 슬라이드/총신 모션을 모두 따라감.
        self._muzzle_flash = self.base.loader.loadModel("models/misc/sphere")
        self._muzzle_flash.reparentTo(self.barrel)
        self._muzzle_flash.setPos(BARREL_TIP_LOCAL)
        self._muzzle_flash.setScale(MUZZLE_FLASH_SCALE)
        self._muzzle_flash.setColor(*MUZZLE_FLASH_COLOR)
        self._muzzle_flash.hide()

        # 탄창 — 재장전 시 아래로 빠졌다 돌아옴 (1.3배 확대).
        # 색은 약간 푸른빛 도는 어두운 회색 — 다른 부품과 대비로 낙하가 잘 보이게.
        self.magazine = self.base.loader.loadModel("models/box")
        self.magazine.reparentTo(self.np)
        self.magazine.setScale(0.045, 0.058, 0.091)
        self._mag_rest_pos = Vec3(-0.0228, -0.078, -0.065)
        self.magazine.setPos(self._mag_rest_pos)
        self.magazine.setColor(0.20, 0.22, 0.30, 1)

        # 오른손 — 항상 pistol 자식, 그립을 잡은 자세
        self.right_hand = Hand("right", self.np, self.base)
        self.right_hand.np.setPos(RIGHT_HAND_REST_POS)
        self.right_hand.np.setHpr(*RIGHT_HAND_REST_HPR)

        # 왼손 — 평상시 pistol 자식 (재장전 중에는 camera로 reparent)
        self.left_hand = Hand("left", self.np, self.base)
        self.left_hand.np.setPos(LEFT_HAND_REST_POS)
        self.left_hand.np.setHpr(*LEFT_HAND_REST_HPR)

    def _setup_raycast(self):
        self.traverser = CollisionTraverser("pistol_shoot")
        self.handler = CollisionHandlerQueue()

        cnode = CollisionNode("shoot_ray")
        cnode.addSolid(CollisionRay(0, 0, 0, 0, 1, 0))
        # 환경(HITTABLE_MASK)과 좀비(ZOMBIE_MASK) 둘 다 검출 → 가장 가까운 hit을
        # entry로 받고, PythonTag로 좀비 여부 판정.
        cnode.setFromCollideMask(HITTABLE_MASK | ZOMBIE_MASK)
        cnode.setIntoCollideMask(BitMask32.allOff())

        self.ray_np = self.base.camera.attachNewNode(cnode)
        self.traverser.addCollider(self.ray_np, self.handler)

    def shoot(self):
        if self.reloading or self.cooldown > 0 or self.ammo <= 0:
            return
        self.ammo -= 1
        self.cooldown = COOLDOWN
        self._play_recoil()
        self._flash_muzzle()

        hit_pos, hit_zombie, hit_part = self._raycast_hit()
        if hit_pos is not None:
            cam_pos = self.base.camera.getPos(self.base.render)
            tracer_distance = (hit_pos - cam_pos).length()
            if hit_zombie is not None:
                # 부위별 배율은 take_damage 안에서 적용. 파티클은 부위 카테고리별 양/색.
                hit_zombie.take_damage(BASE_DAMAGE, hit_part=hit_part)
                spawn_hit_particles(self.base, hit_pos, hit_part)
                # 헤드샷은 크로스헤어 아래 데미지 숫자 띄움.
                if hit_part == "head":
                    final_damage = int(round(BASE_DAMAGE * 1.5))
                    self.game.hud.show_headshot_number(final_damage)
            else:
                self._spawn_hit_marker(hit_pos)
        else:
            tracer_distance = MAX_RANGE
        self._spawn_tracer(tracer_distance)

        self.game.hud.update_ammo(self.ammo, MAG_SIZE, False)

    def reload(self):
        if self.reloading or self.ammo == MAG_SIZE:
            return
        # 재장전 시작 시 ADS lerp가 진행 중이면 종료 — np_seq 와 같은 노드를 다투면
        # 마지막 keyframe 값에 따라 권총이 엉뚱한 위치로 튀어버림.
        # player 의 ADS 플래그도 함께 해제해 FOV/감도가 자동으로 평상시로 복귀.
        if self._current_ads is not None:
            self._current_ads.finish()
            self._current_ads = None
        player = getattr(self.base, "player", None)
        if player is not None:
            player.ads_active = False
        self.reloading = True
        self.game.hud.update_ammo(self.ammo, MAG_SIZE, True)
        self._play_reload_anim()
        self.base.taskMgr.doMethodLater(
            RELOAD_TIME, self._finish_reload, "pistol_reload_finish"
        )

    def _finish_reload(self, task):
        self.ammo = MAG_SIZE
        self.reloading = False
        self.game.hud.update_ammo(self.ammo, MAG_SIZE, False)
        # cleanup 은 헬퍼로 위임 — Sequence 끝 Func / abort_reload 와 동일 로직 공유.
        self._reset_left_hand()
        return task.done

    def _reset_left_hand(self):
        """왼손을 pistol 자식으로 되돌리고 정확히 rest pose 로 강제 보정.

        호출 시점:
          1. _finish_reload — 정상 재장전 종료
          2. _play_reload_anim 의 Sequence 끝 Func — 어떤 식으로든 Sequence 가 종료될 때 보장
          3. abort_reload — 외부 인터럽트(피격 등) 시 안전 복귀

        wrtReparentTo 가 월드 좌표를 보존하므로 직후에 명시적으로 setPos/setHpr 재설정 필요.
        """
        self.left_hand.np.wrtReparentTo(self.np)
        self.left_hand.np.setPos(LEFT_HAND_REST_POS)
        self.left_hand.np.setHpr(*LEFT_HAND_REST_HPR)

    def abort_reload(self):
        """외부 인터럽트(피격 등)로 재장전을 안전하게 중단.

        Sequence finish + doMethodLater 타이머 취소 + 왼손 강제 복귀 모두 수행.
        ammo 는 충전하지 않음 — 피격에 따른 자연스러운 패널티 (다시 R 눌러야 함).
        """
        if not self.reloading:
            return
        if self._current_reload is not None:
            # finish() 는 모든 LerpInterval 을 마지막 keyframe 으로 스냅 + 끝 Func 실행.
            self._current_reload.finish()
            self._current_reload = None
        # 2초 후 ammo 자동 충전 타이머 취소 — 안 그러면 맞고도 보상받는 꼴.
        self.base.taskMgr.remove("pistol_reload_finish")
        self.reloading = False
        self._reset_left_hand()
        self.game.hud.update_ammo(self.ammo, MAG_SIZE, False)

    def set_ads(self, active):
        """우클릭 ADS — 권총 루트를 ADS_GUN_POS (중앙) 또는 _rest_pos (우측 hip) 로 lerp.

        재장전 중에는 무시 — 무기 모션이 np 노드를 점유 중이라 충돌 방지.
        진행 중인 ADS lerp 가 있으면 finish 후 새 lerp 시작.
        """
        if active and self.reloading:
            return
        if self._current_ads is not None:
            self._current_ads.finish()
        target = ADS_GUN_POS if active else self._rest_pos
        self._current_ads = LerpPosInterval(self.np, ADS_LERP_TIME, target)
        self._current_ads.start()

    def update(self, dt):
        if self.cooldown > 0:
            self.cooldown -= dt
        self._update_sway(dt)

    def _update_sway(self, dt):
        """ADS-aware 보행 sway — 매 프레임 절댓값 setPos/setHpr.

        설계:
          - 권총 sway: np_sway.setPos (np_anchor 의 view bob, self.np 의 ADS lerp 와
            별도 노드라 충돌 없음).
          - 팔 sway: right_hand/left_hand 의 HPR delta. REST_HPR 절댓값에 sin 기반 delta 더함.

        분기:
          - 이동 중: sway_time 누적, sin 으로 target 계산.
            * ADS  → gun 진폭 8%, arm 진폭 42% (조준선 안정)
            * 비ADS → gun/arm 모두 100% (기존 손맛 유지)
            * Shift → 진폭 ×1.7, 주파수 ×1.5
          - 정지: target=0, 누적 시간 멈춤 (블렌딩으로 부드럽게 수렴).
          - 재장전 중: 모든 target=0 (왼손 reparent + Sequence 모션 보호).

        팔 sway 는 right_hand REST 절댓값 (HPR=15,-25,0) 에 (0, sway_p, sway_r) 더해
        절댓값으로 setHpr → 누적 회전 폭주 없음. 좌우 손은 위상 동일 (양손 그립 흔들림).
        """
        player = getattr(self.base, "player", None)
        if player is None:
            return

        if self.reloading:
            # 재장전 모션이 권총/왼손을 점유. sway 정지 + 0 으로 수렴.
            target_gun_x = target_gun_z = 0.0
            target_arm_p = target_arm_r = 0.0
        else:
            is_moving = bool(getattr(player, "is_moving", False))
            is_running = bool(getattr(player, "is_running", False))
            is_ads = bool(getattr(player, "ads_active", False))

            if is_moving:
                amp_mult = RUN_AMPLITUDE_MULT if is_running else 1.0
                freq_mult = RUN_FREQ_MULT if is_running else 1.0
                base_amp = WALK_SWAY_AMPLITUDE * amp_mult
                freq = WALK_SWAY_FREQ * freq_mult
                # 위상 진행 — 정지 시엔 누적 안 함 (재시작 시 톡 튀지 않게 sway_time
                # 은 그대로 두고 target 만 0 으로 수렴 → 블렌드가 끄는 역할).
                self._sway_time += dt * freq * 2.0 * math.pi

                if is_ads:
                    gun_amp = base_amp * ADS_GUN_SWAY_MULT
                    arm_amp = base_amp * ADS_ARM_SWAY_MULT
                else:
                    gun_amp = base_amp
                    arm_amp = base_amp

                s = math.sin(self._sway_time)
                s2 = math.sin(self._sway_time * 2.0)
                target_gun_x = s * gun_amp * GUN_SWAY_X_SCALE
                target_gun_z = s2 * gun_amp * GUN_SWAY_Z_SCALE
                target_arm_p = s * arm_amp * ARM_SWAY_P_DEG
                target_arm_r = s2 * arm_amp * ARM_SWAY_R_DEG
            else:
                target_gun_x = target_gun_z = 0.0
                target_arm_p = target_arm_r = 0.0

        # 지수 블렌드 — 프레임률 무관한 부드러운 수렴. dt 가 커도 발산 안 함.
        blend = 1.0 - math.exp(-SWAY_BLEND_RATE * dt)
        self._gun_sway_x += (target_gun_x - self._gun_sway_x) * blend
        self._gun_sway_z += (target_gun_z - self._gun_sway_z) * blend
        self._arm_sway_p += (target_arm_p - self._arm_sway_p) * blend
        self._arm_sway_r += (target_arm_r - self._arm_sway_r) * blend

        # 권총 sway 적용 — np_sway 는 ADS lerp / reload / recoil 과 충돌 없음.
        self.np_sway.setPos(self._gun_sway_x, 0, self._gun_sway_z)

        # 오른손 — 재장전 중에도 pistol 자식이라 안전. REST 절댓값 + sway delta.
        rh, rp, rr = RIGHT_HAND_REST_HPR
        self.right_hand.np.setHpr(rh, rp + self._arm_sway_p, rr + self._arm_sway_r)

        # 왼손 — 재장전 중에는 카메라 자식으로 reparent 되어 Sequence 가 HPR 점유.
        # 그 때는 sway 건너뜀 (위 self.reloading 분기에서 target 은 0 이지만
        # 명시적으로 한 번 더 가드해서 마지막 keyframe 을 안 덮어쓰게).
        if not self.reloading:
            lh, lp, lr = LEFT_HAND_REST_HPR
            self.left_hand.np.setHpr(lh, lp + self._arm_sway_p, lr + self._arm_sway_r)

    def _raycast_hit(self):
        """(hit_pos, zombie_or_None, hit_part_or_None) 반환. miss/범위 초과면 (None, None, None).

        부위별 충돌 노드에 "zombie"/"hit_part" 두 태그가 같이 박혀 있어서
        hit_np.getNetPythonTag 로 둘 다 즉시 잡힘.
        """
        self.traverser.traverse(self.base.render)
        if self.handler.getNumEntries() == 0:
            return None, None, None
        self.handler.sortEntries()
        entry = self.handler.getEntry(0)
        hit_pos = entry.getSurfacePoint(self.base.render)
        cam_pos = self.base.camera.getPos(self.base.render)
        if (hit_pos - cam_pos).length() > MAX_RANGE:
            return None, None, None
        zombie, hit_part = _find_zombie_and_part(entry)
        return hit_pos, zombie, hit_part

    def _spawn_hit_marker(self, world_pos):
        marker = self.base.loader.loadModel("models/misc/sphere")
        marker.reparentTo(self.base.render)
        marker.setPos(world_pos)
        marker.setScale(HIT_MARKER_SCALE)
        marker.setColor(1, 0, 0, 1)

        def _remove(task, m=marker):
            m.removeNode()
            return task.done

        self.base.taskMgr.doMethodLater(
            HIT_MARKER_LIFETIME, _remove, "hit_marker_remove"
        )

    def _flash_muzzle(self):
        self._muzzle_flash.show()
        self.base.taskMgr.doMethodLater(
            MUZZLE_FLASH_DURATION, self._hide_muzzle_flash, "muzzle_flash_hide"
        )

    def _hide_muzzle_flash(self, task):
        self._muzzle_flash.hide()
        return task.done

    def _spawn_tracer(self, distance):
        """카메라 로컬 공간에 그려서 시점 이동에 따른 잔상 없게.

        시작점은 머즐 플래시(=총신 끝)를 카메라 좌표계로 변환한 위치.
        BARREL_TIP_LOCAL은 barrel-local 값이라 그대로 쓰면 안 됨.
        끝점은 (0, distance, 0) — raycast가 카메라 정면이므로.
        """
        segs = LineSegs("tracer")
        segs.setColor(*TRACER_COLOR)
        segs.setThickness(TRACER_THICKNESS)
        segs.moveTo(self._muzzle_flash.getPos(self.base.camera))
        segs.drawTo(Vec3(0, distance, 0))
        tracer_np = self.base.camera.attachNewNode(segs.create())
        tracer_np.setLightOff()

        def _remove(task, n=tracer_np):
            n.removeNode()
            return task.done

        self.base.taskMgr.doMethodLater(TRACER_DURATION, _remove, "tracer_remove")

    def _play_recoil(self):
        """발사 반동: 슬라이드만 뒤로, 권총 전체는 살짝 위로 튕김 (병렬).

        왼손은 self.np의 자식이라 권총의 pitch +2° 튕김을 함께 따라감
        (별도 모션 없음 — spec의 옵션 A).
        """
        if self._current_recoil is not None:
            self._current_recoil.finish()

        slide_back = self._slide_rest_pos + SLIDE_RECOIL_OFFSET
        slide_seq = Sequence(
            LerpPosInterval(self.slide, 0.04, slide_back),
            LerpPosInterval(self.slide, 0.06, self._slide_rest_pos),
        )
        np_pitch_up = (0, RECOIL_PITCH_DEG, 0)
        np_pitch_rest = (0, 0, 0)
        root_seq = Sequence(
            LerpHprInterval(self.np, 0.05, np_pitch_up),
            LerpHprInterval(self.np, 0.10, np_pitch_rest),
        )

        self._current_recoil = Parallel(slide_seq, root_seq)
        self._current_recoil.start()

    def _play_reload_anim(self):
        """재장전 안무 — 검사 자세(inspect pose) 기반 (총 2.0초).

        핵심 변경: 권총을 아래로 내리는 대신 카메라 안쪽으로 끌어와 위로 들어 올려
        탄창 분리/장전 동작이 화면 중앙에서 다 보이게 한다.

          시간        self.np                magazine       slide        left_hand (camera-local)
          ----------  ---------------------  -------------  -----------  ----------------------------
          0.00~0.30   검사 자세로 끌어옴                                  (대기, REST 유지)
          0.30~0.55                                                       탄창 위치로 이동
          0.55~0.85                          아래로 -0.30                탄창과 함께 아래로
          0.85~1.15                          (빠진 상태 유지)             더 아래로 (화면 밖)
          1.15~1.40                                                       다시 올라옴
          1.40~1.65                          제자리 복귀                  탄창 꽂아넣음
          1.65~1.80                                                       슬라이드 위로 + 회전
          1.80~1.92                                         뒤로 -0.06   슬라이드 당김
          1.92~2.00   원자세 복귀                            제자리 복귀  원자세 복귀

        왼손 좌표는 직접 camera-local로 작성 (이전 cam(pl) 변환 패턴 폐기).
        검사 자세에서 권총이 camera-local (0.15, 0.70, -0.12)에 위치하므로
        왼손도 그 근처 Y≈0.5~0.6 범위에서 움직임.

        마지막 keyframe만 PISTOL_REST_POS + LEFT_HAND_REST_POS로 — pistol이 rest로
        돌아간 시점의 camera-local 위치 (wrtReparentTo 복귀 시 jump 최소화).
        """
        if self._current_recoil is not None:
            self._current_recoil.finish()
        if self._current_reload is not None:
            self._current_reload.finish()

        # 왼손을 camera 자식으로 (월드 변환 보존)
        self.left_hand.np.wrtReparentTo(self.base.camera)

        # ----- self.np (권총: 검사 자세 → 복귀) -----
        np_inspect_pos = self._rest_pos + Vec3(-0.10, -0.20, 0.08)
        np_inspect_hpr = (-10, -15, 25)
        np_rest_hpr = (0, 0, 0)
        np_seq = Sequence(
            Parallel(
                LerpPosInterval(self.np, 0.30, np_inspect_pos),
                LerpHprInterval(self.np, 0.30, np_inspect_hpr),
            ),
            Wait(1.62),  # 0.30 ~ 1.92
            Parallel(
                LerpPosInterval(self.np, 0.08, self._rest_pos),
                LerpHprInterval(self.np, 0.08, np_rest_hpr),
            ),
        )

        # ----- magazine -----
        mag_down = self._mag_rest_pos + MAG_DROP_OFFSET
        mag_seq = Sequence(
            Wait(0.55),
            LerpPosInterval(self.magazine, 0.30, mag_down),  # 0.55 ~ 0.85
            Wait(0.55),                                       # 0.85 ~ 1.40
            LerpPosInterval(self.magazine, 0.25, self._mag_rest_pos),  # 1.40 ~ 1.65
        )

        # ----- slide -----
        slide_back = self._slide_rest_pos + Vec3(0, -0.06, 0)  # 재장전 시 슬라이드 후퇴 (recoil보다 큼)
        slide_seq = Sequence(
            Wait(1.80),
            LerpPosInterval(self.slide, 0.12, slide_back),               # 1.80 ~ 1.92
            LerpPosInterval(self.slide, 0.08, self._slide_rest_pos),     # 1.92 ~ 2.00
        )

        # ----- left hand (camera-local 좌표) -----
        L = self.left_hand.np
        left_seq = Sequence(
            # 0.00 ~ 0.30 권총만 검사 자세로. 왼손은 그대로 대기.
            Wait(0.30),
            # 0.30 ~ 0.55 탄창 위치로
            LerpPosInterval(L, 0.25, Vec3(-0.05, 0.55, -0.15)),
            # 0.55 ~ 0.85 탄창과 함께 아래로
            LerpPosInterval(L, 0.30, Vec3(-0.05, 0.55, -0.40)),
            # 0.85 ~ 1.15 더 아래로 (화면 밖, 새 탄창 가지러)
            LerpPosInterval(L, 0.30, Vec3(-0.08, 0.50, -0.55)),
            # 1.15 ~ 1.40 다시 올라옴
            LerpPosInterval(L, 0.25, Vec3(-0.05, 0.55, -0.40)),
            # 1.40 ~ 1.65 탄창 꽂아넣음
            LerpPosInterval(L, 0.25, Vec3(-0.05, 0.55, -0.15)),
            # 1.65 ~ 1.80 슬라이드 위로 + 회전
            Parallel(
                LerpPosInterval(L, 0.15, Vec3(-0.08, 0.60, 0.0)),
                LerpHprInterval(L, 0.15, (0, 0, 45)),
            ),
            # 1.80 ~ 1.92 슬라이드 잡고 뒤로
            LerpPosInterval(L, 0.12, Vec3(-0.08, 0.50, 0.0)),
            # 1.92 ~ 2.00 원자세로 (camera-local에서 pistol rest 위치)
            Parallel(
                LerpPosInterval(L, 0.08, PISTOL_REST_POS + LEFT_HAND_REST_POS),
                LerpHprInterval(L, 0.08, LEFT_HAND_REST_HPR),
            ),
        )

        # Parallel 을 Sequence 로 감싸 마지막 Func 로 cleanup 보장.
        # 정상 종료/finish() 양쪽 모두에서 Func 가 실행되어 왼손이 엉뚱한 부모/위치에
        # 박제되는 버그를 막는다. _finish_reload 와 동일 작업이라 중복 실행돼도 idempotent.
        self._current_reload = Sequence(
            Parallel(np_seq, mag_seq, slide_seq, left_seq),
            Func(self._reset_left_hand),
        )
        self._current_reload.start()
