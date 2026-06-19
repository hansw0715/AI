"""
level.py — 게임 레벨 (방 / 벽 / 충돌 / 색 번짐).

레이아웃 (남→북, 사다리/H 모양) + 진행 규칙
  중앙 긴 복도(spine) + 좌/우 방 2쌍 + 끝의 마지막 방.
  복도는 전진 게이트 2개로 구역이 나뉜다:
    구역0 = 방 1쌍(좌1·우1) → GATE1 (복도 가로막, y=24)
    구역1 = 방 2쌍(좌2·우2) → GATE2 (= 마지막 방 입구, y=47)
  측면 방 입구엔 방화벽 — 부수면 그 방 적이 스폰, 전멸시키면 cleared.
  게이트는 그 구역 양옆 방이 다 cleared 돼야 잠금 해제(부술 수 있게)된다.
  → 양옆 방을 안 비우면 게이트를 못 부수므로 방 입장이 강제됨.
  시작 즉시 스폰 없음 — 케이지 나오면 한동안 조용함.

색 번짐 (시각 장치)
  기본색 = 미점령 구역.  강조색 = 내가 확보한 구역.
  방 전멸·게이트 해제·마지막 방 진입 시 그 바닥 stain 이 기본→강조색으로 번짐.
  누적되면 복도 전체가 강조색.
  케이지 stain 은 따로 빼 둠 — 케이지 F 탈출 순간 fade in.

좌표계: Panda3D 표준 Z-up, Y-forward. 모든 단위 m.
사용법: zombie_game.py 의 __init__ 에서 build_level(self.render) 호출.
"""

from math import atan2, cos, degrees, hypot, sin

from panda3d.core import (CardMaker, Geom, GeomNode, GeomTriangles,
                          GeomVertexData, GeomVertexFormat, GeomVertexWriter,
                          LineSegs)


# ── 튜닝 노브 ────────────────────────────────────────────────────────────
WALL_HEIGHT    = 9.0     # 벽/천장 높이(m) — 3.0 → 9.0 으로 천장 3배(개방감↑, 모든 모드 공통)
WALL_THICKNESS = 0.30
WALL_COLOR     = (0.72, 0.74, 0.78, 1.0)
PLAYER_RADIUS  = 0.40


def _face_shade(base, nx, ny):
    """면의 바깥 법선(월드 XY: nx,ny)에 따라 base 색을 방향 음영으로 굽는다.
    네 방향(±X/±Y)이 모두 다른 밝기가 되도록 비대칭 계수를 써서, 같은 단색
    장애물이라도 인접한 수직면이 한 면처럼 붙어 보이지 않고 입체감이 생긴다.
    조명과 무관하게 항상 적용 → 어느 각도/조명에서도 모서리가 읽힌다."""
    f = 0.80 + 0.13 * nx + 0.07 * ny          # +X 0.93 / -X 0.67 / +Y 0.87 / -Y 0.73
    return (min(1.0, base[0] * f), min(1.0, base[1] * f),
            min(1.0, base[2] * f), base[3] if len(base) > 3 else 1.0)
ZOMBIE_RADIUS  = 0.45
DOOR_WIDTH     = 2.4

# 색 번짐 — 게임 전체 색 일관성의 축.
IMMUNE_COLOR = (0.55, 0.85, 0.90)          # 기본색: 미점령 구역
LESION_COLOR = (0.85, 0.25, 0.55)          # 강조색: 확보 구역


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
        th = atan2(self.by - self.ay, self.bx - self.ax)
        np = parent.attachNewNode('wall')
        np.setPos((self.ax + self.bx) / 2.0, (self.ay + self.by) / 2.0, 0.0)
        np.setH(degrees(th))
        # 앞/뒤 카드의 바깥 법선(월드 XY) — 벽 진행축에 수직. 면별 방향 음영을 굽어
        # 같은 WALL_COLOR 단색이라 인접 수직벽/박스면이 한 면처럼 붙어 보이던(원근감
        # 없던) 문제를 없앤다.
        nfx, nfy = -sin(th), cos(th)

        cm = CardMaker('wall_front')
        cm.setFrame(-length / 2.0, length / 2.0, 0.0, self.height)
        front = np.attachNewNode(cm.generate())
        front.setColor(*_face_shade(WALL_COLOR, nfx, nfy))
        cm_b = CardMaker('wall_back')
        cm_b.setFrame(-length / 2.0, length / 2.0, 0.0, self.height)
        back = np.attachNewNode(cm_b.generate())
        back.setH(180)
        back.setColor(*_face_shade(WALL_COLOR, -nfx, -nfy))
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

    def quad(name, fr, hpr, pos, nx, ny):
        cm = CardMaker(name)
        cm.setFrame(*fr)
        c = np.attachNewNode(cm.generate())
        c.setHpr(*hpr)
        c.setPos(*pos)
        c.setTwoSided(True)
        c.setColor(*_face_shade(color, nx, ny))   # 면별 방향 음영 → 입체감
        return c

    # 옆면 4장 (XZ/YZ 평면). 각 면을 바깥 법선 방향으로 다르게 음영 — 같은 색이라
    # 인접 수직면이 한 면처럼 붙어 보이던 문제 해결.
    quad('pf_s', (x0, x1, 0, top), (0, 0, 0), (0, y0, 0), 0, -1)   # -Y 면
    quad('pf_n', (x0, x1, 0, top), (0, 0, 0), (0, y1, 0), 0, 1)    # +Y 면
    quad('pf_w', (y0, y1, 0, top), (90, 0, 0), (x0, 0, 0), -1, 0)  # -X 면
    quad('pf_e', (y0, y1, 0, top), (90, 0, 0), (x1, 0, 0), 1, 0)   # +X 면
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
    alpha 를 올려 기본→강조색 번짐을 보여준다."""
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

    def resolve(self, x, y, radius, skip=()):
        for _ in range(2):
            for w in self.walls:
                if skip and w in skip:
                    continue              # 자기 팀 스폰 막 — 통과(다른 팀엔 막힘)
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

    # ── 못 올라가는 엄폐물 (키 큰: height ≥ 2.0). 원점 점대칭 자동 추가.
    # 규칙: 못 올라가는 건 올라가는 플랫폼(≤1.0)보다 반드시 높다(헷갈림 방지).
    # (cx, cy, half, height). 중앙(0,0)은 자기대칭이라 한 번만.
    pillar_specs = [
        (0, 0, 1.0, 3.0),     # 중앙 큰 블록(풀높이) — 일직선 사거리 차단(핵심)
        (-8, 2, 0.8, 2.4),    # 측면 큰 블록
        (-9, -7, 0.7, 2.8),   # 코너 큰 블록
        (-4, -6, 0.7, 2.0),   # 중앙 부근 엄폐
        (10, -6, 0.6, 2.4),   # 측면 엄폐
    ]
    for cx, cy, hf, ht in pillar_specs:
        walls += pillar(cx, cy, hf, ht)
        if (cx, cy) != (0, 0):
            walls += pillar(-cx, -cy, hf, ht)

    # 두꺼운 가림벽 (ax, ay, bx, by, height, thickness=0.7 — 얇지 않게).
    wall_specs = [
        (-6, 7, -1, 7, 2.2, 0.7),    # 상단 가로벽
        (5, 2, 5, -4, 2.0, 0.7),     # 우측 세로벽 6m
    ]
    for ax, ay, bx, by, ht, th in wall_specs:
        walls.append(Wall(ax, ay, bx, by, thickness=th, height=ht))
        walls.append(Wall(-ax, -ay, -bx, -by, thickness=th, height=ht))  # 대칭 쌍

    if draw_wall_cards:
        for w in walls:
            w.make_card(root)

    # ── 올라탈 수 있는 플랫폼(박스) — 점프로 윗면에 올라설 수 있다. 높이 다양.
    # (x0, x1, y0, y1, top). 충돌/총알차단은 zombie_game 이 footprint+top 으로 처리.
    # 점대칭 쌍으로 둠 — 단, (cx,cy)=(0,0) 박스는 한 번만.
    # 올라가는 박스는 전부 낮다(top ≤ 1.0) — 점프로 올라설 수 있고, 위 엄폐물보다 낮음.
    platform_specs = [
        (-9.0, -6.5, 8.0, 10.5, 0.8),   # 좌상 낮은 박스(직접 점프) → 점대칭 우하
        (2.2, 3.6, -4.0, -1.5, 1.0),    # 중앙 우측 박스 → 점대칭 좌측
        (-3.0, -0.5, 9.5, 11.5, 0.9),   # 전방 박스(스폰 근처 엄폐) → 점대칭
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


# 축구 필드 색.
PITCH_GREEN = (0.10, 0.42, 0.18, 1.0)
PITCH_LINE  = (0.92, 0.95, 0.95, 1.0)


def _flat_quad(parent, x0, x1, y0, y1, color, z=0.02, alpha=1.0, name='quad'):
    """바닥(XY 평면)에 눕힌 단색 quad. 필드 잔디/라인 등에 사용. z 로 z-fight 회피."""
    cm = CardMaker(name)
    cm.setFrame(x0, x1, y0, y1)
    np = parent.attachNewNode(cm.generate())
    np.setHpr(0, -90, 0)
    np.setZ(z)
    np.setColor(color[0], color[1], color[2], alpha)
    np.setTwoSided(True)
    np.setLightOff()
    if alpha < 1.0:
        np.setTransparency(True)
        np.setDepthWrite(False)
    return np


def build_soccer_field(render, draw_wall_cards=True):
    """총알 축구용 열린 잔디 필드. (LevelCollider, arena_data) 반환.

    레이아웃 (원점 대칭):
      외벽 24×36 (x[-12,12], y[-18,18]), 4면 막힘 — 공이 벽에 튕긴다.
      장애물 없음(공이 굴러갈 수 있게). 중앙선 + 센터서클 + 골에어리어 마킹.
      골: 북쪽 벽(y=+18) / 남쪽 벽(y=-18), 폭 x[-4,4]. 공이 그 안으로 들어가면 골.
      스폰 A (0,-15) 는 북(+y)을 공격 / 스폰 B (0,15) 는 남(-y)을 공격.
    """
    root = render.attachNewNode('soccer')
    walls = []
    HALF_X, HALF_Y = 12.0, 18.0
    GOAL_HW = 4.0          # 골 폭 절반 (x[-4,4])
    GOAL_DEPTH = 2.4       # 골대가 끝벽 바깥으로 들어가는 깊이(네트 포켓)
    GOAL_H = 2.6           # 골대 높이

    # 외벽 — 양 끝벽(N/S)은 골 입구(폭 2*GOAL_HW)만큼 뚫는다(문). 좌우(E/W)는 막힘.
    outer = room_walls(-HALF_X, HALF_X, -HALF_Y, HALF_Y,
                       doors=[('N', 0, 2 * GOAL_HW), ('S', 0, 2 * GOAL_HW)])
    walls += outer
    if draw_wall_cards:
        for w in outer:
            w.make_card(root)

    # ── 필드 잔디 + 라인 마킹 ──────────────────────────────────────────────
    if draw_wall_cards:
        _flat_quad(root, -HALF_X, HALF_X, -HALF_Y, HALF_Y, PITCH_GREEN, z=0.01,
                   name='pitch')
        # 중앙선 (가로) + 센터 스폿/서클(간이: 얇은 사각 링 4변).
        _flat_quad(root, -HALF_X, HALF_X, -0.12, 0.12, PITCH_LINE, z=0.02,
                   name='midline')
        cr = 3.0   # 센터서클 반지름(간이 사각 링)
        _flat_quad(root, -cr, cr, cr - 0.12, cr, PITCH_LINE, z=0.02, name='cc_n')
        _flat_quad(root, -cr, cr, -cr, -cr + 0.12, PITCH_LINE, z=0.02, name='cc_s')
        _flat_quad(root, -cr, -cr + 0.12, -cr, cr, PITCH_LINE, z=0.02, name='cc_w')
        _flat_quad(root, cr - 0.12, cr, -cr, cr, PITCH_LINE, z=0.02, name='cc_e')
        # 골 에어리어 박스(양 끝) — 폭 x[-6,6], 깊이 4m.
        for sy in (1, -1):
            ay = sy * HALF_Y
            iy = ay - sy * 4.0
            _flat_quad(root, -6, 6, min(ay, iy), max(ay, iy), PITCH_GREEN, z=0.015,
                       name='box')
            _flat_quad(root, -6, 6, iy - 0.12 * sy, iy + 0.12 * sy, PITCH_LINE,
                       z=0.02, name='box_line')

    # ── 골대 포켓 — 끝벽 바깥(y 더 큰 쪽)으로 들어간 골대. 안쪽(위/양옆/뒤)은
    #    불투명 어두운 패널로 맵 바깥(void)을 가리고, 그 앞에 흰 그물선을 그린다. ──
    def shell_card(name, fr, hpr, pos):
        # 불투명 어두운 패널 — 골 포켓 안쪽 면. 맵 바깥이 안 보이게 막는다.
        cm = CardMaker(name)
        cm.setFrame(*fr)
        c = root.attachNewNode(cm.generate())
        c.setHpr(*hpr)
        c.setPos(*pos)
        c.setColor(0.05, 0.06, 0.09, 1.0)
        c.setTwoSided(True)
        c.setLightOff()

    def net_grid(o, du, dv, nu, nv):
        # 흰 그물선 격자 — 모서리 o + 두 변(du, dv)로 만든 사각면에 가로·세로 줄.
        seg = LineSegs('net')
        seg.setThickness(1.4)
        seg.setColor(0.92, 0.96, 1.0, 1.0)
        for i in range(nu + 1):
            f = i / nu
            ax, ay, az = o[0] + du[0] * f, o[1] + du[1] * f, o[2] + du[2] * f
            seg.moveTo(ax, ay, az)
            seg.drawTo(ax + dv[0], ay + dv[1], az + dv[2])
        for j in range(nv + 1):
            f = j / nv
            ax, ay, az = o[0] + dv[0] * f, o[1] + dv[1] * f, o[2] + dv[2] * f
            seg.moveTo(ax, ay, az)
            seg.drawTo(ax + du[0], ay + du[1], az + du[2])
        np_ = root.attachNewNode(seg.create())
        np_.setLightOff()

    for sy in (1, -1):
        mouth_y = sy * HALF_Y
        back_y = sy * (HALF_Y + GOAL_DEPTH)
        mid_y = (mouth_y + back_y) * 0.5
        dy = back_y - mouth_y                  # 포켓 깊이 벡터(부호 포함)
        # 충돌벽 — 양옆(x=±GOAL_HW) + 뒷벽(y=back_y). 시각은 아래 패널/그물로 그림.
        walls.append(Wall(-GOAL_HW, mouth_y, -GOAL_HW, back_y))
        walls.append(Wall(GOAL_HW, mouth_y, GOAL_HW, back_y))
        walls.append(Wall(-GOAL_HW, back_y, GOAL_HW, back_y))
        if not draw_wall_cards:
            continue
        # 불투명 안쪽 패널 — 뒷면 + 양 측면은 천장(WALL_HEIGHT)까지 올려서, 골 안에서
        # 점프해 그물 위로 넘겨봐도 맵 바깥이 안 보이게 한다. 윗면은 월드 천장이 덮음.
        H = WALL_HEIGHT
        shell_card('gs_back', (-GOAL_HW, GOAL_HW, 0.0, H), (0, 0, 0),
                   (0, back_y, 0))
        for sx in (1, -1):
            shell_card('gs_side', (-GOAL_DEPTH / 2, GOAL_DEPTH / 2, 0.0, H),
                       (90, 0, 0), (sx * GOAL_HW, mid_y, 0))
        # 바닥 — 골대 안쪽도 어두운 패널(잔디 살짝 위)로 다른 면과 통일.
        shell_card('gs_floor', (-GOAL_HW, GOAL_HW, min(mouth_y, back_y),
                                max(mouth_y, back_y)), (0, -90, 0), (0, 0, 0.02))
        # 흰 그물선 격자 — 뒷면/양옆/윗면/바닥(패널 살짝 앞에 그려 z-fight 회피).
        net_grid((-GOAL_HW, back_y - sy * 0.05, 0.0), (2 * GOAL_HW, 0, 0),
                 (0, 0, GOAL_H), 8, 5)                                  # 뒷면
        net_grid((-GOAL_HW + 0.05, mouth_y, 0.0), (0, dy, 0),
                 (0, 0, GOAL_H), 5, 5)                                  # 좌측면
        net_grid((GOAL_HW - 0.05, mouth_y, 0.0), (0, dy, 0),
                 (0, 0, GOAL_H), 5, 5)                                  # 우측면
        net_grid((-GOAL_HW, mouth_y, GOAL_H), (2 * GOAL_HW, 0, 0),
                 (0, dy, 0), 8, 5)                                      # 윗면(그물)
        net_grid((-GOAL_HW, mouth_y, 0.05), (2 * GOAL_HW, 0, 0),
                 (0, dy, 0), 8, 5)                                      # 바닥(그물)
        # 골대 프레임(입구) — 흰 포스트 2개 + 크로스바.
        frame = root.attachNewNode('goalframe')
        for sx in (1, -1):
            cm = CardMaker('post')
            cm.setFrame(-0.10, 0.10, 0.0, GOAL_H)
            p = frame.attachNewNode(cm.generate())
            p.setPos(sx * GOAL_HW, mouth_y, 0.0)
            p.setTwoSided(True)
        cm = CardMaker('bar')
        cm.setFrame(-GOAL_HW, GOAL_HW, GOAL_H - 0.12, GOAL_H)
        bar = frame.attachNewNode(cm.generate())
        bar.setPos(0, mouth_y, 0.0)
        bar.setTwoSided(True)
        frame.setColor(0.97, 0.97, 1.0, 1.0)
        frame.setLightOff()
        # 골대 위쪽 벽(상인방) — 골 입구는 GOAL_H 까지만 뚫고, 그 위(GOAL_H~천장)는
        # 끝벽이 그대로 막혀 있게 카드로 채운다(끝벽 색과 동일, 양면).
        cm = CardMaker('lintel')
        cm.setFrame(-GOAL_HW, GOAL_HW, GOAL_H, WALL_HEIGHT)
        lin = root.attachNewNode(cm.generate())
        lin.setPos(0, mouth_y, 0.0)
        lin.setColor(*WALL_COLOR)
        lin.setTwoSided(True)

    # ── 스폰 배리어 (PvP 아레나와 동일 — 킥오프 5초 가둠 후 해제) ────────────
    spawn_barriers = [
        Wall(-3, -12, 3, -12), Wall(-3, -18, -3, -12), Wall(3, -18, 3, -12),
        Wall(-3, 12, 3, 12), Wall(-3, 12, -3, 18), Wall(3, 12, 3, 18),
    ]
    shimmer_cards = []
    if draw_wall_cards:
        for w in spawn_barriers:
            shimmer_cards.append(_barrier_shimmer(root, w))

    arena_data = {
        'spawns': [(0, -15, 0), (0, 15, 180)],   # A=남(북 공격) / B=북(남 공격)
        'spawn_barriers': spawn_barriers,
        'shimmer_cards': shimmer_cards,
        'platforms': [],
        'rooms': [], 'gates': [], 'cage_stain': None,
        # 축구 전용 — 공/골 판정에 사용. 공은 골 입구로 들어가 포켓(깊이 goal_depth)에
        # 갇히고, |y| 가 (half_y + 0.4) 넘으면 득점. y>0 → A, y<0 → B.
        'soccer': {
            'half_x': HALF_X, 'half_y': HALF_Y, 'goal_hw': GOAL_HW,
            'goal_depth': GOAL_DEPTH, 'ball_spawn': (0.0, 0.0),
        },
    }
    return LevelCollider(walls), arena_data


# 땅따먹기(영역 페인트) 셀 기본색 — 중립 회색(아직 아무도 안 칠함).
PAINT_NEUTRAL = (0.30, 0.32, 0.36, 1.0)


def build_jump_field(render, draw_wall_cards=True):
    """점프맵(레이스) 맵. (LevelCollider, arena_data) 반환.

    길쭉한 아레나에 두 플레이어용 '평행한 똑같은 코스'(레인 A/B)를 같은 방향(+y)으로
    둔다. 칸막이는 없어(서로 총으로 쏠 수 있게) 두 레인 사이는 뚫린 낙하 공간. 점프로
    발판을 건너 결승 발판까지 먼저 도달하면 승리. 발판은 build_arena 의 platforms 규약
    ({x0,x1,y0,y1,top}) 을 그대로 쓴다(런타임 충돌/스텝업 재사용).
    """
    root = render.attachNewNode('jump')
    walls = []
    HALF_X, Y0, Y1 = 10.0, -20.0, 44.0
    walls += room_walls(-HALF_X, HALF_X, Y0, Y1)   # 외벽(낙하해도 맵 밖으로 안 나감)
    if draw_wall_cards:
        for w in walls:
            w.make_card(root)

    # 레인 A 코스(x ∈ [-8,-2]) — 발판 다양 + '벽 돌아서 점프' 구간. (x0,x1,y0,y1,top).
    # 레인 B 는 x=0 대칭(-x1,-x0)으로 자동 생성 → 똑같은 평행 코스.
    laneA_plat = [
        (-8.0, -2.0, -18.0, -13.0, 0.3),   # 0 넓은 시작(스폰)
        (-7.0, -3.0, -10.5, -8.0, 0.7),    # 1 일반
        (-8.0, -2.0, -5.5, -1.0, 1.0),     # 2 넓은 발판(벽 우회)
        (-7.0, -3.0, 3.0, 5.5, 0.8),       # 3
        (-5.0, -2.5, 9.0, 11.0, 1.2),      # 4 좁은 빔(오른쪽)
        (-8.0, -5.5, 14.0, 16.5, 1.0),     # 5 왼쪽(지그재그)
        (-8.0, -2.0, 19.5, 23.5, 1.6),     # 6 높은 넓은 블록(벽 우회)
        (-6.0, -3.0, 26.5, 29.0, 1.1),     # 7 내려옴
        (-5.5, -4.0, 31.5, 35.0, 1.4),     # 8 좁은 빔(길게)
        (-8.0, -2.0, 37.5, 43.0, 1.0),     # 9 넓은 결승
    ]
    # 벽(돌아가야 하는 장애물) — 발판 위 가로벽. 높이 3 이라 점프로 못 넘고 옆으로 우회.
    # 발판2(y[-5.5,-1]): 왼쪽 막음 → 오른쪽으로 우회. 발판6(y[19.5,23.5]): 오른쪽 막음 → 왼쪽으로.
    laneA_walls = [(-8.0, -2.5, -4.5, -2.5, 3.0), (-4.5, 21.5, -2.0, 21.5, 3.0)]
    # 봇 경로(레인 A 논리 경로) — 발판 중심 + 벽 우회점. (x, y, z). 레인 B 는 대칭(-x).
    laneA_route = [
        (-5.0, -15.5, 0.3), (-5.0, -9.0, 0.7),
        (-5.0, -4.5, 1.0), (-3.2, -2.0, 1.0),       # 발판2: 들어가서 오른쪽으로 우회
        (-5.0, 4.0, 0.8), (-3.7, 10.0, 1.2), (-6.7, 15.0, 1.0),
        (-5.0, 20.5, 1.6), (-6.7, 22.5, 1.6),       # 발판6: 들어가서 왼쪽으로 우회
        (-4.5, 27.5, 1.1), (-4.7, 33.0, 1.4), (-5.0, 40.0, 1.0),
    ]
    platforms = []
    for (x0, x1, y0, y1, top) in laneA_plat:
        platforms.append({'x0': x0, 'x1': x1, 'y0': y0, 'y1': y1, 'top': top})
        platforms.append({'x0': -x1, 'x1': -x0, 'y0': y0, 'y1': y1, 'top': top})
    # 벽 충돌(양 레인) — 가로벽 한 칸.
    for (ax, ay, bx, by, h) in laneA_walls:
        walls.append(Wall(ax, ay, bx, by, height=h))
        walls.append(Wall(-bx, ay, -ax, by, height=h))   # 레인 B 대칭
    bot_route = [(-x, y, z) for (x, y, z) in laneA_route]  # 봇은 레인 B(대칭)
    if draw_wall_cards:
        for p in platforms:
            t = p['top']
            col = (0.42 + 0.10 * t, 0.50, 0.62 - 0.06 * t, 1.0)
            _platform_box(root, p['x0'], p['x1'], p['y0'], p['y1'], p['top'], col)
        for (ax, ay, bx, by, h) in laneA_walls:        # 벽 카드(양 레인)
            Wall(ax, ay, bx, by, height=h).make_card(root)
            Wall(-bx, ay, -ax, by, height=h).make_card(root)
        _flat_quad(root, -HALF_X, HALF_X, 36.5, 37.5, (1.0, 0.9, 0.2, 1.0), z=0.03,
                   name='finish_line')

    arena_data = {
        'spawns': [(-5.0, -16.0, 0), (5.0, -16.0, 0)],
        'spawn_barriers': [], 'shimmer_cards': [],
        'platforms': platforms,
        'rooms': [], 'gates': [], 'cage_stain': None,
        # 점프맵 — 런타임이 결승/낙하 판정 + 봇 경로에 사용.
        'jump': {
            'finish_y': 39.0,        # 이 y 를 넘으면 도착(승리) — 결승 발판 위
            'start_y': -12.5,        # 이보다 앞(>)에서 바닥(낙하)이면 시작점 복귀
            'spawn_top': 0.3,        # 시작 발판 높이(스폰 z)
            'bot_route': bot_route,  # 봇(레인 B) 웨이포인트 — 벽 우회 포함
        },
    }
    return LevelCollider(walls), arena_data


def _box_walls(x0, x1, y0, y1, h):
    """직사각 박스의 4면 충돌 Wall(둘레). (시각은 페인트 셀로 따로 그림.)"""
    return [Wall(x0, y0, x1, y0, height=h), Wall(x0, y1, x1, y1, height=h),
            Wall(x0, y0, x0, y1, height=h), Wall(x1, y0, x1, y1, height=h)]


def _membrane_card(parent, x0, x1, yfix, height, opaque_toward_y, color):
    """스폰 일방향 막 — 카드 2장(바깥 불투명 + 안쪽 반투명)을 등 맞대 둔다.
    바깥(전장) 면은 불투명이라 밖에선 내부가 안 보이고, 안쪽(스폰) 면은 반투명이라
    안에서 보면 옅은 색 막 너머로 밖이 비친다. 각 카드는 한 면만(뒷면 컬링) 그린다.
    (CardMaker 카드는 H=0 이면 -Y 에서 보이고 H=180 이면 +Y 에서 보임을 실측.)"""
    np = parent.attachNewNode('membrane')
    np.setPos((x0 + x1) / 2.0, yfix, 0.0)
    w = (x1 - x0) / 2.0
    h_field = 180 if opaque_toward_y > 0 else 0      # 바깥면 = 전장 쪽 향함
    h_inner = 0 if opaque_toward_y > 0 else 180      # 안쪽면 = 스폰 내부 향함
    cm = CardMaker('mem_out')
    cm.setFrame(-w, w, 0.0, height)
    outer = np.attachNewNode(cm.generate())
    outer.setH(h_field)
    outer.setColor(color[0], color[1], color[2], 1.0)    # 불투명
    outer.setTwoSided(False)
    cm2 = CardMaker('mem_in')
    cm2.setFrame(-w, w, 0.0, height)
    inner = np.attachNewNode(cm2.generate())
    inner.setH(h_inner)
    inner.setY(-opaque_toward_y * 0.02)                  # 안쪽으로 살짝 — z-fight 방지
    inner.setColor(color[0], color[1], color[2], 0.32)   # 반투명
    inner.setTwoSided(False)
    inner.setTransparency(True)
    return np


def build_paint_field(render, draw_wall_cards=True, cell=1.0):
    """땅따먹기(영역 페인트) 맵. (LevelCollider, arena_data) 반환.

    build_arena 와 같은 좌표계/헬퍼/원점 점대칭. 1:1 PvP 보다 장애물 적게(개방적).
    바닥 + 외벽 안쪽면 + 장애물 표면을 모두 cell×cell 격자로 쪼개 '칠할 수 있는 면'으로
    만든다 — 셀마다 정점 4개를 가진 단일 Geom(V3C4, UHDynamic)이라 런타임은 셀의 정점
    색만 갱신해 가볍게 칠한다. 장애물 풋프린트는 격자에 정렬하고, 그 아래 바닥셀은
    아예 생성하지 않아 벽 때문에 바닥셀이 잘려 보이지 않게 한다.
    arena_data['paint'] 에 셀 리스트(정점 시작인덱스 + 월드 3D 중심)와 vdata 를 담는다.
    """
    root = render.attachNewNode('paint')
    walls = []
    HALF_X, HALF_Y = 12.0, 18.0
    PAINT_WALL_H = 3.0          # 벽/장애물에서 칠해지는(격자화) 높이

    # 외벽 4면(충돌). 경계가 격자에 정렬됨.
    walls += room_walls(-HALF_X, HALF_X, -HALF_Y, HALF_Y)
    # 장애물 박스 — 풋프린트를 정수(격자) 좌표에 맞춤. (x0,x1,y0,y1,height)
    obstacles = [(-1.0, 1.0, -1.0, 1.0, 3.0)]      # 중앙 블록(자기대칭)
    for (x0, x1, y0, y1, h) in [(-7.0, -5.0, 4.0, 6.0, 2.0)]:
        obstacles.append((x0, x1, y0, y1, h))
        obstacles.append((-x1, -x0, -y1, -y0, h))  # 점대칭 쌍
    for (x0, x1, y0, y1, h) in obstacles:
        walls += _box_walls(x0, x1, y0, y1, h)

    # ── 스폰 영역 — 한쪽 벽면 뒤 '전체'(풀폭)를 스폰으로. 정면 벽 1장에 문 3개. ──
    # A=남(y≤FRONT_A) 전부 / B=북(y≥FRONT_B) 전부. 좌우/뒤는 외벽이 막아줘 옆벽 불필요.
    # 정면 벽은 외벽~외벽(풀폭)으로 깔고, 거기에 문(일방향 막) 3개를 넓게 뚫는다.
    SPAWN_WALL_H = 3.5
    FRONT_A, FRONT_B = -12.0, 12.0
    DOOR_HW = 1.0                             # 문 반폭(폭 2.0 — 통과 여유)
    DOOR_CENTERS = (-8.0, 0.0, 8.0)           # 문 중심(풀폭에 넓게 분산)
    mem_spans = [(c - DOOR_HW, c + DOOR_HW) for c in DOOR_CENTERS]
    # 정면 솔리드 구간 = [-HALF_X, HALF_X] 에서 문 구간을 뺀 나머지(문 사이/양끝 벽).
    front_solid = []
    cur = -HALF_X
    for (a, b) in mem_spans:                  # mem_spans 는 x 오름차순
        if a > cur:
            front_solid.append((cur, a))
        cur = b
    if cur < HALF_X:
        front_solid.append((cur, HALF_X))
    spawn_solid = []
    for (px0, px1) in front_solid:            # 정면 솔리드(문 사이/양끝) — A·B 둘 다
        spawn_solid.append(Wall(px0, FRONT_A, px1, FRONT_A, height=SPAWN_WALL_H))
        spawn_solid.append(Wall(px0, FRONT_B, px1, FRONT_B, height=SPAWN_WALL_H))
    walls += spawn_solid

    # 불투명 벽 카드(solid) — 페인트 셀(살짝 앞, 틈 있음) 뒤에 깔아 셀 틈으로 바깥이
    # 뚫려 보이지 않게(틈은 이 벽이 보임). 칠은 앞쪽 셀 정점색으로 따로.
    if draw_wall_cards:
        for w in walls:
            w.make_card(root)

    # 정면 일방향 막 — 전장 쪽으로만 불투명(내부 은폐), 안에선 투과. 충돌/총알엔 막혀도
    # 자기 팀은 통과(런타임 resolve skip). A 막 불투명면 +Y(북=전장), B 막 -Y(남=전장).
    COL_A = (0.16, 0.22, 0.34, 1.0)     # 쿨/블루 — A 스폰
    COL_B = (0.34, 0.20, 0.14, 1.0)     # 웜/오렌지 — B 스폰
    membranes_a = [Wall(mx0, FRONT_A, mx1, FRONT_A, height=SPAWN_WALL_H)
                   for (mx0, mx1) in mem_spans]
    membranes_b = [Wall(mx0, FRONT_B, mx1, FRONT_B, height=SPAWN_WALL_H)
                   for (mx0, mx1) in mem_spans]
    if draw_wall_cards:
        for (mx0, mx1) in mem_spans:
            _membrane_card(root, mx0, mx1, FRONT_A, SPAWN_WALL_H, +1, COL_A)
            _membrane_card(root, mx0, mx1, FRONT_B, SPAWN_WALL_H, -1, COL_B)
    walls += membranes_a + membranes_b

    # ── 페인트 셀(단일 Geom, 정점색). 셀마다 4정점(비공유)으로 독립 칠. ──
    fmt = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData('paint_cells', fmt, Geom.UHDynamic)
    vw = GeomVertexWriter(vdata, 'vertex')
    cw = GeomVertexWriter(vdata, 'color')
    tris = GeomTriangles(Geom.UHDynamic)
    cells = []
    state = {'vi': 0}
    INSET = 0.06                # 셀 사이 띄움 비율(격자선처럼)

    def add_quad(p00, p10, p11, p01):
        # 4 모서리(3D)로 셀 하나 추가. INSET 만큼 중심 쪽으로 줄여 셀 사이 틈을 만든다.
        cx = (p00[0] + p10[0] + p11[0] + p01[0]) * 0.25
        cy = (p00[1] + p10[1] + p11[1] + p01[1]) * 0.25
        cz = (p00[2] + p10[2] + p11[2] + p01[2]) * 0.25
        if cy <= FRONT_A or cy >= FRONT_B:    # 스폰 영역엔 페인트 타일 생성 안 함
            return

        def ins(p):
            return (p[0] + (cx - p[0]) * INSET, p[1] + (cy - p[1]) * INSET,
                    p[2] + (cz - p[2]) * INSET)
        for p in (ins(p00), ins(p10), ins(p11), ins(p01)):
            vw.addData3(*p)
            cw.addData4(*PAINT_NEUTRAL)
        vi = state['vi']
        tris.addVertices(vi, vi + 1, vi + 2)
        tris.addVertices(vi, vi + 2, vi + 3)
        cells.append({'v0': vi, 'cx': cx, 'cy': cy, 'cz': cz, 'owner': 0})
        state['vi'] += 4

    def grid_face(ox, oy, oz, du, dv, nu, nv):
        # origin + du*a + dv*b 격자를 셀로(du,dv = 셀 한 칸 벡터).
        for a in range(nu):
            for b in range(nv):
                bx, by, bz = ox + du[0] * a + dv[0] * b, \
                    oy + du[1] * a + dv[1] * b, oz + du[2] * a + dv[2] * b
                p00 = (bx, by, bz)
                p10 = (bx + du[0], by + du[1], bz + du[2])
                p11 = (bx + du[0] + dv[0], by + du[1] + dv[1], bz + du[2] + dv[2])
                p01 = (bx + dv[0], by + dv[1], bz + dv[2])
                add_quad(p00, p10, p11, p01)

    nx = int(round((2 * HALF_X) / cell))
    ny = int(round((2 * HALF_Y) / cell))
    nz = int(round(PAINT_WALL_H / cell))
    Z = 0.04

    def in_obstacle(px, py):
        for (x0, x1, y0, y1, h) in obstacles:
            if x0 <= px <= x1 and y0 <= py <= y1:
                return True
        return False

    # 바닥 셀 — 장애물 풋프린트 아래는 생략(잘림 방지).
    for j in range(ny):
        for i in range(nx):
            ccx = -HALF_X + (i + 0.5) * cell
            ccy = -HALF_Y + (j + 0.5) * cell
            if in_obstacle(ccx, ccy):
                continue
            x0 = -HALF_X + i * cell
            x1 = x0 + cell
            y0 = -HALF_Y + j * cell
            y1 = y0 + cell
            add_quad((x0, y0, Z), (x1, y0, Z), (x1, y1, Z), (x0, y1, Z))

    # 외벽 안쪽 면 4개(높이 PAINT_WALL_H 까지). 면을 살짝 안으로(0.03) 들여 보이게.
    e = 0.03
    grid_face(-HALF_X, HALF_Y - e, 0.0, (cell, 0, 0), (0, 0, cell), nx, nz)   # 북
    grid_face(-HALF_X, -HALF_Y + e, 0.0, (cell, 0, 0), (0, 0, cell), nx, nz)  # 남
    grid_face(HALF_X - e, -HALF_Y, 0.0, (0, cell, 0), (0, 0, cell), ny, nz)   # 동
    grid_face(-HALF_X + e, -HALF_Y, 0.0, (0, cell, 0), (0, 0, cell), ny, nz)  # 서

    # 장애물 — 윗면 + 4 옆면(높이 min(h, PAINT_WALL_H) 까지).
    for (x0, x1, y0, y1, h) in obstacles:
        cnx = int(round((x1 - x0) / cell))
        cny = int(round((y1 - y0) / cell))
        cnz = int(round(min(h, PAINT_WALL_H) / cell))
        grid_face(x0, y0, h + 0.02, (cell, 0, 0), (0, cell, 0), cnx, cny)      # 윗면
        grid_face(x0, y0 - e, 0.0, (cell, 0, 0), (0, 0, cell), cnx, cnz)       # -Y
        grid_face(x0, y1 + e, 0.0, (cell, 0, 0), (0, 0, cell), cnx, cnz)       # +Y
        grid_face(x0 - e, y0, 0.0, (0, cell, 0), (0, 0, cell), cny, cnz)       # -X
        grid_face(x1 + e, y0, 0.0, (0, cell, 0), (0, 0, cell), cny, cnz)       # +X

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    gnode = GeomNode('paint_grid')
    gnode.addGeom(geom)
    gnp = root.attachNewNode(gnode)
    gnp.setTwoSided(True)
    gnp.setLightOff()

    # 영구 스폰룸(일방향 막)을 쓰므로 임시 스폰 배리어는 없음.
    spawn_barriers = []
    shimmer_cards = []

    arena_data = {
        'spawns': [(0, -15, 0), (0, 15, 180)],   # A=남 / B=북
        'spawn_barriers': spawn_barriers,
        'shimmer_cards': shimmer_cards,
        'platforms': [],
        'rooms': [], 'gates': [], 'cage_stain': None,
        # 스폰룸 — 런타임이 팀별 막 통과(skip) + 10초 캠핑 데미지 존에 사용.
        'spawn_rooms': {
            'membranes_a': membranes_a, 'membranes_b': membranes_b,
            'zone_a': (-HALF_X, HALF_X, -HALF_Y, FRONT_A),   # A 스폰 전체(풀폭)
            'zone_b': (-HALF_X, HALF_X, FRONT_B, HALF_Y),    # B 스폰 전체
        },
        # 땅따먹기 — 런타임이 셀 색 갱신/점유 집계에 사용(셀 중심은 3D).
        'paint': {
            'vdata': vdata, 'cells': cells, 'cell': cell,
            'half_x': HALF_X, 'half_y': HALF_Y, 'ball_spawn': (0.0, 0.0),
        },
    }
    return LevelCollider(walls), arena_data
