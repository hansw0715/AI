"""
zombie_game — Mirror's Edge 풍 1인칭 택티컬 슈터 (Panda3D)
Stage 1: 1인칭 카메라 + Y Bot 풀바디 + 기본 입력.
"""
import atexit
import json
import math
import random
import socket
import struct
import sys
import threading
import time
from collections import deque
from math import atan2, ceil, cos, degrees, radians, sin
from pathlib import Path

from direct.actor.Actor import Actor
from direct.gui.DirectGui import DirectButton, DirectEntry, DirectFrame, DirectSlider
from direct.gui import DirectGuiGlobals as DGG
from direct.gui.OnscreenImage import OnscreenImage
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from direct.interval.IntervalGlobal import (
    Func, LerpColorScaleInterval, LerpPosInterval, LerpScaleInterval,
    Parallel, Sequence, Wait,
)
from panda3d.core import (
    AmbientLight, BitMask32, CardMaker, ClockObject, ColorBlendAttrib, CullFaceAttrib,
    DirectionalLight, Filename,
    Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    LineSegs, NodePath, PerspectiveLens, PNMImage, Quat, Spotlight, TextNode,
    Texture, Triangulator,
    Vec3, Vec4, WindowProperties, loadPrcFileData,
)

from level import (PLAYER_RADIUS, ZOMBIE_RADIUS, WALL_HEIGHT, Wall,
                   IMMUNE_COLOR, LESION_COLOR, build_level, build_arena,
                   build_soccer_field, build_paint_field, build_jump_field,
                   LevelCollider)
from weapon_config import (
    WEAPON_LOCAL_SCALE, WEAPON_LOCAL_POS, WEAPON_LOCAL_HPR, WEAPON_MUZZLE_POS,
    RIFLE_LOCAL_SCALE, RIFLE_LOCAL_POS, RIFLE_LOCAL_HPR, RIFLE_MUZZLE_POS,
    RIFLE_LOCAL_PREROT, WEAPON_BODY_OFFSET, WEAPON_BODY_HPR, WEAPON_ADS_OFFSET,
    WEAPON_SPRAY)

# ── 성능 PRC: GPU 스키닝 ────────────────────────────────────────────────────
# 적 14마리 × Mixamo 본 67개 × CPU 정점 변환 매 프레임 = 화각에 적 많을 때 FPS 폭락.
# 두 플래그를 같이 켜면 본 매트릭스만 GPU 에 보내고 vertex skinning 은 GPU shader 가 처리:
#   hardware-animated-vertices : vertex animation 을 GPU 로
#   matrix-palette             : 본 매트릭스 팔레트 (per-vertex 최대 4본) 전송 활성화
# ShowBase 인스턴스 만들기 전에 적용돼야 효과 — 모듈 import 시점 (지금) 에 로딩.
loadPrcFileData('', 'hardware-animated-vertices #t')
loadPrcFileData('', 'matrix-palette #t')

# ── 한글 폰트 ─────────────────────────────────────────────────────────────
# Panda3D 기본 폰트엔 한글 글리프가 없어 OnscreenText / TextNode / DirectGui 에
# 들어간 한글이 □ 로 깨진다. text-default-font 를 PRC 로 등록하면 ShowBase 가
# 만들어지며 자동으로 이 폰트를 기본으로 쓴다 (위젯별 명시 지정 불필요).
# 폰트는 '온글잎 긍정' (레포 루트의 온글잎 긍정.ttf). 한글 + 영문 + 숫자 글리프
# 다 포함. 그게 없으면 fallback 으로 윈도우 맑은 고딕(malgun.ttf) 을 쓴다.
_FONT_BUNDLED = Path(__file__).parent / '온글잎 긍정.ttf'
_FONT_FALLBACK = Path('C:/Windows/Fonts/malgun.ttf')
_FONT_PATH = _FONT_BUNDLED if _FONT_BUNDLED.exists() else _FONT_FALLBACK
loadPrcFileData('', f'text-default-font {_FONT_PATH.as_posix()}')

# ── 그림자 ───────────────────────────────────────────────────────────────
# 키라이트 그림자 패스(깊이맵)에 렌더될 객체를 거르는 카메라 마스크. 평평한 바닥·
# 천장 카드는 이 비트에서 숨겨 '그림자를 던지지' 않게 한다(천장이 맵 전체를 가리는
# 사태 방지). 캐릭터·벽·플랫폼 등 나머지는 기본값(전 비트 켜짐)이라 그대로 캐스팅.
# 그림자를 '받는' 것(메인 셰이딩 패스)은 이 마스크와 무관하므로 바닥도 그림자를 받는다.
SHADOW_CASTER_MASK = BitMask32.bit(1)


# ── HUD 색 ──────────────────────────────────────────────────────────────
# 평소 시안 톤, 글리치 연출(기본 비활성) 시 잠깐 빨강으로 깜빡인다.
HUD_CYAN       = (0.25, 0.88, 1.00, 1.0)   # 표면 액센트
HUD_CYAN_DIM   = (0.43, 0.66, 0.72, 1.0)   # 표면 보조 라벨
HUD_WHITE      = (0.92, 0.98, 1.00, 1.0)   # 큰 숫자
HUD_RED        = (1.00, 0.18, 0.33, 1.0)   # 레드 액센트 (글리치)
HUD_RED_DIM    = (0.88, 0.34, 0.43, 1.0)   # 레드 보조 라벨
HUD_PANEL      = (0.024, 0.070, 0.100, 0.78)
HUD_PANEL_RED  = (0.090, 0.016, 0.030, 0.82)
HUD_ENEMY      = (1.00, 0.39, 0.48, 1.0)   # 적 타겟 정보 (표면에서도 빨강 — "위협")
# 시안 PNG → 빨강 글리치 변환용 setColorScale 값.
# 시안 픽셀 (R≈0.25, G≈0.88, B≈1.0) × (4.0, 0.20, 0.30) → 클램프 후 ≈ (1.0, 0.18, 0.30) 빨강.
# 셰이더에서 곱셈 후 프레임버퍼 쓰기 단계에서 [0,1] 클램프되는 걸 활용.
HUD_TINT_CYAN  = (1.00, 1.00, 1.00, 1.0)
HUD_TINT_RED   = (4.00, 0.20, 0.30, 1.0)
# 반투명 하얀색 — 콤보 게이지 + 탄약 카운터용.
HUD_WHITE_TRANS     = (1.00, 1.00, 1.00, 0.55)   # 텍스트/프레임 (반투명 흰)
HUD_WHITE_TRANS_DIM = (1.00, 1.00, 1.00, 0.28)   # 보조/배경 (더 옅게)
# 시안 PNG(≈0.25,0.88,1.0)를 곱셈으로 흰색화 + 알파 0.55 → 반투명 흰.
HUD_TINT_WHITE_TRANS = (4.00, 1.14, 1.00, 0.55)
# 발로란트 스타일 킬배너 — 전부 흰색(#f2f6f7) + 어두운 원반(#02090c).
KB_WHITE = (0.949, 0.965, 0.969, 1.0)
KB_DISC  = (0.008, 0.035, 0.047, 1.0)

# HUD 전체 크기 배율. 한 값으로 모든 HUD 요소를 키우거나 줄인다.
# 코너(배너/무결성/카트리지/미니맵/카운터)는 스케일 컨테이너로, 중앙(조준점/적
# 타겟/F 프롬프트/메시지)은 개별 scale 에 곱해 일괄 적용. 너무 크면 1.4, 작으면 1.8.
HUD_SCALE = 1.6

# 글리치(HUD 가 잠깐 빨강으로 깜빡이는 연출) ON/OFF. 현재 비활성.
GLITCH_ENABLED = False

# HUD 라벨 텍스트.
GLITCH_LABELS = {
    'system':    ('SYSTEM // OPS v3.1', 'SYSTEM // OPS v3.1'),
    'status':    ('\u25cf 시스템 정상', '\u25cf 시스템 정상'),
    'kills_lbl': ('처치', '처치'),
    'integ_lbl': ('체력', '체력'),
    'ammo_lbl':  ('탄창', '탄창'),
    'zone_lbl':  ('구역', '구역'),
    'interact':  ('[F] 상호작용', '[F] 상호작용'),
}


SCRIPT_DIR = Path(__file__).parent

# 적 테두리(아웃라인) 색 팔레트 — 시작 메뉴에서 고른다. (이름, RGBA)
OUTLINE_PALETTE = [
    ('빨강', (1.00, 0.05, 0.12, 1.0)),
    ('주황', (1.00, 0.45, 0.05, 1.0)),
    ('노랑', (1.00, 0.92, 0.10, 1.0)),
    ('초록', (0.20, 1.00, 0.28, 1.0)),
    ('하늘', (0.20, 0.85, 1.00, 1.0)),
    ('분홍', (1.00, 0.30, 0.80, 1.0)),
    ('흰색', (1.00, 1.00, 1.00, 1.0)),
]
# 설정 파일(JSON) — 고른 테두리 색을 저장해 게임 재시작(메인 복귀) 후에도 유지.
SETTINGS_PATH = SCRIPT_DIR / 'settings.json'


# ── 발로란트풍 택티컬 UI 키트 (게임 ui제작.zip / tactical.css 디자인 이식) ──────
# 웹 디자인 토큰을 Panda3D 좌표/색으로 옮긴 것. "한 키트 · 한 액센트 · 날카로운
# 노치 형태 · 단호한 클립인 모션." 메뉴/타이틀/일시정지가 이 키트에서 파생된다.
def _hexc(s, a=1.0):
    """'#RRGGBB' → Panda3D (r,g,b,a) 0~1 튜플."""
    s = s.lstrip('#')
    return (int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0,
            int(s[4:6], 16) / 255.0, a)

# 컬러 토큰 (tactical.css :root 값 그대로). 액센트는 시그널 레드 딱 하나.
TAC_BG_DEEP    = _hexc('#0E0F12')      # 가장 깊은 배경
TAC_BG_SURF    = _hexc('#181A20')      # 패널/서피스
TAC_SURF_TOP   = _hexc('#21242D')      # 호버/선택 윗단
TAC_LINE       = _hexc('#2E323C')      # 라인/디바이더
TAC_TEXT_1     = _hexc('#ECEDEF')      # 1차 텍스트
TAC_TEXT_2     = _hexc('#878D99')      # 2차(라벨/캡션)
TAC_TEXT_3     = _hexc('#5B616D')      # 3차(흐림)
TAC_ACCENT     = _hexc('#E5403B')      # 시그널 레드 — 유일한 액센트
TAC_ACCENT_DIM = _hexc('#8F2C2A')
TAC_STEEL      = _hexc('#6B7480')      # 콜드 스틸(중립/상대) — 절대 빛나지 않음

# 디자인(tactical.css)이 쓰는 폰트 3종 — Google Fonts. 없으면 Bahnschrift 로 폴백.
#   hero    = Anton   : 초대형 타이틀(PROJECT NULL) — .hero
#   display = Oswald  : 메뉴명/숫자(탄약·체력·점수·번호) — .num / .name
#   label   = Archivo : 라벨/캡션/힌트/태그 — .label / .label-sm
TAC_FONT_DIR = SCRIPT_DIR / 'assets' / 'fonts'
TAC_FONT_HERO_PATH    = TAC_FONT_DIR / 'Anton.ttf'
TAC_FONT_DISPLAY_PATH = TAC_FONT_DIR / 'Oswald.ttf'
TAC_FONT_LABEL_PATH   = TAC_FONT_DIR / 'Archivo.ttf'
TAC_FONT_FALLBACK     = Path('C:/Windows/Fonts/bahnschrift.ttf')


def _notch_pts(l, r, b, t, notch, corners):
    """한쪽(또는 여러) 모서리를 45° 잘라낸(chamfer) 직사각형의 정점들을 시계방향으로.
    corners 는 {'tl','tr','br','bl'} 부분집합. 발로란트 형태 언어의 핵심."""
    n = notch
    pts = []
    pts += [(l, t - n), (l + n, t)] if 'tl' in corners else [(l, t)]
    pts += [(r - n, t), (r, t - n)] if 'tr' in corners else [(r, t)]
    pts += [(r, b + n), (r - n, b)] if 'br' in corners else [(r, b)]
    pts += [(l + n, b), (l, b + n)] if 'bl' in corners else [(l, b)]
    return pts


def _tac_fill(parent, l, r, b, t, color, notch=0.0, corners=()):
    """노치 직사각형을 단색으로 채운 Geom NodePath. (볼록 다각형 → 삼각형 부채꼴)"""
    pts = _notch_pts(l, r, b, t, notch, corners)
    vdata = GeomVertexData('tac_fill', GeomVertexFormat.getV3(), Geom.UHStatic)
    vdata.setNumRows(len(pts))
    vw = GeomVertexWriter(vdata, 'vertex')
    for (x, z) in pts:
        vw.addData3(x, 0, z)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(1, len(pts) - 1):
        tris.addVertices(0, i, i + 1)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode('tac_fill')
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setColor(*color)
    np.setTwoSided(True)
    np.setTransparency(True)
    np.setLightOff()
    return np


def _tac_tri_right(parent, cx, cz, s, color):
    """오른쪽을 가리키는 작은 채워진 삼각형(버튼 화살표). ▸ 글리프가 폰트에 없어 대체."""
    vdata = GeomVertexData('tri', GeomVertexFormat.getV3(), Geom.UHStatic)
    vw = GeomVertexWriter(vdata, 'vertex')
    vw.addData3(cx - s, 0, cz + s)
    vw.addData3(cx + s, 0, cz)
    vw.addData3(cx - s, 0, cz - s)
    tris = GeomTriangles(Geom.UHStatic)
    tris.addVertices(0, 1, 2)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode('tri')
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setColor(*color)
    np.setTwoSided(True)
    np.setTransparency(True)
    np.setLightOff()
    return np


def _tac_outline(parent, l, r, b, t, color, notch=0.0, corners=(), thickness=1.6):
    """노치 직사각형의 1px 라인 프레임."""
    pts = _notch_pts(l, r, b, t, notch, corners)
    ls = LineSegs('tac_outline')
    ls.setThickness(thickness)
    ls.setColor(*color)
    ls.moveTo(pts[0][0], 0, pts[0][1])
    for (x, z) in pts[1:]:
        ls.drawTo(x, 0, z)
    ls.drawTo(pts[0][0], 0, pts[0][1])
    np = parent.attachNewNode(ls.create())
    np.setLightOff()
    np.setTransparency(True)
    return np


def _parse_svg_points(d):
    """단순 SVG path(d) → 절대좌표 (x, y) 폴리곤 점 리스트. M/H/V/L/C/Z 만 지원
    (HUD 무기 실루엣용). C(3차 베지어)는 6등분 샘플링. 좌표계는 SVG 그대로(아래로 +y)."""
    import re
    toks = re.findall(r'[MHVLCZ]|-?\d+\.?\d*', d)
    pts = []
    i = 0
    cx = cz = 0.0
    cmd = None
    while i < len(toks):
        t = toks[i]
        if t in 'MHVLCZ':
            cmd = t
            i += 1
            if cmd == 'Z':
                break
            continue
        if cmd in ('M', 'L'):
            cx, cz = float(toks[i]), float(toks[i + 1]); i += 2
            pts.append((cx, cz))
        elif cmd == 'H':
            cx = float(toks[i]); i += 1
            pts.append((cx, cz))
        elif cmd == 'V':
            cz = float(toks[i]); i += 1
            pts.append((cx, cz))
        elif cmd == 'C':
            x1, y1 = float(toks[i]), float(toks[i + 1])
            x2, y2 = float(toks[i + 2]), float(toks[i + 3])
            ex, ey = float(toks[i + 4]), float(toks[i + 5]); i += 6
            for s in range(1, 7):
                u = s / 6.0
                m = 1.0 - u
                bx = (m * m * m * cx + 3 * m * m * u * x1
                      + 3 * m * u * u * x2 + u * u * u * ex)
                by = (m * m * m * cz + 3 * m * m * u * y1
                      + 3 * m * u * u * y2 + u * u * u * ey)
                pts.append((bx, by))
            cx, cz = ex, ey
        else:
            i += 1
    return pts


def _load_settings():
    try:
        with open(SETTINGS_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _load_outline_color():
    c = _load_settings().get('outline_color')
    if isinstance(c, (list, tuple)) and len(c) == 4:
        return tuple(c)
    return OUTLINE_PALETTE[0][1]   # 기본 빨강


def _save_outline_color(color):
    data = _load_settings()
    data['outline_color'] = list(color)
    try:
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception as e:
        print('[settings] 저장 실패:', e, flush=True)


# Quaternius sci-fi 키트 시각 레이어 사용 여부. False = 기본 맵(level.py 단색 벽).
USE_KIT_MAP = False
BAM_PATH = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'ybot' / 'scene.bam')
)
WEAPON_PATH = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'weapons' / '9mm_pistol.bam')
)

# 권총 attach knob.
#   WEAPON_WORLD_SIZE : 권총의 world 기준 절대 길이 (m). 모델 size 2.21m 가 이
#                       값으로 normalize. Mixamo hand 본의 cm 단위 스케일 잔재를
#                       무시하려 setScale(self.render, ...) 사용.
#   WEAPON_LOCAL_POS  : hand 본 좌표계 기준 권총 위치. hand 본 자체가 cm 단위라
#                       작은 값이 큰 효과 — 0.01 이면 1cm 정도.
#   WEAPON_LOCAL_HPR  : hand 본 좌표계 기준 회전 (H,P,R degree).
# F2 디버그 카메라로 보면서 미세조정.
# 무기/보이는 몸 배치 튜닝 상수는 weapon_config.py 로 분리 (상단 import 참고).
# 게임 중 튜닝(B/화살표/[ ];', .=회전, P=출력)으로 찾은 값을 거기 박아둠.

# 소총 총구 위치 마커 하네스 로드 여부. True 면 게임 중 L 키로 마커 켜고 끔
# (muzzle_marker.py). 튜닝 다 끝나면 False 로 두면 L 토글도 사라짐.
ENABLE_MUZZLE_MARKER = True

# 소총 모델 경로 — Filename/SCRIPT_DIR 의존이라 본체에 유지 (튜닝 숫자값 아님).
RIFLE_PATH = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'weapons' / 'low-poly_armalite_ar-10.glb')
)

# ── 온라인(1:1 멀티) 릴레이 서버 ───────────────────────────────────────────
# 'python zombie_game.py --online' 일 때만 이 서버에 바깥으로 TCP 접속한다.
# 서버는 raw 바이트 중계기(NAT 통과/포트포워딩 불필요) — 한쪽이 보낸 고정크기
# 프레임을 그대로 반대쪽에 흘려준다. 프레이밍/언패킹은 클라(여기)가 책임짐.
# Fly 에 배포한 릴레이(앱 tcp-relay-1v1, dedicated v4) — 포트는 8080.
RELAY_HOST = "37.16.31.147"
RELAY_PORT = 8080
# 내 상태 패킷 포맷: (pos.x, pos.y, pos.z, yaw, pitch, weapon_idx).
# '<5fBBBHBI' = float32 ×5 + uint8 ×3 + uint16 ×1 + uint8 ×1 + uint32 ×1 = 30바이트.
#   floats: x, y, z, yaw, pitch
#   bytes : widx(0=권총 1=소총), reloading(0/1 재장전 중), shot_seq(발사 카운터 uint8)
#   uint16: dmg_dealt(이 클라가 상대에게 누적으로 입힌 총 피해; PvP 체력 동기화용)
#   uint8 : deaths(이 클라가 죽은 누적 횟수; 상대가 이 증가를 보면 '내가 처치' 판정)
#   uint32: nonce(접속 시 뽑은 랜덤값; 두 클라가 비교해 스폰 A/B 자동 배정)
# reloading/shot_seq 는 상대 화면에서 재장전 모션 + 총소리를 재현하기 위한 필드.
# (shot_seq 는 발사할 때마다 1씩 증가; 수신측이 직전값과 달라지면 '새 발사'로 판정.)
# dmg_dealt 는 누적값 — 수신측은 직전값과의 증가분만큼 자기 체력을 깎는다(패킷
#   합쳐짐/유실에도 안전; TCP 라 순서 보장). 65535 에서 wrap(한 세션엔 충분).
# deaths 는 누적 사망 횟수 — 상대측이 증가를 감지하면 킬 배너/사운드 재생(1:1 이라
#   상대가 죽었다 = 내가 죽인 것).
# nonce 는 세션 고정 랜덤 — 큰 쪽=스폰 A, 작은 쪽=스폰 B. (릴레이가 역할 배정을
#   못 하므로 두 클라가 nonce 만으로 대칭/자동으로 서로 다른 스폰을 고른다.)
# name(24s) = 준비방 표시용 플레이어 이름(UTF-8, 24바이트 고정; 남는 자리 \x00 패딩).
# ready(B) = 준비완료 플래그(0/1) — 양쪽 ready 면 게임 시작(준비방 종료).
# ⚠ 송신·수신 양쪽이 반드시 이 새 포맷이어야 한다. 옛 클라와 섞이면 프레임 정렬이
#   어긋나 좌표가 깨지므로, 두 클라 모두 새 버전이어야 함.
# 축구 동기화 추가 필드(뒤에 append): 권위(스폰 A)가 공 위치·점수를 싣고, 양쪽이
#   '내가 공 찬 이벤트'(kick_seq + 명중오프셋 + 방향 + 파워)를 실어 보낸다.
#   ball(3f) + score_a,score_b(2B) + kick_seq(1B) + koff(3f) + kdir(3f) + kpow(1f).
NET_STATE_FMT = '<5fBBBHBI24sB' + '3fBBB7f'
NET_STATE_SIZE = struct.calcsize(NET_STATE_FMT)
NET_NAME_BYTES = 24
# [수정1] 상대 움직임 지연 완화 — 송신 빈도 ↑ + 수신 보간 수렴 ↑. (외삽/예측은 안 씀;
# 부작용 분리를 위해 다음 단계에서 별도로.) 둘 다 여기 상수로 빼서 튜닝 쉽게.
NET_SEND_HZ = 45.0          # 송신 스로틀(40~50Hz 권장; 위치 패킷 21바이트라 부담 적음)
REMOTE_SMOOTH_LERP = 18.0   # 상대 위치 보간 계수 min(1, dt*이값). 클수록 빨리 수렴,
#                             너무 크면 떨림 — 부드러움 유지되는 선(12 → 18).
# [수정2] 순간이동 완화 — 스냅샷 보간(엔티티 인터폴레이션). 상대를 INTERP_DELAY 만큼
# 과거 시점으로 두고, 버퍼에 쌓인 두 스냅샷 사이를 시간 비율로 보간 → 패킷이 몰리거나
# 비어도(렉/지터) 등속으로 부드럽게 흐른다(최신 위치로 바로 튀지 않음). 대가는 약간의
# 시각적 지연. 송신 간격(1/45≈22ms)의 2~3배를 잡아 한두 패킷 누락은 흡수.
REMOTE_INTERP_DELAY = 0.12  # 상대 렌더를 이만큼(초) 과거로. 클수록 부드럽지만 지연↑(0.08~0.18)
REMOTE_TELEPORT_DIST = 6.0  # 한 패킷새 이만큼(m) 넘게 점프하면 진짜 텔레포트(리스폰/스폰배정)로
#                             보고 보간 끊고 즉시 스냅. 정상 이동은 22ms 에 <0.2m 라 오인 없음.

# ── 땅따먹기(영역 페인트) ────────────────────────────────────────────────
# 플레이어 색 — id 1=A(파랑), 2=B(주황). 0=중립(아직 안 칠함). 시안/글리치 테마 안 씀.
PAINT_COLORS = {1: (0.20, 0.45, 1.0, 1.0), 2: (1.0, 0.50, 0.12, 1.0)}
# 킬 부위별 칠하는 디스크 반경(m) — 헤드샷이 가장 넓게. (1m 격자라 작게 — 칸 수 과증가 방지)
PAINT_KILL_RADIUS = {'head': 1.8, 'body': 1.2, 'other': 0.7}
PAINT_TIME = 180.0          # 한 판 제한시간(초, 3분) — 끝나면 많이 칠한 쪽 승리

# 무기별 스탯 — _equip_weapon 이 적용. ammo_max=탄창, cooldown=발사간격(s),
# auto=연발(mouse1 hold 연사), head_onekill=헤드샷 즉사.
WEAPON_STATS = {
    'pistol': {'ammo_max': 8,  'cooldown': 0.18, 'auto': False, 'head_onekill': False},
    'rifle':  {'ammo_max': 25, 'cooldown': 0.09, 'auto': True,  'head_onekill': True},
}

# 무기 스왑 모션 — 팔/총을 아래로 내려 시야 밖으로 → 교체 → 다시 올림.
WEAPON_SWAP_DROP     = 0.6    # 내려가는 깊이 (m, ybot Z offset)
WEAPON_SWAP_DOWN_DUR = 0.13   # 내리는 시간 (s)
WEAPON_SWAP_UP_DUR   = 0.18   # 올리는 시간 (s)

ZOMBIE_BAM = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'zombie' / 'scene.bam')
)
# 외부 Mixamo death 애니메이션 (Death From Front Headshot) — 적와 동일한
# mixamorig 스켈레톤이라 actor.loadAnims 로 바인딩 가능.
ZOMBIE_DEATH_BAM = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'zombie' / 'death_headshot.bam')
)

UI_DIR = SCRIPT_DIR / 'assets' / 'ui'    # 처치 HUD PNG 자산 (시안 단색·4×·투명)


def _ray_sphere(o, d, c, r):
    """ray o + t*d (d 정규화) 가 구(center c, radius r) 에 닿는 최소 t>=0. 없으면 None."""
    m = o - c
    b = 2.0 * d.dot(m)
    cc = m.dot(m) - r * r
    disc = b * b - 4.0 * cc
    if disc < 0.0:
        return None
    s = disc ** 0.5
    t0 = (-b - s) * 0.5
    if t0 >= 0.0:
        return t0
    t1 = (-b + s) * 0.5
    return t1 if t1 >= 0.0 else None


def _ray_capsule(o, d, a, b, r):
    """ray o + t*d (d 정규화) 가 캡슐(선분 a-b, 반경 r) 표면에 처음 닿는 t>=0. 없으면 None.
    양 끝 구 + 유한 원기둥의 최소 교차. 본 2개 사이를 잇는 두꺼운 막대 = 사지/몸통."""
    best = None
    for c in (a, b):                       # 양 끝 구(반구 캡)
        t = _ray_sphere(o, d, c, r)
        if t is not None and (best is None or t < best):
            best = t
    ab = b - a
    length = ab.length()
    if length > 1e-9:                      # 유한 원기둥 몸통
        u = ab * (1.0 / length)
        m = o - a
        d_perp = d - u * d.dot(u)
        m_perp = m - u * m.dot(u)
        aa = d_perp.dot(d_perp)
        if aa > 1e-9:                      # ray 가 축과 평행하면 구로 충분
            bb = 2.0 * d_perp.dot(m_perp)
            cc = m_perp.dot(m_perp) - r * r
            disc = bb * bb - 4.0 * aa * cc
            if disc >= 0.0:
                s = disc ** 0.5
                for t in ((-bb - s) / (2.0 * aa), (-bb + s) / (2.0 * aa)):
                    if t >= 0.0 and (best is None or t < best):
                        axial = (m + d * t).dot(u)   # 축 투영 [0, length] 안일 때만
                        if 0.0 <= axial <= length:
                            best = t
    return best


def _ray_aabb(ox, oy, oz, dx, dy, dz, x0, x1, y0, y1, z0, z1):
    """ray(o, d) vs 축정렬 박스 [x0,x1]×[y0,y1]×[z0,z1]. 진입 t>=0 반환(내부에서
    시작하면 0), 안 맞으면 None. 총알이 3D 로 벽/플랫폼에 막히는지 판정용."""
    tmin, tmax = 0.0, 1e18
    for o, d, lo, hi in ((ox, dx, x0, x1), (oy, dy, y0, y1), (oz, dz, z0, z1)):
        if -1e-12 < d < 1e-12:
            if o < lo or o > hi:
                return None
        else:
            t1 = (lo - o) / d
            t2 = (hi - o) / d
            if t1 > t2:
                t1, t2 = t2, t1
            if t1 > tmin:
                tmin = t1
            if t2 < tmax:
                tmax = t2
            if tmin > tmax:
                return None
    return tmin


class Zombie:
    """적 한 마리 — Actor + 상태머신(IDLE/CHASE/ATTACK) + 시야 기반 AI.

    시야: 거리 < sight_range AND 좌우 시야각 ±sight_fov_half 안 → 본다.
    상태:
      IDLE   — 가만히 Idle anim. 플레이어 시야에 들어오면 CHASE.
      CHASE  — Run anim 돌면서 플레이어 향해 이동. 근접 시 ATTACK, 시야 잃으면 IDLE.
      ATTACK — 랜덤 attack anim 한 번. 끝나면 거리/시야 다시 판정해서 attack/chase/idle.
    """
    IDLE = 'idle'
    CHASE = 'chase'
    ATTACK = 'attack'
    DYING = 'dying'
    DEAD = 'dead'

    # 히트박스 = X Bot 실제 본(joint)에 붙인 캡슐/구. exposeJoint 로 본 world pos 를
    # 매 프레임 따라가므로 idle/run/attack/death 어떤 자세든 머리=머리, 팔=팔 위치에
    # 정확히 붙는다. ray ↔ 캡슐 교차(_ray_capsule)로 판정, 가장 가까운 hit 의 zone 채택.
    # 항목: (본A_suffix, 본B_suffix, 반경 m, zone). A==B 면 구(머리).
    HEAD_UP_OFFSET = 0.07     # Head 본(두개골 밑)에서 머리 구 중심을 살짝 위로 보정
    HITBOX_SPEC = (
        ('Head', 'Head', 0.135, 'head'),          # 머리 구
        ('Hips', 'Spine2', 0.22, 'body'),         # 하/중 몸통
        ('Spine2', 'Neck', 0.17, 'body'),         # 상 몸통/가슴
        ('LeftArm', 'LeftForeArm', 0.075, 'other'),
        ('LeftForeArm', 'LeftHand', 0.06, 'other'),
        ('RightArm', 'RightForeArm', 0.075, 'other'),
        ('RightForeArm', 'RightHand', 0.06, 'other'),
        ('LeftUpLeg', 'LeftLeg', 0.11, 'other'),
        ('LeftLeg', 'LeftFoot', 0.08, 'other'),
        ('RightUpLeg', 'RightLeg', 0.11, 'other'),
        ('RightLeg', 'RightFoot', 0.08, 'other'),
    )
    # head 50 → hp_max 100 이므로 헤드샷 2방에 사망. body/other 는 그대로.
    DAMAGE = {'head': 50, 'body': 10, 'other': 5}

    # Distance LOD — 플레이어로부터 이 거리 너머의 적는 actor.hide() + AI/anim skip.
    # 어차피 시야 25m 너머는 안 쫓아오고 벽 차폐로 시각도 막혀있어서 cost 0 으로 만들어도
    # 게임 플레이에 영향 없음. 맵 길이 ~65m → 다른 방의 적는 거의 다 LOD'd.
    LOD_DISTANCE    = 28.0
    LOD_DIST_SQ     = LOD_DISTANCE * LOD_DISTANCE

    def __init__(self, game, spawn_pos, yaw=0.0):
        self.game = game
        self.actor = Actor(ZOMBIE_BAM)
        self.actor.reparentTo(game.render)

        # Mixamo container action 제외
        self.anim_names = [a for a in self.actor.getAnimNames()
                           if 'mixamo.com' not in a]
        # 외부 death 애니메이션 (Death From Front Headshot) 바인딩 — 동일 mixamorig 본.
        if ZOMBIE_DEATH_BAM.exists():
            self.actor.loadAnims({self.DEATH_ANIM: ZOMBIE_DEATH_BAM})
            if self.DEATH_ANIM not in self.anim_names:
                self.anim_names.append(self.DEATH_ANIM)

        # 본 기반 히트박스 — Head/Hips/팔/다리 본을 exposeJoint 해서 캡슐 구성.
        self._build_hitboxes()
        # (진단) Hips/발 본 노출 — 죽음 낙하 원인 파악용.
        self._hips_np = self._expose_hips()
        self._lfoot_np = self._expose_joint('LeftFoot')
        self._rfoot_np = self._expose_joint('RightFoot')

        self.pos = Vec3(spawn_pos)
        self.anchor = Vec3(self.pos)   # 배회 거점 — 평생 고정 (스폰 위치)
        self.yaw = yaw
        self.actor.setPos(self.pos)
        self.actor.setH(self.yaw + 180)

        # 튜닝 노브
        self.move_speed       = 4.0    # m/s — 추격 속도 (플레이어와 동일)
        self.sight_range      = 25.0   # m  — 최대 시야 거리
        self.sight_fov_half   = 70.0   # deg — 시야각의 절반 (전체 140°)
        self.attack_range     = 1.8    # m  — 이 안이면 공격

        self.attack_anims = [a for a in ('Attack1', 'Attack2', 'Attack3', 'Attack4')
                              if a in self.anim_names]

        self.state = self.IDLE
        self.current_anim = None
        self.attack_t = 0.0
        self.death_comp = 0.0          # 현재 Death Z 보정량 (m)
        self._death_comp_active = False
        # 배회 — IDLE 진입 시 첫 update 가 phase 를 잡음 (None → pause → walk → pause ...)
        self._wander_phase = None      # 'walk' / 'pause' / None
        self._wander_target = (self.pos.x, self.pos.y)
        self._wander_t = 0.0
        self._death_settle_t = 0.0     # 죽을 때 접지 보정 페이드 남은 시간 (sec)
        self._corpse_t = 0.0           # DEAD 진입 후 누워있기+페이드 남은 시간 (sec)
        self.remove_me = False         # 페이드 끝나 정리 대상이 됨

        # Anim blend (crossfade) — 전환 시 180ms 동안 prev → new 가중치 보간
        # → 공격 끝나고 Run 으로 바로 안 튀고 부드럽게 흘러감.
        self.actor.enableBlend()
        # Idle / Run 만 init 에서 loop (계속 active). Attack/Death 는 _play 때
        # actor.play() 로 restart + 가중치 ramp up.
        for a in ('Idle', 'Run'):
            if a in self.anim_names:
                self.actor.loop(a)
                self.actor.setControlEffect(a, 0.0)
        self._anim_prev = None
        self._anim_blend_t = 0.0
        self._play('Idle', loop=True)

        # 발로란트식 빨간 테두리 — 적(적)이 눈에 잘 띄게.
        self.outline = game._attach_outline(self.actor)

        # HP / health bar
        self.hp_max = 100
        self.hp = self.hp_max
        self.hp_bar_t = 0.0           # 남은 표시 시간 (sec)
        self.hp_bar_show_dur = 2.5    # 데미지 후 풀 alpha 로 보이는 시간
        self.hp_bar_fade_dur = 1.5    # 그 뒤 fade out 시간
        self._build_hp_bar()

        # Transform — F 키로 dead 적를 Y Bot 으로 페이드 전환.
        # X Bot alpha 1→0 / Y Bot alpha 0→1 dual fade.
        # 둘 다 같은 self.pos / yaw + Death anim 의 마지막 프레임 pose → 위치/자세 일치.
        self.transformed = False
        self.transform_t = 0.0
        self.transform_dur = 1.2
        self.ybot_replacement = None

        # LOD 상태 — True 면 actor 가 visible + 매 프레임 update. 토글 시에만 show/hide
        # 호출 (매 프레임 hide 콜 피함). 시작 시 visible 가정.
        self._lod_active = True

    BLEND_DUR = 0.18    # crossfade 시간 (sec)

    # 배회 — 플레이어 못 봐도 anchor 주변에서 어슬렁대는 동작.
    # walk(랜덤 점까지 천천히 이동) ↔ pause(잠깐 멈춰 두리번) 반복.
    WANDER_RADIUS       = 2.5     # anchor 에서 목표점 뽑는 최대 거리 (m)
    WANDER_SPEED        = 1.2     # 배회 이동 속도 (m/s) — 추격(4.0) 보다 한참 느림
    WANDER_WALK_TIMEOUT = 6.0     # walk phase 최대 시간 (벽에 막혀 도착 못 해도 끝냄)
    WANDER_PAUSE_MIN    = 1.5
    WANDER_PAUSE_MAX    = 3.5
    WANDER_ARRIVE_DIST  = 0.3     # 이 거리 안이면 도착 — pause 로 전환
    WANDER_YAW_RATE     = 220.0   # 배회 yaw 회전 속도 (deg/s) — 부드럽게

    # 발 접지 보정.
    # Idle/Run 은 Hips location strip 때문에 본이 고정되며 발이 바닥에서 ~0.18m 떠 있음.
    # Death 는 strip 안 돼서 발을 제대로 바닥에 안착시킴 → 죽을 때 그 차이만큼 몸이 내려
    # 앉는 것처럼 보임. 해결: 살아있을 때 가장 낮은 발 본을 GROUND_FOOT_Z 에 맞춰 접지
    # (띄움 제거), 죽을 때 그 접지 보정을 DEATH_SETTLE_DUR 동안 0 으로 페이드해 죽음
    # 모션의 native 바닥 안착으로 부드럽게 넘김 → 추가 낙하 없음.
    GROUND_ZOMBIES = True       # 발 접지 보정 on/off
    GROUND_FOOT_Z = 0.09        # 바닥 접지 시 발 본 로컬 Z (player 발 ~0.10 기준)
    DEATH_SETTLE_DUR = 0.30     # 죽을 때 접지 보정을 0 으로 페이드하는 시간 (sec)
    DEATH_ANIM = 'DeathHeadshot'   # 사용할 죽음 애니메이션 (Death From Front Headshot)
    DEATH_PLAY_RATE = 1.5       # 죽음 모션 재생 속도 (>1 = 더 빨리 쓰러짐)
    CORPSE_LINGER = 0.8         # 죽은 뒤 바닥에 누워있는 시간 (sec)
    CORPSE_FADE_DUR = 0.7       # 그 뒤 페이드아웃되어 사라지는 시간 (sec)
    DEBUG_DEATH = False         # 죽음 진단 로그
    _hips_debug_printed = False
    _death_dbg_done = False

    def _build_hitboxes(self):
        """HITBOX_SPEC 의 본을 exposeJoint 해서 (npA, npB, r, zone) 리스트로.
        없는 본이 낀 항목은 건너뜀. 실패하면 빈 리스트 → hit_test 가 그냥 miss."""
        self.hitboxes = []
        self._hit_np = {}
        try:
            part = (self.actor.getPartNames() or ['modelRoot'])[0]
            names = [j.getName() for j in self.actor.getJoints()]

            def expose(suffix):
                if suffix in self._hit_np:
                    return self._hit_np[suffix]
                full = next((n for n in names if n.endswith(suffix)), None)
                np_j = self.actor.exposeJoint(None, part, full) if full else None
                self._hit_np[suffix] = np_j
                return np_j

            for a, b, r, zone in self.HITBOX_SPEC:
                npa, npb = expose(a), expose(b)
                if npa is None or npb is None:
                    continue
                self.hitboxes.append((npa, npb, r, zone))
        except Exception as e:
            print('[zombie] hitbox build failed:', e, flush=True)
            self.hitboxes = []

    def hit_test(self, render, cam_pos, ray_dir, max_t):
        """ray(cam_pos, ray_dir 정규화) vs 이 적 본 히트박스들. max_t 보다 가까운
        최단 hit 의 (t, zone, world_pos) 반환, 없으면 None."""
        best = None
        for npa, npb, r, zone in self.hitboxes:
            a = npa.getPos(render)
            b = a if npb is npa else npb.getPos(render)
            if zone == 'head':
                off = Vec3(0, 0, self.HEAD_UP_OFFSET)
                a = a + off
                b = b + off
            t = _ray_capsule(cam_pos, ray_dir, a, b, r)
            if t is None or t < 0.0 or t >= max_t:
                continue
            max_t = t
            best = (t, zone, Vec3(cam_pos + ray_dir * t))
        return best

    def _expose_hips(self):
        """Hips 본을 exposeJoint 해서 NodePath 반환 (없거나 실패하면 None).
        getZ(self.actor) 로 actor-local Hips 높이를 읽어 죽음 낙하 보정에 사용."""
        try:
            full = next((j.getName() for j in self.actor.getJoints()
                         if j.getName().endswith('Hips')), None)
            if not full:
                if not Zombie._hips_debug_printed:
                    print('[death] no Hips joint found', flush=True)
                    Zombie._hips_debug_printed = True
                return None
            part = (self.actor.getPartNames() or ['modelRoot'])[0]
            np_j = self.actor.exposeJoint(None, part, full)
            if not Zombie._hips_debug_printed:
                print('[death] hips exposed: joint=%s part=%s localZ=%.3f'
                      % (full, part, np_j.getZ(self.actor)), flush=True)
                Zombie._hips_debug_printed = True
            return np_j
        except Exception as e:
            if not Zombie._hips_debug_printed:
                print('[death] hips expose FAILED:', e, flush=True)
                Zombie._hips_debug_printed = True
            return None

    def _expose_joint(self, suffix):
        """suffix 로 끝나는 본을 exposeJoint. 없거나 실패하면 None."""
        try:
            full = next((j.getName() for j in self.actor.getJoints()
                         if j.getName().endswith(suffix)), None)
            if not full:
                return None
            part = (self.actor.getPartNames() or ['modelRoot'])[0]
            return self.actor.exposeJoint(None, part, full)
        except Exception:
            return None

    def _min_foot_z(self):
        """가장 낮은 발 본의 actor-local Z. 발 본 없으면 None."""
        fz = [fn.getZ(self.actor) for fn in (self._lfoot_np, self._rfoot_np)
              if fn is not None]
        return min(fz) if fz else None

    def _play(self, anim, loop=False):
        if anim not in self.anim_names:
            return
        if self.current_anim == anim:
            # 같은 anim: single-shot 이면 restart, loop 이면 그대로
            if not loop:
                self.actor.play(anim)
            return
        # 다른 anim: 시작 + crossfade
        if not loop:
            self.actor.play(anim)
        else:
            # Idle/Run 은 init 에서 이미 loop 중 → 다시 호출 안 해도 됨
            pass
        # 새 anim 은 weight 0 부터 시작, prev 는 1 부터 ramp down
        self.actor.setControlEffect(anim, 0.0)
        self._anim_prev = self.current_anim
        self.current_anim = anim
        self._anim_blend_t = self.BLEND_DUR

    def _pick_wander_target(self):
        """anchor 주변 WANDER_RADIUS 안 랜덤 점. 현재 pos 와 너무 가까우면 재시도."""
        for _ in range(6):
            a = random.uniform(0.0, 6.283185307179586)
            r = random.uniform(0.5, self.WANDER_RADIUS)
            tx = self.anchor.x + cos(a) * r
            ty = self.anchor.y + sin(a) * r
            if (tx - self.pos.x) ** 2 + (ty - self.pos.y) ** 2 > 0.25:
                return tx, ty
        return self.anchor.x, self.anchor.y   # fallback — anchor 로 복귀

    def _start_wander_walk(self):
        self._wander_target = self._pick_wander_target()
        self._wander_phase = 'walk'
        self._wander_t = self.WANDER_WALK_TIMEOUT

    def _start_wander_pause(self):
        self._wander_phase = 'pause'
        self._wander_t = random.uniform(self.WANDER_PAUSE_MIN,
                                        self.WANDER_PAUSE_MAX)

    @staticmethod
    def _step_toward_yaw(cur, target, max_step):
        """yaw 를 target 방향으로 최대 max_step deg 만큼 이동 (360° wrap 고려)."""
        diff = (target - cur + 540.0) % 360.0 - 180.0
        if abs(diff) <= max_step:
            return target
        return cur + (max_step if diff > 0 else -max_step)

    def _update_anim_blend(self, dt):
        if self._anim_blend_t <= 0:
            return
        self._anim_blend_t -= dt
        if self._anim_blend_t <= 0:
            self.actor.setControlEffect(self.current_anim, 1.0)
            if self._anim_prev is not None and self._anim_prev != self.current_anim:
                self.actor.setControlEffect(self._anim_prev, 0.0)
            self._anim_prev = None
        else:
            t = self._anim_blend_t / self.BLEND_DUR    # 1 → 0
            self.actor.setControlEffect(self.current_anim, 1.0 - t)
            if self._anim_prev is not None and self._anim_prev != self.current_anim:
                self.actor.setControlEffect(self._anim_prev, t)

    def _build_hp_bar(self):
        """적 머리 위 health bar — 평소 hidden, 데미지 시 show + fade out.

        피벗(hp_bar)을 actor Z축 위(0,0,2)에 둔다 — heading 회전축 위라 적가
        어느 방향을 보든 월드 위치 불변. 피벗만 billboard(카메라 정면)로 돌리고,
        bg/fill 은 피벗의 로컬(=화면정렬) 프레임에 자식으로 붙여 좌측 정렬을 유지.
        (이전엔 fill 을 actor 로컬 -0.5 에 직접 놔서 heading 따라 초록이 어긋났음.)"""
        self.hp_bar = self.actor.attachNewNode('hp_bar')
        self.hp_bar.setPos(0, 0, 2.0)
        self.hp_bar.setBillboardPointEye()
        self.hp_bar.setLightOff()
        self.hp_bar.setTransparency(True)
        self.hp_bar.setDepthTest(False)
        self.hp_bar.setDepthWrite(False)
        self.hp_bar.hide()
        # 배경 (빨강) — 풀 너비 1m, 중앙 정렬
        cm_bg = CardMaker('hp_bg')
        cm_bg.setFrame(-0.5, 0.5, -0.04, 0.04)
        self.hp_bg = self.hp_bar.attachNewNode(cm_bg.generate())
        self.hp_bg.setColor(0.5, 0.08, 0.08, 0.85)
        self.hp_bg.setBin('fixed', 80)
        # 채우기 (초록) — 피벗 로컬 x=-0.5(좌측 끝)에서 우로, hp_ratio 만큼 setSx
        cm_f = CardMaker('hp_fill')
        cm_f.setFrame(0, 1, -0.04, 0.04)
        self.hp_fill = self.hp_bar.attachNewNode(cm_f.generate())
        self.hp_fill.setColor(0.2, 0.95, 0.25, 1.0)
        self.hp_fill.setPos(-0.5, 0, 0)
        self.hp_fill.setBin('fixed', 81)

    def take_damage(self, amount):
        if self.hp <= 0:
            return
        self.hp = max(0, self.hp - amount)
        # 바 표시 + 풀 알파 + ratio 갱신
        self.hp_bar_t = self.hp_bar_show_dur + self.hp_bar_fade_dur
        self.hp_bar.show()
        self.hp_bar.setColorScale(1, 1, 1, 1)
        ratio = max(0.001, self.hp / self.hp_max)
        self.hp_fill.setSx(ratio)
        if self.hp <= 0:
            # Death anim 단발 + crossfade (직전 모션에서 부드럽게 이어짐).
            # 빠른 재생속도로 더 빨리 쓰러지고, 끝나면 누워있다 페이드아웃.
            self.state = self.DYING
            self.hp_bar.hide()
            anim = self.DEATH_ANIM if self.DEATH_ANIM in self.anim_names else (
                'Death' if 'Death' in self.anim_names else None)
            if anim is not None:
                self._play(anim, loop=False)
                self.actor.setPlayRate(self.DEATH_PLAY_RATE, anim)
                self.death_t = self.actor.getDuration(anim) / self.DEATH_PLAY_RATE
                # 죽을 때 발 접지 보정을 settle 동안 유지하다 0 으로 페이드 (추가 낙하 방지).
                self._death_settle_t = self.DEATH_SETTLE_DUR
            else:
                self.actor.hide()
                self.state = self.DEAD

    def can_see_player(self, player_pos):
        to_p = player_pos - self.pos
        to_p.z = 0   # 평면 거리만
        dist = to_p.length()
        if dist > self.sight_range:
            return False
        if dist < 0.5:
            return True   # 코앞이면 무조건 인지
        yr = radians(self.yaw)
        forward = Vec3(-sin(yr), cos(yr), 0)
        to_p.normalize()
        if forward.dot(to_p) <= cos(radians(self.sight_fov_half)):
            return False
        # 벽 차폐 — 적↔플레이어 직선상에 벽이 있으면 못 봄. 도어/케이지 갭은
        # wall 박스가 없는 영역이라 자동 통과.
        return not self.game.level_collider.segment_blocked(
            self.pos.x, self.pos.y, player_pos.x, player_pos.y)

    def _start_attack(self):
        if not self.attack_anims:
            return
        attack = random.choice(self.attack_anims)
        # _play 가 같은 anim 이면 restart, 다른 anim 이면 crossfade 처리.
        self._play(attack, loop=False)
        self.attack_t = self.actor.getDuration(attack)
        self.state = self.ATTACK
        # 공격 시작 순간 코어에 10 데미지 (한 번의 anim = 한 번의 타격).
        # 피격 방향 표시용으로 이 적 위치도 전달.
        self.game.take_core_damage(10, self.pos)

    def start_transform(self, game):
        """DEAD 적 → Y Bot 으로 dual fade. 같은 self.pos / yaw + Death 마지막
        프레임 pose 라 위치 / 자세 정확히 일치."""
        if self.transformed or self.state != self.DEAD:
            return
        self.transform_t = self.transform_dur
        self.actor.setTransparency(True)
        # Y Bot 같은 위치 / 같은 yaw 에 생성, alpha 0 부터
        self.ybot_replacement = Actor(BAM_PATH)
        self.ybot_replacement.reparentTo(game.render)
        self.ybot_replacement.setPos(self.pos)
        self.ybot_replacement.setH(self.yaw + 180)
        self.ybot_replacement.setTransparency(True)
        self.ybot_replacement.setColorScale(1, 1, 1, 0)
        # Death anim 의 마지막 프레임 pose — X Bot 과 동일한 자세 (둘 다 Hips
        # location 보존된 anim 이라 바닥 누운 자세 일치).
        anims = self.ybot_replacement.getAnimNames()
        if 'Death' in anims:
            last = self.ybot_replacement.getNumFrames('Death') - 1
            self.ybot_replacement.pose('Death', last)

    def update(self, dt, player_pos):
        # Distance LOD — 멀면 actor 숨기고 모든 update 비용 0. 단, DYING (Death anim
        # 진행 중) / Transform 페이드 중 적는 LOD 보류해서 끊김 없이 마무리.
        dx = player_pos.x - self.pos.x
        dy = player_pos.y - self.pos.y
        busy = (self.state == self.DYING or self.transform_t > 0
                or (self.state == self.DEAD and self._corpse_t > 0.0))
        too_far = (dx * dx + dy * dy) > self.LOD_DIST_SQ and not busy
        if too_far and self._lod_active:
            self.actor.hide()
            if self.ybot_replacement is not None:
                self.ybot_replacement.hide()
            # 다음에 다시 가까워졌을 때 깔끔하게 IDLE 부터 — CHASE 상태로 멈춰있다
            # 갑자기 보이면서 Run anim 으로 튀는 거 방지.
            if self.state == self.CHASE:
                self.state = self.IDLE
            self._lod_active = False
        elif not too_far and not self._lod_active:
            self.actor.show()
            if self.ybot_replacement is not None:
                self.ybot_replacement.show()
            self._lod_active = True
        if too_far:
            return

        # anim blend 가중치 보간 — 모든 state 에서 매 프레임 ramp.
        self._update_anim_blend(dt)

        # Transform dual fade — X Bot alpha 1→0, Y Bot alpha 0→1.
        if self.transform_t > 0:
            self.transform_t -= dt
            if self.transform_t <= 0:
                self.actor.hide()
                if self.ybot_replacement is not None:
                    self.ybot_replacement.setColorScale(1, 1, 1, 1)
                    self.ybot_replacement.clearTransparency()
                self.transformed = True
            else:
                t = self.transform_t / self.transform_dur   # 1 → 0
                self.actor.setColorScale(1, 1, 1, t)        # X Bot 페이드 아웃
                if self.ybot_replacement is not None:
                    self.ybot_replacement.setColorScale(1, 1, 1, 1.0 - t)

        if self.state == self.DEAD:
            # 잠깐 누워있다(CORPSE_LINGER) 페이드아웃(CORPSE_FADE_DUR) 후 제거 표시.
            if self._corpse_t > 0.0:
                self._corpse_t -= dt
                if self._corpse_t < self.CORPSE_FADE_DUR:
                    a = max(0.0, self._corpse_t / self.CORPSE_FADE_DUR)
                    self.actor.setColorScale(1, 1, 1, a)
                if self._corpse_t <= 0.0:
                    self.actor.hide()
                    self.remove_me = True
            return

        if self.state == self.DYING:
            # Death anim 재생 중 — 끝까지 기다린 후 DEAD 로
            self.death_t -= dt
            # 발 접지 보정 페이드 — 시작엔 산 적와 같은 접지(낙하 0)를 유지하다,
            # settle 시간 동안 0 으로 줄여 죽음 모션 native 바닥 안착으로 부드럽게 넘김.
            if Zombie.GROUND_ZOMBIES and self._death_settle_t > 0.0:
                self._death_settle_t -= dt
                mf = self._min_foot_z()
                if mf is not None:
                    fade = max(0.0, self._death_settle_t / self.DEATH_SETTLE_DUR)
                    self.actor.setZ(self.pos.z + (Zombie.GROUND_FOOT_Z - mf) * fade)
                if self._death_settle_t <= 0.0:
                    self.actor.setZ(self.pos.z)
            if self.death_t <= 0:
                self.state = self.DEAD
                self.actor.setZ(self.pos.z)   # native 바닥 위치로 확정
                # 시체 누워있기 + 페이드아웃 타이머 시작.
                self._corpse_t = self.CORPSE_LINGER + self.CORPSE_FADE_DUR
                self.actor.setTransparency(True)
            # 위치(X/Y)는 그대로 (이동 안 함)
            return

        # HP bar fade — show_dur 동안 풀 알파, fade_dur 동안 1→0 lerp, 끝나면 hide
        if self.hp_bar_t > 0:
            self.hp_bar_t -= dt
            if self.hp_bar_t <= 0:
                self.hp_bar.hide()
            elif self.hp_bar_t < self.hp_bar_fade_dur:
                alpha = self.hp_bar_t / self.hp_bar_fade_dur
                self.hp_bar.setColorScale(1, 1, 1, alpha)

        to_p = player_pos - self.pos
        to_p.z = 0
        dist = to_p.length()
        sees = self.can_see_player(player_pos)

        if self.state == self.IDLE:
            if sees:
                self.state = self.CHASE
                self._wander_phase = None
            else:
                # 첫 진입(스폰 직후 / CHASE→IDLE 전환 / LOD 복귀) — pause 부터.
                if self._wander_phase is None:
                    self._start_wander_pause()
                self._wander_t -= dt
                if self._wander_phase == 'pause':
                    self._play('Idle', loop=True)
                    if self._wander_t <= 0:
                        self._start_wander_walk()
                else:   # 'walk'
                    tx, ty = self._wander_target
                    wdx = tx - self.pos.x
                    wdy = ty - self.pos.y
                    wd = (wdx * wdx + wdy * wdy) ** 0.5
                    if wd < self.WANDER_ARRIVE_DIST or self._wander_t <= 0:
                        self._start_wander_pause()
                        self._play('Idle', loop=True)
                    else:
                        self._play('Run', loop=True)
                        inv = 1.0 / wd
                        ux, uy = wdx * inv, wdy * inv
                        self.pos.x += ux * self.WANDER_SPEED * dt
                        self.pos.y += uy * self.WANDER_SPEED * dt
                        nx, ny = self.game.level_collider.resolve(
                            self.pos.x, self.pos.y, ZOMBIE_RADIUS)
                        self.pos.x = nx
                        self.pos.y = ny
                        target_yaw = degrees(atan2(-ux, uy))
                        self.yaw = self._step_toward_yaw(
                            self.yaw, target_yaw, self.WANDER_YAW_RATE * dt)

        elif self.state == self.CHASE:
            if not sees:
                self.state = self.IDLE
                self._wander_phase = None
            elif dist < self.attack_range:
                self._start_attack()
            else:
                self._play('Run', loop=True)
                if dist > 0.01:
                    direction = Vec3(to_p.x / dist, to_p.y / dist, 0)
                    self.pos.x += direction.x * self.move_speed * dt
                    self.pos.y += direction.y * self.move_speed * dt
                    # 벽 충돌 해소 — 좁은 통로/기둥에서 적가 벽 뚫고 직진하지 않게.
                    nx, ny = self.game.level_collider.resolve(
                        self.pos.x, self.pos.y, ZOMBIE_RADIUS)
                    self.pos.x = nx
                    self.pos.y = ny
                    # 추격 중엔 항상 플레이어 향함
                    self.yaw = degrees(atan2(-direction.x, direction.y))

        elif self.state == self.ATTACK:
            self.attack_t -= dt
            if self.attack_t <= 0:
                if sees and dist < self.attack_range:
                    self._start_attack()    # 연속 공격
                elif sees:
                    self.state = self.CHASE
                else:
                    self.state = self.IDLE
                    self._wander_phase = None

        # transform 적용
        self.actor.setPos(self.pos)
        self.actor.setH(self.yaw + 180)
        # 발 접지 — 가장 낮은 발 본을 바닥(GROUND_FOOT_Z)에 맞춰 actor 를 내림.
        # Idle/Run strip 자세가 발을 띄우는 문제 보정 (죽을 때 낙하의 근본 원인).
        if Zombie.GROUND_ZOMBIES:
            mf = self._min_foot_z()
            if mf is not None:
                self.actor.setZ(self.pos.z + (Zombie.GROUND_FOOT_Z - mf))


class Firewall:
    """측면 방 입구 차단막. 쏴서 부수면 통로가 열리고 그 방 적이 스폰.
    그 방을 전멸시키면 cleared -> 방 바닥 색이 번진다."""
    HP_MAX      = 120
    SHOT_DAMAGE = 30
    TINT_DUR    = 1.5
    TINT_ALPHA  = 0.45

    def __init__(self, game, orient, fixed, lo, hi, spawns, stain):
        self.game = game
        self.orient, self.fixed, self.lo, self.hi = orient, fixed, lo, hi
        self.spawns = spawns
        self.stain = stain
        self.hp = self.HP_MAX
        self.broken = False
        self.cleared = False
        self.zombies = []
        self._flash_t = 0.0
        self._tint_t = 0.0

        self.wall = (Wall(fixed, lo, fixed, hi) if orient == 'v'
                     else Wall(lo, fixed, hi, fixed))
        game.level_collider.walls.append(self.wall)

        cm = CardMaker('firewall')
        cm.setFrame(-(hi - lo) / 2.0, (hi - lo) / 2.0, 0.0, WALL_HEIGHT)
        self.node = game.render.attachNewNode(cm.generate())
        self.node.setTwoSided(True)
        if orient == 'v':
            self.node.setPos(fixed, (lo + hi) / 2.0, 0.0)
            self.node.setH(90)
        else:
            self.node.setPos((lo + hi) / 2.0, fixed, 0.0)
            self.node.setH(0)
        self.node.setColor(IMMUNE_COLOR[0], IMMUNE_COLOR[1], IMMUNE_COLOR[2], 0.55)
        self.node.setTransparency(True)
        self.node.setLightOff()

    def ray_distance(self, cam_pos, ray_dir):
        if self.broken:
            return None
        if self.orient == 'v':
            if abs(ray_dir.x) < 1e-6:
                return None
            s = (self.fixed - cam_pos.x) / ray_dir.x
            if s < 0:
                return None
            hy = cam_pos.y + ray_dir.y * s
            hz = cam_pos.z + ray_dir.z * s
            return s if (self.lo <= hy <= self.hi and 0.0 <= hz <= WALL_HEIGHT) else None
        if abs(ray_dir.y) < 1e-6:
            return None
        s = (self.fixed - cam_pos.y) / ray_dir.y
        if s < 0:
            return None
        hx = cam_pos.x + ray_dir.x * s
        hz = cam_pos.z + ray_dir.z * s
        return s if (self.lo <= hx <= self.hi and 0.0 <= hz <= WALL_HEIGHT) else None

    def hit(self):
        if self.broken:
            return
        self.hp = max(0, self.hp - self.SHOT_DAMAGE)
        self._flash_t = 0.07
        self.node.setColorScale(2.2, 2.2, 2.2, 1.0)
        r = self.hp / self.HP_MAX
        self.node.setColor(IMMUNE_COLOR[0], IMMUNE_COLOR[1], IMMUNE_COLOR[2],
                           0.18 + 0.37 * r)
        if self.hp <= 0:
            self._break()

    def _break(self):
        self.broken = True
        self.node.hide()
        try:
            self.game.level_collider.walls.remove(self.wall)
        except ValueError:
            pass
        for x, y in self.spawns:
            z = Zombie(self.game, Vec3(x, y, 0), 180)
            self.game.zombies.append(z)
            self.zombies.append(z)
        print('[firewall] breached -> spawn %d' % len(self.spawns), flush=True)

    def update(self, dt):
        if self._flash_t > 0:
            self._flash_t -= dt
            if self._flash_t <= 0 and not self.broken:
                self.node.setColorScale(1, 1, 1, 1)
        if (self.broken and not self.cleared and self.zombies
                and all(z.hp <= 0 for z in self.zombies)):
            self.cleared = True
            self._tint_t = self.TINT_DUR
            print('[firewall] room cleared -> tint', flush=True)
        if self._tint_t > 0:
            self._tint_t -= dt
            a = self.TINT_ALPHA * min(1.0, 1.0 - max(0.0, self._tint_t) / self.TINT_DUR)
            self.stain.setColor(LESION_COLOR[0], LESION_COLOR[1], LESION_COLOR[2], a)


class Gate:
    """복도를 가로막는 전진 게이트. 해당 구역(zone) 양옆 방이 다 cleared 되기
    전엔 잠겨서 부술 수 없다(쏘면 잠금색이 튕겨냄). 다 cleared 되면 약해져
    돌파 가능 -> 부수면 전진. final_spawns 가 있으면 부순 순간 그 방 적을
    스폰(마지막 방 = 리빌)."""
    HP_MAX      = 160
    SHOT_DAMAGE = 30
    TINT_DUR    = 1.5
    TINT_ALPHA  = 0.45

    def __init__(self, game, orient, fixed, lo, hi, rooms, stain, room_stain,
                 final_spawns):
        self.game = game
        self.orient, self.fixed, self.lo, self.hi = orient, fixed, lo, hi
        self.rooms = rooms
        self.stain = stain
        self.room_stain = room_stain
        self.final_spawns = final_spawns
        self.hp = self.HP_MAX
        self.unlocked = False
        self.broken = False
        self._flash_t = 0.0
        self._tint_t = 0.0
        self._tint_target = None

        self.wall = (Wall(fixed, lo, fixed, hi) if orient == 'v'
                     else Wall(lo, fixed, hi, fixed))
        game.level_collider.walls.append(self.wall)

        cm = CardMaker('gate')
        cm.setFrame(-(hi - lo) / 2.0, (hi - lo) / 2.0, 0.0, WALL_HEIGHT)
        self.node = game.render.attachNewNode(cm.generate())
        self.node.setTwoSided(True)
        if orient == 'v':
            self.node.setPos(fixed, (lo + hi) / 2.0, 0.0)
            self.node.setH(90)
        else:
            self.node.setPos((lo + hi) / 2.0, fixed, 0.0)
            self.node.setH(0)
        self.node.setColor(IMMUNE_COLOR[0], IMMUNE_COLOR[1], IMMUNE_COLOR[2], 0.85)
        self.node.setTransparency(True)
        self.node.setLightOff()

    ray_distance = Firewall.ray_distance      # 동일 로직 재사용

    def hit(self):
        if self.broken:
            return
        if not self.unlocked:
            self._flash_t = 0.10
            self.node.setColorScale(2.6, 2.6, 2.6, 1.0)
            self.game._show_gate_msg('차단막 강화됨 — 양옆 방을 먼저 처치하라')
            return
        self.hp = max(0, self.hp - self.SHOT_DAMAGE)
        self._flash_t = 0.07
        self.node.setColorScale(2.2, 2.2, 2.2, 1.0)
        r = self.hp / self.HP_MAX
        self.node.setColor(IMMUNE_COLOR[0], IMMUNE_COLOR[1], IMMUNE_COLOR[2],
                           0.15 + 0.30 * r)
        if self.hp <= 0:
            self._break()

    def _break(self):
        self.broken = True
        self.node.hide()
        try:
            self.game.level_collider.walls.remove(self.wall)
        except ValueError:
            pass
        if self.final_spawns:
            for x, y in self.final_spawns:
                self.game.zombies.append(Zombie(self.game, Vec3(x, y, 0), 180))
            if self.room_stain is not None:
                self._tint_target = self.room_stain
                self._tint_t = self.TINT_DUR
            self.game._show_gate_msg('구역 동화 진행 — ASSIMILATING ZONE',
                                     2.4, reveal=True)   # 강조
        print('[gate] breached', flush=True)

    def update(self, dt):
        if not self.unlocked and self.rooms and all(r.cleared for r in self.rooms):
            self.unlocked = True
            self.node.setColor(IMMUNE_COLOR[0], IMMUNE_COLOR[1], IMMUNE_COLOR[2], 0.40)
            self._tint_target = self.stain
            self._tint_t = self.TINT_DUR
            self.game._show_gate_msg('차단막 약화됨 — 돌파 가능')
            print('[gate] unlocked', flush=True)
        if self._flash_t > 0:
            self._flash_t -= dt
            if self._flash_t <= 0 and not self.broken:
                self.node.setColorScale(1, 1, 1, 1)
        if self._tint_t > 0 and self._tint_target is not None:
            self._tint_t -= dt
            a = self.TINT_ALPHA * min(1.0, 1.0 - max(0.0, self._tint_t) / self.TINT_DUR)
            self._tint_target.setColor(LESION_COLOR[0], LESION_COLOR[1],
                                       LESION_COLOR[2], a)


class SoccerBall:
    """총알 축구 공 — 위치/속도/스핀(각속도)을 들고 직접 적분한다. 총알이 공을
    맞히면 _kick() 으로 추진 임펄스 + (빗맞으면) 스핀이 실려, 마그누스 효과로 휘어
    나간다(감아차기). 지면/벽 반사 + 공기/구름 마찰. 시각은 흰 구체."""

    RADIUS = 0.55              # 공 반지름(m) — 맞히기 쉽게 약간 크게
    GRAVITY = 14.0             # 중력(m/s^2)
    LINEAR_DRAG = 0.35         # 공기 저항(1/s) — 속도 지수 감쇠
    ROLL_FRICTION = 0.6        # 지면에서 구를 때 마찰(1/s) — 작을수록 멀리 굴러감
    SPIN_DRAG = 3.4            # 스핀 감쇠(1/s) — 크면 커브가 앞부분만(스파이럴 방지)
    SPIN_FACTOR = 0.30         # 빗맞을 때 실리는 스핀량(공식: power * 이값 * 오프셋)
    SPIN_CAP = 6.0             # 스핀 상한(rad/s) — 과한 U턴 커브 방지
    MAGNUS = 0.20              # 마그누스 계수 — 클수록 더 휜다(감아차기)
    RESTITUTION = 0.62         # 벽/지면 반발(0=안튐 1=완전탄성)
    MAX_SPEED = 42.0           # 속도 상한(터무니없는 가속 방지)

    def __init__(self, game, spawn_xy):
        self.game = game
        self._spawn = Vec3(spawn_xy[0], spawn_xy[1], self.RADIUS)
        self.pos = Vec3(self._spawn)
        self.vel = Vec3(0, 0, 0)
        self.spin = Vec3(0, 0, 0)        # 각속도(rad/s) — 주로 z(수직)축 → 수평 커브
        self._orient = Quat()            # 시각 회전 누적(구르기+스핀) — 무늬로 보이게
        self._orient.set(1, 0, 0, 0)     # 단위 쿼터니언
        # 시각 — 내장 구체 모델 + 흑백 무늬 텍스처(회전이 보이게). 모델 없으면 빌보드 폴백.
        self.node = game.render.attachNewNode('soccer_ball')
        model = None
        try:
            model = game.loader.loadModel('models/misc/sphere')
        except Exception:
            model = None
        if model is not None and not model.isEmpty():
            model.reparentTo(self.node)
            model.setScale(self.RADIUS)
            model.setColor(0.97, 0.97, 1.0, 1.0)   # 흰 공
            self._has_model = True
        else:
            cm = CardMaker('ball_bb')
            cm.setFrame(-self.RADIUS, self.RADIUS, -self.RADIUS, self.RADIUS)
            bb = self.node.attachNewNode(cm.generate())
            bb.setBillboardPointEye()
            bb.setColor(0.97, 0.97, 1.0, 1.0)
            self._has_model = True   # 패턴 링으로 회전 표시(빌보드여도)
        # 무늬 — 검은 고리 3개(직교 평면)를 공 표면에 둘러 회전을 또렷이 보이게.
        # self.node 자식이라 node.setQuat 회전을 그대로 따라간다(텍스처 의존 X).
        self._build_ball_pattern()
        self.node.setLightOff()
        self.node.setPos(self.pos)

    @staticmethod
    def _make_pentagon(r):
        """반지름 r 의 정오각형(채움) — XZ 평면, 법선 +Y. 축구공 검은 패치용."""
        fmt = GeomVertexFormat.getV3()
        vdata = GeomVertexData('pent', fmt, Geom.UHStatic)
        vw = GeomVertexWriter(vdata, 'vertex')
        vw.addData3(0.0, 0.0, 0.0)             # 중심
        TAU = 6.2831853
        for i in range(5):
            a = (i / 5.0) * TAU + TAU / 4.0
            vw.addData3(r * cos(a), 0.0, r * sin(a))
        tris = GeomTriangles(Geom.UHStatic)
        for i in range(5):                      # 삼각형 팬(중심+테두리)
            tris.addVertices(0, 1 + i, 1 + ((i + 1) % 5))
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        gn = GeomNode('pentagon')
        gn.addGeom(geom)
        return NodePath(gn)

    def _build_ball_pattern(self):
        """진짜 축구공 무늬 — 정20면체 12꼭짓점 방향에 검은 오각형 12개를 흰 구 표면에
        박는다(클래식 Telstar 패턴 근사). node 자식이라 회전을 그대로 따라간다."""
        phi = (1.0 + 5.0 ** 0.5) / 2.0
        verts = []
        for s1 in (1, -1):
            for s2 in (1, -1):
                verts.append((0.0, s1 * 1.0, s2 * phi))
                verts.append((s1 * 1.0, s2 * phi, 0.0))
                verts.append((s1 * phi, 0.0, s2 * 1.0))
        R = self.RADIUS
        pr = R * 0.42                           # 오각형 크기(반지름)
        for vx, vy, vz in verts:                # 12개
            d = Vec3(vx, vy, vz)
            d.normalize()
            pent = self._make_pentagon(pr)
            pent.reparentTo(self.node)
            pent.setColor(0.05, 0.05, 0.07, 1.0)   # 검정 패치
            pent.setTwoSided(True)
            pent.setLightOff()
            pent.setPos(d * (R * 1.005))           # 표면에 살짝 띄워 박음
            pent.lookAt(d * (R * 2.0))             # +Y(법선)를 바깥으로 → 표면에 접하게

    def reset(self, xy=None):
        if xy is not None:
            self._spawn = Vec3(xy[0], xy[1], self.RADIUS)
        self.pos = Vec3(self._spawn)
        self.vel = Vec3(0, 0, 0)
        self.spin = Vec3(0, 0, 0)
        self.node.setPos(self.pos)

    def kick(self, hit_offset, direction, power):
        """총알 명중 — direction(정규화된 총알 진행방향)으로 추진, hit_offset(공중심→
        명중점)이 중심에서 벗어날수록 스핀이 실린다 → 휘어 나감."""
        d = Vec3(direction)
        if d.lengthSquared() < 1e-9:
            return
        d.normalize()
        self.vel += d * power
        # 빗맞은 정도 = offset 의 진행방향 수직 성분 → 토크(스핀). 위/아래 맞으면 z 회전.
        off = Vec3(hit_offset)
        torque = off.cross(d)          # 오른손 법칙 — 빗맞은 면에 따라 방향 결정
        self.spin += torque * (power * self.SPIN_FACTOR)
        if self.spin.length() > self.SPIN_CAP:
            self.spin = self.spin * (self.SPIN_CAP / self.spin.length())
        if self.vel.length() > self.MAX_SPEED:
            self.vel = self.vel * (self.MAX_SPEED / self.vel.length())

    def update(self, dt, half_x, half_y, goal_hw, goal_depth):
        """물리 적분 1스텝. 벽 반사 + 골 입구로 들어가 포켓에 갇힘. 포켓 깊숙이
        (|y| >= half_y+0.4) 들어가면 득점. 반환: 'A'/'B'/None (득점 팀)."""
        on_ground = self.pos.z <= self.RADIUS + 1e-3
        # 마그누스(휨) — F = MAGNUS * (spin × vel). 수평 커브가 주효과.
        if self.vel.lengthSquared() > 1e-6:
            self.vel += self.spin.cross(self.vel) * (self.MAGNUS * dt)
        # 중력
        self.vel.z -= self.GRAVITY * dt
        # 마찰 — 지면이면 구름마찰(수평), 공중이면 공기저항.
        if on_ground:
            damp = max(0.0, 1.0 - self.ROLL_FRICTION * dt)
            self.vel.x *= damp
            self.vel.y *= damp
        else:
            damp = max(0.0, 1.0 - self.LINEAR_DRAG * dt)
            self.vel.x *= damp
            self.vel.y *= damp
        self.spin *= max(0.0, 1.0 - self.SPIN_DRAG * dt)
        # 적분
        self.pos += self.vel * dt
        scored = None
        # 지면
        if self.pos.z < self.RADIUS:
            self.pos.z = self.RADIUS
            if self.vel.z < 0:
                self.vel.z = -self.vel.z * self.RESTITUTION
                if abs(self.vel.z) < 0.6:
                    self.vel.z = 0.0
        R = self.RADIUS
        in_mouth = abs(self.pos.x) <= goal_hw
        near_end = (self.pos.y > half_y - R) or (self.pos.y < -(half_y - R))
        in_pocket = in_mouth and near_end      # 골 입구 통과해 포켓 안/진입 중
        # 측벽 x — 포켓 안이면 골대 옆벽(±goal_hw), 아니면 필드 측벽(±half_x).
        x_bound = goal_hw if in_pocket else half_x
        if self.pos.x < -x_bound + R:
            self.pos.x = -x_bound + R
            self.vel.x = abs(self.vel.x) * self.RESTITUTION
        elif self.pos.x > x_bound - R:
            self.pos.x = x_bound - R
            self.vel.x = -abs(self.vel.x) * self.RESTITUTION
        # 끝벽 / 골 — 골 입구(|x|<=goal_hw) 안이면 포켓으로 들어가 뒷벽까지, 아니면 끝벽 반사.
        if in_mouth:
            score_line = half_y + 0.4          # 이만큼 들어가면 득점
            back = half_y + goal_depth         # 네트 뒷벽
            if self.pos.y >= score_line:
                scored = 'A'                   # 북쪽 골 → A 득점
            elif self.pos.y <= -score_line:
                scored = 'B'                   # 남쪽 골 → B 득점
            # 뒷벽 반사(득점 전 못 빠져나가게; 보통 득점이 먼저 일어남)
            if self.pos.y > back - R:
                self.pos.y = back - R
                self.vel.y = -abs(self.vel.y) * self.RESTITUTION
            elif self.pos.y < -(back - R):
                self.pos.y = -(back - R)
                self.vel.y = abs(self.vel.y) * self.RESTITUTION
        else:
            if self.pos.y < -half_y + R:
                self.pos.y = -half_y + R
                self.vel.y = abs(self.vel.y) * self.RESTITUTION
            elif self.pos.y > half_y - R:
                self.pos.y = half_y - R
                self.vel.y = -abs(self.vel.y) * self.RESTITUTION
        self.node.setPos(self.pos)
        self._spin_visual(dt)
        return scored

    def _spin_visual(self, dt):
        """무늬 구체를 실제로 회전 — 굴러가는 회전(속도 기반) + 물리 스핀을 누적해
        node 의 자세에 적용한다. 텍스처 무늬 덕에 회전이 눈에 보인다."""
        if not getattr(self, '_has_model', False):
            return
        # 각속도 = 구름(수평속도 → 수직축 기준 굴림) + 물리 스핀.
        horiz = Vec3(self.vel.x, self.vel.y, 0.0)
        omega = Vec3(self.spin)
        if horiz.length() > 0.02:
            roll_axis = Vec3(0, 0, 1).cross(horiz)   # 진행방향에 수직인 수평축
            if roll_axis.lengthSquared() > 1e-9:
                roll_axis.normalize()
                omega += roll_axis * (horiz.length() / self.RADIUS)
        mag = omega.length()
        if mag < 1e-5:
            return
        axis = omega * (1.0 / mag)
        dq = Quat()
        dq.setFromAxisAngleRad(mag * dt, axis)
        self._orient = dq * self._orient
        self._orient.normalize()
        self.node.setQuat(self._orient)

    def ray_hit(self, origin, direction):
        """ray(origin+ t*dir) vs 공(구) 교차. 맞으면 (t, hit_point) 아니면 None."""
        oc = origin - self.pos
        d = Vec3(direction)
        b = oc.dot(d)
        c = oc.dot(oc) - self.RADIUS * self.RADIUS
        disc = b * b - c
        if disc < 0:
            return None
        t = -b - disc ** 0.5
        if t < 0:
            t = -b + disc ** 0.5
        if t < 0:
            return None
        return t, origin + d * t

    def destroy(self):
        if self.node is not None:
            self.node.removeNode()
            self.node = None


class ZombieGame(ShowBase):
    def __init__(self, online=False, spawn_b=False, menu=True, soccer=False,
                 paint=False, jump=False):
        super().__init__()
        # 직접실행('--soccer'/'--paint'/'--jump') — 상대 없이 솔로(AI 봇)로 시작. 멀티는 메뉴로.
        self._paint_solo_launch = paint and not online
        self._soccer_solo_launch = soccer and not online
        self._jump_solo_launch = jump and not online
        # 점프맵 — 솔로(봇이 평행 레인에서 사격) / 멀티(2인 레이스+전투).
        self.jump_mode = bool(jump)
        self._jump = None
        self._jump_checkpoint = None
        self._jump_start_t = 0.0
        self._jump_finished = False
        # 아레나 스폰 측 — False=스폰 A(0,-15 북향), True=스폰 B(0,15 남향).
        # 두 클라이언트가 겹치지 않게 한쪽은 '--p2' 로 띄운다(릴레이는 역할 배정 못함).
        self._spawn_b = spawn_b
        # menu=True → 시작 화면(타이틀+싱글/멀티 선택)부터. False(=--online/--p2 직접
        # 실행)면 메뉴 건너뛰고 바로 해당 모드로 진입. _build_start_menu/_start_game 참조.
        self._use_menu = menu
        # 적 테두리 색 — settings.json 에서 불러옴(없으면 빨강). 시작 메뉴에서 변경.
        self.outline_color = _load_outline_color()
        self._remote_outline = None       # 상대 아바타 테두리 노드(라이브 색변경용)
        self._swatch_hl = None            # 메뉴 색 스와치 선택 하이라이트 프레임

        # ── 온라인(1:1 멀티) 모드 플래그 + 네트워크 상태 ────────────────────
        # online=True ('--online') 일 때만 소켓 접속 + 상대 아바타 + 적/웨이브
        # 정지 + 튜닝키 차단. 싱글(False)은 아래 변수들을 일절 안 쓰므로 동작 동일.
        self.online_mode = online
        # 축구 모드 — 총알로 공을 차서 골대에 넣는 1:1 멀티(킬은 5초 부활, 먼저 5골 승리).
        # _start_game(메뉴) 또는 '--soccer'(직접) 가 설정. online_mode 와 함께 켜진다.
        self.soccer_mode = soccer
        # 땅따먹기(영역 페인트) 모드 — 솔로(AI 봇) / 멀티. _start_game(메뉴) 또는
        # '--paint'(직접) 가 설정. 솔로 직접실행이면 ai_mode 도 함께 켠다.
        self.paint_mode = bool(paint)
        self._paint = None                # arena_data['paint'] 참조(셀/vdata)
        self._paint_my_id = 1             # 내 색 id(1=A 파랑/2=B 주황) — _setup_paint 가 확정
        self._paint_opp_id = 2
        self._health_packs = []           # 땅따먹기 — 적 시체 위 힐팩 [{node,x,y,t}]
        # AI 대결 모드 — 아레나에서 상대 자리에 AI 봇(소총 추격/무빙/사격). _start_game 이 설정.
        # 솔로 축구/땅따먹기/점프맵 직접실행이면 봇 상대로 함께 켠다.
        self.ai_mode = bool(self._paint_solo_launch or self._soccer_solo_launch
                            or self._jump_solo_launch)
        self.ai_max_hp = 100
        self.ai_hp = self.ai_max_hp
        self._ai_pos = Vec3(0, 0, 0)      # AI 봇 현재 위치(이동/충돌 해소 대상)
        self._ai_spawn = Vec3(0, 0, 0)    # AI 스폰(라운드 리셋 시 복귀)
        self._ai_yaw = 0.0
        self._ai_fire_t = 0.0             # 사격 쿨다운 누적(초)
        self._ai_foot_t = 0.0             # 발소리 보폭 누적(초)
        # 봇 부활 무적(축구/땅따먹기 솔로) — 죽으면 스폰 복귀 + 잠깐 무적 + 보호 링.
        self.AI_INVULN_DUR = 1.0
        self._ai_invuln_t = 0.0
        self._ai_invuln_ring = None
        # 점프맵 봇 — 자기 레인 코스를 웨이포인트 따라 스스로 진행.
        self.AI_JUMP_SPEED = 3.8          # 봇 코스 진행 속도(m/s) — 작을수록 쉬움
        self._ai_wp = []                  # 봇 경로(레인 B 발판 중심들)
        self._ai_wp_i = 1                 # 향하는 웨이포인트 인덱스
        self._ai_jump_z = 0.0             # 봇 현재 높이(호 포함)
        self._ai_jump_done = False        # 봇 결승 도달 여부
        self._ai_strafe_dir = 1           # 좌우 스트레이프 방향(+1/-1)
        self._ai_strafe_t = 0.0           # 스트레이프 방향 전환까지 남은 시간(초)
        # AI 튜닝 — 이동/교전 거리/사격.
        self.AI_SPEED = 4.2               # m/s
        self.AI_PREF_MIN = 5.0            # 이보다 가까우면 후퇴
        self.AI_PREF_MAX = 11.0           # 이보다 멀면 접근
        self.AI_SHOOT_RANGE = 32.0        # 이 안이면 사격 시도
        self.AI_FIRE_INTERVAL = 0.22      # 발 간격(초) — 소총 연사 느낌
        self.AI_DMG = 10                  # 한 발 명중 시 내 체력 감소
        # AI 탄약 — 다 쓰면 재장전(모든 모드). 재장전 중엔 사격 안 함.
        self.AI_AMMO_MAX = 25
        self.AI_RELOAD_DUR = 2.2          # 재장전 시간(초)
        self._ai_ammo = self.AI_AMMO_MAX
        self._ai_reload_t = 0.0
        # 준비방(로비) — 멀티 입장 시 이름 입력 + 양쪽 준비완료 후 시작.
        self.player_name = 'PLAYER'   # 멀티 입장 시 이름 입력으로 덮어씀(패킷에 실어 전송)
        self._in_lobby = False        # 준비방 진행 중(커서 보이게 + 마우스룩/카운트다운 보류)
        self._ready = False           # 내 준비완료 여부(패킷에 실어 전송)
        self._remote_ready = 0        # 상대 준비완료(수신)
        self._remote_name = ''        # 상대 이름(수신)
        self.lobby_root = None        # 준비방 UI 루트(자식 정리용)
        self.remote_state = None      # 수신 스레드가 최신 (x,y,z,yaw,pitch) 저장
        # 스냅샷 보간 버퍼 — 수신 스레드가 (t_recv, x, y, z, yaw) 누적, 메인 루프가
        # INTERP_DELAY 과거 시점을 두 스냅샷 사이로 보간(순간이동 완화). 락으로 보호.
        self._remote_buf = deque(maxlen=64)
        self._remote_buf_lock = threading.Lock()
        self.remote_avatar = None     # 상대 3인칭 아바타 Actor (online 일 때만 생성)
        self._sock = None
        self._net_alive = False
        self._net_send_t = 0.0        # 송신 스로틀 누적(초)
        self._remote_smooth = None    # 보간된 현재 위치 Vec3
        self._remote_prev = None      # 직전 프레임 위치(애니 run/idle 판정용)
        self._remote_anim = None      # 현재 상대 아바타 루프 애니 이름
        # 상대 아바타 손에 들 무기 — 로컬 weapon_anchor/right_hand_joint 방식을 복제.
        self._remote_hand = None          # av 의 RightHand 본 expose
        self._remote_weapon_anchor = None # av 손 본 월드 트랜스폼을 매 프레임 따라감
        self._remote_weapons = {}         # name -> 무기 NodePath
        self._remote_weapon_order = []    # 등록 순서(로컬과 동일: 0=권총 1=소총)
        self._remote_weapon_shown = None  # 현재 보이는 상대 무기 이름
        # 상대 발사/재장전 이벤트 재현 + 발소리 — 패킷의 reloading/shot_seq 로 감지.
        self._net_shot_seq = 0            # 내 발사 카운터(상대가 새 발사 감지용)
        self._remote_last_shot_seq = None # 마지막으로 본 상대 shot_seq (None=첫 패킷)
        self._remote_last_reloading = 0   # 직전 프레임 상대 재장전 플래그(상승 에지 감지)
        self._remote_action_t = 0.0       # 상대 단발 모션(재장전) 재생 중 loco 억제 타이머
        self._remote_foot_t = 0.0         # 상대 발소리 보폭 누적(초)
        # 상대 사운드 — 거리별 음량을 매번 바꿔야 해서 로컬과 별도 인스턴스로 로드(online).
        self._r_sfx_shot = []
        self._r_sfx_shot_i = 0
        self._r_sfx_m16 = []
        self._r_sfx_m16_i = 0
        self._r_sfx_reload = None
        self._r_sfx_foot = []
        self._r_last_foot_i = -1
        # 상대 플레이어 히트박스 — 적와 동일한 본 기반 (캡슐/머리 구). 사격 ray 로 검사.
        self._remote_hitboxes = []        # [(npa, npb, r, zone), ...]
        # PvP 체력 — 내가 상대에게 입힌 누적 피해(송신) / 상대가 나에게 입힌 누적값(수신).
        self._dmg_dealt = 0               # 내가 상대에 입힌 총 피해(패킷에 실어 보냄)
        self._remote_last_dmg_total = None  # 상대가 나에게 입힌 누적값 마지막(첫=None)
        self._pvp_dead_t = 0.0            # 사망 후 리스폰까지 남은 시간(초; >0 이면 사망중)
        self._deaths = 0                  # 내가 죽은 누적 횟수(패킷에 실어 보냄)
        self._remote_last_deaths = None   # 상대 사망 누적값 마지막(첫=None; 증가=내 킬)
        # PvP 점수 — 상대를 죽이면 내 점수 +1, 내가 죽으면 상대 점수 +1. 먼저 10점=승리.
        self.WIN_SCORE = 10
        self._my_score = 0                # 내가 상대를 처치한 횟수(= 내 점수)
        self._enemy_score = 0             # 내가 죽은 횟수(= 상대 점수, self._deaths 와 동일)
        self._match_over = False          # 매치 종료 플래그(이후 점수/리스폰 정지)
        # ── 축구 모드 상태 ────────────────────────────────────────────────
        self.SOCCER_WIN = 5               # 먼저 이 골 수 넣으면 승리
        # 무기별 공 차는 파워(m/s) — 소총이 권총보다 강하다.
        self.SOCCER_KICK_RIFLE = 25.0
        self.SOCCER_KICK_PISTOL = 15.0
        self._ball = None                 # SoccerBall (soccer_mode 일 때 생성)
        self._goals_a = 0                 # 북쪽 골(스폰 A 공격) 누적 — A 득점
        self._goals_b = 0                 # 남쪽 골(스폰 B 공격) 누적 — B 득점
        self._goal_cele_t = 0.0           # 골 세리머니/킥오프 대기 잔여(초)
        self._am_a = True                 # 내가 스폰 A 인가(공 권위·득점 매핑). 역할배정 시 갱신
        # 공 동기화 — 권위(A)가 공/점수 브로드캐스트, 양쪽이 자기 킥을 이벤트로 전송.
        self._kick_seq = 0                # 내가 공 찬 횟수(전송) — 권위가 증가 감지 시 적용
        self._kick_off = Vec3(0, 0, 0)    # 마지막 킥 명중 오프셋(전송용)
        self._kick_dir = Vec3(0, 0, 0)    # 마지막 킥 방향(전송용)
        self._kick_power = 0.0            # 마지막 킥 파워(전송용)
        self._remote_kick_seq = None      # 상대가 보낸 마지막 kick_seq(권위가 적용 판정)
        self._soccer_wait_t = 0.0         # 솔로 시작 대기 누적(상대 없으면 A 로 시작)
        self.hud_goal_banner = None       # 골 배너(OnscreenText) — _build_soccer_hud
        # 부활 무적 — 리스폰 후 INVULN_DUR 초 동안 피해 무효 + 보호 링 표시.
        self.INVULN_DUR = 3.0
        self._invuln_t = 0.0
        self._invuln_ring = None
        # 슬로우모션 — 매치 종료 시 dt 와 모든 애니메이션 재생속도를 SLOWMO_FACTOR 로
        # 부드럽게 떨어뜨려 영화 같은 슬로우모션 연출. _time_scale 은 매 프레임 target 으로 수렴.
        self.SLOWMO_FACTOR = 0.18         # 슬로우모션 배속(1.0=정상, 0.18=약 5.5배 느림)
        self.SLOWMO_RAMP = 0.9            # target 까지 수렴에 걸리는 실시간(초)
        self._time_scale = 1.0
        self._time_scale_target = 1.0
        self._remote_tracer = None        # 상대 총알 궤적 노드(online 일 때 생성)
        self._remote_tracer_t = 0.0       # 상대 트레이서 표시 남은 시간(초)
        # PvP 아레나 — 스폰 배리어로 5초 가둠 후 해제(FIGHT). build_arena 데이터.
        self._arena_data = None
        self._spawn_barriers = []         # 런타임이 collider.walls 에 add/remove
        self._shimmer_cards = []          # 배리어 반투명 카드(해제 시 fade)
        self._barriers_active = False     # 배리어가 walls 에 들어가 있는 동안 True
        self._countdown_t = None          # None=상대 대기, 5.0→0 카운트다운
        self._fight_t = 0.0               # FIGHT! 배너 잔여 표시(초)
        self._shimmer_a = 0.25            # shimmer 현재 alpha (fade 용)
        self._shimmer_fading = False
        self._spawn_pos = Vec3(0, 0, 0)   # 리스폰 지점(아레나면 내 스폰)
        self._spawn_yaw = 0.0
        self._platforms = []              # 올라타는 박스 [{x0,x1,y0,y1,top,collider}]
        self._step_assist = 0.45          # 이 높이 차 이내면 옆면 통과+윗면 스냅(스텝업)
        # 데스캠 — 사망 시 3초간: 죽은 사람은 자기 시체 위 3인칭 뷰(고정), 죽인 사람은 자유 이동.
        self.DEATHCAM_DUR = 3.0
        self._deathcam_t = 0.0            # >0 이면 데스캠/유예 진행 중(끝나면 라운드 리셋)
        self._dead = False                # 내가 이번 라운드 사망자인가(시점 고정+시체)
        self._corpse = None               # 죽은 사람(나 또는 상대) 시체 Actor
        self._dropped_weapons = []        # 사망 시 바닥에 떨군 무기 노드(라운드 리셋 시 정리)
        self._death_yaw = 0.0             # 죽은 순간 방향(데스캠 카메라 각도용)
        self._remote_death_anim = None    # (구) 미사용
        self._remote_hidden_for_death = False  # 상대를 시체로 대체하며 av 숨겼는지
        # 스폰 자동 배정 — 세션 고정 랜덤 nonce. 상대 nonce 와 비교해 큰 쪽=A, 작은=B.
        self._nonce = random.randint(1, 0xFFFFFFFF)
        self._role_decided = False        # 첫 상대 패킷의 nonce 로 스폰 확정

        # 윈도우/마우스 — 시작 메뉴 동안은 커서 보이게(버튼 클릭용). 게임 시작 시
        # _build_world() 가 커서 숨김 + 화면 가둠(FPS 마우스룩)으로 전환한다.
        props = WindowProperties()
        props.setTitle('zombie_game')
        self.win.requestProperties(props)
        self.disableMouse()  # ShowBase 기본 마우스-카메라 비활성
        self._is_fullscreen = False   # F11 토글 — 진짜 전체화면(작업표시줄 가림)
        self.setBackgroundColor(0.015, 0.020, 0.030)   # 어두운 검푸른 야간 하늘

        # ── 설정/오디오/릴레이 상태 — 메뉴(SETTINGS/로비)에서 _build_world 전에도
        # 쓰이므로 여기서 먼저 초기화한다. (게임 시작 시 _build_world 가 덮지 않음) ──
        self.SENS_MIN = 0.005     # 슬라이더 0 — 매우 느림
        self.SENS_MAX = 0.18      # 슬라이더 1 — 매우 빠름 (기하평균=0.03)
        self._sens_norm = 0.5     # 슬라이더 위치(0~1) — 기본 중앙
        self.mouse_sens = self._sens_from_norm(self._sens_norm)  # = 0.03
        self._vol_master = 1.0    # 오디오 볼륨(0~1) — 일시정지/설정 공통
        self._vol_sfx = 1.0
        self._relay_host = None   # 로비에서 입력한 릴레이 주소(없으면 모듈 기본)
        self._relay_port = None

        # ── 시작 화면 ───────────────────────────────────────────────────────
        # 타이틀 + 싱글/멀티/종료 메뉴. 월드 빌드(_build_world)는 메뉴 선택 이후로
        # 미룬다 — online_mode 가 레벨(아레나 vs 캠페인)·적·네트워크를 좌우하므로
        # 모드가 정해지기 전엔 만들 수 없다. _use_menu=False 면 바로 빌드.
        self._game_started = False
        self._menu_root = None
        if self._use_menu:
            self._build_start_menu()
        else:
            self._build_world()

    def _build_world(self):
        # 게임 진입 — 커서 숨김 + 화면 가둠(FPS 마우스룩). 메뉴를 거쳤든 직접
        # 실행이든 실제 게임 월드는 여기서 한 번만 만들어진다.
        gprops = WindowProperties()
        gprops.setCursorHidden(True)
        gprops.setMouseMode(WindowProperties.M_confined)
        self.win.requestProperties(gprops)

        # 환경
        self.setBackgroundColor(0.015, 0.020, 0.030)   # 어두운 검푸른 야간 하늘
        self._make_lights()
        # GPU 스키닝 보장 — 상단 PRC 두 플래그는 fixed-function 경로라 요즘 드라이버에선
        # 무시되고 조용히 CPU 스키닝으로 폴백하는 경우가 흔함. auto-shader 가 진짜 HW
        # 스키닝 셰이더를 생성해줘서 적 다수 시 vertex 변환이 GPU 로 옮겨감.
        # (simplepbr 는 텍스처/IBL 없는 Mixamo 모델에선 오히려 더 평평·칙칙해 되돌림.)
        self.render.setShaderAuto()
        self._make_ground()
        # level.py 가 render 아래에 방·벽·기둥을 만들고 collider + 적 spawn 좌표 반환.
        # 키트 .bam 이 있으면 단색 벽 카드를 끄고(z-fighting 방지) kit_map 메쉬로 대체.
        import os
        kit_available = USE_KIT_MAP and os.path.isfile("assets/kit/Wall_1.bam")
        self.kit_root = None
        if self.jump_mode:
            # 점프맵 — 길쭉한 평행 레인 + 점프 발판.
            self.level_collider, self.level_data = build_jump_field(
                self.render, draw_wall_cards=True)
            self._arena_data = self.level_data
            kit_available = False
        elif self.paint_mode:
            # 땅따먹기 — 개방적 아레나 + 바닥 페인트 격자.
            self.level_collider, self.level_data = build_paint_field(
                self.render, draw_wall_cards=True)
            self._arena_data = self.level_data
            kit_available = False
        elif self.soccer_mode:
            # 총알 축구 — 장애물 없는 열린 잔디 필드 + 골대.
            self.level_collider, self.level_data = build_soccer_field(
                self.render, draw_wall_cards=True)
            self._arena_data = self.level_data
            kit_available = False
        elif self.online_mode or self.ai_mode:
            # 1대1 PvP(온라인) / AI 대결 — 적 캠페인 레벨 대신 대칭 아레나.
            self.level_collider, self.level_data = build_arena(
                self.render, draw_wall_cards=True)
            self._arena_data = self.level_data
            kit_available = False
        else:
            self.level_collider, self.level_data = build_level(
                self.render, draw_wall_cards=not kit_available)
        if kit_available:
            # kit_map.py 가 같은 collider.walls 위에 Quaternius sci-fi 키트 메쉬를
            # 입힌다 (보이는 벽 = 부딪히는 벽).
            try:
                from kit_map import build_kit_visuals
                self.kit_root = build_kit_visuals(self.render, self.level_collider)
                print("[zombie_game] kit_map 시각 레이어 적용됨")
            except Exception as e:
                print(f"[zombie_game] kit_map 실패 ({e}) — 단색 벽으로 폴백")
                for w in self.level_collider.walls:
                    w.make_card(self.render)

        # 단색 벽 카드(level.py)는 두께 0 의 앞/뒤 카드가 같은 평면에 겹쳐 있어, 그림자
        # 깊이맵에서 자기 자신에게 그림자를 드리워 벽에 물결(섀도우 애크네)이 생긴다.
        # → 벽을 그림자 '캐스팅'에서만 제외(SHADOW_CASTER_MASK off). 받기(receive)는
        # 그대로라 캐릭터·적 그림자는 벽에 정상적으로 비친다. 두께 있는 키트 메쉬는 제외 안 함.
        if self.kit_root is None:
            for w in self.render.findAllMatches('**/wall'):
                w.hide(SHADOW_CASTER_MASK)

        # 카메라 — 캐릭터 머리 안쪽에서 보더라도 클리핑 안 되게 near 매우 작게.
        # FOV 크면 시야 넓어지고 자기 몸이 작게 보임 (FPS 표준 90~100).
        self.camLens.setNear(0.01)
        self.fov_hip = 100.0          # hip-fire 기본 FOV
        self.fov_ads = 55.0           # ADS (우클릭 hold) zoom-in FOV
        self.camLens.setFov(self.fov_hip)

        # ADS (aim down sights) 상태
        self.aiming = False           # 우클릭 hold 동안 True
        self._mouse1_down = False      # 좌클릭 hold 상태 (연발 무기 연사용)
        # 무기 스왑 모션 상태 — 'idle'/'down'/'up', 팔 내림 offset(z) 애니메이션.
        self._swap_state = 'idle'
        self._swap_t = 0.0
        self._swap_z = 0.0
        self._swap_pending_idx = 0
        self.aim_t = 0.0              # 0=hip / 1=ADS 보간 (지수 ramp)
        self.aim_speed = 9.0          # 1/sec — 클수록 빠른 전환 (~110ms)
        # ADS 시 ybot 전체를 player-frame 으로 이 만큼 이동, 카메라는 같은 양 보정.
        # 결과: 손·팔·총 다 같이 이 지점으로 이동, 시점(world background) 정적.
        # 단위 m. (X=우/좌, Y=앞/뒤, Z=위/아래). 현재: 좌 13cm + 앞 5cm + 아래 2cm.
        self.ads_body_offset = Vec3(-0.13, 0.05, -0.02)
        # 무기별 "보이는 몸" 오프셋 — 장착 무기에 따라 _equip_weapon 이 갱신.
        # ADS 오프셋과 동일 원리(몸만 이동, 카메라·히트박스 불변) 지만 항상 적용.
        self.weapon_body_offset = Vec3(0, 0, 0)
        self.weapon_body_hpr = Vec3(0, 0, 0)   # 보이는 몸 회전(H,P,R deg)
        self._tune_mode = 'weapon'   # 'weapon'=총 위치, 'body'=보이는 몸 위치/회전
        # ADS 시 마우스 감도 배율 — 작을수록 좌우 시점이 천천히·작게.
        self.ads_mouse_factor = 0.35
        # ADS 시 이동 속도 배율 — 작을수록 천천히 걸음.
        self.ads_move_factor  = 0.40

        # 플레이어 상태 (panda3d 표준: Z-up, Y-forward)
        self.player_pos = Vec3(0, 0, 0)  # 발 기준
        self.player_yaw = 0.0            # H (좌우)
        self.player_pitch = 0.0          # P (위아래)
        self.player_vz = 0.0
        self.on_ground = True
        self.head_height = 1.65
        self.move_speed = 4.0   # 적 추격 속도와 동일 (Zombie.move_speed)
        # 무기별 이동속도 배율 — 권총은 가벼워 빠름(소총 대비 1.3배). _equip_weapon 갱신.
        self._weapon_speed_mult = 1.0
        # 피격 연출 — 화면 흔들림 + 피격 후 잠깐 감속(플레이어/AI 봇).
        self._shake_t = 0.0       # 카메라 흔들림 남은 시간
        self._shake_dur = 0.0
        self._shake_mag = 0.0     # 흔들림 진폭(deg)
        self._slow_t = 0.0        # 플레이어 피격 감속 남은 시간
        self._ai_slow_t = 0.0     # AI 봇 피격 감속 남은 시간
        self.HIT_SLOW_DUR = 0.45  # 피격 감속 지속(초)
        self.HIT_SLOW_MULT = 0.55 # 감속 중 이동속도 배율
        self.HUD_SWAP_DUR = 0.26  # 무기 교체 시 HUD 실루엣 스왑 애니 길이(초)
        # (감도/오디오/릴레이 상태는 __init__ 에서 이미 초기화 — 여기서 덮지 않음)
        self.jump_speed = 5.0   # 정점 ~1.04m — 낮은 플랫폼(≤1.0)에 점프해 올라설 수 있게
        self.gravity = 12.0

        # Y Bot Actor (월드에 직접 부착)
        self.ybot = Actor(BAM_PATH)
        self.ybot.reparentTo(self.render)
        self.ybot.setPos(self.player_pos)
        # Mixamo Y Bot은 보통 panda -Y를 봄. 캐릭터 forward를 +Y(player_yaw=0 시
        # 카메라가 보는 방향)에 맞추려면 H 에 180을 더해야 함.
        self.ybot.setH(self.player_yaw + 180)
        self.anim_names = list(self.ybot.getAnimNames())
        print(f'[zombie_game] animations: {self.anim_names}', flush=True)

        # 골격을 3파트로 분리.
        #   lower : Hips + 다리/발            → 항상 locomotion (펀치 모드에서도 다리는 안 멈춤)
        #   upper : Spine + 자손 (손 제외)   → locomotion
        #   hands : 양손 + 손가락             → Shoot 단발 또는 upper 와 동기화
        # 글로브 패턴 주의: '*' 는 빈 문자열 포함이라 'Spine' 만 정확히 매치하고
        # 'Spine1' 은 매치 안 함 → upper 의 include='*Spine' 으로 Spine 본 하나만
        # 잡고 자손은 hierarchy 로 자동 포함. lower 의 exclude='*Spine*' 은 양옆
        # 와일드카드라 Spine/Spine1/Spine2 모두 잡아 자손까지 lower 에서 제외.
        # 그리고 Actor 내부 traversal 이 `if include / elif exclude` 순서라 include
        # 패턴이 너무 광범위하면 exclude 가 무시되므로 include 는 좁게 잡는 게 안전.
        self._parts = ('lower', 'upper', 'hands')
        self.ybot.makeSubpart(
            'lower',
            includeJoints=['*Hips'],
            excludeJoints=['*Spine*', '*LeftHand*', '*RightHand*'],
        )
        self.ybot.makeSubpart(
            'upper',
            includeJoints=['*Spine'],
            excludeJoints=['*LeftHand*', '*RightHand*'],
        )
        self.ybot.makeSubpart(
            'hands',
            includeJoints=['*LeftHand*', '*RightHand*'],
        )

        # 블렌딩 모드: 여러 애니메이션을 동시에 돌리면서 weight 로 섞는다.
        # Unity 의 crossfade 와 동일한 효과 — 액션 전환 시 움찔거림 제거.
        self.ybot.enableBlend()
        if 'Idle' in self.anim_names:
            for p in self._parts:
                self.ybot.loop('Idle', partName=p)

        # Kneel 상태 머신: stand → (going_down=StandToKneel 단발) → kneel
        #                 kneel → (going_up=KneelToStand 단발) → stand
        # transition 중에는 이동/사격 모두 잠금.
        self.kneel_state = 'stand'
        self.current_anim = 'Idle'        # upper 파트의 현재 상태 (HUD 표시용)
        self._hands_oneshot = False       # hands 가 Shoot 단발 중인지
        self._anim_token = 0              # Kneel transition 단발 토큰
        self._hands_token = 0             # Shoot 단발 토큰
        self._reload_oneshot = False
        self._reload_token = 0
        # 각 파트·애니메이션의 현재 weight, 목표 weight. _update_blend 가 매 프레임
        # 지수 평활로 current → target 수렴시킨다.
        self._current_w = {
            p: {a: (1.0 if a == 'Idle' else 0.0) for a in self.anim_names}
            for p in self._parts
        }
        self._target_w = {p: dict(d) for p, d in self._current_w.items()}
        for p in self._parts:
            for a, w in self._current_w[p].items():
                self.ybot.setControlEffect(a, w, partName=p)
        self.blend_speed = 14.0       # 크면 빠른 전환, 작으면 부드러움
        self.blend_out_time = 0.18    # 단발 anim 끝나기 이만큼 전부터 다음 상태로 페이드
        # 재장전 종료 시 자세 복귀가 휙 튀지 않게 잠깐 느린 블렌드 사용.
        self._slow_blend_t = 0.0          # >0 이면 느린 블렌드(초)
        self.slow_blend_speed = 5.0       # 재장전 복귀용 느린 전환 속도
        self.reload_return_slow_dur = 0.5 # 재장전 끝 느린 블렌드 지속(초)

        # 모든 locomotion anim 을 양쪽 파트에서 항상 loop — weight 가 0 이어도
        # 내부 time 은 흐르고, 보이는 건 _current_w 가 결정. 액션 전환 시 시작
        # 프레임이 갑자기 튀지 않게 함.
        self._loop_anim_set = {
            'Idle', 'RunForward', 'RunBackward', 'StrafeL', 'StrafeR',
            'KneelIdle', 'Jump',
            # Walk* 도 loop 만 깔아둠 — 현재 코드에선 미사용이지만 추후 Shift+이동
            # 같은 걸 붙일 때 시작 프레임이 튀지 않게 미리 돌려 둠.
            'WalkForward', 'WalkBackward',
            # 소총(Pro Rifle Pack) 로코모션 — 소총 장착 시 _target_anim 이 선택.
            'RifleIdle', 'RifleRunForward', 'RifleRunBackward',
            'RifleStrafeL', 'RifleStrafeR', 'RifleKneelIdle', 'RifleJump',
            'RifleWalkForward', 'RifleWalkBackward',
        }
        for a in self.anim_names:
            if a in self._loop_anim_set:
                for p in self._parts:
                    self.ybot.loop(a, partName=p)

        # 사격 반동 — 카메라가 아닌 weapon_anchor 에 적용해서 권총+팔이 살짝
        # 뒤로 빠지는 효과. recoil_back 만 사용, pitch 킥은 거슬려서 제거.
        self.recoil_back = 0.0           # 현재 반동 양 (m, world 단위)
        self.recoil_decay = 10.0         # 1/sec, 클수록 빨리 복귀
        self.recoil_shoot_back = 0.03    # 발사 시 인가되는 뒤로 오프셋 (3cm — pistol 적당)

        # 탄 퍼짐(발로란트식) 상태 — 연사 카운터 + 이번 발 각도 편차(deg).
        self._spray_shots = 0     # 이번 버스트에서 쏜 발수 (idle 시 리셋 → 첫발 정확)
        self._spray_idle = 0.0    # 마지막 발 이후 경과(초)
        self._shot_yaw_off = 0.0  # 이번 발 좌우 편차 (deg) — ray/tracer 둘 다 적용
        self._shot_pitch_off = 0.0
        self.JUMP_SPREAD_DEG = 9.0  # 공중(점프) 사격 시 첫발부터 더해지는 큰 랜덤 콘(deg)

        # Reload 중 W/S 걸을 때 lower 가 Idle 로 고정되어 몸이 미끄러지는 느낌
        # → ybot 에 사인파 Z bob 을 더하고 카메라엔 같은 값을 빼서 상쇄. 화면은
        # 정적, 자기 팔·손·총만 위아래로 까딱이는 효과. _walk_bob_t 로 reload+이동
        # 조건일 때만 ramp in, 끝나면 ramp out.
        self._walk_bob_t = 0.0
        self._walk_bob_phase = 0.0
        self._walk_bob_amp_z = 0.025     # peak ±2.5cm
        self._walk_bob_freq = 10.0       # rad/s (≈ 1.6 Hz)
        self._walk_bob_speed = 5.0       # in/out ramp 1/sec

        # Hips root motion 상쇄용. Mixamo 머지 .bam 은 각 액션의 Hips 시작 위치가
        # 미묘하게 달라서 (예: Idle Y=-0.944, Shoot Y=-0.892) 액션 전환 시 캐릭터
        # 전체가 5cm 가량 카메라 방향으로 평행이동 → 머리가 카메라 안으로 밀려들어와
        # 뒤통수가 화면을 덮음. 매 프레임 Hips 의 actor-local XY drift 를 측정해서
        # actor NodePath 를 반대로 밀어줘서 시각적 anchor 를 고정한다. Z(높이) 는
        # 그대로 둬서 anim 의 자연스러운 body bob 은 유지.
        hips_name = next(
            (j.getName() for j in self.ybot.getJoints() if j.getName().endswith('Hips')),
            None,
        )
        head_name = next(
            (j.getName() for j in self.ybot.getJoints() if j.getName().endswith('Head')),
            None,
        )
        print(f'[zombie_game] hips/head joints: {hips_name} / {head_name}', flush=True)
        # makeSubpart 이후 'modelRoot' 는 어느 subpart 에도 속하지 않은 본만 다루므로
        # exposeJoint 는 본이 실제로 속한 subpart 이름으로 호출해야 함. 카메라가
        # head 본을 따라가야 하므로 매 프레임 위치가 필요. Hips=lower, Head=upper.
        self.hips_joint = (
            self.ybot.exposeJoint(None, 'lower', hips_name) if hips_name else None
        )
        self.head_joint = (
            self.ybot.exposeJoint(None, 'upper', head_name) if head_name else None
        )
        self._hips_ref_local = None
        # pitch 회전 피벗용 — RightShoulder world pos 를 pre/post 캡처해서 ybot 평행
        # 이동으로 보정 → 어깨 기준 회전 효과.
        rshoulder_name = next(
            (j.getName() for j in self.ybot.getJoints()
             if j.getName().endswith('RightShoulder')), None)
        self.rshoulder_joint = (
            self.ybot.exposeJoint(None, 'upper', rshoulder_name)
            if rshoulder_name else None
        )

        # 권총 메쉬: RightHand 본에 attach — 본 transform 따라 손에 붙어 다님.
        rhand_name = next(
            (j.getName() for j in self.ybot.getJoints() if j.getName().endswith('RightHand')),
            None,
        )
        self.right_hand_joint = (
            self.ybot.exposeJoint(None, 'hands', rhand_name) if rhand_name else None
        )
        # 무기 레지스트리 — 권총/소총 모두 weapon_anchor 에 붙여두고 활성 1개만 show.
        # anchor 갱신은 _update 안에서 ybot.update(force=True) 직후에 호출 —
        # 별도 task 로 두면 frame order 가 어긋나서 1프레임 lag (잔상) 발생.
        self.slide_recoil = 0.0
        self.slide_recoil_kick = 0.4   # 모델 local units (음수 X 로 후퇴)
        self.slide_recoil_decay = 14.0 # 1/sec — 클수록 빠른 복귀

        self.weapon = None
        self.weapon_name = None
        self.slide_node = None
        self.slide_rest_x = 0.0
        self._weapons = {}        # name -> dict(node, slide_node, slide_rest_x, muzzle)
        self._weapon_order = []   # 휠 순환 순서 (로드 성공한 것만)
        self._weapon_idx = 0

        if self.right_hand_joint is not None and not self.right_hand_joint.isEmpty():
            self.weapon_anchor = self.render.attachNewNode('weapon_anchor')
            # 순서 = 휠 순환 순서: [0]=권총, [1]=소총.
            self._register_weapon('pistol', WEAPON_PATH,
                                  WEAPON_LOCAL_SCALE, WEAPON_LOCAL_POS,
                                  WEAPON_LOCAL_HPR, WEAPON_MUZZLE_POS)
            self._register_weapon('rifle', RIFLE_PATH,
                                  RIFLE_LOCAL_SCALE, RIFLE_LOCAL_POS,
                                  RIFLE_LOCAL_HPR, RIFLE_MUZZLE_POS,
                                  prerot=RIFLE_LOCAL_PREROT)
            if self._weapon_order:
                self._weapon_idx = 0
                self._equip_weapon(self._weapon_order[0])
            else:
                print('[zombie_game] WARN no weapon loaded', flush=True)
        else:
            print(f'[zombie_game] WARN weapon not loaded (rhand={rhand_name})',
                  flush=True)

        # 총구(muzzle) marker — 평소엔 비활성. ENABLE_MUZZLE_MARKER=True 일 때만
        # 붙는다 (muzzle_marker.py). RIFLE_MUZZLE_POS 재조정용 튜닝 하네스.
        self.muzzle_marker = None
        if ENABLE_MUZZLE_MARKER and not self.online_mode:
            # 멀티에선 개발용 튜닝 하네스(L 토글 포함) 안 붙임.
            from muzzle_marker import MuzzleMarker
            self.muzzle_marker = MuzzleMarker(self)
        print('[weapon-tune] B로 모드 순환(weapon→body→both→ads) | '
              '위치 ←/→ ↑/↓ PgUp/PgDn | 회전 [ ]=H  ; \'=P  , .=R | P=현재값 출력 '
              '(weapon=총만 / body=몸만 / both=소총+몸 / ads=줌 오프셋[우클릭 hold])',
              flush=True)
        # 카메라를 Head 본의 월드 좌표에 매 프레임 따라붙임. 머리가 애니메이션으로
        # 흔들려도 카메라가 동행하니까 자기 뒤통수가 보이는 일이 없음.
        # 시선 방향(yaw/pitch) 은 마우스 입력 그대로 — head 본의 회전은 무시.
        self.eye_forward_offset = 0.18  # 머리 본 중심에서 시선 방향으로 m
        self.eye_lateral_offset = 0.10  # 카메라를 왼쪽으로 (m) → 권총 우측 배치

        # 입력
        self.keys = {'w': False, 'a': False, 's': False, 'd': False, 'space': False}
        # editor 모드: F2 로 토글하는 free-cam. 진입 시 현재 카메라 위치/방향에서
        # 시작하고 마우스 룩 + WASD/Space 로 자유 비행.
        self.editor_mode = False
        self.editor_pos = Vec3(0, -5, 1.6)
        self.editor_yaw = 0.0
        self.editor_pitch = 0.0
        self.editor_speed = 8.0
        self._bind_inputs()

        # 마우스 센터링
        self._win_cx = self.win.getXSize() // 2
        self._win_cy = self.win.getYSize() // 2
        self.win.movePointer(0, self._win_cx, self._win_cy)
        self._first_frame = True

        # ── HUD ──────────────────────────────────────────────────────────
        self._interact_target = None    # 현재 가까이 있는 dead 적
        self.interact_range = 2.5       # m
        self._gate_msg_token = 0
        # 플레이어 코어 무결성 ("체력"). 아직 적 공격이 데미지를 안 주지만
        # HUD 요소로 노출 — take_core_damage() 로 깎으면 자동 반영된다.
        self.core_integrity = 100
        self.core_integrity_max = 100
        # 피격 방향 표시 — 데미지 입은 방향으로 조준점 둘레 빨간 아크, 잠깐 보이고 fade.
        self._dmg_arc_geom = None
        self._dmg_dir_t = 0.0
        self._dmg_dir_dur = 1.1         # 아크 표시 후 fade 지속(초)
        self.purified = 0               # 처치 카운터
        # 글리치 상태: _glitch_t > 0 이면 빨강으로 표시.
        self._glitch_t = 0.0
        self._glitch_cooldown = random.uniform(6.0, 11.0)
        # 탄창 (HUD 도트 개수 계산에 ammo_max 가 필요 → _build_hud 전에 정의)
        self.ammo_max = 8
        self.ammo = self.ammo_max
        self._build_hud()

        # 사격 쿨다운
        # 발사 쿨다운 — 이전엔 Shoot anim 끝까지 (~1초+) 막혀서 너무 느렸음.
        # 0.18s = 약 5.5 발/초. 값 줄이면 더 빨라짐 (자동소총 0.1, 권총 0.2 정도).
        self.shoot_cooldown_t = 0.0
        self.shoot_cooldown_dur = 0.18

        # 효과음 — 발사(동시 겹침 풀) / 재장전
        self.sfx_shot_pool = self._load_sfx_pool('shot.wav', 4)
        self._sfx_shot_i = 0
        # 소총(M16) 발사음 — 연발 빠른 연사라 겹침 풀 넉넉히(8개) 로 끊김 방지.
        self.sfx_m16_pool = self._load_sfx_pool('m16sound.mp3', 8)
        self._sfx_m16_i = 0
        # 소총 발사음 볼륨 — 기본(1.0) 대비 +30%. (Panda3D 는 1.0 초과 증폭 허용)
        for _s in self.sfx_m16_pool:
            _s.setVolume(1.3)
        self.sfx_reload = self._load_sfx('Reload.wav')
        # 빈 탄창 클릭 — 총알 없을 때 발사 시도하면 권총·소총 공통으로 재생.
        self.sfx_empty = self._load_sfx('emptygun.wav')
        self._empty_click_t = 0.0   # 빈총 소리 연타 방지 쿨다운(초)

        # 발소리 — f1/f2/f3 중 랜덤 재생하되 직전과 같은 건 안 나오게(중복 방지).
        self.sfx_foot = [s for s in (self._load_sfx('f1.mp3'),
                                     self._load_sfx('f2.mp3'),
                                     self._load_sfx('f3.mp3')) if s is not None]
        self._last_foot_i = -1
        self._footstep_t = 0.0          # 다음 발소리까지 남은 시간(초)
        self.footstep_interval = 0.30   # run 기준 보폭 간격(낮을수록 빠름). ADS 면 늘림

        # 킬 사운드 (Valorant) — 연속 헤드샷 킬 콤보로 단계 상승.
        #   1킬 → 1st. 직전 킬 5초 이내 + 헤드샷이면 2nd→3rd→4th→5th-6th 로 상승,
        #   그 뒤로는 계속 5th-6th. 콤보 끊기면(5초 초과 or 헤드샷 아님) 다시 1st.
        self.sfx_kill = {
            1: self._load_sfx('valorant-1st-kill-sound.mp3'),
            2: self._load_sfx('valorant-2nd-kill-sound.mp3'),
            3: self._load_sfx('valorant-3rd-kill-sound.mp3'),
            4: self._load_sfx('valorant-4th-kill-sound.mp3'),
            5: self._load_sfx('valorant-5th-6th-kill-sound.mp3'),
        }
        self._last_kill_snd = None
        self._kill_tier = 0             # 현재 콤보 단계 (1..5)
        self._combo_window = 0.0        # 콤보 유지 남은 시간(초)
        self.kill_combo_dur = 5.0       # 연속킬 인정 시간
        self.kills = 0                  # 총 처치 수 (HUD)

        # 피격 사운드 — 부위(head/body/other) 상관없이 Voicy_Headshot 으로 통일.
        # 연사로 빠르게 겹칠 수 있어 풀로 로드해 라운드로빈 재생.
        self.sfx_hit = self._load_sfx_pool('Voicy_Headshot .mp3', 4)
        self._hit_i = 0
        for _s in self.sfx_hit:
            _s.setVolume(0.4)

        # 피격 파티클 — Kenney particle pack 의 fire 스프라이트. 맞은 부위에 랜덤 1개.
        _fire_dir = SCRIPT_DIR / 'kenney_particle-pack' / 'PNG (Transparent)'
        self._fire_tex = []
        for fn in ('fire_01.png', 'fire_02.png'):
            t = self.loader.loadTexture(
                Filename.from_os_specific(str(_fire_dir / fn)))
            if t is not None:
                self._fire_tex.append(t)
        self._hit_particles = []        # [{np, t, dur, base}, ...] — _update 가 animate
        print(f'[fx] fire 파티클 {len(self._fire_tex)}종 로드', flush=True)
        # 재장전 사운드 길이에 맞춰 Reload 애니메이션 속도를 동기화 (오디오 원음 유지).
        # 권총=Reload, 소총=RifleReload 둘 다 처리. 실제 재생 시간을 _reload_dur 에
        # 저장해 타이머에 사용. 과한 워핑은 클램프(0.6~1.6)로 방지.
        self._reload_dur = {}
        snd_len = (self.sfx_reload.length()
                   if self.sfx_reload is not None else 0.0)
        for _ranim in ('Reload', 'RifleReload'):
            if _ranim not in self.anim_names:
                continue
            anim_len = self.ybot.getDuration(_ranim)
            play_dur = anim_len
            if snd_len > 0.05 and anim_len > 0.05:
                rate = max(0.6, min(1.6, anim_len / snd_len))
                for _pp in ('upper', 'hands'):
                    self.ybot.setPlayRate(rate, _ranim, partName=_pp)
                play_dur = anim_len / rate
                print('[sfx] %s synced: snd=%.2fs anim=%.2fs rate=%.2f -> %.2fs'
                      % (_ranim, snd_len, anim_len, rate, play_dur), flush=True)
            self._reload_dur[_ranim] = play_dur
        self._reload_play_dur = self._reload_dur.get('Reload', 0.0)

        # Muzzle flash — weapon_anchor (= hand world frame, m 단위) 에 parent.
        # ybot 숨겨도 (Valorant 스타일) 영향 없이 그대로 보임. billboard + additive.
        if self.weapon is not None and self.right_hand_joint is not None:
            cm_mf = CardMaker('muzzle_flash')
            cm_mf.setFrame(-1, 1, -1, 1)
            self.muzzle_flash = self.weapon_anchor.attachNewNode(cm_mf.generate())
            # (8, 32, 8) cm hand-local 위치를 m 로 변환 → anchor local
            self.muzzle_flash.setPos(0.08, 0.32, 0.08)
            self.muzzle_flash_base_scale = 0.025  # ~5cm quad in world meters
            self.muzzle_flash.setScale(self.muzzle_flash_base_scale)
            self.muzzle_flash.setColor(1.0, 0.85, 0.35, 1.0)
            self.muzzle_flash.setBillboardPointEye()
            self.muzzle_flash.setLightOff()
            self.muzzle_flash.setTransparency(True)
            self.muzzle_flash.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd))
            self.muzzle_flash.setBin('fixed', 100)
            self.muzzle_flash.setDepthTest(False)
            self.muzzle_flash.setDepthWrite(False)
            self.muzzle_flash.hide()
        else:
            self.muzzle_flash = None
            self.muzzle_flash_base_scale = 0.0
        self.muzzle_flash_t = 0.0
        self.muzzle_flash_dur = 0.06

        # Tracer — 사격 시 muzzle 에서 forward 30m 짧은 얇은 선 (player_yaw 방향).
        # 매 사격마다 위치/방향 다시 잡고 50ms 표시 후 hide.
        ls_tr = LineSegs('tracer')
        ls_tr.setThickness(1)                  # 진짜 얇게
        ls_tr.setColor(1.0, 0.9, 0.55, 0.65)   # 따뜻한 노란빛, 살짝 투명
        ls_tr.moveTo(0, 0, 0)
        ls_tr.drawTo(0, 30, 0)                 # local +Y 로 30m
        self.tracer = self.render.attachNewNode(ls_tr.create())
        self.tracer.setTransparency(True)
        self.tracer.setLightOff()
        self.tracer.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd))
        self.tracer.setBin('fixed', 99)
        self.tracer.setDepthWrite(False)
        self.tracer.hide()
        self.tracer_t = 0.0
        self.tracer_dur = 0.05

        # 일시정지 메뉴 (ESC 토글)
        self.paused = False
        self._build_pause_menu()
        # 화면 중앙 십자 조준점
        self._build_crosshair()
        # 화면 하단 연속킬 콤보 게이지 (남은 시간 → 왼쪽으로 슬라이드 소진)
        self._build_combo_bar()
        # 발로란트 스타일 킬배너 (처치 시 하단 중앙에 '쾅' 등장)
        self._build_kill_banner()

        # Valorant 스타일 — 1인칭에서 자기 몸·다리 숨기고 팔·손은 그대로. ybot 메쉬가
        # Alpha_Surface (body 8.7K verts) + Alpha_Surface_Arms (arm 8.6K verts) 로 분리되어
        # 있음 (scripts/blender_split_arms.py 로 사전 처리). body 만 hide.
        # Alpha_Joints / Alpha_Joints_Arms 도 동일 split — joints 는 보통 invisible 이지만
        # 안전하게 body 쪽만 hide. arms 쪽은 그대로 visible.
        self._body_meshes = []
        for name in ('Alpha_Surface', 'Alpha_Joints'):
            np = self.ybot.find(f'**/{name}')
            if not np.isEmpty():
                self._body_meshes.append(np)
        self._set_body_visible(False)

        # 적 spawn + 방화벽/게이트 + damage popup 텍스트 풀
        self.zombies = []
        self.firewalls = []
        self.gates = []
        self._damage_numbers = []     # [{np, t, dur}, ...] — _update 가 animate
        self._spawn_zombies()
        # 온라인: 적/웨이브 완전 정지 — _spawn_points 만 비우면 _update 의 웨이브
        # 매니저('if self._spawn_points:')가 통째로 안 돌아 스폰/인터미션/WAVE
        # 메시지가 전부 멈춘다. (다른 데 if 흩뿌리지 않는다.) 적 목록도 비움.
        if self.online_mode or self.ai_mode or self.jump_mode or self.paint_mode:
            self._spawn_points = []
            self.zombies = []
        if self.online_mode:
            self._setup_online()      # 상대 아바타 생성 + 릴레이 접속(데몬 수신 스레드)
        elif self.ai_mode:
            self._setup_ai()          # AI 봇 생성(아레나·아바타·소총, 네트워크 없음)
        if self.soccer_mode:
            self._setup_soccer()      # 공 생성 + 골/점수 HUD
        if self.paint_mode:
            self._setup_paint()       # 색 배정 + 페인트 격자 참조
        if self.jump_mode:
            self._setup_jump()        # 스폰/발판/체크포인트/결승 세팅

        # 메인 루프
        self.taskMgr.add(self._update, 'game_update')

        # 진단: Idle 한 프레임 돌고 나서 본 이름/좌표 한 번 출력
        self.taskMgr.doMethodLater(0.3, self._dump_joints, 'dump_joints')

    def _tac_fonts(self):
        # 콘덴스드 폰트 1회 로드(캐시). 파일 없으면 Bahnschrift 로 폴백. 한글 글리프는
        # 없으므로 택티컬 UI 카피는 영어로 통일(디자인 명세대로). 한글 입력 필드는
        # 기본 폰트를 그대로 둔다.
        if getattr(self, '_tac_fonts_done', False):
            return
        self._tac_fonts_done = True       # 1회만 시도(실패해도 재시도 스팸 방지)

        def _load(primary):
            path = primary if primary.exists() else TAC_FONT_FALLBACK
            try:
                # loadFont 은 Panda VFS 경로 문자열을 받는다. Windows 'C:\...' 는
                # from_os_specific 로 Panda 식('/c/...')으로 변환해 넘겨야 찾는다.
                vfs = Filename.from_os_specific(str(path)).getFullpath()
                f = self.loader.loadFont(vfs)
                f.setPixelsPerUnit(120)
                return f
            except Exception as e:
                print('[tac-ui] 폰트 로드 실패:', path, e, flush=True)
                return None

        self._tac_hero_font = _load(TAC_FONT_HERO_PATH)
        self._tac_display_font = _load(TAC_FONT_DISPLAY_PATH)
        self._tac_label_font = _load(TAC_FONT_LABEL_PATH)

    def _tac_button(self, parent, text, pos, w, h, command,
                    text_scale=0.052, variant='base', arrow=False):
        # 디자인 .btn — 평평한 노치 서피스 + 1px 라인 + 좌측 텍스트(+우측 화살표).
        #   base   : 다크 서피스, 호버 시 윗단색 + 좌측 레드 슬래시 wipe
        #   accent : 레드 채움 + 어두운 텍스트(슬래시 없음), 호버 시 더 밝은 레드
        #   ghost  : 투명 + 라인만, 호버 시 윗단색 + 텍스트 점등 + 레드 슬래시
        self._tac_fonts()
        l, r, b, t = -w / 2.0, w / 2.0, -h / 2.0, h / 2.0
        nn = h * 0.34
        bright = _hexc('#F24D48')
        btn = DirectButton(
            parent=parent, pos=pos, relief=None, pressEffect=0,
            frameSize=(l, r, b, t), command=command, text='')
        if variant == 'accent':
            base_c, hover_c, line_c, txt_c = TAC_ACCENT, bright, TAC_ACCENT, TAC_BG_DEEP
        elif variant == 'ghost':
            base_c, hover_c, line_c, txt_c = TAC_BG_DEEP, TAC_SURF_TOP, TAC_LINE, TAC_TEXT_2
        else:
            base_c, hover_c, line_c, txt_c = TAC_BG_SURF, TAC_SURF_TOP, TAC_LINE, TAC_TEXT_1
        surf = _tac_fill(btn, l, r, b, t, base_c, notch=nn, corners=('tl', 'br'))
        if variant == 'ghost':
            surf.setColorScale(1, 1, 1, 0.0)        # 평소 투명
        _tac_outline(btn, l, r, b, t, line_c, notch=nn,
                     corners=('tl', 'br'), thickness=1.4)
        bar = None
        if variant != 'accent':                     # accent 는 슬래시 없음(HTML 동일)
            # 좌측 끝에 고정된 노드 + 폭 가진 지오메트리 → sX 0→1 로 좌→우 자람.
            # 윗부분을 버튼 좌상단 노치에 맞춰 비스듬히 잘라(conform) 버튼 밖으로
            # 삐져나오지 않게 한다.
            bw = 0.016
            bar = btn.attachNewNode('slash')
            bar.setPos(l + 0.004, 0, 0)
            _tac_fill(bar, 0.0, bw, b + 0.012, t - nn + bw, TAC_ACCENT,
                      notch=bw, corners=('tl',))
            bar.setSx(0.001)
            bar.setTransparency(1)
        lbl = OnscreenText(
            parent=btn, text=text, pos=(l + 0.05, -text_scale * 0.34),
            scale=text_scale, fg=txt_c, align=TextNode.ALeft,
            font=self._tac_label_font, mayChange=True)
        arrow_np = None
        if arrow:
            acol = TAC_BG_DEEP if variant == 'accent' else TAC_TEXT_3
            arrow_np = _tac_tri_right(btn, r - 0.05, 0.0, text_scale * 0.34, acol)

        def _enter(_=None):
            if variant == 'ghost':
                surf.setColorScale(1, 1, 1, 1.0)
                lbl.setFg(TAC_TEXT_1)
            surf.setColor(*hover_c)
            if bar is not None:                      # 레드 슬래시 좌→우 wipe
                bar.setSx(0.001)
                LerpScaleInterval(bar, 0.13, Vec3(1, 1, 1), Vec3(0.001, 1, 1),
                                  blendType='easeOut').start()
            if arrow_np is not None:                 # 화살표 우측으로 살짝 + 액센트
                LerpPosInterval(arrow_np, 0.12, (0.006, 0, 0), (0, 0, 0),
                                blendType='easeOut').start()
                if variant != 'accent':
                    arrow_np.setColor(*TAC_ACCENT)

        def _exit(_=None):
            surf.setColor(*base_c)
            if variant == 'ghost':
                surf.setColorScale(1, 1, 1, 0.0)
                lbl.setFg(TAC_TEXT_2)
            if bar is not None:                      # 우→좌 되감김
                LerpScaleInterval(bar, 0.10, Vec3(0.001, 1, 1), Vec3(1, 1, 1),
                                  blendType='easeOut').start()
            if arrow_np is not None:
                LerpPosInterval(arrow_np, 0.10, (0, 0, 0), (0.006, 0, 0),
                                blendType='easeOut').start()
                if variant != 'accent':
                    arrow_np.setColor(*TAC_TEXT_3)

        btn.bind(DGG.WITHIN, _enter)
        btn.bind(DGG.WITHOUT, _exit)
        # 누름 시 1px 시프트 (HTML .btn:active translate(1px,1px))
        op = pos
        btn.bind(DGG.B1PRESS,
                 lambda _=None: btn.setPos(op[0] + 0.003, op[1], op[2] - 0.003))
        btn.bind(DGG.B1RELEASE,
                 lambda _=None: btn.setPos(op[0], op[1], op[2]))
        return btn

    def _build_start_menu(self):
        # 디자인(screens.jsx TitleScreen) 그대로: 캡션(레드 틱 + CONTAINMENT PROTOCOL)
        # + 두 줄 초대형 타이틀(PROJECT 흰 / NULL 레드, Anton) + 태그라인 + 번호 리스트
        # 메뉴(01 SOLO PLAY … 구분선·레드 슬래시 호버·우측 힌트) + 푸터. 좌측 9vw 정렬.
        self._tac_fonts()
        ar = self.getAspectRatio()
        lx = -ar * 0.82                 # 좌측 패딩 ≈ 9vw
        root = DirectFrame(
            frameColor=TAC_BG_DEEP, frameSize=(-2.0, 2.0, -1.0, 1.0),
            pos=(0, 0, 0), parent=self.aspect2d,
        )
        self._menu_root = root

        # ── 상단 우측 태그 칩: BUILD 2693044 / ● ONLINE ───────────────────────
        rx_tag = ar * 0.82
        OnscreenText(text='BUILD 2693044', pos=(rx_tag - 0.18, 0.86), scale=0.026,
                     fg=TAC_TEXT_2, align=TextNode.ARight, mayChange=False,
                     parent=root, font=self._tac_label_font)
        _tac_fill(root, rx_tag - 0.155, rx_tag - 0.14, 0.852, 0.872, TAC_ACCENT)
        OnscreenText(text='ONLINE', pos=(rx_tag, 0.86), scale=0.026,
                     fg=TAC_ACCENT, align=TextNode.ARight, mayChange=False,
                     parent=root, font=self._tac_label_font)

        # ── 캡션: 레드 틱 + CONTAINMENT PROTOCOL ──────────────────────────────
        _tac_fill(root, lx, lx + 0.10, 0.516, 0.524, TAC_ACCENT)
        OnscreenText(text='CONTAINMENT  PROTOCOL', pos=(lx + 0.135, 0.508),
                     scale=0.030, fg=TAC_TEXT_2, align=TextNode.ALeft,
                     mayChange=False, parent=root, font=self._tac_label_font)

        # ── 두 줄 초대형 타이틀 (Anton) — PROJECT(흰) / NULL(레드) ────────────
        OnscreenText(text='PROJECT', pos=(lx - 0.012, 0.30), scale=0.235,
                     fg=TAC_TEXT_1, align=TextNode.ALeft, mayChange=False,
                     parent=root, font=self._tac_hero_font)
        OnscreenText(text='NULL', pos=(lx - 0.012, 0.07), scale=0.235,
                     fg=TAC_ACCENT, align=TextNode.ALeft, mayChange=False,
                     parent=root, font=self._tac_hero_font)
        OnscreenText(
            text='ISOLATE THE BREACH  ·  PURIFY THE FACILITY  ·  TRUST NO SIGNAL',
            pos=(lx, -0.04), scale=0.028, fg=TAC_TEXT_2, align=TextNode.ALeft,
            mayChange=False, parent=root, font=self._tac_label_font)

        # ── 번호 리스트 메뉴 (상·하·행간 구분선 + 레드 슬래시 호버) ──────────
        items = [('SOLO PLAY',   'SINGLE — AI / MODES',   self._prompt_solo_mode),
                 ('MULTIPLAYER', '2 PLAYERS — RELAY',     self._prompt_multi_mode),
                 ('SETTINGS',    'CONFIG',                self._prompt_settings),
                 ('QUIT',        'EXIT',                  self.userExit)]
        mrx = lx + 1.34                 # 메뉴 폭 ≈ 540px
        rowh = 0.118
        top = -0.16                     # nav 상단 구분선 z
        _tac_fill(root, lx, mrx, top - 0.0016, top + 0.0016, TAC_LINE)
        self._menu_btns = []
        self._menu_row_btns = []        # 행 버튼(오버레이 중 비활성화 대상)
        for i, (name, hint, cmd) in enumerate(items):
            zc = top - rowh * (i + 0.5)
            row = self._tac_menu_row(root, i + 1, name, hint, zc, lx, mrx, cmd)
            self._menu_btns.append(row)
            # 행 하단 구분선
            _tac_fill(root, lx, mrx, zc - rowh / 2 - 0.0016,
                      zc - rowh / 2 + 0.0016, TAC_LINE)
            # 스태거 클립인
            Sequence(Wait(0.05 * i),
                     LerpPosInterval(row, 0.18, (0, 0, 0),
                                     (-0.04, 0, 0), blendType='easeOut')).start()

        # ── 푸터: © SECTOR-7 … + 우측 틱 ──────────────────────────────────────
        OnscreenText(text='© SECTOR-7 SIMULATION DIVISION', pos=(lx, -0.92),
                     scale=0.025, fg=TAC_TEXT_3, align=TextNode.ALeft,
                     mayChange=False, parent=root, font=self._tac_label_font)
        ticks = LineSegs('foot_ticks')
        ticks.setThickness(1.4)
        for k in range(13):
            tx = rx_tag - 0.012 * (12 - k)
            hh = 0.018 if k % 3 == 0 else 0.011
            col = TAC_STEEL if k % 3 == 0 else TAC_LINE
            ticks.setColor(*col)
            ticks.moveTo(tx, 0, -0.928)
            ticks.drawTo(tx, 0, -0.928 + hh)
        tnp = root.attachNewNode(ticks.create())
        tnp.setTransparency(True)
        tnp.setLightOff()

    def _tac_menu_row(self, parent, idx, name, hint, zc, lx, rx, command):
        # 번호 리스트 메뉴 행 — 평소: 번호(흐림)+이름(2차색). 호버: 서피스 윗단색 +
        # 좌측 레드 슬래시 + 이름 1차색 + 살짝 우측 패딩 + 우측 힌트 노출.
        self._tac_fonts()
        h = 0.118
        b, t = zc - h / 2, zc + h / 2
        row = parent.attachNewNode(f'menu_row_{idx}')
        btn = DirectButton(
            parent=row, pos=(0, 0, 0), relief=None, pressEffect=0,
            frameSize=(lx, rx, b, t), command=command, text='')
        hover = _tac_fill(btn, lx, rx, b, t, TAC_SURF_TOP)
        hover.setTransparency(1)
        hover.setColorScale(1, 1, 1, 0.0)     # 평소 투명 — 호버 시 페이드인/아웃
        # 좌측 레드 슬래시 — 좌측 고정 노드 + sX 0→1 로 좌→우 자람.
        slash = btn.attachNewNode('rowslash')
        slash.setPos(lx, 0, 0)
        _tac_fill(slash, 0.0, 0.008, b + 0.014, t - 0.014, TAC_ACCENT)
        slash.setSx(0.001)
        slash.setTransparency(1)
        OnscreenText(parent=btn, text=f'0{idx}', pos=(lx + 0.05, zc - 0.016),
                     scale=0.034, fg=TAC_TEXT_3, align=TextNode.ALeft,
                     font=self._tac_display_font, mayChange=False)
        nm = OnscreenText(parent=btn, text=name.upper(),
                          pos=(lx + 0.135, zc - 0.026), scale=0.062,
                          fg=TAC_TEXT_2, align=TextNode.ALeft,
                          font=self._tac_display_font, mayChange=True)
        ht = OnscreenText(parent=btn, text=hint, pos=(rx - 0.03, zc - 0.011),
                          scale=0.024, fg=TAC_TEXT_3, align=TextNode.ARight,
                          font=self._tac_label_font, mayChange=False)
        ht.setTransparency(1)
        ht.setColorScale(1, 1, 1, 0.0)        # 평소 투명, 호버 시 페이드인
        nz = zc - 0.026                        # 이름 baseline z

        def _en(_=None):
            LerpColorScaleInterval(hover, 0.10, (1, 1, 1, 1), (1, 1, 1, 0),
                                   blendType='easeOut').start()   # 회색 베이스 페이드인
            slash.setSx(0.001)
            LerpScaleInterval(slash, 0.13, Vec3(1, 1, 1), Vec3(0.001, 1, 1),
                              blendType='easeOut').start()
            nm.setFg(TAC_TEXT_1)
            nm.setX(lx + 0.16)        # 살짝 우측 패딩(즉시 — OnscreenText LerpPos 부작용 회피)
            LerpColorScaleInterval(ht, 0.12, (1, 1, 1, 1), (1, 1, 1, 0)).start()

        def _ex(_=None):
            LerpColorScaleInterval(hover, 0.20, (1, 1, 1, 0), (1, 1, 1, 1),
                                   blendType='easeOut').start()   # 회색 베이스 페이드아웃
            LerpScaleInterval(slash, 0.10, Vec3(0.001, 1, 1), Vec3(1, 1, 1),
                              blendType='easeOut').start()
            nm.setFg(TAC_TEXT_2)
            nm.setX(lx + 0.135)
            LerpColorScaleInterval(ht, 0.10, (1, 1, 1, 0), (1, 1, 1, 1)).start()

        btn.bind(DGG.WITHIN, _en)
        btn.bind(DGG.WITHOUT, _ex)
        self._menu_row_btns.append(btn)   # 오버레이 열릴 때 일괄 비활성화용
        return row

    def _set_menu_clickable(self, on):
        # 풀스크린 오버레이(설정/로비)가 열린 동안 타이틀 메뉴 행 클릭을 막아
        # 뒤로 클릭이 통과해 옛 패널이 뜨는 것을 방지. on=False → DISABLED.
        for b in getattr(self, '_menu_row_btns', []):
            try:
                b['state'] = DGG.NORMAL if on else DGG.DISABLED
            except Exception:
                pass

    def _close_menu_overlay(self, scr):
        scr.destroy()
        self._set_menu_clickable(True)
        # 메인 메뉴로 복귀 — 타이틀 메뉴도 좌→우 슬라이드+페이드로 다시 등장.
        if getattr(self, '_menu_root', None) is not None:
            self._overlay_reveal(self._menu_root)

    def _overlay_reveal(self, scr):
        # 화면 전환 — 왼쪽에서 슬라이드 + 페이드로 '촤라락' 등장. 배경 프레임이 화면보다
        # 큼(-2~2)이라 슬라이드해도 가장자리 빈틈이 없다.
        scr.setTransparency(1)
        scr.setColorScale(1, 1, 1, 0)
        scr.setX(-0.13)
        Parallel(
            LerpPosInterval(scr, 0.30, (0, 0, 0), (-0.13, 0, 0),
                            blendType='easeOut'),
            LerpColorScaleInterval(scr, 0.22, (1, 1, 1, 1), (1, 1, 1, 0),
                                   blendType='easeOut'),
        ).start()

    def _prompt_settings(self):
        # 메인 메뉴 SETTINGS — 디자인 SettingsScreen 그대로(전체화면 2열):
        # 좌측 INPUT/AUDIO(+ENEMY OUTLINE) 슬라이더, 우측 CONTROLS 표, 우하단 DONE.
        if self._menu_root is None or self._game_started:
            return
        self._tac_fonts()
        ar = self.getAspectRatio()
        lx, rx = -ar * 0.85, ar * 0.85
        scr = DirectFrame(frameColor=TAC_BG_DEEP, frameSize=(-2.0, 2.0, -1.0, 1.0),
                          pos=(0, 0, 0), parent=self._menu_root)
        self._set_menu_clickable(False)   # 뒤 타이틀 메뉴 클릭 통과 차단
        self._overlay_reveal(scr)         # 등장 페이드인
        # 헤더 (kicker + title + sub)
        _tac_fill(scr, lx, lx + 0.06, 0.622, 0.632, TAC_ACCENT)
        OnscreenText(text='CONFIGURATION', pos=(lx + 0.09, 0.614), scale=0.026,
                     fg=TAC_TEXT_2, align=TextNode.ALeft, mayChange=False,
                     parent=scr, font=self._tac_label_font)
        OnscreenText(text='SETTINGS', pos=(lx, 0.50), scale=0.105,
                     fg=TAC_TEXT_1, align=TextNode.ALeft, mayChange=False,
                     parent=scr, font=self._tac_display_font)
        OnscreenText(text='INPUT · AUDIO · CONTROLS', pos=(lx + 0.62, 0.515),
                     scale=0.024, fg=TAC_TEXT_3, align=TextNode.ALeft,
                     mayChange=False, parent=scr, font=self._tac_label_font)
        midL, colR = -0.08, 0.10
        # ── 좌측: INPUT / AUDIO / TARGETING ──
        self._tac_panel_head(scr, 'INPUT', lx, midL, 0.36)
        self._build_setting_slider(scr, 'sens', 'MOUSE SENSITIVITY',
                                   'SLOW — FAST', 0.27, lx, midL)
        self._tac_panel_head(scr, 'AUDIO', lx, midL, 0.13)
        self._build_setting_slider(scr, 'master', 'MASTER', '0 — 100', 0.04, lx, midL)
        self._build_setting_slider(scr, 'sfx', 'EFFECTS', '0 — 100', -0.08, lx, midL)
        self._tac_panel_head(scr, 'TARGETING', lx, midL, -0.24)
        OnscreenText(text='ENEMY OUTLINE', pos=(lx, -0.32), scale=0.026,
                     fg=TAC_TEXT_2, align=TextNode.ALeft, mayChange=False,
                     parent=scr, font=self._tac_label_font)
        self._build_outline_swatches(scr, -0.42, sw=0.115, cx=lx + 0.05, left=True)
        # ── 우측: CONTROLS 표 ──
        self._tac_panel_head(scr, 'CONTROLS', colR, rx, 0.36)
        controls = [('W / S', 'MOVE'), ('A / D', 'STRAFE'), ('SPACE', 'JUMP'),
                    ('CTRL', 'CROUCH'), ('LMB', 'FIRE'), ('R', 'RELOAD'),
                    ('F', 'INTERACT'), ('ESC', 'PAUSE')]
        rowh, top = 0.078, 0.28
        _tac_outline(scr, colR, rx, top - rowh * len(controls), top, TAC_LINE,
                     thickness=1.2)
        for i, (k, v) in enumerate(controls):
            zc = top - rowh * (i + 0.5)
            if i % 2 == 0:
                _tac_fill(scr, colR, rx, zc - rowh / 2, zc + rowh / 2, TAC_BG_SURF)
            if i < len(controls) - 1:
                _tac_fill(scr, colR, rx, zc - rowh / 2 - 0.0007,
                          zc - rowh / 2 + 0.0007, TAC_LINE)
            OnscreenText(text=k, pos=(colR + 0.03, zc - 0.014), scale=0.034,
                         fg=TAC_TEXT_1, align=TextNode.ALeft, mayChange=False,
                         parent=scr, font=self._tac_display_font)
            OnscreenText(text=v, pos=(rx - 0.03, zc - 0.011), scale=0.024,
                         fg=TAC_TEXT_2, align=TextNode.ARight, mayChange=False,
                         parent=scr, font=self._tac_label_font)
        self._tac_button(scr, 'DONE', (rx - 0.22, 0, -0.44), 0.4, 0.10,
                         lambda: self._close_menu_overlay(scr),
                         variant='accent', arrow=True)

    def _menu_btn_kw(self, parent, fs=(-4.6, 4.6, -0.7, 1.1), text_scale=0.85):
        # 서브패널 버튼 공통 스타일 — 발로란트 다크 팔레트(평면 + 호버 시 윗단 색).
        return dict(
            scale=0.075, parent=parent,
            frameColor=(TAC_BG_SURF, TAC_SURF_TOP, TAC_SURF_TOP, TAC_BG_SURF),
            text_fg=TAC_TEXT_1, relief=DGG.FLAT, frameSize=fs,
            text_scale=text_scale)

    def _prompt_multi_mode(self):
        # 멀티플레이 로비 — 디자인 LobbyScreen 그대로(전체화면 2열): 좌측 RELAY
        # ENDPOINT(서버주소/콜사인/HOST·JOIN/모드/배너), 우측 OPERATORS(슬롯 2 +
        # READY + BACK/START). 정확히 2인 1방.
        if self._menu_root is None or self._game_started:
            return
        self._tac_fonts()
        self._lobby_ready = False
        self._lobby_mode = 'pvp'
        ar = self.getAspectRatio()
        lx, rx = -ar * 0.85, ar * 0.85
        scr = DirectFrame(frameColor=TAC_BG_DEEP, frameSize=(-2.0, 2.0, -1.0, 1.0),
                          pos=(0, 0, 0), parent=self._menu_root)
        self._lobby_scr = scr
        self._set_menu_clickable(False)   # 뒤 타이틀 메뉴 클릭 통과 차단
        self._overlay_reveal(scr)         # 등장 페이드인
        # 헤더
        _tac_fill(scr, lx, lx + 0.06, 0.622, 0.632, TAC_ACCENT)
        OnscreenText(text='MULTIPLAYER', pos=(lx + 0.09, 0.614), scale=0.026,
                     fg=TAC_TEXT_2, align=TextNode.ALeft, mayChange=False,
                     parent=scr, font=self._tac_label_font)
        OnscreenText(text='ESTABLISH LINK', pos=(lx, 0.50), scale=0.105,
                     fg=TAC_TEXT_1, align=TextNode.ALeft, mayChange=False,
                     parent=scr, font=self._tac_display_font)
        OnscreenText(text='TCP RELAY · 1 ROOM · 2 SLOTS', pos=(lx + 1.02, 0.515),
                     scale=0.024, fg=TAC_TEXT_3, align=TextNode.ALeft,
                     mayChange=False, parent=scr, font=self._tac_label_font)
        midL, colR = -0.06, 0.12
        # ── 좌측: RELAY ENDPOINT ──
        self._tac_panel_head(scr, 'RELAY ENDPOINT', lx, midL, 0.36)
        # 서버 주소 — 고정 릴레이라 읽기전용으로 표시만(편집 불가).
        OnscreenText(text='SERVER ADDRESS', pos=(lx, 0.295), scale=0.024,
                     fg=TAC_TEXT_2, align=TextNode.ALeft, mayChange=False,
                     parent=scr, font=self._tac_label_font)
        _tac_fill(scr, lx, midL, 0.17, 0.27, TAC_BG_DEEP, notch=0.02,
                  corners=('tl',))
        _tac_outline(scr, lx, midL, 0.17, 0.27, TAC_LINE, notch=0.02,
                     corners=('tl',), thickness=1.2)
        OnscreenText(text=f'{RELAY_HOST}:{RELAY_PORT}', pos=(lx + 0.03, 0.205),
                     scale=0.038, fg=TAC_TEXT_3, align=TextNode.ALeft,
                     mayChange=False, parent=scr, font=self._tac_display_font)
        OnscreenText(text='FIXED', pos=(midL - 0.03, 0.212), scale=0.020,
                     fg=TAC_TEXT_3, align=TextNode.ARight, mayChange=False,
                     parent=scr, font=self._tac_label_font)
        # 콜사인 — 편집 가능(이름)
        self._lobby_name_entry = self._tac_field(
            scr, 'CALLSIGN', lx, midL, 0.04, self.player_name)
        OnscreenText(text='MODE', pos=(lx, -0.10), scale=0.024, fg=TAC_TEXT_2,
                     align=TextNode.ALeft, mayChange=False, parent=scr,
                     font=self._tac_label_font)
        self._lobby_modes_node = scr.attachNewNode('lobby_modes')
        self._rebuild_lobby_modes()
        self._tac_banner(scr, lx, -0.32, 'STANDBY · RELAY READY',
                         w=midL - lx, state='idle')
        # ── 우측: OPERATORS ──
        self._tac_panel_head(scr, 'OPERATORS', colR, rx, 0.36,
                             right='2 / 2 REQUIRED')
        mid = colR + (rx - colR) / 2.0
        self._tac_player_slot(scr, colR, mid - 0.02, 0.04, 0.30, True, 'P1',
                              (self.player_name or 'YOU').upper(), 'CONNECTED')
        self._tac_player_slot(scr, mid + 0.02, rx, 0.04, 0.30, False, 'P2',
                              'OPEN SLOT', 'AWAITING…')
        self._lobby_ready_node = scr.attachNewNode('lobby_ready')
        self._rebuild_lobby_ready()
        self._tac_button(scr, 'BACK', (colR + 0.19, 0, -0.44), 0.36, 0.09,
                         lambda: self._close_menu_overlay(scr), variant='ghost')
        self._tac_button(scr, 'START', (rx - 0.22, 0, -0.44), 0.4, 0.09,
                         self._lobby_start, variant='accent', arrow=True)

    def _tac_mode_chip(self, parent, x0, x1, z, label, on, command):
        # 모드 선택 칩 — 선택: 레드 테두리/글자/하단 언더라인. 호버: 서피스 윗단색 +
        # 하단 레드 언더라인이 좌→우로 자람(다른 버튼과 같은 모션 문법).
        self._tac_fonts()
        zt, zb = z + 0.032, z - 0.032
        btn = DirectButton(parent=parent, pos=(0, 0, 0), relief=None,
                           pressEffect=0, frameSize=(x0, x1, zb, zt), text='',
                           command=command)
        surf = _tac_fill(btn, x0, x1, zb, zt,
                         TAC_SURF_TOP if on else TAC_BG_SURF, notch=0.02,
                         corners=('tl',))
        _tac_outline(btn, x0, x1, zb, zt, TAC_ACCENT if on else TAC_LINE,
                     notch=0.02, corners=('tl',), thickness=1.2)
        under = btn.attachNewNode('chip_under')          # 하단 레드 언더라인
        under.setPos(x0 + 0.006, 0, 0)
        _tac_fill(under, 0.0, (x1 - x0) - 0.012, zb + 0.002, zb + 0.006, TAC_ACCENT)
        under.setSx(1.0 if on else 0.001)
        under.setTransparency(1)
        if not on:
            under.hide()                  # 미선택 시 완전 숨김(sX 잔여 점 방지)
        lbl = OnscreenText(parent=btn, text=label, pos=((x0 + x1) / 2, z - 0.011),
                           scale=0.024, fg=(TAC_ACCENT if on else TAC_TEXT_2),
                           align=TextNode.ACenter, font=self._tac_label_font,
                           mayChange=True)

        def _en(_=None):
            if on:
                return
            surf.setColor(*TAC_SURF_TOP)
            lbl.setFg(TAC_TEXT_1)
            under.setSx(0.001)
            under.show()
            LerpScaleInterval(under, 0.12, Vec3(1, 1, 1), Vec3(0.001, 1, 1),
                              blendType='easeOut').start()

        def _ex(_=None):
            if on:
                return
            surf.setColor(*TAC_BG_SURF)
            lbl.setFg(TAC_TEXT_2)
            # 좌로 줄어든 뒤 완전히 숨겨 잔여 점이 안 남게.
            Sequence(LerpScaleInterval(under, 0.10, Vec3(0.001, 1, 1),
                                       Vec3(1, 1, 1), blendType='easeOut'),
                     Func(under.hide)).start()

        btn.bind(DGG.WITHIN, _en)
        btn.bind(DGG.WITHOUT, _ex)
        return btn

    def _rebuild_lobby_modes(self):
        # 모드 칩(PVP/SOCCER/PAINT/JUMP) — 선택/호버 애니메이션은 _tac_mode_chip.
        node = self._lobby_modes_node
        for c in list(node.getChildren()):
            c.removeNode()
        ar = self.getAspectRatio()
        lx = -ar * 0.85
        modes = [('pvp', 'PVP'), ('soccer', 'SOCCER'),
                 ('paint', 'PAINT'), ('jump', 'JUMP')]
        w, gap, z = 0.235, 0.022, -0.165
        for i, (key, lbl) in enumerate(modes):
            x0 = lx + i * (w + gap)
            x1 = x0 + w
            self._tac_mode_chip(node, x0, x1, z, lbl, self._lobby_mode == key,
                                (lambda k=key: self._lobby_set_mode(k)))

    def _rebuild_lobby_ready(self):
        node = self._lobby_ready_node
        for c in list(node.getChildren()):
            c.removeNode()
        colR = 0.12
        self._tac_toggle(node, colR, -0.07, self._lobby_ready, 'READY',
                         self._on_lobby_ready)
        self._lobby_ready_status = OnscreenText(
            parent=node, text=('ALL OPERATORS READY' if self._lobby_ready
                               else 'AWAITING READY'),
            pos=(colR + 0.36, -0.081), scale=0.022, fg=TAC_TEXT_3,
            align=TextNode.ALeft, font=self._tac_label_font, mayChange=True)

    def _prompt_multi_name(self, soccer=False, paint=False, jump=False):
        # 멀티 입장 전 — 이름 입력 패널을 메뉴 위에 띄운다. 입장/엔터 → _confirm_multi_name.
        if self._menu_root is None or self._game_started:
            return
        self._name_soccer = soccer    # 입장 시 이 모드로 시작
        self._name_paint = paint
        self._name_jump = jump
        panel = DirectFrame(
            frameColor=(0.055, 0.059, 0.071, 0.98),
            frameSize=(-0.75, 0.75, -0.36, 0.36),
            pos=(0, 0, 0.0), parent=self._menu_root)
        _tac_fill(panel, -0.75, 0.75, 0.335, 0.36, TAC_ACCENT)   # 상단 레드 액센트
        title = ('축구 — 이름을 입력하세요' if soccer else
                 '땅따먹기 — 이름을 입력하세요' if paint else
                 '점프맵 — 이름을 입력하세요' if jump else '이름을 입력하세요')
        OnscreenText(text=title, pos=(0, 0.23), scale=0.055,
                     fg=TAC_TEXT_1, align=TextNode.ACenter, mayChange=False, parent=panel)
        self._name_entry = DirectEntry(
            parent=panel, scale=0.08, pos=(-0.46, 0, 0.04), width=12, numLines=1,
            focus=1, initialText=self.player_name, overflow=1,
            frameColor=TAC_BG_SURF, text_fg=TAC_TEXT_1,
            command=lambda *_a: self._confirm_multi_name())
        DirectButton(
            text='입장', pos=(-0.22, 0, -0.20), scale=0.075, parent=panel,
            frameColor=(TAC_ACCENT, TAC_ACCENT, _hexc('#F2615C'), TAC_ACCENT_DIM),
            text_fg=TAC_TEXT_1, relief=DGG.FLAT, frameSize=(-2.6, 2.6, -0.7, 1.1),
            text_scale=0.9, command=self._confirm_multi_name)
        DirectButton(
            text='뒤로', pos=(0.22, 0, -0.20), command=lambda: (
                panel.destroy(), self._prompt_multi_mode()),
            **self._menu_btn_kw(panel, fs=(-2.6, 2.6, -0.7, 1.1), text_scale=0.9))

    def _confirm_multi_name(self):
        # 입력한 이름을 확정(빈칸이면 PLAYER) 후 멀티(online=True) 시작. 축구면 soccer=True.
        name = (self._name_entry.get() or '').strip() or 'PLAYER'
        self.player_name = name[:8]   # 표시·전송 길이 제한(대략 한글 8/영문 8)
        self._start_game(True, soccer=getattr(self, '_name_soccer', False),
                         paint=getattr(self, '_name_paint', False),
                         jump=getattr(self, '_name_jump', False))

    def _prompt_solo_mode(self):
        # 솔로 — 멀티 로비와 같은 택티컬 UI. 단 상대(P2) 슬롯 없이 내 슬롯을 가로로 길게.
        # 모드 칩 + 콜사인 + START(바로 시작) / BACK.
        if self._menu_root is None or self._game_started:
            return
        self._tac_fonts()
        self._solo_mode = 'ai'
        ar = self.getAspectRatio()
        lx, rx = -ar * 0.85, ar * 0.85
        scr = DirectFrame(frameColor=TAC_BG_DEEP, frameSize=(-2.0, 2.0, -1.0, 1.0),
                          pos=(0, 0, 0), parent=self._menu_root)
        self._set_menu_clickable(False)
        self._overlay_reveal(scr)         # 등장 페이드인
        # 헤더
        _tac_fill(scr, lx, lx + 0.06, 0.622, 0.632, TAC_ACCENT)
        OnscreenText(text='SOLO', pos=(lx + 0.09, 0.614), scale=0.026,
                     fg=TAC_TEXT_2, align=TextNode.ALeft, mayChange=False,
                     parent=scr, font=self._tac_label_font)
        OnscreenText(text='DEPLOY', pos=(lx, 0.50), scale=0.105, fg=TAC_TEXT_1,
                     align=TextNode.ALeft, mayChange=False, parent=scr,
                     font=self._tac_display_font)
        OnscreenText(text='AI OPPONENT · OFFLINE', pos=(lx + 0.52, 0.515),
                     scale=0.024, fg=TAC_TEXT_3, align=TextNode.ALeft,
                     mayChange=False, parent=scr, font=self._tac_label_font)
        # 모드 칩
        self._tac_panel_head(scr, 'MODE', lx, rx, 0.36)
        self._solo_modes_node = scr.attachNewNode('solo_modes')
        self._rebuild_solo_modes()
        # 콜사인
        self._solo_name_entry = self._tac_field(
            scr, 'CALLSIGN', lx, lx + 0.7, 0.11, self.player_name)
        # ── 내 슬롯(가로로 길게, 상대 슬롯 없음) ──
        self._tac_panel_head(scr, 'OPERATOR', lx, rx, -0.02)
        sb, st = -0.30, -0.10
        _tac_fill(scr, lx, rx, sb, st, TAC_BG_SURF, notch=0.04, corners=('tl',))
        _tac_outline(scr, lx, rx, sb, st, TAC_ACCENT_DIM, notch=0.04,
                     corners=('tl',), thickness=1.4)
        OnscreenText(parent=scr, text='P1', pos=(rx - 0.03, st - 0.05),
                     scale=0.026, fg=TAC_TEXT_3, align=TextNode.ARight,
                     font=self._tac_display_font, mayChange=False)
        _tac_fill(scr, lx + 0.03, lx + 0.048, st - 0.058, st - 0.04, TAC_ACCENT)
        OnscreenText(parent=scr, text='YOU', pos=(lx + 0.066, st - 0.056),
                     scale=0.022, fg=TAC_ACCENT, align=TextNode.ALeft,
                     font=self._tac_label_font, mayChange=False)
        OnscreenText(parent=scr, text=(self.player_name or 'OPERATOR'),
                     pos=(lx + 0.03, (sb + st) / 2 - 0.02), scale=0.055,
                     fg=TAC_TEXT_1, align=TextNode.ALeft, mayChange=False)
        OnscreenText(parent=scr, text='READY TO DEPLOY', pos=(rx - 0.03, sb + 0.05),
                     scale=0.024, fg=TAC_TEXT_2, align=TextNode.ARight,
                     font=self._tac_label_font, mayChange=False)
        # BACK / START
        self._tac_button(scr, 'BACK', (lx + 0.19, 0, -0.46), 0.36, 0.10,
                         lambda: self._close_menu_overlay(scr), variant='ghost')
        self._tac_button(scr, 'START', (rx - 0.22, 0, -0.46), 0.4, 0.10,
                         self._solo_start, variant='accent', arrow=True)

    def _rebuild_solo_modes(self):
        node = self._solo_modes_node
        for c in list(node.getChildren()):
            c.removeNode()
        ar = self.getAspectRatio()
        lx = -ar * 0.85
        modes = [('ai', 'AI DUEL'), ('soccer', 'SOCCER'),
                 ('paint', 'PAINT'), ('jump', 'JUMP')]
        w, gap, z = 0.28, 0.022, 0.27
        for i, (key, lbl) in enumerate(modes):
            x0 = lx + i * (w + gap)
            x1 = x0 + w
            self._tac_mode_chip(node, x0, x1, z, lbl, self._solo_mode == key,
                                (lambda k=key: self._solo_set_mode(k)))

    def _solo_set_mode(self, mode):
        self._solo_mode = mode
        self._rebuild_solo_modes()

    def _solo_start(self):
        # 솔로 즉시 시작 — AI 봇 상대(online=False, ai=True). 모드 칩으로 분기.
        if self._menu_root is None or self._game_started:
            return
        name = (self._solo_name_entry.get() or '').strip() or 'PLAYER'
        self.player_name = name[:8]
        m = getattr(self, '_solo_mode', 'ai')
        self._start_game(False, True, soccer=(m == 'soccer'),
                         paint=(m == 'paint'), jump=(m == 'jump'))

    def _start_game(self, online, ai=False, soccer=False, paint=False,
                    jump=False):
        # 메뉴에서 모드 확정 → 메뉴 제거 후 실제 게임 월드 빌드(한 번만).
        if self._game_started:
            return
        self._game_started = True
        self.online_mode = online
        self.ai_mode = ai
        self.soccer_mode = soccer
        self.paint_mode = paint
        self.jump_mode = jump
        if self._menu_root is not None:
            self._menu_root.destroy()
            self._menu_root = None
        self._build_world()

    def _attach_outline(self, actor, color=None, grow=1.07):
        if color is None:
            color = self.outline_color
        """발로란트식 적 테두리 — 적이 눈에 잘 띄게. 액터의 Character(스킨드 모델)를
        한 번 더 instanceTo 해서 살짝 키우고 '앞면 컬' → 확대된 뒷면 헐만 남아 원본
        실루엣 둘레로 단색 테두리가 보인다(인버티드 헐). outline 은 actor 의 자식이라
        위치/회전/사망 페이드(colorScale 상속)를 자동으로 따라가고 actor 가 제거되면
        같이 정리된다. instanceTo 라 본 애니메이션을 공유 → 테두리도 같이 움직인다.
        auto-shader 는 끄지 않는다(끄면 HW 스키닝이 빠져 바인드 포즈로 굳음)."""
        char = actor.find('**/+Character')
        if char.isEmpty():
            return None
        # 모델 대략 중심(z≈1.0) 기준으로 확대 → 발 기준 확대보다 머리/발 어긋남이 적다.
        pivot = actor.attachNewNode('enemy_outline')
        pivot.setPos(0, 0, 1.0)
        inner = pivot.attachNewNode('enemy_outline_in')
        inner.setPos(0, 0, -1.0)
        char.instanceTo(inner)
        pivot.setScale(grow)
        pivot.setColor(color, 1)          # 강제 단색(테두리 색)
        pivot.setTextureOff(1)            # 텍스처 무시
        pivot.setLightOff(1)              # 조명 무시 → 평면 단색
        # 앞면 컬 → 확대된 뒷면 헐만 남는다. + 깊이 오프셋으로 원본보다 뒤로 밀어
        # 겹치는 중앙은 원본이 덮고, 실루엣 밖으로 삐져나온 둘레만 테두리로 보이게.
        pivot.setAttrib(CullFaceAttrib.make(CullFaceAttrib.MCullCounterClockwise))
        pivot.setDepthOffset(-3)
        return pivot

    def _set_outline_color(self, color):
        # 메뉴에서 적 테두리 색 변경 → settings.json 저장 + 이미 생성된 적들 즉시 갱신.
        self.outline_color = tuple(color)
        _save_outline_color(self.outline_color)
        for z in getattr(self, 'zombies', []):
            if getattr(z, 'outline', None) is not None:
                z.outline.setColor(self.outline_color, 1)
        if self._remote_outline is not None:
            self._remote_outline.setColor(self.outline_color, 1)
        self._refresh_outline_swatches()

    def _refresh_outline_swatches(self):
        # 현재 선택된 색 스와치 위로 흰 하이라이트 프레임 이동.
        if self._swatch_hl is None:
            return
        match_x = None
        for col, x in self._swatch_positions:
            if tuple(col) == tuple(self.outline_color):
                match_x = x
                break
        if match_x is None:
            self._swatch_hl.hide()
        else:
            self._swatch_hl.setX(match_x)
            self._swatch_hl.show()

    def _spawn_zombies(self):
        # 웨이브 모드 — 방화벽/게이트 진행 대신, 맵의 스폰 지점들에 매 웨이브
        # 적를 점점 더 많이 풀어놓는다. 다 처치하면 인터미션 후 다음 웨이브.
        pts = []
        for room in self.level_data['rooms']:
            pts.extend(room['spawns'])
        for g in self.level_data['gates']:
            if g.get('final_spawns'):
                pts.extend(g['final_spawns'])
        self._spawn_points = pts

        # 웨이브 상태
        self.wave = 0
        self.wave_active = False
        self.wave_base = 4              # 웨이브1 적 수
        self.wave_growth = 2            # 웨이브마다 +N
        self.intermission_dur = 4.0     # 웨이브 사이 대기(초)
        self._intermission_t = 3.0      # 첫 웨이브까지 대기

        if not ZOMBIE_BAM.exists():
            print(f'[zombie] BAM not found: {ZOMBIE_BAM}', flush=True)
            self._spawn_points = []
        print(f'[wave] {len(self._spawn_points)} 스폰 지점 준비', flush=True)

    def _spawn_wave(self, n):
        """웨이브 n 의 적를 스폰 지점에 분산 배치."""
        if not self._spawn_points:
            return
        self._clear_corpses()
        pts = list(self._spawn_points)
        random.shuffle(pts)
        count = self.wave_base + self.wave_growth * (n - 1)
        for i in range(count):
            x, y = pts[i % len(pts)]
            self.zombies.append(Zombie(self, Vec3(x, y, 0), 180))
        self.wave_active = True
        self._show_gate_msg(f'WAVE {n}', dur=2.0)
        print(f'[wave] {n}: 적 {count} 스폰', flush=True)

    def _clear_corpses(self):
        """완전히 죽은(DEAD) 적 노드를 정리해 누적 부하를 막는다.
        사망 연출/페이드 중인 적은 유지."""
        keep = []
        for z in self.zombies:
            if (z.state == Zombie.DEAD and not z.transformed
                    and z.transform_t <= 0):
                z.actor.removeNode()
                if z.ybot_replacement is not None:
                    z.ybot_replacement.removeNode()
            else:
                keep.append(z)
        self.zombies = keep

    def _show_gate_msg(self, text, dur=1.6, reveal=False):
        # 미니멀 HUD — 중앙 웨이브/게이트 메시지 제거 (표시 안 함).
        return
        # reveal=True → 강조 톤(빨강) + 짧은 글리치. 게이트 돌파 같은 순간에 쓴다.
        self.gate_msg.setText(text)
        self.gate_msg.setFg(HUD_RED if reveal else HUD_CYAN)
        self.gate_msg.show()
        if reveal:
            self._trigger_glitch(0.5)
        self._gate_msg_token += 1
        token = self._gate_msg_token

        def _hide(task, t=token):
            if t == self._gate_msg_token:
                self.gate_msg.hide()
            return Task.done

        self.taskMgr.doMethodLater(dur, _hide, 'gate_msg_hide')

    # --- world setup --------------------------------------------------------

    def _make_lights(self):
        # 4점 조명(키/필/림/앰비언트) + 키라이트 그림자. ambient 를 낮춰 음영을 살리고,
        # 웜 키 / 쿨 필 대비 + 쿨 림으로 어두운 배경에서 모델 윤곽을 또렷이 분리한다.
        # auto-shader(render.setShaderAuto) 위에서 setShadowCaster 만으로 그림자 생성.
        amb = AmbientLight('ambient')
        amb.setColor(Vec4(0.25, 0.27, 0.33, 1))      # 낮고 살짝 쿨 — 그림자 면 톤
        self.render.setLight(self.render.attachNewNode(amb))

        # 키 라이트 — 강하고 살짝 웜. 그림자 캐스터.
        dl = DirectionalLight('dir')
        dl.setColor(Vec4(1.00, 0.95, 0.86, 1))       # 웜 톤, 강하게
        # 그림자 — 넓은 맵(64×98)을 한 번에 덮으면 텍셀이 흩어져 흐릿해진다. 대신
        # 고해상도 + 좁은(타이트) 직교 프러스텀을 매 프레임 플레이어를 따라가게 해서
        # (_update_shadow_frustum) 항상 플레이어 주변에 텍셀을 몰아 어디서든 선명하게.
        SHADOW_RES = 4096                             # 2048 → 4096 (밀도 2배)
        dl.setShadowCaster(True, SHADOW_RES, SHADOW_RES)
        # 깊이맵 패스는 SHADOW_CASTER_MASK 비트 객체만 렌더 → 바닥·천장 카드 제외
        # (_make_ground 에서 hide). 천장이 맵 전체를 그림자로 가리는 사태 방지.
        dl.setCameraMask(SHADOW_CASTER_MASK)
        # 직교 프러스텀을 플레이어 주변 ~45 유닛에 타이트하게. 4096² / 45 ≈ 1cm/텍셀.
        lens = dl.getLens()
        lens.setFilmSize(45, 45)
        lens.setNearFar(2, 90)
        dlnp = self.render.attachNewNode(dl)
        dlnp.setHpr(45, -55, 0)                       # 방향 고정(웜 키) — 위치만 추적
        self.render.setLight(dlnp)
        # 플레이어 추적용 — 라이트 전방 벡터(고정) + 뒤로 물러나는 거리(backoff).
        self._shadow_light_np = dlnp
        self._shadow_fwd = dlnp.getQuat(self.render).getForward()
        self._shadow_backoff = 45.0

        # 필 라이트(반대쪽) — 차갑게, 약하게. 그림자 지는 면을 너무 어둡지 않게 채움.
        dl2 = DirectionalLight('dir2')
        dl2.setColor(Vec4(0.30, 0.34, 0.45, 1))      # 쿨 톤 대비 → 영화 같은 룩
        dl2np = self.render.attachNewNode(dl2)
        dl2np.setHpr(-130, -35, 0)
        self.render.setLight(dl2np)

        # 림(백) 라이트 — 위·뒤에서 차갑고 강하게 쏴 캐릭터/적의 윤곽 모서리만 밝게
        # 태운다(grazing). 어두운 배경에서 실루엣이 분리돼 모델이 또렷하게 '뜬다'.
        # 정면 면엔 거의 안 닿아 전체 노출은 안 올리는 게 핵심(엣지 분리 전용).
        rim = DirectionalLight('rim')
        rim.setColor(Vec4(0.55, 0.62, 0.78, 1))      # 쿨 림 — 살짝 푸른 하이라이트
        rimnp = self.render.attachNewNode(rim)
        rimnp.setHpr(200, -18, 0)                     # 높이 뒤쪽에서 낮은 각도로
        self.render.setLight(rimnp)

        # 플래시라이트 제거 — 밝은 맵이라 불필요. (참조 안전용 None)
        self.flashlight = None

    def _update_shadow_frustum(self):
        """키 라이트 그림자 프러스텀을 매 프레임 플레이어 중심으로 이동. 방향(HPR)은
        고정하고 위치만 라이트 전방 반대로 backoff 만큼 물러나게 둬, 좁은 고해상 그림자가
        항상 플레이어 주변을 따라오게 한다(넓은 맵 어디서나 선명)."""
        np_ = getattr(self, '_shadow_light_np', None)
        if np_ is None:
            return
        np_.setPos(self.player_pos - self._shadow_fwd * self._shadow_backoff)

    def _make_ground(self):
        # level.py 의 5방 라인업(y=-2~70) + 아레나(y=-18~18)를 모두 여유 있게 덮음.
        cm = CardMaker('ground')
        cm.setFrame(-32, 32, -22, 76)   # 축구 골 포켓(y≈±20.4)까지 덮음
        gnd = self.render.attachNewNode(cm.generate())
        gnd.setHpr(0, -90, 0)        # XY 평면으로 눕히기 — 법선 +Z 위
        gnd.setColor(0.55, 0.55, 0.58, 1)
        gnd.hide(SHADOW_CASTER_MASK)   # 평평한 바닥은 그림자 캐스팅 제외(받기는 함)

        # 천장 — 같은 XY 풋프린트 / z = WALL_HEIGHT 에 놓고 법선은 아래(-Z) 향함.
        # setHpr(0, 90, 0) 으로 P=+90 → 카드 법선이 -Z 로 뒤집힘 → 아래에서 비추는
        # 플래시 빛만 받음. 색은 바닥보다 어둡게 (실내 천장 톤).
        cm_c = CardMaker('ceiling')
        cm_c.setFrame(-32, 32, -22, 76)
        ceil = self.render.attachNewNode(cm_c.generate())
        ceil.setHpr(0, 90, 0)
        ceil.setZ(WALL_HEIGHT)
        ceil.setColor(0.30, 0.30, 0.34, 1)
        ceil.hide(SHADOW_CASTER_MASK)   # 천장이 맵 전체를 그림자로 덮는 사태 방지

    # --- input --------------------------------------------------------------

    def _bind_inputs(self):
        for k in ('w', 'a', 's', 'd', 'space'):
            self.accept(k, self._set_key, [k, True])
            self.accept(f'{k}-up', self._set_key, [k, False])
        self.accept('escape', self._toggle_pause)
        self.accept('mouse1', self._on_fire_down)
        self.accept('mouse1-up', self._on_fire_up)
        self.accept('mouse3', self._set_aim, [True])
        self.accept('mouse3-up', self._set_aim, [False])
        self.accept('r', self._play_reload_oneshot)
        self.accept('wheel_down', self._cycle_weapon, [1])   # 휠 다운 → 소총
        self.accept('wheel_up',   self._cycle_weapon, [-1])  # 휠 업 → 권총
        self.accept('f2', self._toggle_editor)
        self.accept('f3', self._toggle_debug)
        self.accept('f11', self._toggle_fullscreen)   # 진짜 전체화면 토글
        # Ctrl 토글 — Panda3D 에선 'control' 단독 이벤트가 안 들어오므로 lcontrol/
        # rcontrol 만 바인딩 (left/right 둘 다 잡힘)
        for k in ('lcontrol', 'rcontrol'):
            self.accept(k, self._toggle_kneel)

        # 무기 위치/회전 튜닝 하네스 — 장착 무기(self.weapon) local POS/HPR 조절.
        #   이동(POS):  ←/→ = X(좌/우),  ↑/↓ = Y(앞/뒤, 총신),  PageUp/Down = Z(위/아래)
        #   회전(HPR):  [ ] = H(좌우 yaw),  ; ' = P(상하 pitch),  , . = R(roll)
        #   P = 현재 값 PowerShell 출력 + 화면 표시
        # 멀티(online_mode)에선 실수로 총 위치가 틀어지지 않게 이 개발용 키들을
        # 아예 바인딩하지 않는다 (B/P/화살표/PgUp·Dn/[ ];'/, . 전부).
        if not self.online_mode:
            weapon_pos_binds = {
                'arrow_right': (0,  1), 'arrow_left': (0, -1),   # ±X
                'arrow_up':    (1,  1), 'arrow_down': (1, -1),   # ±Y (총신 전후)
                'page_up':     (2,  1), 'page_down':  (2, -1),   # ±Z
            }
            for key, args in weapon_pos_binds.items():
                self.accept(key, self._nudge_weapon_pos, list(args))
                self.accept(f'{key}-repeat', self._nudge_weapon_pos, list(args))
            # Panda3D 는 구두점 키를 'bracketleft' 같은 단어가 아니라 글자 그대로
            # ('[' / ']' / ';' / "'" / ',' / '.') 이벤트로 보낸다.
            weapon_hpr_binds = {
                ']': (0,  1), '[': (0, -1),   # ±H (yaw)
                "'": (1,  1), ';': (1, -1),   # ±P (pitch)
                '.': (2,  1), ',': (2, -1),   # ±R (roll)
            }
            for key, args in weapon_hpr_binds.items():
                self.accept(key, self._nudge_weapon_hpr, list(args))
                self.accept(f'{key}-repeat', self._nudge_weapon_hpr, list(args))

            self.accept('b', self._toggle_tune_mode)  # B → 모드 순환(weapon→body→both)
            self.accept('p', self._dump_weapon)   # P → 무기 위치/회전 콘솔 출력

    def _set_key(self, k, v):
        self.keys[k] = v

    def _set_aim(self, on):
        # 우클릭 hold — ADS on/off. 재장전 transition 중에도 그대로 받음
        # (사용자가 R + 우클릭 동시 누르는 흔치 않은 케이스 그냥 허용).
        self.aiming = on

    def _register_weapon(self, name, path, scale, pos, hpr, muzzle, prerot=(0, 0, 0)):
        """무기 .bam/.glb 로드 → weapon_anchor 에 붙이고 숨겨둠. 성공 시 등록.
        prerot: 모델 native 방향 보정(모델 자기 frame 기준 회전). 배치 hpr 과 분리하려고
        wrapper node 를 끼우고 모델에 prerot, wrapper 에 scale/pos/hpr 를 건다."""
        if not path.exists():
            print(f'[weapon] {name} file missing: {path}', flush=True)
            return
        try:
            model = self.loader.loadModel(path)
        except Exception as e:
            print(f'[weapon] {name} load failed: {e}', flush=True)
            return
        # AR-10 GLB 에 소품으로 딸려오는, 공중에 뜬 예비 탄창(총알 든 풀 탄창)과
        # 낱알 총알을 제거. 총에 꽂힌 탄창(magempty.001)은 유지. 권총 등 해당
        # 노드가 없는 모델에선 매칭 0개라 무해. (flatten 전에 원본 이름으로 매칭.)
        for _prop in ('7.62x51 mag.001', '76251'):
            for _np in model.findAllMatches(f'**/*{_prop}*'):
                _np.removeNode()
        model.flattenLight()                # glTF RootNode self-transform 우회 (named node 보존)
        node = self.weapon_anchor.attachNewNode(f'{name}_weapon')
        model.reparentTo(node)
        model.setHpr(*prerot)               # 모델 native 방향 보정 (소총 앞뒤 뒤집힘 등)
        node.setScale(scale)
        node.setPos(*pos)
        node.setHpr(*hpr)
        node.setTwoSided(True)
        node.hide()
        slide = node.find('**/Slide')       # 총신 축 X → -X 후퇴. 없으면 None.
        if slide.isEmpty():
            slide_node, slide_rest_x = None, 0.0
        else:
            slide_node, slide_rest_x = slide, slide.getX()
        # 무기별 탄약을 개별 보관 — 교체해도 각 총의 남은 탄약이 유지된다(풀충전 X).
        _amax = WEAPON_STATS.get(name, {}).get('ammo_max', 8)
        self._weapons[name] = {
            'node': node, 'slide_node': slide_node,
            'slide_rest_x': slide_rest_x, 'muzzle': muzzle,
            'ammo': _amax, 'ammo_max': _amax,
        }
        self._weapon_order.append(name)
        print(f'[weapon] {name} registered (slide={"Y" if slide_node else "N"})',
              flush=True)

    def _equip_weapon(self, name):
        """활성 무기 교체 — show/hide + slide_node + muzzle flash 위치 갱신."""
        if name not in self._weapons:
            return
        # 진행 중 재장전이 있으면 확실히 취소(직접 교체 경로 안전망). 끊긴 무기는 충전 안 됨.
        self._cancel_reload()
        # 교체 전, 들고 있던 무기의 현재 탄약을 저장 → 다시 들 때 그대로 복원(풀충전 방지).
        prev = self.weapon_name
        if prev is not None and prev in self._weapons:
            self._weapons[prev]['ammo'] = self.ammo
        for w in self._weapons.values():
            w['node'].hide()
        d = self._weapons[name]
        d['node'].show()
        self.weapon = d['node']
        self.weapon_name = name        # 현재 무기 — 로코모션 anim 세트 선택에 사용
        self.weapon_body_offset = Vec3(*WEAPON_BODY_OFFSET.get(name, (0, 0, 0)))
        self.weapon_body_hpr = Vec3(*WEAPON_BODY_HPR.get(name, (0, 0, 0)))
        # ADS(줌) 시 몸 이동 오프셋 — 무기별로 줌 시 총이 중앙에 오게.
        self.ads_body_offset = Vec3(*WEAPON_ADS_OFFSET.get(name, (-0.13, 0.05, -0.02)))
        self.slide_node = d['slide_node']
        self.slide_rest_x = d['slide_rest_x']
        self.slide_recoil = 0.0
        mf = getattr(self, 'muzzle_flash', None)   # muzzle flash 는 나중에 생성됨
        if mf is not None:
            mf.setPos(*d['muzzle'])
        # 무기별 스탯 적용 — 발사간격 + 연발/헤드원킬 플래그. 탄약은 풀충전이 아니라
        # 해당 무기에 저장돼 있던 남은 탄약을 복원한다.
        st = WEAPON_STATS.get(name, {})
        self.ammo_max = st.get('ammo_max', 8)
        self.ammo = d.get('ammo', self.ammo_max)
        self.shoot_cooldown_dur = st.get('cooldown', 0.18)
        self.shoot_cooldown_t = 0.0
        self._auto_fire = st.get('auto', False)
        self._head_onekill = st.get('head_onekill', False)
        # 권총은 소총보다 빠르게(1.3배) — 가벼운 무기일수록 기동력.
        self._weapon_speed_mult = 1.3 if name == 'pistol' else 1.0
        print(f'[weapon] equipped {name} '
              f'(ammo={self.ammo}/{self.ammo_max}, auto={self._auto_fire}, '
              f'head1k={self._head_onekill}, spd={self._weapon_speed_mult})', flush=True)

    def _cancel_reload(self):
        """진행 중이던 재장전을 즉시 중단 — 무기 교체로 끊겼을 때. 예약된 _back(탄약
        충전)/슬라이드킥 콜백을 토큰 증가로 무효화하고 단발 모션 상태를 해제한다.
        → 바꾼 무기에서 재장전 모션이 이어 보이지 않고, 끊긴 무기는 탄약이 차지 않는다
        (재장전 미완료)."""
        if not self._reload_oneshot:
            return
        self._reload_token += 1            # 예약된 _back/_slide_kick 콜백 무효화(탄약 충전 X)
        self._reload_oneshot = False
        self.current_anim = '__reload_done__'   # 다음 프레임 upper/hands 를 loco 로 재평가

    def _cycle_weapon(self, delta):
        """마우스 휠 무기 순환 — 즉시 교체하지 않고 스왑 모션 시작.
        delta +1=다음(휠 다운), -1=이전(휠 업). 모션 중엔 입력 무시."""
        if self.paused or len(self._weapon_order) < 2:
            return
        if self._swap_state != 'idle':
            return  # 스왑 모션 진행 중 — 무시
        target = (self._weapon_idx + delta) % len(self._weapon_order)
        if target == self._weapon_idx:
            return
        # 재장전 중 교체 시작 — 재장전을 곧장 취소(스왑 모션 도중 _back 이 먼저 발동해
        # 탄약이 차거나, 바꾼 무기에서 재장전 모션이 이어지는 것을 방지).
        self._cancel_reload()
        self._swap_pending_idx = target
        self._swap_state = 'down'      # 팔 내리기 시작 → 바닥에서 교체 → 올리기
        self._swap_t = 0.0

    def _update_weapon_swap(self, dt):
        """스왑 모션 진행 — down(팔 내림) 끝에서 무기 교체 후 up(팔 올림).
        self._swap_z 를 ybot setPos 에 더해 팔/총을 시야 밖으로 내렸다 올린다."""
        if self._swap_state == 'idle':
            return
        self._swap_t += dt
        if self._swap_state == 'down':
            f = min(1.0, self._swap_t / WEAPON_SWAP_DOWN_DUR)
            self._swap_z = -WEAPON_SWAP_DROP * (f * f)          # easeIn → 빠르게 내림
            if f >= 1.0:
                # 시야 밖(바닥)에서 실제 무기 교체 → 스왑처럼 안 보이게.
                self._weapon_idx = self._swap_pending_idx
                self._equip_weapon(self._weapon_order[self._weapon_idx])
                self._swap_state = 'up'
                self._swap_t = 0.0
        else:  # 'up'
            f = min(1.0, self._swap_t / WEAPON_SWAP_UP_DUR)
            self._swap_z = -WEAPON_SWAP_DROP * (1.0 - f) ** 2   # easeOut → 올라와 안착
            if f >= 1.0:
                self._swap_z = 0.0
                self._swap_state = 'idle'

    def _on_interact(self):
        # F 키 — 가까이 있는 dead 적 가 있으면 Y Bot 으로 transform 시작.
        # F 상호작용 (현재 비활성 — 적은 죽으면 사라짐).
        if self.paused or self._interact_target is None:
            return
        self._interact_target.start_transform(self)
        self._interact_target = None
        self.interact_frame.hide()
        self.purified += 1          # 처치 카운터

    # --- weapon tuning harness (조정 끝나면 통째로 제거) -------------------
    # 현재 장착 무기(self.weapon 노드)의 local POS/HPR 을 실시간으로 미세조정.
    # 화살표/PageUp·Down = XYZ 이동, [ ] ; ' , . = 회전(H/P/R), P = 콘솔 dump.
    # 무기 node 의 pos/hpr 은 매 프레임 갱신 안 됨(register 때 1회) → 여기서 바꾼
    # 값이 그대로 유지됨. 반동(weapon_anchor)·슬라이드(slide_node)·스왑(ybot Z)
    # 은 별도 노드라 충돌 없음.
    WEAPON_TUNE_POS_STEP = 0.005   # m (5mm)
    WEAPON_TUNE_HPR_STEP = 1.0     # deg

    def _toggle_tune_mode(self):
        """B 키 — 튜닝 대상 순환: weapon → body → both → ads.
        weapon=총만, body=보이는 몸만(총은 화면 고정), both=소총+몸 함께,
        ads=줌(우클릭 hold) 시 몸 이동 오프셋(줌하면서 화살표로 조절)."""
        order = ('weapon', 'body', 'both', 'ads')
        self._tune_mode = order[(order.index(self._tune_mode) + 1) % len(order)]
        label = {'weapon': '총 위치/회전 (손 기준)',
                 'body':   '보이는 몸만 이동 (총 화면고정) / 회전(몸+총)',
                 'both':   '소총+몸 함께 이동/회전',
                 'ads':    '줌(ADS) 몸 오프셋 — 우클릭 hold 한 채 화살표/PgUp·Dn'}[
            self._tune_mode]
        print(f'[tune] 모드 = {self._tune_mode}  ({label})', flush=True)

    def _nudge_weapon_pos(self, idx, sign):
        """화살표/PgUp·Dn — 모드에 따라 총 위치(weapon) 또는 보이는 몸(body) 이동.
        idx 0=X(우/좌) 1=Y(앞/뒤) 2=Z(위/아래).

        body 모드: 보이는 몸을 player-frame 으로 이동시키되, 총은 손목에 고정돼
        같이 끌려가므로 그만큼 총 local 오프셋을 반대로 빼서 보정 → 총은 화면에서
        제자리, 손목(몸)만 총 쪽으로 이동. (보정량은 현재 손 회전 기준 정확히 상쇄)
        both 모드: body 와 같이 몸을 이동하되 보정 없음 → 소총이 몸을 따라가
        소총+몸이 함께 이동.
        ads 모드: 줌 시 몸 이동 오프셋(ads_body_offset) 조절. 우클릭 hold 로 줌한
        상태에서 화살표를 누르면 실시간으로 줌 자세가 움직임 (P 로 값 출력)."""
        step = sign * self.WEAPON_TUNE_POS_STEP
        if self._tune_mode == 'ads':
            v = self.ads_body_offset
            cur = [v.x, v.y, v.z]
            cur[idx] += step
            self.ads_body_offset = Vec3(*cur)
            return
        if self._tune_mode in ('body', 'both'):
            # player-frame 축 → world 벡터
            yr = radians(self.player_yaw)
            axis_w = (Vec3(cos(yr), sin(yr), 0),    # 0=우/좌
                      Vec3(-sin(yr), cos(yr), 0),   # 1=앞/뒤
                      Vec3(0, 0, 1))[idx]           # 2=위/아래
            delta_world = axis_w * step
            v = self.weapon_body_offset
            cur = [v.x, v.y, v.z]
            cur[idx] += step
            self.weapon_body_offset = Vec3(*cur)
            # body 만: 총 고정 보정(몸 이동량만큼 총 local 을 반대로 빼기).
            # both: 보정 생략 → 총이 손(몸)을 따라가 몸과 함께 이동.
            if self._tune_mode == 'body' and self.weapon is not None:
                d_local = self.weapon_anchor.getRelativeVector(
                    self.render, delta_world)
                p = self.weapon.getPos()
                self.weapon.setPos(p.x - d_local.x,
                                   p.y - d_local.y,
                                   p.z - d_local.z)
            return
        if self.weapon is None:
            return
        p = list(self.weapon.getPos())
        p[idx] += step
        self.weapon.setPos(*p)

    def _nudge_weapon_hpr(self, idx, sign):
        """[ ] ; ' , . — 회전. (B로 대상 토글)
        weapon 모드: 총 자체 회전(node local hpr = RIFLE_LOCAL_HPR).
        body/both 모드: 보이는 몸 회전(weapon_body_hpr) → 몸+총 함께 회전.
        ads 모드: 회전 없음(무시).
        idx 0=H,1=P,2=R."""
        if self._tune_mode == 'ads':
            return
        step = sign * self.WEAPON_TUNE_HPR_STEP
        if self._tune_mode == 'weapon':
            if self.weapon is None:
                return
            h = list(self.weapon.getHpr())
            h[idx] += step
            self.weapon.setHpr(*h)
            return
        v = self.weapon_body_hpr
        cur = [v.x, v.y, v.z]
        cur[idx] += step
        self.weapon_body_hpr = Vec3(*cur)

    def _dump_weapon(self):
        """장착 무기의 현재 POS/HPR 을 PowerShell(콘솔)에 출력 + 화면 3초 overlay.
        출력 형식은 zombie_game.py 상단 상수에 그대로 붙여넣을 수 있게 맞춤."""
        if self.weapon is None:
            print('[weapon-tune] no weapon equipped', flush=True)
            return
        name = self.weapon_name or '?'
        p = self.weapon.getPos()
        h = self.weapon.getHpr()
        b = self.weapon_body_offset
        bh = self.weapon_body_hpr
        a = self.ads_body_offset
        prefix = 'RIFLE' if name == 'rifle' else 'WEAPON'
        pos_line = (f'{prefix}_LOCAL_POS   = '
                    f'({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f})')
        hpr_line = (f'{prefix}_LOCAL_HPR   = '
                    f'({h[0]:.1f}, {h[1]:.1f}, {h[2]:.1f})')
        body_line = (f"WEAPON_BODY_OFFSET['{name}'] = "
                     f'({b.x:.3f}, {b.y:.3f}, {b.z:.3f})')
        body_hpr_line = (f"WEAPON_BODY_HPR['{name}'] = "
                         f'({bh.x:.1f}, {bh.y:.1f}, {bh.z:.1f})')
        ads_line = (f"WEAPON_ADS_OFFSET['{name}'] = "
                    f'({a.x:.3f}, {a.y:.3f}, {a.z:.3f})')
        print(f'[weapon-tune] {name}  (mode={self._tune_mode})', flush=True)
        print('  ' + pos_line, flush=True)
        print('  ' + hpr_line, flush=True)
        print('  ' + body_line, flush=True)
        print('  ' + body_hpr_line, flush=True)
        print('  ' + ads_line, flush=True)
        # ads 모드면 화면 오버레이도 ADS 값 위주로.
        txt = (f'{name.upper()} [{self._tune_mode}]\n' +
               (ads_line if self._tune_mode == 'ads'
                else f'{body_line}\n{body_hpr_line}'))
        if getattr(self, '_weapon_tune_text', None) is not None:
            self._weapon_tune_text.destroy()
        self._weapon_tune_text = OnscreenText(
            text=txt, pos=(0, 0.2), scale=0.06,
            fg=(0.4, 1, 0.4, 1), bg=(0, 0, 0, 0.85),
            align=TextNode.ACenter, mayChange=False,
            parent=self.aspect2d,
        )
        token = self._weapon_tune_text
        def _remove(task, t=token):
            if getattr(self, '_weapon_tune_text', None) is t:
                self._weapon_tune_text.destroy()
                self._weapon_tune_text = None
            return Task.done
        self.taskMgr.doMethodLater(3.0, _remove, 'weapon_tune_dump_remove')

    def _toggle_kneel(self):
        if self._reload_oneshot:
            return
        # transition 중에는 무시 (anim 끝까지 재생).
        if self.kneel_state in ('going_down', 'going_up'):
            return
        if self.kneel_state == 'stand':
            if 'StandToKneel' in self.anim_names:
                self._play_kneel_transition('StandToKneel', 'going_down', 'kneel')
            elif 'KneelIdle' in self.anim_names:
                self.kneel_state = 'kneel'  # transition anim 없으면 즉시 전환
        else:  # 'kneel'
            if 'KneelToStand' in self.anim_names:
                self._play_kneel_transition('KneelToStand', 'going_up', 'stand')
            else:
                self.kneel_state = 'stand'

    def _play_kneel_transition(self, anim_name, mid_state, end_state):
        """무릎꿇기/일어서기 transition 단발 — 모든 파트에 anim 적용."""
        self.kneel_state = mid_state
        self.current_anim = anim_name
        new_t = {a: (1.0 if a == anim_name else 0.0) for a in self.anim_names}
        self._target_w['lower'] = dict(new_t)
        self._target_w['upper'] = dict(new_t)
        if not self._hands_oneshot:
            self._target_w['hands'] = dict(new_t)
        for p in ('lower', 'upper'):
            self.ybot.play(anim_name, partName=p)
        if not self._hands_oneshot:
            self.ybot.play(anim_name, partName='hands')

        self._anim_token += 1
        token = self._anim_token
        dur = self.ybot.getDuration(anim_name)
        back_after = max(dur - 0.05, 0.05)

        def _back(task, t=token):
            if t != self._anim_token:
                return Task.done
            self.kneel_state = end_state
            # current_anim 이 transition anim 이름이라 _update_locomotion 의
            # `if target != self.current_anim` 분기에서 KneelIdle / Idle 로 자동 갱신.
            return Task.done

        self.taskMgr.doMethodLater(back_after, _back, 'kneel_transition_return')

    def _loco_anim(self, base):
        """소총 장착 시 base 로코모션 anim 을 Pro Rifle Pack 변형(Rifle*)으로 치환.
        해당 rifle 변형이 bam 에 없으면(예: 무릎 transition) base 그대로 폴백."""
        if self.weapon_name == 'rifle':
            rifle = 'Rifle' + base
            if rifle in self.anim_names:
                return rifle
        return base

    def _target_anim(self):
        """현재 상태(공중/무릎/이동방향)에 맞는 loop anim 이름.
        소총 장착 중이면 _loco_anim 이 Rifle* 변형으로 자동 치환."""
        if self.kneel_state == 'going_down' and 'StandToKneel' in self.anim_names:
            return self._loco_anim('StandToKneel')
        if self.kneel_state == 'going_up' and 'KneelToStand' in self.anim_names:
            return self._loco_anim('KneelToStand')
        if self.kneel_state == 'kneel' and 'KneelIdle' in self.anim_names:
            return self._loco_anim('KneelIdle')
        if not self.on_ground and 'Jump' in self.anim_names:
            return self._loco_anim('Jump')
        fwd = self.keys['w'] - self.keys['s']
        rgt = self.keys['d'] - self.keys['a']
        if fwd > 0 and 'RunForward' in self.anim_names:
            return self._loco_anim('RunForward')
        if fwd < 0 and 'RunBackward' in self.anim_names:
            return self._loco_anim('RunBackward')
        if rgt > 0 and 'StrafeR' in self.anim_names:
            return self._loco_anim('StrafeR')
        if rgt < 0 and 'StrafeL' in self.anim_names:
            return self._loco_anim('StrafeL')
        return self._loco_anim('Idle')

    def _update_locomotion(self):
        # Kneel transition 중에는 _play_kneel_transition 이 target_w 를 잡고 있음.
        # 모든 파트가 transition anim 으로 가야 하니 여기서 건드리지 않음.
        if self.kneel_state in ('going_down', 'going_up'):
            return
        target = self._target_anim()
        # Reload 중 W/S = RunForward/RunBackward 는 Mixamo anim 의 Hips pitch
        # (앞으로 숙임) 가 살아있어서 Spine→Arm→Hand 로 전파 → 권총·팔이 화면
        # 아래로 빠짐. A/D 의 StrafeL/R 은 Hips pitch 가 없어 reload 가 정상으로
        # 보이는 거. 같은 효과를 W/S 에도 주려고 lower 를 Idle 로 대체 — 다리는
        # 멈추지만 player_pos 는 그대로 전진/후진. 1인칭이라 다리는 거의 안 보임.
        if self._reload_oneshot and target in ('RunForward', 'RunBackward',
                                               'RifleRunForward', 'RifleRunBackward'):
            target = self._loco_anim('Idle')
        # ADS + 이동 시 lower 까지 Idle 강제 → Hips rotation 사라져서 상체로 전파 안 됨
        # → 팔 완전 정지. (다리는 어차피 hidden, body slide 만 발생)
        if self.aim_t > 0.5 and target in ('RunForward', 'RunBackward',
                                            'StrafeL', 'StrafeR',
                                            'RifleRunForward', 'RifleRunBackward',
                                            'RifleStrafeL', 'RifleStrafeR'):
            target = self._loco_anim('Idle')
        loco_w = {a: (1.0 if a == target else 0.0) for a in self.anim_names}
        # lower: 항상 locomotion. Shoot 단발 중에도 다리는 안 멈춤.
        self._target_w['lower'] = dict(loco_w)
        # upper: locomotion (단, reload 중에는 reload 가 잡고 있음).
        if not self._reload_oneshot and target != self.current_anim:
            self.current_anim = target
            self._target_w['upper'] = dict(loco_w)
        # hands: Shoot/Reload 단발 중 아니면 upper 와 동일.
        if not self._hands_oneshot and not self._reload_oneshot:
            self._target_w['hands'] = dict(self._target_w['upper'])

    def _compute_spray(self, name):
        """발로란트식 탄 퍼짐 각도(deg) → (yaw_off, pitch_off). _spray_shots 기반.
        첫발(n=0)은 편차 0(정확). pattern=소총 climb+sway, scatter=권총 랜덤 콘.
        이동(WASD) 중이면 'move' 반경만큼 랜덤 콘을 추가로 더해 더 크게 퍼짐."""
        cfg = WEAPON_SPRAY.get(name)
        if not cfg:
            return 0.0, 0.0
        n = self._spray_shots   # 이번 버스트에서 이미 쏜 발수 (0=첫발)
        airborne = not self.on_ground   # 점프/낙하 중 — 첫발부터 크게 튐
        # 소총: 가만히 있을 때 첫 두 발(n<2)은 무조건 조준점 정중앙(편차 0).
        # 단 이동 중·공중에선 적용 안 함 — 첫발부터 퍼지는 게 맞음.
        # (연발 3발째부터 퍼짐. idle 시 _spray_shots 리셋돼 첫 두 발 정확 보장.)
        if cfg['mode'] == 'pattern' and n < 2 and not airborne \
                and not any(self.keys[k] for k in ('w', 'a', 's', 'd')):
            return 0.0, 0.0
        if cfg['mode'] == 'pattern':
            # 소총: 약한 상승 중심 둘레로 사방(0~360°) 랜덤 콘. 연사할수록 콘이 커져
            # 위·아래·좌·우 골고루 튐 (한 방향 쏠림 방지).
            pitch_center = min(n, cfg.get('v_max', 10)) * cfg.get('v_step', 0.55)
            t = min(1.0, n / max(1, cfg.get('cone_ramp', 8)))
            radius = (cfg.get('cone_min', 1.4)
                      + (cfg.get('cone_max', 5.0) - cfg.get('cone_min', 1.4)) * t)
            ang = random.uniform(0.0, 6.28318)
            r = radius * random.uniform(0.35, 1.0)
            yaw_off = r * cos(ang)
            pitch_off = pitch_center + r * sin(ang)
        else:
            # 권총(scatter): 빨리 연타할수록(n 클수록) 랜덤 콘 반경 증가. 첫발 정확.
            radius = min(n, cfg['max_shots']) * cfg['step']
            ang = random.uniform(0.0, 6.28318)
            r = radius * random.uniform(0.35, 1.0)
            yaw_off, pitch_off = r * cos(ang), r * sin(ang)
        # 이동 중이면 추가 랜덤 콘 — 가만히 있을 때보다 더 크게 퍼짐.
        moving = any(self.keys[k] for k in ('w', 'a', 's', 'd'))
        mv = cfg.get('move', 0.0)
        if moving and mv > 0.0:
            ang = random.uniform(0.0, 6.28318)
            r = mv * random.uniform(0.4, 1.0)
            yaw_off += r * cos(ang)
            pitch_off += r * sin(ang)
        # 공중(점프) 사격 — 첫발부터 '엄청 튀게' 큰 랜덤 콘 추가(무기/연사 무관).
        if airborne:
            ang = random.uniform(0.0, 6.28318)
            r = self.JUMP_SPREAD_DEG * random.uniform(0.6, 1.0)
            yaw_off += r * cos(ang)
            pitch_off += r * sin(ang)
        # 조준(ADS) 시 전체 퍼짐 축소 — aim_t(0=hip,1=줌)로 1.0 ↔ ads 보간.
        ads_mult = 1.0 + (cfg.get('ads', 1.0) - 1.0) * self.aim_t
        return yaw_off * ads_mult, pitch_off * ads_mult

    def _resolve_shot_hit(self):
        """카메라 ray vs 각 적의 본 기반 히트박스(머리 구 + 몸통/사지 캡슐).
        가장 가까운 hit 의 zone 으로 damage + damage number popup."""
        cam_pos = self.camera.getPos(self.render)
        # 탄 퍼짐 편차(deg)를 조준 방향에 더함 → 발로란트식 스프레이.
        yr = radians(self.player_yaw + self._shot_yaw_off)
        pp = radians(self.player_pitch + self._shot_pitch_off)
        ray_dir = Vec3(-sin(yr) * cos(pp), cos(yr) * cos(pp), sin(pp))
        ray_dir.normalize()

        best_t = float('inf')
        best_z = None
        best_zone = None
        best_hit_pos = None
        for z in self.zombies:
            if z.hp <= 0 or not z._lod_active:
                continue
            res = z.hit_test(self.render, cam_pos, ray_dir, best_t)
            if res is None:
                continue
            best_t, best_zone, best_hit_pos = res
            best_z = z

        # 방화벽 / 게이트 — 적보다 앞에 있으면 그걸 맞힘 (적 무효화).
        best_barrier = None
        for b in self.firewalls + self.gates:
            s = b.ray_distance(cam_pos, ray_dir)
            if s is None or s >= best_t:
                continue
            best_t = s
            best_barrier = b
            best_z = None

        # 상대 플레이어(온라인) — 적/방화벽과 같은 ray 로 히트박스 검사.
        # best_t 보다 더 가까우면 상대를 맞힌 것 → 적/방화벽 판정 무효.
        remote_hit_pos = None
        if self.online_mode or self.ai_mode:
            res = self._remote_hit_test(cam_pos, ray_dir, best_t)
            # 총알이 벽을 못 뚫게 — 나→상대 ray 가 벽/플랫폼(높이 인식)에 막히면 취소.
            if res is not None and not self._bullet_blocked(
                    cam_pos, ray_dir, res[0]):
                best_t, best_zone, remote_hit_pos = res
                best_z = None
                best_barrier = None

        # 트레이서 종점 — 카메라 ray 상의 실제 명중 지점(없으면 먼 거리). 머즐→이 점으로
        # 트레이서를 그어야 조준점(화면 중앙)에 수렴한다. 머즐에서 평행선만 그으면
        # 카메라와 머즐 오프셋만큼 조준점을 빗나가 '안 날아가고 끊긴' 것처럼 보였다.
        self._last_shot_end = cam_pos + ray_dir * (best_t if best_t < 1e8 else 120.0)

        # 축구 공 — 적/상대/벽보다 가까우면 공을 맞힌 것(차기). best_t 와 비교.
        if self.soccer_mode and self._ball is not None:
            res = self._ball.ray_hit(cam_pos, ray_dir)
            if res is not None and res[0] < best_t and not self._bullet_blocked(
                    cam_pos, ray_dir, res[0]):
                t_hit, hit_pt = res
                power = (self.SOCCER_KICK_RIFLE if self.weapon_name == 'rifle'
                         else self.SOCCER_KICK_PISTOL)
                self._soccer_kick_ball(hit_pt - self._ball.pos, ray_dir, power)
                self._spawn_hit_particle(hit_pt)
                self._play_pool(self.sfx_hit, '_hit_i')
                return            # 공을 맞히면 뒤 판정 무효(공이 막아줌)

        if remote_hit_pos is not None:
            self._on_remote_player_hit(best_zone, remote_hit_pos)
            return
        if best_barrier is not None:
            best_barrier.hit()
            return
        if best_z is None:
            return
        dmg = Zombie.DAMAGE[best_zone]
        # 소총 등 head_onekill 무기는 헤드샷 즉사 — hp_max 만큼 데미지.
        if best_zone == 'head' and getattr(self, '_head_onekill', False):
            dmg = max(dmg, best_z.hp_max)
        was_alive = best_z.hp > 0
        best_z.take_damage(dmg)
        # 피격 사운드 — 부위 상관없이 Voicy_Headshot 통일.
        self._play_pool(self.sfx_hit, '_hit_i')
        if was_alive and best_z.hp <= 0:
            self._on_zombie_killed(best_zone)
        self._spawn_hit_particle(best_hit_pos)
        self._spawn_damage_number(best_hit_pos, dmg)
        self._show_hitmarker(kill=(was_alive and best_z.hp <= 0))  # 명중=흰 X, 처치=레드
        print(f'[hit] {best_zone} dmg={dmg} → hp={best_z.hp}/{best_z.hp_max}',
              flush=True)

    def _spawn_damage_number(self, world_pos, dmg):
        """피격 위치 근처 (랜덤 offset) 에 3D billboard text 띄움. 위로 떠오르며 fade."""
        tn = TextNode('dmg')
        tn.setText(str(dmg))
        tn.setAlign(TextNode.ACenter)
        # 데미지 크기 따라 색
        if dmg >= 20:
            tn.setTextColor(1.0, 0.35, 0.20, 1)   # 진한 주황 — head
        elif dmg >= 10:
            tn.setTextColor(1.0, 0.85, 0.30, 1)   # 노랑 — body
        else:
            tn.setTextColor(0.95, 0.95, 0.95, 1)  # 흰색 — other
        tn.setShadow(0.05, 0.05)
        tn.setShadowColor(0, 0, 0, 1)
        np_text = self.render.attachNewNode(tn)
        np_text.setBillboardPointEye()
        np_text.setScale(0.30)
        np_text.setLightOff()
        np_text.setTransparency(True)
        np_text.setBin('fixed', 95)
        np_text.setDepthTest(False)
        np_text.setDepthWrite(False)
        off = Vec3(random.uniform(-0.20, 0.20),
                   random.uniform(-0.20, 0.20),
                   random.uniform(0.05, 0.20))
        np_text.setPos(world_pos + off)
        self._damage_numbers.append({'np': np_text, 't': 1.0, 'dur': 1.0})

    def _resolve_sfx(self, filename):
        """여러 후보 경로에서 효과음 파일 경로를 찾음. 없으면 None + 경고."""
        candidates = [
            SCRIPT_DIR / 'Sound' / filename,
            SCRIPT_DIR / 'assets' / 'sounds' / filename,
            SCRIPT_DIR / 'assets' / filename,
            SCRIPT_DIR / 'sounds' / filename,
            SCRIPT_DIR / filename,
        ]
        for c in candidates:
            if c.exists():
                return Filename.from_os_specific(str(c))
        print('[sfx] NOT FOUND: %s (예상 위치: %s)'
              % (filename, SCRIPT_DIR / 'assets' / 'sounds' / filename),
              flush=True)
        return None

    def _load_sfx(self, filename):
        """효과음 1개 로드 (동시 재생 1개). 없으면 None."""
        fn = self._resolve_sfx(filename)
        if fn is None:
            return None
        snd = self.loader.loadSfx(fn)
        if snd is not None:
            print('[sfx] loaded %s' % filename, flush=True)
        return snd

    def _load_sfx_pool(self, filename, n):
        """같은 효과음을 n개 로드해 동시 겹침 재생용 풀로 반환. 없으면 []."""
        fn = self._resolve_sfx(filename)
        if fn is None:
            return []
        pool = [self.loader.loadSfx(fn) for _ in range(n)]
        pool = [s for s in pool if s is not None]
        if pool:
            print('[sfx] loaded %s x%d (겹침 풀)' % (filename, len(pool)), flush=True)
        return pool

    def _play_pool(self, pool, idx_attr):
        """겹침 풀에서 다음 사운드를 라운드로빈으로 재생 (연사 시 끊김 방지)."""
        if self.paused or not pool:
            return
        i = getattr(self, idx_attr)
        pool[i].play()
        setattr(self, idx_attr, (i + 1) % len(pool))

    def _play_footstep(self):
        """발소리 한 발 — f1/f2/f3 중 직전과 다른 것을 랜덤으로 골라 재생."""
        if self.paused or not self.sfx_foot:
            return
        n = len(self.sfx_foot)
        if n == 1:
            i = 0
        else:
            i = random.randrange(n)
            while i == self._last_foot_i:   # 직전과 같으면 다시 뽑아 중복 방지
                i = random.randrange(n)
        self._last_foot_i = i
        self.sfx_foot[i].play()

    def _on_zombie_killed(self, zone):
        """적 처치 시 호출 — 킬 카운트 + 콤보 단계 갱신 + 킬 사운드.
        zone: 마지막에 맞혀 죽인 부위('head'/'body'/'other'). 콤보 판정에 사용."""
        headshot = (zone == 'head')
        self.kills += 1
        # 직전 킬 5초 이내 + 이번이 헤드샷이면 단계 상승(최대 5), 아니면 1로 리셋.
        if headshot and self._combo_window > 0.0:
            self._kill_tier = min(self._kill_tier + 1, 5)
        else:
            self._kill_tier = 1
        self._combo_window = self.kill_combo_dur
        self._play_kill_sound(self._kill_tier)
        self._show_kill_banner()   # 발로란트 스타일 킬배너 (콤보 단계 반영)

    def _play_kill_sound(self, tier):
        """현재 콤보 단계의 킬 사운드 재생. 이전 킬 사운드는 멈춰 겹침 방지."""
        snd = self.sfx_kill.get(tier)
        if snd is None:
            return
        if self._last_kill_snd is not None:
            self._last_kill_snd.stop()
        snd.play()
        self._last_kill_snd = snd

    def _spawn_hit_particle(self, world_pos):
        """맞은 부위(world_pos)에 fire 스프라이트 1개(랜덤)를 잠깐 띄운다."""
        if not self._fire_tex or world_pos is None:
            return
        cm = CardMaker('hit_fire')
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        np = self.render.attachNewNode(cm.generate())
        np.setTexture(random.choice(self._fire_tex))
        np.setPos(world_pos)
        np.setBillboardPointEye()          # 항상 카메라 정면
        np.setLightOff()
        np.setTransparency(True)
        np.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd))  # additive 글로우
        np.setBin('fixed', 90)
        np.setDepthTest(True)
        np.setDepthWrite(False)
        base = 0.40                        # ~40cm
        np.setScale(base)
        # Kenney fire 텍스처는 흰 연기형 → 따뜻한 색으로 틴트해 불꽃처럼. 약간 랜덤.
        col = random.choice([(1.0, 0.50, 0.12), (1.0, 0.70, 0.20), (1.0, 0.36, 0.07)])
        np.setColorScale(col[0], col[1], col[2], 1)
        self._hit_particles.append({'np': np, 't': 0.28, 'dur': 0.28,
                                    'base': base, 'col': col})

    def _on_fire_down(self):
        # 좌클릭 누름 — 즉발 1발. 연발 무기는 _update 가 hold 동안 반복 발사.
        # 준비방 동안은 버튼 클릭이 발사로 새지 않게 무시.
        if self._in_lobby:
            return
        self._mouse1_down = True
        self._play_shoot_oneshot()

    def _on_fire_up(self):
        self._mouse1_down = False

    def _play_shoot_oneshot(self):
        if self.paused:
            return
        if self._dead or self._barriers_active:
            return  # 사망 중/라운드 카운트다운(가둠) 중엔 발사 안 함
        if self._swap_state != 'idle':
            return  # 무기 교체(스왑) 모션 중 — 발사 안 함
        if self.ammo <= 0:
            # 빈 탄창 — 발사 대신 빈총 클릭음 (권총·소총 공통). 연타/연사 방지 쿨다운.
            if self._reload_oneshot:
                return
            if self.sfx_empty is not None and self._empty_click_t <= 0:
                self.sfx_empty.play()
                self._empty_click_t = 0.35
            return  # R 로 재장전
        if self.shoot_cooldown_t > 0:
            return  # 발사 간격 쿨다운
        if 'Shoot' not in self.anim_names or self._reload_oneshot:
            return
        self.ammo -= 1
        self._net_shot_seq = (self._net_shot_seq + 1) & 0xFF  # 상대에 '새 발사' 알림
        self.shoot_cooldown_t = self.shoot_cooldown_dur
        # 발사음 — 활성 무기에 맞춰 선택. 소총=M16(겹침 풀), 그 외=기본 shot.
        name = (self._weapon_order[self._weapon_idx]
                if self._weapon_order else 'pistol')
        # 탄 퍼짐(발로란트식) — 이번 발 각도 편차 계산 후 연사 카운터 증가.
        # ray(_resolve_shot_hit)와 tracer 둘 다 이 편차를 적용해 일치시킴.
        self._shot_yaw_off, self._shot_pitch_off = self._compute_spray(name)
        self._spray_shots += 1
        self._spray_idle = 0.0
        if name == 'rifle' and self.sfx_m16_pool:
            self._play_pool(self.sfx_m16_pool, '_sfx_m16_i')
        else:
            self._play_pool(self.sfx_shot_pool, '_sfx_shot_i')
        # 히트 판정 — 카메라 위치에서 yaw+pitch 방향으로 ray, 각 적의 3 zone
        # (head/body/foot) sphere 와 교차 검사. 가장 가까운 zone 에 damage.
        self._resolve_shot_hit()
        # 권총 등은 hands 만 Shoot 단발 자세로. 소총은 그 포즈(권총 파지)가 어색해서
        # 생략 → 손은 소총 파지 자세 유지, 권총처럼 몸 반동(뒤로 밀림)만. (oneshot 도 스킵)
        is_rifle = (name == 'rifle')
        if not is_rifle:
            self.ybot.play('Shoot', partName='hands')
        self.recoil_back = self.recoil_shoot_back
        self.slide_recoil = self.slide_recoil_kick
        # Muzzle flash — anchor 에 parent 라 위치는 자동. show + timer 만.
        if self.muzzle_flash is not None:
            self.muzzle_flash_t = self.muzzle_flash_dur
            self.muzzle_flash.setScale(self.muzzle_flash_base_scale)
            self.muzzle_flash.show()
            # Tracer — 머즐에서 '실제 명중 지점'(_last_shot_end, 카메라 ray 상)으로 향하게
            # lookAt + 길이 스케일. 이러면 조준점에 수렴하고 끊겨 보이지 않는다.
            muzzle = self.muzzle_flash.getPos(self.render)
            end = getattr(self, '_last_shot_end', None)
            self.tracer.setPos(muzzle)
            if end is not None:
                self.tracer.lookAt(end)                  # 로컬 +Y 를 명중점으로
                dist = (end - muzzle).length()
                self.tracer.setSy(max(0.05, dist / 30.0))  # 30m 기준 라인을 실제 거리로
            else:
                self.tracer.setHpr(self.player_yaw + self._shot_yaw_off,
                                   self.player_pitch + self._shot_pitch_off, 0)
                self.tracer.setSy(1.0)
            self.tracer.show()
            self.tracer_t = self.tracer_dur
        if not is_rifle:
            self._hands_oneshot = True
            self._target_w['hands'] = {
                a: (1.0 if a == 'Shoot' else 0.0) for a in self.anim_names
            }
            self._hands_token += 1
            token = self._hands_token
            dur = self.ybot.getDuration('Shoot')
            back_after = max(dur - self.blend_out_time, 0.05)

            def _back(task, t=token):
                if t != self._hands_token:
                    return Task.done
                self._hands_oneshot = False
                # upper 의 현재 target 으로 hands 동기화.
                self._target_w['hands'] = dict(self._target_w['upper'])
                return Task.done

            self.taskMgr.doMethodLater(back_after, _back, 'hands_return')

    def _play_reload_oneshot(self):
        # 소총 장착 시 RifleReload, 그 외 Reload.
        anim = ('RifleReload' if (self.weapon_name == 'rifle'
                                  and 'RifleReload' in self.anim_names) else 'Reload')
        if (anim not in self.anim_names or self._reload_oneshot
                or self.kneel_state in ('going_down', 'going_up')):
            return
        # upper + hands 두 파트만 단발 (lower 는 locomotion 유지 → 달리며 재장전)
        self.ybot.play(anim, partName='upper')
        self.ybot.play(anim, partName='hands')
        self._reload_oneshot = True
        if self.sfx_reload is not None:
            self.sfx_reload.play()
        rl = {a: (1.0 if a == anim else 0.0) for a in self.anim_names}
        self._target_w['upper'] = dict(rl)
        self._target_w['hands'] = dict(rl)
        self._reload_token += 1
        token = self._reload_token
        dur = self._reload_dur.get(anim, self.ybot.getDuration(anim))  # 동기화된 재생 시간
        # HUD 재장전 진행 게이지용 — 시작 시각 + 총 길이 기록.
        self._reload_started = ClockObject.getGlobalClock().getFrameTime()
        self._reload_total = max(0.05, dur)

        # 슬라이드 래킹 — reload 후반에 기존 slide_recoil 재사용
        def _slide_kick(task, t=token):
            if t == self._reload_token and self.slide_node is not None:
                self.slide_recoil = self.slide_recoil_kick
            return Task.done

        self.taskMgr.doMethodLater(dur * 0.88, _slide_kick, 'reload_slide_kick')

        back_after = max(dur - self.blend_out_time, 0.05)

        def _back(task, t=token):
            if t != self._reload_token:
                return Task.done
            self._reload_oneshot = False
            # 재장전 자세 → 평상시 자세 복귀를 느린 블렌드로 부드럽게 (휙 튐 방지)
            self._slow_blend_t = self.reload_return_slow_dur
            self.ammo = self.ammo_max   # 탄창 충전
            # upper/hands 를 다음 프레임에 locomotion 으로 강제 재평가시키는 sentinel
            self.current_anim = '__reload_done__'
            return Task.done

        self.taskMgr.doMethodLater(back_after, _back, 'reload_return')

    def _update_blend(self, dt):
        # 지수 평활: 각 파트마다 current_w 를 target_w 쪽으로 비례 수렴.
        # 재장전 복귀 중에는 느린 블렌드(slow_blend_speed)로 부드럽게.
        if self._slow_blend_t > 0.0:
            self._slow_blend_t -= dt
            speed = self.slow_blend_speed
        else:
            speed = self.blend_speed
        alpha = min(1.0, dt * speed)
        for p in self._parts:
            cur_w = self._current_w[p]
            tgt_w = self._target_w[p]
            for a in self.anim_names:
                cur = cur_w[a]
                tgt = tgt_w[a]
                if cur == tgt:
                    continue
                new = cur + (tgt - cur) * alpha
                if abs(new - tgt) < 0.001:
                    new = tgt
                cur_w[a] = new
                self.ybot.setControlEffect(a, new, partName=p)

    def _set_body_visible(self, visible):
        """body / leg / spine 메쉬만 show/hide. 팔/손은 항상 그대로."""
        for np in self._body_meshes:
            if visible:
                np.show()
            else:
                np.hide()

    def _toggle_editor(self):
        self.editor_mode = not self.editor_mode
        # cursor 상태는 안 바꿈 (양쪽 다 confined+hidden = 무한 회전 가능).
        if self.editor_mode:
            self.editor_pos = Vec3(self.camera.getPos(self.render))
            self.editor_yaw = self.player_yaw
            self.editor_pitch = self.player_pitch
            self._set_body_visible(True)    # 3인칭으로 자기 몸 다시 봄
        else:
            self._set_body_visible(False)   # FPS — body 숨기고 팔만
        self.win.movePointer(0, self._win_cx, self._win_cy)
        self._first_frame = True

    # --- pause menu ---------------------------------------------------------

    def _build_pause_menu(self):
        # 디자인(screens.jsx PauseScreen) 그대로 — 풀스크린 어두운 오버레이 + 중앙
        # 컬럼: 캡션(양쪽 레드 틱 + SIMULATION HALTED) + PAUSED(Anton) + 노치 패널
        # (마우스 감도 슬라이더) + 적 테두리 패널 + RESUME(레드)/QUIT TO MENU(고스트).
        # 등장 시 각 그룹이 페이드+9px 슬라이드로 스태거 진입(_animate_pause_in).
        self._tac_fonts()
        # 풀스크린 컨테이너(투명) + 어두운 오버레이(페이드 대상)
        self.pause_frame = DirectFrame(
            frameColor=(0, 0, 0, 0), frameSize=(-2.0, 2.0, -1.0, 1.0),
            pos=(0, 0, 0), parent=self.aspect2d)
        self._pause_bg = DirectFrame(
            frameColor=(0.031, 0.035, 0.043, 0.78), frameSize=(-2.0, 2.0, -1.0, 1.0),
            parent=self.pause_frame)
        self._pause_bg.setTransparency(1)

        # 애니메이션 그룹 4개 (캡션+타이틀 / 감도 패널 / 테두리 패널 / 버튼)
        gT = self.pause_frame.attachNewNode('pz_title')
        gS = self.pause_frame.attachNewNode('pz_sens')
        gO = self.pause_frame.attachNewNode('pz_outline')
        gB = self.pause_frame.attachNewNode('pz_btns')
        for g in (gT, gS, gO, gB):
            g.setTransparency(1)
        self._pause_groups = [gT, gS, gO, gB]

        # ── 캡션: 레드 틱 + SIMULATION HALTED + 레드 틱, 그 아래 PAUSED ──────────
        _tac_fill(gT, -0.205, -0.145, 0.626, 0.634, TAC_ACCENT)
        _tac_fill(gT, 0.145, 0.205, 0.626, 0.634, TAC_ACCENT)
        OnscreenText(text='SIMULATION HALTED', pos=(0, 0.618), scale=0.026,
                     fg=TAC_TEXT_2, align=TextNode.ACenter, mayChange=False,
                     parent=gT, font=self._tac_label_font)
        OnscreenText(text='PAUSED', pos=(0, 0.475), scale=0.135,
                     fg=TAC_TEXT_1, align=TextNode.ACenter, mayChange=False,
                     parent=gT, font=self._tac_hero_font)

        # ── 입력 + 오디오 노치 패널 (감도 / 마스터 / 효과음 — 설정과 동일 항목) ──
        _tac_fill(gS, -0.46, 0.46, 0.06, 0.43, TAC_BG_SURF, notch=0.03,
                  corners=('tl', 'br'))
        _tac_outline(gS, -0.46, 0.46, 0.06, 0.43, TAC_LINE, notch=0.03,
                     corners=('tl', 'br'), thickness=1.4)
        self._build_setting_slider(gS, 'sens', 'MOUSE SENSITIVITY', 'SLOW — FAST',
                                   0.37, -0.42, 0.42)
        self._build_setting_slider(gS, 'master', 'MASTER VOLUME', None,
                                   0.25, -0.42, 0.42)
        self._build_setting_slider(gS, 'sfx', 'SFX VOLUME', None,
                                   0.13, -0.42, 0.42)

        # ── 적 테두리 색 노치 패널 (게임 고유 기능 — 같은 디자인 언어로) ────────
        _tac_fill(gO, -0.46, 0.46, -0.18, -0.02, TAC_BG_SURF, notch=0.03,
                  corners=('tl', 'br'))
        _tac_outline(gO, -0.46, 0.46, -0.18, -0.02, TAC_LINE, notch=0.03,
                     corners=('tl', 'br'), thickness=1.4)
        OnscreenText(text='ENEMY OUTLINE', pos=(-0.42, -0.065), scale=0.027,
                     fg=TAC_TEXT_2, align=TextNode.ALeft, mayChange=False,
                     parent=gO, font=self._tac_label_font)
        self._build_outline_swatches(gO, -0.13)

        # ── 버튼: RESUME(accent) / QUIT TO MENU(ghost → 메인 메뉴 복귀) ────────
        self._tac_button(gB, 'RESUME', (0, 0, -0.29), 0.92, 0.105,
                         self._toggle_pause, variant='accent', arrow=True)
        self._tac_button(gB, 'QUIT TO MENU', (0, 0, -0.415), 0.92, 0.105,
                         self._return_to_main_menu, variant='ghost')
        self.pause_frame.hide()

    def _animate_pause_in(self):
        # 디자인 Reveal — 각 그룹이 투명+9px 아래에서 페이드인+위로 슬라이드, 스태거.
        # 일시정지 중엔 글로벌 클럭이 MSlave 라 인터벌이 멈추므로, 실제 시계(time)로
        # 도는 태스크가 매 프레임 직접 진행시킨다.
        self.pause_frame.setColorScale(1, 1, 1, 1)
        self._pause_bg.setColorScale(1, 1, 1, 0)
        for g in getattr(self, '_pause_groups', []):
            g.setColorScale(1, 1, 1, 0)
            g.setPos(0, 0, -0.05)
        self._pause_anim_t0 = time.time()
        self.taskMgr.remove('pause_anim_in')
        self.taskMgr.add(self._pause_anim_task, 'pause_anim_in')

    def _pause_anim_task(self, task):
        if not self.paused:
            return Task.done
        el = time.time() - self._pause_anim_t0
        self._pause_bg.setColorScale(1, 1, 1, min(1.0, el / 0.16))
        done = el >= 0.16
        for i, g in enumerate(self._pause_groups):
            d = 0.03 + 0.06 * i
            p = max(0.0, min(1.0, (el - d) / 0.24))
            e = 1.0 - (1.0 - p) ** 3        # easeOutCubic
            g.setColorScale(1, 1, 1, e)
            g.setZ((e - 1.0) * 0.05)        # -0.05 → 0
            if p < 1.0:
                done = False
        return Task.done if done else Task.cont

    def _animate_pause_out(self):
        # 닫기 — 열기의 역재생(페이드아웃 + 아래로 슬라이드, 역스태거). 끝나면 hide.
        self._pause_out_t0 = time.time()
        self.taskMgr.remove('pause_anim_in')
        self.taskMgr.remove('pause_anim_out')
        self.taskMgr.add(self._pause_anim_out_task, 'pause_anim_out')

    def _pause_anim_out_task(self, task):
        if self.paused:                    # 닫는 중 다시 열림 → 열기 애니에 양보
            return Task.done
        el = time.time() - self._pause_out_t0
        n = len(self._pause_groups)
        done = True
        for i, g in enumerate(self._pause_groups):
            d = 0.03 + 0.055 * (n - 1 - i)  # 역스태거(아래 그룹부터 먼저 빠짐)
            p = max(0.0, min(1.0, (el - d) / 0.20))
            e = p ** 3                      # easeInCubic (역방향)
            g.setColorScale(1, 1, 1, 1.0 - e)
            g.setZ(-e * 0.05)               # 0 → -0.05
            if p < 1.0:
                done = False
        self._pause_bg.setColorScale(1, 1, 1, max(0.0, 1.0 - el / 0.22))
        if done:
            self.pause_frame.hide()
            return Task.done
        return Task.cont

    def _trigger_shake(self, mag=2.2, dur=0.28):
        """피격 화면 흔들림 1회. mag=진폭(deg), dur=지속(초). 더 센 흔들림이 들어오면
        진폭은 큰 값으로 갱신(겹쳐도 약해지지 않게)."""
        self._shake_mag = max(self._shake_mag, mag) if self._shake_t > 0 else mag
        self._shake_dur = dur
        self._shake_t = dur

    def take_core_damage(self, amount, source_pos=None):
        """적 공격 → 코어 무결성(체력) 깎기. 0 이 되면 게임오버 훅(현재 미구현).
        source_pos 주어지면 그 방향으로 피격 방향 아크 표시."""
        old_hp = self.core_integrity
        self.core_integrity = max(0, self.core_integrity - amount)
        self._show_dmg_flash(old_hp, self.core_integrity)   # 체력바 닳은 구간 플래시
        if self.core_integrity < old_hp:
            self._trigger_dmg_vignette()                    # 화면 가장자리 레드 플래시
            self._trigger_shake(2.2, 0.28)                  # 화면 흔들림
            self._slow_t = self.HIT_SLOW_DUR                # 피격 후 잠깐 감속
        if source_pos is not None:
            self._show_damage_dir(source_pos)

    def _show_damage_dir(self, source_pos):
        """피격 방향을 조준점 둘레의 빨간 아크로 표시. 시선(player_yaw) 기준 상대
        방위로 위치 — 앞=위, 뒤=아래, 좌/우. aspect2d 중심(조준점)에 그림."""
        yr = radians(self.player_yaw)
        fx, fy = -sin(yr), cos(yr)        # 시선 forward (XY)
        rx, ry = cos(yr), sin(yr)         # 시선 right (XY)
        dx = source_pos.x - self.player_pos.x
        dy = source_pos.y - self.player_pos.y
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return
        f_dot = dx * fx + dy * fy
        r_dot = dx * rx + dy * ry
        theta = atan2(r_dot, f_dot)       # 0=정면(위), +=우, ±π=뒤(아래)
        R = 0.22                          # 조준점에서 아크까지 반경 (aspect2d)
        half = radians(30.0)              # 아크 폭(±)
        seg = 16
        ls = LineSegs('dmg_arc')
        ls.setThickness(7.0)
        ls.setColor(1.0, 0.15, 0.12, 1.0)
        for k in range(seg + 1):
            phi = theta - half + (2.0 * half) * (k / seg)
            x, z = R * sin(phi), R * cos(phi)   # 정면(theta=0) → (0,R)=위
            if k == 0:
                ls.moveTo(x, 0, z)
            else:
                ls.drawTo(x, 0, z)
        if self._dmg_arc_geom is not None:
            self._dmg_arc_geom.removeNode()
        self._dmg_arc_geom = self.aspect2d.attachNewNode(ls.create())
        self._dmg_arc_geom.setTransparency(True)
        self._dmg_arc_geom.setLightOff()
        self._dmg_arc_geom.setBin('fixed', 101)
        self._dmg_arc_geom.setDepthTest(False)
        self._dmg_arc_geom.setDepthWrite(False)
        self._dmg_dir_t = self._dmg_dir_dur

    def _sens_from_norm(self, n):
        """슬라이더 정규화값(0~1) → 실제 마우스 감도. 지수 매핑이라 0.5=기하평균(=0.03,
        현재 기본)이고 양끝이 크게 벌어진다(0=느림, 1=빠름)."""
        n = max(0.0, min(1.0, n))
        return self.SENS_MIN * (self.SENS_MAX / self.SENS_MIN) ** n

    def _on_sens_change(self):
        # DirectSlider command — 매 변경마다 호출. 정규화값(0~1) 읽어 실제 감도로 변환.
        n = self.sens_slider['value']
        self._sens_norm = n
        self.mouse_sens = self._sens_from_norm(n)
        self.sens_value_text.setText(f'{n:.2f}')
        if getattr(self, 'sens_fill', None) is not None:
            self.sens_fill['frameSize'] = (-1.0, -1.0 + 2.0 * n, -0.16, 0.16)

    # ── 공통 설정 위젯 — 일시정지/설정이 동일한 항목·콜백을 공유(레이아웃만 다름) ──
    def _apply_volume(self):
        # 매니저 전역 볼륨에 master·sfx 반영(개별 사운드 거리감쇠 위에 곱해짐).
        v = max(0.0, min(1.0, self._vol_master)) * max(0.0, min(1.0, self._vol_sfx))
        try:
            for mgr in self.sfxManagerList:
                mgr.setVolume(v)
        except Exception:
            pass
        try:
            self.musicManager.setVolume(max(0.0, min(1.0, self._vol_master)))
        except Exception:
            pass

    def _fmt_setting(self, key, v):
        return f'{v:.2f}' if key == 'sens' else f'{int(round(v * 100))}'

    def _on_setting_change(self, key):
        # 공통 슬라이더 콜백. 생성 시 1회 조기 발화는 슬라이더 attr 미등록이라 무시됨.
        sl = getattr(self, f'_set_slider_{key}', None)
        if sl is None:
            return
        v = sl['value']
        if key == 'sens':
            self._sens_norm = v
            self.mouse_sens = self._sens_from_norm(v)
        elif key == 'master':
            self._vol_master = v
            self._apply_volume()
        elif key == 'sfx':
            self._vol_sfx = v
            self._apply_volume()
        vt = getattr(self, f'_set_text_{key}', None)
        if vt is not None:
            vt.setText(self._fmt_setting(key, v))
        geom = getattr(self, f'_set_geom_{key}', None)
        if geom is not None:
            track_l, tw, z, th = geom
            fill = getattr(self, f'_set_fill_{key}', None)
            if fill is not None:
                fill.setSx(max(0.0001, v))            # 채움 폭 = 값
            handle = getattr(self, f'_set_handle_{key}', None)
            if handle is not None:
                handle.setX(track_l + tw * v)         # 핸들 위치

    def _setting_value(self, key):
        return {'sens': self._sens_norm, 'master': self._vol_master,
                'sfx': self._vol_sfx}[key]

    def _build_setting_slider(self, parent, key, label, hint, z, lx, rx):
        # HTML .slider 그대로: 얇은 트랙(다크+라인) + 틱 11개 + 레드 채움 + 작은
        # 노치 흰 핸들 + 우측 값. 드래그는 보이지 않는 DirectSlider 가 처리하고,
        # 트랙/틱/채움/핸들은 직접 그려 콜백(_on_setting_change)에서 동기화한다.
        self._tac_fonts()
        value0 = self._setting_value(key)
        OnscreenText(parent=parent, text=label, pos=(lx, z + 0.05), scale=0.026,
                     fg=TAC_TEXT_2, align=TextNode.ALeft,
                     font=self._tac_label_font, mayChange=False)
        if hint:
            OnscreenText(parent=parent, text=hint, pos=(rx, z + 0.05), scale=0.023,
                         fg=TAC_TEXT_3, align=TextNode.ARight,
                         font=self._tac_label_font, mayChange=False)
        val_w = 0.12
        track_l, track_r = lx, rx - val_w
        tw = track_r - track_l
        th = 0.010                                  # 트랙 반높이(≈6px)
        # 트랙(얇은 다크 + 1px 라인) — 전부 지오메트리, 생성순서로 레이어링.
        _tac_fill(parent, track_l, track_r, z - th, z + th, TAC_BG_SURF)
        _tac_outline(parent, track_l, track_r, z - th, z + th, TAC_LINE,
                     thickness=1.2)
        # 틱 11개(양끝 포함)
        for i in range(11):
            tx = track_l + tw * i / 10.0
            _tac_fill(parent, tx - 0.0005, tx + 0.0005, z - 0.006, z + 0.006,
                      TAC_LINE)
        # 레드 채움 — 좌측 고정 노드 + sX 로 폭 = 값(좌→값).
        fill = parent.attachNewNode(f'sfill_{key}')
        fill.setPos(track_l, 0, 0)
        _tac_fill(fill, 0.0, tw, z - th, z + th, TAC_ACCENT)
        fill.setSx(max(0.0001, value0))
        # 핸들 — 작은 노치 흰 사각(트랙보다 약간 큼). 노드를 값 위치로 이동.
        hw, hh = 0.009, 0.022
        handle = parent.attachNewNode(f'handle_{key}')
        hfill = _tac_fill(handle, -hw, hw, z - hh, z + hh, TAC_TEXT_1,
                          notch=hw * 0.8, corners=('tl',))
        handle.setX(track_l + tw * value0)
        vt = OnscreenText(parent=parent, text=self._fmt_setting(key, value0),
                          pos=(rx, z - 0.013), scale=0.034, fg=TAC_TEXT_1,
                          align=TextNode.ARight, font=self._tac_display_font,
                          mayChange=True)
        # 드래그용 보이지 않는 DirectSlider(트랙 영역 위 클릭/드래그 캡처).
        s_cx = (track_l + track_r) / 2.0
        s_scale = max(0.05, tw / 2.0)
        gh = 0.05 / s_scale                          # 잡기 영역 반높이(로컬)
        sl = DirectSlider(
            range=(0.0, 1.0), value=value0, pageSize=0.05,
            command=self._on_setting_change, extraArgs=[key],
            parent=parent, pos=(s_cx, 0, z), scale=s_scale,
            relief=DGG.FLAT, frameColor=(0, 0, 0, 0),
            frameSize=(-1, 1, -gh, gh),
            thumb_relief=DGG.FLAT, thumb_frameColor=(0, 0, 0, 0),
            thumb_frameSize=(-0.02 / s_scale, 0.02 / s_scale, -gh, gh))
        setattr(self, f'_set_slider_{key}', sl)
        setattr(self, f'_set_text_{key}', vt)
        setattr(self, f'_set_fill_{key}', fill)
        setattr(self, f'_set_handle_{key}', handle)
        setattr(self, f'_set_hfill_{key}', hfill)
        setattr(self, f'_set_geom_{key}', (track_l, tw, z, th))
        sl['value'] = value0       # 값 동기(텍스트·채움·핸들 갱신)
        # 트랙/핸들 호버 시 핸들 흰→레드 (HTML .slider .track:hover .handle)
        sl.bind(DGG.WITHIN, lambda _=None: hfill.setColor(*TAC_ACCENT))
        sl.bind(DGG.WITHOUT, lambda _=None: hfill.setColor(*TAC_TEXT_1))
        return sl

    def _build_outline_swatches(self, parent, z, sw=0.115, cx=0.0, left=False):
        # 적 테두리 색 스와치 행 — 선택 표시는 '흰 외곽선'(채움 X, 옆칸과 안 겹침),
        # 호버하면 스와치가 살짝 커진다(0.042→0.050).
        self._swatch_positions = []
        n = len(OUTLINE_PALETTE)
        for i, (name, col) in enumerate(OUTLINE_PALETTE):
            x = (cx + i * sw) if left else (cx + (i - (n - 1) / 2.0) * sw)
            b = DirectButton(
                text='', pos=(x, 0, z), scale=0.042, parent=parent,
                frameColor=col, relief=DGG.FLAT, frameSize=(-1.1, 1.1, -1.1, 1.1),
                command=self._set_outline_color, extraArgs=[col])

            # 호버 스케일 — pause 메뉴는 일시정지 중 글로벌 클럭이 멈춰 direct.interval
            # 이 안 도므로(LerpScaleInterval 무효), 실시간 태스크로 구동해 settings·pause
            # 양쪽에서 동일하게 동작하게 한다.
            def _en(_=None, bb=b):
                self._anim_swatch(bb, 0.050)

            def _ex(_=None, bb=b):
                self._anim_swatch(bb, 0.042)

            b.bind(DGG.WITHIN, _en)
            b.bind(DGG.WITHOUT, _ex)
            self._swatch_positions.append((col, x))
        # 선택 표시 — 흰 1px 외곽선 프레임(채움 없음). _refresh 가 선택 스와치로 이동.
        m = 0.055
        self._swatch_hl = parent.attachNewNode('swatch_hl')
        _tac_outline(self._swatch_hl, -m, m, z - m, z + m, TAC_TEXT_1, thickness=2.2)
        self._swatch_hl.setTransparency(1)
        self._refresh_outline_swatches()

    def _anim_swatch(self, bb, target, dur=0.10):
        """스와치 호버 스케일 애니 — 일시정지(글로벌 클럭 정지) 중에도 동작하도록
        direct.interval 대신 실시간(time.time) 태스크로 구동. settings/pause 공통."""
        name = 'swhover_%d' % id(bb)
        self.taskMgr.remove(name)
        try:
            start = bb.getScale()[0]
        except Exception:
            start = target
        if abs(start - target) < 1e-4:
            bb.setScale(target)
            return
        t0 = time.time()

        def _step(task, bb=bb, start=start, target=target, t0=t0, dur=dur):
            if bb.isEmpty():
                return Task.done
            el = time.time() - t0
            f = min(1.0, el / dur)
            e = 1.0 - (1.0 - f) ** 2          # easeOut
            bb.setScale(start + (target - start) * e)
            return Task.done if f >= 1.0 else Task.cont

        self.taskMgr.add(_step, name)

    # ── 디자인 키트 컴포넌트 (Settings/Lobby 화면 공통) ───────────────────────
    def _tac_panel_head(self, parent, text, lx, rx, z, right=None):
        # 라벨 + 우측으로 뻗는 얇은 라인 + 하단 보더. (.panel-head)
        self._tac_fonts()
        OnscreenText(parent=parent, text=text, pos=(lx, z), scale=0.028,
                     fg=TAC_TEXT_1, align=TextNode.ALeft,
                     font=self._tac_label_font, mayChange=False)
        lstart = lx + 0.016 * len(text) + 0.03
        lend = (rx - 0.22) if right else rx
        _tac_fill(parent, lstart, lend, z + 0.005, z + 0.0065, TAC_LINE)
        _tac_fill(parent, lx, rx, z - 0.035, z - 0.0337, TAC_LINE)  # 하단 보더
        if right:
            OnscreenText(parent=parent, text=right, pos=(rx, z), scale=0.023,
                         fg=TAC_TEXT_3, align=TextNode.ARight,
                         font=self._tac_label_font, mayChange=False)

    def _tac_field(self, parent, label, lx, rx, z, initial, on_enter=None):
        # 라벨 + 노치 입력칸(DirectEntry) + 하단 액센트 라인. (.field)
        self._tac_fonts()
        OnscreenText(parent=parent, text=label, pos=(lx, z + 0.07), scale=0.024,
                     fg=TAC_TEXT_2, align=TextNode.ALeft,
                     font=self._tac_label_font, mayChange=False)
        h = 0.052
        _tac_fill(parent, lx, rx, z - h, z + h, TAC_BG_SURF, notch=0.02,
                  corners=('tl',))
        _tac_outline(parent, lx, rx, z - h, z + h, TAC_LINE, notch=0.02,
                     corners=('tl',), thickness=1.2)
        _tac_fill(parent, lx, rx, z - h - 0.004, z - h, TAC_ACCENT_DIM)
        width_chars = max(6, int((rx - lx - 0.06) / 0.026))
        entry = DirectEntry(
            parent=parent, scale=0.05, pos=(lx + 0.03, 0, z - 0.018),
            width=width_chars, numLines=1, initialText=initial, overflow=1,
            frameColor=(0, 0, 0, 0), text_fg=TAC_TEXT_1,
            command=(on_enter or (lambda *_a: None)))
        return entry

    def _tac_banner(self, parent, lx, z, text, w=0.5, state='idle'):
        # 노치 박스 + 점 + 텍스트. (.banner)
        rx = lx + w
        h = 0.044
        _tac_fill(parent, lx, rx, z - h, z + h, TAC_BG_SURF, notch=0.02,
                  corners=('tl',))
        _tac_outline(parent, lx, rx, z - h, z + h, TAC_LINE, notch=0.02,
                     corners=('tl',), thickness=1.2)
        dot = (TAC_ACCENT if state == 'live' else
               _hexc('#CFD3DA') if state == 'ok' else TAC_STEEL)
        _tac_fill(parent, lx + 0.03, lx + 0.05, z - 0.01, z + 0.01, dot)
        OnscreenText(parent=parent, text=text, pos=(lx + 0.075, z - 0.011),
                     scale=0.025, fg=(TAC_TEXT_1 if state == 'ok' else TAC_TEXT_2),
                     align=TextNode.ALeft, font=self._tac_label_font,
                     mayChange=False)

    def _tac_player_slot(self, parent, lx, rx, zb, zt, me, tag, name, state):
        # 노치 카드 — 코너 태그, 점+YOU/REMOTE, 이름, 상태. (.slot)
        self._tac_fonts()
        line = TAC_ACCENT_DIM if me else TAC_LINE
        _tac_fill(parent, lx, rx, zb, zt, TAC_BG_SURF, notch=0.04, corners=('tl',))
        _tac_outline(parent, lx, rx, zb, zt, line, notch=0.04, corners=('tl',),
                     thickness=1.4)
        OnscreenText(parent=parent, text=tag, pos=(rx - 0.03, zt - 0.05),
                     scale=0.026, fg=TAC_TEXT_3, align=TextNode.ARight,
                     font=self._tac_display_font, mayChange=False)
        _tac_fill(parent, lx + 0.03, lx + 0.048, zt - 0.062, zt - 0.044,
                  TAC_ACCENT if me else TAC_STEEL)
        OnscreenText(parent=parent, text=('YOU' if me else 'REMOTE'),
                     pos=(lx + 0.066, zt - 0.064), scale=0.022,
                     fg=(TAC_ACCENT if me else TAC_STEEL), align=TextNode.ALeft,
                     font=self._tac_label_font, mayChange=False)
        OnscreenText(parent=parent, text=name, pos=(lx + 0.03, (zt + zb) / 2 - 0.02),
                     scale=0.05, fg=(TAC_TEXT_3 if state == 'OPEN SLOT' else TAC_TEXT_1),
                     align=TextNode.ALeft, font=self._tac_display_font,
                     mayChange=False)
        OnscreenText(parent=parent, text=state, pos=(lx + 0.03, zb + 0.04),
                     scale=0.022, fg=TAC_TEXT_2, align=TextNode.ALeft,
                     font=self._tac_label_font, mayChange=False)

    def _tac_toggle(self, parent, x, z, on, label, command):
        # 사각 스위치 + knob + 라벨. 클릭 시 knob 이 좌↔우로 슬라이드 + 색 전환
        # (HTML .toggle .knob: left .14s expo, steel↔accent). 자체 상태 보유.
        sw_w, sw_h, knob_w = 0.07, 0.026, 0.02
        travel = sw_w - knob_w - 0.012        # knob 좌↔우 이동 거리
        state = {'on': bool(on)}
        btn = DirectButton(
            parent=parent, pos=(0, 0, 0), relief=None, pressEffect=0,
            frameSize=(x, x + sw_w + 0.22, z - 0.04, z + 0.04), text='')
        _tac_fill(btn, x, x + sw_w, z - sw_h, z + sw_h, TAC_BG_SURF)
        _tac_outline(btn, x, x + sw_w, z - sw_h, z + sw_h, TAC_LINE, thickness=1.2)
        knob = btn.attachNewNode('knob')
        kfill = _tac_fill(knob, x + 0.006, x + 0.006 + knob_w,
                          z - 0.018, z + 0.018, TAC_STEEL)
        OnscreenText(parent=btn, text=label, pos=(x + sw_w + 0.03, z - 0.011),
                     scale=0.024, fg=TAC_TEXT_1, align=TextNode.ALeft,
                     font=self._tac_label_font, mayChange=False)

        def _apply(animate):
            o = state['on']
            tx = travel if o else 0.0
            kfill.setColor(*(TAC_ACCENT if o else TAC_STEEL))
            if animate:
                LerpPosInterval(knob, 0.14, (tx, 0, 0), (knob.getX(), 0, 0),
                                blendType='easeOut').start()
            else:
                knob.setX(tx)

        _apply(False)

        def _click(_=None):
            state['on'] = not state['on']
            _apply(True)
            if command:
                command(state['on'])

        btn['command'] = _click
        return btn

    # ── 멀티플레이 로비 상태/액션 ─────────────────────────────────────────────
    def _lobby_set_mode(self, mode):
        self._lobby_mode = mode
        self._rebuild_lobby_modes()

    def _on_lobby_ready(self, val):
        # 토글이 자체적으로 knob 슬라이드 애니메이션 → 여기선 상태/문구만 갱신(재빌드 X).
        self._lobby_ready = val
        if getattr(self, '_lobby_ready_status', None) is not None:
            self._lobby_ready_status.setText('ALL OPERATORS READY' if val
                                             else 'AWAITING READY')

    def _lobby_start(self):
        # 콜사인 확정 후 온라인 시작(선택 모드). 서버는 고정 릴레이(읽기전용).
        if self._menu_root is None or self._game_started:
            return
        name = (self._lobby_name_entry.get() or '').strip() or 'PLAYER'
        self.player_name = name[:8]
        m = getattr(self, '_lobby_mode', 'pvp')
        self._start_game(True, soccer=(m == 'soccer'), paint=(m == 'paint'),
                         jump=(m == 'jump'))

    def _make_vignette_tex(self, inner, edge_alpha):
        """레드 라디얼 비네트 텍스처 1장 생성. 중앙 inner(0~1) 까지 완전 투명,
        가장자리(1.0)로 갈수록 TAC_ACCENT 레드 alpha 가 edge_alpha 까지 차오름.
        (디자인 .dmg-vig / .low-vig 의 radial-gradient 를 PNMImage 로 베이크.)"""
        size = 128
        img = PNMImage(size, size, 4)
        cx = cy = (size - 1) * 0.5
        maxd = size * 0.5
        r, g, b = TAC_ACCENT[0], TAC_ACCENT[1], TAC_ACCENT[2]
        span = max(1e-4, 1.0 - inner)
        for y in range(size):
            for x in range(size):
                dx, dy = x - cx, y - cy
                d = ((dx * dx + dy * dy) ** 0.5) / maxd     # 0(중앙)~1.41(모서리)
                t = max(0.0, min(1.0, (d - inner) / span))
                t = t * t                                    # 가장자리로 더 가파르게
                img.setXel(x, y, r, g, b)
                img.setAlpha(x, y, t * edge_alpha)
        tex = Texture()
        tex.load(img)
        return tex

    def _build_vignette(self):
        """화면 가장자리 레드 비네트 2종(피격 플래시 + 저체력 상시)을 풀스크린
        쿼드로 깔아 둔다. render2d 의 background bin → 모든 HUD 보다 뒤(디자인과 동일).
        피격 시 _vig_dmg_t 로 '팍' 떴다 페이드, 저체력(<30%)이면 _vig_low 상시 표시."""
        self._vig_dmg_tex = self._make_vignette_tex(0.58, 0.55)
        self._vig_low_tex = self._make_vignette_tex(0.64, 0.34)
        for name, tex in (('vig_low', self._vig_low_tex),
                          ('vig_dmg', self._vig_dmg_tex)):
            cm = CardMaker(name)
            cm.setFrame(-1, 1, -1, 1)            # render2d 전체(풀스크린)
            cm.setUvRange((0, 0), (1, 1))
            card = self.render2d.attachNewNode(cm.generate())
            card.setTexture(tex)
            card.setTransparency(True)
            card.setLightOff()
            card.setBin('background', 10)        # 모든 2D 보다 뒤에 깔림
            card.setDepthTest(False)
            card.setDepthWrite(False)
            card.setColorScale(1, 1, 1, 0)       # 평소 완전 투명
            setattr(self, name, card)
        self._vig_dmg_t = 0.0                    # 피격 비네트 잔여 시간
        self._vig_dmg_dur = 0.30

    def _trigger_dmg_vignette(self):
        """피격 순간 레드 비네트 플래시 1회 (디자인 .dmg-vig.on 130ms 점멸)."""
        if getattr(self, 'vig_dmg', None) is None:
            return
        self._vig_dmg_t = self._vig_dmg_dur

    def _update_vignette(self, dt, hp_ratio):
        """피격 비네트 페이드 + 저체력 비네트 상시 표시(살짝 맥동)."""
        if getattr(self, 'vig_dmg', None) is None:
            return
        # 피격 — 떴다가 선형 페이드아웃.
        if self._vig_dmg_t > 0.0:
            self._vig_dmg_t = max(0.0, self._vig_dmg_t - dt)
            a = self._vig_dmg_t / self._vig_dmg_dur
            self.vig_dmg.setColorScale(1, 1, 1, a)
        else:
            self.vig_dmg.setColorScale(1, 1, 1, 0)
        # 저체력(30% 이하) — 상시 표시, 체력 낮을수록 진하게 + 은은한 맥동.
        if hp_ratio < 0.30:
            ft = ClockObject.getGlobalClock().getFrameTime()
            pulse = 0.82 + 0.18 * (0.5 + 0.5 * math.sin(ft * 4.0))
            depth = 0.45 + 0.55 * (1.0 - hp_ratio / 0.30)   # 0.45~1.0
            self.vig_low.setColorScale(1, 1, 1, depth * pulse)
        else:
            self.vig_low.setColorScale(1, 1, 1, 0)

    def _build_crosshair(self):
        """발로란트식 크로스헤어 — 중앙 점 + 상하좌우 4선. 정지 시 좁고 이동/연사 시
        바깥으로 벌어짐(spread). 명중 순간 빨간 X 히트마커. 흰색 기본·적중 시 레드."""
        S = HUD_SCALE
        self.crosshair = self.aspect2d.attachNewNode('crosshair')
        self.crosshair.setTransparency(True)
        self.crosshair.setLightOff()
        self.crosshair.setBin('fixed', 80)
        self.crosshair.setDepthTest(False)
        self.crosshair.setDepthWrite(False)
        self._ch_len = 0.020 * S          # 선 길이
        self._ch_gap0 = 0.011 * S         # 기본 간격(정지)
        self._ch_lines = {}
        # 각 방향마다 컨테이너 노드 하나 → 그 안에 어두운 외곽선(굵게) + 흰 선(얇게).
        # 외곽선 덕에 밝은 벽/어두운 바닥 어디서나 또렷이 보인다(발로란트식).
        for key, (dx, dz) in {'t': (0, 1), 'b': (0, -1),
                              'l': (-1, 0), 'r': (1, 0)}.items():
            cont = self.crosshair.attachNewNode('ch_' + key)
            for thick, col in ((4.2, (0, 0, 0, 0.9)), (2.2, TAC_TEXT_1)):
                ls = LineSegs()
                ls.setThickness(thick)
                ls.setColor(*col)
                ls.moveTo(0, 0, 0)
                ls.drawTo(dx * self._ch_len, 0, dz * self._ch_len)
                np = cont.attachNewNode(ls.create())
                if thick < 3:
                    self._ch_lines[key] = (cont, np, dx, dz)   # 흰 선 = 색 갱신 대상
        d = 0.0016 * S                    # 중앙 점 (어두운 외곽 + 흰 점)
        _tac_fill(self.crosshair, -d * 2.1, d * 2.1, -d * 2.1, d * 2.1,
                  (0, 0, 0, 0.9))
        self.ch_dot = _tac_fill(self.crosshair, -d, d, -d, d, TAC_TEXT_1)
        # 히트마커 — 빨간 X, 평소 hide, 명중 순간 잠깐 표시.
        self.hitmarker = self.aspect2d.attachNewNode('hitmarker')
        self.hitmarker.setTransparency(True)
        self.hitmarker.setLightOff()
        self.hitmarker.setBin('fixed', 81)
        self.hitmarker.setDepthTest(False)
        self.hitmarker.setDepthWrite(False)
        hm = LineSegs()
        hm.setThickness(2.6)
        hm.setColor(*TAC_TEXT_1)   # 흰색 베이스 — 명중=흰 X, 처치=setColorScale 로 레드
        g0, g1 = 0.012 * S, 0.027 * S
        for (sx, sz) in [(1, 1), (-1, -1), (1, -1), (-1, 1)]:
            hm.moveTo(sx * g0, 0, sz * g0)
            hm.drawTo(sx * g1, 0, sz * g1)
        self.hitmarker.attachNewNode(hm.create())
        self.hitmarker.hide()
        self._hitmarker_t = 0.0
        self._ch_alert = False        # 적 조준 중이면 빨강
        self._ch_spread = 0.0         # 기본 간격 위에 더해지는 추가 벌어짐
        self._ch_kick = 0.0           # 발사 시 순간 킥(감쇠)
        self._ch_lastpos = Vec3(getattr(self, 'player_pos', Vec3(0, 0, 0)))

    def _update_crosshair(self, dt):
        # spread = 이동/연사 시 추가 벌어짐(부드럽게 수렴). gap = 기본 + spread.
        S = HUD_SCALE
        pos = getattr(self, 'player_pos', None)
        moving = False
        if pos is not None:
            moving = (pos - self._ch_lastpos).lengthSquared() > (0.02 ** 2)
            self._ch_lastpos = Vec3(pos)
        if getattr(self, '_hands_oneshot', False):
            self._ch_kick = 0.030 * S
        self._ch_kick = max(0.0, self._ch_kick - dt * 0.10)
        target = (0.013 * S if moving else 0.0) + self._ch_kick
        self._ch_spread += (target - self._ch_spread) * min(1.0, dt * 14.0)
        gap = self._ch_gap0 + self._ch_spread
        hot = self._ch_alert or self._hitmarker_t > 0
        col = TAC_ACCENT if hot else TAC_TEXT_1
        for (cont, white, dx, dz) in self._ch_lines.values():
            cont.setPos(dx * gap, 0, dz * gap)
            white.setColor(*col)
        self.ch_dot.setColor(*col)

    # 콤보 게이지 바 — 화면 하단 중앙. 좌측 고정, 남은 시간만큼 우측 가장자리가
    # 차오르고, 시간이 흐르면 우측 가장자리가 왼쪽으로 줄며 소진된다.
    COMBO_BAR_HW = 0.34      # 바 절반 너비 (x: -HW ~ +HW)
    COMBO_BAR_HH = 0.012     # 바 절반 높이
    COMBO_BAR_Z  = 0.135     # 화면 하단 가장자리 위로 띄운 높이

    def _build_combo_bar(self):
        hw, hh, z = self.COMBO_BAR_HW, self.COMBO_BAR_HH, self.COMBO_BAR_Z
        pad = 0.006
        # 바텀 센터 기준 컨테이너 — 평소 hidden, 콤보 진행 중에만 show.
        self.combo_bar = self.a2dBottomCenter.attachNewNode('combo_bar')
        self.combo_bar.setPos(0, 0, z)
        # 트랙(배경) — 옅은 반투명 흰 + 살짝 큰 테두리.
        self.combo_bar_track = DirectFrame(
            frameColor=HUD_WHITE_TRANS_DIM,
            frameSize=(-hw - pad, hw + pad, -hh - pad, hh + pad),
            pos=(0, 0, 0), parent=self.combo_bar)
        # 채움 — 좌측(-hw) 고정, 우측 가장자리를 매 프레임 갱신.
        self.combo_bar_fill = DirectFrame(
            frameColor=HUD_WHITE_TRANS,
            frameSize=(-hw, hw, -hh, hh),
            pos=(0, 0, 0), parent=self.combo_bar)
        # 단계 텍스트 (x2 ~ x5) — 바 우측 끝 위에 작게.
        self.combo_bar_tier = OnscreenText(
            text='', pos=(hw + pad, hh + 0.012), scale=0.05,
            fg=HUD_WHITE_TRANS, align=TextNode.ARight, mayChange=True,
            parent=self.combo_bar)
        self.combo_bar.hide()

    def _update_combo_bar(self):
        # 콤보 윈도우가 살아있을 때만 표시. ratio = 남은시간 / 전체.
        if self._combo_window <= 0.0 or self.kill_combo_dur <= 0.0:
            if not self.combo_bar.isHidden():
                self.combo_bar.hide()
            return
        ratio = max(0.0, min(1.0, self._combo_window / self.kill_combo_dur))
        hw, hh = self.COMBO_BAR_HW, self.COMBO_BAR_HH
        # 좌측 고정, 우측 가장자리만 ratio 따라 이동 → 왼쪽으로 슬라이드 소진.
        right = -hw + 2.0 * hw * ratio
        self.combo_bar_fill['frameSize'] = (-hw, right, -hh, hh)
        # 단계 표시 — 2단계 이상일 때만 (1단계는 콤보 아님).
        if self._kill_tier >= 2:
            self.combo_bar_tier.setText(f'x{self._kill_tier}')
        else:
            self.combo_bar_tier.setText('')
        if self.combo_bar.isHidden():
            self.combo_bar.show()

    # --- 발로란트 스타일 킬배너 ----------------------------------------------

    def _make_filled_circle(self, radius, color, segs=48):
        """X-Z 평면 채워진 원(삼각형 팬) NodePath. aspect2d 용 — 위젯은 한 번만 생성."""
        vdata = GeomVertexData('disc', GeomVertexFormat.getV3(), Geom.UHStatic)
        vw = GeomVertexWriter(vdata, 'vertex')
        vw.addData3(0, 0, 0)                       # 중심
        for i in range(segs + 1):
            a = (i / segs) * 6.283185307179586
            vw.addData3(radius * cos(a), 0, radius * sin(a))
        tris = GeomTriangles(Geom.UHStatic)
        for i in range(1, segs + 1):
            tris.addVertices(0, i, i + 1)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        gn = GeomNode('disc')
        gn.addGeom(geom)
        np = NodePath(gn)
        np.setColor(*color)
        np.setLightOff()
        np.setTwoSided(True)
        return np

    def _make_skull(self, S):
        """HTML 의 해골 SVG(viewBox 0..100, 100px 표시) 를 다각형 지오메트리로 재현.
        흰 외곽(직선 16각) + 어두운 눈·코 구멍 + 이빨 3줄. translate(0,4.5) 반영.
        S = 디자인(px)→aspect2d 스케일. 원반 안에 알맞게 들어감."""
        KB, DISC = KB_WHITE, KB_DISC

        def M(sx, sy):
            # 해골박스 중심(50,50)→레티클 중심, 아래로 4.5; svg y-down → z-up.
            return ((sx - 50.0) * S, -(sy - 45.5) * S)

        # 흰 두개골 외곽 (전부 직선 16각) — 턱 부분 오목 → Triangulator.
        outline = [(50, 7), (32, 11), (20, 23), (16, 39), (22, 54), (31, 60),
                   (34, 72), (45, 84), (50, 80), (55, 84), (66, 72), (69, 60),
                   (78, 54), (84, 39), (80, 23), (68, 11)]
        pts = [M(sx, sy) for (sx, sy) in outline]
        tri = Triangulator()
        for (x, z) in pts:
            tri.addPolygonVertex(tri.addVertex(x, z))
        tri.triangulate()
        vdata = GeomVertexData('skull', GeomVertexFormat.getV3(), Geom.UHStatic)
        vw = GeomVertexWriter(vdata, 'vertex')
        for (x, z) in pts:
            vw.addData3(x, 0, z)
        prim = GeomTriangles(Geom.UHStatic)
        for k in range(tri.getNumTriangles()):
            prim.addVertices(tri.getTriangleV0(k), tri.getTriangleV1(k),
                             tri.getTriangleV2(k))
        gn = GeomNode('skull_white')
        gn.addGeom(self._geom_from(vdata, prim))
        white = NodePath(gn)
        white.setColor(*KB)
        white.setTwoSided(True)
        white.setLightOff()

        # 어두운 눈(2)·코(1) — 볼록 다각형, 팬 삼각분할.
        feats = [
            [(22, 40), (45, 47), (42, 55), (27, 53)],   # 왼 눈
            [(78, 40), (55, 47), (58, 55), (73, 53)],   # 오른 눈
            [(50, 59), (45, 69), (50, 67), (55, 69)],   # 코
        ]
        dvd = GeomVertexData('skullf', GeomVertexFormat.getV3(), Geom.UHStatic)
        dvw = GeomVertexWriter(dvd, 'vertex')
        dprim = GeomTriangles(Geom.UHStatic)
        base = 0
        for poly in feats:
            for (sx, sy) in poly:
                x, z = M(sx, sy)
                dvw.addData3(x, 0, z)
            for k in range(1, len(poly) - 1):
                dprim.addVertices(base, base + k, base + k + 1)
            base += len(poly)
        dgn = GeomNode('skull_dark')
        dgn.addGeom(self._geom_from(dvd, dprim))
        dark = NodePath(dgn)
        dark.setColor(*DISC)
        dark.setTwoSided(True)
        dark.setLightOff()
        dark.setBin('fixed', 62)     # 흰 두개골(60) 위에 구멍 표시

        # 이빨 3줄 — 어두운 짧은 선.
        teeth = LineSegs()
        teeth.setThickness(1.6)
        teeth.setColor(*DISC)
        for (a, b) in [((46, 72), (45, 79)), ((50, 73), (50, 80)),
                       ((54, 72), (55, 79))]:
            ax, az = M(*a)
            bx, bz = M(*b)
            teeth.moveTo(ax, 0, az)
            teeth.drawTo(bx, 0, bz)
        teeth_np = NodePath(teeth.create())
        teeth_np.setLightOff()
        teeth_np.setBin('fixed', 62)

        grp = NodePath('skull')
        white.reparentTo(grp)
        dark.reparentTo(grp)
        teeth_np.reparentTo(grp)
        return grp

    def _arc(self, radius, thick, color, a0, a1):
        """단일 호 NodePath (a0~a1 deg, 로컬 반지름)."""
        ls = LineSegs()
        ls.setThickness(thick)
        ls.setColor(*color)
        steps = max(2, int(abs(a1 - a0) / 3.0))
        for s in range(steps + 1):
            ang = radians(a0 + (a1 - a0) * s / steps)
            x, z = radius * cos(ang), radius * sin(ang)
            if s == 0:
                ls.moveTo(x, 0, z)
            else:
                ls.drawTo(x, 0, z)
        np = NodePath(ls.create())
        np.setLightOff()
        return np

    def _radial_tick(self, r0, r1, thick, color, ang_deg):
        """ang_deg 방향 r0→r1 방사 틱 NodePath."""
        ls = LineSegs()
        ls.setThickness(thick)
        ls.setColor(*color)
        a = radians(ang_deg)
        ls.moveTo(r0 * cos(a), 0, r0 * sin(a))
        ls.drawTo(r1 * cos(a), 0, r1 * sin(a))
        np = NodePath(ls.create())
        np.setLightOff()
        return np

    def _kb_card(self, name, parent, S):
        """UI_DIR/name (reticle 와 동일한 220유닛 캔버스) 을 reticle 전체에 꽉 차는
        투명 카드로 중앙 배치. 파일 없으면 None (→ 호출부가 LineSegs 폴백)."""
        p = UI_DIR / name
        if not p.exists():
            return None
        tex = self.loader.loadTexture(Filename.from_os_specific(str(p)))
        img = OnscreenImage(image=tex, pos=(0, 0, 0),
                            scale=(110 * S, 1, 110 * S), parent=parent)
        img.setTransparency(True)
        return img

    @staticmethod
    def _geom_from(vdata, prim):
        g = Geom(vdata)
        g.addPrimitive(prim)
        return g

    def _dashed_ring(self, radius, thick, color, on_deg, off_deg, start_deg=0.0):
        """끊긴(점선/호) 원형 링 NodePath — LineSegs 호 세그먼트로 구성.
        on_deg 켜짐 / off_deg 꺼짐 을 360° 둘레에 반복. on_deg=360 이면 실선."""
        ls = LineSegs()
        ls.setThickness(thick)
        ls.setColor(*color)
        period = on_deg + off_deg
        a = start_deg
        end = start_deg + 360.0
        while a < end - 1e-6:
            a1 = min(a + on_deg, end)
            steps = max(1, int((a1 - a) / 3.0))    # 호를 3° 간격으로 세분
            for s in range(steps + 1):
                ang = radians(a + (a1 - a) * s / steps)
                x, z = radius * cos(ang), radius * sin(ang)
                if s == 0:
                    ls.moveTo(x, 0, z)
                else:
                    ls.drawTo(x, 0, z)
            a += period
        np = NodePath(ls.create())
        np.setLightOff()
        return np

    @staticmethod
    def _cb_ease(t, x1, y1, x2, y2):
        """CSS cubic-bezier(x1,y1,x2,y2) — 시간비 t(0..1)에 대한 진행값을 반환.
        Bx(u)=t 를 Newton 으로 풀어 u 를 구한 뒤 By(u). 버스트 이징을 HTML 과 일치."""
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        u = t
        for _ in range(8):
            mu = 1.0 - u
            x = 3.0 * mu * mu * u * x1 + 3.0 * mu * u * u * x2 + u * u * u
            dx = (3.0 * mu * mu * x1 + 6.0 * mu * u * (x2 - x1)
                  + 3.0 * u * u * (1.0 - x2))
            if abs(dx) < 1e-6:
                break
            u = min(1.0, max(0.0, u - (x - t) / dx))
        mu = 1.0 - u
        return 3.0 * mu * mu * u * y1 + 3.0 * mu * u * u * y2 + u * u * u

    def _build_kill_banner(self):
        """처치 알림 위젯을 한 번만 생성하고 평소엔 hide. 색은 흰색 고정.
        HTML(kill_banner_motion.html): 정적 타겟팅 프레임 + 회전 레티클 2겹 + 원반
        + 해골 + 등장 플래시/쇼크링/파티클 버스트."""
        S = 0.00125                       # 디자인(px) → aspect2d 스케일
        self._kb_S = S
        KB, DISC = KB_WHITE, KB_DISC
        white = (KB[0], KB[1], KB[2], 1.0)

        self.kb_root = self.aspect2d.attachNewNode('kill_banner')
        self.kb_root.setPos(0, 0, -0.62)  # 화면 하단 중앙
        self.kb_root.setTransparency(True)
        self.kb_root.setLightOff()
        self.kb_root.setBin('fixed', 60)
        self.kb_root.setDepthTest(False)
        self.kb_root.setDepthWrite(False)

        # 등장 플래시 (radial, .85→0) — root 직속, 뒤에 깔림.
        self.kb_flash = self._make_filled_circle(100 * S, KB, segs=40)
        self.kb_flash.reparentTo(self.kb_root)
        self.kb_flash.setTransparency(True)
        self.kb_flash.setColorScale(1, 1, 1, 0)
        self.kb_flash.setBin('fixed', 58)

        # 쇼크 링 (scale .4→2, alpha .8→0) — root 직속, 독립 확산.
        self.kb_shock = self._dashed_ring(70 * S, 2.0, white, 360.0, 0.0)
        self.kb_shock.reparentTo(self.kb_root)
        self.kb_shock.setTransparency(True)
        self.kb_shock.setColorScale(1, 1, 1, 0)
        self.kb_shock.setBin('fixed', 59)

        # slam(scale/alpha) 대상 — 프레임/링/원반/해골 모두 자식.
        self.kb_motion = self.kb_root.attachNewNode('kb_motion')

        # 정적 타겟팅 프레임 (회전 안 함) — frame.png (220유닛 캔버스) 우선,
        # 없으면 LineSegs 폴백(코너 브래킷 4 + 방위 틱 4 + 바깥 호 4).
        self.kb_frame = self.kb_motion.attachNewNode('kb_frame')
        if self._kb_card('frame.png', self.kb_frame, S) is None:
            for c in (45, 135, 225, 315):
                self._arc(101 * S, 2.0, white, c - 34, c + 34).reparentTo(self.kb_frame)
            for a in (0, 90, 180, 270):
                self._radial_tick(88 * S, 105 * S, 3.0, white, a).reparentTo(self.kb_frame)
                self._arc(107 * S, 2.5, white, a - 8, a + 8).reparentTo(self.kb_frame)

        # 회전 레티클 링 2겹 — ring_outer/inner.png (220유닛 캔버스, r93/r85 박힘)
        # 우선. 위치·굵기·대시는 PNG 에 그대로 있으니 카드만 깔고 노드를 회전시킨다.
        # 파일 없으면 LineSegs 폴백.
        self.kb_ringA = self.kb_motion.attachNewNode('ringA')   # 바깥, 시계방향 9s
        self.kb_ringB = self.kb_motion.attachNewNode('ringB')   # 안쪽, 반시계방향 6s
        if self._kb_card('ring_outer.png', self.kb_ringA, S) is None:
            self._dashed_ring(93 * S, 2.0, (KB[0], KB[1], KB[2], 0.5), 3.7, 6.2
                              ).reparentTo(self.kb_ringA)
            self._dashed_ring(93 * S, 6.0, white, 20.9, 73.9).reparentTo(self.kb_ringA)
        if self._kb_card('ring_inner.png', self.kb_ringB, S) is None:
            self._dashed_ring(85 * S, 2.0, (KB[0], KB[1], KB[2], 0.7), 1.35, 4.7
                              ).reparentTo(self.kb_ringB)
            self._dashed_ring(85 * S, 5.0, white, 13.5, 141.6).reparentTo(self.kb_ringB)

        # 중앙 원반(어두움) + 흰 테두리.
        self._make_filled_circle(76 * S, DISC, segs=56).reparentTo(self.kb_motion)
        self._dashed_ring(76 * S, 2.5, white, 360.0, 0.0).reparentTo(self.kb_motion)

        # 해골 — assets/ui/skull.png (512² 투명, 좌우 그라데이션) 우선 사용.
        # 이미지 art 가 프레임의 ~68%×77% → full 이미지를 100-box(=50*S 반폭)에 맞추면
        # art 가 원반 안에 알맞게 들어감. HTML translate(0,4.5) → 살짝 아래로.
        skull_path = UI_DIR / 'skull.png'
        if skull_path.exists():
            tex = self.loader.loadTexture(Filename.from_os_specific(str(skull_path)))
            self.kb_skull = OnscreenImage(
                image=tex, pos=(0, 0, -4.5 * S), scale=(50 * S, 1, 50 * S),
                parent=self.kb_motion)
            self.kb_skull.setTransparency(True)
            # 틴트 없이 원본 그라데이션 유지 (이미 흰/회색 톤).
        else:
            self.kb_skull = self._make_skull(S)
            self.kb_skull.reparentTo(self.kb_motion)

        # 파티클 버스트 풀 (root 직속, 위에 그림) — 작은 원들이 '팡' 터지는 느낌.
        # 위젯(원 28개)을 한 번만 만들고 매 킬마다 재사용 → 드랍 방지.
        self.kb_burst = self.kb_root.attachNewNode('kb_burst')
        self.kb_burst.setBin('fixed', 63)
        self._kb_dots = []
        for _ in range(28):
            d = self._make_filled_circle(1.0 * S, KB, segs=12)
            d.reparentTo(self.kb_burst)
            d.setTransparency(True)
            d.setColorScale(1, 1, 1, 0)
            self._kb_dots.append(d)
        self._kb_dot_dir = [(0.0, 0.0)] * len(self._kb_dots)
        self._kb_dot_dist = [0.0] * len(self._kb_dots)
        self._kb_dot_life = [0.0] * len(self._kb_dots)
        self._kb_dot_scale = [1.0] * len(self._kb_dots)
        self._kb_burst_t = 0.0
        self._kb_burst_life = 0.0

        self.kb_root.hide()

        # 링 회전 + 버스트 task.
        self._kb_angle_a = 0.0
        self._kb_angle_b = 0.0
        self.taskMgr.add(self._kb_task, 'kb_task')

        # 등장→유지→퇴장 Sequence (재사용; 새 킬마다 restart).
        appear = Parallel(
            Sequence(
                LerpScaleInterval(self.kb_motion, 0.27, 0.97,
                                  startScale=1.45, blendType='easeOut'),
                LerpScaleInterval(self.kb_motion, 0.07, 1.0,
                                  startScale=0.97, blendType='easeOut'),
            ),
            LerpColorScaleInterval(self.kb_motion, 0.204, (1, 1, 1, 1),
                                   startColorScale=(1, 1, 1, 0), blendType='easeOut'),
            LerpColorScaleInterval(self.kb_flash, 0.45, (1, 1, 1, 0),
                                   startColorScale=(1, 1, 1, 0.85), blendType='easeOut'),
            LerpScaleInterval(self.kb_shock, 0.55, 2.0,
                              startScale=0.4, blendType='easeOut'),
            LerpColorScaleInterval(self.kb_shock, 0.55, (1, 1, 1, 0),
                                   startColorScale=(1, 1, 1, 0.8), blendType='easeOut'),
        )
        leave = Parallel(
            LerpScaleInterval(self.kb_motion, 0.4, 1.1,
                              startScale=1.0, blendType='easeIn'),
            LerpColorScaleInterval(self.kb_motion, 0.4, (1, 1, 1, 0),
                                   startColorScale=(1, 1, 1, 1), blendType='easeIn'),
        )
        self._kb_seq = Sequence(
            Func(self._kb_prep),
            appear,
            Wait(1.25),    # appear(최대 0.55s) + 1.25 = play 후 1.8s 에 out (HTML 동일)
            leave,
            Func(self.kb_root.hide),
        )

    def _kb_prep(self):
        """Sequence 시작 — 초기 상태(scale/alpha) 세팅 + show + 버스트 발사."""
        self.kb_motion.setScale(1.45)
        self.kb_motion.setColorScale(1, 1, 1, 0)
        self.kb_flash.setColorScale(1, 1, 1, 0.85)
        self.kb_shock.setScale(0.4)
        self.kb_shock.setColorScale(1, 1, 1, 0.8)
        self.kb_root.show()
        self._kb_fire_burst()

    def _kb_fire_burst(self):
        """작은 원들을 중앙에서 사방으로 '팡' — 방향/거리/수명/크기 랜덤.
        위치·크기·알파는 task 가 매 프레임 갱신. 모두 중앙(0)에서 동시에 출발."""
        S = self._kb_S
        self._kb_burst_life = 0.0
        for i, d in enumerate(self._kb_dots):
            ang = random.uniform(0.0, 6.283185307179586)
            # HTML burst(): dist 46+rand*60, dur 320+rand*240ms, size 2+rand*3 px.
            dist = (46.0 + random.uniform(0.0, 60.0)) * S
            life = 0.32 + random.uniform(0.0, 0.24)
            scl = 1.0 + random.uniform(0.0, 1.5)            # 지름 2~5px (base r=1px)
            self._kb_dot_dir[i] = (cos(ang), -sin(ang))     # svg y-down → z-up
            self._kb_dot_dist[i] = dist
            self._kb_dot_life[i] = life
            self._kb_dot_scale[i] = scl
            d.setPos(0, 0, 0)
            d.setScale(scl)
            d.setColorScale(1, 1, 1, 1)
            if life > self._kb_burst_life:
                self._kb_burst_life = life
        self._kb_burst_t = self._kb_burst_life

    def _kb_task(self, task):
        clock = ClockObject.getGlobalClock()
        dt = clock.getDt()
        # 링 회전 (보일 때만).
        if not self.kb_root.isHidden():
            self._kb_angle_a = (self._kb_angle_a + 40.0 * dt) % 360.0   # CW  ~9s
            self._kb_angle_b = (self._kb_angle_b - 60.0 * dt) % 360.0   # CCW ~6s
            self.kb_ringA.setR(self._kb_angle_a)
            self.kb_ringB.setR(self._kb_angle_b)
        # 파티클 버스트 진행 — 빠르게 튀어나가(강한 easeOut) 작아지며 사라짐 → '팡'.
        if self._kb_burst_t > 0.0:
            self._kb_burst_t = max(0.0, self._kb_burst_t - dt)
            elapsed = self._kb_burst_life - self._kb_burst_t
            for i, d in enumerate(self._kb_dots):
                life = self._kb_dot_life[i] or 1.0
                f = min(1.0, elapsed / life)
                ease = self._cb_ease(f, 0.12, 0.85, 0.25, 1.0)   # HTML cubic-bezier
                ux, uz = self._kb_dot_dir[i]
                dist = self._kb_dot_dist[i] * ease
                d.setPos(ux * dist, 0, uz * dist)
                d.setScale(self._kb_dot_scale[i] * (1.0 - 0.6 * ease))  # 1→.4
                a = 1.0 if f < 0.5 else max(0.0, 1.0 - (f - 0.5) / 0.5)
                d.setColorScale(1, 1, 1, a)
            if self._kb_burst_t <= 0.0:
                for d in self._kb_dots:
                    d.setColorScale(1, 1, 1, 0)
        return task.cont

    def _show_kill_banner(self):
        """처치 시 호출 — HTML(kill_banner_motion.html) 그대로 화면 하단 중앙에 해골
        슬램 배너를 재생. play()/setInterval 처럼 진행 중이어도 처음부터 재시작."""
        seq = getattr(self, '_kb_seq', None)
        if seq is not None:
            seq.start()

    def _push_killfeed(self, text='ELIMINATED', mine=True):
        # 한 줄 행(좌측 레드/스틸 바 + 우측정렬 텍스트)을 쌓고, 최신이 위로.
        self._tac_fonts()
        if not hasattr(self, '_kf_parent'):
            return
        row = self._kf_parent.attachNewNode('kf_row')
        OnscreenText(parent=row, text=text, pos=(-0.05, -0.011), scale=0.040,
                     fg=TAC_TEXT_1, align=TextNode.ARight,
                     font=self._tac_label_font, mayChange=False)
        _tac_fill(row, -0.038, -0.024, -0.020, 0.020,
                  TAC_ACCENT if mine else TAC_STEEL)
        self._kf_rows.insert(0, [row, 0.0])
        if len(self._kf_rows) > 5:
            self._kf_rows.pop()[0].removeNode()
        self._relayout_killfeed()

    def _relayout_killfeed(self):
        for i, entry in enumerate(self._kf_rows):
            entry[0].setPos(0, 0, -0.12 - i * 0.060)

    def _update_killfeed(self, dt):
        # 행 수명 3.6s, 마지막 0.6s 페이드아웃.
        if not getattr(self, '_kf_rows', None):
            return
        changed = False
        for entry in list(self._kf_rows):
            entry[1] += dt
            if entry[1] > 3.6:
                entry[0].removeNode()
                self._kf_rows.remove(entry)
                changed = True
            else:
                a = 1.0 if entry[1] < 3.0 else max(0.0, (3.6 - entry[1]) / 0.6)
                entry[0].setColorScale(1, 1, 1, a)
        if changed:
            self._relayout_killfeed()

    # --- HUD -----------------------------------------------------------------

    def _hud_img(self, name, pos, scale, parent, hidden=False):
        """UI_DIR/{name} PNG 을 OnscreenImage 로 띄우고 _hud_images 에 등록.
        등록된 이미지는 _set_glitch 에서 일괄 setColorScale 로 시안↔빨강 틴트.
        텍스처를 명시 로드해서 전달 — OnscreenImage 가 PNG 를 모델로 오해하는 케이스 회피."""
        fn = Filename.from_os_specific(str(UI_DIR / name))
        tex = self.loader.loadTexture(fn)
        if tex is None:
            raise RuntimeError(f'[hud] failed to load {fn}')
        img = OnscreenImage(image=tex, pos=pos, scale=scale, parent=parent)
        img.setTransparency(True)
        img.setColorScale(*HUD_TINT_CYAN)
        if hidden:
            img.hide()
        self._hud_images.append(img)
        return img

    def _build_weapon_tab(self, parent, l, r, b, t, keynum, name):
        """무기 레일 탭 하나 — 노치 다크 패널 + 키번호 + 이름 + (액티브) 좌측 레드 바.
        반환 dict 의 위젯 색을 _update_hud 에서 토글해 현재 무기를 강조한다."""
        n = 0.018
        fill = _tac_fill(parent, l, r, b, t, (0.055, 0.060, 0.072, 0.50),
                         notch=n, corners=('tl', 'br'))
        _tac_outline(parent, l, r, b, t, TAC_LINE, notch=n, corners=('tl', 'br'),
                     thickness=1.2)
        bar = _tac_fill(parent, l, l + 0.012, b + 0.009, t - 0.009, TAC_ACCENT)
        zc = (b + t) / 2 - 0.013
        OnscreenText(parent=parent, text=keynum, pos=(l + 0.028, zc), scale=0.028,
                     fg=TAC_TEXT_3, align=TextNode.ALeft, mayChange=False,
                     font=getattr(self, '_tac_label_font', None))
        nm = OnscreenText(parent=parent, text=name, pos=(l + 0.066, zc), scale=0.032,
                          fg=TAC_TEXT_2, align=TextNode.ALeft, mayChange=True,
                          font=getattr(self, '_tac_label_font', None))
        return {'fill': fill, 'bar': bar, 'name': nm}

    # 무기 실루엣 — 디자인 kit 의 PistolSil/RifleSil SVG path 를 그대로 폴리곤화.
    WEAPON_SIL = {
        'pistol': (150.0, 90.0,
                   'M8 30 H132 V44 L104 47 L97 58 H78 L72 50 H46 V52 H40 V72 H60 '
                   'L54 86 H26 L19 64 C16 54 20 49 30 48 H34 V44 H8 Z'),
        'rifle': (220.0, 84.0,
                  'M6 30 H150 V22 H176 V30 H214 V40 H176 V36 H150 V46 H120 L112 64 '
                  'H92 L99 46 H64 V58 H82 V64 H40 V58 H50 V46 H30 L24 58 H10 L16 46 H6 Z'),
    }

    def _build_weapon_sil(self, parent, weapon, right_x, top_z, width):
        """무기 실루엣(흰 단색)을 ammo 플레이트 상단 우측에 그린다. SVG y(아래로+)는
        flip 해서 z(위로+)로. 오목 형상이라 Triangulator 로 삼각분할."""
        vb = self.WEAPON_SIL.get(weapon)
        if vb is None:
            return None
        vbw, vbh, d = vb
        raw = _parse_svg_points(d)
        if len(raw) < 3:
            return None
        sc = width / vbw
        pts = [(x * sc + (right_x - width), top_z - y * sc) for (x, y) in raw]
        tri = Triangulator()
        for (x, z) in pts:
            tri.addPolygonVertex(tri.addVertex(x, z))
        tri.triangulate()
        if tri.getNumTriangles() == 0:
            return None
        vdata = GeomVertexData('wsil', GeomVertexFormat.getV3(), Geom.UHStatic)
        vw = GeomVertexWriter(vdata, 'vertex')
        for (x, z) in pts:
            vw.addData3(x, 0, z)
        prim = GeomTriangles(Geom.UHStatic)
        for k in range(tri.getNumTriangles()):
            prim.addVertices(tri.getTriangleV0(k), tri.getTriangleV1(k),
                             tri.getTriangleV2(k))
        gn = GeomNode('wsil')
        gn.addGeom(self._geom_from(vdata, prim))
        np = parent.attachNewNode(gn)
        np.setColor(*TAC_TEXT_1)
        np.setTwoSided(True)
        np.setTransparency(True)
        np.setLightOff()
        return np

    def _deathmatch_active(self):
        """데스매치(킬 점수) 진행 중인가 — 상대 HP 칩(OppCompact)을 띄울 조건.
        축구/땅따먹기/점프맵·준비방 제외."""
        return ((self.online_mode or self.ai_mode)
                and not (self.soccer_mode or self.paint_mode
                         or getattr(self, 'jump_mode', False))
                and not getattr(self, '_in_lobby', False))

    def _rebuild_mag_strip(self, amax):
        """탄창 스트립을 amax 개의 세그먼트로 다시 그린다(무기 교체 시 ammo_max 변동 대응).
        매 프레임 색만 갱신하면 되도록 지오메트리는 여기서 한 번만 만든다."""
        for seg in getattr(self, '_mag_segs', []):
            seg.removeNode()
        self._mag_segs = []
        amax = max(1, int(amax))
        mag_l, mag_r, mag_z, mag_hh = -0.360, -0.045, 0.072, 0.011
        gap = 0.004 if amax <= 12 else 0.0022
        seg_w = (mag_r - mag_l) / amax
        for i in range(amax):
            x0 = mag_l + seg_w * i
            x1 = x0 + max(0.004, seg_w - gap)
            seg = _tac_fill(self._mag_strip, x0, x1, mag_z - mag_hh, mag_z + mag_hh,
                            TAC_LINE)
            self._mag_segs.append(seg)
        self._mag_built_max = amax

    def _build_hud(self):
        """플레이어 상태 표시 HUD. 외형은 HUD PNG (assets/ui/) 로 그리고,
        그 위에 텍스트·동적 채움을 얹음."""
        # 코너 기준 HUD 는 코너마다 스케일 컨테이너를 하나 끼워 거기에 HUD_SCALE 를
        # 건다. 개별 요소의 pos/scale 은 그대로 두고도 정렬 보존된 채 비례 확대된다.
        self._tac_fonts()       # 택티컬 콘덴스드 폰트 먼저 로드(이하 전부 사용)
        self._build_vignette()  # 화면 가장자리 레드 비네트(피격/저체력) — 풀스크린
        L = self.a2dTopLeft.attachNewNode('hud_tl');     L.setScale(HUD_SCALE)
        R = self.a2dTopRight.attachNewNode('hud_tr');    R.setScale(HUD_SCALE)
        BL = self.a2dBottomLeft.attachNewNode('hud_bl');  BL.setScale(HUD_SCALE)
        BR = self.a2dBottomRight.attachNewNode('hud_br'); BR.setScale(HUD_SCALE)
        s = GLITCH_LABELS

        self._hud_images = []   # _set_glitch 가 일괄 틴트

        # 좌상단 — 시스템 식별 배너 (banner.png, 2000×496 ≈ 4.03:1).
        # 배너 왼쪽 ~11% 는 액센트 블록 (세그먼트 노치 있는 cyan 블록) — 텍스트는 그 우측
        # 내부 패널에 위치해야 안 겹침. 액센트 끝 ≈ banner_x0 + 0.055.
        self.hud_banner_img = self._hud_img(
            'banner.png', pos=(0.30, 0, -0.135),
            scale=(0.25, 1, 0.062), parent=L)
        self.hud_sys_name = OnscreenText(
            text=s['system'][0], pos=(0.125, -0.115), scale=0.034,
            fg=HUD_CYAN, align=TextNode.ALeft, mayChange=True, parent=L)
        self.hud_sys_status = OnscreenText(
            text=s['status'][0], pos=(0.125, -0.165), scale=0.026,
            fg=HUD_CYAN_DIM, align=TextNode.ALeft, mayChange=True, parent=L)

        # 우상단 — "처치 완료" 카운터 + 구역 확보율 (텍스트만)
        self.hud_kills_lbl = OnscreenText(
            text=s['kills_lbl'][0], pos=(-0.05, -0.10), scale=0.040,
            fg=HUD_CYAN_DIM, align=TextNode.ARight, mayChange=True, parent=R)
        self.hud_kills_num = OnscreenText(
            text='00', pos=(-0.05, -0.205), scale=0.090,
            fg=HUD_WHITE, align=TextNode.ARight, mayChange=True, parent=R)
        self.hud_zone = OnscreenText(
            text='구역 확보 0%', pos=(-0.05, -0.255), scale=0.036,
            fg=HUD_CYAN, align=TextNode.ARight, mayChange=True, parent=R)

        # ── 점수 택티컬 프레임(상단중앙) — 다크 노치 패널 + 양쪽 레드 틱(메뉴 톤).
        #    hud_score 와 함께 show/hide. 점수 텍스트보다 먼저 만들어 뒤에 깔린다.
        self.hud_score_frame = self.aspect2d.attachNewNode('score_frame')
        _tac_fill(self.hud_score_frame, -0.165, 0.165, 0.785, 0.905,
                  (0.055, 0.060, 0.072, 0.55), notch=0.025, corners=('tl', 'br'))
        _tac_outline(self.hud_score_frame, -0.165, 0.165, 0.785, 0.905, TAC_LINE,
                     notch=0.025, corners=('tl', 'br'), thickness=1.3)
        _tac_fill(self.hud_score_frame, -0.205, -0.17, 0.838, 0.852, TAC_ACCENT)
        _tac_fill(self.hud_score_frame, 0.17, 0.205, 0.838, 0.852, TAC_ACCENT)
        self.hud_score_frame.hide()
        # ── PvP 점수(online 전용) — 상단 중앙 "내점수 : 상대점수", 먼저 10점이면 승리.
        # 버서스 규칙: 나 = 레드, 상대 = 콜드 스틸, 콜론 = 흐림. (디자인 ScorePlate)
        self.hud_score = self.aspect2d.attachNewNode('score_grp')
        self.hud_score_colon = OnscreenText(
            text=':', pos=(0, 0.84), scale=0.10,
            fg=TAC_TEXT_3, align=TextNode.ACenter, mayChange=False,
            parent=self.hud_score, font=self._tac_display_font)
        self.hud_score_me = OnscreenText(
            text='0', pos=(-0.03, 0.84), scale=0.10,
            fg=TAC_ACCENT, align=TextNode.ARight, mayChange=True,
            parent=self.hud_score, font=self._tac_display_font)
        self.hud_score_op = OnscreenText(
            text='0', pos=(0.03, 0.84), scale=0.10,
            fg=TAC_STEEL, align=TextNode.ALeft, mayChange=True,
            parent=self.hud_score, font=self._tac_display_font)
        self.hud_score_cap = OnscreenText(
            text='FIRST TO 10', pos=(0, 0.798), scale=0.025,
            fg=TAC_TEXT_2, align=TextNode.ACenter, mayChange=True,
            parent=self.hud_score, font=getattr(self, '_tac_label_font', None))
        self.hud_score.hide()             # online 일 때만 _setup_online 에서 show
        # ── 상대 HP 칩(점수 플레이트 우측) — 이름 + 콜드 스틸 막대. (디자인 OppCompact)
        #    데스매치에서만 표시. HP 는 AI 모드에선 ai_hp 반영, 온라인은 동기화 안 돼 풀.
        self.hud_opp = self.aspect2d.attachNewNode('opp_comp')
        ocx, ocr, ocz, ochh = 0.235, 0.40, 0.838, 0.007
        self._opp_bar_l, self._opp_bar_w = ocx, ocr - ocx
        self.hud_opp_name = OnscreenText(
            text='OPERATOR', pos=(ocx, ocz + 0.022), scale=0.030,
            fg=TAC_STEEL, align=TextNode.ALeft, mayChange=True,
            parent=self.hud_opp, font=getattr(self, '_tac_label_font', None))
        self.hud_opp_track = DirectFrame(
            frameColor=(0.094, 0.102, 0.125, 0.9), relief=DGG.FLAT,
            frameSize=(ocx, ocr, ocz - ochh, ocz + ochh), parent=self.hud_opp)
        self.hud_opp_fill = DirectFrame(
            frameColor=TAC_STEEL, relief=DGG.FLAT,
            frameSize=(ocx, ocr, ocz - ochh, ocz + ochh), parent=self.hud_opp)
        self.hud_opp.hide()
        # 승/패 결과 배너 — 매치 종료 시 화면 중앙에 크게.
        self.hud_match_result = OnscreenText(
            text='', pos=(0, 0.12), scale=0.20,
            fg=TAC_TEXT_1, align=TextNode.ACenter, mayChange=True,
            parent=self.aspect2d, font=self._tac_display_font)
        self.hud_match_result.hide()
        # 라운드 시작 카운트다운 — 화면 중앙 "5..1 / FIGHT!" (스폰 배리어 해제 타이밍).
        self.hud_countdown = OnscreenText(
            text='', pos=(0, 0.30), scale=0.22,
            fg=TAC_ACCENT, align=TextNode.ACenter, mayChange=True,
            parent=self.aspect2d, font=self._tac_display_font)
        self.hud_countdown.hide()

        # ── 킬피드 (우상단) — 발로란트식 한 줄 행이 쌓였다 사라짐. ──────────────
        self._kf_parent = self.a2dTopRight.attachNewNode('killfeed')
        self._kf_rows = []

        # 결과/대기 배경은 가장 마지막에 만들어 다른 HUD 보다 뒤(bin)에 깔리게 하고,
        # 그 위 텍스트는 더 앞 bin 으로 → 어두운 패널 위에 글자가 보인다.
        self.hud_match_result.setBin('fixed', 60)
        # ── 대기방 — 상대 접속 전 어둡게 + 안내문(online 시작 직후). ───────────
        self.hud_wait_bg = DirectFrame(
            frameColor=(0.055, 0.059, 0.071, 0.86), frameSize=(-2, 2, -2, 2),
            parent=self.aspect2d)
        self.hud_wait_bg.setBin('fixed', 50)
        self.hud_wait = OnscreenText(
            text='대기방\n\n다른 플레이어를 기다리는 중...', pos=(0, 0.12),
            scale=0.085, fg=TAC_TEXT_1, align=TextNode.ACenter,
            mayChange=True, parent=self.aspect2d)
        self.hud_wait.setBin('fixed', 60)
        self.hud_wait_bg.hide()
        self.hud_wait.hide()

        # ── 결과창 — 매치 종료 시 승/패 + 킬/데스. (어두운 패널 + 텍스트) ──────
        self.hud_result_bg = DirectFrame(
            frameColor=(0.055, 0.059, 0.071, 0.90), frameSize=(-2, 2, -2, 2),
            parent=self.aspect2d)
        self.hud_result_bg.setBin('fixed', 50)
        self.hud_result = OnscreenText(
            text='', pos=(0, -0.12), scale=0.12,
            fg=TAC_TEXT_1, align=TextNode.ACenter, mayChange=True,
            parent=self.aspect2d)
        self.hud_result.setBin('fixed', 60)
        # 결산 화면 하단 — "N초 후 메인 화면으로" 카운트다운 안내.
        self.hud_result_return = OnscreenText(
            text='', pos=(0, -0.30), scale=0.045,
            fg=TAC_TEXT_2, align=TextNode.ACenter, mayChange=True,
            parent=self.aspect2d, font=getattr(self, '_tac_label_font', None))
        self.hud_result_return.setBin('fixed', 60)
        self.hud_result_bg.hide()
        self.hud_result.hide()
        self.hud_result_return.hide()

        # 우상단 미니맵 — minimap.png (1040×1040, 정사각)
        # 가운데 도트는 별도 DirectFrame (위치/색 갱신용).
        self.hud_map_img = self._hud_img(
            'minimap.png', pos=(-0.15, 0, -0.45),
            scale=(0.10, 1, 0.10), parent=R)
        self.hud_map_lbl = OnscreenText(
            text=s['zone_lbl'][0], pos=(-0.245, -0.345), scale=0.028,
            fg=HUD_CYAN_DIM, align=TextNode.ALeft, mayChange=True, parent=R)
        self.hud_map_dot = DirectFrame(
            frameColor=HUD_CYAN, frameSize=(-0.006, 0.006, -0.006, 0.006),
            pos=(-0.15, 0, -0.45), parent=R)

        # 좌하단 — 코어 무결성 ("체력"). core-bar.png (2400×440 ≈ 5.45:1).
        # 채움 동적: PNG 의 베이크된 cyan fill 우측에 어두운 cover 사각형을 덮어,
        # left X 를 hp_ratio 에 따라 이동 → 100% 일 때 PNG 의 원본 fill 노출, 0% 면 전부 가림.
        self.hud_integ_lbl = OnscreenText(
            text=s['integ_lbl'][0], pos=(0.05, 0.215), scale=0.036,
            fg=HUD_CYAN_DIM, align=TextNode.ALeft, mayChange=True, parent=BL)
        self.hud_integ_img = self._hud_img(
            'core-bar.png', pos=(0.325, 0, 0.150),
            scale=(0.275, 1, 0.0504), parent=BL)
        # 바 좌표 — pos x ± scale x. baked PNG cyan fill 정규화 0.125 ~ 0.708,
        # 그 우측 rail (tick) 은 정규화 0.708 ~ 0.96 — 100% HP 일 때 cyan 확장이 채움.
        bar_left, bar_w = 0.050, 0.550
        self._integ_baked_x0 = bar_left + bar_w * 0.125     # 0.119
        self._integ_baked_x1 = bar_left + bar_w * 0.708     # 0.439
        self._integ_ext_x1   = bar_left + bar_w * 0.960     # 0.578 (end-cap 안쪽)
        self._integ_zhi      = 0.018                         # cover/ext z 반폭
        zhi = self._integ_zhi
        bx1 = self._integ_baked_x1
        # 어두운 cover — HP < 68% 일 때만 baked fill 을 우측부터 가림.
        self.hud_integ_cover = DirectFrame(
            frameColor=HUD_PANEL,
            frameSize=(bx1, bx1, -zhi, zhi),
            pos=(0, 0, 0.150), parent=BL)
        # cyan 확장 — HP > 68% 일 때 baked 우측의 rail 영역을 채워 풀바 연출.
        self.hud_integ_ext = DirectFrame(
            frameColor=HUD_CYAN,
            frameSize=(bx1, bx1, -zhi, zhi),
            pos=(0, 0, 0.150), parent=BL)
        self.hud_integ_num = OnscreenText(
            text='100%', pos=(0.05, 0.075), scale=0.040,
            fg=HUD_CYAN, align=TextNode.ALeft, mayChange=True, parent=BL)
        # 체력바는 일단 시각적으로 숨김 — core_integrity 데이터는 유지 (데미지 로직용).
        # 다시 켜고 싶으면 아래 4 줄 제거.
        self.hud_integ_lbl.hide()
        self.hud_integ_img.hide()
        self.hud_integ_cover.hide()
        self.hud_integ_ext.hide()
        self.hud_integ_num.hide()

        # ── 플레이어 체력바 — 항상 표시. 숨긴 코어바(BL 컨테이너)와 독립적으로
        # a2dBottomLeft 코너에 단순 track+fill 로. core_integrity 를 매 프레임 반영.
        php_w, php_h = 0.52, 0.024
        php_x, php_z = 0.10, 0.13
        self._php_w, self._php_h = php_w, php_h
        self._php_x, self._php_z = php_x, php_z
        # 체력 택티컬 플레이트 — 다크 노치 패널 + 좌측 레드 바 + 라인 (메뉴 디자인 톤)
        self._health_plate = self.a2dBottomLeft.attachNewNode('health_plate')
        _tac_fill(self._health_plate, 0.035, 0.665, 0.085, 0.235,
                  (0.055, 0.060, 0.072, 0.50), notch=0.03, corners=('tl', 'br'))
        _tac_outline(self._health_plate, 0.035, 0.665, 0.085, 0.235, TAC_LINE,
                     notch=0.03, corners=('tl', 'br'), thickness=1.3)
        _tac_fill(self._health_plate, 0.035, 0.051, 0.10, 0.22, TAC_ACCENT)
        # 레이어 순서를 '씬그래프 순서'로 확정 — setBin draw_order 가 이 DirectFrame
        # 들에선 신뢰가 안 돼(반투명/불투명 자동 bin 분류로 트랙이 fill 위로 올라옴),
        # ghost·fill 을 track 의 '자식'으로 둔다. 같은 bin 내 자식은 부모 뒤에(=위에)
        # 그려지므로 track → ghost → fill 순서가 보장된다(회색 트랙 위로 vital 이 또렷).
        self.php_track = DirectFrame(
            frameColor=(0.094, 0.102, 0.125, 1.0),      # #181A20 톤 트랙(불투명)
            frameSize=(-0.006, php_w + 0.006, -php_h - 0.006, php_h + 0.006),
            pos=(php_x, 0, php_z), parent=self.a2dBottomLeft)
        # 고스트(지연) 바 — 방금 잃은 체력 구간을 레드로 남겼다 천천히 줄어듦(잔상).
        self.php_ghost = DirectFrame(
            frameColor=TAC_ACCENT,
            frameSize=(0, php_w, -php_h, php_h),
            pos=(0, 0, 0), parent=self.php_track)        # track 자식 → track 위
        self._php_ghost_r = 1.0
        self.php_fill = DirectFrame(
            frameColor=(0.92, 0.93, 0.94, 1.0),         # 불투명 흰색(감소 시 레드로)
            frameSize=(0, php_w, -php_h, php_h),
            pos=(0, 0, 0), parent=self.php_track)        # ghost 뒤에 생성 → 맨 위
        # 바 위쪽 행: VITALS 라벨(좌) + 숫자(우). 디자인 .health .hrow.
        # 반투명 플레이트 패널이 텍스트 위로 올라와 흐려 보이던 문제 → fill 과 똑같이
        # php_track 자식으로 둬서 패널보다 위에 그린다(pos 는 track 원점 기준 상대).
        self.hud_vitals_lbl = OnscreenText(
            text='V I T A L S', pos=(0, 0.050), scale=0.030,
            fg=TAC_TEXT_2, align=TextNode.ALeft, mayChange=False,
            parent=self.php_track,
            font=getattr(self, '_tac_label_font', None))
        self.php_num = OnscreenText(
            text='100', pos=(php_w, 0.044), scale=0.072,
            fg=TAC_TEXT_1, align=TextNode.ARight, mayChange=True,
            parent=self.php_track, font=getattr(self, '_tac_display_font', None))
        # 바 위 눈금(tick) — 25/50/75% 자리에 얇은 어두운 선. (디자인 .hbar .tick)
        for f in (0.25, 0.5, 0.75):
            tx = php_x + php_w * f
            tk = _tac_fill(self._health_plate, tx - 0.0014, tx + 0.0014,
                           php_z - php_h, php_z + php_h, (0.055, 0.060, 0.072, 0.92))
            tk.setBin('fixed', 22)
        # LOW 배지 — 체력 30% 이하일 때 VITALS 옆에 레드 칩. (디자인 .low-tag)
        self.hud_low_bg = _tac_fill(self._health_plate, 0.305, 0.40,
                                    php_z + 0.036, php_z + 0.074, TAC_ACCENT)
        self.hud_low_tag = OnscreenText(
            text='LOW', pos=(0.3525, php_z + 0.0445), scale=0.026,
            fg=(0.055, 0.060, 0.072, 1.0), align=TextNode.ACenter, mayChange=False,
            parent=self._health_plate, font=getattr(self, '_tac_label_font', None))
        self.hud_low_bg.setBin('fixed', 22)
        self.hud_low_tag.setBin('fixed', 23)
        self.hud_low_bg.hide()
        self.hud_low_tag.hide()

        # 우하단 — 탄약 카운터. 라벨("처치 카트리지")·카트리지 아이콘 UI 제거하고
        # "현재/최대" 숫자(예: 3/8, 7/25)만 표시. 재장전 중엔 위에 "reloading...".
        # 탄약 택티컬 플레이트 — 다크 노치 패널 + 우측 레드 바 + 라인 (메뉴 디자인 톤)
        self._ammo_plate = BR.attachNewNode('ammo_plate')
        _tac_fill(self._ammo_plate, -0.40, -0.005, 0.045, 0.40,
                  (0.055, 0.060, 0.072, 0.50), notch=0.05, corners=('tl', 'br'))
        _tac_outline(self._ammo_plate, -0.40, -0.005, 0.045, 0.40, TAC_LINE,
                     notch=0.05, corners=('tl', 'br'), thickness=1.3)
        _tac_fill(self._ammo_plate, -0.022, -0.005, 0.07, 0.30, TAC_ACCENT)
        # 디자인 .ammo — 무기 라벨(위) + 큰 현재탄(Oswald) + 작은 최대탄(흐림).
        # 세로 밴드로 또렷이 분리: (위) 실루엣 → 무기 라벨(z0.255) → 큰 현재탄(z0.10,
        # 작게) + 최대탄 → 탄창 스트립 → 재장전 바. 큰 숫자가 라벨·실루엣과 안 겹치게.
        self.hud_weapon_lbl = OnscreenText(
            text='P I S T O L', pos=(-0.05, 0.255), scale=0.034,
            fg=TAC_TEXT_2, align=TextNode.ARight, mayChange=True, parent=BR,
            font=self._tac_label_font)
        self.hud_ammo_max = OnscreenText(
            text='/ 8', pos=(-0.05, 0.10), scale=0.058,
            fg=TAC_TEXT_3, align=TextNode.ARight, mayChange=True, parent=BR,
            font=self._tac_display_font)
        self.hud_ammo_num = OnscreenText(
            text='08', pos=(-0.16, 0.10), scale=0.135,
            fg=TAC_TEXT_1, align=TextNode.ARight, mayChange=True, parent=BR,
            font=self._tac_display_font)
        # RELOADING — 라벨과 같은 행(z0.255). 재장전 중엔 무기 라벨 대신 이게 뜬다
        # (실루엣과 겹치지 않게 라벨 자리로). _update_hud 에서 상호 토글.
        self.hud_reload_text = OnscreenText(
            text='RELOADING', pos=(-0.05, 0.255), scale=0.034,
            fg=TAC_ACCENT, align=TextNode.ARight, mayChange=False, parent=BR,
            font=self._tac_label_font)
        self.hud_reload_text.hide()
        # 재장전 진행 게이지 — 탄창 스트립 바로 아래(빈 하단 레인)에 얇은 레드 바가
        # 좌→우로 채워짐. (디자인 .reloadg) 무기 실루엣과 안 겹치게 하단 배치.
        # 재장전 중에만 표시. 진행도는 _update_hud 에서 갱신.
        rg_l, rg_r, rg_z, rg_hh = -0.360, -0.045, 0.054, 0.005
        self._rg_l, self._rg_w = rg_l, rg_r - rg_l
        self.hud_reload_track = DirectFrame(
            frameColor=TAC_LINE,
            frameSize=(rg_l, rg_r, rg_z - rg_hh, rg_z + rg_hh), parent=BR)
        self.hud_reload_track.setBin('fixed', 22)
        self.hud_reload_fill = DirectFrame(
            frameColor=TAC_ACCENT,
            frameSize=(rg_l, rg_l, rg_z - rg_hh, rg_z + rg_hh), parent=BR)
        self.hud_reload_fill.setBin('fixed', 23)
        self.hud_reload_track.hide()
        self.hud_reload_fill.hide()
        # 무기 레일 탭(플레이트 위) — "1 PISTOL" / "2 RIFLE", 현재 무기 = 좌측 레드 바 + 강조.
        # _ammo_plate 자식이라 인게임 HUD show/hide 에 같이 따라간다. (디자인 .wrail)
        self._wtabs = {}
        order = [w for w in ('pistol', 'rifle') if w in self._weapons]
        if not order:
            order = list(self._weapons.keys()) or ['pistol']
        keymap = {'pistol': '1', 'rifle': '2'}
        tab_w, tab_gap, tab_b, tab_t = 0.188, 0.014, 0.415, 0.475
        group_l = -0.005 - (len(order) * tab_w + (len(order) - 1) * tab_gap)
        for idx, w in enumerate(order):
            tl = group_l + idx * (tab_w + tab_gap)
            self._wtabs[w] = self._build_weapon_tab(
                self._ammo_plate, tl, tl + tab_w, tab_b, tab_t,
                keymap.get(w, '?'), w.upper())
        # 탄창 스트립 — 플레이트 하단, 남은 탄을 작은 세그먼트로. (디자인 .magstrip)
        self._mag_strip = self._ammo_plate.attachNewNode('mag_strip')
        self._mag_segs = []
        self._mag_built_max = 0
        self._rebuild_mag_strip(getattr(self, 'ammo_max', 8))
        # 무기 실루엣(플레이트 상단 우측) — 무기마다 하나씩 만들어 두고 현재 것만 show.
        self._wsils = {}
        for w in order:
            wid = 0.165 if w == 'rifle' else 0.14
            sil = self._build_weapon_sil(self._ammo_plate, w,
                                         right_x=-0.04, top_z=0.39, width=wid)
            if sil is not None:
                sil.hide()
                self._wsils[w] = sil

        # 무기 교체 시 우하단 패널 전체가 살짝 내려갔다 올라오는 슬라이드(디자인
        # silStyle clip-out/in)를 한 번에 주려면 패널 요소가 한 노드 아래 모여 있어야
        # 한다. BR 직속이던 탄약 텍스트·재장전 바를 _ammo_plate(원점 (0,0,0)) 자식으로
        # 옮긴다 — pos 는 BR 기준 = 패널 기준이라 보이는 위치는 그대로 유지된다.
        for _w in (self.hud_weapon_lbl, self.hud_ammo_max, self.hud_ammo_num,
                   self.hud_reload_text, self.hud_reload_track,
                   self.hud_reload_fill):
            _w.reparentTo(self._ammo_plate)
        self._ammo_plate_z0 = 0.0
        self._ammo_slide = None

        # 중앙 상단 — 적 타겟 정보 그룹 (enemy.png 1600×1040 ≈ 1.54:1, 평소 hidden).
        # 컨테이너 NodePath 아래에 PNG + 2줄 텍스트 묶음 → enemy_target.show/hide 한 번에 처리.
        self.enemy_target = self.aspect2d.attachNewNode('enemy_target_grp')
        self.enemy_target.setScale(HUD_SCALE)
        self.enemy_target.hide()
        self.enemy_target_img = self._hud_img(
            'enemy.png', pos=(0, 0, 0.42),
            scale=(0.20, 1, 0.130), parent=self.enemy_target)
        self.enemy_target_l1 = OnscreenText(
            text='', pos=(0, 0.44), scale=0.034,
            fg=HUD_ENEMY, align=TextNode.ACenter, mayChange=True,
            parent=self.enemy_target)
        self.enemy_target_l2 = OnscreenText(
            text='', pos=(0, 0.39), scale=0.040,
            fg=(1.0, 0.56, 0.63, 1.0), align=TextNode.ACenter, mayChange=True,
            parent=self.enemy_target)

        # 하단 중앙 — F 상호작용 프롬프트 그룹 (keycap.png 600×600, 평소 hidden).
        # 컨테이너에 HUD_SCALE 를 걸고, 자식 pos 는 1/HUD_SCALE 로 미리 나눠 둬서
        # 스케일 후 최종 위치가 원래 디자인 위치(하단 중앙)에 그대로 오게 한다.
        self.interact_frame = self.aspect2d.attachNewNode('interact_grp')
        self.interact_frame.setScale(HUD_SCALE)
        self.interact_frame.hide()
        self.interact_keycap = self._hud_img(
            'keycap.png', pos=(-0.10, 0, -0.3875),
            scale=(0.035, 1, 0.035), parent=self.interact_frame)
        self.interact_f = OnscreenText(
            text='F', pos=(-0.10, -0.3956), scale=0.038,
            fg=HUD_CYAN, align=TextNode.ACenter, mayChange=True,
            parent=self.interact_frame)
        self.interact_text = OnscreenText(
            text=s['interact'][0], pos=(-0.0625, -0.3956), scale=0.040,
            fg=HUD_CYAN, align=TextNode.ALeft, mayChange=True,
            parent=self.interact_frame)

        # 중앙 — 게이트 / 리빌 메시지 (잠깐 떴다 사라짐)
        self.gate_msg = OnscreenText(
            text='', pos=(0, -0.5), scale=0.060 * HUD_SCALE,
            fg=HUD_CYAN, align=TextNode.ACenter, mayChange=True,
            parent=self.aspect2d)
        self.gate_msg.hide()

        # 좌상단 하단부 — 개발자 디버그 오버레이 (F3 토글, 평소 hidden)
        self.debug_text = OnscreenText(
            text='', pos=(0.05, -0.30), scale=0.034,
            fg=(0.45, 0.68, 0.62, 1.0), bg=(0, 0, 0, 0.45),
            align=TextNode.ALeft, mayChange=True, parent=L)
        self.debug_text.hide()
        self._debug_on = False

        # 글리치 때 (텍스트, 색)을 바꿀 위젯 묶음.
        self._glitch_widgets = [
            (self.hud_sys_name,  'system',    HUD_CYAN),
            (self.hud_sys_status,'status',    HUD_CYAN_DIM),
            (self.hud_kills_lbl, 'kills_lbl', HUD_CYAN_DIM),
            (self.hud_integ_lbl, 'integ_lbl', HUD_CYAN_DIM),
            (self.hud_map_lbl,   'zone_lbl',  HUD_CYAN_DIM),
        ]

        # 미니멀 HUD — 탄약(BR)·조준점·일시정지만 남기고 나머지 코너 UI 전부 숨김.
        #   L  = 좌상단 시스템 배너 + 디버그
        #   R  = 우상단 킬 카운터 + 미니맵
        #   BL = 좌하단 코어 무결성(체력) 바
        # (BR = 탄약 카운터는 유지)
        L.hide()
        R.hide()
        BL.hide()

    def _set_glitch(self, on):
        """on=True → 빨강 강조, False → 기본 시안. HUD 전반에 적용.
        모든 시안 PNG 는 _hud_images 일괄 setColorScale 로 빨강 틴트 처리 (PNG 교체 없음)."""
        cyan_set = (self.hud_kills_num, self.hud_integ_num, self.hud_zone,
                    self.interact_text, self.interact_f)
        for w, key, base in self._glitch_widgets:
            txt, fg = GLITCH_LABELS[key][1 if on else 0], (HUD_RED_DIM if on else base)
            if key in ('system',):
                fg = HUD_RED if on else HUD_CYAN
            w.setText(txt)
            w.setFg(fg)
        accent = HUD_RED if on else HUD_CYAN
        for w in cyan_set:
            w.setFg(accent if w is not self.hud_kills_num else
                    (HUD_RED if on else HUD_WHITE))
        self.hud_map_dot['frameColor'] = accent
        # 시안 PNG → 빨강 틴트 (시안 픽셀이 setColorScale 곱셈 후 클램프되어 빨강이 됨)
        tint = HUD_TINT_RED if on else HUD_TINT_CYAN
        for img in self._hud_images:
            img.setColorScale(*tint)
        # 크로스헤어/히트마커도 동일 — 단 적 조준 시엔 글리치와 무관하게 빨강 유지
        ch_tint = HUD_TINT_RED if (on or self._ch_alert) else HUD_TINT_CYAN
        self.crosshair.setColorScale(*ch_tint)
        self.hitmarker.setColorScale(*tint)

    def _trigger_glitch(self, dur=0.18):
        """글리치 한 번. 웨이브가 올라갈수록 자주 불리도록 update 에서 호출.
        GLITCH_ENABLED=False 면 no-op — HUD 가 시안 표면 상태에 머문다."""
        if not GLITCH_ENABLED:
            return
        self._glitch_t = dur
        self._set_glitch(True)

    def _toggle_debug(self):
        self._debug_on = not self._debug_on
        if self._debug_on:
            self.debug_text.show()
        else:
            self.debug_text.hide()

    def _update_hud(self, dt):
        glitching = self._glitch_t > 0

        # 탄약 — 큰 현재탄 + 작은 최대탄. 0발이면 EMPTY (R) 레드 점멸. 무기명 갱신.
        # 단, 재장전 중엔 EMPTY 를 띄우지 않는다 — 'EMPTY'(5글자)가 숫자보다 넓어
        # 무기 라벨/실루엣과 겹쳐 보였다. 재장전 중엔 '00'(채워지는 중)으로 표시.
        if self.ammo == 0 and not self._reload_oneshot:
            ft = ClockObject.getGlobalClock().getFrameTime()
            # 'EMPTY'(5글자)는 숫자(2글자)용 큰 스케일로 그리면 플레이트를 벗어난다.
            # 상태 진입 시 한 번만 작은 스케일로 낮춰 "(R)" 와 한 줄에 들어오게.
            if not getattr(self, '_ammo_empty_shown', False):
                self.hud_ammo_num.setScale(0.052)
                self._ammo_empty_shown = True
            self.hud_ammo_num.setText('EMPTY')
            self.hud_ammo_num.setFg(TAC_ACCENT if int(ft * 3) % 2 == 0
                                    else TAC_ACCENT_DIM)
            self.hud_ammo_max.setText('(R)')
            self.hud_ammo_max.setFg(TAC_ACCENT_DIM)
        else:
            if getattr(self, '_ammo_empty_shown', False):
                self.hud_ammo_num.setScale(0.135)   # 숫자 표시 — 원래 큰 스케일 복원
                self._ammo_empty_shown = False
            low = self.ammo <= max(1, self.ammo_max // 4)
            self.hud_ammo_num.setText(f'{self.ammo:02d}')
            self.hud_ammo_num.setFg(TAC_ACCENT if low else TAC_TEXT_1)
            self.hud_ammo_max.setText(f'/ {self.ammo_max}')
            self.hud_ammo_max.setFg(TAC_TEXT_3)
        # 구경 캡션 — "PISTOL · 9MM" / "RIFLE · AR-10". (디자인 .wname)
        cur_w = self.weapon_name or 'pistol'
        self.hud_weapon_lbl.setText(
            {'pistol': 'PISTOL · 9MM', 'rifle': 'RIFLE · AR-10'}.get(
                cur_w, cur_w.upper()))
        # 무기 레일 탭 — 현재 무기 강조(레드 바 + 밝은 면/글자), 나머지는 흐림.
        for nm, tab in getattr(self, '_wtabs', {}).items():
            active = (nm == cur_w)
            tab['bar'].setColor(*(TAC_ACCENT if active else (0, 0, 0, 0)))
            tab['name'].setFg(TAC_TEXT_1 if active else TAC_TEXT_2)
            tab['fill'].setColor(*((0.13, 0.14, 0.17, 0.62) if active
                                   else (0.055, 0.060, 0.072, 0.50)))
        # 탄창 스트립 — ammo_max 변동 시 재생성, 매 프레임 채움 색만 갱신.
        if getattr(self, '_mag_built_max', 0) != self.ammo_max:
            self._rebuild_mag_strip(self.ammo_max)
        for i, seg in enumerate(self._mag_segs):
            seg.setColor(*(TAC_TEXT_1 if i < self.ammo else TAC_LINE))
        # 무기 실루엣 — 현재 무기 표시 + 교체 시 슬라이드 스왑(파일 꺼내듯: 이전 건
        # 아래로 빠지며 사라지고, 새 건 위에서 미끄러져 안착).
        sils = getattr(self, '_wsils', {})
        # _hud_prev_w 는 트리거 안에서만 기록하므로 getattr 기본값을 cur_w 로 두면
        # prev_w 가 영영 cur_w 와 같아져 스왑이 절대 감지되지 않는다 → 기본 None,
        # 최초 1회는 애니 없이 기록만, 이후 실제 변경에서만 슬라이드/실루엣 스왑.
        prev_w = getattr(self, '_hud_prev_w', None)
        if prev_w is None:
            self._hud_prev_w = cur_w
        elif cur_w != prev_w:
            self._hud_swap_t = self.HUD_SWAP_DUR
            self._hud_swap_from = prev_w
            self._hud_prev_w = cur_w
            self._start_ammo_panel_slide()
        swt = getattr(self, '_hud_swap_t', 0.0)
        if swt > 0.0 and sils:
            swt = max(0.0, swt - dt)
            self._hud_swap_t = swt
            p = 1.0 - swt / self.HUD_SWAP_DUR            # 0→1 진행
            frm = getattr(self, '_hud_swap_from', None)
            for w, sil in sils.items():
                if w == cur_w:                          # 새 무기 — 후반에 위에서 안착
                    if p < 0.5:
                        sil.hide()
                    else:
                        q = (p - 0.5) / 0.5
                        sil.show(); sil.setZ(0.05 * (1.0 - q))
                        sil.setColorScale(1, 1, 1, q)
                elif w == frm:                          # 이전 무기 — 전반에 아래로 빠짐
                    if p < 0.5:
                        q = p / 0.5
                        sil.show(); sil.setZ(-0.05 * q)
                        sil.setColorScale(1, 1, 1, 1.0 - q)
                    else:
                        sil.hide()
                else:
                    sil.hide()
        else:
            for w, sil in sils.items():
                if w == cur_w:
                    sil.show(); sil.setZ(0); sil.setColorScale(1, 1, 1, 1)
                else:
                    sil.hide()
        # 재장전 중 "reloading..." + 진행 게이지(좌→우 채움) 표시.
        if self._reload_oneshot:
            self.hud_weapon_lbl.hide()        # 라벨 자리에 RELOADING 표시(상호 배타)
            self.hud_reload_text.show()
            self.hud_reload_track.show()
            self.hud_reload_fill.show()
            ft = ClockObject.getGlobalClock().getFrameTime()
            total = getattr(self, '_reload_total', 0.0) or 0.05
            p = max(0.0, min(1.0,
                             (ft - getattr(self, '_reload_started', ft)) / total))
            z0, z1 = self.hud_reload_fill['frameSize'][2:4]
            self.hud_reload_fill['frameSize'] = (
                self._rg_l, self._rg_l + self._rg_w * p, z0, z1)
        else:
            self.hud_weapon_lbl.show()
            self.hud_reload_text.hide()
            self.hud_reload_track.hide()
            self.hud_reload_fill.hide()

        # 코어 무결성 — 두 단계 채움.
        #   HP 68 ~ 100 : baked PNG fill 은 그대로 + cyan 확장이 rail 영역 채움 (풀바)
        #   HP  0 ~  68 : 확장 0, 어두운 cover 가 baked fill 을 우측부터 가림
        r = max(0.0, self.core_integrity / self.core_integrity_max)
        thr = 0.68
        zhi = self._integ_zhi
        bx0 = self._integ_baked_x0
        bx1 = self._integ_baked_x1
        ex1 = self._integ_ext_x1
        if r >= thr:
            cover_left = bx1                                      # cover 0폭
            ext_right  = bx1 + (ex1 - bx1) * (r - thr) / (1 - thr)
        else:
            cover_left = bx0 + (bx1 - bx0) * (r / thr)
            ext_right  = bx1                                      # 확장 0폭
        self.hud_integ_cover['frameSize'] = (cover_left, bx1, -zhi, zhi)
        self.hud_integ_ext['frameSize']   = (bx1, ext_right, -zhi, zhi)
        self.hud_integ_num.setText(f'{int(round(self.core_integrity))}%')

        # 플레이어 체력바 — 너비 = 체력 비율, 색 = 흰색(만땅)→레드(위험).
        self.php_fill['frameSize'] = (0, self._php_w * r, -self._php_h, self._php_h)
        self.php_fill['frameColor'] = (0.90, 0.25 + 0.68 * r,
                                       0.22 + 0.72 * r, 1.0)   # 불투명 — 회색 비침 방지
        # 고스트 바 — 회복 시 즉시 따라붙고, 감소 시 천천히 따라 내려옴(레드 잔상).
        gr = getattr(self, '_php_ghost_r', r)
        gr = r if r >= gr else gr + (r - gr) * min(1.0, dt * 3.2)
        self._php_ghost_r = gr
        self.php_ghost['frameSize'] = (0, self._php_w * gr,
                                       -self._php_h, self._php_h)
        # 화면 가장자리 비네트 — 피격 플래시 + 저체력 상시.
        self._update_vignette(dt, r)
        self.php_num.setText(str(int(round(self.core_integrity))))
        low_hp = r < 0.3
        self.php_num.setFg(TAC_ACCENT if low_hp else TAC_TEXT_1)
        # LOW 배지 — 체력 30% 이하에서만 표시.
        if low_hp:
            self.hud_low_bg.show()
            self.hud_low_tag.show()
        else:
            self.hud_low_bg.hide()
            self.hud_low_tag.hide()

        # 상대 HP 칩 — 데스매치에서만. AI 모드는 ai_hp 반영, 온라인은 동기화 없어 풀.
        if self._deathmatch_active():
            if self.hud_opp.isHidden():
                self.hud_opp.show()
            nm = (self._remote_name or 'OPERATOR') if self.online_mode else 'OPERATOR'
            self.hud_opp_name.setText(nm.upper())
            if self.ai_mode and not self.online_mode:
                oratio = max(0.0, min(1.0, self.ai_hp / max(1, self.ai_max_hp)))
            else:
                oratio = 1.0
            ol, ow = self._opp_bar_l, self._opp_bar_w
            fs = self.hud_opp_track['frameSize']
            self.hud_opp_fill['frameSize'] = (ol, ol + ow * oratio, fs[2], fs[3])
            self.hud_opp_fill['frameColor'] = (TAC_ACCENT if oratio <= 0.3
                                               else TAC_STEEL)
        elif not self.hud_opp.isHidden():
            self.hud_opp.hide()

        # 웨이브 모드 HUD — 총 처치 수 + 현재 웨이브/남은 적
        alive = sum(1 for z in self.zombies if z.hp > 0)
        self.hud_kills_num.setText(f'{self.kills:02d}')
        if self.online_mode:
            self.hud_zone.setText('')   # 멀티: "WAVE N 남은 적" 표시 제거
        elif self.wave_active:
            self.hud_zone.setText(f'WAVE {self.wave}  남은 적 {alive}')
        elif self.wave >= 1:
            self.hud_zone.setText(f'WAVE {self.wave + 1} 준비…')
        else:
            self.hud_zone.setText('WAVE 시작 대기…')

        # 히트마커 타이머 — pulse 종료 시 hide.
        if self._hitmarker_t > 0:
            self._hitmarker_t -= dt
            if self._hitmarker_t <= 0:
                self.hitmarker.hide()
        # 발로란트식 크로스헤어 spread/색 갱신.
        self._update_crosshair(dt)
        # 킬피드 행 수명/페이드.
        self._update_killfeed(dt)
        # 데미지 플래시(하얀 네모) 애니메이션.
        self._update_dmg_flash(dt)

        # 정면 적 타겟 정보
        self._update_enemy_target()

        # 글리치 타이머 — 라운드가 올라갈수록 자주 터진다
        if self._glitch_t > 0:
            self._glitch_t -= dt
            if self._glitch_t <= 0:
                self._set_glitch(False)
        else:
            # 웨이브가 올라갈수록 글리치가 잦아지게.
            spread = min(1.0, max(0, self.wave - 1) / 12.0)
            self._glitch_cooldown -= dt
            if self._glitch_cooldown <= 0:
                self._trigger_glitch(0.12 + 0.10 * spread)
                lo = max(1.5, 9.0 - 7.0 * spread)
                self._glitch_cooldown = random.uniform(lo, lo + 3.0)

        # 개발자 디버그 오버레이 (F3)
        if self._debug_on:
            fps = ClockObject.getGlobalClock().getAverageFrameRate()
            self.debug_text.setText(
                f'[F3 debug]\n'
                f'anim: {self.current_anim}'
                f'{" +shoot" if self._hands_oneshot else ""}'
                f'{" +reload" if self._reload_oneshot else ""}\n'
                f'ammo: {self.ammo}/{self.ammo_max}\n'
                f'fps:  {fps:.0f}\n'
                f'pos:  ({self.player_pos.x:.1f}, {self.player_pos.y:.1f}, '
                f'{self.player_pos.z:.1f})\n'
                f'mode: {"editor[F2]" if self.editor_mode else "fps"}'
                f'{"  kneel" if self.kneel_state == "kneel" else ""}'
                f'{"  ADS" if self.aim_t > 0.5 else ""}'
            )

    def _update_enemy_target(self):
        # 미니멀 HUD — 적 타겟 정보 패널 제거 (항상 숨김).
        self.enemy_target.hide()
        return
        from math import radians, sin, cos
        fx = -sin(radians(self.player_yaw))
        fy = cos(radians(self.player_yaw))
        best, best_d = None, 12.0
        for i, z in enumerate(self.zombies):
            if z.state == Zombie.DEAD or z.transformed or z.transform_t > 0:
                continue
            dx = z.pos.x - self.player_pos.x
            dy = z.pos.y - self.player_pos.y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < 0.3 or dist >= best_d:
                continue
            if (dx * fx + dy * fy) / dist < 0.95:     # 정면 ±18° 밖
                continue
            best, best_d = (i, z), dist
        if best is None:
            self.enemy_target.hide()
            return
        i, z = best
        hp_max = getattr(z, 'hp_max', 100) or 100
        infect = int(round(max(0.0, z.hp / hp_max) * 100))
        if self._glitch_t > 0:
            self.enemy_target_l1.setText(f'대상 · #K-{i:02d}')
            self.enemy_target_l2.setText(f'체력 {infect}%')
        else:
            self.enemy_target_l1.setText(f'대상 식별 · #K-{i:02d}')
            self.enemy_target_l2.setText(f'체력 {infect}%')
        self.enemy_target.show()

    def _toggle_fullscreen(self):
        """F11 — 진짜 전체화면 토글. 전체화면이면 디스플레이 해상도로 채워
        Windows 작업표시줄(언더바)까지 가림. 창 모드 복귀는 1280×720."""
        self._is_fullscreen = not self._is_fullscreen
        props = WindowProperties()
        if self._is_fullscreen:
            props.setFullscreen(True)
            props.setSize(self.pipe.getDisplayWidth(),
                          self.pipe.getDisplayHeight())
        else:
            props.setFullscreen(False)
            props.setSize(1280, 720)
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_confined)
        self.win.requestProperties(props)

    def windowEvent(self, win):
        # 창 크기 변경(전체화면 토글 등) 시 마우스 재중심 좌표 갱신.
        super().windowEvent(win)
        if win is self.win:
            self._win_cx = self.win.getXSize() // 2
            self._win_cy = self.win.getYSize() // 2

    def _toggle_pause(self):
        self.paused = not self.paused
        props = WindowProperties()
        clock = ClockObject.getGlobalClock()
        if self.paused:
            # 시간 정지 — MSlave 에선 main loop 의 tick() 이 frame_time 을 안 흘려서
            # Actor loop anim / doMethodLater / dt 기반 update 모두 자동 멈춤.
            # (참고: setDt(0) 는 Panda3D 가 assert 로 거부함 — MSlave 면 setDt 불필요.)
            clock.setMode(ClockObject.MSlave)
            self.pause_frame.show()
            self._animate_pause_in()        # 페이드+슬라이드 스태거 등장
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)
        else:
            # 재개 — MNormal 복귀. 첫 프레임 dt 폭발은 _update 의 cap (≤0.1) 이 잡음.
            clock.setMode(ClockObject.MNormal)
            self._animate_pause_out()    # 열기 역재생 페이드아웃 후 hide
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_confined)
            self.win.requestProperties(props)
            self.win.movePointer(0, self._win_cx, self._win_cy)
            self._first_frame = True

    # --- debug --------------------------------------------------------------

    def _dump_joints(self, task):
        names = [j.getName() for j in self.ybot.getJoints()]
        print(f'[joint] count={len(names)}', flush=True)
        print(f'[joint] first 10: {names[:10]}', flush=True)
        wanted = ('Hips', 'Spine', 'Head', 'LeftHand', 'RightHand', 'LeftFoot', 'RightFoot')
        for tag in wanted:
            m = next((n for n in names if n.endswith(tag)), None)
            if not m:
                print(f'[joint] {tag}: not found', flush=True)
                continue
            # 본이 어느 subpart 에 속하는지 모르니 순서대로 시도.
            for part in self._parts:
                try:
                    j = self.ybot.exposeJoint(None, part, m)
                    if j is None or j.isEmpty():
                        continue
                    p = j.getPos(self.ybot)
                    print(f'[joint] {tag} [{part}] ({m}): '
                          f'({p.x:.2f}, {p.y:.2f}, {p.z:.2f})', flush=True)
                    break
                except Exception:
                    continue
        return Task.done

    # --- 온라인(1:1 멀티) -----------------------------------------------------
    # 1단계: 두 플레이어가 서로 보이고 움직임이 동기화되는 것만. 사격/피격/라운드/
    # 점수/리스폰 없음. 모든 메서드는 online_mode 일 때만 호출된다.

    def _build_lobby_ui(self):
        """준비방 UI(인게임 온라인) — 발로란트풍 택티컬. 좌=나 / 우=상대 슬롯 카드 +
        VS + READY UP 버튼. 상대 이름/준비 상태는 _update_lobby 가 매 프레임 갱신."""
        self._tac_fonts()
        root = DirectFrame(frameColor=(0.043, 0.047, 0.055, 0.96),
                           frameSize=(-2, 2, -1, 1), parent=self.aspect2d)
        root.setBin('fixed', 55)
        self.lobby_root = root
        # 캡션 + 타이틀
        _tac_fill(root, -0.205, -0.145, 0.516, 0.524, TAC_ACCENT)
        _tac_fill(root, 0.145, 0.205, 0.516, 0.524, TAC_ACCENT)
        OnscreenText(text='MATCH LOBBY', pos=(0, 0.508), scale=0.026,
                     fg=TAC_TEXT_2, align=TextNode.ACenter, mayChange=False,
                     parent=root, font=self._tac_label_font)
        OnscreenText(text='STANDBY', pos=(0, 0.37), scale=0.125, fg=TAC_TEXT_1,
                     align=TextNode.ACenter, mayChange=False, parent=root,
                     font=self._tac_hero_font)
        OnscreenText(text='VS', pos=(0, 0.075), scale=0.058, fg=TAC_TEXT_3,
                     align=TextNode.ACenter, mayChange=False, parent=root,
                     font=self._tac_display_font)

        def _slot(lx, rx, me, tag, who, name):
            line = TAC_ACCENT_DIM if me else TAC_LINE
            _tac_fill(root, lx, rx, -0.10, 0.30, TAC_BG_SURF, notch=0.04,
                      corners=('tl',))
            _tac_outline(root, lx, rx, -0.10, 0.30, line, notch=0.04,
                         corners=('tl',), thickness=1.4)
            OnscreenText(parent=root, text=tag, pos=(rx - 0.03, 0.24),
                         scale=0.026, fg=TAC_TEXT_3, align=TextNode.ARight,
                         font=self._tac_display_font, mayChange=False)
            dot = _tac_fill(root, lx + 0.03, lx + 0.048, 0.238, 0.256,
                            TAC_ACCENT if me else TAC_STEEL)
            OnscreenText(parent=root, text=who, pos=(lx + 0.066, 0.236),
                         scale=0.022, fg=(TAC_ACCENT if me else TAC_STEEL),
                         align=TextNode.ALeft, font=self._tac_label_font,
                         mayChange=False)
            nm = OnscreenText(parent=root, text=name, pos=(lx + 0.03, 0.10),
                              scale=0.052, fg=TAC_TEXT_1, align=TextNode.ALeft,
                              mayChange=True)
            st = OnscreenText(parent=root, text='STANDBY', pos=(lx + 0.03, -0.02),
                              scale=0.024, fg=TAC_TEXT_2, align=TextNode.ALeft,
                              font=self._tac_label_font, mayChange=True)
            return nm, st, dot

        _myname, self.lobby_my_status, _md = _slot(-0.62, -0.05, True, 'P1',
                                                   'YOU', self.player_name or 'YOU')
        self.lobby_op_name, self.lobby_op_status, op_dot = _slot(
            0.05, 0.62, False, 'P2', 'REMOTE', 'CONNECTING…')
        # 상대 점 펄스 — 접속 대기 표시(HTML 'connecting' 점 펄스). 클럭 정상이라 루프 OK.
        op_dot.setTransparency(1)
        self._lobby_pulse = Sequence(
            LerpColorScaleInterval(op_dot, 0.55, (1, 1, 1, 0.2), (1, 1, 1, 1)),
            LerpColorScaleInterval(op_dot, 0.55, (1, 1, 1, 1), (1, 1, 1, 0.2)))
        self._lobby_pulse.loop()
        # READY UP 버튼 + 안내
        self.lobby_ready_btn = self._tac_button(
            root, 'READY UP', (0, 0, -0.34), 0.6, 0.10, self._on_ready,
            variant='accent', arrow=True)
        OnscreenText(text='BOTH OPERATORS READY → MATCH STARTS IN 5S',
                     pos=(0, -0.50), scale=0.026, fg=TAC_TEXT_3,
                     align=TextNode.ACenter, mayChange=False, parent=root,
                     font=self._tac_label_font)

    def _on_ready(self):
        # 내 준비완료 — 상태 표시 갱신 + 버튼 비활성. _ready 는 패킷으로 상대에게 전송됨.
        if self._ready:
            return
        self._ready = True
        self.lobby_my_status.setText('READY')
        self.lobby_my_status.setFg(TAC_ACCENT)
        self.lobby_ready_btn['state'] = 'disabled'
        print('[lobby] 내 준비완료', flush=True)

    def _update_lobby(self):
        # 매 프레임 — 상대 이름/준비 상태를 패킷에서 읽어 UI 갱신.
        rs = self.remote_state
        if rs is None or len(rs) < 13:
            return
        name, ready = rs[11], rs[12]
        self._remote_name = name
        self._remote_ready = ready
        self.lobby_op_name.setText(name if name else 'REMOTE')
        if ready:
            self.lobby_op_status.setText('READY')
            self.lobby_op_status.setFg(TAC_ACCENT)
        else:
            self.lobby_op_status.setText('CONNECTED' if name else 'STANDBY')
            self.lobby_op_status.setFg(TAC_TEXT_2)

    def _set_ingame_hud_visible(self, on):
        # 준비방(로비)이 떠 있는 동안 인게임 HUD(조준점/탄약/체력/킬피드/점수)를
        # 숨겨 준비방 위로 겹쳐 보이는 걸 막는다. 매치 시작(_exit_lobby) 시 복귀.
        for nm in ('crosshair', 'hitmarker', 'hud_ammo_num', 'hud_ammo_max',
                   'hud_weapon_lbl', 'hud_reload_text', 'php_track', 'php_fill',
                   'php_ghost', 'php_num', 'hud_vitals_lbl', 'hud_score',
                   'hud_score_frame', '_ammo_plate', '_health_plate', '_kf_parent'):
            w = getattr(self, nm, None)
            if w is not None:
                (w.show if on else w.hide)()

    def _exit_lobby(self):
        # 양쪽 준비완료 — 준비방 종료. UI 숨기고 커서 잡아(FPS 마우스룩 복귀) 카운트다운으로.
        self._in_lobby = False
        if getattr(self, '_lobby_pulse', None) is not None:
            self._lobby_pulse.finish()
            self._lobby_pulse = None
        if self.lobby_root is not None:
            self.lobby_root.hide()
        self._set_ingame_hud_visible(True)   # 인게임 HUD 복귀
        props = WindowProperties()
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_confined)
        self.win.requestProperties(props)
        self.win.movePointer(0, self._win_cx, self._win_cy)
        self._first_frame = True
        print('[lobby] 양쪽 준비완료 — 5초 카운트다운 시작', flush=True)

    def _setup_ai(self):
        """AI 대결 — 아레나 + 상대 자리에 AI 봇(소총). 네트워크 없음. 플레이어=스폰 A,
        AI=스폰 B 고정. 5초 카운트다운 후 FIGHT. 이동/사격은 _ai_update 가 구동한다."""
        if self._arena_data is not None:
            spawns = self._arena_data['spawns']
            sp = spawns[0]                       # 플레이어 = 스폰 A
            self._spawn_pos = Vec3(sp[0], sp[1], 0)
            self._spawn_yaw = sp[2]
            self.player_pos = Vec3(self._spawn_pos)
            self.player_yaw = self._spawn_yaw
            bp = spawns[1]                       # AI = 스폰 B
            self._ai_spawn = Vec3(bp[0], bp[1], 0)
            self._ai_pos = Vec3(self._ai_spawn)
            self._ai_yaw = bp[2]
            # 스폰 배리어로 양 포켓 가둠 — 카운트다운 끝나면 해제(= 시작).
            self._spawn_barriers = list(self._arena_data.get('spawn_barriers', []))
            self._shimmer_cards = list(self._arena_data.get('shimmer_cards', []))
            self.level_collider.walls.extend(self._spawn_barriers)
            self._barriers_active = True
            self._platforms = []
            for pd in self._arena_data.get('platforms', []):
                box = Wall(pd['x0'], pd['y0'], pd['x1'], pd['y1'],
                           thickness=0.0, height=pd['top'])
                self._platforms.append({
                    'x0': pd['x0'], 'x1': pd['x1'], 'y0': pd['y0'], 'y1': pd['y1'],
                    'top': pd['top'], 'collider': LevelCollider([box])})
        self._setup_remote_avatar()      # 아바타 + 소총 + 히트박스 + 사운드 + 트레이서
        self.ai_hp = self.ai_max_hp
        self._role_decided = True         # 스폰 고정(nonce 불필요)
        self._in_lobby = False            # AI 모드는 준비방 없음
        self._countdown_t = 5.0           # 바로 5초 카운트다운 → FIGHT
        self.hud_countdown.setFg((1, 0.92, 0.4, 1))
        av = self.remote_avatar
        if av is not None:                # 카운트다운 동안 스폰에 보이게.
            av.setPos(self._ai_pos)
            av.setH(self._ai_yaw + 180)
            av.show()
            self._remote_smooth = Vec3(self._ai_pos)
        self.hud_score.show()
        self.hud_score_frame.show()
        self._update_score_hud()
        print(f'[ai] AI 대결 시작 — 플레이어=A, AI=B, hp={self.ai_hp}', flush=True)

    def _ai_update(self, dt):
        """AI 봇 1프레임 — 거리 유지 + 좌우 스트레이프(무빙)로 플레이어 추격, 항상 조준,
        시야 트이면 소총 연사. 카운트다운/데스캠/매치종료 중엔 스폰에서 대기."""
        av = self.remote_avatar
        if av is None:
            return
        # 봇 부활 무적 타이머 — 끝나면 보호 링 숨김.
        if self._ai_invuln_t > 0.0:
            self._ai_invuln_t -= dt
            if self._ai_invuln_t <= 0.0 and self._ai_invuln_ring is not None:
                self._ai_invuln_ring.hide()
        # 재장전 타이머 — 끝나면 탄약 충전.
        if self._ai_reload_t > 0.0:
            self._ai_reload_t -= dt
            if self._ai_reload_t <= 0.0:
                self._ai_ammo = self.AI_AMMO_MAX
        frozen = (self._barriers_active or self._deathcam_t > 0.0
                  or self._match_over)
        dxp = self.player_pos.x - self._ai_pos.x
        dyp = self.player_pos.y - self._ai_pos.y
        dist = (dxp * dxp + dyp * dyp) ** 0.5 or 1e-5
        ux, uy = dxp / dist, dyp / dist
        self._ai_yaw = degrees(atan2(-ux, uy))    # 항상 플레이어 향함
        moving = False
        if not frozen and not self.jump_mode:     # 점프맵은 추격 X, 웨이포인트만(아래)
            # 스트레이프 방향 주기적 전환(저크).
            self._ai_strafe_t -= dt
            if self._ai_strafe_t <= 0.0:
                self._ai_strafe_dir = random.choice((-1, 1))
                self._ai_strafe_t = random.uniform(0.5, 1.3)
            # 멈춰서 쏘기 — 사거리 안 + 시야 트임 + 재장전 아님 + 탄약 있음이면 '정지'해
            # 조준/사격(플레이어가 피할 여지를 줌). 그 외엔 접근/측면 무빙으로 자리 잡기.
            los = not self.level_collider.segment_blocked(
                self._ai_pos.x, self._ai_pos.y,
                self.player_pos.x, self.player_pos.y)
            shoot_stance = (dist < self.AI_SHOOT_RANGE and los
                            and self._ai_reload_t <= 0.0 and self._ai_ammo > 0)
            fwd = 0.0
            strafe_mult = 0.85
            if shoot_stance:
                strafe_mult = 0.0                  # 사격 자세 — 완전 정지
            elif dist > self.AI_PREF_MAX:
                fwd = 1.0                          # 멀면 접근
            elif dist < self.AI_PREF_MIN:
                fwd = -1.0                         # 너무 가까우면 후퇴
            # 피격 직후엔 봇도 잠깐 감속.
            spd = self.AI_SPEED * (self.HIT_SLOW_MULT if self._ai_slow_t > 0.0 else 1.0)
            sx, sy = -uy, ux                       # 플레이어 기준 오른쪽(수직)
            mvx = (ux * fwd + sx * self._ai_strafe_dir * strafe_mult) * spd
            mvy = (uy * fwd + sy * self._ai_strafe_dir * strafe_mult) * spd
            nx0 = self._ai_pos.x + mvx * dt
            ny0 = self._ai_pos.y + mvy * dt
            nx, ny = self.level_collider.resolve(nx0, ny0, PLAYER_RADIUS)
            # 발판(올라타는 박스) 옆면 충돌 — 봇은 지면(z≈0)이라 윗면보다 낮아 통과 못 함.
            for p in self._platforms:
                if self._ai_pos.z < p['top'] - self._step_assist:
                    nx, ny = p['collider'].resolve(nx, ny, PLAYER_RADIUS)
            moved = ((nx - self._ai_pos.x) ** 2 + (ny - self._ai_pos.y) ** 2) ** 0.5
            self._ai_pos.x, self._ai_pos.y = nx, ny
            moving = moved > 0.003
            # 벽/발판에 비비면 스트레이프 방향 뒤집어 빠져나오게.
            if (mvx * mvx + mvy * mvy) > 1e-4 and moved < 0.3 * spd * dt:
                self._ai_strafe_dir *= -1
        # 점프맵 — 봇은 자기 레인 B 코스를 스스로 진행(웨이포인트 추종, 점프하듯 호 그림)
        # 하고 플레이어를 독립적으로 향해 조준/사격. (플레이어를 따라하지 않음.)
        bot_z = 0.0
        if self.jump_mode:
            bot_z = self._ai_jump_z if not frozen else self._ai_jump_z
            if not frozen:
                bot_z = self._ai_jump_step(dt)
                self._ai_jump_z = bot_z
                moving = True
            ddx = self.player_pos.x - self._ai_pos.x
            ddy = self.player_pos.y - self._ai_pos.y
            dist = (ddx * ddx + ddy * ddy) ** 0.5 or 1e-5
            self._ai_yaw = degrees(atan2(-ddx / dist, ddy / dist))  # 플레이어 조준
        # 아바타 배치/표시.
        self._remote_smooth = Vec3(self._ai_pos.x, self._ai_pos.y, bot_z)
        av.setPos(self._ai_pos.x, self._ai_pos.y, bot_z)
        av.setH(self._ai_yaw + 180)
        if av.isHidden() and not self._remote_hidden_for_death:
            av.show()
        # 애니메이션(소총 자세).
        want = ('RifleRunForward' if (moving and 'RifleRunForward' in self.anim_names)
                else ('RifleIdle' if 'RifleIdle' in self.anim_names else 'Idle'))
        if want and want != self._remote_anim:
            av.loop(want)
            self._remote_anim = want
        # 손 본 따라 무기 앵커 갱신 + 소총 표시. (사망 중엔 무기를 바닥에 떨궜으니 건너뜀)
        av.update(force=True)
        if not self._remote_hidden_for_death:
            if (self._remote_weapon_anchor is not None and self._remote_hand is not None
                    and not self._remote_hand.isEmpty()):
                self._remote_weapon_anchor.setPos(self._remote_hand.getPos(self.render))
                self._remote_weapon_anchor.setHpr(self._remote_hand.getHpr(self.render))
            self._show_remote_weapon(1)               # 소총(인덱스 1)
        # 발소리.
        if moving and not frozen:
            self._ai_foot_t -= dt
            if self._ai_foot_t <= 0.0:
                self._play_remote_footstep()
                self._ai_foot_t = self.footstep_interval
        else:
            self._ai_foot_t = 0.0
        # 트레이서 페이드.
        if self._remote_tracer_t > 0.0:
            self._remote_tracer_t -= dt
            if self._remote_tracer_t <= 0.0 and self._remote_tracer is not None:
                self._remote_tracer.hide()
        if frozen:
            return
        if self._ai_invuln_t > 0.0:
            return                          # 봇 무적(막 부활/처치당함) 중엔 사격 안 함
        if self._ai_reload_t > 0.0:
            return                          # 재장전 중엔 사격 안 함
        # 사격 — 쿨다운마다. 축구면 공↔플레이어 번갈아 사격(공은 봇 골 방향으로 차기).
        self._ai_fire_t -= dt
        if self._ai_fire_t <= 0.0:
            if self._ai_ammo <= 0:          # 탄약 소진 → 재장전 시작(모든 모드)
                self._ai_reload_t = self.AI_RELOAD_DUR
                self._ai_fire_t = self.AI_FIRE_INTERVAL
                self._play_remote_reload(True)
                print('[ai] 봇 재장전', flush=True)
                return
            fired = False
            if self.soccer_mode and self._ball is not None:
                self._ai_fire_t = 0.8        # 축구는 또박또박(공/플레이어 교대)
                self._ai_shoot_ball = not getattr(self, '_ai_shoot_ball', False)
                if self._ai_shoot_ball:
                    self._ai_kick_ball_toward_goal()
                    fired = True
                elif dist < self.AI_SHOOT_RANGE:
                    self._ai_try_shoot(dist)
                    fired = True
            elif self.jump_mode:
                # 점프맵 — 견제만. 드물게(랜덤 간격) + 저명중/저데미지라 진행 가능.
                self._ai_fire_t = random.uniform(1.1, 1.8)
                if dist < self.AI_SHOOT_RANGE:
                    self._ai_try_shoot(dist, weak=True)
                    fired = True
            elif dist < self.AI_SHOOT_RANGE:
                self._ai_fire_t = self.AI_FIRE_INTERVAL
                self._ai_try_shoot(dist)
                fired = True
            else:
                self._ai_fire_t = self.AI_FIRE_INTERVAL
            if fired:
                self._ai_ammo -= 1          # 한 발 소비(0 되면 다음 사이클에 재장전)

    def _ai_kick_ball_toward_goal(self):
        """축구 AI — 공을 봇의 공격 골(남쪽 y<0) 방향으로 찬다. 시야 막히면 패스. 솔로라
        로컬(플레이어 A)이 공 권위이므로 공에 직접 임펄스."""
        b = self._ball
        if b is None:
            return
        if self.level_collider.segment_blocked(
                self._ai_pos.x, self._ai_pos.y, b.pos.x, b.pos.y):
            return                            # 공이 벽 뒤 — 패스
        sc = self._arena_data.get('soccer', {})
        gy = -sc.get('half_y', 18.0)          # 봇(B)은 남쪽 골 공격
        dirx, diry = 0.0 - b.pos.x, gy - b.pos.y
        L = (dirx * dirx + diry * diry) ** 0.5 or 1e-5
        kick_dir = Vec3(dirx / L, diry / L, 0.04)
        # 공을 향해 조준(트레이서/소리)
        bdx, bdy = b.pos.x - self._ai_pos.x, b.pos.y - self._ai_pos.y
        bdist = (bdx * bdx + bdy * bdy) ** 0.5 or 1e-5
        self._ai_yaw = degrees(atan2(-bdx, bdy))
        pitch = degrees(atan2(b.pos.z - 1.4, bdist))
        self._show_remote_tracer((0, 0, 0, self._ai_yaw, pitch))
        vol = self._remote_dist_volume(1.3, 5.0, 90.0)
        if vol > 0.0:
            self._play_pool_vol(self._r_sfx_m16, '_r_sfx_m16_i', vol)
        # 중앙 명중(스핀 없이) 골 방향으로 강하게 — 솔로는 로컬이 권위라 직접 적용.
        b.kick(Vec3(0, 0, 0), kick_dir, self.SOCCER_KICK_RIFLE)

    def _ai_jump_step(self, dt):
        """점프맵 봇 — 자기 레인 웨이포인트를 스스로 따라 진행(갭은 포물선 호로 '점프').
        결승 웨이포인트 도달 시 봇 승리. 반환: 현재 봇 높이(z)."""
        wps = self._ai_wp
        i = self._ai_wp_i
        if not wps or i >= len(wps):
            return self._ai_jump_z
        tx, ty, ttop = wps[i]
        px, py, ptop = wps[i - 1]
        dx, dy = tx - self._ai_pos.x, ty - self._ai_pos.y
        d = (dx * dx + dy * dy) ** 0.5
        step = self.AI_JUMP_SPEED * dt
        if d <= max(step, 0.3):
            self._ai_pos.x, self._ai_pos.y = tx, ty
            self._ai_wp_i += 1
            if self._ai_wp_i >= len(wps) and not self._ai_jump_done:
                self._ai_jump_done = True
                print('[jump] 봇 결승 도달 — 패배', flush=True)
                self._end_match(False)        # 봇이 먼저 도착 → 플레이어 패배
            return ttop
        self._ai_pos.x += dx / d * step
        self._ai_pos.y += dy / d * step
        seg = ((tx - px) ** 2 + (ty - py) ** 2) ** 0.5 or 1e-5
        frac = max(0.0, min(1.0, 1.0 - d / seg))
        # 갭(긴 구간)이면 포물선 호로 점프하는 듯 보이게.
        arc = 0.75 * (1.0 - (2.0 * frac - 1.0) ** 2) if seg > 1.5 else 0.0
        return ptop + (ttop - ptop) * frac + arc

    def _ai_jump_reset_route(self):
        """봇 코스 처음으로 — 처치당하거나 시작 시. 무적 잠깐 부여."""
        if self._ai_wp:
            w0 = self._ai_wp[0]
            self._ai_pos = Vec3(w0[0], w0[1], 0)
            self._ai_jump_z = w0[2]
        self._ai_wp_i = 1
        self._ai_jump_done = False

    def _ai_respawn(self):
        """봇 부활(축구/땅따먹기 솔로) — 원래 스폰으로 복귀 + 잠깐 무적 + 발밑 보호 링.
        (죽은 자리에서 다시 살아나던 버그 수정.)"""
        self._ai_pos = Vec3(self._ai_spawn)
        self.ai_hp = self.ai_max_hp
        self._ai_fire_t = 0.0
        self._ai_ammo = self.AI_AMMO_MAX     # 부활 시 탄약 충전
        self._ai_reload_t = 0.0
        self._ai_invuln_t = self.AI_INVULN_DUR
        av = self.remote_avatar
        if av is not None:
            av.setPos(self._ai_pos)
            self._remote_smooth = Vec3(self._ai_pos)
        self._show_ai_invuln_ring()
        print('[ai] 봇 부활 — 스폰 복귀 + 무적', flush=True)

    def _show_ai_invuln_ring(self):
        """봇 발밑 보호 링 — remote_avatar 에 부착(부활자를 원으로 감쌈)."""
        av = self.remote_avatar
        if av is None:
            return
        if self._ai_invuln_ring is None:
            seg = LineSegs('ai_invuln_ring')
            seg.setThickness(3.0)
            seg.setColor(1.0, 0.85, 0.25, 0.9)   # 봇 보호 링(노랑)
            steps = 36
            R = 1.1
            for i in range(steps + 1):
                a = (i / steps) * 6.28318
                seg.drawTo(R * cos(a), R * sin(a), 0.05)
            self._ai_invuln_ring = av.attachNewNode(seg.create())
            self._ai_invuln_ring.setLightOff()
            self._ai_invuln_ring.setTransparency(True)
        self._ai_invuln_ring.show()

    def _ai_try_shoot(self, dist, weak=False):
        """AI 한 발 — 벽에 막히면 안 쏨. 트레이서 + 거리별 소총음 + 거리 기반 명중 확률로
        내 체력 감소. weak=True(점프맵 견제)면 명중·데미지를 크게 낮춰 진행을 막지 않는다."""
        if self.level_collider.segment_blocked(
                self._ai_pos.x, self._ai_pos.y,
                self.player_pos.x, self.player_pos.y):
            return                                # 벽 뒤 — 사격 안 함
        # 헤드샷 굴림 — 일정 확률로 머리 조준(데미지↑·트레이서도 머리로). 그 외 몸통.
        gun_z = 1.4
        headshot = (not weak) and random.random() < 0.28
        tgt_z = self.player_pos.z + self.head_height * (0.95 if headshot else 0.5)
        pitch = degrees(atan2(tgt_z - gun_z, dist))
        self._show_remote_tracer((0, 0, 0, self._ai_yaw, pitch))
        vol = self._remote_dist_volume(1.3, 5.0, 90.0)
        if vol > 0.0:
            self._play_pool_vol(self._r_sfx_m16, '_r_sfx_m16_i', vol)
        # 명중 확률 — 살짝 낮춤(0.28~0.60). '멈춰 쏘므로' 플레이어가 피할 여지를 둔다.
        acc = max(0.28, min(0.60, 0.64 - dist * 0.016))
        dmg = self.AI_DMG
        if headshot:
            dmg = int(self.AI_DMG * 2.2)      # 헤드샷 추가 데미지
        if weak:                              # 점프맵 견제 — 대부분 빗나가고 데미지도 약하게
            acc *= 0.40
            dmg = max(3, self.AI_DMG // 2)
        if random.random() < acc:
            self._apply_pvp_damage(dmg)

    def _setup_online(self):
        """상대 3인칭 아바타 생성 + 릴레이 접속 + 아레나 스폰/배리어 세팅."""
        # ── 아레나 — 두 포켓 모두 배리어로 가두고, 임시로 스폰 A 에 둔다.
        #    실제 스폰(A/B)은 첫 상대 패킷의 nonce 비교로 _decide_role 에서 확정.
        if self._arena_data is not None:
            # 임시 위치: --p2 면 B, 아니면 A (nonce 결정 전 잠깐). 어차피 둘 다 가둬짐.
            sp = self._arena_data['spawns'][1 if self._spawn_b else 0]
            self._spawn_pos = Vec3(sp[0], sp[1], 0)
            self._spawn_yaw = sp[2]
            self.player_pos = Vec3(self._spawn_pos)
            self.player_yaw = self._spawn_yaw
            # 스폰 배리어로 즉시 가둠(양 포켓 모두) — 역할 확정 + 준비되면 5초 후 해제.
            self._spawn_barriers = list(self._arena_data.get('spawn_barriers', []))
            self._shimmer_cards = list(self._arena_data.get('shimmer_cards', []))
            self.level_collider.walls.extend(self._spawn_barriers)
            self._barriers_active = True
            self._role_decided = False
            self._countdown_t = None      # 역할 확정 + 상대 보이면 카운트다운 시작
            # 올라타는 플랫폼 — 각 박스 footprint 를 두께 0 Wall 1개로 만든 LevelCollider
            # 로 옆면 충돌 처리(아래에서만 막음). 윗면 지지는 이동 코드가 top 으로 판정.
            self._platforms = []
            for pd in self._arena_data.get('platforms', []):
                box = Wall(pd['x0'], pd['y0'], pd['x1'], pd['y1'],
                           thickness=0.0, height=pd['top'])
                self._platforms.append({
                    'x0': pd['x0'], 'x1': pd['x1'], 'y0': pd['y0'], 'y1': pd['y1'],
                    'top': pd['top'], 'collider': LevelCollider([box])})
            print(f'[arena] 대기 — nonce={self._nonce} (스폰 자동배정), '
                  f'플랫폼 {len(self._platforms)}개', flush=True)

        self._setup_remote_avatar()
        self._connect_relay()
        # PvP 점수 HUD 표시 (먼저 10점 승리). 단일플레이에선 숨김 유지.
        self.hud_score.show()
        self.hud_score_frame.show()
        self._update_score_hud()
        # 준비방(로비) — 이름(좌=나 / 우=상대) 표시 + 양쪽 준비완료 대기. 버튼 클릭을
        # 위해 커서를 보이게 하고 마우스룩/카운트다운은 보류한다(_in_lobby).
        if self._arena_data is not None:
            self._in_lobby = True
            self._build_lobby_ui()
            self._set_ingame_hud_visible(False)   # 준비방 동안 인게임 HUD 숨김
            props = WindowProperties()
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)

    def _setup_soccer(self):
        """축구 — _setup_online/_setup_ai 직후 호출. 멀티는 로비 생략 + nonce 역할배정.
        솔로(ai)는 _setup_ai 가 이미 역할/카운트다운/봇을 세팅했으니 공만 추가한다."""
        self._am_a = not self._spawn_b   # 솔로=A(플레이어). 멀티는 nonce/타임아웃이 확정
        if not self.ai_mode:
            # 멀티 — 로비 생략, _role_decided=False 로 두고 _arena_update 가 nonce 로 확정.
            if self.lobby_root is not None:
                self.lobby_root.destroy()
                self.lobby_root = None
            self._in_lobby = False
            self._role_decided = False
            self._countdown_t = None
            self._soccer_wait_t = 0.0
            self.hud_countdown.setFg((1, 0.92, 0.4, 1))
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_confined)
            self.win.requestProperties(props)
            self.win.movePointer(0, self._win_cx, self._win_cy)
            self._first_frame = True
        # 공 생성(중앙).
        sc = self._arena_data.get('soccer', {}) if self._arena_data else {}
        self._ball = SoccerBall(self, sc.get('ball_spawn', (0.0, 0.0)))
        self._goals_a = 0
        self._goals_b = 0
        self._goal_cele_t = 0.0
        # 봇 사격 교대 시작값 — True 로 두면 첫 토글이 False(=플레이어)라 첫 발은 플레이어.
        self._ai_shoot_ball = True
        self._build_soccer_hud()
        self._update_score_hud()
        print('[soccer] 축구 시작 — 먼저 5골 승리 (총으로 공을 차세요)', flush=True)

    def _build_soccer_hud(self):
        """골 배너 — 득점 시 화면 중앙에 크게 잠깐 표시."""
        if self.hud_goal_banner is None:
            self.hud_goal_banner = OnscreenText(
                text='', pos=(0, 0.18), scale=0.22, fg=(0.3, 1.0, 0.5, 1.0),
                align=TextNode.ACenter, mayChange=True, parent=self.aspect2d)
            self.hud_goal_banner.setBin('fixed', 55)
        self.hud_goal_banner.hide()

    def _soccer_kick_ball(self, offset, direction, power):
        """공 차기 — 권위(A)면 직접 적용, 비권위(B)면 킥 이벤트로 권위에 전송(A 가
        적용 후 공 위치를 브로드캐스트)."""
        if self._am_a:
            self._ball.kick(offset, direction, power)
        else:
            self._kick_seq = (self._kick_seq + 1) & 0xFF
            self._kick_off = Vec3(offset)
            self._kick_dir = Vec3(direction)
            self._kick_power = power

    def _soccer_update(self, dt):
        """축구 1프레임. 권위(A): 상대 킥 적용 + 공 물리 + 골 판정 + 세리머니/킥오프.
        비권위(B): 권위가 보낸 공 위치를 따라가고, 점수 변화로 골/승리 처리."""
        if self._ball is None:
            return
        # 골 배너 표시 시간 — 끝나면 배너만 숨김. (재시작은 _soccer_round_reset 의
        # 배리어 5초 카운트다운이 처리하므로 여기서 멈추거나 킥오프하지 않는다.)
        if self._goal_cele_t > 0.0:
            self._goal_cele_t -= dt
            if self._goal_cele_t <= 0.0 and self.hud_goal_banner is not None:
                self.hud_goal_banner.hide()

        if not self._am_a:
            # ── 비권위(B) — 권위가 보낸 공 위치 추종(부드럽게) + 점수 동기화. ──
            rs = self.remote_state
            if rs is not None and len(rs) >= 26:
                target = Vec3(rs[13], rs[14], rs[15])
                new_pos = self._ball.pos + (target - self._ball.pos) * min(
                    1.0, dt * 16.0)
                # 추정 속도(위치 변화량) → 회전 시각화에 사용(구르는 무늬가 보이게).
                self._ball.vel = (new_pos - self._ball.pos) * (1.0 / max(dt, 1e-5))
                self._ball.pos = new_pos
                self._ball.node.setPos(self._ball.pos)
                self._ball._spin_visual(dt)
                self._soccer_client_scores(rs[16], rs[17])
            return

        # ── 권위(A) ──────────────────────────────────────────────────────
        # 상대(B)가 보낸 킥 이벤트 적용(seq 증가 감지).
        rs = self.remote_state
        if rs is not None and len(rs) >= 26:
            kseq = rs[18]
            if self._remote_kick_seq is None:
                self._remote_kick_seq = kseq
            elif kseq != self._remote_kick_seq:
                self._remote_kick_seq = kseq
                kdir = Vec3(rs[22], rs[23], rs[24])
                if kdir.lengthSquared() > 1e-9:
                    self._ball.kick(Vec3(rs[19], rs[20], rs[21]), kdir, rs[25])
        # 킥오프 카운트다운(배리어) 중엔 공 정지.
        if self._barriers_active:
            return
        sc = self._arena_data.get('soccer', {})
        scored = self._ball.update(dt, sc['half_x'], sc['half_y'],
                                   sc['goal_hw'], sc['goal_depth'])
        self._soccer_ball_vs_players()        # 공이 몸을 통과하지 않게(튕겨냄)
        # 매치 종료 후엔 공이 슬로우모션으로 네트까지 굴러 들어가는 걸 보여주되(연출),
        # 새 골은 더 트리거하지 않는다.
        if scored is not None and not self._match_over:
            self._soccer_goal(scored)

    def _soccer_ball_vs_players(self):
        """공 vs 플레이어 몸통 충돌(권위만). 공은 '쏠 때만' 움직인다:
        - 날아오는(빠른) 공 → 몸에 튕김(공 반사, 통과 방지).
        - 느린/정지 공 → 공은 그대로, 파고든 쪽(나/봇)을 밀어내 막기만(저절로 안 굴러감).
        몸은 반지름 PLAYER_RADIUS 의 수직 기둥으로 근사. 머리 위로 뜬 공은 통과."""
        b = self._ball
        if b is None or b.pos.z > 2.0:
            return
        targets = [('me', self.player_pos)]
        av = self.remote_avatar
        if (self._remote_smooth is not None and av is not None
                and not av.isHidden()):
            targets.append(('bot' if self.ai_mode else 'remote', self._remote_smooth))
        mind = b.RADIUS + PLAYER_RADIUS
        ball_fast = (b.vel.x * b.vel.x + b.vel.y * b.vel.y) > 4.0   # >2 m/s = 쏜 공
        for kind, p in targets:
            dx = b.pos.x - p.x
            dy = b.pos.y - p.y
            d2 = dx * dx + dy * dy
            if d2 >= mind * mind:
                continue
            if d2 > 1e-9:
                d = d2 ** 0.5
                nx, ny = dx / d, dy / d
            else:
                nx, ny = 1.0, 0.0
            if ball_fast:
                # 날아오는 공 → 몸 밖으로 밀고 반사(튕김).
                b.pos.x = p.x + nx * mind
                b.pos.y = p.y + ny * mind
                vn = b.vel.x * nx + b.vel.y * ny
                if vn < 0.0:
                    k = (1.0 + b.RESTITUTION) * vn
                    b.vel.x -= k * nx
                    b.vel.y -= k * ny
                b.node.setPos(b.pos)
            elif kind == 'me':
                # 정지 공 — 내가 파고들면 나를 공 밖으로(공은 안 움직임).
                self.player_pos.x = b.pos.x - nx * mind
                self.player_pos.y = b.pos.y - ny * mind
            elif kind == 'bot':
                self._ai_pos.x = b.pos.x - nx * mind
                self._ai_pos.y = b.pos.y - ny * mind
                self._remote_smooth = Vec3(self._ai_pos.x, self._ai_pos.y, 0)
            # 'remote'(멀티 상대)는 자기 클라가 충돌 처리 → 여기선 공 안 움직임

    def _soccer_client_scores(self, sa, sb):
        """비권위(B) — 권위가 보낸 점수 변화 감지 → 배너/HUD/승리 처리."""
        if sa == self._goals_a and sb == self._goals_b:
            return
        scored_a = sa > self._goals_a
        self._goals_a, self._goals_b = sa, sb
        self._update_score_hud()
        i_scored = (scored_a == self._am_a)
        self._show_goal_banner(i_scored)
        if (sa >= self.SOCCER_WIN or sb >= self.SOCCER_WIN) \
                and not self._match_over:
            self._goal_cele_t = 0.0
            self._end_match(i_scored)
        else:
            self._goal_cele_t = 2.0
            self._soccer_round_reset()       # 나도 스폰 복귀 + 5초 카운트다운

    def _show_goal_banner(self, i_scored):
        """득점/실점 배너 표시 + 득점 효과음(있으면). 권위·클라 공용."""
        if self.hud_goal_banner is not None:
            self.hud_goal_banner.setText('골!!!' if i_scored else '실점...')
            self.hud_goal_banner.setFg((0.3, 1.0, 0.5, 1.0) if i_scored
                                       else (1.0, 0.5, 0.4, 1.0))
            self.hud_goal_banner.show()
        if i_scored and getattr(self, 'sfx_kill_pool', None):
            try:
                self.sfx_kill_pool[0].play()
            except Exception:
                pass

    def _soccer_round_reset(self):
        """1점 득실 후 — 공 중앙 + 양쪽(나/봇) 스폰 복귀 + 배리어 재가둠 + 5초 카운트다운
        후 재시작. (_arena_round_reset 재사용 + 공 리셋.)"""
        if self._ball is not None:
            self._ball.reset()
        self._ai_shoot_ball = True
        self._arena_round_reset()

    def _soccer_goal(self, team):
        """골 처리(권위) — 득점 갱신 + 배너. 승리(5골)면 매치 종료, 아니면 1점 득실마다
        양쪽 스폰 복귀 + 공 중앙 + 5초 카운트다운 후 재시작."""
        if team == 'A':
            self._goals_a += 1
        else:
            self._goals_b += 1
        self._update_score_hud()
        i_scored = ((team == 'A') == self._am_a)
        self._show_goal_banner(i_scored)
        print(f'[soccer] GOAL ({team})  A {self._goals_a} : {self._goals_b} B',
              flush=True)
        scorer_goals = self._goals_a if team == 'A' else self._goals_b
        if scorer_goals >= self.SOCCER_WIN:
            self._goal_cele_t = 0.0
            self._end_match(i_scored)        # 승리 → 매치 종료
        else:
            self._goal_cele_t = 2.0          # 배너 표시 시간(재시작은 카운트다운이 처리)
            self._soccer_round_reset()       # 양쪽 스폰 복귀 + 5초 카운트다운

    def _soccer_kickoff_reset(self):
        """킥오프 — 공을 중앙으로, 양 플레이어를 스폰으로 복귀(부활 무적 부여)."""
        if self._ball is not None:
            self._ball.reset()
        self.player_pos = Vec3(self._spawn_pos)
        self.player_yaw = self._spawn_yaw
        self.player_vz = 0.0
        self.on_ground = True
        self._ai_shoot_ball = True           # 킥오프 후에도 봇 첫 발은 플레이어부터
        self._grant_invuln()                 # 킥오프 직후 잠깐 무적
        self.hud_countdown.setText('KICK OFF')
        self.hud_countdown.setFg((1, 0.92, 0.4, 1))
        self.hud_countdown.show()
        self._fight_t = 1.0                  # 1초 뒤 _arena_update 가 숨김

    def _soccer_respawn_self(self):
        """축구 사망 후 부활 — 나만 스폰 복귀 + HP/탄 회복 + 무적(보호 링). 공/경기 유지."""
        self.player_pos = Vec3(self._spawn_pos)
        self.player_yaw = self._spawn_yaw
        self.player_pitch = 0.0
        self.player_vz = 0.0
        self.on_ground = True
        self.core_integrity = self.core_integrity_max
        self.ammo = self.ammo_max
        for w in self._weapons.values():
            w['ammo'] = w['ammo_max']
        self._pvp_dead_t = 0.0
        self._grant_invuln()
        print('[soccer] 부활 — 3초 무적', flush=True)

    def _grant_invuln(self):
        """부활/킥오프 무적 — INVULN_DUR 초 피해 무효 + 발밑 보호 링 표시."""
        self._invuln_t = self.INVULN_DUR
        if self._invuln_ring is None:
            # 발밑 청록 링(빌보드 아님 — 바닥에 눕힌 원판). 내 몸(ybot)에 부착.
            seg = LineSegs('invuln_ring')
            seg.setThickness(3.0)
            seg.setColor(0.3, 1.0, 0.9, 0.9)
            steps = 36
            R = 1.1
            for i in range(steps + 1):
                a = (i / steps) * 6.28318
                seg.drawTo(R * cos(a), R * sin(a), 0.05)
            self._invuln_ring = self.ybot.attachNewNode(seg.create())
            self._invuln_ring.setLightOff()
            self._invuln_ring.setTransparency(True)
        self._invuln_ring.show()

    # --- 땅따먹기(영역 페인트) -------------------------------------------------

    def _setup_paint(self):
        """땅따먹기 — _setup_online/_setup_ai 직후 호출. 색 배정 + 격자 참조 + HUD.
        솔로(ai)면 내가 A(파랑)·봇이 B(주황). 멀티는 _decide_role(nonce)이 _am_a 확정."""
        self._paint = self._arena_data.get('paint') if self._arena_data else None
        self._am_a = not self._spawn_b
        self._paint_my_id = 1 if self._am_a else 2
        self._paint_opp_id = 2 if self._am_a else 1
        self._paint_count = {1: 0, 2: 0}     # 칠한 칸 수(색별) — _paint_disc 가 증감
        self._paint_time_left = PAINT_TIME
        self.hud_score.hide()                # 킬 점수 HUD 숨김(땅따먹기는 안 씀)
        self.hud_score_frame.hide()
        self._build_paint_hud()
        self._update_paint_hud()
        print(f'[paint] 땅따먹기 시작 — 내 색={"A(파랑)" if self._am_a else "B(주황)"} '
              f'(3분, 더 많이 칠한 쪽 승리)', flush=True)

    def _build_paint_hud(self):
        """상단 HUD — 3분 타이머 + 그 밑에 칠한 칸 수 (A 파랑):(B 주황). 시안/글리치 안 씀."""
        ca = PAINT_COLORS[1]
        cb = PAINT_COLORS[2]
        # 타이머/점수 택티컬 프레임 — 다크 노치 패널 + 양쪽 레드 틱(메뉴 디자인 톤).
        self.hud_paint_frame = self.aspect2d.attachNewNode('paint_frame')
        _tac_fill(self.hud_paint_frame, -0.16, 0.16, 0.775, 0.965,
                  (0.055, 0.060, 0.072, 0.55), notch=0.028, corners=('tl', 'br'))
        _tac_outline(self.hud_paint_frame, -0.16, 0.16, 0.775, 0.965, TAC_LINE,
                     notch=0.028, corners=('tl', 'br'), thickness=1.3)
        _tac_fill(self.hud_paint_frame, -0.20, -0.165, 0.91, 0.924, TAC_ACCENT)
        _tac_fill(self.hud_paint_frame, 0.165, 0.20, 0.91, 0.924, TAC_ACCENT)
        _tac_fill(self.hud_paint_frame, -0.13, 0.13, 0.872, 0.8735, TAC_LINE)  # 구분선
        self.hud_paint_timer = OnscreenText(
            text='3:00', pos=(0, 0.92), scale=0.085, fg=(1, 1, 1, 0.96),
            align=TextNode.ACenter, mayChange=True, parent=self.aspect2d)
        self.hud_paint_a = OnscreenText(
            text='0', pos=(-0.07, 0.83), scale=0.075, fg=ca,
            align=TextNode.ARight, mayChange=True, parent=self.aspect2d)
        self.hud_paint_colon = OnscreenText(
            text=':', pos=(0, 0.83), scale=0.075, fg=(1, 1, 1, 0.9),
            align=TextNode.ACenter, mayChange=False, parent=self.aspect2d)
        self.hud_paint_b = OnscreenText(
            text='0', pos=(0.07, 0.83), scale=0.075, fg=cb,
            align=TextNode.ALeft, mayChange=True, parent=self.aspect2d)

    def _update_paint_hud(self):
        """칸 수 표시 갱신 — (A 칸):(B 칸)."""
        if getattr(self, 'hud_paint_a', None) is None:
            return
        self.hud_paint_a.setText(str(self._paint_count.get(1, 0)))
        self.hud_paint_b.setText(str(self._paint_count.get(2, 0)))

    def _update_paint_timer_hud(self):
        t = max(0, int(self._paint_time_left + 0.999))
        if getattr(self, 'hud_paint_timer', None) is not None:
            self.hud_paint_timer.setText(f'{t // 60}:{t % 60:02d}')

    def _paint_update(self, dt):
        """땅따먹기 1프레임 — 시작 카운트다운 끝난 뒤 3분 타이머 감소, 0 이면 종료."""
        self._update_health_packs(dt)     # 힐팩 둥실/회전/줍기
        if self._match_over:
            return
        if self._barriers_active:
            return                            # 시작 5초 카운트다운 중엔 타이머 대기
        self._paint_time_left -= dt
        if self._paint_time_left <= 0.0:
            self._paint_time_left = 0.0
            self._update_paint_timer_hud()
            self._paint_end_by_time()
            return
        self._update_paint_timer_hud()

    def _paint_end_by_time(self):
        """제한시간 종료 — 칸 수 많은 쪽 승리(동수면 패/무)."""
        mine = self._paint_count.get(self._paint_my_id, 0)
        opp = self._paint_count.get(self._paint_opp_id, 0)
        print(f'[paint] 시간 종료 — 내 칸 {mine} vs 상대 {opp}', flush=True)
        self._end_match(mine > opp)

    def _paint_disc(self, cx, cy, radius, color_id, cz=0.5):
        """(cx,cy,cz) 중심 반경 안의 셀(바닥+벽+장애물)을 color_id 색으로 칠한다.
        3D 거리라 칠한 자리 근처의 낮은 벽면에도 자연스럽게 색이 번진다. 칸 수도 증감."""
        if self._paint is None:
            return
        col = PAINT_COLORS.get(color_id)
        if col is None:
            return
        cw = GeomVertexWriter(self._paint['vdata'], 'color')
        r2 = radius * radius
        for cell in self._paint['cells']:
            dx = cell['cx'] - cx
            dy = cell['cy'] - cy
            cz_cell = cell.get('cz', 0.0)
            dz = cz_cell - cz
            if dx * dx + dy * dy + dz * dz <= r2:
                old = cell['owner']
                if old == color_id:
                    continue
                cell['owner'] = color_id
                cw.setRow(cell['v0'])
                cw.setData4(*col)
                cw.setData4(*col)
                cw.setData4(*col)
                cw.setData4(*col)
                # 점수는 바닥(땅) 칸만 1점씩 — 벽/장애물 칸은 칠하되 점수엔 안 센다.
                if cz_cell < 0.1:
                    if old in self._paint_count:
                        self._paint_count[old] -= 1
                    self._paint_count[color_id] = \
                        self._paint_count.get(color_id, 0) + 1
        self._update_paint_hud()

    def _paint_on_kill(self, victim_xy, zone, color_id):
        """처치 위치 주변을 color_id 색으로 칠함. 부위(zone)별 반경 차등."""
        radius = PAINT_KILL_RADIUS.get(zone, PAINT_KILL_RADIUS['other'])
        self._paint_disc(victim_xy[0], victim_xy[1], radius, color_id)
        print(f'[paint] 칠하기 — 색{color_id} zone={zone} r={radius} '
              f'@({victim_xy[0]:.1f},{victim_xy[1]:.1f})', flush=True)

    def _spawn_health_pack(self, x, y):
        """적 시체 위 힐팩 — 초록 박스+흰 십자. 둥실거리며 회전, 밟으면 체력 회복."""
        node = self.render.attachNewNode('healthpack')
        h = 0.28
        faces = [((0, 0, 0), (0, -h, 0)), ((0, 0, 0), (0, h, 0)),
                 ((90, 0, 0), (-h, 0, 0)), ((90, 0, 0), (h, 0, 0)),
                 ((0, -90, 0), (0, 0, h)), ((0, -90, 0), (0, 0, -h))]
        for hpr, pos in faces:
            cm = CardMaker('hpf')
            cm.setFrame(-h, h, -h, h)
            f = node.attachNewNode(cm.generate())
            f.setHpr(*hpr)
            f.setPos(*pos)
            f.setTwoSided(True)
        node.setColor(0.15, 0.85, 0.35, 1.0)          # 초록 박스
        node.setLightOff()
        for fr in [(-h * 0.7, h * 0.7, -h * 0.18, h * 0.18),
                   (-h * 0.18, h * 0.18, -h * 0.7, h * 0.7)]:
            cm = CardMaker('hpx')                       # 흰 십자(윗면)
            cm.setFrame(*fr)
            c = node.attachNewNode(cm.generate())
            c.setHpr(0, -90, 0)
            c.setZ(h + 0.02)
            c.setColor(1, 1, 1, 1)
            c.setTwoSided(True)
        node.setPos(x, y, 0.7)
        self._health_packs.append({'node': node, 'x': x, 'y': y, 't': 0.0,
                                   'phase': 0.0})

    HEALTH_PACK_LIFE = 5.0            # 힐팩 수명(초) — 그 동안 점점 빨리 깜빡이다 소멸

    def _update_health_packs(self, dt):
        """힐팩 — 둥실+회전 + 수명(5초) 동안 서서히→엄청 빠르게 깜빡이다 사라짐.
        플레이어 근접 시 풀 회복 + 제거."""
        if not self._health_packs:
            return
        px, py = self.player_pos.x, self.player_pos.y
        for hp in self._health_packs[:]:
            hp['t'] += dt
            if hp['t'] >= self.HEALTH_PACK_LIFE:      # 수명 끝 → 소멸
                hp['node'].removeNode()
                self._health_packs.remove(hp)
                continue
            hp['node'].setZ(0.7 + 0.12 * sin(hp['t'] * 3.2))
            hp['node'].setH(hp['t'] * 90.0)
            # 깜빡임 — 5초에 가까울수록 빨라짐(서서히 → 엄청 빨리). frac^2 로 후반 가속.
            frac = hp['t'] / self.HEALTH_PACK_LIFE
            blink_hz = 1.5 + frac * frac * 20.0
            hp['phase'] += blink_hz * dt
            if (hp['phase'] % 1.0) < 0.55:
                hp['node'].show()
            else:
                hp['node'].hide()
            dx, dy = hp['x'] - px, hp['y'] - py
            if dx * dx + dy * dy < 2.0:               # 근접(√2≈1.4m) → 줍기
                self.core_integrity = self.core_integrity_max
                self._play_pool(self.sfx_hit, '_hit_i')
                hp['node'].removeNode()
                self._health_packs.remove(hp)
                print('[paint] 힐팩 획득 — 체력 회복', flush=True)

    # --- 점프맵(레이스) --------------------------------------------------------

    def _setup_jump(self):
        """점프맵 — _setup_online/_setup_ai 직후(멀티) 또는 단독(솔로) 호출. 솔로면 직접
        스폰 배치 + 발판 빌드 + 커서 가둠. 체크포인트/결승/타이머 세팅."""
        self._jump = self._arena_data.get('jump', {}) if self._arena_data else {}
        self._am_a = not self._spawn_b
        if not self.online_mode and not self.ai_mode:
            # 솔로 타임트라이얼 — 레인 A 스폰에 직접 배치.
            sp = self._arena_data['spawns'][0]
            self._spawn_pos = Vec3(sp[0], sp[1], 0)
            self._spawn_yaw = sp[2]
            self.player_pos = Vec3(self._spawn_pos)
            self.player_yaw = self._spawn_yaw
            self.player_vz = 0.0
            self.on_ground = True
            self._in_lobby = False
            # 발판 충돌(옆면 막기) — arena_data 의 platforms 로 LevelCollider 구성.
            self._platforms = []
            for pd in self._arena_data.get('platforms', []):
                box = Wall(pd['x0'], pd['y0'], pd['x1'], pd['y1'],
                           thickness=0.0, height=pd['top'])
                self._platforms.append({
                    'x0': pd['x0'], 'x1': pd['x1'], 'y0': pd['y0'], 'y1': pd['y1'],
                    'top': pd['top'], 'collider': LevelCollider([box])})
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_confined)
            self.win.requestProperties(props)
            self.win.movePointer(0, self._win_cx, self._win_cy)
            self._first_frame = True
        self._jump_finished = False
        self._jump_start_t = time.monotonic()
        # 봇 경로 — 레벨이 준 명시 경로(레인 B, 벽 우회 포함). 없으면 발판 중심 폴백.
        self._ai_wp = list(self._jump.get('bot_route', []))
        if not self._ai_wp:
            for pd in self._arena_data.get('platforms', []):
                cx = (pd['x0'] + pd['x1']) * 0.5
                if cx > 0:
                    self._ai_wp.append((cx, (pd['y0'] + pd['y1']) * 0.5, pd['top']))
            self._ai_wp.sort(key=lambda w: w[1])
        if self._ai_wp and self.ai_mode:
            w0 = self._ai_wp[0]
            self._ai_pos = Vec3(w0[0], w0[1], 0)
            self._ai_jump_z = w0[2]
        self._ai_wp_i = 1
        self._ai_jump_done = False
        self._build_jump_hud()
        print('[jump] 점프맵 시작 — 결승까지 달려라!', flush=True)

    def _build_jump_hud(self):
        """상단 타이머 + 안내. 시안/글리치 안 씀."""
        if getattr(self, 'hud_jump_timer', None) is None:
            # 타이머 택티컬 프레임 — 다크 노치 패널 + 양쪽 레드 틱(메뉴 디자인 톤).
            self.hud_jump_frame = self.aspect2d.attachNewNode('jump_frame')
            _tac_fill(self.hud_jump_frame, -0.14, 0.14, 0.872, 0.968,
                      (0.055, 0.060, 0.072, 0.55), notch=0.025, corners=('tl', 'br'))
            _tac_outline(self.hud_jump_frame, -0.14, 0.14, 0.872, 0.968, TAC_LINE,
                         notch=0.025, corners=('tl', 'br'), thickness=1.3)
            _tac_fill(self.hud_jump_frame, -0.18, -0.145, 0.913, 0.927, TAC_ACCENT)
            _tac_fill(self.hud_jump_frame, 0.145, 0.18, 0.913, 0.927, TAC_ACCENT)
            self.hud_jump_timer = OnscreenText(
                text='0.0s', pos=(0, 0.92), scale=0.07, fg=(1, 1, 1, 0.96),
                align=TextNode.ACenter, mayChange=True, parent=self.aspect2d)
            self.hud_jump_info = OnscreenText(
                text='결승선까지 점프! (떨어지면 마지막 발판으로)', pos=(0, 0.84),
                scale=0.035, fg=(0.8, 0.85, 0.9, 0.9), align=TextNode.ACenter,
                mayChange=False, parent=self.aspect2d)

    def _update_jump_hud(self):
        if getattr(self, 'hud_jump_timer', None) is not None:
            t = time.monotonic() - self._jump_start_t
            self.hud_jump_timer.setText(f'{t:.1f}s')

    def _jump_to_start(self, invuln=False):
        """시작점으로 복귀 — 낙하(invuln=False) 또는 사망(invuln=True, 2초 무적)."""
        self.player_pos = Vec3(self._spawn_pos.x, self._spawn_pos.y,
                               self._jump.get('spawn_top', 0.3) + 0.15)
        self.player_yaw = self._spawn_yaw
        self.player_vz = 0.0
        self.on_ground = True
        if invuln:
            self.core_integrity = self.core_integrity_max
            self.INVULN_DUR = 2.0
            self._grant_invuln()

    def _jump_finish(self):
        """결승 도달 — 솔로는 완주(승리), 시간 기록."""
        if self._jump_finished:
            return
        self._jump_finished = True
        self._jump_time = time.monotonic() - self._jump_start_t
        print(f'[jump] 도착! 완주 시간 {self._jump_time:.1f}s', flush=True)
        self._end_match(True)

    def _jump_update(self, dt):
        """점프맵 1프레임 — 타이머 + 결승 판정 + 낙하 시 시작점 복귀."""
        if self._match_over or self._jump_finished:
            return
        if self._barriers_active:
            self._jump_start_t = time.monotonic()   # 시작 카운트다운 중엔 타이머 0
            self._update_jump_hud()
            return
        self._update_jump_hud()
        finish_y = self._jump.get('finish_y', 37.0)
        start_y = self._jump.get('start_y', -12.5)
        if self.player_pos.y >= finish_y:
            self._jump_finish()
            return
        if self.on_ground and self.player_pos.z < 0.25 and self.player_pos.y > start_y:
            # 바닥(낙하) + 시작구역 지남 → 처음 출발점으로 복귀.
            self._jump_to_start(invuln=False)

    def _setup_remote_avatar(self):
        """상대용 ybot Actor 하나 더 생성 — 평범한 3인칭 월드 Actor.
        내 1인칭 트릭(머리뼈 카메라 부착/어깨 피벗 pitch/walk-bob/hips anchor 보정/
        바디 메쉬 숨김)은 일절 적용하지 않는다. 첫 패킷 수신 전까지 숨김."""
        av = Actor(BAM_PATH)
        av.reparentTo(self.render)
        av.setPos(0, 0, 0)
        av.setH(180)                  # self.ybot 과 동일한 +180 기준
        # 사망 애니 — 플레이어 모델(Y Bot)의 네이티브 'Death' 사용. 외부 death_headshot.bam
        # 을 loadAnims 하면 Mixamo cm 스케일 보정이 안 맞아 몸이 거대해지므로 안 씀.
        # (적가 최종적으로 눕는 포즈도 Y Bot 'Death' 라 결과적으로 동일.)
        self._remote_death_anim = 'Death' if 'Death' in self.anim_names else None
        idle = 'Idle' if 'Idle' in self.anim_names else (
            self.anim_names[0] if self.anim_names else None)
        if idle:
            av.loop(idle)
            self._remote_anim = idle
        av.hide()                     # remote_state 도착 전엔 안 보이게
        self.remote_avatar = av
        # 발로란트식 빨간 테두리 — 상대(적)가 눈에 잘 띄게. av 가 숨으면 같이 숨고
        # 사망 처리(av.hide)에도 함께 정리된다(자식).
        self._remote_outline = self._attach_outline(av)

        # 상대 손에 무기 부착 — 로컬(right_hand_joint + weapon_anchor + _weapons)을
        # 그대로 복제. av 는 subpart 가 없으니 part='modelRoot' 로 RightHand 본 expose.
        rhand_name = next(
            (j.getName() for j in av.getJoints()
             if j.getName().endswith('RightHand')), None)
        self._remote_hand = (av.exposeJoint(None, 'modelRoot', rhand_name)
                             if rhand_name else None)
        self._remote_weapon_anchor = self.render.attachNewNode('remote_weapon_anchor')
        # 로컬과 동일한 순서/배치 상수로 등록 → 인덱스 매핑이 로컬과 일치(0=권총 1=소총).
        self._register_remote_weapon('pistol', WEAPON_PATH, WEAPON_LOCAL_SCALE,
                                     WEAPON_LOCAL_POS, WEAPON_LOCAL_HPR)
        self._register_remote_weapon('rifle', RIFLE_PATH, RIFLE_LOCAL_SCALE,
                                     RIFLE_LOCAL_POS, RIFLE_LOCAL_HPR,
                                     prerot=RIFLE_LOCAL_PREROT)

        # 상대 사운드(총소리/재장전/발소리) — 거리별 음량을 재생할 때마다 setVolume 하므로
        # 로컬 사운드와 섞이지 않게 별도 인스턴스로 로드한다. (없으면 빈 리스트/None → 무음)
        self._r_sfx_shot = self._load_sfx_pool('shot.wav', 4)
        self._r_sfx_m16 = self._load_sfx_pool('m16sound.mp3', 8)
        self._r_sfx_reload = self._load_sfx('Reload.wav')
        self._r_sfx_foot = [s for s in (self._load_sfx('f1.mp3'),
                                        self._load_sfx('f2.mp3'),
                                        self._load_sfx('f3.mp3')) if s is not None]

        # 상대 플레이어 히트박스 — 적와 동일한 본 기반 캡슐/머리 구를 av 본으로 구성.
        self._remote_hitboxes = self._build_remote_hitboxes(av)

        # 상대 총알 궤적(트레이서) — 로컬 self.tracer 와 동일한 모양의 월드 노드 1개.
        ls_rt = LineSegs('remote_tracer')
        ls_rt.setThickness(1)
        ls_rt.setColor(1.0, 0.9, 0.55, 0.65)
        ls_rt.moveTo(0, 0, 0)
        ls_rt.drawTo(0, 30, 0)                # local +Y 로 30m
        self._remote_tracer = self.render.attachNewNode(ls_rt.create())
        self._remote_tracer.setTransparency(True)
        self._remote_tracer.setLightOff()
        self._remote_tracer.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd))
        self._remote_tracer.setBin('fixed', 99)
        self._remote_tracer.setDepthWrite(False)
        self._remote_tracer.hide()

        print('[net] 상대 아바타 준비 (첫 패킷까지 숨김) '
              f'무기 {len(self._remote_weapon_order)}종 '
              f'히트박스 {len(self._remote_hitboxes)}개', flush=True)

    def _register_remote_weapon(self, name, path, scale, pos, hpr, prerot=(0, 0, 0)):
        """상대 아바타용 무기 등록 — 로컬 _register_weapon 의 배치 로직(prerot +
        scale/pos/hpr, AR-10 소품 제거)을 그대로 따르되, 1인칭 트릭/슬라이드/muzzle 은
        빼고 '손에 보이기'만 한다. _remote_weapon_anchor 의 자식으로 붙여 숨겨둔다."""
        if not path.exists():
            return
        try:
            model = self.loader.loadModel(path)
        except Exception as e:
            print(f'[net] 상대 무기 {name} 로드 실패: {e}', flush=True)
            return
        for _prop in ('7.62x51 mag.001', '76251'):   # AR-10 딸려오는 소품 제거(로컬과 동일)
            for _np in model.findAllMatches(f'**/*{_prop}*'):
                _np.removeNode()
        model.flattenLight()
        node = self._remote_weapon_anchor.attachNewNode(f'remote_{name}')
        model.reparentTo(node)
        model.setHpr(*prerot)
        node.setScale(scale)
        node.setPos(*pos)
        node.setHpr(*hpr)
        node.setTwoSided(True)
        node.hide()
        self._remote_weapons[name] = node
        self._remote_weapon_order.append(name)

    def _show_remote_weapon(self, widx):
        """무기 인덱스(0=권총 1=소총)에 맞는 상대 무기만 show, 나머지 hide.
        로컬이 무기를 바꾸면 패킷의 인덱스가 바뀌어 상대 화면 손 총도 바뀐다."""
        if not self._remote_weapon_order:
            return
        name = (self._remote_weapon_order[widx]
                if 0 <= widx < len(self._remote_weapon_order) else None)
        if name == self._remote_weapon_shown:
            return
        for n, nd in self._remote_weapons.items():
            nd.show() if n == name else nd.hide()
        self._remote_weapon_shown = name

    # --- 상대 사운드(거리별 음량) + 발사/재장전 이벤트 ------------------------

    def _remote_dist_volume(self, base, near, far):
        """상대 아바타와 내 위치 거리로 음량을 스케일해 반환.
        near 이내 = base(최대), far 이상 = 0(안 들림), 그 사이는 선형 감쇠.
        (가까울수록 크게 — 총소리/발소리/재장전 공통.)"""
        if self._remote_smooth is None:
            return 0.0
        d = (self._remote_smooth - self.player_pos).length()
        if d <= near:
            return base
        if d >= far:
            return 0.0
        return base * (1.0 - (d - near) / (far - near))

    def _play_pool_vol(self, pool, idx_attr, vol):
        """겹침 풀에서 라운드로빈 재생하되 이번 재생 음량을 vol 로 설정."""
        if not pool or vol <= 0.0 or self.paused:
            return
        i = getattr(self, idx_attr)
        s = pool[i]
        s.setVolume(vol)
        s.play()
        setattr(self, idx_attr, (i + 1) % len(pool))

    # --- 아레나 스폰 배리어 라운드 흐름 -------------------------------------

    def _arena_update(self, dt):
        """스폰 배리어 흐름 — 양쪽 준비되면 5초 카운트다운, 끝나면 배리어 제거
        (가둠 해제) + shimmer fade out + FIGHT! 배너. 아레나(online) 전용."""
        # 데스캠/유예(사망 후) — 끝나면 시점 복구. PvP/AI 는 라운드 리셋, 축구는 죽은
        # 사람만 부활(공/경기는 계속). 데스캠 동안은 그 외 정지. 단 축구는 공이 계속
        # 굴러가야 하므로 여기서 return 하지 않고 아래로 흐른다(_soccer_update 가 구동).
        if self._deathcam_t > 0.0:
            self._deathcam_t -= dt
            if self._deathcam_t <= 0.0:
                was_victim = self._dead       # 내가 죽은 쪽이었나(킬러는 계속 플레이 중)
                self._exit_deathcam()
                if self.soccer_mode or self.paint_mode:
                    if was_victim:
                        self._soccer_respawn_self()   # 나만 부활(무적) — 라운드 리셋 X
                    elif self.ai_mode:
                        self._ai_respawn()            # 봇이 죽었음 → 스폰 복귀 + 무적
                else:
                    self._arena_round_reset()
            if not (self.soccer_mode or self.paint_mode):
                return
        # shimmer fade out (해제 후 진행)
        if self._shimmer_fading and self._shimmer_cards:
            self._shimmer_a = max(0.0, self._shimmer_a - dt / 0.6)
            for card in self._shimmer_cards:
                card.setColor(IMMUNE_COLOR[0], IMMUNE_COLOR[1], IMMUNE_COLOR[2],
                              self._shimmer_a)
            if self._shimmer_a <= 0.0:
                self._shimmer_fading = False
                for card in self._shimmer_cards:
                    card.hide()
        # FIGHT! 배너 잔여 시간
        if self._fight_t > 0.0:
            self._fight_t -= dt
            if self._fight_t <= 0.0:
                self.hud_countdown.hide()
        # 카운트다운 — 배리어가 살아있는 동안만.
        if not self._barriers_active:
            return
        # 스폰 자동 배정 — 첫 상대 패킷의 nonce(rs[10]) 비교로 A/B 확정.
        if not self._role_decided:
            rs = self.remote_state
            if rs is not None and len(rs) >= 11 and rs[10] != 0:
                self._decide_role(rs[10])
            elif self.soccer_mode:
                # 축구는 로비 없이 진행 — 상대 nonce 가 일정 시간 안 오면 혼자(A) 시작.
                self._soccer_wait_t += dt
                if self._soccer_wait_t > 3.0:
                    self._am_a = not self._spawn_b
                    self._role_decided = True
                    self._countdown_t = 5.0
                return
            else:
                return                    # 아직 상대 nonce 없음 → 대기
        # 준비방 — 양쪽 준비완료 전까지 카운트다운 보류. 상대 이름/준비 상태 갱신.
        if self._in_lobby:
            self._update_lobby()
            if self._ready and self._remote_ready:
                self._exit_lobby()        # 준비방 종료 → 커서 잡고 카운트다운
                self._countdown_t = 5.0
            return
        if self._countdown_t is None:
            return                        # 준비방 종료 후 _exit_lobby 가 5.0 설정
        self._countdown_t -= dt
        if self._countdown_t > 0.0:
            self.hud_countdown.setText(str(int(ceil(self._countdown_t))))
            self.hud_countdown.show()
        else:
            self._arena_release()

    def _decide_role(self, remote_nonce):
        """상대 nonce 와 비교해 스폰을 확정(큰 쪽=A spawns[0], 작은 쪽=B spawns[1]).
        동률(극히 드묾)이면 둘 다 A로 떨어질 수 있으나 32비트라 사실상 무시.
        확정 즉시 해당 스폰으로 텔레포트(두 포켓 다 가둬져 있어 안전)."""
        am_a = self._nonce >= remote_nonce
        idx = 0 if am_a else 1
        sp = self._arena_data['spawns'][idx]
        self._spawn_pos = Vec3(sp[0], sp[1], 0)
        self._spawn_yaw = sp[2]
        self.player_pos = Vec3(self._spawn_pos)
        self.player_yaw = self._spawn_yaw
        self.player_vz = 0.0
        self.on_ground = True
        self._role_decided = True
        self._am_a = am_a                 # 축구 공 권위 + 득점 매핑
        # 축구는 로비가 없으므로 역할 확정 즉시 킥오프 카운트다운 시작.
        if self.soccer_mode and self._countdown_t is None:
            self._countdown_t = 5.0
        print(f'[arena] 스폰 자동배정 — 나={"A" if am_a else "B"} '
              f'({sp[0]},{sp[1]}) nonce {self._nonce} vs {remote_nonce}', flush=True)

    def _arena_release(self):
        """카운트다운 종료 — 배리어를 walls 에서 같은 객체로 remove(가둠 해제) +
        shimmer fade 시작 + FIGHT! 배너. 이때부터 이동 자유 = 게임 시작."""
        for w in self._spawn_barriers:
            if w in self.level_collider.walls:
                self.level_collider.walls.remove(w)
        self._barriers_active = False
        self._countdown_t = 0.0
        self._shimmer_fading = True
        self.hud_countdown.setText('FIGHT!')
        self.hud_countdown.setFg((1, 0.45, 0.3, 1))
        self.hud_countdown.show()
        self._fight_t = 1.2
        print('[arena] 배리어 해제 — FIGHT!', flush=True)

    def _handle_remote_events(self, rs):
        """패킷의 shot_seq/ reloading 변화를 감지해 상대 발사음·재장전 모션/소리 재생.
        첫 패킷은 기준값만 잡고 아무 것도 재생하지 않는다(접속 직후 오발 방지)."""
        widx, reloading, shot_seq = rs[5], rs[6], rs[7]
        is_rifle = (0 <= widx < len(self._remote_weapon_order)
                    and self._remote_weapon_order[widx] == 'rifle')
        # 발사 — 카운터가 직전과 다르면 '새 발사'. 거리별 음량 총소리 + 총알 궤적.
        if self._remote_last_shot_seq is None:
            self._remote_last_shot_seq = shot_seq      # 첫 수신은 baseline 만
        elif shot_seq != self._remote_last_shot_seq:
            self._remote_last_shot_seq = shot_seq
            if is_rifle and self._r_sfx_m16:
                self._play_pool_vol(self._r_sfx_m16, '_r_sfx_m16_i',
                                    self._remote_dist_volume(1.3, 5.0, 90.0))
            else:
                self._play_pool_vol(self._r_sfx_shot, '_r_sfx_shot_i',
                                    self._remote_dist_volume(1.0, 5.0, 90.0))
            self._show_remote_tracer(rs)               # 상대 총알 궤적
        # 재장전 — 0→1 상승 에지에서 모션 + 소리(한 번만).
        if reloading and not self._remote_last_reloading:
            self._play_remote_reload(is_rifle)
        self._remote_last_reloading = reloading

        # PvP 체력 — 상대가 나에게 입힌 누적 피해(rs[8])의 증가분만큼 내 체력을 깎는다.
        dmg_total = rs[8]
        if self._remote_last_dmg_total is None:
            self._remote_last_dmg_total = dmg_total     # 첫 수신은 baseline 만
        elif dmg_total != self._remote_last_dmg_total:
            delta = (dmg_total - self._remote_last_dmg_total) & 0xFFFF
            self._remote_last_dmg_total = dmg_total
            if delta > 0 and self._pvp_dead_t <= 0.0:
                self._apply_pvp_damage(delta)

        # PvP 킬 — 상대 사망 누적(rs[9])이 늘면 내가 처치한 것(1:1). 배너 + 킬 사운드.
        deaths = rs[9]
        if self._remote_last_deaths is None:
            self._remote_last_deaths = deaths           # 첫 수신은 baseline 만
        elif deaths != self._remote_last_deaths:
            self._remote_last_deaths = deaths
            self._on_remote_player_killed()

    def _play_remote_reload(self, is_rifle):
        """상대 아바타에 재장전 단발 모션 + 거리별 음량 재장전 소리.
        단일 파트 Actor 라 전신 단발로 재생하고, 재생 시간 동안 loco 를 억제한다."""
        av = self.remote_avatar
        if av is None:
            return
        anim = ('RifleReload' if (is_rifle and 'RifleReload' in self.anim_names)
                else ('Reload' if 'Reload' in self.anim_names else None))
        if anim is not None:
            av.play(anim)
            self._remote_anim = anim
            # 재생 시간만큼 loco 루프 억제 → 끝나면 _update_remote_avatar 가 자동 복귀.
            self._remote_action_t = av.getDuration(anim)
        if self._r_sfx_reload is not None:
            # 작게 — base 0.55. 가까울수록 크게, 24m 너머는 0(안 들림). near 3m 이내 최대.
            vol = self._remote_dist_volume(0.55, 3.0, 24.0)
            if vol > 0.0:
                self._r_sfx_reload.setVolume(vol)
                self._r_sfx_reload.play()

    def _play_remote_footstep(self):
        """상대 발소리 한 발 — f1/f2/f3 중 직전과 다른 것을, 거리별 음량으로."""
        pool = self._r_sfx_foot
        if not pool:
            return
        vol = self._remote_dist_volume(23.4, 2.0, 26.0)  # base 23.4 = 직전(7.8)의 3배 증폭(가까울 때 크게)
        if vol <= 0.0:
            return                        # 너무 멀면 안 들림 → 재생 생략
        n = len(pool)
        i = random.randrange(n) if n > 1 else 0
        while n > 1 and i == self._r_last_foot_i:
            i = random.randrange(n)
        self._r_last_foot_i = i
        pool[i].setVolume(vol)
        pool[i].play()

    # --- 상대 플레이어 히트박스(PvP 명중 판정) ------------------------------

    def _build_remote_hitboxes(self, av):
        """상대 아바타 본을 Zombie.HITBOX_SPEC 와 동일하게 expose →
        (npa, npb, r, zone) 리스트. 없는 본이 낀 항목은 건너뜀(실패 시 빈 리스트)."""
        boxes = []
        try:
            names = [j.getName() for j in av.getJoints()]
            cache = {}

            def expose(suffix):
                if suffix in cache:
                    return cache[suffix]
                full = next((n for n in names if n.endswith(suffix)), None)
                np_j = av.exposeJoint(None, 'modelRoot', full) if full else None
                cache[suffix] = np_j
                return np_j

            for a, b, r, zone in Zombie.HITBOX_SPEC:
                npa, npb = expose(a), expose(b)
                if npa is None or npb is None:
                    continue
                boxes.append((npa, npb, r, zone))
        except Exception as e:
            print('[net] 상대 히트박스 생성 실패:', e, flush=True)
        return boxes

    def _remote_hit_test(self, cam_pos, ray_dir, max_t):
        """사격 ray vs 상대 아바타 히트박스. max_t 보다 가까운 최단 (t, zone, world_pos)
        반환, 없으면 None. 아바타 미접속(숨김)이면 검사 안 함."""
        av = self.remote_avatar
        if av is None or av.isHidden() or not self._remote_hitboxes:
            return None
        best = None
        for npa, npb, r, zone in self._remote_hitboxes:
            a = npa.getPos(self.render)
            b = a if npb is npa else npb.getPos(self.render)
            if zone == 'head':
                off = Vec3(0, 0, Zombie.HEAD_UP_OFFSET)
                a = a + off
                b = b + off
            t = _ray_capsule(cam_pos, ray_dir, a, b, r)
            if t is None or t < 0.0 or t >= max_t:
                continue
            max_t = t
            best = (t, zone, Vec3(cam_pos + ray_dir * t))
        return best

    def _bullet_blocked(self, cam, rdir, t_hit):
        """사격 ray(cam, rdir 정규화)가 벽/플랫폼에 막혀 t_hit(상대까지 거리)보다
        먼저 차단되는지 3D 로 판정. 벽은 실제 높이까지만 막아(낮은 엄폐는 위로 넘겨
        쏠 수 있음), 벽 끝단의 두께 확장은 제거 + margin 인셋 → 모서리 옆 살짝 보이는
        적도 맞는다(과한 차단 수정)."""
        ox, oy, oz = cam.x, cam.y, cam.z
        dx, dy, dz = rdir.x, rdir.y, rdir.z
        m = 0.10                          # 끝단 여유(모서리 피킹 관대)
        for w in self.level_collider.walls:
            if abs(w.ay - w.by) < 1e-6:   # 수평벽(긴축 x) — 끝단만 인셋, 두께 정확
                bx0, bx1 = min(w.ax, w.bx) + m, max(w.ax, w.bx) - m
                by0, by1 = w.y0, w.y1
            else:                         # 수직벽(긴축 y)
                bx0, bx1 = w.x0, w.x1
                by0, by1 = min(w.ay, w.by) + m, max(w.ay, w.by) - m
            if bx1 <= bx0 or by1 <= by0:
                continue
            hgt = getattr(w, 'height', WALL_HEIGHT)
            t = _ray_aabb(ox, oy, oz, dx, dy, dz, bx0, bx1, by0, by1, 0.0, hgt)
            if t is not None and 1e-4 < t < t_hit - 1e-4:
                return True
        for p in self._platforms:         # 올라타는 박스도 윗면 높이까지 총알 차단
            t = _ray_aabb(ox, oy, oz, dx, dy, dz,
                          p['x0'] + m, p['x1'] - m, p['y0'] + m, p['y1'] - m,
                          0.0, p['top'])
            if t is not None and 1e-4 < t < t_hit - 1e-4:
                return True
        return False

    def _on_remote_player_hit(self, zone, world_pos):
        """상대 플레이어 명중 — 적와 같은 피드백(피격음 + 파티클 + 데미지 숫자).
        동기화 전용 1:1 모드라 HP/사망/점수는 없고 '맞았다' 피드백만 준다."""
        dmg = Zombie.DAMAGE.get(zone, 5)
        if zone == 'head' and getattr(self, '_head_onekill', False):
            dmg = max(dmg, 100)
        self._play_pool(self.sfx_hit, '_hit_i')
        self._spawn_hit_particle(world_pos)
        self._spawn_damage_number(world_pos, dmg)
        self._show_hitmarker()      # 적 명중 — 조준점에 흰 X (처치 시 아래서 레드로)
        if self.ai_mode:
            if self._ai_invuln_t > 0.0:
                return                       # 봇 부활 무적 — 피해 무효
            # AI 대결 — 로컬 HP 를 직접 깎고, 0 이하면 처치 처리(점수/데스캠/리셋).
            self.ai_hp -= dmg
            self._ai_slow_t = self.HIT_SLOW_DUR   # 봇도 피격 시 잠깐 감속
            print(f'[ai] AI 명중 zone={zone} dmg={dmg} → hp={self.ai_hp}', flush=True)
            if self.ai_hp <= 0:
                self._show_hitmarker(kill=True)   # 처치 — 레드 히트마커로 덮어쓰기
                if self.paint_mode:      # 봇 처치 위치를 내 색으로 칠함(부위별 반경)
                    self._paint_on_kill((self._ai_pos.x, self._ai_pos.y),
                                        zone, self._paint_my_id)
                    self._spawn_health_pack(self._ai_pos.x, self._ai_pos.y)  # 시체 위 힐팩
                self.ai_hp = self.ai_max_hp
                if self.jump_mode:
                    # 점프맵 — 킬배너+사운드는 띄우되(처치 피드백), 데스캠/라운드리셋은
                    # 안 하고 봇을 코스 처음으로 되돌리고 2초 무적(레이스 후퇴).
                    self._on_zombie_killed(zone)   # 발로란트 킬배너 + 콤보 + 사운드
                    self._ai_invuln_t = 2.0
                    self._ai_jump_reset_route()
                    self._show_ai_invuln_ring()
                else:
                    self._on_remote_player_killed()
            return
        # 누적 피해 적립 → 다음 송신 패킷으로 상대에게 전달되어 상대 체력이 깎인다.
        self._dmg_dealt = (self._dmg_dealt + dmg) & 0xFFFF
        print(f'[pvp] 상대 명중 zone={zone} dmg={dmg} 누적={self._dmg_dealt}',
              flush=True)

    def _show_hitmarker(self, kill=False):
        """적 명중 — 조준점에 X(히트마커)를 0.18초 점멸. 일반 명중=흰색,
        처치(kill=True)=레드. (디자인 .hitx.white / .hitx.red)"""
        if getattr(self, 'hitmarker', None) is None:
            return
        if kill:
            self.hitmarker.setColorScale(2.0, 0.22, 0.25, 1.0)   # 흰 베이스 → 레드
        else:
            self.hitmarker.setColorScale(1.0, 1.0, 1.0, 1.0)     # 흰색 그대로
        self.hitmarker.show()
        self._hitmarker_t = 0.18
        # 팝 — 크게(1.4) 떴다 빠르게 1.0 으로 settle. 명중 순간(상태 전환)에만 start.
        pop = getattr(self, '_hm_pop', None)
        if pop is not None:
            pop.finish()
        self.hitmarker.setScale(1.4)
        self._hm_pop = LerpScaleInterval(self.hitmarker, 0.09, 1.0,
                                         startScale=1.4, blendType='easeOut')
        self._hm_pop.start()

    def _start_ammo_panel_slide(self):
        """무기 교체 시 우하단 탄약 패널이 살짝 내려갔다(clip-out) 다시 올라오는
        (clip-in) 슬라이드. 무기 변경(상태 전환) 시점에만 인터벌 start — 매 프레임
        setPos 하지 않는다. online·솔로 공통(무기 교체는 로컬 동작)."""
        panel = getattr(self, '_ammo_plate', None)
        if panel is None:
            return
        z0 = getattr(self, '_ammo_plate_z0', 0.0)
        sl = getattr(self, '_ammo_slide', None)
        if sl is not None:
            sl.finish()
        panel.setPos(0, 0, z0)
        drop = 0.05
        self._ammo_slide = Sequence(
            LerpPosInterval(panel, 0.08, (0, 0, z0 - drop),
                            startPos=(0, 0, z0), blendType='easeIn'),
            LerpPosInterval(panel, 0.16, (0, 0, z0),
                            startPos=(0, 0, z0 - drop), blendType='easeOut'),
        )
        self._ammo_slide.start()

    def _show_dmg_flash(self, old_hp, new_hp):
        """체력바에서 방금 닳은 구간 위에 하얀 직사각형을 띄워 '팍' 커지며 페이드아웃.
        직사각형 = 닳은 체력 폭(체력바의 new_hp~old_hp 구간)."""
        if old_hp <= new_hp:
            return
        mx = max(1.0, float(self.core_integrity_max))
        r0 = max(0.0, min(1.0, old_hp / mx))   # 닳기 전 비율
        r1 = max(0.0, min(1.0, new_hp / mx))   # 닳은 후 비율
        seg_w = (r0 - r1) * self._php_w        # 닳은 구간 폭
        cx = self._php_x + (r0 + r1) * 0.5 * self._php_w   # 닳은 구간 중심 x
        if getattr(self, 'php_dmg_flash', None) is None:
            self.php_dmg_flash = DirectFrame(
                frameColor=(1, 1, 1, 0.9),
                frameSize=(-0.5, 0.5, -self._php_h, self._php_h),
                parent=self.a2dBottomLeft)
            self.php_dmg_flash.setBin('fixed', 25)   # 채움 위에
            self.php_dmg_flash.setTransparency(True)
            self.php_dmg_flash.hide()
            self._dmg_flash_t = 0.0
        # 닳은 구간 폭에 맞춰 X 스케일(프레임은 폭 1), 중심에 배치.
        self.php_dmg_flash['frameSize'] = (-seg_w * 0.5, seg_w * 0.5,
                                           -self._php_h, self._php_h)
        self.php_dmg_flash.setPos(cx, 0, self._php_z)
        self.php_dmg_flash.setColor(1, 1, 1, 0.9)
        self.php_dmg_flash.setScale(1.0)
        self.php_dmg_flash.show()
        self._dmg_flash_dur = 0.32
        self._dmg_flash_t = 0.32

    def _update_dmg_flash(self, dt):
        """데미지 플래시 — 닳은 구간 직사각형이 세로로 팍 커지며 알파 1→0."""
        if getattr(self, '_dmg_flash_t', 0.0) <= 0.0:
            return
        self._dmg_flash_t -= dt
        p = 1.0 - max(0.0, self._dmg_flash_t) / self._dmg_flash_dur   # 0→1
        # 세로로 크게(2.6배)·가로로 약간(1.3배) 팍 커지며 페이드.
        self.php_dmg_flash.setScale(1.0 + 0.3 * p, 1.0, 1.0 + 1.6 * p)
        self.php_dmg_flash.setColor(1, 1, 1, 0.9 * (1.0 - p))
        if self._dmg_flash_t <= 0.0:
            self.php_dmg_flash.hide()

    def _apply_pvp_damage(self, amount):
        """상대 총에 맞아 내 체력(core_integrity) 감소. 피격 방향 아크 + 0 되면 사망."""
        if self._match_over or self._barriers_active or self._deathcam_t > 0.0:
            return                        # 매치 종료/카운트다운/데스캠 중엔 피해 없음
        if self._invuln_t > 0.0:
            return                        # 부활 무적 — 피해 무효
        old_hp = self.core_integrity
        self.core_integrity = max(0, self.core_integrity - amount)
        self._show_dmg_flash(old_hp, self.core_integrity)   # 체력바 닳은 구간 플래시
        if self.core_integrity < old_hp:
            self._trigger_dmg_vignette()                    # 가장자리 레드 플래시
            self._trigger_shake(2.6, 0.30)                  # 화면 흔들림(총상은 더 세게)
            self._slow_t = self.HIT_SLOW_DUR                # 피격 후 잠깐 감속
        # 피격 방향 — 상대 아바타 위치를 source 로 빨간 아크 표시(적 피격과 동일).
        if self._remote_smooth is not None:
            self._show_damage_dir(self._remote_smooth)
        print(f'[pvp] 피격 -{amount} → 체력 {self.core_integrity}', flush=True)
        if self.core_integrity <= 0:
            self._pvp_die()

    def _on_remote_player_killed(self):
        """상대를 처치(상대 사망 카운터 증가 감지) — 킬 배너 + 사운드 + 내 점수 +1.
        내 점수가 WIN_SCORE(10) 이상이면 매치 승리."""
        if self._match_over:
            return
        self._on_zombie_killed('body')   # kills+1 + 콤보/킬 사운드 + 발로란트 킬 배너
        self._my_score += 1
        self._update_score_hud()
        print(f'[pvp] 상대 처치! 점수 {self._my_score}:{self._enemy_score}', flush=True)
        if not self.soccer_mode and not self.paint_mode \
                and self._my_score >= self.WIN_SCORE:
            self._end_match(True)
        else:
            # 축구/땅따먹기: 킬은 승리 조건이 아님. 상대만 잠깐 쓰러뜨림(경기는 계속).
            self._enter_deathcam(victim=False)   # 자유 이동 → 라운드 리셋 안 함

    def _update_score_hud(self):
        """상단 중앙 점수 텍스트 갱신 (online 일 때만 보임)."""
        if self.paint_mode:
            return                        # 땅따먹기는 킬 점수 안 씀(타이머+칸수 HUD 별도)
        if self.soccer_mode:
            mine = self._goals_a if self._am_a else self._goals_b
            opp = self._goals_b if self._am_a else self._goals_a
            self.hud_score_cap.setText('FIRST TO 5')
        else:
            mine = self._my_score
            opp = self._enemy_score
            self.hud_score_cap.setText('FIRST TO 10')
        self.hud_score_me.setText(str(mine))
        self.hud_score_op.setText(str(opp))

    def _end_match(self, won):
        """매치 종료 — 결과창(승/패 + 킬/데스) 표시 + 이후 정지. 진행 중이면 데스캠도 정리."""
        self._match_over = True
        # 게임 종료 슬로우모션 — 이 순간부터 모든 이동/총알/모션이 천천히 흐른다.
        self._time_scale_target = self.SLOWMO_FACTOR
        # 데스캠 중이었다면 시점/시체 정리(결과창 잘 보이게).
        self._deathcam_t = 0.0
        self._exit_deathcam()
        self.hud_countdown.hide()
        self._hide_match_huds()       # 슬로우모션 피날레 때부터 인게임 UI 숨김
        print(f'[pvp] 매치 종료 — {"WIN" if won else "LOSE"} '
              f'kills={self._my_score} deaths={self._enemy_score}', flush=True)
        # 결과창은 곧장 띄우지 않고, 슬로우모션으로 마지막 장면(처치 순간)을 ~1.8초
        # (실시간) 보여준 뒤에 띄운다 — 어두운 결과 패널이 화면을 덮기 전에 슬로우모션을
        # 감상할 수 있게. 중복 예약 방지.
        if not getattr(self, '_return_scheduled', False):
            self._return_scheduled = True
            self._pending_match_won = won
            self.taskMgr.doMethodLater(1.8, self._reveal_match_result,
                                       'reveal_match_result')

    def _hide_match_huds(self):
        # 매치 종료~결산 동안 인게임 UI 전부 숨김(조준점/탄약/체력/점수/킬피드 +
        # 모드별 상단 타이머·점수 + 피격 아크). 슬로우모션 피날레 때부터 깔끔하게.
        self._set_ingame_hud_visible(False)
        for nm in ('hud_paint_timer', 'hud_paint_a', 'hud_paint_colon',
                   'hud_paint_b', 'hud_paint_frame', 'hud_jump_timer',
                   'hud_jump_info', 'hud_jump_frame', 'hud_goal_banner',
                   'hud_countdown'):
            w = getattr(self, nm, None)
            if w is not None:
                w.hide()
        self._dmg_dir_t = 0.0
        if getattr(self, '_dmg_arc_geom', None) is not None:
            self._dmg_arc_geom.removeNode()
            self._dmg_arc_geom = None

    def _build_results_screen(self, won, kicker, title, sub, stats):
        # 디자인 ResultsScreen — 좌측정렬: 킥커(틱+라벨) + 큰 타이틀(Anton, 승=레드)
        # + 서브 + 스탯 행(라벨/값, 첫 값 승=레드) + 버튼. 인게임 HUD 는 숨긴다.
        self._tac_fonts()
        self._hide_match_huds()        # 인게임 HUD/모드 HUD/피격 아크 전부 숨김
        ar = self.getAspectRatio()
        lx = -ar * 0.82
        root = DirectFrame(frameColor=(0.043, 0.047, 0.055, 0.97),
                           frameSize=(-2, 2, -1, 1), parent=self.aspect2d)
        root.setBin('fixed', 90)
        root.setTransparency(1)
        self._results_root = root
        groups = []                                   # (노드, 등장 지연)

        def grp(delay):
            g = root.attachNewNode('rg')
            g.setTransparency(1)
            groups.append((g, delay))
            return g

        # 킥커
        gk = grp(0.0)
        _tac_fill(gk, lx, lx + 0.10, 0.418, 0.426, TAC_ACCENT if won else TAC_STEEL)
        OnscreenText(parent=gk, text=kicker, pos=(lx + 0.135, 0.41), scale=0.028,
                     fg=TAC_TEXT_2, align=TextNode.ALeft, font=self._tac_label_font,
                     mayChange=False)
        # 타이틀
        gt = grp(0.07)
        OnscreenText(parent=gt, text=title, pos=(lx - 0.012, 0.18), scale=0.22,
                     fg=(TAC_ACCENT if won else TAC_TEXT_1), align=TextNode.ALeft,
                     font=self._tac_hero_font, mayChange=False)
        # 서브
        gs = grp(0.13)
        OnscreenText(parent=gs, text=sub, pos=(lx, 0.05), scale=0.030,
                     fg=TAC_TEXT_2, align=TextNode.ALeft, font=self._tac_label_font,
                     mayChange=False)
        # 스탯 행
        srx = lx + 0.86
        for i, (k, v) in enumerate(stats):
            zr = -0.07 - i * 0.10
            gr = grp(0.19 + i * 0.06)
            _tac_fill(gr, lx, srx, zr - 0.05, zr - 0.0486, TAC_LINE)   # 하단 구분선
            OnscreenText(parent=gr, text=k, pos=(lx, zr - 0.012), scale=0.026,
                         fg=TAC_TEXT_2, align=TextNode.ALeft,
                         font=self._tac_label_font, mayChange=False)
            OnscreenText(parent=gr, text=str(v), pos=(srx, zr - 0.018), scale=0.05,
                         fg=(TAC_ACCENT if (i == 0 and won) else TAC_TEXT_1),
                         align=TextNode.ARight, font=self._tac_display_font,
                         mayChange=False)
        # 버튼 + 카운트다운
        bz = -0.07 - len(stats) * 0.10 - 0.10
        gb = grp(0.19 + len(stats) * 0.06 + 0.06)
        acc_lbl = 'REMATCH' if self.online_mode else 'RETRY'
        self._tac_button(gb, acc_lbl, (lx + 0.19, 0, bz), 0.36, 0.10,
                         self._retry_match, variant='accent', arrow=True)
        self._tac_button(gb, 'RETURN TO MENU', (lx + 0.72, 0, bz), 0.52, 0.10,
                         self._return_to_main_menu, variant='ghost')
        self._results_groups = groups
        self._animate_results_in()

    def _animate_results_in(self):
        # 등장 — 각 그룹이 살짝 왼쪽(투명)에서 제자리(불투명)로 슬라이드, 스태거.
        # (일시정지는 아래→위, 여긴 요청대로 좌→우 이동.) 매치종료 중엔 글로벌
        # 클럭이 정상이라 인터벌로 재생.
        for g, delay in getattr(self, '_results_groups', []):
            g.setColorScale(1, 1, 1, 0)
            g.setX(-0.14)
            Sequence(
                Wait(delay),
                Parallel(
                    LerpPosInterval(g, 0.26, (0, 0, 0), (-0.14, 0, 0),
                                    blendType='easeOut'),
                    LerpColorScaleInterval(g, 0.26, (1, 1, 1, 1),
                                           (1, 1, 1, 0), blendType='easeOut')),
            ).start()

    def _retry_match(self):
        # REMATCH/RETRY — 같은 모드로 재시작(플래그 relaunch). 복합/AI대결은 메뉴로.
        flag = None
        if self.online_mode and not (self.soccer_mode or self.paint_mode
                                     or self.jump_mode):
            flag = '--online'
        elif self.soccer_mode and not self.online_mode:
            flag = '--soccer'
        elif self.paint_mode and not self.online_mode:
            flag = '--paint'
        elif self.jump_mode and not self.online_mode:
            flag = '--jump'
        if flag is None:
            self._return_to_main_menu()
            return
        import os
        import subprocess
        try:
            self._net_shutdown()
        except Exception:
            pass
        try:
            kw = {}
            if sys.platform == 'win32':
                kw['creationflags'] = (subprocess.DETACHED_PROCESS
                                       | subprocess.CREATE_NEW_PROCESS_GROUP)
            subprocess.Popen([sys.executable, os.path.abspath(__file__), flag],
                             cwd=os.path.dirname(os.path.abspath(__file__)), **kw)
        except Exception as e:
            print('[retry] 재시작 실패:', e, flush=True)
        self.userExit()

    def _reveal_match_result(self, task):
        """슬로우모션 잠시 후 결산화면(ResultsScreen)을 띄우고 메인 복귀 카운트다운."""
        won = getattr(self, '_pending_match_won', False)
        if getattr(self, 'hud_goal_banner', None) is not None:
            self.hud_goal_banner.hide()       # 축구 '골!' 배너 숨김
        # 모드별 타이틀/서브/스탯.
        if self.jump_mode:
            title = 'FINISH' if won else 'DEFEAT'
            sub = 'COURSE CLEARED' if won else 'DID NOT FINISH'
            t = getattr(self, '_jump_time', 0.0)
            stats = [['TIME', f'{t:.1f}S']]
        elif self.paint_mode:
            mine = self._paint_count.get(self._paint_my_id, 0)
            opp = self._paint_count.get(self._paint_opp_id, 0)
            title = 'VICTORY' if won else 'DEFEAT'
            sub = 'ZONE DOMINATED' if won else 'ZONE LOST'
            stats = [['MY TILES', mine], ['ENEMY TILES', opp]]
        elif self.soccer_mode:
            mine = self._goals_a if self._am_a else self._goals_b
            opp = self._goals_b if self._am_a else self._goals_a
            title = 'VICTORY' if won else 'DEFEAT'
            sub = 'OBJECTIVE SECURED' if won else 'OPERATOR DOWN'
            stats = [['GOALS', mine], ['CONCEDED', opp]]
        else:
            title = 'VICTORY' if won else 'DEFEAT'
            sub = 'OBJECTIVE SECURED' if won else 'OPERATOR DOWN'
            stats = [['KILLS', self._my_score], ['DEATHS', self._enemy_score]]
        self._build_results_screen(won, 'MATCH RESULT', title, sub, stats)
        # 버튼 클릭용 커서 표시.
        props = WindowProperties()
        props.setCursorHidden(False)
        props.setMouseMode(WindowProperties.M_absolute)
        self.win.requestProperties(props)
        # 자동 복귀 없음 — RETURN TO MENU 버튼을 눌러야 메인 화면으로 간다.
        return Task.done

    def _return_to_main_menu(self):
        # 게임 월드(적/네트워크/HUD/액터…)를 안전히 되감는 대신, 프로세스를 새로
        # 띄워 깨끗한 상태의 시작 메뉴로 복귀한다(모드 인자 없이 실행 → 항상 메뉴).
        # 네트워크 소켓을 먼저 닫고, 새 프로세스는 현재 env(PYTHONUTF8 등)를 상속.
        import os
        import subprocess
        try:
            self._net_shutdown()
        except Exception:
            pass
        try:
            kw = {}
            if sys.platform == 'win32':
                # 종료되는 현재 프로세스/콘솔에 묶이지 않게 새 프로세스로 완전 분리 —
                # 부모가 닫혀도 새 메뉴 창이 독립적으로 살아남는다.
                kw['creationflags'] = (subprocess.DETACHED_PROCESS
                                       | subprocess.CREATE_NEW_PROCESS_GROUP)
            subprocess.Popen([sys.executable, os.path.abspath(__file__)],
                             cwd=os.path.dirname(os.path.abspath(__file__)), **kw)
        except Exception as e:
            print('[menu] 재시작 실패:', e, flush=True)
        self.userExit()

    def _pvp_die(self):
        """체력 0 — 내 사망 +1(상대 점수 +1). 상대가 10점이면 패배(매치 종료),
        아니면 라운드 리셋(양쪽 스폰 복귀 + 5초 후 재시작). 내 누적 사망 횟수를
        올려 상대가 '처치'를 인지(킬 배너/점수)하게 한다."""
        self._deaths = (self._deaths + 1) & 0xFF
        self._enemy_score = self._deaths   # 상대가 나를 죽인 횟수 = 상대 점수
        self._update_score_hud()
        print(f'[pvp] 사망 — 점수 {self._my_score}:{self._enemy_score}', flush=True)
        if self.jump_mode:
            # 점프맵 — 데스캠 없이 즉시 시작점 복귀 + 2초 무적(레이스 계속).
            self._jump_to_start(invuln=True)
            return
        if self.paint_mode:      # 내 죽은 자리를 상대 색으로 칠함(상대가 처치한 것)
            self._paint_on_kill((self.player_pos.x, self.player_pos.y),
                                'body', self._paint_opp_id)
        if not self.soccer_mode and not self.paint_mode \
                and self._enemy_score >= self.WIN_SCORE:
            self._end_match(False)         # 매치 종료
        else:
            self._enter_deathcam(victim=True)   # 사망 후 3인칭(축구/땅=5초) → 부활

    def _drop_weapon(self, pos, yaw, name='rifle'):
        """사망 시 손에 들고 있던 무기를 바닥에 떨군다 — 해당 무기 모델을 로드해 죽은
        자리 바닥에 옆으로 눕혀 놓는다. _dropped_weapons 에 등록(데스캠 끝나면 정리)."""
        if name == 'rifle':
            path, scale, prerot = RIFLE_PATH, RIFLE_LOCAL_SCALE, RIFLE_LOCAL_PREROT
        else:
            path, scale, prerot = WEAPON_PATH, WEAPON_LOCAL_SCALE, (0, 0, 0)
        if path is None or not path.exists():
            return
        try:
            model = self.loader.loadModel(path)
        except Exception as e:
            print('[drop] 무기 로드 실패:', e, flush=True)
            return
        for _prop in ('7.62x51 mag.001', '76251'):   # AR-10 딸려오는 소품 제거
            for _np in model.findAllMatches(f'**/*{_prop}*'):
                _np.removeNode()
        model.flattenLight()
        drop = self.render.attachNewNode('dropped_weapon')
        model.reparentTo(drop)
        model.setHpr(*prerot)
        drop.setScale(scale)
        drop.setTwoSided(True)
        # 바닥에 옆으로 쓰러뜨려 놓기 — 죽은 방향(yaw) + 옆으로 굴림(R=90).
        drop.setPos(pos.x, pos.y, 0.05)
        drop.setHpr(yaw, 0, 90)
        self._dropped_weapons.append(drop)

    def _clear_dropped_weapons(self):
        for d in self._dropped_weapons:
            try:
                d.removeNode()
            except Exception:
                pass
        self._dropped_weapons = []

    def _make_death_corpse(self, pos, h):
        """현재 적이 죽을 때와 '똑같이' — 적 모델(X Bot) + DeathHeadshot 을 1.5배속
        으로 재생하는 시체 Actor 생성. (DeathHeadshot 은 X Bot 본에서만 정상 스케일이라
        플레이어 Y Bot 대신 적 모델로 시체를 만든다.) NodePath 반환."""
        c = Actor(ZOMBIE_BAM)
        c.reparentTo(self.render)
        c.setPos(pos)
        c.setH(h)
        if ZOMBIE_DEATH_BAM.exists():
            try:
                c.loadAnims({Zombie.DEATH_ANIM: ZOMBIE_DEATH_BAM})
                c.play(Zombie.DEATH_ANIM)
                c.setPlayRate(Zombie.DEATH_PLAY_RATE, Zombie.DEATH_ANIM)
            except Exception as e:
                print('[pvp] 시체 death 애니 실패:', e, flush=True)
        return c

    def _enter_deathcam(self, victim):
        """사망 처리 3초 유예. victim=True(죽은 사람): 시점 고정 + 내 시체(현재 적와
        동일한 DeathHeadshot)를 머리 위 3인칭으로 본다. victim=False(죽인 사람): 3초
        자유 이동, 상대(죽은 자)는 시체로 쓰러짐. 3초 뒤 _exit_deathcam + 라운드 리셋."""
        if self._match_over:
            return
        # 축구는 부활까지 5초(요청), 그 외 PvP/AI 는 3초.
        self._deathcam_t = 5.0 if self.soccer_mode else self.DEATHCAM_DUR
        if victim:
            self._dead = True
            self._death_yaw = self.player_yaw
            # 1인칭 팔/총 숨기고, 그 자리에 적과 같은 death 시체 생성(데스캠으로 봄).
            self.ybot.hide()
            self.weapon_anchor.hide()
            self._corpse = self._make_death_corpse(self.player_pos,
                                                   self.player_yaw + 180)
            # 들고 있던 총을 바닥에 떨군다(1인칭 총은 숨겼으니 월드에 별도 모델로).
            self._drop_weapon(self.player_pos, self.player_yaw,
                              self.weapon_name or 'rifle')
            print('[pvp] 사망 — 3초 데스캠', flush=True)
        else:
            # 죽은 상대 — Y Bot 아바타 숨기고 그 자리에 적과 같은 death 시체로 대체.
            av = self.remote_avatar
            if av is not None:
                self._corpse = self._make_death_corpse(av.getPos(self.render),
                                                       av.getH())
                # 손에 떠 있던 상대 무기를 숨기고 바닥에 떨군다.
                if self._remote_weapon_anchor is not None:
                    self._remote_weapon_anchor.hide()
                self._drop_weapon(av.getPos(self.render), av.getH() - 180,
                                  self._remote_weapon_shown or 'rifle')
                av.hide()
                # 손에 든 무기 앵커는 render 직속(av 자식이 아님)이라 av.hide() 로는
                # 안 사라진다 → 따로 숨겨야 시체 옆에 총이 공중에 안 뜬다.
                if self._remote_weapon_anchor is not None:
                    self._remote_weapon_anchor.hide()
                self._remote_hidden_for_death = True
            print('[pvp] 처치 — 3초 자유 이동', flush=True)

    def _exit_deathcam(self):
        """데스캠 종료 — 시체 제거 + 1인칭/상대 아바타 복구. (라운드 리셋 직전 호출.)"""
        if self._corpse is not None:
            try:
                self._corpse.cleanup()
                self._corpse.removeNode()
            except Exception:
                pass
            self._corpse = None
        if self._dead:
            self._dead = False
            self.ybot.show()
            self.weapon_anchor.show()
        if self._remote_hidden_for_death:
            self._remote_hidden_for_death = False
            if self.remote_avatar is not None:
                self.remote_avatar.show()
            if self._remote_weapon_anchor is not None:
                self._remote_weapon_anchor.show()   # 손 무기 복구
        # 바닥에 떨군 무기 제거(다음 라운드 깨끗하게).
        self._clear_dropped_weapons()
        self._remote_action_t = 0.0
        self._remote_anim = None

    def _arena_round_reset(self):
        """한 명이 죽으면 호출 — 내 스폰으로 복귀 + 체력/탄 회복 + 스폰 배리어 재가둠
        + 5초 카운트다운 후 재시작. (양 클라가 각자 사망/처치를 인지하는 시점에
        독립적으로 호출 — 둘 다 똑같이 리셋되어 라운드가 다시 시작된다.)"""
        if self._match_over:
            return
        self.player_pos = Vec3(self._spawn_pos)
        self.player_yaw = self._spawn_yaw
        self.player_pitch = 0.0
        self.player_vz = 0.0
        self.on_ground = True
        self.core_integrity = self.core_integrity_max
        self.ammo = self.ammo_max
        for w in self._weapons.values():     # 새 라운드 — 모든 무기 풀충전
            w['ammo'] = w['ammo_max']
        self._pvp_dead_t = 0.0
        # 스폰 배리어 재가둠(중복 add 방지) + shimmer 다시 보이게.
        if self._spawn_barriers and not self._barriers_active:
            self.level_collider.walls.extend(self._spawn_barriers)
            self._barriers_active = True
        self._shimmer_fading = False
        self._shimmer_a = 0.25
        for card in self._shimmer_cards:
            card.show()
            card.setColor(IMMUNE_COLOR[0], IMMUNE_COLOR[1], IMMUNE_COLOR[2],
                          self._shimmer_a)
        # AI 대결 — AI 도 스폰 복귀 + 체력 회복.
        if self.ai_mode:
            self._ai_pos = Vec3(self._ai_spawn)
            self.ai_hp = self.ai_max_hp
            self._ai_fire_t = 0.0
            self._ai_ammo = self.AI_AMMO_MAX
            self._ai_reload_t = 0.0
            if self.remote_avatar is not None:
                self.remote_avatar.setPos(self._ai_pos)
        # 5초 카운트다운 재시작 — _arena_update 가 끝에서 배리어 제거 + FIGHT!.
        self._countdown_t = 5.0
        self.hud_countdown.setFg((1, 0.92, 0.4, 1))
        print('[arena] 라운드 리셋 — 5초 후 재시작', flush=True)

    def _pvp_respawn(self, task=None):
        """스폰 지점(아레나면 내 스폰)으로 복귀 + 체력/탄창 회복."""
        self.player_pos = Vec3(self._spawn_pos)
        self.player_yaw = self._spawn_yaw
        self.player_vz = 0.0
        self.on_ground = True
        self.core_integrity = self.core_integrity_max
        self.ammo = self.ammo_max
        for w in self._weapons.values():     # 리스폰 — 모든 무기 풀충전
            w['ammo'] = w['ammo_max']
        self._pvp_dead_t = 0.0
        print('[pvp] 리스폰 완료', flush=True)
        return Task.done

    def _show_remote_tracer(self, rs):
        """상대 발사 시 상대 무기 머즐에서 상대 조준 방향으로 총알 궤적(트레이서) 표시.
        로컬 self.tracer 와 동일한 방식 — 월드 노드를 위치/방향만 잡고 잠깐 보였다 숨김."""
        tr = self._remote_tracer
        if tr is None:
            return
        # 머즐 위치 — 상대 무기 앵커(손 본)를 따라가므로 그 월드 좌표를 시작점으로.
        if (self._remote_weapon_anchor is not None
                and not self._remote_weapon_anchor.isEmpty()):
            tr.setPos(self._remote_weapon_anchor.getPos(self.render))
        elif self._remote_smooth is not None:
            tr.setPos(self._remote_smooth + Vec3(0, 0, self.head_height))
        # 방향 — 상대 yaw/pitch(rs[3], rs[4]). 로컬 트레이서와 동일한 heading 규칙.
        tr.setHpr(rs[3], rs[4], 0)
        tr.show()
        self._remote_tracer_t = self.tracer_dur

    def _connect_relay(self):
        """릴레이 서버에 TCP 접속. 실패해도 크래시 없이 경고만 찍고 계속(싱글처럼)."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            host = getattr(self, '_relay_host', None) or RELAY_HOST
            port = getattr(self, '_relay_port', None) or RELAY_PORT
            s.connect((host, port))
            s.settimeout(None)        # 이후 blocking recv/send
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = s
            self._net_alive = True
            atexit.register(self._net_shutdown)   # 프로세스 종료 시 소켓 정리
            threading.Thread(target=self._net_recv_loop, daemon=True).start()
            print(f'[net] 릴레이 접속 성공 {host}:{port}', flush=True)
        except Exception as e:
            self._sock = None
            self._net_alive = False
            print(f'[net] 릴레이 접속 실패 ({e}) — 네트워크 없이 계속', flush=True)

    def _net_recv_loop(self):
        """데몬 스레드: TCP 스트림에서 정확히 NET_STATE_SIZE(21)바이트씩 프레임을
        모아 언패킹 → self.remote_state 에 최신값만 저장. 부분수신/연결끊김 안전."""
        sock = self._sock
        buf = b''
        try:
            while self._net_alive:
                data = sock.recv(4096)
                if not data:
                    break             # 상대/서버 연결 종료(스트림 끝)
                buf += data
                # TCP 는 스트림 — 21바이트가 다 모였을 때만 한 프레임으로 해석.
                while len(buf) >= NET_STATE_SIZE:
                    frame = buf[:NET_STATE_SIZE]
                    buf = buf[NET_STATE_SIZE:]
                    try:
                        (x, y, z, yaw, pitch, widx, reloading,
                         shot_seq, dmg_total, deaths, nonce,
                         name_b, ready,
                         bx, by, bz, sa, sb, kseq,
                         kox, koy, koz, kdx, kdy, kdz, kpow
                         ) = struct.unpack(NET_STATE_FMT, frame)
                    except struct.error:
                        continue
                    name = name_b.split(b'\x00', 1)[0].decode('utf-8', 'ignore')
                    # 참조 교체(원자적) — 위치/시점 + 무기 + 재장전/발사 + 피해 + 사망 +
                    # nonce + (준비방용) 이름 + 준비완료 플래그 + (축구) 공/점수/킥 이벤트.
                    self.remote_state = (x, y, z, yaw, pitch, widx, reloading,
                                         shot_seq, dmg_total, deaths, nonce,
                                         name, ready,
                                         bx, by, bz, sa, sb, kseq,
                                         kox, koy, koz, kdx, kdy, kdz, kpow)
                    # 위치 스냅샷을 도착시각과 함께 버퍼에 적재(메인이 시간보간에 사용).
                    # 직전 스냅샷에서 크게 점프했으면(리스폰 등 텔레포트) 버퍼를 비워
                    # 보간을 끊고 새 위치부터 다시 시작 → 맵을 가로질러 미끄러지지 않게.
                    with self._remote_buf_lock:
                        if self._remote_buf:
                            pt = self._remote_buf[-1]
                            if ((x - pt[1]) ** 2 + (y - pt[2]) ** 2
                                    + (z - pt[3]) ** 2
                                    > REMOTE_TELEPORT_DIST ** 2):
                                self._remote_buf.clear()
                        self._remote_buf.append(
                            (time.monotonic(), x, y, z, yaw))
        except OSError:
            pass                      # 끊김 — 마지막 remote_state 유지
        finally:
            self._net_alive = False
        print('[net] 수신 스레드 종료', flush=True)

    def _net_send(self, dt):
        """내 위치/시점/무기인덱스를 ~NET_SEND_HZ 로 스로틀해서 고정 21바이트로 전송."""
        if self._sock is None or not self._net_alive:
            return
        self._net_send_t += dt
        if self._net_send_t < (1.0 / NET_SEND_HZ):
            return
        self._net_send_t = 0.0
        try:
            name_b = self.player_name.encode('utf-8')[:NET_NAME_BYTES]
            # 축구 — 권위(A)면 공 위치·점수를 싣는다(B 는 0; 무시됨). 킥 이벤트는 양쪽 다 실음.
            if self.soccer_mode and self._am_a and self._ball is not None:
                bx, by, bz = self._ball.pos.x, self._ball.pos.y, self._ball.pos.z
                sa, sb = self._goals_a & 0xFF, self._goals_b & 0xFF
            else:
                bx = by = bz = 0.0
                sa = sb = 0
            ko, kd = self._kick_off, self._kick_dir
            pkt = struct.pack(NET_STATE_FMT,
                              self.player_pos.x, self.player_pos.y,
                              self.player_pos.z, self.player_yaw,
                              self.player_pitch,
                              self._weapon_idx & 0xFF,            # 0=권총 1=소총 (uint8)
                              1 if self._reload_oneshot else 0,   # 재장전 중 플래그
                              self._net_shot_seq & 0xFF,          # 발사 카운터
                              self._dmg_dealt & 0xFFFF,           # 상대에 입힌 누적 피해
                              self._deaths & 0xFF,                # 내 누적 사망 횟수
                              self._nonce & 0xFFFFFFFF,           # 스폰 배정용 랜덤
                              name_b,                             # 준비방 표시 이름(24바이트)
                              1 if self._ready else 0,            # 준비완료 플래그
                              bx, by, bz,                         # (축구) 공 위치(권위만 유효)
                              sa, sb,                             # (축구) 점수 A,B(권위만 유효)
                              self._kick_seq & 0xFF,              # (축구) 내 킥 카운터
                              ko.x, ko.y, ko.z,                   # (축구) 킥 명중 오프셋
                              kd.x, kd.y, kd.z,                   # (축구) 킥 방향
                              self._kick_power)                   # (축구) 킥 파워
            self._sock.sendall(pkt)
        except OSError as e:
            print(f'[net] 송신 실패 ({e}) — 연결 종료', flush=True)
            self._net_alive = False

    @staticmethod
    def _lerp_angle(a, b, t):
        """각도(deg) 최단호 보간 — 359°→1° 가 358°가 아니라 2° 로 돌게."""
        d = (b - a + 180.0) % 360.0 - 180.0
        return a + d * t

    def _update_remote_avatar(self, dt):
        """수신한 remote_state 로 상대 아바타를 부드럽게 보간 이동 + 방향 + run/idle.
        몸 전체 pitch 는 적용 안 함(요청대로). 데이터 없으면 숨김 유지."""
        av = self.remote_avatar
        if av is None:
            return
        rs = self.remote_state        # 스레드가 최신값으로 교체 — 한 번만 읽음
        if rs is None:
            return                    # 아직 첫 패킷 없음 → 숨김 유지(크래시 없음)
        # 스냅샷 보간 — 상대를 REMOTE_INTERP_DELAY 과거 시점으로 두고, 그 시점을 감싸는
        # 두 스냅샷 사이를 시간비율로 보간한다. 패킷이 몰리거나(버스트) 비어도(렉) 등속
        # 으로 흐르게 해 '찔끔 순간이동'을 없앤다. (외삽은 안 함 — 방향전환 시 오버슈트
        # 튐 방지. 버퍼 고갈 시엔 최신 스냅샷에서 잠깐 멈췄다 재개.)
        render_t = time.monotonic() - REMOTE_INTERP_DELAY
        with self._remote_buf_lock:
            buf = list(self._remote_buf)
        if not buf:
            ipos = Vec3(rs[0], rs[1], rs[2]); iyaw = rs[3]   # 버퍼 비면 최신값(드묾)
        elif render_t <= buf[0][0]:
            s = buf[0]; ipos = Vec3(s[1], s[2], s[3]); iyaw = s[4]
        elif render_t >= buf[-1][0]:
            s = buf[-1]; ipos = Vec3(s[1], s[2], s[3]); iyaw = s[4]  # 고갈 → 멈춤
        else:
            a = buf[0]; b = buf[-1]
            for nxt in buf[1:]:        # render_t 를 감싸는 A(<=) / B(>) 탐색
                if nxt[0] > render_t:
                    b = nxt; break
                a = nxt
            span = b[0] - a[0]
            al = (render_t - a[0]) / span if span > 1e-6 else 0.0
            ipos = Vec3(a[1] + (b[1] - a[1]) * al,
                        a[2] + (b[2] - a[2]) * al,
                        a[3] + (b[3] - a[3]) * al)
            iyaw = self._lerp_angle(a[4], b[4], al)
        if self._remote_smooth is None:
            self._remote_smooth = Vec3(ipos)   # 첫 등장은 즉시 배치(점프 방지)
            self._remote_prev = Vec3(ipos)
            av.show()
        elif ((ipos - self._remote_smooth).lengthSquared()
                > REMOTE_TELEPORT_DIST ** 2):
            self._remote_smooth = Vec3(ipos)   # 텔레포트(리스폰/스폰배정) → 즉시 스냅
            self._remote_prev = Vec3(ipos)
        else:
            # 보간 결과 위로 가벼운 잔여 스무딩 — 버퍼 경계/재개 시 미세한 끊김도 흡수.
            self._remote_smooth += ((ipos - self._remote_smooth)
                                    * min(1.0, dt * REMOTE_SMOOTH_LERP))
        av.setPos(self._remote_smooth)
        av.setH(iyaw + 180)           # yaw 만 — pitch 로 몸 전체를 기울이지 않음
        # 애니: 직전 프레임 대비 이동 속도로 run/idle 판정. 실제 있는 이름만 사용.
        moved = (self._remote_smooth - self._remote_prev).length()
        self._remote_prev = Vec3(self._remote_smooth)
        speed = moved / max(dt, 1e-5)   # 프레임율 독립 속도(m/s) — 스무딩 위치 기준
        moving = speed > 0.6            # >0.6 m/s 면 이동 중(걷기·달리기 모두 포함)

        # 발사/재장전 이벤트 — 패킷 카운터/플래그 변화를 감지해 소리 + 단발 모션 재생.
        # (위치 보간이 끝난 뒤라 거리별 음량 계산이 정확함.)
        self._handle_remote_events(rs)

        # 소총 장착 시 Rifle* 변형 로코모션을 써서 '소총 든 자세'가 상대에게 보이게.
        # (로컬 _loco_anim 과 동일한 규칙: Rifle 변형이 있으면 그걸, 없으면 기본.)
        is_rifle = (0 <= rs[5] < len(self._remote_weapon_order)
                    and self._remote_weapon_order[rs[5]] == 'rifle')

        def _ranim(base):
            if is_rifle and ('Rifle' + base) in self.anim_names:
                return 'Rifle' + base
            return base if base in self.anim_names else None

        run = _ranim('RunForward')
        idle = _ranim('Idle')
        want = run if (run and moving) else idle
        # 재장전 등 단발 모션 재생 중에는 loco 루프로 덮어쓰지 않음(억제 타이머).
        if self._remote_action_t > 0.0:
            self._remote_action_t -= dt
            if self._remote_action_t <= 0.0:
                self._remote_anim = None   # 모션 끝 → 아래에서 loco 강제 재개
        if self._remote_action_t <= 0.0 and want and want != self._remote_anim:
            av.loop(want)
            self._remote_anim = want

        # 발소리 — 상대가 이동 중이면 보폭 간격마다 한 발, 거리 가까울수록 크게.
        if moving and self._remote_action_t <= 0.0:
            self._remote_foot_t -= dt
            if self._remote_foot_t <= 0.0:
                self._play_remote_footstep()
                self._remote_foot_t = self.footstep_interval
        else:
            self._remote_foot_t = 0.0     # 멈추면 다음 이동 첫 발은 즉시

        # 상대 손에 든 무기 — av 손 본의 월드 트랜스폼을 anchor 가 따라가게.
        # (1인칭 트릭은 일절 안 씀: 머리뼈 카메라/어깨피벗/ADS 오프셋/walk-bob 전부 X.
        #  3인칭으로 그냥 손에 총만 들려 있으면 됨.) 손 본 좌표를 현재 프레임으로
        # 동기화하려고 av.update 후 읽는다(로컬 ybot.update(force=True) 와 동일 패턴).
        av.update(force=True)
        # 사망 중엔 무기를 바닥에 떨궜으니 손 무기 추적/표시를 건너뛴다(공중 고정 방지).
        if not self._remote_hidden_for_death:
            if (self._remote_weapon_anchor is not None
                    and self._remote_hand is not None
                    and not self._remote_hand.isEmpty()):
                self._remote_weapon_anchor.setPos(
                    self._remote_hand.getPos(self.render))
                self._remote_weapon_anchor.setHpr(
                    self._remote_hand.getHpr(self.render))
            # 무기 종류 동기화 — 패킷의 무기 인덱스(rs[5])에 맞는 모델만 보이게.
            self._show_remote_weapon(rs[5])

        # 상대 총알 궤적 — 잠깐 보였다 시간 지나면 숨김(로컬 tracer 와 동일 방식).
        if self._remote_tracer_t > 0.0:
            self._remote_tracer_t -= dt
            if self._remote_tracer_t <= 0.0 and self._remote_tracer is not None:
                self._remote_tracer.hide()

    def _net_shutdown(self):
        """소켓 close + 수신 스레드 종료 신호(데몬이라 프로세스와 함께 사라짐)."""
        self._net_alive = False
        s = self._sock
        self._sock = None
        if s is not None:
            try:
                s.close()
            except OSError:
                pass

    def _apply_slowmo_anim_rate(self, rate):
        """슬로우모션 동안 화면에 보이는 모든 Actor 의 골격 애니메이션 재생속도를 rate
        로 맞춘다(이동 dt 와 동기화). 매 프레임 호출해도 idempotent — 새로 시작된
        애니(예: 죽음 모션)도 즉시 같이 느려진다. 액터가 없으면 조용히 건너뜀."""
        actors = []
        if getattr(self, 'ybot', None) is not None:
            actors.append(self.ybot)
        if getattr(self, 'remote_avatar', None) is not None:
            actors.append(self.remote_avatar)
        if getattr(self, '_corpse', None) is not None:
            actors.append(self._corpse)
        for z in getattr(self, 'zombies', []):
            if getattr(z, 'actor', None) is not None:
                actors.append(z.actor)
            rep = getattr(z, 'ybot_replacement', None)
            if rep is not None and getattr(z, 'transformed', False):
                actors.append(rep)
        for a in actors:
            try:
                for an in a.getAnimNames():
                    a.setPlayRate(rate, an)
            except Exception:
                pass

    # --- main loop ----------------------------------------------------------

    def _update(self, task):
        # paused: 게임 update 통째로 skip. doMethodLater 단발 anim 콜백은 계속
        # 흘러가지만 (실시간 기반) 일시정지 중에 사용자가 할 일이 거의 없으니 OK.
        if self.paused:
            return Task.cont
        dt = ClockObject.getGlobalClock().getDt()
        # pause 직후 첫 프레임 wall-clock 누적 dt 폭발 cap — 적 워프 방지.
        if dt > 0.1:
            dt = 0.1
        # ── 슬로우모션 ─────────────────────────────────────────────────────
        # _time_scale 을 실시간(real dt) 기준으로 target 에 부드럽게 수렴시킨 뒤, 게임
        # 로직에 쓰이는 dt 를 그만큼 줄인다 → 이동/AI/총알 궤적/반동/타이머가 전부 느려짐.
        # 골격 애니메이션은 Panda 글로벌클럭으로 도니 별도로 재생속도를 같이 낮춰준다.
        if self._time_scale != self._time_scale_target:
            step = dt / max(0.001, self.SLOWMO_RAMP)
            if self._time_scale < self._time_scale_target:
                self._time_scale = min(self._time_scale_target,
                                       self._time_scale + step)
            else:
                self._time_scale = max(self._time_scale_target,
                                       self._time_scale - step)
        if self._time_scale < 0.999:
            self._apply_slowmo_anim_rate(self._time_scale)
        dt *= self._time_scale

        # 그림자 프러스텀을 플레이어 따라가게(좁은 고해상 그림자 추적).
        self._update_shadow_frustum()
        # 피격 연출 타이머 — 화면 흔들림 / 감속 감쇠.
        if self._shake_t > 0.0:
            self._shake_t = max(0.0, self._shake_t - dt)
        if self._slow_t > 0.0:
            self._slow_t = max(0.0, self._slow_t - dt)
        if self._ai_slow_t > 0.0:
            self._ai_slow_t = max(0.0, self._ai_slow_t - dt)

        # ── 온라인: 내 상태 송신(스로틀) + 상대 아바타 보간/애니 ──────────────
        # 싱글이면 online_mode=False 라 통째로 건너뜀(네트워크 코드 안 탐).
        if self.online_mode:
            self._net_send(dt)
            self._update_remote_avatar(dt)
            self._arena_update(dt)        # 스폰 배리어 카운트다운 + shimmer fade
        elif self.ai_mode:
            self._ai_update(dt)           # AI 봇 이동/조준/사격(네트워크 없음)
            self._arena_update(dt)        # 카운트다운/라운드 흐름 공유
        if self.soccer_mode:
            self._soccer_update(dt)       # 공 물리 + 골/킥오프
        if self.paint_mode:
            self._paint_update(dt)        # 3분 타이머 + 종료 판정
        if self.jump_mode:
            self._jump_update(dt)         # 타이머 + 결승/체크포인트

        # 부활 무적 타이머 — 끝나면 보호 링 숨김.
        if self._invuln_t > 0.0:
            self._invuln_t -= dt
            if self._invuln_t <= 0.0 and self._invuln_ring is not None:
                self._invuln_ring.hide()

        # 애니메이션 블렌딩 weight 수렴
        self._update_blend(dt)

        # 사격 반동 자연 감쇠 — weapon_anchor 위치에 적용 (카메라엔 영향 없음)
        decay = min(1.0, dt * self.recoil_decay)
        self.recoil_back += (0.0 - self.recoil_back) * decay

        # 발사 쿨다운 감쇠
        if self.shoot_cooldown_t > 0:
            self.shoot_cooldown_t -= dt
        if self._empty_click_t > 0:
            self._empty_click_t -= dt

        # 탄 퍼짐 연사 카운터 — reset 초 동안 발사 없으면 0 으로 (다음 첫발 정확).
        if self._spray_shots > 0:
            self._spray_idle += dt
            reset_t = WEAPON_SPRAY.get(self.weapon_name, {}).get('reset', 0.25)
            if self._spray_idle > reset_t:
                self._spray_shots = 0

        # 피격 방향 아크 fade — 시간 지나며 alpha 1→0, 끝나면 숨김.
        if self._dmg_dir_t > 0 and self._dmg_arc_geom is not None:
            self._dmg_dir_t -= dt
            if self._dmg_dir_t <= 0:
                self._dmg_arc_geom.hide()
            else:
                self._dmg_arc_geom.setColorScale(
                    1, 1, 1, self._dmg_dir_t / self._dmg_dir_dur)

        # 연발(full-auto) — 좌클릭 hold 동안 쿨다운마다 자동 발사. (반자동은 클릭당 1발)
        if getattr(self, '_auto_fire', False) and getattr(self, '_mouse1_down', False):
            self._play_shoot_oneshot()

        # 무기 스왑 모션 진행 (팔 내림 offset _swap_z 갱신, 바닥에서 실제 교체).
        self._update_weapon_swap(dt)

        # Muzzle flash timer — 위치는 anchor parent 가 자동 처리, 크기만 fade.
        if self.muzzle_flash is not None and self.muzzle_flash_t > 0:
            self.muzzle_flash_t -= dt
            if self.muzzle_flash_t <= 0:
                self.muzzle_flash.hide()
            else:
                t_norm = self.muzzle_flash_t / self.muzzle_flash_dur
                self.muzzle_flash.setScale(
                    self.muzzle_flash_base_scale * (0.4 + 0.6 * t_norm))

        # Tracer timer — 단순히 시간 지나면 hide.
        if self.tracer_t > 0:
            self.tracer_t -= dt
            if self.tracer_t <= 0:
                self.tracer.hide()
        # 슬라이드 후퇴 감쇠 + 실제 노드 위치 적용. 모델의 +X 가 권총 뒤쪽이라
        # rest 에서 +slide_recoil 만큼 더해야 뒤로 빠지는 효과.
        if self.slide_node is not None:
            sdec = min(1.0, dt * self.slide_recoil_decay)
            self.slide_recoil += (0.0 - self.slide_recoil) * sdec
            self.slide_node.setX(self.slide_rest_x + self.slide_recoil)

        # 마우스 룩 — 1인칭이면 player_yaw/pitch, editor 면 editor_yaw/pitch.
        # 준비방·결산(매치 종료) 동안은 커서가 자유(버튼 클릭용)라 마우스룩/포인터
        # 재중심을 건너뛴다.
        if self.win.hasPointer(0) and not self._in_lobby and not self._match_over:
            md = self.win.getPointer(0)
            dx = md.getX() - self._win_cx
            dy = md.getY() - self._win_cy
            self.win.movePointer(0, self._win_cx, self._win_cy)
            if self._first_frame:
                self._first_frame = False  # 초기화 직후 점프 방지
            elif self.editor_mode:
                self.editor_yaw -= dx * self.mouse_sens
                self.editor_pitch -= dy * self.mouse_sens
                self.editor_pitch = max(-89.0, min(89.0, self.editor_pitch))
            elif not self._dead:
                # 1인칭 yaw + pitch — 위·아래 ±89° (총 178°) 자유 시야.
                # ADS 시 감도 낮춤 → 손/총 좌우 swing 천천히·작게. (사망 중엔 동결)
                sens = self.mouse_sens * (
                    1.0 + (self.ads_mouse_factor - 1.0) * self.aim_t)
                self.player_yaw -= dx * sens
                self.player_pitch -= dy * sens
                self.player_pitch = max(-89.0, min(89.0, self.player_pitch))

        if self.editor_mode:
            # editor free-cam: 카메라가 보는 방향 + 우 + 위. Space=상, 잠금 없음.
            yr = radians(self.editor_yaw)
            pr = radians(self.editor_pitch)
            forward = Vec3(-sin(yr) * cos(pr), cos(yr) * cos(pr), sin(pr))
            right_v = Vec3(cos(yr), sin(yr), 0)
            mv = Vec3(0, 0, 0)
            if self.keys['w']: mv += forward
            if self.keys['s']: mv -= forward
            if self.keys['d']: mv += right_v
            if self.keys['a']: mv -= right_v
            if self.keys['space']: mv += Vec3(0, 0, 1)
            if mv.length() > 0:
                mv.normalize()
                self.editor_pos += mv * (self.editor_speed * dt)
        else:
            # WASD 이동 + 점프 (1인칭, 서있는 상태에서만 — 무릎/transition 중 잠금)
            if self.kneel_state == 'stand':
                yr = radians(self.player_yaw)
                forward = Vec3(-sin(yr), cos(yr), 0)
                right_v = Vec3(cos(yr), sin(yr), 0)
                mv = Vec3(0, 0, 0)
                if not self._dead:        # 사망 중엔 이동 동결(데스캠 고정)
                    if self.keys['w']: mv += forward
                    if self.keys['s']: mv -= forward
                    if self.keys['d']: mv += right_v
                    if self.keys['a']: mv -= right_v
                if mv.length() > 0:
                    mv.normalize()
                    spd_mult = (1.0 + (self.ads_move_factor - 1.0) * self.aim_t) \
                        * self._weapon_speed_mult   # 무기별 속도(권총 1.3배)
                    if self._slow_t > 0.0:          # 피격 직후 잠깐 감속
                        spd_mult *= self.HIT_SLOW_MULT
                    self.player_pos += mv * (self.move_speed * spd_mult * dt)
                    # 벽 충돌 해소 (XY 평면) — 박스 안쪽으로 침투했으면 바깥으로 밀어냄.
                    nx, ny = self.level_collider.resolve(
                        self.player_pos.x, self.player_pos.y, PLAYER_RADIUS)
                    self.player_pos.x = nx
                    self.player_pos.y = ny
                    # 플랫폼(올라타는 박스) — 발이 윗면보다 step_assist 이상 낮으면
                    # 옆면이 막고, step_assist 이내면 윗면으로 스냅(올라섬). 위/근처면 자유.
                    for p in self._platforms:
                        if self.player_pos.z >= p['top'] - self._step_assist:
                            if (p['x0'] <= self.player_pos.x <= p['x1']
                                    and p['y0'] <= self.player_pos.y <= p['y1']
                                    and self.player_pos.z < p['top']):
                                self.player_pos.z = p['top']   # 윗면으로 올라섬
                                self.player_vz = 0.0
                                self.on_ground = True
                        else:
                            nx, ny = p['collider'].resolve(
                                self.player_pos.x, self.player_pos.y, PLAYER_RADIUS)
                            self.player_pos.x = nx
                            self.player_pos.y = ny
                if self.keys['space'] and self.on_ground and not self._dead:
                    self.player_vz = self.jump_speed
                    self.on_ground = False

            # 지지 높이 — 플랫폼 윗면 위(또는 step_assist 이내)에 올라타 있으면 그게 바닥.
            support = 0.0
            for p in self._platforms:
                if (p['x0'] <= self.player_pos.x <= p['x1']
                        and p['y0'] <= self.player_pos.y <= p['y1']
                        and self.player_pos.z >= p['top'] - self._step_assist
                        and p['top'] > support):
                    support = p['top']
            # 중력은 항상 적용 (무릎자세에서도)
            self.player_vz -= self.gravity * dt
            self.player_pos.z += self.player_vz * dt
            if self.player_pos.z <= support:
                self.player_pos.z = support
                self.player_vz = 0
                self.on_ground = True

            # 발소리 — 지상에서 서서 WASD 이동 중일 때 보폭 간격마다 한 발.
            # (점프 중·무릎 자세·에디터 free-cam 에선 안 남)
            stepping = (self.on_ground and self.kneel_state == 'stand'
                        and any(self.keys[k] for k in ('w', 'a', 's', 'd')))
            if stepping:
                self._footstep_t -= dt
                if self._footstep_t <= 0.0:
                    self._play_footstep()
                    # ADS 면 이동이 느려지므로(spd_mult<1) 보폭 간격도 그만큼 늘려
                    # 발소리 템포를 실제 속도(무기별 배율 포함)에 맞춘다.
                    spd_mult = (1.0 + (self.ads_move_factor - 1.0) * self.aim_t) \
                        * self._weapon_speed_mult
                    self._footstep_t = self.footstep_interval / max(0.3, spd_mult)
            else:
                self._footstep_t = 0.0   # 멈추면 다음 이동 첫 발은 즉시 재생

        # 현재 상태에 맞는 locomotion anim 선택
        self._update_locomotion()

        # 캐릭터 트랜스폼 동기화 (+ Hips XY anchor 보정 + 사격 반동 뒤로 이동).
        # 사격 반동은 캐릭터 전체를 카메라 forward 의 반대 방향으로 살짝 밀어서
        # 팔·손·권총 다 같이 뒤로 빠지게. 카메라는 아래쪽에서 보정해서 시점은 고정.
        yr_recoil = radians(self.player_yaw)
        fwd_recoil = Vec3(-sin(yr_recoil), cos(yr_recoil), 0)
        recoil_offset = fwd_recoil * (-self.recoil_back)

        # Walk bob (Z) — reload 중 + 이동키 눌렸을 때만 ramp in. 카메라에서 같은
        # bob_z 를 빼서 화면은 정적, 자기 몸·팔·총만 까딱.
        moving = any(self.keys[k] for k in ('w', 'a', 's', 'd'))
        target_bob = 1.0 if (self._reload_oneshot and moving) else 0.0
        self._walk_bob_t += ((target_bob - self._walk_bob_t)
                             * min(1.0, dt * self._walk_bob_speed))
        if self._walk_bob_t > 0.001:
            self._walk_bob_phase += dt * self._walk_bob_freq
        else:
            self._walk_bob_phase = 0.0
        bob_z = (self._walk_bob_amp_z * self._walk_bob_t
                 * sin(self._walk_bob_phase))

        # ADS body offset — player-frame (우/앞/위) 벡터를 world 로 회전해서 ybot 에
        # 더함. 카메라는 아래 setPos 에서 같은 양 -로 보정 → 시점 정적.
        yr_ads = radians(self.player_yaw)
        ads_right_w = Vec3(cos(yr_ads), sin(yr_ads), 0)
        ads_fwd_w   = Vec3(-sin(yr_ads), cos(yr_ads), 0)
        ads_offset_world = (ads_right_w * self.ads_body_offset.x
                            + ads_fwd_w * self.ads_body_offset.y
                            + Vec3(0, 0, self.ads_body_offset.z)) * self.aim_t
        # 무기별 보이는 몸 오프셋 — 항상 적용 (aim_t 무관). 카메라·히트박스 불변.
        bo = self.weapon_body_offset
        body_off_world = (ads_right_w * bo.x
                          + ads_fwd_w * bo.y
                          + Vec3(0, 0, bo.z))

        self.ybot.setPos(self.player_pos + recoil_offset
                         + Vec3(0, 0, bob_z + self._swap_z)
                         + ads_offset_world + body_off_world)
        # 일단 pitch=0 으로 세팅 → 아래에서 shoulder 피벗 트릭으로 pitch 적용.
        # 보이는 몸 회전 오프셋(weapon_body_hpr) 을 더함 — 몸+총 같이 회전(같은 축).
        # 총은 손 본을 그대로 따라가므로 몸과 동일하게 움직임. H=x P=y R=z.
        bh = self.weapon_body_hpr
        self.ybot.setHpr(self.player_yaw + 180 + bh.x, bh.y, bh.z)
        # 애니메이션을 현재 시각으로 강제 동기화. 안 하면 joint 의 world 좌표가
        # 1프레임 lag 된 상태를 반환해서 카메라가 머리에서 떨림.
        self.ybot.update(force=True)
        if self.hips_joint is not None:
            local = self.hips_joint.getPos(self.ybot)
            if self._hips_ref_local is None:
                self._hips_ref_local = Vec3(local)
            dlx = self._hips_ref_local.x - local.x
            dly = self._hips_ref_local.y - local.y
            h_rad = radians(self.ybot.getH())
            c, s = cos(h_rad), sin(h_rad)
            self.ybot.setX(self.ybot.getX() + c * dlx - s * dly)
            self.ybot.setY(self.ybot.getY() + s * dlx + c * dly)

        # 어깨 피벗 pitch — RightShoulder world 를 pre/post 캡처해서 ybot 평행이동으로
        # 보정 → 어깨가 안 움직이고 그 주위로 몸이 회전 = 어깨 축 회전 효과.
        # 1인칭이라 다리/몸통이 어색하게 움직여도 안 보이고, 팔·손·총은 어깨 주위로
        # 자연스럽게 회전.
        if (not self.editor_mode and self.rshoulder_joint is not None
                and abs(self.player_pitch) > 0.001):
            sh_up = self.rshoulder_joint.getPos(self.render)
            self.ybot.setHpr(self.player_yaw + 180 + bh.x,
                             -self.player_pitch + bh.y, bh.z)
            sh_pitched = self.rshoulder_joint.getPos(self.render)
            self.ybot.setPos(self.ybot.getPos() + (sh_up - sh_pitched))

        # ADS ramp + FOV 보간 — 우클릭 hold 동안 aim_t 가 1 로 수렴 (~110ms).
        target_aim = 1.0 if self.aiming else 0.0
        self.aim_t += ((target_aim - self.aim_t)
                       * min(1.0, dt * self.aim_speed))
        if not self.editor_mode:
            current_fov = (self.fov_hip
                           + (self.fov_ads - self.fov_hip) * self.aim_t)
            self.camLens.setFov(current_fov)

        # 카메라 배치 — shoulder pivot 기준 forward/up 평면에서 player_pitch 만큼 회전.
        # 손/총이 어꺠 축으로 회전하니 카메라도 같은 축으로 회전해서 정렬됨.
        # bob / ads 는 ybot 에만 적용했으니 camera 에 영향 X (자연히 정적).
        if self.editor_mode:
            self.camera.setPos(self.editor_pos)
            self.camera.setHpr(self.editor_yaw, self.editor_pitch, 0)
            cam_pos = self.editor_pos
        else:
            shoulder_h = 1.40   # shoulder world Z 근사 (Y Bot)
            sh_pivot = self.player_pos + Vec3(0, 0, shoulder_h)
            yr = radians(self.player_yaw)
            forward = Vec3(-sin(yr), cos(yr), 0)
            right_v = Vec3(cos(yr), sin(yr), 0)
            # pitch=0 시 카메라 offset (어깨 기준): 앞 / 위 / 좌
            cam_fwd_off = self.eye_forward_offset + self.recoil_back
            cam_up_off  = self.head_height - shoulder_h    # ≈ 0.25m
            cam_lat_off = -self.eye_lateral_offset         # 좌측
            # (forward, up) 평면에서 player_pitch 만큼 회전 → 어깨 orbit
            pp = radians(self.player_pitch)
            new_fwd = cam_fwd_off * cos(pp) - cam_up_off * sin(pp)
            new_up  = cam_fwd_off * sin(pp) + cam_up_off * cos(pp)
            cam_pos = (sh_pivot
                       + forward * new_fwd
                       + right_v * cam_lat_off
                       + Vec3(0, 0, new_up))
            self.camera.setPos(cam_pos)
            # 피격 화면 흔들림 — 남은 시간 비례 진폭으로 yaw/pitch/roll 에 랜덤 오프셋.
            if self._shake_t > 0.0:
                k = self._shake_t / max(0.001, self._shake_dur)
                a = self._shake_mag * k
                self.camera.setHpr(self.player_yaw + random.uniform(-a, a),
                                   self.player_pitch + random.uniform(-a, a),
                                   random.uniform(-a, a))
            else:
                self.camera.setHpr(self.player_yaw, self.player_pitch, 0)

        # 데스캠 — 죽은 사람은 자기 시체 머리 위(뒤쪽) 3인칭에서 내려다봄.
        if self._dead and self._corpse is not None:
            base = self._corpse.getPos(self.render)
            yr = radians(self._death_yaw)
            behind = Vec3(sin(yr), -cos(yr), 0)        # 시선 forward 의 반대
            cam_pos = base + behind * 2.6 + Vec3(0, 0, 3.6)
            self.camera.setPos(cam_pos)
            self.camera.lookAt(base + Vec3(0, 0, 0.8))

        # weapon anchor 갱신: hand 본 따라감. 이제 ybot 자체가 head 본 피벗으로
        # pitch 되어 손 본도 같이 회전 → player_pitch 를 따로 더할 필요 없음
        # (더하면 이중 적용).
        if (self.weapon is not None
                and self.right_hand_joint is not None
                and not self.right_hand_joint.isEmpty()):
            # 총은 손 본(=몸의 일부)을 그대로 따라감 → 몸과 완전히 같은 축으로 회전.
            self.weapon_anchor.setPos(self.right_hand_joint.getPos(self.render))
            self.weapon_anchor.setHpr(self.right_hand_joint.getHpr(self.render))

        # 적 AI tick — 페이드아웃 끝난 시체는 노드 정리 후 목록에서 제거.
        for z in self.zombies:
            z.update(dt, self.player_pos)
        if any(z.remove_me for z in self.zombies):
            for z in self.zombies:
                if z.remove_me:
                    z.actor.removeNode()
            self.zombies = [z for z in self.zombies if not z.remove_me]

        # 방화벽 / 게이트 tick (웨이브 모드에선 비어 있음 — 안전상 유지)
        for fw in self.firewalls:
            fw.update(dt)
        for g in self.gates:
            g.update(dt)

        # ── 웨이브 매니저 ─────────────────────────────────────────────────
        if self._spawn_points:
            if self.wave_active:
                if not any(z.hp > 0 for z in self.zombies):
                    self.wave_active = False
                    self._intermission_t = self.intermission_dur
                    self._show_gate_msg(f'WAVE {self.wave} 클리어', dur=2.0)
            else:
                self._intermission_t -= dt
                if self._intermission_t <= 0:
                    self.wave += 1
                    self._spawn_wave(self.wave)

        # 킬 콤보 윈도우 카운트다운 — 0 이 되면 다음 킬은 1단계부터.
        if self._combo_window > 0.0:
            self._combo_window = max(0.0, self._combo_window - dt)
        # 하단 콤보 게이지 갱신 (남은 시간 → 왼쪽으로 슬라이드 소진)
        self._update_combo_bar()

        # (F 처치/복원 상호작용 제거 — 적는 죽으면 페이드아웃되어 사라짐)

        # 피격 fire 파티클 — 살짝 커지며 fade out 후 제거
        for p in self._hit_particles[:]:
            p['t'] -= dt
            if p['t'] <= 0:
                p['np'].removeNode()
                self._hit_particles.remove(p)
            else:
                f = p['t'] / p['dur']                      # 1 → 0
                p['np'].setScale(p['base'] * (1.5 - 0.5 * f))   # 점점 커짐
                c = p['col']
                p['np'].setColorScale(c[0] * f, c[1] * f, c[2] * f, 1)  # 틴트+페이드

        # Damage number popup — 위로 떠오르며 fade out
        for d in self._damage_numbers[:]:
            d['t'] -= dt
            if d['t'] <= 0:
                d['np'].removeNode()
                self._damage_numbers.remove(d)
            else:
                d['np'].setZ(d['np'].getZ() + 0.6 * dt)       # 60cm/sec 위로
                alpha = d['t'] / d['dur']
                d['np'].setColorScale(1, 1, 1, alpha)

        # HUD
        self._update_hud(dt)

        return Task.cont


if __name__ == '__main__':
    # 인자 없음 → 시작 화면(타이틀 + 싱글/멀티/종료 메뉴)부터.
    # '--online' → 메뉴 건너뛰고 바로 멀티(릴레이 접속).
    # '--p2' → 아레나 스폰 B(0,15) 로 시작(상대는 인자 없이 스폰 A). 한 명만 --p2.
    # 모드를 직접 지정(--online/--p2)하면 메뉴를 건너뛴다.
    # '--soccer' → 메뉴 건너뛰고 바로 축구(릴레이 접속 + 혼자면 연습). 테스트/직접실행용.
    # '--paint' → 메뉴 건너뛰고 바로 땅따먹기 솔로(AI 봇). 테스트/직접실행용.
    online = '--online' in sys.argv
    soccer = '--soccer' in sys.argv
    paint = '--paint' in sys.argv
    jump = '--jump' in sys.argv     # 점프맵 솔로(타임트라이얼)
    spawn_b = '--p2' in sys.argv
    menu = not (online or spawn_b or soccer or paint or jump)
    ZombieGame(online=online, spawn_b=spawn_b, menu=menu, soccer=soccer,
               paint=paint, jump=jump).run()
