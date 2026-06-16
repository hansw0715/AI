"""플레이어 체력(코어 무결성) 시스템.

zombie_game.py 의 플레이어가 데미지를 받는 모든 경로(적 총탄 take_core_damage /
스폰 캠핑 _apply_spawn_damage / PvP _apply_pvp_damage)가 공통으로 쓰던
'체력 깎기 + 0 클램프 + 사망 판정' 규칙을 한 곳으로 모은 모듈.

같은 코드가 세 군데 복붙돼 있던 걸 PlayerHealth 로 통일해, 규칙을 바꿀 때
한 곳만 고치면 되도록 했다. (예: 최소/최대 체력, 회복 등)
"""


class PlayerHealth:
    """플레이어 한 명의 체력 상태와 규칙.

    max_hp : 최대 체력(기본 100). zombie_game 의 core_integrity_max 와 맞춘다.
    hp     : 현재 체력. 외부 스칼라(core_integrity)와 동기화해서 쓴다.
    """

    def __init__(self, max_hp=100):
        self.max_hp = max_hp
        self.hp = max_hp

    def take_damage(self, current_hp, amount):
        """현재 체력에서 amount 만큼 깎아 0 아래로 내려가지 않게 클램프한 값을 반환.
        내부 self.hp 도 갱신한다(회복/HUD 재사용 가능)."""
        self.hp = max(0, current_hp - amount)
        return self.hp

    def heal(self, current_hp, amount):
        """amount 만큼 회복하되 max_hp 를 넘지 않게 클램프한 값을 반환."""
        self.hp = min(self.max_hp, current_hp + amount)
        return self.hp

    def is_dead(self, hp=None):
        """체력이 0 이하이면 사망. hp 를 주면 그 값으로, 없으면 내부 hp 로 판정."""
        return (self.hp if hp is None else hp) <= 0

    def reset(self):
        """최대 체력으로 복구(리스폰/라운드 리셋)."""
        self.hp = self.max_hp
        return self.hp

    def ratio(self, hp=None):
        """체력바용 0.0~1.0 비율."""
        h = self.hp if hp is None else hp
        return max(0.0, h / self.max_hp) if self.max_hp else 0.0
