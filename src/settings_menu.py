"""일시정지 + 설정 메뉴 — Esc 키로 토글.

DirectGUI(panda3d 내장) 위젯 트리:
  self.frame (DirectFrame, 반투명 배경, aspect2d 자식)
    ├── 타이틀 "PAUSED"
    ├── "Mouse Sensitivity" 라벨
    ├── self.sens_slider — 감도 변경 즉시 self.game.player.sensitivity에 반영
    ├── self.sens_value_label — 슬라이더 현재값 표시 (소수점 둘째 자리)
    ├── Resume 버튼  → game._toggle_pause()
    └── Quit 버튼    → game.userExit()

게임 시작 시 생성된 후 즉시 hide(). _toggle_pause가 show/hide 토글.
"""

from direct.gui.DirectGui import (
    DirectButton,
    DirectFrame,
    DirectLabel,
    DirectSlider,
)


class SettingsMenu:
    def __init__(self, game):
        self.game = game
        self._build()
        self.hide()

    def _build(self):
        # 반투명 검정 배경 — aspect2d에 attach해 16:9에서도 비율 유지.
        self.frame = DirectFrame(
            parent=self.game.aspect2d,
            frameColor=(0, 0, 0, 0.7),
            frameSize=(-1.5, 1.5, -1, 1),
        )

        DirectLabel(
            parent=self.frame,
            text="PAUSED",
            text_fg=(1, 1, 1, 1),
            text_scale=0.15,
            pos=(0, 0, 0.6),
            relief=None,
        )

        DirectLabel(
            parent=self.frame,
            text="Mouse Sensitivity",
            text_fg=(1, 1, 1, 1),
            text_scale=0.06,
            pos=(0, 0, 0.25),
            relief=None,
        )

        # 기본 민감도가 0.075 로 내려갔으므로 슬라이더 최솟값도 그 절반(0.025) 까지
        # 내려 더 정밀한 조준 선호 유저를 수용. pageSize 도 비례로 축소.
        current_sens = self._get_current_sens()
        self.sens_slider = DirectSlider(
            parent=self.frame,
            range=(0.025, 0.5),
            value=current_sens,
            pageSize=0.025,
            scale=0.4,
            pos=(0, 0, 0.15),
            command=self._on_sens_change,
        )

        # 슬라이더 값 표시 라벨 — _on_sens_change에서 갱신.
        self.sens_value_label = DirectLabel(
            parent=self.frame,
            text=f"{current_sens:.2f}",
            text_fg=(1, 1, 1, 1),
            text_scale=0.06,
            pos=(0, 0, 0.05),
            relief=None,
        )

        DirectButton(
            parent=self.frame,
            text="Resume",
            text_scale=0.06,
            scale=0.1,
            pos=(0, 0, -0.2),
            command=self._on_resume,
        )

        DirectButton(
            parent=self.frame,
            text="Quit",
            text_scale=0.06,
            scale=0.1,
            pos=(0, 0, -0.45),
            command=self._on_quit,
        )

    def _get_current_sens(self):
        return self.game.player.sensitivity

    def _on_sens_change(self):
        # DirectSlider.command는 인자 없이 호출 → 위젯에서 직접 값 읽음.
        value = self.sens_slider["value"]
        self.game.player.sensitivity = value
        self.sens_value_label["text"] = f"{value:.2f}"

    def _on_resume(self):
        # 토글 위임 — main이 paused 플래그/마우스 캡처/_first_mouse를 다 처리.
        self.game._toggle_pause()

    def _on_quit(self):
        self.game.userExit()

    def show(self):
        self.frame.show()

    def hide(self):
        self.frame.hide()
