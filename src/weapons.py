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

from direct.interval.IntervalGlobal import (
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

        self._build_model()
        self._setup_raycast()

    def _build_model(self):
        # View bob 적용용 anchor 노드. player가 매 프레임 이 노드의 pos를 흔들어
        # 권총이 카메라와 별개로 화면 안에서 살짝 떨림 (걷기/달리기 시 손맛).
        # pistol_root는 anchor의 자식이라 reload/recoil 애니메이션이 anchor의
        # 좌표계에서 동작 → bob과 애니메이션이 겹쳐도 충돌 없음.
        self.np_anchor = self.base.camera.attachNewNode("pistol_bob_anchor")
        self.np = self.np_anchor.attachNewNode("pistol_root")
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

        # 왼손을 pistol 자식으로 되돌리고 정확히 rest pose로 보정.
        # Sequence의 마지막 keyframe에 작은 오차가 있을 수 있어 명시적으로 한 번 더 set.
        self.left_hand.np.wrtReparentTo(self.np)
        self.left_hand.np.setPos(LEFT_HAND_REST_POS)
        self.left_hand.np.setHpr(*LEFT_HAND_REST_HPR)
        return task.done

    def update(self, dt):
        if self.cooldown > 0:
            self.cooldown -= dt

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

        self._current_reload = Parallel(np_seq, mag_seq, slide_seq, left_seq)
        self._current_reload.start()
