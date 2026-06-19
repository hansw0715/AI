"""적(AI 봇) 체력 시스템.

zombie_game.py 에서 적이 데미지를 받는 경로(봇0 명중 _on_remote_player_hit /
추가 봇 명중 _on_bot_hit / 스폰 캠핑 역공)가 공통으로 쓰던
'체력 깎기 + 0 클램프 + 사망 판정' 규칙을 한 곳으로 모은 모듈.

봇0 은 self.ai_hp 스칼라, 추가 봇은 bot['hp'] 딕셔너리 값으로 체력을 들고 있어
저장 위치가 제각각이었다. EnemyHealth.take_damage 는 현재 체력을 인자로 받아
새 체력을 돌려주므로 두 경우 모두 같은 규칙으로 처리한다.
"""


class EnemyHealth:
    """적 한 기의 체력 상태와 규칙.

    max_hp : 최대 체력(기본 100). zombie_game 의 ai_max_hp 와 맞춘다.
    hp     : 현재 체력. self.ai_hp / bot['hp'] 와 동기화해서 쓴다.
    """

    def __init__(self, max_hp=100):
        self.max_hp = max_hp
        self.hp = max_hp

    def take_damage(self, current_hp, amount):
        """현재 체력에서 amount 만큼 깎아 0 아래로 내려가지 않게 클램프한 값을 반환.
        current_hp 를 인자로 받으므로 봇0(ai_hp)·추가봇(bot['hp']) 모두에 쓸 수 있다."""
        self.hp = max(0, current_hp - amount)
        return self.hp

    def is_dead(self, hp=None):
        """체력이 0 이하이면 처치됨. hp 를 주면 그 값으로, 없으면 내부 hp 로 판정."""
        return (self.hp if hp is None else hp) <= 0

    def respawn(self):
        """처치된 적을 최대 체력으로 부활."""
        self.hp = self.max_hp
        return self.hp

    def ratio(self, hp=None):
        """적 체력바용 0.0~1.0 비율."""
        h = self.hp if hp is None else hp
        return max(0.0, min(1.0, h / self.max_hp)) if self.max_hp else 0.0
