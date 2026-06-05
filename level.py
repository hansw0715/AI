"""
level.py — zombie_game 연구실 레벨 (방 / 벽 / 충돌 / 색 번짐).

레이아웃 (남→북, 사다리/H 모양) + 진행 규칙
  중앙 긴 복도(spine) + 좌/우 방 2쌍 + 끝의 마지막 방.
  복도는 전진 게이트 2개로 구역이 나뉜다:
    구역0 = 방 1쌍(좌1·우1) → GATE1 (복도 가로막, y=24)
    구역1 = 방 2쌍(좌2·우2) → GATE2 (= 마지막 방 입구, y=47)
  측면 방 입구엔 방화벽 — 부수면 그 방 좀비(백신)가 스폰, 전멸시키면 cleared.
  게이트는 그 구역 양옆 방이 다 cleared 돼야 잠금 해제(부술 수 있게)된다.
  → 양옆 방을 안 비우면 게이트를 못 부수므로 방 입장이 강제됨.
  시작 즉시 스폰 없음 — 케이지 나오면 한동안 조용함.

색 번짐 (메인 시각 장치)
  면역색 = 시설/백신/차단막(미점령).  병변색 = 나/내가 점령한 구역.
  방 전멸·게이트 해제·마지막 방 진입 시 그 바닥 stain 이 면역→병변으로 번짐.
  표면: '정화' / 진실: '감염 점령'. 누적되면 복도 전체가 병변색.
  케이지 stain 은 따로 빼 둠 — 케이지 F 탈출 순간 fade in (patient zero 펀치).

좌표계: Panda3D 표준 Z-up, Y-forward. 모든 단위 m.
사용법: zombie_game.py 의 __init__ 에서 build_level(self.render) 호출.
"""

from math import atan2, degrees, hypot

from panda3d.core import CardMaker


# ── 튜닝 노브 ────────────────────────────────────────────────────────────
WALL_HEIGHT    = 3.0
WALL_THICKNESS = 0.30
WALL_COLOR     = (0.72, 0.74, 0.78, 1.0)
PLAYER_RADIUS  = 0.40
ZOMBIE_RADIUS  = 0.45
DOOR_WIDTH     = 2.4

# 색 번짐 — 게임 전체 색 일관성의 축.
IMMUNE_COLOR = (0.55, 0.85, 0.90)          # 면역색: 시설/백신/차단막
LESION_COLOR = (0.85, 0.25, 0.55)          # 병변색: 나/감염 점령


class Wall:
    """축정렬 벽 한 칸. 중심선 (ax,ay)->(bx,by) + 두께 → footprint 박스.
    height: 벽 높이(m). 충돌(resolve)은 2D 라 무시하지만, 총알 3D 차단·시각 카드는
    이 높이를 쓴다 → 낮은 엄폐물은 위로 넘겨 쏠 수 있다."""
    __slots__ = ('x0', 'x1', 'y0', 'y1', 'ax', 'ay', 'bx', 'by', 'height')

    def __init__(self, ax, ay, bx, by, thickness=WALL_THICKNESS, height=WALL_HEIGHT):
        self.ax, self.ay, self.bx, self.by = ax, ay, bx, by
        self.height = height
        half = thickness * 0.5
        self.x0 = min(ax, bx) - half
        self.x1 = max(ax, bx) + half
        self.y0 = min(ay, by) - half
        self.y1 = max(ay, by) + half

    def make_card(self, parent):
        # 벽 한 칸 — CardMaker 카드는 한쪽 법선만 가져, 라이트가 뒷면에서 오면
        # 그 벽이 검게 칠해진다 (어떤 벽은 밝고 어떤 벽은 어두운 문제의 원인).
        # setTwoSided 는 양면 렌더만 시키고 법선은 그대로라 라이팅 보정이 안 됨.
        # 해결: 카드 두 장을 180° 회전해 등 맞대게 → 각 면의 법선이 바깥을 향함.
        # backface culling 이 카메라 반대쪽 카드를 알아서 숨기고, 라이트는 면이
        # 향한 방향만 비춤 — 양쪽에서 봐도 자연스러운 음영.
        length = hypot(self.bx - self.ax, self.by - self.ay)
        np = parent.attachNewNode('wall')
        np.setPos((self.ax + self.bx) / 2.0, (self.ay + self.by) / 2.0, 0.0)
        np.setH(degrees(atan2(self.by - self.ay, self.bx - self.ax)))
        np.setColor(*WALL_COLOR)

        cm = CardMaker('wall_front')
        cm.setFrame(-length / 2.0, length / 2.0, 0.0, self.height)
        np.attachNewNode(cm.generate())
        cm_b = CardMaker('wall_back')
        cm_b.setFrame(-length / 2.0, length / 2.0, 0.0, self.height)
        back = np.attachNewNode(cm_b.generate())
        back.setH(180)
        return np


def _add(walls, orient, fixed, a, b):
    if b - a < 1e-3:
        return
    if orient == 'h':
        walls.append(Wall(a, fixed, b, fixed))
    else:
        walls.append(Wall(fixed, a, fixed, b))


def room_walls(x0, x1, y0, y1, doors=()):
    """방 4면 벽. doors: (side, center, width). N/S=center 가 x, E/W=center 가 y.
    width 를 그 면 전체 길이 이상으로 주면 그 면이 통째로 개방."""
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

    emit('h', y1, x0, x1, by_side['N'])
    emit('h', y0, x0, x1, by_side['S'])
    emit('v', x1, y0, y1, by_side['E'])
    emit('v', x0, y0, y1, by_side['W'])
    return walls


def _side_room(x0, x1, y0, y1, open_side):
    """복도에 붙는 방 — open_side(복도 쪽 면)는 벽 없이 비움. 복도 벽이 막아 주고
    그 door gap 이 통로가 됨."""
    walls = []
    if open_side != 'N':
        _add(walls, 'h', y1, x0, x1)
    if open_side != 'S':
        _add(walls, 'h', y0, x0, x1)
    if open_side != 'E':
        _add(walls, 'v', x1, y0, y1)
    if open_side != 'W':
        _add(walls, 'v', x0, y0, y1)
    return walls


def pillar(cx, cy, half=0.5, height=WALL_HEIGHT):
    return [
        Wall(cx - half, cy - half, cx + half, cy - half, height=height),
        Wall(cx - half, cy + half, cx + half, cy + half, height=height),
        Wall(cx - half, cy - half, cx - half, cy + half, height=height),
        Wall(cx + half, cy - half, cx + half, cy + half, height=height),
    ]


def _platform_box(parent, x0, x1, y0, y1, top, color=(0.50, 0.54, 0.60, 1.0)):
    """올라탈 수 있는 박스 — 4 옆면 + 윗면 카드. 높이 top(m). 충돌/총알차단은
    호출측(zombie_game)이 footprint+top 으로 처리한다(여긴 시각 메쉬만).
    윗면은 살짝 밝게 해서 '올라설 수 있다'는 걸 시각적으로 알려 준다."""
    np = parent.attachNewNode('platform')

    def quad(name, fr, hpr, pos):
        cm = CardMaker(name)
        cm.setFrame(*fr)
        c = np.attachNewNode(cm.generate())
        c.setHpr(*hpr)
        c.setPos(*pos)
        c.setTwoSided(True)
        return c

    # 옆면 4장 (XZ/YZ 평면). setTwoSided 라 안팎 다 보임.
    quad('pf_s', (x0, x1, 0, top), (0, 0, 0), (0, y0, 0))          # -Y 면
    quad('pf_n', (x0, x1, 0, top), (0, 0, 0), (0, y1, 0))          # +Y 면
    quad('pf_w', (y0, y1, 0, top), (90, 0, 0), (x0, 0, 0))         # -X 면
    quad('pf_e', (y0, y1, 0, top), (90, 0, 0), (x1, 0, 0))         # +X 면
    np.setColor(*color)
    # 윗면 — XY 평면으로 눕히고 top 높이에. 살짝 밝게.
    cm_t = CardMaker('pf_top')
    cm_t.setFrame(x0, x1, y0, y1)
    top_np = np.attachNewNode(cm_t.generate())
    top_np.setHpr(0, -90, 0)
    top_np.setZ(top)
    top_np.setColor(min(1.0, color[0] + 0.12), min(1.0, color[1] + 0.12),
                    min(1.0, color[2] + 0.12), 1.0)
    top_np.setTwoSided(True)
    return np


def _floor_stain(parent, x0, x1, y0, y1, color):
    """바닥 반투명 색 번짐 quad. 처음엔 투명(alpha 0). 런타임이 setColor 로
    alpha 를 올려 면역→병변 점령을 보여준다."""
    cm = CardMaker('stain')
    cm.setFrame(x0, x1, y0, y1)
    np = parent.attachNewNode(cm.generate())
    np.setHpr(0, -90, 0)        # XY 평면으로 눕히기 (ground 와 동일)
    np.setZ(0.02)               # 바닥 살짝 위 — z-fight 방지
    np.setColor(color[0], color[1], color[2], 0.0)
    np.setTransparency(True)
    np.setTwoSided(True)
    np.setLightOff()
    np.setDepthWrite(False)
    return np


class LevelCollider:
    """원(반지름 r) vs 벽 박스 충돌 해소. walls 는 런타임 add/remove 가능 —
    방화벽·게이트가 갭을 막았다 부수면 제거."""

    def __init__(self, walls):
        self.walls = walls

    def segment_blocked(self, x0, y0, x1, y1):
        dx = x1 - x0
        dy = y1 - y0
        for w in self.walls:
            t_near = 0.0
            t_far = 1.0
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
                    d = d2 ** 0.5
                    push = radius - d
                    x += (dx / d) * push
                    y += (dy / d) * push
                else:
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


def build_level(render, draw_wall_cards=True):
    """레벨 생성. (collider, level_data) 반환.

    draw_wall_cards: True 면 level.py 가 단색 벽 카드를 그린다. kit_map.py 로 키트
      메쉬 벽을 입힐 때는 False 로 줘서 z-fighting 을 막는다 (stain/ground 는 유지).

    level_data = {
      'cage_stain': NodePath,             # 케이지 바닥 stain (F 탈출 시 fade in)
      'rooms': [   # 측면 방 — firewall 부수면 spawns 스폰, 전멸 시 cleared
        {'name','zone','firewall':(orient,fixed,lo,hi),'spawns':[...],'stain':NodePath},
      ],
      'gates': [   # 전진 게이트 — zone 의 방 전멸해야 잠금 해제, 부수면 전진
        {'name','zone','barrier':(orient,fixed,lo,hi),'stain':NodePath,
         'room_stain':NodePath|None,'final_spawns':[...]|None},
      ],
    }
      orient 'v'=x=fixed 세로, 'h'=y=fixed 가로. (각 door 갭과 정확히 일치)
    """
    root = render.attachNewNode('level')
    walls = []
    D = DOOR_WIDTH
    h = D / 2.0

    CX0, CX1 = -2.5, 2.5
    CORRIDOR_W = CX1 - CX0
    DOOR_Y1 = 14.0
    DOOR_Y2 = 33.0
    GATE1_Y = 24.0            # 구역0/구역1 사이 복도 가로막
    FINAL_Y = 47.0           # 마지막 방 입구 = GATE2

    # ── 중앙 복도 (y=-3 → 47). 북면 개방 → 마지막 방. ───────────────────────
    walls += room_walls(
        CX0, CX1, -3, FINAL_Y,
        doors=[('W', DOOR_Y1, D), ('W', DOOR_Y2, D),
               ('E', DOOR_Y1, D), ('E', DOOR_Y2, D),
               ('N', 0, CORRIDOR_W)],
    )
    # 시작 케이지 (3면, N 열림)
    walls += [Wall(-1.0, -1.0, 1.0, -1.0), Wall(-1.0, -1.0, -1.0, 1.0),
              Wall(1.0, -1.0, 1.0, 1.0)]

    # ── 측면 방 4개 (벽만) — 더 넓게: 바깥벽 ±19, 1쌍 y[7,22] / 2쌍 y[26,41] ──
    walls += _side_room(-19, CX0, 7, 22, open_side='E')   # 좌1
    walls += _side_room(CX1, 19, 7, 22, open_side='W')    # 우1
    walls += _side_room(-19, CX0, 26, 41, open_side='E')  # 좌2
    walls += _side_room(CX1, 19, 26, 41, open_side='W')   # 우2

    # ── 마지막 방 ──────────────────────────────────────────────────────────
    walls += room_walls(-8, 8, FINAL_Y, 62, doors=[('S', 0, D)])
    walls += pillar(-3, 54)
    walls += pillar(3, 54)

    if draw_wall_cards:
        for w in walls:
            w.make_card(root)

    # ── 색 번짐 stain (바닥) ───────────────────────────────────────────────
    L = LESION_COLOR
    st_w1 = _floor_stain(root, -19, CX0, 7, 22, L)
    st_e1 = _floor_stain(root, CX1, 19, 7, 22, L)
    st_w2 = _floor_stain(root, -19, CX0, 26, 41, L)
    st_e2 = _floor_stain(root, CX1, 19, 26, 41, L)
    st_zone0 = _floor_stain(root, CX0, CX1, 1, GATE1_Y, L)        # 구역0 복도 (케이지 제외)
    st_zone1 = _floor_stain(root, CX0, CX1, GATE1_Y, FINAL_Y, L)  # 구역1 복도
    st_final = _floor_stain(root, -8, 8, FINAL_Y, 62, L)         # 마지막 방
    st_cage = _floor_stain(root, -1, 1, -1, 1, L)               # 케이지 (F 탈출 시)

    level_data = {
        'cage_stain': st_cage,
        'rooms': [
            {'name': 'W1', 'zone': 0, 'firewall': ('v', CX0, DOOR_Y1 - h, DOOR_Y1 + h),
             'spawns': [(-16, 10), (-7, 14), (-15, 20)], 'stain': st_w1},
            {'name': 'E1', 'zone': 0, 'firewall': ('v', CX1, DOOR_Y1 - h, DOOR_Y1 + h),
             'spawns': [(16, 10), (7, 14), (15, 20)], 'stain': st_e1},
            {'name': 'W2', 'zone': 1, 'firewall': ('v', CX0, DOOR_Y2 - h, DOOR_Y2 + h),
             'spawns': [(-16, 29), (-7, 33), (-15, 39)], 'stain': st_w2},
            {'name': 'E2', 'zone': 1, 'firewall': ('v', CX1, DOOR_Y2 - h, DOOR_Y2 + h),
             'spawns': [(16, 29), (7, 33), (15, 39)], 'stain': st_e2},
        ],
        'gates': [
            {'name': 'GATE1', 'zone': 0, 'barrier': ('h', GATE1_Y, CX0, CX1),
             'stain': st_zone0, 'room_stain': None, 'final_spawns': None},
            {'name': 'GATE2', 'zone': 1, 'barrier': ('h', FINAL_Y, -h, h),
             'stain': st_zone1, 'room_stain': st_final,
             'final_spawns': [(-5, 52), (5, 52), (0, 57), (-6, 60), (6, 60)]},
        ],
    }
    return LevelCollider(walls), level_data


def _barrier_shimmer(parent, wall, color=IMMUNE_COLOR, alpha=0.25, height=WALL_HEIGHT):
    """스폰 배리어용 반투명 shimmer 카드 — 벽 중심선을 따라 세운 빛벽 한 장.
    Wall.make_card 와 같은 배치(중심/heading)지만 단색 벽이 아니라 alpha 반투명.
    해제 시 런타임이 이 카드의 setColor alpha 를 0 으로 fade out 한다
    (_floor_stain 의 setColor+Transparency 방식과 동일). 카드 NodePath 반환."""
    length = hypot(wall.bx - wall.ax, wall.by - wall.ay)
    holder = parent.attachNewNode('spawn_barrier_shimmer')
    holder.setPos((wall.ax + wall.bx) / 2.0, (wall.ay + wall.by) / 2.0, 0.0)
    holder.setH(degrees(atan2(wall.by - wall.ay, wall.bx - wall.ax)))
    cm = CardMaker('shimmer')
    cm.setFrame(-length / 2.0, length / 2.0, 0.0, height)
    card = holder.attachNewNode(cm.generate())
    card.setColor(color[0], color[1], color[2], alpha)
    card.setTransparency(True)
    card.setTwoSided(True)
    card.setLightOff()
    card.setDepthWrite(False)
    return card


def build_arena(render, draw_wall_cards=True):
    """1대1 PvP 슈터용 대칭 아레나. (LevelCollider, arena_data) 반환.

    build_level 과 동일한 Wall / LevelCollider / room_walls / pillar 헬퍼와 좌표계
    (Z-up, Y-forward, m)를 그대로 사용한다. 새 충돌 코드는 만들지 않는다 —
    충돌/총알 차단은 호출측이 LevelCollider.resolve / segment_blocked 로 처리.

    레이아웃 (원점 점대칭 — 두 스폰이 완전히 공평):
      외벽 24×36 (x[-12,12], y[-18,18]), 4면 막힘.
      스폰 A (0,-15,yaw0=북향) / 스폰 B (0,15,yaw180=남향).
      엄폐물은 (x,y) 에 두면 (-x,-y) 에도 동일 — 중앙 기둥이 일직선 사거리 차단.

    스폰 배리어(arena_data['spawn_barriers'])는 walls 에 미리 넣지 않는다 —
    런타임이 직접 collider.walls 에 add(가둠) 했다가 5초 후 remove(해제)한다.
    draw_wall_cards 여도 배리어는 단색 벽 카드를 그리지 않고, 대신 반투명 shimmer
    카드(arena_data['shimmer_cards'])만 둬서 해제 시 fade out 한다.
    """
    root = render.attachNewNode('arena')
    walls = []

    # ── 외벽 24m × 36m — 4면 막힘(문 없음). ────────────────────────────────
    walls += room_walls(-12, 12, -18, 18)

    # ── 엄폐물 (원점 점대칭 — (cx,cy) 마다 (-cx,-cy) 자동 추가) ────────────
    # 크기 + 높이 다양: half 0.45~1.0, height 1.3~3.0. 낮은 건 위로 넘겨 쏠 수 있다.
    # (cx, cy, half, height). 중앙(0,0)은 자기대칭이라 한 번만.
    pillar_specs = [
        (0, 0, 1.0, 3.0),     # 중앙 큰 블록(풀높이) — 일직선 사거리 차단(핵심)
        (-9, 1, 0.9, 3.0),    # 측면 큰 블록(풀높이)
        (-10, -4, 0.7, 2.2),  # 코너 중간 — 머리 높이
        (-5, 5, 0.6, 1.6),    # 중간 — 가슴 높이(넘겨 쏘기 가능)
        (-2, -4, 0.5, 1.3),   # 중앙 부근 낮은 엄폐
        (-6, -8, 0.5, 2.0),   # 스폰 앞 엄폐
        (-3, 9, 0.45, 1.4),   # 전방 낮은 엄폐
    ]
    for cx, cy, hf, ht in pillar_specs:
        walls += pillar(cx, cy, hf, ht)
        if (cx, cy) != (0, 0):
            walls += pillar(-cx, -cy, hf, ht)

    # (ax, ay, bx, by, height)
    wall_specs = [
        (-8, 3, -8, -2, 3.0),     # 좌측 세로벽 5m 풀높이
        (2, 7, 7, 7, 1.8),        # 우중 가로벽 5m 낮음
        (-11, 9, -7, 9, 2.4),     # 좌상 가로벽 4m 중간
    ]
    for ax, ay, bx, by, ht in wall_specs:
        walls.append(Wall(ax, ay, bx, by, height=ht))
        walls.append(Wall(-ax, -ay, -bx, -by, height=ht))   # 점대칭 쌍

    if draw_wall_cards:
        for w in walls:
            w.make_card(root)

    # ── 올라탈 수 있는 플랫폼(박스) — 점프로 윗면에 올라설 수 있다. 높이 다양.
    # (x0, x1, y0, y1, top). 충돌/총알차단은 zombie_game 이 footprint+top 으로 처리.
    # 점대칭 쌍으로 둠 — 단, (cx,cy)=(0,0) 박스는 한 번만.
    platform_specs = [
        (-1.5, 1.5, -1.5, 1.5, 0.9),   # 중앙 낮은 단상(자기대칭) — 점프해 올라서기
        (5.5, 8.5, 4.5, 7.5, 1.0),     # 우상 중간 박스(직접 점프) → 점대칭 좌하
        (-9.5, -7.0, 6.0, 9.0, 0.9),   # 좌상 낮은 박스(직접 점프) → 점대칭 우하
        (3.0, 5.5, -10.5, -8.0, 1.8),  # 우하 높은 저격대 → 점대칭 좌상
        (5.5, 7.0, -10.5, -8.0, 0.9),  # ↑ 옆 디딤 스텝(여기서 한 번 더 점프) → 대칭
    ]
    platforms = []
    for x0, x1, y0, y1, top in platform_specs:
        platforms.append({'x0': x0, 'x1': x1, 'y0': y0, 'y1': y1, 'top': top})
        if not (abs(x0 + x1) < 1e-6 and abs(y0 + y1) < 1e-6):   # 원점대칭 아니면 쌍 추가
            platforms.append({'x0': -x1, 'x1': -x0, 'y0': -y1, 'y1': -y0, 'top': top})
    if draw_wall_cards:
        for p in platforms:
            _platform_box(root, p['x0'], p['x1'], p['y0'], p['y1'], p['top'])

    # ── 스폰 배리어 (walls 에 안 넣음 — 런타임이 add/remove) ───────────────
    # 각 스폰을 6m × 6m 포켓으로 가둠: 입구 가로벽 + 좌우 세로벽(x=±3).
    # 포켓 뒤쪽은 외벽(y=±18)이 막아 준다.
    spawn_barriers = [
        # 스폰 A 포켓 (0,-15): 입구 y=-12, 좌우 x=±3 (y[-18,-12])
        Wall(-3, -12, 3, -12),
        Wall(-3, -18, -3, -12),
        Wall(3, -18, 3, -12),
        # 스폰 B 포켓 (0,15): 입구 y=12, 좌우 x=±3 (y[12,18])
        Wall(-3, 12, 3, 12),
        Wall(-3, 12, -3, 18),
        Wall(3, 12, 3, 18),
    ]
    shimmer_cards = []
    if draw_wall_cards:
        for w in spawn_barriers:
            shimmer_cards.append(_barrier_shimmer(root, w))

    arena_data = {
        'spawns': [(0, -15, 0), (0, 15, 180)],   # (x, y, yaw)
        'spawn_barriers': spawn_barriers,         # 런타임이 add/remove
        'shimmer_cards': shimmer_cards,           # 해제 시 fade out
        'platforms': platforms,                   # 올라타는 박스 {x0,x1,y0,y1,top}
        # build_level 호환용 빈 키 (zombie_game._spawn_zombies 가 참조해도 안전).
        'rooms': [],
        'gates': [],
        'cage_stain': None,
    }
    return LevelCollider(walls), arena_data
