"""게임 시작 화면 — 타이틀 + 3개 버튼 (Start / Settings / Controls).

DirectGUI 위젯 트리:
  self.frame_main      — 타이틀 "Game" + 메인 버튼 3개 (Start/Settings/Controls)
  self.frame_settings  — 마우스 감도 슬라이더 + Back
  self.frame_controls  — 조작법 텍스트 + Back

세 프레임 모두 aspect2d 자식, frameColor 알파 0 → 월드가 메뉴 뒤로 그대로 보임.

상태 전이:
  main → Start          → game._begin_game (게임 시작)
  main → Settings       → settings 패널 표시
  main → Controls       → controls 패널 표시
  settings/controls → Back → main 으로 복귀

마우스 캡처/HUD 표시/첫 웨이브 스폰은 game._begin_game 가 담당.
StartScreen 은 순수히 UI 표시/숨김만 처리.
"""

from direct.gui.DirectGui import (
    DirectButton,
    DirectFrame,
    DirectLabel,
    DirectSlider,
)


TITLE_TEXT = "Game"
TITLE_COLOR = (1, 1, 1, 1)
TITLE_SCALE = 0.22
SUBTITLE_SCALE = 0.10              # Settings / Controls 패널 헤더 크기

BUTTON_SCALE = 0.10                # DirectButton 외곽 스케일
BUTTON_TEXT_SCALE = 0.55           # 버튼 안 텍스트 스케일 (DirectButton scale 에 곱해짐)
LABEL_TEXT_SCALE = 0.06

# 조작법 본문 — center-align 으로 한 줄씩 표시. em-dash 로 구분.
CONTROLS_BODY = (
    "WASD  —  Move\n"
    "Shift  —  Run\n"
    "Space  —  Jump\n"
    "Mouse  —  Look\n"
    "Left Click  —  Fire\n"
    "Right Click  —  Aim Down Sights\n"
    "R  —  Reload\n"
    "Esc  —  Pause"
)


class StartScreen:
    def __init__(self, game):
        self.game = game
        self._build_main()
        self._build_settings()
        self._build_controls()
        # 처음에는 메인 메뉴 보이고 나머지 hide.
        self.show_main()

    # ---------- 빌드 ----------

    def _build_main(self):
        # frameColor 알파 0 → 배경 투명. 월드가 메뉴 뒤로 그대로 보임.
        # frameSize 가 없으면 자동이라 hit area 가 없어 hide/show 만 동작 (클릭 불필요).
        self.frame_main = DirectFrame(
            parent=self.game.aspect2d,
            frameColor=(0, 0, 0, 0),
        )

        DirectLabel(
            parent=self.frame_main,
            text=TITLE_TEXT,
            text_fg=TITLE_COLOR,
            text_scale=TITLE_SCALE,
            pos=(0, 0, 0.5),
            relief=None,
        )

        DirectButton(
            parent=self.frame_main,
            text="Start",
            text_scale=BUTTON_TEXT_SCALE,
            scale=BUTTON_SCALE,
            pos=(0, 0, 0.05),
            command=self._on_start,
        )
        DirectButton(
            parent=self.frame_main,
            text="Settings",
            text_scale=BUTTON_TEXT_SCALE,
            scale=BUTTON_SCALE,
            pos=(0, 0, -0.15),
            command=self._on_settings,
        )
        DirectButton(
            parent=self.frame_main,
            text="Controls",
            text_scale=BUTTON_TEXT_SCALE,
            scale=BUTTON_SCALE,
            pos=(0, 0, -0.35),
            command=self._on_controls,
        )

    def _build_settings(self):
        self.frame_settings = DirectFrame(
            parent=self.game.aspect2d,
            frameColor=(0, 0, 0, 0),
        )

        DirectLabel(
            parent=self.frame_settings,
            text="Settings",
            text_fg=TITLE_COLOR,
            text_scale=SUBTITLE_SCALE,
            pos=(0, 0, 0.55),
            relief=None,
        )

        DirectLabel(
            parent=self.frame_settings,
            text="Mouse Sensitivity",
            text_fg=(1, 1, 1, 1),
            text_scale=LABEL_TEXT_SCALE,
            pos=(0, 0, 0.25),
            relief=None,
        )

        current_sens = self.game.player.sensitivity
        # SettingsMenu (일시정지) 와 동일한 슬라이더 사양 — 일관성 유지.
        self.sens_slider = DirectSlider(
            parent=self.frame_settings,
            range=(0.025, 0.5),
            value=current_sens,
            pageSize=0.025,
            scale=0.4,
            pos=(0, 0, 0.13),
            command=self._on_sens_change,
        )
        self.sens_value_label = DirectLabel(
            parent=self.frame_settings,
            text=f"{current_sens:.2f}",
            text_fg=(1, 1, 1, 1),
            text_scale=LABEL_TEXT_SCALE,
            pos=(0, 0, 0.03),
            relief=None,
        )

        DirectButton(
            parent=self.frame_settings,
            text="Back",
            text_scale=BUTTON_TEXT_SCALE,
            scale=BUTTON_SCALE,
            pos=(0, 0, -0.25),
            command=self.show_main,
        )
        self.frame_settings.hide()

    def _build_controls(self):
        self.frame_controls = DirectFrame(
            parent=self.game.aspect2d,
            frameColor=(0, 0, 0, 0),
        )

        DirectLabel(
            parent=self.frame_controls,
            text="Controls",
            text_fg=TITLE_COLOR,
            text_scale=SUBTITLE_SCALE,
            pos=(0, 0, 0.55),
            relief=None,
        )

        DirectLabel(
            parent=self.frame_controls,
            text=CONTROLS_BODY,
            text_fg=(1, 1, 1, 1),
            text_scale=0.055,
            pos=(0, 0, 0.25),
            relief=None,
        )

        DirectButton(
            parent=self.frame_controls,
            text="Back",
            text_scale=BUTTON_TEXT_SCALE,
            scale=BUTTON_SCALE,
            pos=(0, 0, -0.45),
            command=self.show_main,
        )
        self.frame_controls.hide()

    # ---------- 화면 전환 ----------

    def show_main(self):
        self.frame_main.show()
        self.frame_settings.hide()
        self.frame_controls.hide()

    def show_settings(self):
        self.frame_main.hide()
        self.frame_settings.show()
        self.frame_controls.hide()

    def show_controls(self):
        self.frame_main.hide()
        self.frame_settings.hide()
        self.frame_controls.show()

    def hide(self):
        self.frame_main.hide()
        self.frame_settings.hide()
        self.frame_controls.hide()

    # ---------- 콜백 ----------

    def _on_start(self):
        # 메뉴 전체 hide → 게임 진행 시작 위임.
        self.hide()
        self.game._begin_game()

    def _on_settings(self):
        self.show_settings()

    def _on_controls(self):
        self.show_controls()

    def _on_sens_change(self):
        # DirectSlider.command 는 인자 없이 호출 → 위젯에서 직접 값 읽음.
        value = self.sens_slider["value"]
        self.game.player.sensitivity = value
        self.sens_value_label["text"] = f"{value:.2f}"
