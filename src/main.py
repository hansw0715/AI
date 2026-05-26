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
    Filename,
    TextNode,
    Vec3,
    Vec4,
    WindowProperties,
)

from .level_up import LevelUpManager, LevelUpScreen, xp_to_next
from .physics import GROUND_MASK, HITTABLE_MASK
from .player import PlayerController
from .settings_menu import SettingsMenu
from .start_screen import StartScreen
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

        # 전역 한글 폰트 등록 — Panda3D 기본 폰트엔 한글 글리프가 없어 레벨업 카드
        # (`데미지 증가`, `희귀` 등) 가 네모 박스로 깨져 보임. Windows 맑은 고딕을
        # 동적 로드해 TextNode 기본 폰트로 지정 → 이후 생성되는 모든 OnscreenText /
        # DirectGUI 위젯이 자동으로 한글 렌더링.
        # 경로: Panda3D VFS 는 Unix-style 경로 요구 → Filename.fromOsSpecific 으로 변환.
        # loadFont 는 실패 시 IOError 를 raise 하므로 try/except 로 감싸 비-Windows /
        # 폰트 없는 환경에서도 게임 자체는 시작되도록 fallback. setPixelsPerUnit 으로
        # 글리프 해상도 키워 작은 scale 에서도 선명.
        try:
            font_path = Filename.fromOsSpecific(
                "C:/Windows/Fonts/malgun.ttf"
            ).getFullpath()
            kr_font = self.loader.loadFont(font_path)
            if kr_font is not None and kr_font.isValid():
                kr_font.setPixelsPerUnit(60)
                TextNode.setDefaultFont(kr_font)
        except (OSError, IOError):
            pass  # 폰트 못 찾으면 기존 기본 폰트 유지 (영문만 정상, 한글은 네모).

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

        # 게임 상태 플래그.
        #   started=False, paused=False, level_up_active=False  → 시작 화면 표시 중
        #   started=True,  paused=False, level_up_active=False  → 게임 진행
        #   started=True,  paused=True,  level_up_active=False  → 일시정지 메뉴
        #   started=True,  paused=False, level_up_active=True   → 레벨업 카드 선택
        # player/pistol/zombies update 와 입력 핸들러가 세 값을 모두 본다.
        # level_up_active 는 paused 와 동일한 게이트 — 게임 진행은 모두 멈춤.
        self.paused = False
        self.started = False
        self.level_up_active = False

        # 부팅 직후 — 시작 화면 버튼을 클릭할 수 있도록 커서 표시 + 절대 모드.
        # _begin_game 에서 M_relative + cursor hidden 으로 전환.
        props = WindowProperties()
        props.setCursorHidden(False)
        props.setMouseMode(WindowProperties.M_absolute)
        self.win.requestProperties(props)

        self.player = PlayerController(self)
        self.hud = HUD(self)
        # 시작 화면 동안 HUD 전체 숨김 — _begin_game 가 show_gameplay 호출.
        self.hud.hide_gameplay()
        self.pistol = Pistol(self)

        # 좀비 매니저는 생성만 — 첫 웨이브 스폰은 _begin_game 에서.
        self.zombies = ZombieManager(self)

        # 레벨업 매니저 + 카드 화면 — HUD/zombies 다음 생성.
        # zombie.take_damage 가 self.level_up.add_xp 를 호출하므로 zombies 보다 늦으면 안 됨.
        # 단 ZombieManager 는 인스턴스 생성만 했고 좀비 spawn 은 _begin_game 부터라 OK.
        self.level_up = LevelUpManager(self)
        self.level_up_screen = LevelUpScreen(self)
        # 초기 XP HUD 표시 — Lv 1, 0/30.
        self.hud.set_xp(self.level_up.level, self.level_up.xp,
                        xp_to_next(self.level_up.level))

        # 일시정지/시작 UI — 둘 다 생성 직후 자체 hide() 처리됨.
        self.settings_menu = SettingsMenu(self)
        self.start_screen = StartScreen(self)

        # Esc 는 시작 화면에선 무시(메뉴 버튼으로 진입 강제), 게임 중에만 일시정지 토글.
        # mouse1/mouse3/R 도 시작 화면 클릭이 사격/ADS/재장전을 발동하지 않도록 게이트.
        self.accept("escape", self._toggle_pause)
        self.accept("mouse1", self._on_mouse1)
        self.accept("mouse3", self._on_mouse3, [True])
        self.accept("mouse3-up", self._on_mouse3, [False])
        self.accept("r", self._on_reload)

        self.taskMgr.add(self._weapons_update_task, "weapons_update")

    def _begin_game(self):
        """StartScreen 의 Start 버튼 콜백. 게임 진행 상태로 전이.

        - HUD 표시 복귀
        - 마우스 캡처 (M_relative + 커서 hidden) + 첫 프레임 델타 무시
        - 첫 웨이브 스폰 (ZombieManager 가 이후 자체 진행)
        """
        if self.started:
            return
        self.started = True
        self.hud.show_gameplay()
        self.player._first_mouse = True
        self.player._capture_mouse()
        self.zombies.start_wave(1)

    def _toggle_pause(self):
        # 시작 화면에서는 Esc 무시 — 사용자가 메뉴 버튼으로 명시적 진입하도록.
        if not self.started:
            return
        # 레벨업 카드 선택 중에는 Esc 무시 — 카드 선택 강제 (스킵 금지).
        if self.level_up_active:
            return
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

    # ----- 입력 게이트 -----
    # 시작 화면/일시정지 중에 mouse1/mouse3/R 이벤트가 들어와도 사격/ADS/재장전이
    # 발동하지 않도록 한 곳에서 게이트. DirectGUI 버튼 클릭으로 들어오는 mouse1 도 포함.

    def _on_mouse1(self):
        if self.started and not self.paused and not self.level_up_active:
            self.pistol.shoot()

    def _on_mouse3(self, active):
        if self.started and not self.paused and not self.level_up_active:
            self.player.set_ads(active)

    def _on_reload(self):
        if self.started and not self.paused and not self.level_up_active:
            self.pistol.reload()

    def _weapons_update_task(self, task):
        if not self.started or self.paused or self.level_up_active:
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
