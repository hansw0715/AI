"""
level.py — zombie_game 연구실 레벨 (방 / 벽 / 충돌).

설계 요약
  - 방(room) = XY 평면의 축정렬 사각형. room_walls() 가 4면 벽을 만들고
    door 위치는 통로(구멍)로 비운다.
  - 벽(Wall) = 얇은 축정렬 박스. 시각용 2-sided card + 충돌용 footprint AABB.
  - 충돌 = 원(플레이어 반지름) vs 박스. LevelCollider.resolve(x, y, r) 가
    벽을 뚫지 못하게 보정한 (x, y) 를 돌려준다.

레이아웃 (남→북, 사다리/H 모양)
  중앙에 긴 복도(spine)가 세로로 뻗고, 그 좌/우로 방이 가지처럼 붙는다.
  복도를 따라 방 2쌍(좌1·우1 / 좌2·우2)을 지나, 복도 끝에서 넓은 마지막
  방(출구 전 / 리빌)으로 이어진다.

방화벽(firewall) / 스폰
  각 방 입구 door 는 처음엔 그냥 '뚫린 통로'로 둔다 (벽이 없는 구간). 방화벽은
  런타임(zombie_game.Firewall)에서 그 door 갭을 막는 파괴형 배리어로 생성되고,
  부수면 통로가 열리며 그 방 좀비가 그제서야 스폰된다. build_level 은 방화벽의
  '위치 스펙'과 '그 방 좀비 스폰 좌표'만 level_data 로 넘긴다 — 즉시 스폰되는 건
  복도 정찰병(start_spawns)뿐이라 한꺼번에 14마리가 돌지 않아 과부하가 없다.

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
        (N/S 면은 center 가 x 좌표, E/W 면은 center 가 y 좌표)
      width 를 그 면 전체 길이 이상으로 주면 그 면 벽이 통째로 사라짐 (완전 개방).
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


def _side_room(x0, x1, y0, y1, open_side):
    """복도에 가지처럼 붙는 방. open_side(복도 쪽 면)는 벽을 만들지 않는다 —
    복도 벽이 그 면을 막아 주고, 복도 벽에 뚫어 둔 door gap 이 통로가 된다.
    덕분에 경계에 벽이 이중으로 겹치지 않는다.

    open_side: 'N' / 'S' / 'E' / 'W' — 비울 면 (복도를 마주보는 면).
    """
    walls = []
    if open_side != 'N':
        _add(walls, 'h', y1, x0, x1)   # 북
    if open_side != 'S':
        _add(walls, 'h', y0, x0, x1)   # 남
    if open_side != 'E':
        _add(walls, 'v', x1, y0, y1)   # 동
    if open_side != 'W':
        _add(walls, 'v', x0, y0, y1)   # 서
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
    """원(반지름 r) vs 모든 벽 박스 충돌 해소.

    walls 는 런타임에 추가/제거 가능 — Firewall 이 도어 갭을 막는 벽을 append
    했다가 파괴 시 remove 한다.
    """

    def __init__(self, walls):
        self.walls = walls

    def segment_blocked(self, x0, y0, x1, y1):
        """선분 (x0,y0)→(x1,y1) 이 어느 벽 박스든 가로지르면 True.

        좀비 시야 차폐용 — 벽 너머 플레이어를 인지·추격하지 못하게. 표준 slab 방식
        2D 선분 vs AABB 교차 검사. 도어/케이지 N면처럼 '벽이 없는' 구간은 자연히
        통과 (그 영역에 wall 박스 자체가 없음).
        """
        dx = x1 - x0
        dy = y1 - y0
        for w in self.walls:
            t_near = 0.0
            t_far = 1.0
            # X 슬랩
            if abs(dx) < 1e-9:
                if x0 < w.x0 or x0 > w.x1:
                    continue
            else:
                t1 = (w.x0 - x0) / dx
                t2 = (w.x1 - x0) / dx
                if t1 > t2:
                    t1, t2 = t2, t1
                if t1 > t_near:
                    t_near = t1
                if t2 < t_far:
                    t_far = t2
                if t_near > t_far:
                    continue
            # Y 슬랩
            if abs(dy) < 1e-9:
                if y0 < w.y0 or y0 > w.y1:
                    continue
            else:
                t1 = (w.y0 - y0) / dy
                t2 = (w.y1 - y0) / dy
                if t1 > t2:
                    t1, t2 = t2, t1
                if t1 > t_near:
                    t_near = t1
                if t2 < t_far:
                    t_far = t2
                if t_near > t_far:
                    continue
            return True
        return False

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
    """레벨을 render 아래에 생성. (collider, level_data) 반환.

    level_data = {
      'start_spawns': [(x, y), ...],   # 게임 시작 시 즉시 스폰 (복도 정찰병)
      'rooms': [
        {'name': 'W1',
         'firewall': (orient, fixed, lo, hi),   # 도어 갭을 막는 방화벽 위치
         'spawns':   [(x, y), ...]},            # 방화벽 부수면 스폰할 좀비
        ...
      ],
    }
      firewall: orient 'v' → x=fixed 세로 배리어, y∈[lo,hi].
                orient 'h' → y=fixed 가로 배리어, x∈[lo,hi].
                (각 door 갭과 정확히 일치 — center±width/2)

    숫자만 바꾸면 방 크기/위치 조정. F2 free-cam 으로 좌표 보면서 튜닝.
    """
    root = render.attachNewNode('level')
    walls = []
    D = DOOR_WIDTH
    h = D / 2.0                # door 갭 반폭

    # 복도(spine) X 범위 — 좌/우 방이 이 벽(x=CX0 / x=CX1)에 door 로 붙는다.
    CX0, CX1 = -2.5, 2.5
    CORRIDOR_W = CX1 - CX0      # 5.0 — 북면 완전 개방용 (door width 로 사용)
    DOOR_Y1 = 14.0             # 방 1쌍 (좌1·우1) door 중심
    DOOR_Y2 = 33.0             # 방 2쌍 (좌2·우2) door 중심
    FINAL_Y = 47.0             # 마지막 방 남벽 (= 복도 끝)

    # ── 중앙 복도 (남 y=-3 → 북 y=47) ─────────────────────────────────────
    walls += room_walls(
        CX0, CX1, -3, FINAL_Y,
        doors=[
            ('W', DOOR_Y1, D), ('W', DOOR_Y2, D),
            ('E', DOOR_Y1, D), ('E', DOOR_Y2, D),
            ('N', 0, CORRIDOR_W),      # 북면 통째 개방 → 마지막 방으로
        ],
    )
    # 시작 케이지(격리체 보관함): 3면. N 열림 (F 게이트는 나중에, story §1.3).
    walls += [
        Wall(-1.0, -1.0,  1.0, -1.0),   # 케이지 S
        Wall(-1.0, -1.0, -1.0,  1.0),   # 케이지 W
        Wall( 1.0, -1.0,  1.0,  1.0),   # 케이지 E
    ]
    # 긴 복도 중간 엄폐 기둥 (방 두 쌍 사이) — 일자 사선 차단.
    walls += pillar(0, 23.5)

    # ── 방 4개 (벽만; 좀비/방화벽은 level_data 로) ─────────────────────────
    walls += _side_room(-15, CX0, 8, 20, open_side='E')   # 좌1
    walls += _side_room(CX1, 15, 8, 20, open_side='W')    # 우1
    walls += _side_room(-15, CX0, 27, 39, open_side='E')  # 좌2
    walls += _side_room(CX1, 15, 27, 39, open_side='W')   # 우2

    # ── 마지막 방 (출구 전 / 리빌). 남벽 door, 북벽=출구(예정) ───────────────
    walls += room_walls(-8, 8, FINAL_Y, 62, doors=[('S', 0, D)])
    walls += pillar(-3, 54)
    walls += pillar(3, 54)

    for w in walls:
        w.make_card(root)

    level_data = {
        # 복도 정찰병 — 케이지에서 좀 떨어진 안쪽(y=11)에 둬서 바로 안 붙음.
        'start_spawns': [(-1.5, 11), (1.5, 11)],
        'rooms': [
            {'name': 'W1', 'firewall': ('v', CX0, DOOR_Y1 - h, DOOR_Y1 + h),
             'spawns': [(-10, 12), (-7, 17)]},
            {'name': 'E1', 'firewall': ('v', CX1, DOOR_Y1 - h, DOOR_Y1 + h),
             'spawns': [(10, 12), (7, 17)]},
            {'name': 'W2', 'firewall': ('v', CX0, DOOR_Y2 - h, DOOR_Y2 + h),
             'spawns': [(-11, 31), (-7, 36), (-10, 35)]},
            {'name': 'E2', 'firewall': ('v', CX1, DOOR_Y2 - h, DOOR_Y2 + h),
             'spawns': [(11, 31), (7, 36), (10, 35)]},
            {'name': 'FINAL', 'firewall': ('h', FINAL_Y, -h, h),
             'spawns': [(-5, 58), (5, 58)]},
        ],
    }
    return LevelCollider(walls), level_data
