"""
kit_map.py — Quaternius "Ultimate Modular Sci-Fi" 키트로 레벨 시각 레이어를 입힌다.

설계 원칙 (중요):
  게임 로직(충돌·스폰·게이트·색번짐)은 level.py 가 만든 그대로 둔다. 이 모듈은
  '보이는 것'만 담당한다 — collider.walls 의 각 충돌선 위에 진짜 sci-fi 벽 메쉬를
  깔고, 바닥 전체를 타일로 덮고, 소품 몇 개를 스토리 지점에 놓는다.
  → 보이는 벽 = 부딪히는 벽 (둘이 같은 collider.walls 에서 나오므로 100% 일치).

스케일 자동 보정:
  blend2bam 이 어떤 스케일/축으로 들여오는지 미리 알 수 없으므로, 로드 직후
  getTightBounds() 로 메쉬 실제 크기를 재서 목표(미터)에 맞춰 스케일을 계산한다.
  → IMPORT_SCALE 같은 매직넘버 없이, 변환 결과가 무엇이든 알아서 맞는다.

전제:
  - 변환된 .bam 들이 KIT_DIR 에 있다 (FloorTile_Basic / Wall_1 / Props_* / Staircase).
  - blend2bam 결과가 Panda3D 표준 Z-up (= blend2bam 기본 동작).
  - 키트 조각은 바닥(Z=0)에 발 딛고 +Z 로 자라며, 가로 중심이 원점 (측정으로 확인됨).

사용법 (zombie_game.py __init__, build_level 호출 직후):
    self.level_collider, self.level_data = build_level(self.render)
    from kit_map import build_kit_visuals
    self.kit_root = build_kit_visuals(self.render, self.level_collider)

그리고 level.py 의  `for w in walls: w.make_card(root)`  한 줄을 주석 처리해서
단색 평면 카드를 끈다 (안 끄면 키트 벽이랑 겹쳐 z-fighting). stain/ground 는 그대로 둔다.

좌표계: Panda3D Z-up, Y-forward, 단위 m.
"""

from math import atan2, degrees, hypot

from panda3d.core import NodePath


# ── 튜닝 노브 ────────────────────────────────────────────────────────────
KIT_DIR        = "assets/kit"   # 변환된 .bam 들이 있는 폴더
TILE_M         = 2.0            # 바닥 타일 한 칸 목표 크기 (m). 키트 네이티브 ≈ 2m
WALL_HEIGHT_M  = 3.2            # 벽 목표 높이 (m). level.py WALL_HEIGHT=3.0 보다 살짝 높여 천장 여유
WALL_THICK_M   = 0.30          # 벽 목표 두께 (m). level.py WALL_THICKNESS 와 맞춤
PLACE_PROPS    = True          # 소품(케이지 포드·콘솔·텔레포터) 배치 여부
PLACE_FLOOR    = True          # 바닥 타일링 여부
FLOOR_PAD      = 1.0           # 바닥을 레벨 경계보다 이만큼 더 깔아 가장자리 빈틈 방지 (m)

# 메쉬가 90° 돌아 들어오면 여기만 만지면 됨 (벽이 옆으로 누우면 90, 거꾸로면 180):
WALL_YAW_FIX   = 0.0


def _size(np):
    """NodePath 의 (sx, sy, sz) 월드 크기를 tight bounds 로 잰다."""
    lo, hi = np.getTightBounds()
    return (hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)


def _load(loader, name):
    """KIT_DIR/name.bam 로드. 실패하면 None (게임이 죽지 않게)."""
    try:
        return loader.loadModel(f"{KIT_DIR}/{name}.bam")
    except Exception as e:
        print(f"[kit_map] '{name}.bam' 로드 실패: {e}")
        return None


def build_kit_visuals(render, collider, loader=None):
    """키트 시각 레이어를 render 아래에 깔고 그 루트 NodePath 를 반환한다.

    collider : level.py 의 LevelCollider — collider.walls 를 그대로 시각화한다.
    loader   : Panda3D loader. None 이면 builtins 의 전역 loader 사용.
    """
    if loader is None:
        import builtins
        loader = builtins.loader

    root = render.attachNewNode("kit_visuals")

    # ── 1. 바닥 타일링 ──────────────────────────────────────────────────
    if PLACE_FLOOR and collider.walls:
        tile = _load(loader, "FloorTile_Basic")
        if tile is not None:
            tw, td, _ = _size(tile)
            native = max(tw, td) or 1.0          # 한 변 길이 (보통 둘이 같음)
            s = TILE_M / native
            # 타일 윗면이 Z≈0 바로 아래 오도록 (stain 은 Z=0.02 → 가려지지 않음)
            _, _, th = _size(tile)
            floor_z = -th * s

            xs = [w.x0 for w in collider.walls] + [w.x1 for w in collider.walls]
            ys = [w.y0 for w in collider.walls] + [w.y1 for w in collider.walls]
            x_min, x_max = min(xs) - FLOOR_PAD, max(xs) + FLOOR_PAD
            y_min, y_max = min(ys) - FLOOR_PAD, max(ys) + FLOOR_PAD

            floor_root = root.attachNewNode("floor")
            x = x_min + TILE_M / 2.0
            while x < x_max:
                y = y_min + TILE_M / 2.0
                while y < y_max:
                    inst = floor_root.attachNewNode("ft")
                    tile.instanceTo(inst)
                    inst.setScale(s)
                    inst.setPos(x, y, floor_z)
                    y += TILE_M
                x += TILE_M

    # ── 2. 벽: collider.walls 의 각 충돌선 위에 메쉬 한 장씩 ─────────────
    wall = _load(loader, "Wall_1")
    if wall is not None:
        ww, wd, wh = _size(wall)
        # 네이티브 가로(긴 수평 축) = ww, 두께 = wd, 높이 = wh
        native_w = ww or 1.0
        native_t = wd or 1.0
        native_h = wh or 1.0
        wall_root = root.attachNewNode("walls")

        sx = native_w  # 가로 native (충돌선 길이로 나중에 나눔)
        for w in collider.walls:
            length = hypot(w.bx - w.ax, w.by - w.ay)
            if length < 1e-3:
                continue
            cx, cy = (w.ax + w.bx) / 2.0, (w.ay + w.by) / 2.0
            base_h = degrees(atan2(w.by - w.ay, w.bx - w.ax)) + WALL_YAW_FIX
            # 키트 Wall_1 은 앞면만 라이팅되는 단면 메쉬 → 그냥 두면 뒷면이 검게
            # 보인다. 같은 모델을 180° 돌린 복제본을 등 맞대 붙여서(앞면이 양쪽
            # 바깥을 향하게) 어느 방향에서 봐도 정상 음영으로 보이게 한다.
            for extra_h in (0.0, 180.0):
                inst = wall_root.attachNewNode("wall")
                wall.instanceTo(inst)
                inst.setScale(length / sx,               # 가로: 충돌선 길이에 맞춤
                              WALL_THICK_M / native_t,    # 두께
                              WALL_HEIGHT_M / native_h)    # 높이
                inst.setPos(cx, cy, 0.0)
                inst.setH(base_h + extra_h)

    # ── 3. 소품 — 방마다 다른 테마로 다채롭게 배치 ──────────────────────────
    # 키트의 native 스케일(≈1m)을 그대로 써서 크레이트 0.8m / 선반 2.5m 처럼 실제
    # 비례를 유지한다. target_h 를 주면 그 키에 맞춰 스케일.
    if PLACE_PROPS:
        prop_root = root.attachNewNode("props")
        _cache = {}

        def place(name, x, y, yaw=0.0, target_h=None, z=0.0):
            m = _cache.get(name)
            if m is None:
                m = _load(loader, name)
                _cache[name] = m
            if m is None:
                return
            inst = prop_root.attachNewNode(name)
            m.instanceTo(inst)
            # 메쉬 원점이 바닥이 아닌 조각(Base·Statue·Pod 등)은 그냥 두면 공중에
            # 뜨거나 바닥에 박힌다. tight bounds 의 바닥(lo.z)을 재서 발을 Z=0 에
            # 정확히 올린다. z 인자는 그 위에 추가로 쌓을 높이.
            lo, hi = m.getTightBounds()
            s = 1.0
            if target_h:
                s = target_h / ((hi.z - lo.z) or 1.0)
                inst.setScale(s)
            inst.setH(yaw)                      # yaw 는 Z축 회전 → 바닥 높이 불변
            inst.setPos(x, y, z - lo.z * s)     # 발을 바닥에 정렬(+z 만큼 쌓기)

        # ── 시작 케이지 = Pod (시각용 메쉬).
        place("Props_Pod", 0.0, 0.0)

        # ── W1 (좌1) — 보급 창고: 선반 + 크레이트 + 컨테이너  (벽: x=-19) ───────
        place("Props_Shelf",        -18.0, 11.0, yaw=90)
        place("Props_Shelf",        -18.0, 18.0, yaw=90)
        place("Props_Crate",        -13.0, 12.5)
        place("Props_Crate",        -12.2, 12.5)
        place("Props_Crate",        -12.6, 12.5, z=0.81)   # 한 칸 위로 쌓기
        place("Props_CrateLong",     -7.0,  9.0, yaw=20)
        place("Props_ContainerFull", -6.0, 20.0, yaw=-15)

        # ── E1 (우1) — 실험실: 캡슐 + 베슬 + 격리 포드 + 콘솔  (벽: x=19) ───────
        place("Props_Pod",           17.0, 14.0)
        place("Props_Capsule",        6.0, 10.0)
        place("Props_Capsule",        6.0, 19.0)
        place("Props_Vessel_Tall",    9.0, 10.0)
        place("Props_Vessel",         9.8, 10.6)
        place("Props_Vessel_Short",   9.3,  9.3)
        place("Props_Computer",      18.0, 20.0, yaw=-90)

        # ── W2 (좌2) — 무기고: 레이저 터렛 + 체스트 + 조각상  (벽: x=-19) ───────
        place("Props_Laser",        -12.0, 33.0, yaw=90)
        place("Props_Chest",        -18.0, 28.0, yaw=90)
        place("Props_Chest",        -18.0, 39.0, yaw=90)
        place("Props_Statue",        -6.0, 33.0, yaw=120)
        place("Props_Crate",         -8.0, 28.0)
        place("Props_CrateLong",     -8.0, 39.0, yaw=90)

        # ── E2 (우2) — 데이터/서버실: 높은 선반 + 소형 콘솔 + 베이스  (벽: x=19) ─
        place("Props_Shelf_Tall",    18.0, 29.0, yaw=-90)
        place("Props_Shelf_Tall",    18.0, 38.0, yaw=-90)
        place("Props_ComputerSmall",  6.0, 28.0)
        place("Props_ComputerSmall",  7.5, 28.0)
        place("Props_Computer",       6.0, 40.0, yaw=170)
        place("Props_Base",          11.0, 33.0)

        # ── 마지막 방 — 리빌: 텔레포터 + 조각상 호위 + 기둥 메쉬 ───────────────
        place("Props_Teleporter_1",   0.0, 58.0)
        place("Props_Statue",        -6.0, 60.0, yaw=20)
        place("Props_Statue",         6.0, 60.0, yaw=-20)
        place("Column_1",            -3.0, 54.0)   # level.py pillar 충돌체와 정렬
        place("Column_1",             3.0, 54.0)

    return root
