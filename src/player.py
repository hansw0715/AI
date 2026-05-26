"""1인칭 플레이어 컨트롤러.

구조:
  - self.node  : 플레이어 루트. yaw(H)와 위치를 가짐
  - base.camera: self.node의 자식. 눈높이에 위치하고 pitch(P)만 가짐
이렇게 분리해야 위/아래를 봐도 이동 방향이 평면에 유지된다.

View bob:
  걷기/달리기 중에는 카메라 자체를 살짝 위아래(Z) + 좌우(X)로 흔든다.
  카메라가 흔들리면 그 자식인 권총/양손도 같이 따라가서 1인칭 이동감이 살아남.
  player.node는 흔들지 않으므로 충돌/물리 로직에는 영향 없음.
"""

import math

from panda3d.core import (
    ClockObject,
    CollisionHandlerQueue,
    CollisionTraverser,
    KeyboardButton,
    Vec3,
    WindowProperties,
)

from .physics import make_ground_ray


# 1.7 → 1.55: 1.7m 는 사람 정수리 높이라 1인칭 시점에서 팔/총이 화면을 너무 많이
# 차지함. 평균 한국 성인 눈높이(1.55~1.6m) 로 낮춰 1인칭 구도를 더 자연스럽게.
EYE_HEIGHT = 1.55
WALK_SPEED = 8.0
RUN_MULTIPLIER = 1.5
# 이전 기본값 0.15는 너무 민감해 무빙 중 시점이 휙휙 돌아간다는 피드백.
# 절반 수준(0.075)으로 낮춰 정밀 사격이 가능하게 함. 설정 메뉴 슬라이더로 0.025 ~ 0.5
# 범위에서 런타임 조절 가능.
MOUSE_SENSITIVITY = 0.075
GRAVITY = 20.0
JUMP_VELOCITY = 7.5
SPAWN_POS = Vec3(0, 0, 2)
MAX_DT = 1.0 / 30.0
GROUND_SCAN_HEIGHT = 200.0
GROUND_EPSILON = 0.01

# ADS (Aim Down Sights) — 마우스 우클릭으로 조준 모드 진입 ---------
# 카메라 FOV 를 좁히고(시각적 줌) + 권총을 화면 중앙으로 이동(가늠쇠 조준) + 마우스
# 민감도 절반으로 정밀 조준 가능. 권총 이동은 weapons.Pistol.set_ads 에서 처리.
ADS_DEFAULT_FOV = 70.0        # 평상시 시야각 (도)
ADS_ZOOM_FOV = 50.0           # 조준 시 시야각 (도) — 약 1.4배 줌 (40→50 으로 완화)
ADS_LERP_TIME = 0.12          # FOV 전환 시간 (초) — 권총 이동과 동기화
ADS_SENSITIVITY_MULT = 0.5    # 조준 중 마우스 민감도 배율

# 체력 / 피격 비네트 -----------------------------------------------
PLAYER_MAX_HP = 100
DAMAGE_FLASH_PEAK_ALPHA = 0.55     # 비네트 최대 알파 (피격 직후)
DAMAGE_FLASH_FADE_SEC = 0.8        # 비네트 1→0 페이드 시간

# View bob — 걷기/달리기 시 카메라가 흔들리는 정도와 주기.
# 주파수는 이전 다운 상태 유지 (사용자가 만족), 진폭은 키워서 흔들림이 더 보이게.
WALK_BOB_AMPLITUDE_Z = 0.025   # 0.06 → 0.025: 카메라 상하 흔들림 ~42%로
WALK_BOB_AMPLITUDE_X = 0.015   # 0.035 → 0.015: 카메라 좌우 흔들림 ~43%로
WALK_BOB_FREQUENCY = 2.8       # 5.5 → 2.8: 너무 잔망스러워서 사람 걸음 속도 (≈2~3 Hz)로
RUN_BOB_AMPLITUDE_Z = 0.035    # 0.08 → 0.035: 달리기 상하 ~44%로
RUN_BOB_AMPLITUDE_X = 0.022    # 0.05 → 0.022: 달리기 좌우 ~44%로
RUN_BOB_FREQUENCY = 4.0        # 7.0 → 4.0: 달리기 페이스에 맞춤
BOB_BLEND_RATE = 8.0           # 보빙 fade in/out 속도

# 권총 anchor를 카메라 bob의 몇 배로 움직일지 (sin 위상 동일).
#  0   = 카메라와 lockstep → 화면 안에서 권총 정지 (배경만 흔들림)
# -1   = 권총이 월드에 고정 → 화면 안에서 권총이 배경과 같은 진폭으로 흔들림 (자연스러움)
# +1   = 권총이 월드에서 2배 진폭으로 흔들림 (화면 안에서 배경 반대 방향 — 어색함)
# -0.5 = 권총이 배경의 절반 정도 흔들림 (중간)
GUN_BOB_RATIO = -1.0

_clock = ClockObject.getGlobalClock()


class PlayerController:
    def __init__(self, base):
        self.base = base

        # 마우스 감도를 인스턴스 변수로 — 설정 메뉴에서 런타임에 변경 가능.
        self.sensitivity = MOUSE_SENSITIVITY
        # 보행 속도도 인스턴스로 — 레벨업 "이동 속도" 특성이 런타임 곱연산 적용.
        # 모듈 상수 WALK_SPEED 는 초기값 source 로만 남음.
        self.walk_speed = WALK_SPEED

        # ADS 상태 — set_ads(True/False)로 토글. 매 프레임 _update_ads_fov가
        # ads_current_fov를 ads_target_fov로 ADS_LERP_TIME에 맞춰 보간.
        # camLens 초기 FOV도 ADS_DEFAULT_FOV로 설정해 시작부터 70도 시야 보장.
        self.ads_active = False
        self.ads_current_fov = ADS_DEFAULT_FOV
        base.camLens.setFov(ADS_DEFAULT_FOV)

        self.node = base.render.attachNewNode("player")
        self.node.setPos(SPAWN_POS)

        base.camera.reparentTo(self.node)
        base.camera.setPos(0, 0, EYE_HEIGHT)
        base.camera.setHpr(0, 0, 0)

        base.disableMouse()
        # 마우스 캡처는 시작 화면에서 Start 클릭 시 main._begin_game 가 호출.
        # 부팅 직후엔 커서가 보여서 메뉴 버튼이 클릭 가능해야 함.

        self.yaw = 0.0
        self.pitch = 0.0
        self._first_mouse = True

        self.vz = 0.0
        self.on_ground = False

        # 이동/달리기 상태 — weapons.py 의 _update_sway 등 외부 모션 시스템이 참조.
        # _update_movement 가 매 프레임 갱신. 키 입력 + on_ground 둘 다 충족해야 True.
        self.is_moving = False
        self.is_running = False

        # View bob 상태
        self._bob_phase = 0.0
        self._bob_intensity = 0.0

        # 체력 / 피격 비네트 — HUD 갱신은 HUD 생성 후에 zombie.take_damage에서 진행.
        self.max_hp = PLAYER_MAX_HP
        self.hp = self.max_hp
        self._damage_flash_alpha = 0.0

        self.traverser = CollisionTraverser("player_traverser")
        self.ground_handler = CollisionHandlerQueue()
        self.ground_ray_np = make_ground_ray(
            self.node, self.traverser, self.ground_handler,
            origin_z=GROUND_SCAN_HEIGHT,
        )

        # 스폰 직후 즉시 지면 위로 스냅 — 첫 프레임 dt 폭주로 인한 터널링 방지
        gz = self._query_ground_z()
        if gz is not None:
            self.node.setZ(gz + GROUND_EPSILON)
            self.on_ground = True

        base.taskMgr.add(self.update, "player_update")

    def _capture_mouse(self):
        props = WindowProperties()
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_relative)
        self.base.win.requestProperties(props)

    def update(self, task):
        # 일시정지/시작화면/레벨업 카드 중에는 마우스룩/이동/중력/bob 모두 정지.
        # _first_mouse 리셋은 resume 시 main._toggle_pause / _begin_game / LevelUpScreen
        # 카드 클릭 콜백에서 처리.
        # ADS FOV 는 그래도 진행 — 멈추면 메뉴 들어갈 때 FOV 가 어색하게 박제됨.
        # `started` 는 시작 화면이 떠 있을 때만 False. 기본값 True 로 fallback (테스트 호환).
        if (not getattr(self.base, "started", True)
                or getattr(self.base, "paused", False)
                or getattr(self.base, "level_up_active", False)):
            self._update_ads_fov(_clock.getDt())
            return task.cont
        dt = _clock.getDt()
        if dt > MAX_DT:
            dt = MAX_DT
        self._update_mouse_look()
        self._update_movement(dt)
        self._update_gravity_and_ground(dt)
        self._update_view_bob(dt)
        self._update_damage_flash(dt)
        self._update_ads_fov(dt)
        return task.cont

    def set_ads(self, active):
        """우클릭 누르면 active=True, 떼면 False. 일시정지/재장전 중에는 무시.

        FOV 와 민감도는 본 클래스에서, 권총 위치 lerp 는 weapons.Pistol.set_ads
        에 위임.
        """
        if getattr(self.base, "paused", False):
            # 일시정지 중 누른 우클릭은 메뉴 클릭 의도일 가능성이 높으므로 ADS 무시.
            return
        pistol = getattr(self.base, "pistol", None)
        # 재장전 중 ADS 진입 금지 — 권총 모션 충돌 방지.
        if active and pistol is not None and pistol.reloading:
            return
        self.ads_active = bool(active)
        if pistol is not None:
            pistol.set_ads(active)

    def _update_ads_fov(self, dt):
        """ads_current_fov 를 target FOV 로 ADS_LERP_TIME 에 맞춰 선형 보간.

        target 에 0.01도 이내로 접근하면 정확한 target 값으로 스냅 — float 누적 오차 방지.
        """
        target_fov = ADS_ZOOM_FOV if self.ads_active else ADS_DEFAULT_FOV
        if abs(self.ads_current_fov - target_fov) < 0.01:
            if self.ads_current_fov != target_fov:
                self.ads_current_fov = target_fov
                self.base.camLens.setFov(target_fov)
            return
        # ADS_LERP_TIME 동안 (DEFAULT - ZOOM) 만큼 변화하는 속도.
        delta_per_sec = (ADS_DEFAULT_FOV - ADS_ZOOM_FOV) / ADS_LERP_TIME
        if self.ads_current_fov > target_fov:
            self.ads_current_fov = max(
                target_fov, self.ads_current_fov - delta_per_sec * dt
            )
        else:
            self.ads_current_fov = min(
                target_fov, self.ads_current_fov + delta_per_sec * dt
            )
        self.base.camLens.setFov(self.ads_current_fov)

    def take_damage(self, amount, source=None):
        """좀비 _enter_strike에서 호출됨. hp가 0 이하면 추가 데미지 무시 (게임오버는 다음 단계)."""
        if self.hp <= 0:
            return
        self.hp = max(0, self.hp - amount)
        self._damage_flash_alpha = DAMAGE_FLASH_PEAK_ALPHA
        self.base.hud.set_player_hp(self.hp, self.max_hp)
        self.base.hud.set_damage_flash(self._damage_flash_alpha)
        # 피격 시 재장전 중이면 모션을 안전하게 중단 — 왼손이 카메라 자식으로 남아
        # 엉뚱한 위치에 박제되는 버그 방지. ammo 는 그대로 두어 패널티로 작용.
        pistol = getattr(self.base, "pistol", None)
        if pistol is not None and pistol.reloading:
            pistol.abort_reload()

    def _update_damage_flash(self, dt):
        if self._damage_flash_alpha <= 0.0:
            return
        fade_rate = DAMAGE_FLASH_PEAK_ALPHA / DAMAGE_FLASH_FADE_SEC
        self._damage_flash_alpha = max(0.0, self._damage_flash_alpha - dt * fade_rate)
        self.base.hud.set_damage_flash(self._damage_flash_alpha)

    def _query_ground_z(self):
        """플레이어 XY 위치 바로 아래의 지면 Z를 반환. 없으면 None."""
        self.traverser.traverse(self.base.render)
        if self.ground_handler.getNumEntries() == 0:
            return None
        self.ground_handler.sortEntries()
        return self.ground_handler.getEntry(0).getSurfacePoint(self.base.render).z

    def _update_view_bob(self, dt):
        """걷기/달리기 시 카메라 흔들기. 권총/양손은 camera 자식이라 자동으로 따라감.

        phase는 항상 진행시키고, intensity로 fade in/out — 멈출 때/시작할 때 자연스럽게.
        - Z (위아래): sin(phase) — 한 발걸음마다 한 번 올라갔다 내려옴
        - X (좌우): sin(phase / 2) — 두 발걸음마다 한 번 좌우 → 자연스런 figure-8
        """
        # _update_movement 에서 이미 갱신된 플래그 재사용 — 중복 계산 제거.
        moving = self.is_moving
        running = self.is_running

        # intensity 부드러운 fade — 멈춰도 갑자기 0으로 떨어지지 않고 잔잔히 잦아듦
        target_intensity = 1.0 if moving else 0.0
        blend = 1.0 - math.exp(-BOB_BLEND_RATE * dt)
        self._bob_intensity += (target_intensity - self._bob_intensity) * blend

        if running:
            amp_z = RUN_BOB_AMPLITUDE_Z
            amp_x = RUN_BOB_AMPLITUDE_X
            freq = RUN_BOB_FREQUENCY
        else:
            amp_z = WALK_BOB_AMPLITUDE_Z
            amp_x = WALK_BOB_AMPLITUDE_X
            freq = WALK_BOB_FREQUENCY

        # phase는 [0, 4π)로 클램프해 float 정밀도 문제 방지 (sin(phase/2)가 4π 주기라서)
        self._bob_phase = (self._bob_phase + 2 * math.pi * freq * dt) % (4 * math.pi)

        bob_z = self._bob_intensity * amp_z * math.sin(self._bob_phase)
        bob_x = self._bob_intensity * amp_x * math.sin(self._bob_phase / 2)

        self.base.camera.setPos(bob_x, 0, EYE_HEIGHT + bob_z)

        # 권총 bob — pistol bob anchor에 camera bob과 같은 위상의 오프셋 적용.
        # GUN_BOB_RATIO=-1이면 anchor가 camera bob을 정확히 상쇄해
        # 권총은 월드 좌표에서 정지, 화면 안에서는 배경과 동일 진폭으로 흔들림 (자연스러움).
        pistol = getattr(self.base, "pistol", None)
        if pistol is not None and hasattr(pistol, "np_anchor"):
            gun_z = self._bob_intensity * amp_z * GUN_BOB_RATIO * math.sin(self._bob_phase)
            gun_x = self._bob_intensity * amp_x * GUN_BOB_RATIO * math.sin(self._bob_phase / 2)
            pistol.np_anchor.setPos(gun_x, 0, gun_z)

    def _update_mouse_look(self):
        if not self.base.mouseWatcherNode.hasMouse():
            return
        md = self.base.win.getPointer(0)
        x, y = md.getX(), md.getY()
        cx = self.base.win.getXSize() // 2
        cy = self.base.win.getYSize() // 2
        if not self.base.win.movePointer(0, cx, cy):
            return
        if self._first_mouse:
            self._first_mouse = False
            return
        dx = x - cx
        dy = y - cy
        # ADS 중에는 정밀 조준이 가능하도록 민감도 절반 적용.
        sens = self.sensitivity * (ADS_SENSITIVITY_MULT if self.ads_active else 1.0)
        self.yaw -= dx * sens
        self.pitch -= dy * sens
        if self.pitch > 89.0:
            self.pitch = 89.0
        elif self.pitch < -89.0:
            self.pitch = -89.0
        self.node.setH(self.yaw)
        self.base.camera.setP(self.pitch)

    def _read_keys(self):
        is_down = self.base.mouseWatcherNode.is_button_down
        return {
            "w": is_down(KeyboardButton.ascii_key("w")),
            "a": is_down(KeyboardButton.ascii_key("a")),
            "s": is_down(KeyboardButton.ascii_key("s")),
            "d": is_down(KeyboardButton.ascii_key("d")),
            "shift": is_down(KeyboardButton.shift()),
            "space": is_down(KeyboardButton.space()),
        }

    def _update_movement(self, dt):
        keys = self._read_keys()
        self._last_keys = keys

        forward = (1 if keys["w"] else 0) - (1 if keys["s"] else 0)
        strafe = (1 if keys["d"] else 0) - (1 if keys["a"] else 0)

        # 이동/달리기 플래그 갱신 — w+s 처럼 상쇄되어도 키는 눌린 상태이므로
        # has_input 은 키 기준으로 판정 (sway 모션이 "걸을 의지"를 반영하도록).
        has_input = bool(keys["w"] or keys["a"] or keys["s"] or keys["d"])
        self.is_moving = has_input and self.on_ground
        self.is_running = self.is_moving and bool(keys["shift"])

        if forward == 0 and strafe == 0:
            return

        local = Vec3(strafe, forward, 0)
        local.normalize()
        speed = self.walk_speed * (RUN_MULTIPLIER if keys["shift"] else 1.0)

        move = self.node.getQuat(self.base.render).xform(local) * (speed * dt)
        move.z = 0
        self.node.setPos(self.node.getPos() + move)

    def _update_gravity_and_ground(self, dt):
        keys = getattr(self, "_last_keys", None) or self._read_keys()

        if keys["space"] and self.on_ground:
            self.vz = JUMP_VELOCITY
            self.on_ground = False

        self.vz -= GRAVITY * dt
        self.node.setZ(self.node.getZ() + self.vz * dt)

        ground_z = self._query_ground_z()
        if ground_z is None:
            self.on_ground = False
            return
        if self.node.getZ() <= ground_z:
            self.node.setZ(ground_z)
            self.vz = 0.0
            self.on_ground = True
        else:
            self.on_ground = False
