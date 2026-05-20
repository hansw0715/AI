"""화면 HUD — 크로스헤어 + 탄약 + 체력 + 피격 비네트 + 웨이브 UI."""

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import CardMaker, TextNode, TransparencyAttrib


CROSSHAIR_SCALE = 0.07
AMMO_SCALE = 0.07
HP_SCALE = 0.07
AMMO_COLOR = (1, 1, 1, 1)
HP_COLOR = (1, 1, 1, 1)
VIGNETTE_RGB = (0.6, 0.0, 0.0)            # 피격 비네트 색 (붉은색)

# 웨이브 UI -------------------------------------------------------
WAVE_LABEL_SCALE = 0.06
WAVE_LABEL_COLOR = (1, 1, 1, 1)
REMAINING_LABEL_SCALE = 0.05
REMAINING_LABEL_COLOR = (0.9, 0.9, 0.9, 1)
INTERMISSION_SCALE = 0.12
INTERMISSION_COLOR = (1.0, 1.0, 0.6, 1)   # 밝은 노란빛 (카운트다운)
VICTORY_SCALE = 0.20
VICTORY_COLOR = (0.3, 1.0, 0.3, 1)        # 밝은 녹색
# 화면 중앙 텍스트(aspect2d 기준 (0,0)=정중앙)를 크로스헤어와 겹치지 않게 살짝 위로.
CENTER_TEXT_Z = 0.18


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

        # HP 텍스트 — 좌하단. 좀비 공격으로 hp가 깎이면 갱신.
        # HUD 는 PlayerController 다음에 생성되므로 base.player 가 이미 존재.
        initial_hp = base.player.hp
        initial_max = base.player.max_hp
        self.hp_text = OnscreenText(
            text=f"HP {initial_hp}/{initial_max}",
            parent=base.a2dBottomLeft,
            pos=(0.05, 0.1),
            scale=HP_SCALE,
            fg=HP_COLOR,
            align=TextNode.ALeft,
            mayChange=True,
        )

        # 피격 비네트 — render2d 전체를 덮는 붉은 카드.
        # setBin("background", 0) 으로 다른 UI 요소보다 먼저 그려져
        # 크로스헤어/HP 텍스트가 위에 보이게 한다.
        cm = CardMaker("damage_vignette")
        cm.setFrame(-1, 1, -1, 1)
        self.damage_vignette = base.render2d.attachNewNode(cm.generate())
        self.damage_vignette.setTransparency(TransparencyAttrib.MAlpha)
        self.damage_vignette.setColor(*VIGNETTE_RGB, 0.0)
        self.damage_vignette.setBin("background", 0)
        self.damage_vignette.hide()

        # 상단 중앙 — 현재 웨이브 / 총 웨이브. 항상 보임.
        # a2dTopCenter 의 (0,0) 은 화면 상단 가운데. Z 가 -면 아래쪽.
        self.wave_text = OnscreenText(
            text="Wave 0 / 0",
            parent=base.a2dTopCenter,
            pos=(0, -0.10),
            scale=WAVE_LABEL_SCALE,
            fg=WAVE_LABEL_COLOR,
            align=TextNode.ACenter,
            mayChange=True,
        )

        # 상단 중앙(웨이브 아래) — 남은 좀비 수. active 동안만 표시.
        self.remaining_text = OnscreenText(
            text="",
            parent=base.a2dTopCenter,
            pos=(0, -0.18),
            scale=REMAINING_LABEL_SCALE,
            fg=REMAINING_LABEL_COLOR,
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.remaining_text.hide()

        # 화면 중앙 — 인터미션 카운트다운. intermission 동안만 표시.
        self.intermission_text = OnscreenText(
            text="",
            pos=(0, CENTER_TEXT_Z),
            scale=INTERMISSION_SCALE,
            fg=INTERMISSION_COLOR,
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.intermission_text.hide()

        # 화면 중앙 — 10웨이브 클리어 시 표시. 한 번 표시하면 그대로.
        self.victory_text = OnscreenText(
            text="VICTORY",
            pos=(0, CENTER_TEXT_Z),
            scale=VICTORY_SCALE,
            fg=VICTORY_COLOR,
            align=TextNode.ACenter,
            mayChange=False,
        )
        self.victory_text.hide()

    def update_ammo(self, current, max_, reloading):
        if reloading:
            self.ammo_text.setText("Reloading...")
        else:
            self.ammo_text.setText(f"{current} / {max_}")

    def set_player_hp(self, hp, max_hp):
        self.hp_text.setText(f"HP {hp}/{max_hp}")

    def set_damage_flash(self, alpha):
        self.damage_vignette.setColor(*VIGNETTE_RGB, alpha)
        if alpha <= 0.0:
            self.damage_vignette.hide()
        else:
            self.damage_vignette.show()

    # ----- 웨이브 -----
    def set_wave(self, current, total):
        self.wave_text.setText(f"Wave {current} / {total}")

    def set_remaining(self, count):
        """남은 좀비 수 갱신. 0 이면 자동으로 숨김 (인터미션/클리어 시 호출자 별도 처리 불필요)."""
        if count > 0:
            self.remaining_text.setText(f"Zombies: {count}")
            self.remaining_text.show()
        else:
            self.remaining_text.hide()

    def show_intermission_countdown(self, seconds_left, next_wave):
        self.intermission_text.setText(
            f"Wave {next_wave} starting in {seconds_left}..."
        )
        self.intermission_text.show()

    def hide_intermission(self):
        self.intermission_text.hide()

    def show_victory(self):
        self.victory_text.show()
