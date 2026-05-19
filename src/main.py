"""FPS 게임 진입점.

실행:
  - 프로젝트 루트에서 `python -m src.main`
  - 또는 `python src/main.py`  (아래 부트스트랩이 sys.path와 __package__를 보정)
"""

# `python src/main.py`로 직접 실행 시, src의 부모가 sys.path에 없어서
# 상대 임포트가 깨지므로 부트스트랩으로 보정한다.
if __name__ == "__main__" and __package__ in (None, ""):
    import os
    import sys

    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    __package__ = "src"

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight,
    ClockObject,
    DirectionalLight,
    Vec3,
    Vec4,
    WindowProperties,
)

from .physics import GROUND_MASK, HITTABLE_MASK
from .player import PlayerController
from .settings_menu import SettingsMenu
from .ui import HUD
from .weapons import Pistol
from .zombie import ZombieManager


_clock = ClockObject.getGlobalClock()


# 사람 키(1.7m) 기준으로 자연스러워 보이는 환경 스케일.
# 너무 작거나 어색하면 0.05 ~ 0.15 범위에서 튜닝.
ENVIRONMENT_SCALE = 0.05
# 원래 framing은 setScale(0.25) + setPos(-8, 42, 0) 기준이었으므로,
# 스케일을 줄일 때 오프셋도 같은 비율로 축소해야 플레이어 스폰 XY(0,0)가
# 지형 위에 남는다 (안 그러면 첫 ground snap이 실패해 다시 무한낙하).
ENVIRONMENT_POS = Vec3(-8, 42, 0) * (ENVIRONMENT_SCALE / 0.25)


class FPSGame(ShowBase):
    def __init__(self):
        super().__init__()

        # 1인칭 무기 모델은 카메라에서 0.5m 부근에 부착되는데, 기본 near plane이
        # 1.0m라 무기가 통째로 클립됨. 표준 FPS 관행대로 near를 충분히 작게.
        self.camLens.setNear(0.05)

        self.scene = self.loader.loadModel("models/environment")
        self.scene.reparentTo(self.render)
        self.scene.setScale(ENVIRONMENT_SCALE)
        self.scene.setPos(ENVIRONMENT_POS)
        self.scene.setCollideMask(GROUND_MASK | HITTABLE_MASK)
        # 잎/풀 등 single-sided 폴리곤의 뒷면도 그리도록 양면 렌더링 활성화
        self.scene.setTwoSided(True)
        # 1단계 좀비 테스트 — 바닥 빼고 다 제거해서 좀비 시인성 확보.
        # 나무/대나무/바위/잎/실린더는 다음 단계에서 다시 추가.
        # Ground (small, Z≈0)와 Ground01 (large, Z≈-0.28) 두 메시만 남김.
        _KEEP_NAMES = {"Ground", "Ground01"}
        for child in list(self.scene.getChildren()):
            if child.getName() not in _KEEP_NAMES:
                child.removeNode()

        ambient = AmbientLight("ambient")
        ambient.setColor(Vec4(0.4, 0.4, 0.4, 1))
        self.render.setLight(self.render.attachNewNode(ambient))

        directional = DirectionalLight("directional")
        directional.setColor(Vec4(0.8, 0.8, 0.7, 1))
        directional_np = self.render.attachNewNode(directional)
        directional_np.setHpr(45, -45, 0)
        self.render.setLight(directional_np)

        # 일시정지 플래그 — Esc로 토글. zombies/pistol/player update가 이 값을 본다.
        # 설정 메뉴는 player 생성 후에 만들어야 _get_current_sens가 sensitivity를 읽을 수 있음.
        self.paused = False

        self.player = PlayerController(self)
        self.hud = HUD(self)
        self.pistol = Pistol(self)

        # 좀비 추적 5마리.
        self.zombies = ZombieManager(self)
        self.zombies.spawn_initial_wave()

        # 일시정지 + 설정 UI — 생성 직후 hide(). _toggle_pause가 show/hide.
        self.settings_menu = SettingsMenu(self)

        # Esc는 종료가 아니라 일시정지 토글. 종료는 설정 메뉴의 Quit 버튼.
        self.accept("escape", self._toggle_pause)
        self.accept("mouse1", self.pistol.shoot)
        self.accept("r", self.pistol.reload)

        self.taskMgr.add(self._weapons_update_task, "weapons_update")

    def _toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.settings_menu.show()
            # 마우스 커서 표시 + 절대 모드 → UI 클릭 가능.
            props = WindowProperties()
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)
        else:
            self.settings_menu.hide()
            # resume 첫 프레임 마우스 델타 무시 — 안 그러면 시점이 휙 돌아감.
            self.player._first_mouse = True
            self.player._capture_mouse()

    def _weapons_update_task(self, task):
        if self.paused:
            return task.cont
        dt = _clock.getDt()
        self.pistol.update(dt)
        self.zombies.update(dt)
        return task.cont


def main():
    app = FPSGame()
    app.run()


if __name__ == "__main__":
    main()
