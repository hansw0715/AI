"""화면 HUD — 크로스헤어 + 탄약 카운터."""

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode


CROSSHAIR_SCALE = 0.07
AMMO_SCALE = 0.07
AMMO_COLOR = (1, 1, 1, 1)


class HUD:
    def __init__(self, base):
        self.base = base

        self.crosshair = OnscreenText(
            text="+",
            pos=(0, 0),
            scale=CROSSHAIR_SCALE,
            fg=AMMO_COLOR,
            mayChange=False,
        )

        # a2dBottomRight 부모를 쓰면 (0,0)이 화면 우하단 코너.
        # 안쪽으로 들이려면 X는 음수, Z는 양수.
        self.ammo_text = OnscreenText(
            text="12 / 12",
            parent=base.a2dBottomRight,
            pos=(-0.05, 0.1),
            scale=AMMO_SCALE,
            fg=AMMO_COLOR,
            align=TextNode.ARight,
            mayChange=True,
        )

    def update_ammo(self, current, max_, reloading):
        if reloading:
            self.ammo_text.setText("Reloading...")
        else:
            self.ammo_text.setText(f"{current} / {max_}")
