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


EYE_HEIGHT = 1.7
WALK_SPEED = 8.0
RUN_MULTIPLIER = 1.5
MOUSE_SENSITIVITY = 0.15
GRAVITY = 20.0
JUMP_VELOCITY = 7.5
SPAWN_POS = Vec3(0, 0, 2)
MAX_DT = 1.0 / 30.0
GROUND_SCAN_HEIGHT = 200.0
GROUND_EPSILON = 0.01

# View bob — 걷기/달리기 시 카메라가 흔들리는 정도와 주기.
# 주파수는 이전 다운 상태 유지 (사용자가 만족), 진폭은 키워서 흔들림이 더 보이게.
WALK_BOB_AMPLITUDE_Z = 0.06
WALK_BOB_AMPLITUDE_X = 0.035
WALK_BOB_FREQUENCY = 2.8       # 5.5 → 2.8: 너무 잔망스러워서 사람 걸음 속도 (≈2~3 Hz)로
RUN_BOB_AMPLITUDE_Z = 0.08
RUN_BOB_AMPLITUDE_X = 0.05
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

        self.node = base.render.attachNewNode("player")
        self.node.setPos(SPAWN_POS)

        base.camera.reparentTo(self.node)
        base.camera.setPos(0, 0, EYE_HEIGHT)
        base.camera.setHpr(0, 0, 0)

        base.disableMouse()
        self._capture_mouse()

        self.yaw = 0.0
        self.pitch = 0.0
        self._first_mouse = True

        self.vz = 0.0
        self.on_ground = False

        # View bob 상태
        self._bob_phase = 0.0
        self._bob_intensity = 0.0

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
        dt = _clock.getDt()
        if dt > MAX_DT:
            dt = MAX_DT
        self._update_mouse_look()
        self._update_movement(dt)
        self._update_gravity_and_ground(dt)
        self._update_view_bob(dt)
        return task.cont

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
        keys = getattr(self, "_last_keys", None) or {}
        has_input = bool(keys.get("w") or keys.get("a") or keys.get("s") or keys.get("d"))
        moving = has_input and self.on_ground
        running = moving and bool(keys.get("shift", False))

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
        self.yaw -= dx * MOUSE_SENSITIVITY
        self.pitch -= dy * MOUSE_SENSITIVITY
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
        if forward == 0 and strafe == 0:
            return

        local = Vec3(strafe, forward, 0)
        local.normalize()
        speed = WALK_SPEED * (RUN_MULTIPLIER if keys["shift"] else 1.0)

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
