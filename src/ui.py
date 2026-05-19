"""화면 HUD — 크로스헤어 + 탄약 + 체력 + 피격 비네트 + 헤드샷 데미지 숫자."""

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import CardMaker, ClockObject, TextNode, TransparencyAttrib


_clock = ClockObject.getGlobalClock()

CROSSHAIR_SCALE = 0.07
AMMO_SCALE = 0.07
HP_SCALE = 0.07
AMMO_COLOR = (1, 1, 1, 1)
HP_COLOR = (1, 1, 1, 1)
VIGNETTE_RGB = (0.6, 0.0, 0.0)     # 피격 비네트 색 (붉은색)

# 헤드샷 데미지 숫자 ---------------------------------------------
HEADSHOT_TEXT_COLOR = (1.0, 0.95, 0.3, 1.0)   # 노란색
HEADSHOT_TEXT_SCALE = 0.07
HEADSHOT_TEXT_X = 0.0
HEADSHOT_TEXT_Z = -0.08                       # 크로스헤어 바로 아래
HEADSHOT_TEXT_HOLD_SEC = 0.35
HEADSHOT_TEXT_FADE_SEC = 0.25
HEADSHOT_TEXT_RISE = 0.05                     # 숫자가 떠오르는 거리
_HEADSHOT_TASK_DT_CAP = 1.0 / 30.0


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

    def show_headshot_number(self, damage_value):
        """크로스헤어 아래 "+{N}" 숫자가 0.35s 유지 → 0.25s 페이드 + 살짝 떠오름.

        매번 새 OnscreenText 생성 → 페이드 끝나면 destroy.
        동시 다발 헤드샷 시에도 각 인스턴스가 독립적으로 진행.
        """
        text = OnscreenText(
            text=f"+{damage_value}",
            pos=(HEADSHOT_TEXT_X, HEADSHOT_TEXT_Z),
            scale=HEADSHOT_TEXT_SCALE,
            fg=HEADSHOT_TEXT_COLOR,
            align=TextNode.ACenter,
            mayChange=True,
        )
        text.setTransparency(TransparencyAttrib.MAlpha)

        state = {"age": 0.0, "text": text}
        task_name = f"headshot_text_{id(state)}"
        total = HEADSHOT_TEXT_HOLD_SEC + HEADSHOT_TEXT_FADE_SEC

        def _update(task, _state=state, _total=total):
            dt = min(_clock.getDt(), _HEADSHOT_TASK_DT_CAP)
            _state["age"] += dt
            age = _state["age"]
            t = age / _total
            new_z = HEADSHOT_TEXT_Z + HEADSHOT_TEXT_RISE * t
            _state["text"].setPos(HEADSHOT_TEXT_X, new_z)
            if age < HEADSHOT_TEXT_HOLD_SEC:
                alpha = 1.0
            elif age < _total:
                alpha = 1.0 - (age - HEADSHOT_TEXT_HOLD_SEC) / HEADSHOT_TEXT_FADE_SEC
            else:
                alpha = 0.0
            _state["text"].setAlphaScale(max(0.0, alpha))
            if age >= _total:
                _state["text"].destroy()
                return task.done
            return task.cont

        self.base.taskMgr.add(_update, task_name)
