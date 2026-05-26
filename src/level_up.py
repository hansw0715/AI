"""레벨업 시스템 — Vampire Survivors 스타일 특성 카드 선택.

좀비 처치 시 XP 누적 → 레벨업 → 게임 일시정지 + 4 장 카드 표시 → 카드 클릭 시 효과 적용.

모듈 구성:
  - LevelUpManager  : XP/레벨 상태 + 레벨업 큐. add_xp(amount) 가 시작점.
  - LevelUpScreen   : DirectGUI 4 카드 UI. 마우스 모드 토글 + 카드 클릭 처리.
  - PERK_POOL       : 8 개 특성 정의 (이름 + 4 단계 효과량 + apply 콜백).
  - RARITY_WEIGHTS  : 희귀도 확률.
  - RARITY_COLORS   : 희귀도 색.

의존 방향: level_up → player / weapons 인스턴스 (단방향).
player/weapons 는 level_up 을 import 하지 않는다.

페어링된 main 게이트:
  - game.level_up_active 플래그가 True 이면 _weapons_update_task / 입력 핸들러 /
    player.update 가 모두 스킵 — paused 와 동일하게 게임 진행 정지.
  - Esc 는 level_up_active 동안 무시 (특성 선택 강제).
"""

import random

from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel
from panda3d.core import TextNode, WindowProperties


# XP / 레벨 곡선 --------------------------------------------------
# 곡선: xp_to_next(L) = XP_BASE + (L-1) * XP_PER_LEVEL + (L-1)^2 * XP_QUADRATIC
# 선형 증가만으로는 후반에 너무 쉽게 레벨업되므로, 2 차 항을 더해 레벨이
# 오를수록 가파르게 어려워지게 함.
#   Lv 1→2: 30   Lv 2→3: 55   Lv 3→4: 90   Lv 4→5: 135
#   Lv 5→6: 190  Lv 6→7: 255  Lv 7→8: 330  Lv 8→9: 415  Lv 9→10: 510
# 누적 (Lv L 까지 필요 XP 합):
#   Lv 5 도달: 310    Lv 7 도달: 755    Lv 10 도달: 1655
# 좀비 총 147 마리 × 10 XP = 1470 XP → 보통 Lv 9~10 부근까지 도달 (특성 보상 없을 때).
ZOMBIE_XP_REWARD = 10
XP_BASE = 30                             # Lv 1→2 필요 XP
XP_PER_LEVEL = 20                        # 선형 증가량
XP_QUADRATIC = 5                         # 2 차 항 — 0 이면 기존 선형 곡선과 동일


def xp_to_next(level):
    """level 에서 다음 레벨까지 필요 XP. 2 차 곡선으로 후반일수록 가파르게 어려워짐."""
    step = level - 1
    return XP_BASE + step * XP_PER_LEVEL + step * step * XP_QUADRATIC


# 희귀도 -------------------------------------------------------
# 카드 1 장당 독립적으로 굴림. 같은 레벨업 화면 4 장은 희귀도 중복 허용.
RARITY_WEIGHTS = [
    ("common",    50.0),
    ("rare",      30.0),
    ("epic",      15.0),
    ("legendary",  5.0),
]

RARITY_COLORS = {
    "common":    (0.8, 0.8, 0.8, 1),
    "rare":      (0.3, 0.6, 1.0, 1),
    "epic":      (0.7, 0.4, 1.0, 1),
    "legendary": (1.0, 0.8, 0.2, 1),
}

RARITY_LABELS = {
    "common":    "기본",
    "rare":      "희귀",
    "epic":      "에픽",
    "legendary": "전설",
}

# 카드 효과량 인덱스 — perk 의 amounts 튜플에서 희귀도별 값 꺼낼 때 사용.
RARITY_INDEX = {"common": 0, "rare": 1, "epic": 2, "legendary": 3}


def _roll_rarity():
    """RARITY_WEIGHTS 분포로 희귀도 키 하나 굴림."""
    return random.choices(
        [r for r, _ in RARITY_WEIGHTS],
        weights=[w for _, w in RARITY_WEIGHTS],
        k=1,
    )[0]


# 특성 풀 ----------------------------------------------------
# 각 perk dict:
#   id              : 중복 방지용 키 (같은 레벨업 화면에서 같은 perk 두 장 금지)
#   name            : 한글 이름 (카드 중앙)
#   describe(amt)   : 효과 설명 텍스트 (카드 하단). amt 는 amounts 튜플에서 꺼낸 값
#   amounts         : (common, rare, epic, legendary) 효과량
#   apply(game, amt): 효과 적용 콜백. game.player / game.pistol 인스턴스 속성 직접 가감
def _apply_damage(game, amt):
    game.pistol.base_damage += amt

def _apply_fire_rate(game, amt):
    # amt 는 0..1 사이 감소 비율 (예: 0.25 = 25% 감소).
    game.pistol.cooldown_time *= (1.0 - amt)

def _apply_mag_size(game, amt):
    game.pistol.mag_size += amt
    # 현재 탄약도 같이 증가 — 재장전 안 해도 즉시 보상이 보이도록.
    game.pistol.ammo += amt
    game.hud.update_ammo(game.pistol.ammo, game.pistol.mag_size, game.pistol.reloading)

def _apply_reload_speed(game, amt):
    game.pistol.reload_time *= (1.0 - amt)

def _apply_move_speed(game, amt):
    game.player.walk_speed *= (1.0 + amt)

def _apply_max_hp(game, amt):
    game.player.max_hp += amt
    game.player.hp += amt
    game.hud.set_player_hp(game.player.hp, game.player.max_hp)

def _apply_heal(game, amt):
    """amt 가 None 이면 풀 회복 (legendary), 아니면 정수만큼 회복 (max 클램프)."""
    player = game.player
    if amt is None:
        player.hp = player.max_hp
    else:
        player.hp = min(player.max_hp, player.hp + amt)
    game.hud.set_player_hp(player.hp, player.max_hp)

def _apply_xp_mult(game, amt):
    game.level_up.xp_multiplier *= (1.0 + amt)


PERK_POOL = [
    {
        "id": "damage",
        "name": "데미지 증가",
        "amounts": (2, 5, 10, 20),
        "describe": lambda a: f"데미지 +{a}",
        "apply": _apply_damage,
    },
    {
        "id": "fire_rate",
        "name": "연사 속도",
        "amounts": (0.05, 0.12, 0.25, 0.45),
        "describe": lambda a: f"발사 쿨다운 -{int(round(a * 100))}%",
        "apply": _apply_fire_rate,
    },
    {
        "id": "mag_size",
        "name": "탄창 크기",
        "amounts": (2, 4, 8, 16),
        "describe": lambda a: f"탄창 +{a}",
        "apply": _apply_mag_size,
    },
    {
        "id": "reload_speed",
        "name": "신속 재장전",
        "amounts": (0.08, 0.18, 0.35, 0.60),
        "describe": lambda a: f"재장전 시간 -{int(round(a * 100))}%",
        "apply": _apply_reload_speed,
    },
    {
        "id": "move_speed",
        "name": "이동 속도",
        "amounts": (0.05, 0.12, 0.25, 0.45),
        "describe": lambda a: f"이동 속도 +{int(round(a * 100))}%",
        "apply": _apply_move_speed,
    },
    {
        "id": "max_hp",
        "name": "최대 체력",
        "amounts": (10, 25, 50, 100),
        "describe": lambda a: f"최대 체력 +{a}",
        "apply": _apply_max_hp,
    },
    {
        "id": "heal",
        "name": "즉시 회복",
        # 전설은 None — _apply_heal 이 풀 회복 처리.
        "amounts": (20, 50, 100, None),
        "describe": lambda a: "체력 완전 회복" if a is None else f"체력 +{a} 회복",
        "apply": _apply_heal,
    },
    {
        "id": "xp_mult",
        "name": "경험치 획득",
        "amounts": (0.10, 0.25, 0.50, 1.00),
        "describe": lambda a: f"경험치 획득량 +{int(round(a * 100))}%",
        "apply": _apply_xp_mult,
    },
]

PERK_BY_ID = {p["id"]: p for p in PERK_POOL}


# UI 상수 --------------------------------------------------------
NUM_CARDS = 4
CARD_WIDTH = 0.5
CARD_HEIGHT = 0.9
# 카드 4 장 가로 배치 — 화면 중앙에 균등 간격.
CARD_SPACING = 0.6
CARD_Z = -0.1   # 화면 중앙보다 살짝 아래 (TITLE 자리 확보)

TITLE_SCALE = 0.14
LEVEL_LABEL_SCALE = 0.07
CARD_RARITY_SCALE = 0.06
CARD_NAME_SCALE = 0.06
CARD_DESC_SCALE = 0.045


class LevelUpManager:
    """XP / 레벨 상태머신 + 큐.

    - add_xp(amount) 가 진입점. xp_multiplier 가 자동 적용된 후 누적.
    - 누적이 xp_to_next 임계를 넘으면 _pending_levelups 큐에 쌓고 LevelUpScreen 표시.
    - 카드 한 장 선택 시 큐에서 하나 빼고 다음 카드 화면 또는 게임 재개.
    """

    def __init__(self, game):
        self.game = game
        self.level = 1
        self.xp = 0
        self.xp_multiplier = 1.0   # "경험치 획득" 특성이 곱연산 누적.
        # 한 번에 여러 레벨업 가능 — 큐로 처리해 카드 화면을 연속 표시.
        self._pending_levelups = 0

    def add_xp(self, amount):
        """좀비 처치 등에서 호출. 멀티플라이어 적용 후 누적 + 레벨업 판정."""
        if amount <= 0:
            return
        gained = int(round(amount * self.xp_multiplier))
        self.xp += gained
        # 누적이 임계 넘으면 큐에 쌓음. 한 번에 여러 레벨업 가능.
        while self.xp >= xp_to_next(self.level):
            self.xp -= xp_to_next(self.level)
            self.level += 1
            self._pending_levelups += 1
        # HUD 갱신 — 레벨업 화면 진입 직전 마지막 상태가 바 가득찬 모습이 되지 않게.
        self._update_hud()
        if self._pending_levelups > 0:
            self._show_next_card()

    def _update_hud(self):
        hud = getattr(self.game, "hud", None)
        if hud is not None:
            hud.set_xp(self.level, self.xp, xp_to_next(self.level))

    def _show_next_card(self):
        """큐가 비지 않았다면 다음 레벨업 카드 화면 띄움. 비었으면 게임 재개."""
        if self._pending_levelups <= 0:
            self.game.level_up_active = False
            screen = getattr(self.game, "level_up_screen", None)
            if screen is not None:
                screen.hide()
            return
        self.game.level_up_active = True
        screen = getattr(self.game, "level_up_screen", None)
        if screen is not None:
            screen.show(self.level - self._pending_levelups + 1)

    def consume_card(self):
        """카드 한 장 선택 완료 후 호출 — 큐 하나 줄이고 다음 단계 진행."""
        self._pending_levelups = max(0, self._pending_levelups - 1)
        self._show_next_card()


class LevelUpScreen:
    """4 장 카드 화면. DirectFrame 반투명 배경 + DirectButton 4 개."""

    def __init__(self, game):
        self.game = game
        self._build()
        self.hide()

    def _build(self):
        # 다른 메뉴(StartScreen/SettingsMenu)와 동일한 패턴.
        # frameColor 알파 0.7 → 게임 화면이 어두워지면서 카드가 떠 보임.
        self.frame = DirectFrame(
            parent=self.game.aspect2d,
            frameColor=(0, 0, 0, 0.7),
            frameSize=(-1.5, 1.5, -1, 1),
        )

        self.title_label = DirectLabel(
            parent=self.frame,
            text="LEVEL UP!",
            text_fg=(1.0, 0.85, 0.2, 1),
            text_scale=TITLE_SCALE,
            pos=(0, 0, 0.65),
            relief=None,
        )

        self.level_label = DirectLabel(
            parent=self.frame,
            text="Level 1",
            text_fg=(1, 1, 1, 1),
            text_scale=LEVEL_LABEL_SCALE,
            pos=(0, 0, 0.5),
            relief=None,
        )

        # 카드 4 장 — 가로 중앙 정렬. CARD_SPACING 만큼 균등 간격.
        # 인덱스 0~3 의 X 위치는 (i - (N-1)/2) * SPACING.
        self.cards = []
        for i in range(NUM_CARDS):
            x = (i - (NUM_CARDS - 1) / 2.0) * CARD_SPACING
            card = self._build_card(x)
            self.cards.append(card)

    def _build_card(self, x):
        """카드 한 장 — DirectButton + 자식 라벨 3 개 (희귀도/이름/설명).

        DirectButton 의 frameColor 가 희귀도 색 테두리 역할.
        text 인자는 비워두고 라벨로 별도 표시 (멀티라인 + 색 분리 필요).
        """
        # 버튼 frame — 카드 전체 클릭 영역. command 는 show() 에서 설정.
        button = DirectButton(
            parent=self.frame,
            frameSize=(
                -CARD_WIDTH / 2, CARD_WIDTH / 2,
                -CARD_HEIGHT / 2, CARD_HEIGHT / 2,
            ),
            frameColor=(0.15, 0.15, 0.20, 0.95),
            relief="raised",
            borderWidth=(0.02, 0.02),
            pos=(x, 0, CARD_Z),
            command=lambda: None,
        )

        rarity_label = DirectLabel(
            parent=button,
            text="",
            text_fg=(1, 1, 1, 1),
            text_scale=CARD_RARITY_SCALE,
            pos=(0, 0, CARD_HEIGHT / 2 - 0.10),
            relief=None,
        )

        name_label = DirectLabel(
            parent=button,
            text="",
            text_fg=(1, 1, 1, 1),
            text_scale=CARD_NAME_SCALE,
            pos=(0, 0, 0.0),
            relief=None,
        )

        # 효과 설명 — 카드 폭에 맞게 wrap. wordwrap 은 scale 단위 기준.
        desc_label = DirectLabel(
            parent=button,
            text="",
            text_fg=(0.9, 0.9, 0.9, 1),
            text_scale=CARD_DESC_SCALE,
            text_align=TextNode.ACenter,
            text_wordwrap=10,
            pos=(0, 0, -CARD_HEIGHT / 2 + 0.18),
            relief=None,
        )

        return {
            "button": button,
            "rarity_label": rarity_label,
            "name_label": name_label,
            "desc_label": desc_label,
        }

    # ---------- 표시 / 숨김 ----------

    def show(self, current_level):
        """4 장 카드 굴려 표시. current_level 은 이번 레벨업 후 도달한 레벨 번호."""
        self.level_label["text"] = f"Level {current_level}"

        # 4 장 perk 무작위 추출 — 같은 화면 안에서 중복 금지 (희귀도는 중복 허용).
        chosen_perks = random.sample(PERK_POOL, NUM_CARDS)

        for card, perk in zip(self.cards, chosen_perks):
            rarity = _roll_rarity()
            amt = perk["amounts"][RARITY_INDEX[rarity]]
            color = RARITY_COLORS[rarity]

            # 카드 테두리 — frameColor 알파는 유지하고 RGB 만 희귀도 색으로.
            # raised relief 의 borderColor 효과를 위해 frameColor 자체를 약간 어둡게 깔고
            # 텍스트로 희귀도 강조. 시각적으로 가장 안정적인 방식.
            card["button"]["frameColor"] = (
                color[0] * 0.25, color[1] * 0.25, color[2] * 0.25, 0.95
            )
            card["rarity_label"]["text"] = RARITY_LABELS[rarity]
            card["rarity_label"]["text_fg"] = color
            card["name_label"]["text"] = perk["name"]
            card["name_label"]["text_fg"] = color
            card["desc_label"]["text"] = perk["describe"](amt)

            # 클릭 콜백 — closure 로 perk/amt 캡처. _on_pick 이 효과 적용 + 화면 닫음.
            card["button"]["command"] = (
                lambda p=perk, a=amt: self._on_pick(p, a)
            )

        self.frame.show()
        # 마우스 커서 + M_absolute — SettingsMenu show 와 동일 패턴.
        # 카드 클릭이 가능하도록 절대 좌표 모드로.
        props = WindowProperties()
        props.setCursorHidden(False)
        props.setMouseMode(WindowProperties.M_absolute)
        self.game.win.requestProperties(props)

    def hide(self):
        self.frame.hide()

    def _on_pick(self, perk, amt):
        """카드 클릭 콜백 — 효과 적용 후 다음 카드 또는 게임 재개."""
        perk["apply"](self.game, amt)
        # 큐를 줄이고 다음 카드 / 재개 결정은 매니저에 위임.
        self.game.level_up.consume_card()
        # 큐가 비어 게임 재개로 전이됐다면 마우스 캡처 + _first_mouse 복원.
        # consume_card → _show_next_card 가 level_up_active 를 False 로 만든 직후 처리.
        if not self.game.level_up_active:
            player = getattr(self.game, "player", None)
            if player is not None:
                player._first_mouse = True
                player._capture_mouse()
