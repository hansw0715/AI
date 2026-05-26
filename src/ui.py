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

# XP 바 -----------------------------------------------------------
# Vampire Survivors 스타일 — 화면 최상단을 가로지르는 얇은 노란색 바.
# render2d 좌표계: X = -1..+1 (전체 너비), Z = -1..+1 (전체 높이).
# 바를 render2d 에 부착해 화면비 무관하게 화면 전폭(width 2.0) 으로 펼침.
XP_BAR_HEIGHT = 0.015      # render2d 단위 — 화면 상단 1.5% 높이
XP_BAR_Z_TOP = 1.0         # 화면 최상단
XP_BAR_BG_COLOR = (0.15, 0.15, 0.15, 0.85)
XP_BAR_FILL_COLOR = (1.0, 0.85, 0.2, 1)   # 황금빛 노란색
XP_LEVEL_TEXT_SCALE = 0.05
XP_LEVEL_TEXT_COLOR = (1.0, 0.85, 0.2, 1)


class HUD:
    def __init__(self, base):
        self.base = base

        # OnscreenText 는 baseline 기준 앵커링이라 pos=(0,0) 이면 baseline 이 화면 중앙에
        # 놓이고 글리프 시각 중심은 ~capHeight/2 만큼 위로 떠 있다 → 플레이어가 +
        # 시각 중심을 보고 조준하면 raycast (camera +Y, 정중앙) 가 + 아래에 hit.
        # CROSSHAIR_SCALE × 0.30 만큼 Z 를 내려 + 의 가운데가 정확히 (0, 0) 에 오게 보정.
        self.crosshair = OnscreenText(
            text="+",
            pos=(0, -CROSSHAIR_SCALE * 0.30),
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

        # XP 바 (render2d 부착, 화면 전폭). 배경 카드 + 채우기 pivot 패턴 —
        # 좀비 체력바와 동일하게 pivot 의 setSx 만 변경하면 왼쪽 정렬로 폭이 줄어듦.
        # render2d X = -1..+1 → 바 너비 2.0 (화면 전폭).
        xp_bg_cm = CardMaker("xp_bar_bg")
        xp_bg_cm.setFrame(-1.0, 1.0, XP_BAR_Z_TOP - XP_BAR_HEIGHT, XP_BAR_Z_TOP)
        self.xp_bar_bg = base.render2d.attachNewNode(xp_bg_cm.generate())
        self.xp_bar_bg.setTransparency(TransparencyAttrib.MAlpha)
        self.xp_bar_bg.setColor(*XP_BAR_BG_COLOR)

        # 채우기 pivot — 원점을 바 왼쪽 끝 (X = -1) 으로.
        # 이후 pivot.setSx(ratio) 만 호출하면 왼쪽 끝 고정으로 폭이 변함.
        self.xp_bar_fill_pivot = base.render2d.attachNewNode("xp_bar_fill_pivot")
        self.xp_bar_fill_pivot.setX(-1.0)

        # 채우기 카드 — pivot 원점에서 +X 방향으로 2.0 (화면 전폭).
        xp_fill_cm = CardMaker("xp_bar_fill")
        xp_fill_cm.setFrame(0.0, 2.0, XP_BAR_Z_TOP - XP_BAR_HEIGHT, XP_BAR_Z_TOP)
        self.xp_bar_fill = self.xp_bar_fill_pivot.attachNewNode(xp_fill_cm.generate())
        self.xp_bar_fill.setColor(*XP_BAR_FILL_COLOR)

        # 초기 폭 0 — set_xp 호출 시 갱신. setSx(0) 은 singular matrix 경고가 뜨므로
        # 좀비 체력바와 같은 패턴으로 0.001 클램프.
        self.xp_bar_fill_pivot.setSx(0.001)

        # Lv 텍스트 — XP 바 바로 아래 좌측. 가독성 위해 a2dTopLeft 부모.
        # a2dTopLeft (0,0) = 화면 좌상단 코너. X 양수 = 안쪽, Z 음수 = 아래.
        self.xp_level_text = OnscreenText(
            text="Lv 1",
            parent=base.a2dTopLeft,
            pos=(0.04, -0.06),
            scale=XP_LEVEL_TEXT_SCALE,
            fg=XP_LEVEL_TEXT_COLOR,
            align=TextNode.ALeft,
            mayChange=True,
        )

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

    # ----- XP / 레벨 -----
    def set_xp(self, level, xp, xp_to_next_):
        """XP 바 폭과 Lv 텍스트 동시 갱신. xp_to_next_ 가 0 이면 가득 채움."""
        if xp_to_next_ <= 0:
            ratio = 1.0
        else:
            ratio = max(0.001, min(1.0, xp / xp_to_next_))
        self.xp_bar_fill_pivot.setSx(ratio)
        self.xp_level_text.setText(f"Lv {level}")

    # ----- 시작 화면 동안 HUD 전체 토글 -----
    def hide_gameplay(self):
        """시작 화면이 떠 있는 동안 모든 게임플레이 UI 숨김. 월드만 배경처럼 보이게."""
        self.crosshair.hide()
        self.ammo_text.hide()
        self.hp_text.hide()
        self.wave_text.hide()
        self.remaining_text.hide()
        self.intermission_text.hide()
        self.victory_text.hide()
        self.damage_vignette.hide()
        self.xp_bar_bg.hide()
        self.xp_bar_fill_pivot.hide()
        self.xp_level_text.hide()

    def show_gameplay(self):
        """게임 시작 시 호출. 항상 보여야 하는 요소만 다시 표시 —
        remaining/intermission/victory 는 ZombieManager 가 상태에 따라 show 함."""
        self.crosshair.show()
        self.ammo_text.show()
        self.hp_text.show()
        self.wave_text.show()
        self.xp_bar_bg.show()
        self.xp_bar_fill_pivot.show()
        self.xp_level_text.show()
