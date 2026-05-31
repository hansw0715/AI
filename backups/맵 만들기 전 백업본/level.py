"""
level.py — zombie_game 연구실 레벨 (방 / 벽 / 충돌).

설계 요약
  - 방(room) = XY 평면의 축정렬 사각형. room_walls() 가 4면 벽을 만들고
    door 위치는 통로(구멍)로 비운다.
  - 벽(Wall) = 얇은 축정렬 박스. 시각용 2-sided card + 충돌용 footprint AABB.
  - 충돌 = 원(플레이어 반지름) vs 박스. LevelCollider.resolve(x, y, r) 가
    벽을 뚫지 못하게 보정한 (x, y) 를 돌려준다.
  - 여기서 door 는 그냥 "뚫린 통로". 방화벽(firewall)/문/구역 트리거는 다음 단계.

좌표계: Panda3D 표준 Z-up, Y-forward. 모든 단위 m.
사용법: zombie_game.py 의 __init__ 에서 build_level(self.render) 호출.
"""

from math import atan2, degrees, hypot

from panda3d.core import CardMaker


# ── 튜닝 노브 ────────────────────────────────────────────────────────────
WALL_HEIGHT    = 3.0                       # m — 벽 높이
WALL_THICKNESS = 0.30                      # m — 충돌 박스 두께
WALL_COLOR     = (0.72, 0.74, 0.78, 1.0)   # 연구실 패널 느낌 밝은 회색
PLAYER_RADIUS  = 0.40                       # m — 플레이어 충돌 반지름
ZOMBIE_RADIUS  = 0.45                       # m — 좀비 충돌 반지름 (선택)
DOOR_WIDTH     = 2.4                        # m — 통로 폭 (플레이어 통과 여유)


class Wall:
    """축정렬 벽 한 칸. 중심선 (ax,ay)->(bx,by) + 두께 → footprint 박스."""
    __slots__ = ('x0', 'x1', 'y0', 'y1', 'ax', 'ay', 'bx', 'by')

    def __init__(self, ax, ay, bx, by, thickness=WALL_THICKNESS):
        self.ax, self.ay, self.bx, self.by = ax, ay, bx, by
        half = thickness * 0.5
        self.x0 = min(ax, bx) - half
        self.x1 = max(ax, bx) + half
        self.y0 = min(ay, by) - half
        self.y1 = max(ay, by) + half

    def make_card(self, parent):
        """중심선을 따라 세운 2-sided 사각 card 를 parent 아래에 만든다."""
        length = hypot(self.bx - self.ax, self.by - self.ay)
        cm = CardMaker('wall')
        # CardMaker 기본 card 는 XZ 평면(Y=0)에 섬 → bottom/top 이 Z(높이).
        cm.setFrame(-length / 2.0, length / 2.0, 0.0, WALL_HEIGHT)
        np = parent.attachNewNode(cm.generate())
        np.setTwoSided(True)
        np.setPos((self.ax + self.bx) / 2.0, (self.ay + self.by) / 2.0, 0.0)
        # local +X 를 벽 방향으로 정렬. (수평벽 H=0, 수직벽 H=90)
        np.setH(degrees(atan2(self.by - self.ay, self.bx - self.ax)))
        np.setColor(*WALL_COLOR)
        return np


def _add(walls, orient, fixed, a, b):
    """[a,b] 구간 벽 한 칸 추가. orient 'h'=X 따라(고정 y), 'v'=Y 따라(고정 x)."""
    if b - a < 1e-3:
        return
    if orient == 'h':
        walls.append(Wall(a, fixed, b, fixed))
    else:
        walls.append(Wall(fixed, a, fixed, b))


def room_walls(x0, x1, y0, y1, doors=()):
    """방 사각형의 4면 벽 리스트.

    doors: (side, center, width) 들.
      side: 'N'(+Y, y=y1), 'S'(-Y, y=y0), 'E'(+X, x=x1), 'W'(-X, x=x0)
      center: 그 면 위 구멍의 중심 좌표, width: 구멍 폭.
    """
    walls = []
    by_side = {'N': [], 'S': [], 'E': [], 'W': []}
    for side, c, w in doors:
        by_side[side].append((c, w))

    def emit(orient, fixed, lo, hi, side_doors):
        gaps = sorted((c - w / 2.0, c + w / 2.0) for (c, w) in side_doors)
        cursor = lo
        for g0, g1 in gaps:
            if g0 > cursor:
                _add(walls, orient, fixed, cursor, g0)
            cursor = max(cursor, g1)
        if cursor < hi:
            _add(walls, orient, fixed, cursor, hi)

    emit('h', y1, x0, x1, by_side['N'])   # 북
    emit('h', y0, x0, x1, by_side['S'])   # 남
    emit('v', x1, y0, y1, by_side['E'])   # 동
    emit('v', x0, y0, y1, by_side['W'])   # 서
    return walls


def pillar(cx, cy, half=0.5):
    """정사각 기둥 = 4 벽. 엄폐물용."""
    return [
        Wall(cx - half, cy - half, cx + half, cy - half),
        Wall(cx - half, cy + half, cx + half, cy + half),
        Wall(cx - half, cy - half, cx - half, cy + half),
        Wall(cx + half, cy - half, cx + half, cy + half),
    ]


class LevelCollider:
    """원(반지름 r) vs 모든 벽 박스 충돌 해소."""

    def __init__(self, walls):
        self.walls = walls

    def resolve(self, x, y, radius):
        # 코너에서 두 벽에 동시에 끼는 경우를 위해 2패스.
        for _ in range(2):
            for w in self.walls:
                cx = min(max(x, w.x0), w.x1)
                cy = min(max(y, w.y0), w.y1)
                dx = x - cx
                dy = y - cy
                d2 = dx * dx + dy * dy
                if d2 >= radius * radius:
                    continue
                if d2 > 1e-9:
                    # 박스 바깥 — 가장 가까운 점에서 바깥쪽으로 밀어냄
                    d = d2 ** 0.5
                    push = radius - d
                    x += (dx / d) * push
                    y += (dy / d) * push
                else:
                    # 중심이 박스 안 — 최소 침투축으로 탈출
                    left, right = x - w.x0, w.x1 - x
                    bottom, top = y - w.y0, w.y1 - y
                    m = min(left, right, bottom, top)
                    if m == left:
                        x = w.x0 - radius
                    elif m == right:
                        x = w.x1 + radius
                    elif m == bottom:
                        y = w.y0 - radius
                    else:
                        y = w.y1 + radius
        return x, y


def build_level(render):
    """레벨을 render 아래에 생성. (collider, spawns) 반환.

    spawns: 방별 좀비 스폰 좌표 [(x, y), ...] — 다음 단계(좀비 배치)에서 사용.
    레이아웃 = 남→북 선형 5방. door 는 인접 방 양쪽에 같은 위치로 뚫어 통로 형성.
    숫자만 바꾸면 방 크기/위치 조정. F2 free-cam 으로 좌표 보면서 튜닝.
    """
    root = render.attachNewNode('level')
    walls = []
    spawns = []
    D = DOOR_WIDTH

    # ── R0: 시작(케이지) 로비. 플레이어 (0,0) 가 안쪽이 되도록 남벽 y=-2 ──
    walls += room_walls(-6, 6, -2, 12, doors=[('N', 0, D)])

    # ── R1: 서버실 — 좁고 기둥 엄폐. 좀비 3 ──
    walls += room_walls(-6, 6, 12, 26, doors=[('S', 0, D), ('N', 0, D)])
    walls += pillar(-3, 19)
    walls += pillar(3, 19)
    spawns += [(-3, 16), (3, 22), (0, 24)]

    # ── R2: 실험실 — 넓은 첫 고비. 좀비 4 ──
    walls += room_walls(-9, 9, 26, 40, doors=[('S', 0, D), ('N', 0, D)])
    spawns += [(-6, 31), (6, 31), (-5, 37), (5, 37)]

    # ── R3: 제어실 — 콘솔/복선 방. 좀비 3 ──
    walls += room_walls(-6, 6, 40, 54, doors=[('S', 0, D), ('N', 0, D)])
    walls += pillar(0, 47)
    spawns += [(-3, 45), (3, 45), (0, 51)]

    # ── R4: 격리 구역 — 리빌. 좀비 2 ──
    walls += room_walls(-8, 8, 54, 70, doors=[('S', 0, D)])
    spawns += [(-4, 63), (4, 63)]

    for w in walls:
        w.make_card(root)

    return LevelCollider(walls), spawns
