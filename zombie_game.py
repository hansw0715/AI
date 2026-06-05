"""
zombie_game — Mirror's Edge style 1인칭 좀비 슈터 (Panda3D)
Stage 1: 1인칭 카메라 + Y Bot 풀바디 + 기본 입력.
"""
import atexit
import random
import socket
import struct
import sys
import threading
from math import atan2, ceil, cos, degrees, radians, sin
from pathlib import Path

from direct.actor.Actor import Actor
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectSlider
from direct.gui.OnscreenImage import OnscreenImage
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from direct.interval.IntervalGlobal import (
    Func, LerpColorScaleInterval, LerpScaleInterval, Parallel, Sequence, Wait,
)
from panda3d.core import (
    AmbientLight, CardMaker, ClockObject, ColorBlendAttrib, DirectionalLight, Filename,
    Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    LineSegs, NodePath, PerspectiveLens, Quat, Spotlight, TextNode, Triangulator,
    Vec3, Vec4, WindowProperties, loadPrcFileData,
)

from level import (PLAYER_RADIUS, ZOMBIE_RADIUS, WALL_HEIGHT, Wall,
                   IMMUNE_COLOR, LESION_COLOR, build_level, build_arena)
from weapon_config import (
    WEAPON_LOCAL_SCALE, WEAPON_LOCAL_POS, WEAPON_LOCAL_HPR, WEAPON_MUZZLE_POS,
    RIFLE_LOCAL_SCALE, RIFLE_LOCAL_POS, RIFLE_LOCAL_HPR, RIFLE_MUZZLE_POS,
    RIFLE_LOCAL_PREROT, WEAPON_BODY_OFFSET, WEAPON_BODY_HPR, WEAPON_ADS_OFFSET,
    WEAPON_SPRAY)

# ── 성능 PRC: GPU 스키닝 ────────────────────────────────────────────────────
# 좀비 14마리 × Mixamo 본 67개 × CPU 정점 변환 매 프레임 = 화각에 좀비 많을 때 FPS 폭락.
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


# ── HUD 색 / 글리치 라벨 ────────────────────────────────────────────────────
# 게임의 핵심 트릭: HUD 는 플레이어를 "선한 백신 AI" 라고 믿게 만드는 공범이다.
# 평소엔 깨끗한 시안색 임상(antivirus) 톤(=거짓)으로 떠 있다가, 글리치가 터지면
# 0.x 초 동안 빨강으로 깨지며 진짜 단어(=진실)가 비친다. 같은 데이터, 라벨만 반전.
HUD_CYAN       = (0.25, 0.88, 1.00, 1.0)   # 표면 액센트
HUD_CYAN_DIM   = (0.43, 0.66, 0.72, 1.0)   # 표면 보조 라벨
HUD_WHITE      = (0.92, 0.98, 1.00, 1.0)   # 큰 숫자
HUD_RED        = (1.00, 0.18, 0.33, 1.0)   # 진실 액센트 (글리치)
HUD_RED_DIM    = (0.88, 0.34, 0.43, 1.0)   # 진실 보조 라벨
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

# 글리치 (HUD 가 일시적으로 빨강 진실 라벨로 깜빡이는 "지지직" 연출) ON/OFF.
# False 면 _trigger_glitch 가 no-op → HUD 가 항상 시안 표면 상태로 고정.
GLITCH_ENABLED = False

# (표면 거짓 라벨, 진실 라벨) — 글리치 때 진실로 교체된다.
GLITCH_LABELS = {
    'system':    ('SENTINEL // 면역 프로토콜 v3.1', 'SENT!N3L // 숙주 확산 v3.1'),
    'status':    ('\u25cf 시스템 정상 · 위협 감시 중', '\u25cf 감염체 활동 · 숙주 탐색 중'),
    'kills_lbl': ('정화 완료', '감염시킴'),
    'integ_lbl': ('코어 무결성', '바이러스 부하'),
    'ammo_lbl':  ('정화 카트리지', '감염 페이로드'),
    'zone_lbl':  ('정화 구역', '확산 범위'),
    'interact':  ('[F] 정화 / 복원', '[F] 감염 / 동화시키기'),
}


SCRIPT_DIR = Path(__file__).parent
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
# ⚠ 송신·수신 양쪽이 반드시 이 새 30바이트 포맷이어야 한다. 옛 26/25바이트 클라와
#   섞이면 프레임 정렬이 어긋나 좌표가 깨지므로, 두 클라 모두 새 버전이어야 함.
NET_STATE_FMT = '<5fBBBHBI'
NET_STATE_SIZE = struct.calcsize(NET_STATE_FMT)   # = 30
# [수정1] 상대 움직임 지연 완화 — 송신 빈도 ↑ + 수신 보간 수렴 ↑. (외삽/예측은 안 씀;
# 부작용 분리를 위해 다음 단계에서 별도로.) 둘 다 여기 상수로 빼서 튜닝 쉽게.
NET_SEND_HZ = 45.0          # 송신 스로틀(40~50Hz 권장; 위치 패킷 21바이트라 부담 적음)
REMOTE_SMOOTH_LERP = 18.0   # 상대 위치 보간 계수 min(1, dt*이값). 클수록 빨리 수렴,
#                             너무 크면 떨림 — 부드러움 유지되는 선(12 → 18).

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
# 외부 Mixamo death 애니메이션 (Death From Front Headshot) — 좀비와 동일한
# mixamorig 스켈레톤이라 actor.loadAnims 로 바인딩 가능.
ZOMBIE_DEATH_BAM = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'zombie' / 'death_headshot.bam')
)

UI_DIR = SCRIPT_DIR / 'assets' / 'ui'    # 정화 HUD PNG 자산 (시안 단색·4×·투명)


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


class Zombie:
    """좀비 한 마리 — Actor + 상태머신(IDLE/CHASE/ATTACK) + 시야 기반 AI.

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

    # Distance LOD — 플레이어로부터 이 거리 너머의 좀비는 actor.hide() + AI/anim skip.
    # 어차피 시야 25m 너머는 안 쫓아오고 벽 차폐로 시각도 막혀있어서 cost 0 으로 만들어도
    # 게임 플레이에 영향 없음. 맵 길이 ~65m → 다른 방의 좀비는 거의 다 LOD'd.
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

        # HP / health bar
        self.hp_max = 100
        self.hp = self.hp_max
        self.hp_bar_t = 0.0           # 남은 표시 시간 (sec)
        self.hp_bar_show_dur = 2.5    # 데미지 후 풀 alpha 로 보이는 시간
        self.hp_bar_fade_dur = 1.5    # 그 뒤 fade out 시간
        self._build_hp_bar()

        # Transform — F 키로 dead 좀비를 Y Bot 으로 페이드 전환.
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
        """ray(cam_pos, ray_dir 정규화) vs 이 좀비 본 히트박스들. max_t 보다 가까운
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
        """좀비 머리 위 health bar — 평소 hidden, 데미지 시 show + fade out.

        피벗(hp_bar)을 actor Z축 위(0,0,2)에 둔다 — heading 회전축 위라 좀비가
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
        # 벽 차폐 — 좀비↔플레이어 직선상에 벽이 있으면 못 봄. 도어/케이지 갭은
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
        # 피격 방향 표시용으로 이 좀비 위치도 전달.
        self.game.take_core_damage(10, self.pos)

    def start_transform(self, game):
        """DEAD 좀비 → Y Bot 으로 dual fade. 같은 self.pos / yaw + Death 마지막
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
        # 진행 중) / Transform 페이드 중 좀비는 LOD 보류해서 끊김 없이 마무리.
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
            # 발 접지 보정 페이드 — 시작엔 산 좀비와 같은 접지(낙하 0)를 유지하다,
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
                    # 벽 충돌 해소 — 좁은 통로/기둥에서 좀비가 벽 뚫고 직진하지 않게.
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
    """측면 방 입구 차단막. 쏴서 부수면 통로가 열리고 그 방 좀비(백신)가 스폰.
    그 방을 전멸시키면 cleared -> 방 바닥이 병변색으로 번진다.
    표면: 오염 잠금 해제/정화 / 진실: 격리벽 파괴/감염 확산."""
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
    전엔 잠겨서 부술 수 없다(쏘면 면역색이 튕겨냄). 다 cleared 되면 약해져
    돌파 가능 -> 부수면 전진. final_spawns 가 있으면 부순 순간 그 방 좀비를
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
            self.game._show_gate_msg('차단막 강화됨 — 양옆 방을 먼저 정화하라')
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
                                     2.4, reveal=True)   # 진실 누출
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


class ZombieGame(ShowBase):
    def __init__(self, online=False, spawn_b=False):
        super().__init__()
        # 아레나 스폰 측 — False=스폰 A(0,-15 북향), True=스폰 B(0,15 남향).
        # 두 클라이언트가 겹치지 않게 한쪽은 '--p2' 로 띄운다(릴레이는 역할 배정 못함).
        self._spawn_b = spawn_b

        # ── 온라인(1:1 멀티) 모드 플래그 + 네트워크 상태 ────────────────────
        # online=True ('--online') 일 때만 소켓 접속 + 상대 아바타 + 좀비/웨이브
        # 정지 + 튜닝키 차단. 싱글(False)은 아래 변수들을 일절 안 쓰므로 동작 동일.
        self.online_mode = online
        self.remote_state = None      # 수신 스레드가 최신 (x,y,z,yaw,pitch) 저장
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
        # 상대 플레이어 히트박스 — 좀비와 동일한 본 기반 (캡슐/머리 구). 사격 ray 로 검사.
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
        # 스폰 자동 배정 — 세션 고정 랜덤 nonce. 상대 nonce 와 비교해 큰 쪽=A, 작은=B.
        self._nonce = random.randint(1, 0xFFFFFFFF)
        self._role_decided = False        # 첫 상대 패킷의 nonce 로 스폰 확정

        # 윈도우/마우스
        props = WindowProperties()
        props.setTitle('zombie_game')
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_confined)
        self.win.requestProperties(props)
        self.disableMouse()  # ShowBase 기본 마우스-카메라 비활성
        self._is_fullscreen = False   # F11 토글 — 진짜 전체화면(작업표시줄 가림)

        # 환경
        self.setBackgroundColor(0.015, 0.020, 0.030)   # 어두운 검푸른 야간 하늘
        self._make_lights()
        # GPU 스키닝 보장 — 상단 PRC 두 플래그는 fixed-function 경로라 요즘 드라이버에선
        # 무시되고 조용히 CPU 스키닝으로 폴백하는 경우가 흔함. auto-shader 가 진짜 HW
        # 스키닝 셰이더를 생성해줘서 좀비 다수 시 vertex 변환이 GPU 로 옮겨감.
        # 부작용: 라이팅 모델 살짝 바뀜 — 톤이 어색하면 dl color/ambient 보정.
        self.render.setShaderAuto()
        self._make_ground()
        # level.py 가 render 아래에 방·벽·기둥을 만들고 collider + 좀비 spawn 좌표 반환.
        # 키트 .bam 이 있으면 단색 벽 카드를 끄고(z-fighting 방지) kit_map 메쉬로 대체.
        import os
        kit_available = USE_KIT_MAP and os.path.isfile("assets/kit/Wall_1.bam")
        self.kit_root = None
        if self.online_mode:
            # 1대1 PvP — 좀비 캠페인 레벨 대신 대칭 아레나. kit_map 미적용(단색 벽).
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
        self.move_speed = 4.0   # 좀비 추격 속도와 동일 (Zombie.move_speed)
        self.mouse_sens = 0.03    # 기본값 — ESC pause 메뉴 슬라이더로 0.02~0.30 조정
        self.jump_speed = 4.5
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

        # ── HUD (임상 안티바이러스 톤 + 글리치 진실 누출) ──────────────────
        self._interact_target = None    # 현재 가까이 있는 dead 좀비
        self.interact_range = 2.5       # m
        self._gate_msg_token = 0
        # 플레이어 코어 무결성 ("체력"). 아직 좀비 공격이 데미지를 안 주지만
        # HUD 요소로 노출 — take_core_damage() 로 깎으면 자동 반영된다.
        self.core_integrity = 100
        self.core_integrity_max = 100
        # 피격 방향 표시 — 데미지 입은 방향으로 조준점 둘레 빨간 아크, 잠깐 보이고 fade.
        self._dmg_arc_geom = None
        self._dmg_dir_t = 0.0
        self._dmg_dir_dur = 1.1         # 아크 표시 후 fade 지속(초)
        self.purified = 0               # "정화 완료" = 사실은 감염시킨 수
        # 글리치 상태: _glitch_t > 0 이면 진실 라벨/빨강으로 표시.
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

        # 좀비 spawn + 방화벽/게이트 + damage popup 텍스트 풀
        self.zombies = []
        self.firewalls = []
        self.gates = []
        self._damage_numbers = []     # [{np, t, dur}, ...] — _update 가 animate
        self._spawn_zombies()
        # 온라인: 좀비/웨이브 완전 정지 — _spawn_points 만 비우면 _update 의 웨이브
        # 매니저('if self._spawn_points:')가 통째로 안 돌아 스폰/인터미션/WAVE
        # 메시지가 전부 멈춘다. (다른 데 if 흩뿌리지 않는다.) 좀비 목록도 비움.
        if self.online_mode:
            self._spawn_points = []
            self.zombies = []
            self._setup_online()      # 상대 아바타 생성 + 릴레이 접속(데몬 수신 스레드)

        # 메인 루프
        self.taskMgr.add(self._update, 'game_update')

        # 진단: Idle 한 프레임 돌고 나서 본 이름/좌표 한 번 출력
        self.taskMgr.doMethodLater(0.3, self._dump_joints, 'dump_joints')

    def _spawn_zombies(self):
        # 웨이브 모드 — 방화벽/게이트 진행 대신, 맵의 스폰 지점들에 매 웨이브
        # 좀비를 점점 더 많이 풀어놓는다. 다 처치하면 인터미션 후 다음 웨이브.
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
        self.wave_base = 4              # 웨이브1 좀비 수
        self.wave_growth = 2            # 웨이브마다 +N
        self.intermission_dur = 4.0     # 웨이브 사이 대기(초)
        self._intermission_t = 3.0      # 첫 웨이브까지 대기

        if not ZOMBIE_BAM.exists():
            print(f'[zombie] BAM not found: {ZOMBIE_BAM}', flush=True)
            self._spawn_points = []
        print(f'[wave] {len(self._spawn_points)} 스폰 지점 준비', flush=True)

    def _spawn_wave(self, n):
        """웨이브 n 의 좀비를 스폰 지점에 분산 배치."""
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
        print(f'[wave] {n}: 좀비 {count} 스폰', flush=True)

    def _clear_corpses(self):
        """완전히 죽은(DEAD) 좀비 노드를 정리해 누적 부하를 막는다.
        변환(아군)·사망 연출/페이드 중인 좀비는 유지."""
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
        # reveal=True → 진실 누출 톤(빨강) + 짧은 글리치 동반. 게이트 돌파처럼
        # 확산이 한 단계 진행되는 순간에 쓴다 ('ASSIMILATING ZONE' 등).
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
        # 밝은 실내 — ambient 를 충분히 올려 맵 전체가 환하게. (플래시라이트 제거)
        amb = AmbientLight('ambient')
        amb.setColor(Vec4(0.62, 0.63, 0.67, 1))      # 밝은 회백색 베이스
        self.render.setLight(self.render.attachNewNode(amb))

        # 메인 디렉셔널 — 표면 음영/입체감.
        dl = DirectionalLight('dir')
        dl.setColor(Vec4(0.48, 0.48, 0.50, 1))
        dlnp = self.render.attachNewNode(dl)
        dlnp.setHpr(45, -55, 0)
        self.render.setLight(dlnp)

        # 보조 디렉셔널(반대쪽) — 그림자 지는 면도 너무 어둡지 않게 채움.
        dl2 = DirectionalLight('dir2')
        dl2.setColor(Vec4(0.26, 0.26, 0.30, 1))
        dl2np = self.render.attachNewNode(dl2)
        dl2np.setHpr(-130, -35, 0)
        self.render.setLight(dl2np)

        # 플래시라이트 제거 — 밝은 맵이라 불필요. (참조 안전용 None)
        self.flashlight = None

    def _make_ground(self):
        # level.py 의 5방 라인업(y=-2~70) + 아레나(y=-18~18)를 모두 여유 있게 덮음.
        cm = CardMaker('ground')
        cm.setFrame(-32, 32, -20, 76)
        gnd = self.render.attachNewNode(cm.generate())
        gnd.setHpr(0, -90, 0)        # XY 평면으로 눕히기 — 법선 +Z 위
        gnd.setColor(0.55, 0.55, 0.58, 1)

        # 천장 — 같은 XY 풋프린트 / z = WALL_HEIGHT 에 놓고 법선은 아래(-Z) 향함.
        # setHpr(0, 90, 0) 으로 P=+90 → 카드 법선이 -Z 로 뒤집힘 → 아래에서 비추는
        # 플래시 빛만 받음. 색은 바닥보다 어둡게 (실내 천장 톤).
        cm_c = CardMaker('ceiling')
        cm_c.setFrame(-32, 32, -20, 76)
        ceil = self.render.attachNewNode(cm_c.generate())
        ceil.setHpr(0, 90, 0)
        ceil.setZ(WALL_HEIGHT)
        ceil.setColor(0.30, 0.30, 0.34, 1)

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
        self._weapons[name] = {
            'node': node, 'slide_node': slide_node,
            'slide_rest_x': slide_rest_x, 'muzzle': muzzle,
        }
        self._weapon_order.append(name)
        print(f'[weapon] {name} registered (slide={"Y" if slide_node else "N"})',
              flush=True)

    def _equip_weapon(self, name):
        """활성 무기 교체 — show/hide + slide_node + muzzle flash 위치 갱신."""
        if name not in self._weapons:
            return
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
        # 무기별 스탯 적용 — 탄창 풀충전 + 발사간격 + 연발/헤드원킬 플래그.
        st = WEAPON_STATS.get(name, {})
        self.ammo_max = st.get('ammo_max', 8)
        self.ammo = self.ammo_max
        self.shoot_cooldown_dur = st.get('cooldown', 0.18)
        self.shoot_cooldown_t = 0.0
        self._auto_fire = st.get('auto', False)
        self._head_onekill = st.get('head_onekill', False)
        print(f'[weapon] equipped {name} '
              f'(ammo={self.ammo_max}, auto={self._auto_fire}, '
              f'head1k={self._head_onekill})', flush=True)

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
        # F 키 — 가까이 있는 dead 좀비 가 있으면 Y Bot 으로 transform 시작.
        # 표면 라벨은 "정화/복원", 실제로는 한 개체를 더 감염(동화)시키는 행위.
        if self.paused or self._interact_target is None:
            return
        self._interact_target.start_transform(self)
        self._interact_target = None
        self.interact_frame.hide()
        self.purified += 1          # "정화 완료" 카운터 (= 감염시킨 수)

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
        """카메라 ray vs 각 좀비의 본 기반 히트박스(머리 구 + 몸통/사지 캡슐).
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

        # 방화벽 / 게이트 — 좀비보다 앞에 있으면 그걸 맞힘 (좀비 무효화).
        best_barrier = None
        for b in self.firewalls + self.gates:
            s = b.ray_distance(cam_pos, ray_dir)
            if s is None or s >= best_t:
                continue
            best_t = s
            best_barrier = b
            best_z = None

        # 상대 플레이어(온라인) — 좀비/방화벽과 같은 ray 로 히트박스 검사.
        # best_t 보다 더 가까우면 상대를 맞힌 것 → 좀비/방화벽 판정 무효.
        remote_hit_pos = None
        if self.online_mode:
            res = self._remote_hit_test(cam_pos, ray_dir, best_t)
            # 총알이 벽을 못 뚫게 — 나→상대 2D 경로가 벽으로 막히면 명중 취소.
            if res is not None and not self.level_collider.segment_blocked(
                    cam_pos.x, cam_pos.y, res[2].x, res[2].y):
                best_t, best_zone, remote_hit_pos = res
                best_z = None
                best_barrier = None

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
        # 미니멀 HUD — 히트마커(명중 X) 제거.
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
        """좀비 처치 시 호출 — 킬 카운트 + 콤보 단계 갱신 + 킬 사운드.
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
        self._mouse1_down = True
        self._play_shoot_oneshot()

    def _on_fire_up(self):
        self._mouse1_down = False

    def _play_shoot_oneshot(self):
        if self.paused:
            return
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
        # 히트 판정 — 카메라 위치에서 yaw+pitch 방향으로 ray, 각 좀비의 3 zone
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
            # Tracer — muzzle 위치에서 발사 방향(조준 + 탄 퍼짐 편차). ray 와 일치.
            self.tracer.setPos(self.muzzle_flash.getPos(self.render))
            self.tracer.setHpr(self.player_yaw + self._shot_yaw_off,
                               self.player_pitch + self._shot_pitch_off, 0)
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
        # 어두운 패널 + 시안 임상 톤. 부제로 게임 정체성("면역 시스템 일시정지")을 깐다.
        self.pause_frame = DirectFrame(
            frameColor=(0.012, 0.035, 0.050, 0.88),
            frameSize=(-0.55, 0.55, -0.45, 0.45),
            pos=(0, 0, 0),
            parent=self.aspect2d,
        )
        # 상단 시안 라인
        DirectFrame(
            frameColor=HUD_CYAN, frameSize=(-0.55, 0.55, -0.004, 0.004),
            pos=(0, 0, 0.44), parent=self.pause_frame,
        )
        OnscreenText(
            text='일시정지', pos=(0, 0.30), scale=0.11,
            fg=HUD_WHITE, align=TextNode.ACenter, mayChange=False,
            parent=self.pause_frame,
        )
        OnscreenText(
            text='SENTINEL // 면역 프로토콜 보류됨', pos=(0, 0.235), scale=0.034,
            fg=HUD_CYAN_DIM, align=TextNode.ACenter, mayChange=False,
            parent=self.pause_frame,
        )
        OnscreenText(
            text='마우스 감도', pos=(0, 0.13), scale=0.042,
            fg=HUD_CYAN, align=TextNode.ACenter, mayChange=False,
            parent=self.pause_frame,
        )
        self.sens_slider = DirectSlider(
            range=(0.02, 0.30),
            value=self.mouse_sens,
            pageSize=0.01,
            command=self._on_sens_change,
            parent=self.pause_frame,
            pos=(0, 0, 0.06),
            scale=0.35,
            thumb_frameColor=HUD_CYAN,
        )
        self.sens_value_text = OnscreenText(
            text=f'{self.mouse_sens:.3f}', pos=(0, -0.005), scale=0.038,
            fg=HUD_CYAN, align=TextNode.ACenter, mayChange=True,
            parent=self.pause_frame,
        )
        btn_kw = dict(
            scale=0.07, parent=self.pause_frame,
            frameColor=(0.05, 0.14, 0.18, 1.0),
            text_fg=HUD_WHITE, relief=1,
            frameSize=(-3.6, 3.6, -0.7, 1.1),
            text_scale=0.9,
        )
        DirectButton(text='계속하기', pos=(0, 0, -0.14),
                     command=self._toggle_pause, **btn_kw)
        DirectButton(text='종료', pos=(0, 0, -0.32),
                     command=self.userExit, **btn_kw)
        self.pause_frame.hide()

    def take_core_damage(self, amount, source_pos=None):
        """좀비 공격 → 코어 무결성(체력) 깎기. 0 이 되면 게임오버 훅(현재 미구현).
        source_pos 주어지면 그 방향으로 피격 방향 아크 표시."""
        self.core_integrity = max(0, self.core_integrity - amount)
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

    def _on_sens_change(self):
        # DirectSlider command — 매 변경마다 호출. 현재 값 읽어서 mouse_sens 갱신.
        v = self.sens_slider['value']
        self.mouse_sens = v
        self.sens_value_text.setText(f'{v:.3f}')

    def _build_crosshair(self):
        """중앙 조준점 — reticle.png (시안 단색, 880×880 PNG, 4× 해상도).
        히트마커는 명중 순간 잠깐 점멸. 둘 다 setColorScale 로 시안↔빨강 틴트."""
        ret_tex = self.loader.loadTexture(
            Filename.from_os_specific(str(UI_DIR / 'reticle.png')))
        self.crosshair = OnscreenImage(
            image=ret_tex, pos=(0, 0, 0),
            scale=(0.030 * HUD_SCALE, 1, 0.030 * HUD_SCALE),
            parent=self.aspect2d)
        self.crosshair.setTransparency(True)
        self.crosshair.setColorScale(*HUD_TINT_CYAN)
        # 히트마커 — 평소 hide, 명중 순간 0.18s 표시.
        hit_tex = self.loader.loadTexture(
            Filename.from_os_specific(str(UI_DIR / 'hitmarker.png')))
        self.hitmarker = OnscreenImage(
            image=hit_tex, pos=(0, 0, 0),
            scale=(0.025 * HUD_SCALE, 1, 0.025 * HUD_SCALE),
            parent=self.aspect2d)
        self.hitmarker.setTransparency(True)
        self.hitmarker.hide()
        self._hitmarker_t = 0.0
        self._ch_alert = False        # 적 조준 중이면 빨강

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
            d = self._make_filled_circle(1.6 * S, KB, segs=10)
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
            LerpColorScaleInterval(self.kb_motion, 0.18, (1, 1, 1, 1),
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
            Wait(1.6),
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
            dist = (52.0 + random.uniform(0.0, 84.0)) * S   # 더 넓게 퍼짐
            life = 0.30 + random.uniform(0.0, 0.22)
            scl = random.uniform(0.7, 2.3)                  # 원 크기 다양
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
                ease = 1.0 - (1.0 - f) ** 4                # quartic easeOut (초반 폭발)
                ux, uz = self._kb_dot_dir[i]
                dist = self._kb_dot_dist[i] * ease
                d.setPos(ux * dist, 0, uz * dist)
                d.setScale(self._kb_dot_scale[i] * (1.0 - 0.62 * f))   # 점점 작아짐
                a = 1.0 if f < 0.55 else max(0.0, 1.0 - (f - 0.55) / 0.45)
                d.setColorScale(1, 1, 1, a)
            if self._kb_burst_t <= 0.0:
                for d in self._kb_dots:
                    d.setColorScale(1, 1, 1, 0)
        return task.cont

    def _show_kill_banner(self):
        """처치 시 호출 — 진행 중이던 Sequence 멈추고 처음부터 재생(겹침 방지)."""
        self._kb_seq.start()   # start() 가 t=0 으로 리셋하며 재생

    # --- HUD (임상 안티바이러스 톤 + 글리치) ---------------------------------

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

    def _build_hud(self):
        """플레이어를 '백신 AI' 로 믿게 만드는 표면 HUD. 글리치 때 진실로 반전.
        외형은 정화 HUD PNG (assets/ui/) 로 그리고, 그 위에 텍스트·동적 채움을 얹음."""
        # 코너 기준 HUD 는 코너마다 스케일 컨테이너를 하나 끼워 거기에 HUD_SCALE 를
        # 건다. 개별 요소의 pos/scale 은 그대로 두고도 정렬 보존된 채 비례 확대된다.
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

        # 우상단 — "정화 완료" 카운터 + 구역 확보율 (텍스트만)
        self.hud_kills_lbl = OnscreenText(
            text=s['kills_lbl'][0], pos=(-0.05, -0.10), scale=0.040,
            fg=HUD_CYAN_DIM, align=TextNode.ARight, mayChange=True, parent=R)
        self.hud_kills_num = OnscreenText(
            text='00', pos=(-0.05, -0.205), scale=0.090,
            fg=HUD_WHITE, align=TextNode.ARight, mayChange=True, parent=R)
        self.hud_zone = OnscreenText(
            text='구역 확보 0%', pos=(-0.05, -0.255), scale=0.036,
            fg=HUD_CYAN, align=TextNode.ARight, mayChange=True, parent=R)

        # ── PvP 점수(online 전용) — 상단 중앙 "내점수 : 상대점수", 먼저 10점이면 승리.
        self.hud_score = OnscreenText(
            text='0 : 0', pos=(0, 0.86), scale=0.085,
            fg=(1, 1, 1, 0.96), align=TextNode.ACenter, mayChange=True,
            parent=self.aspect2d)
        self.hud_score.hide()             # online 일 때만 _setup_online 에서 show
        # 승/패 결과 배너 — 매치 종료 시 화면 중앙에 크게.
        self.hud_match_result = OnscreenText(
            text='', pos=(0, 0.12), scale=0.18,
            fg=(1, 1, 1, 1), align=TextNode.ACenter, mayChange=True,
            parent=self.aspect2d)
        self.hud_match_result.hide()
        # 라운드 시작 카운트다운 — 화면 중앙 "5..1 / FIGHT!" (스폰 배리어 해제 타이밍).
        self.hud_countdown = OnscreenText(
            text='', pos=(0, 0.30), scale=0.20,
            fg=(1, 0.92, 0.4, 1), align=TextNode.ACenter, mayChange=True,
            parent=self.aspect2d)
        self.hud_countdown.hide()

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
        self.php_track = DirectFrame(
            frameColor=(0.10, 0.03, 0.03, 0.72),
            frameSize=(0, php_w, -php_h, php_h),
            pos=(php_x, 0, php_z), parent=self.a2dBottomLeft)
        self.php_track.setBin('fixed', 20)
        self.php_fill = DirectFrame(
            frameColor=(0.25, 0.85, 0.30, 0.95),
            frameSize=(0, php_w, -php_h, php_h),
            pos=(php_x, 0, php_z), parent=self.a2dBottomLeft)
        self.php_fill.setBin('fixed', 21)
        self.php_num = OnscreenText(
            text='100', pos=(php_x + php_w + 0.04, php_z - 0.018), scale=0.052,
            fg=(1, 1, 1, 0.95), align=TextNode.ALeft, mayChange=True,
            parent=self.a2dBottomLeft)
        self.php_num.setBin('fixed', 22)

        # 우하단 — 탄약 카운터. 라벨("정화 카트리지")·카트리지 아이콘 UI 제거하고
        # "현재/최대" 숫자(예: 3/8, 7/25)만 표시. 재장전 중엔 위에 "reloading...".
        self.hud_ammo_num = OnscreenText(
            text='8/8', pos=(-0.05, 0.215), scale=0.110,
            fg=HUD_WHITE_TRANS, align=TextNode.ARight, mayChange=True, parent=BR)
        self.hud_reload_text = OnscreenText(
            text='reloading...', pos=(-0.05, 0.390), scale=0.045,
            fg=HUD_WHITE_TRANS, align=TextNode.ARight, mayChange=False, parent=BR)
        self.hud_reload_text.hide()

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
        """on=True → 진실 라벨/빨강, False → 표면 라벨/시안. HUD 전반에 적용.
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
        """진실 누출 한 번. 확산이 진행될수록 자주 불리도록 update 에서 호출.
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

        # 탄약 — "현재/최대" 숫자만 (카트리지 아이콘 UI 제거). 빈 탄창은 더 옅게.
        self.hud_ammo_num.setText(f'{self.ammo}/{self.ammo_max}')
        self.hud_ammo_num.setFg(HUD_WHITE_TRANS_DIM if self.ammo == 0
                                else HUD_WHITE_TRANS)
        # 재장전 중 "reloading..." 표시.
        if self._reload_oneshot:
            self.hud_reload_text.show()
        else:
            self.hud_reload_text.hide()

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

        # 플레이어 체력바 — 너비 = 체력 비율, 색 = 초록(만땅)→빨강(위험).
        self.php_fill['frameSize'] = (0, self._php_w * r, -self._php_h, self._php_h)
        self.php_fill['frameColor'] = (0.90 - 0.65 * r, 0.20 + 0.65 * r,
                                       0.22 + 0.06 * r, 0.95)
        self.php_num.setText(str(int(round(self.core_integrity))))

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

        # 정면 적 타겟 정보
        self._update_enemy_target()

        # 글리치 타이머 — 확산이 진행될수록 자주 터진다
        if self._glitch_t > 0:
            self._glitch_t -= dt
            if self._glitch_t <= 0:
                self._set_glitch(False)
        else:
            # 웨이브가 올라갈수록 글리치가 잦아지게 (확산률 대용).
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
            self.enemy_target_l1.setText(f'정상 개체 · #K-{i:02d} · 동족')
            self.enemy_target_l2.setText(f'온전함 {infect}% — 아직 안 감염됨')
        else:
            self.enemy_target_l1.setText(f'감염 개체 식별 · #K-{i:02d}')
            self.enemy_target_l2.setText(f'감염도 {infect}%')
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
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)
        else:
            # 재개 — MNormal 복귀. 첫 프레임 dt 폭발은 _update 의 cap (≤0.1) 이 잡음.
            clock.setMode(ClockObject.MNormal)
            self.pause_frame.hide()
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
            print(f'[arena] 대기 — nonce={self._nonce} (스폰 자동배정)', flush=True)

        self._setup_remote_avatar()
        self._connect_relay()
        # PvP 점수 HUD 표시 (먼저 10점 승리). 단일플레이에선 숨김 유지.
        self.hud_score.show()
        self._update_score_hud()

    def _setup_remote_avatar(self):
        """상대용 ybot Actor 하나 더 생성 — 평범한 3인칭 월드 Actor.
        내 1인칭 트릭(머리뼈 카메라 부착/어깨 피벗 pitch/walk-bob/hips anchor 보정/
        바디 메쉬 숨김)은 일절 적용하지 않는다. 첫 패킷 수신 전까지 숨김."""
        av = Actor(BAM_PATH)
        av.reparentTo(self.render)
        av.setPos(0, 0, 0)
        av.setH(180)                  # self.ybot 과 동일한 +180 기준
        idle = 'Idle' if 'Idle' in self.anim_names else (
            self.anim_names[0] if self.anim_names else None)
        if idle:
            av.loop(idle)
            self._remote_anim = idle
        av.hide()                     # remote_state 도착 전엔 안 보이게
        self.remote_avatar = av

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

        # 상대 플레이어 히트박스 — 좀비와 동일한 본 기반 캡슐/머리 구를 av 본으로 구성.
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
            else:
                return                    # 아직 상대 nonce 없음 → 대기
        if self._countdown_t is None:
            # 역할 확정 + 상대 아바타 보이면 양쪽 준비 완료 → 카운트다운 시작.
            if self.remote_avatar is not None and not self.remote_avatar.isHidden():
                self._countdown_t = 5.0
                print('[arena] 양쪽 준비 — 5초 카운트다운 시작', flush=True)
            return
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
        vol = self._remote_dist_volume(1.6, 3.0, 28.0)  # base>1 = 증폭(가까이서 크게)
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

    def _on_remote_player_hit(self, zone, world_pos):
        """상대 플레이어 명중 — 좀비와 같은 피드백(피격음 + 파티클 + 데미지 숫자).
        동기화 전용 1:1 모드라 HP/사망/점수는 없고 '맞았다' 피드백만 준다."""
        dmg = Zombie.DAMAGE.get(zone, 5)
        if zone == 'head' and getattr(self, '_head_onekill', False):
            dmg = max(dmg, 100)
        self._play_pool(self.sfx_hit, '_hit_i')
        self._spawn_hit_particle(world_pos)
        self._spawn_damage_number(world_pos, dmg)
        # 누적 피해 적립 → 다음 송신 패킷으로 상대에게 전달되어 상대 체력이 깎인다.
        self._dmg_dealt = (self._dmg_dealt + dmg) & 0xFFFF
        print(f'[pvp] 상대 명중 zone={zone} dmg={dmg} 누적={self._dmg_dealt}',
              flush=True)

    def _apply_pvp_damage(self, amount):
        """상대 총에 맞아 내 체력(core_integrity) 감소. 피격 방향 아크 + 0 되면 리스폰."""
        if self._match_over:
            return                        # 매치 끝나면 더 이상 피해/점수 없음
        self.core_integrity = max(0, self.core_integrity - amount)
        # 피격 방향 — 상대 아바타 위치를 source 로 빨간 아크 표시(좀비 피격과 동일).
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
        if self._my_score >= self.WIN_SCORE:
            self._end_match(True)

    def _update_score_hud(self):
        """상단 중앙 점수 텍스트 갱신 (online 일 때만 보임)."""
        self.hud_score.setText(f'{self._my_score} : {self._enemy_score}')

    def _end_match(self, won):
        """매치 종료 — 승/패 배너 표시 + 이후 점수/리스폰 정지."""
        self._match_over = True
        self.hud_match_result.setText('승리!' if won else '패배...')
        self.hud_match_result.setFg((0.30, 1.0, 0.45, 1.0) if won
                                    else (1.0, 0.35, 0.35, 1.0))
        self.hud_match_result.show()
        print(f'[pvp] 매치 종료 — {"WIN" if won else "LOSE"} '
              f'{self._my_score}:{self._enemy_score}', flush=True)

    def _pvp_die(self):
        """체력 0 — 내 사망 +1(상대 점수 +1). 상대가 10점이면 패배(리스폰 안 함),
        아니면 2초 뒤 스폰 지점으로 리스폰(체력/탄 회복). 내 누적 사망 횟수를 올려
        상대가 '처치'를 인지(킬 배너/점수)하게 한다."""
        self._deaths = (self._deaths + 1) & 0xFF
        self._enemy_score = self._deaths   # 상대가 나를 죽인 횟수 = 상대 점수
        self._update_score_hud()
        print(f'[pvp] 사망 — 점수 {self._my_score}:{self._enemy_score}', flush=True)
        if self._enemy_score >= self.WIN_SCORE:
            self._end_match(False)
            return                         # 매치 종료 — 리스폰 안 함
        self._pvp_dead_t = 2.0
        # 2초 뒤 리스폰. (doMethodLater 단발 — pause 와 무관히 실시간으로 흐름)
        self.taskMgr.doMethodLater(self._pvp_dead_t, self._pvp_respawn,
                                   'pvp_respawn')

    def _pvp_respawn(self, task=None):
        """스폰 지점(아레나면 내 스폰)으로 복귀 + 체력/탄창 회복."""
        self.player_pos = Vec3(self._spawn_pos)
        self.player_yaw = self._spawn_yaw
        self.player_vz = 0.0
        self.on_ground = True
        self.core_integrity = self.core_integrity_max
        self.ammo = self.ammo_max
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
            s.connect((RELAY_HOST, RELAY_PORT))
            s.settimeout(None)        # 이후 blocking recv/send
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = s
            self._net_alive = True
            atexit.register(self._net_shutdown)   # 프로세스 종료 시 소켓 정리
            threading.Thread(target=self._net_recv_loop, daemon=True).start()
            print(f'[net] 릴레이 접속 성공 {RELAY_HOST}:{RELAY_PORT}', flush=True)
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
                         shot_seq, dmg_total, deaths, nonce) = struct.unpack(
                            NET_STATE_FMT, frame)
                    except struct.error:
                        continue
                    # 참조 교체(원자적) — 위치/시점 + 무기 + 재장전/발사 + 피해 + 사망 + nonce.
                    self.remote_state = (x, y, z, yaw, pitch, widx, reloading,
                                         shot_seq, dmg_total, deaths, nonce)
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
            pkt = struct.pack(NET_STATE_FMT,
                              self.player_pos.x, self.player_pos.y,
                              self.player_pos.z, self.player_yaw,
                              self.player_pitch,
                              self._weapon_idx & 0xFF,            # 0=권총 1=소총 (uint8)
                              1 if self._reload_oneshot else 0,   # 재장전 중 플래그
                              self._net_shot_seq & 0xFF,          # 발사 카운터
                              self._dmg_dealt & 0xFFFF,           # 상대에 입힌 누적 피해
                              self._deaths & 0xFF,                # 내 누적 사망 횟수
                              self._nonce & 0xFFFFFFFF)           # 스폰 배정용 랜덤
            self._sock.sendall(pkt)
        except OSError as e:
            print(f'[net] 송신 실패 ({e}) — 연결 종료', flush=True)
            self._net_alive = False

    def _update_remote_avatar(self, dt):
        """수신한 remote_state 로 상대 아바타를 부드럽게 보간 이동 + 방향 + run/idle.
        몸 전체 pitch 는 적용 안 함(요청대로). 데이터 없으면 숨김 유지."""
        av = self.remote_avatar
        if av is None:
            return
        rs = self.remote_state        # 스레드가 최신값으로 교체 — 한 번만 읽음
        if rs is None:
            return                    # 아직 첫 패킷 없음 → 숨김 유지(크래시 없음)
        target = Vec3(rs[0], rs[1], rs[2])
        if self._remote_smooth is None:
            self._remote_smooth = Vec3(target)   # 첫 패킷은 즉시 배치(점프 방지)
            self._remote_prev = Vec3(target)
            av.show()
        else:
            # 핑 대응 — 현재→목표 지수 보간(계수 REMOTE_SMOOTH_LERP). 외삽 없음.
            self._remote_smooth += ((target - self._remote_smooth)
                                    * min(1.0, dt * REMOTE_SMOOTH_LERP))
        av.setPos(self._remote_smooth)
        av.setH(rs[3] + 180)          # yaw 만 — pitch 로 몸 전체를 기울이지 않음
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

    # --- main loop ----------------------------------------------------------

    def _update(self, task):
        # paused: 게임 update 통째로 skip. doMethodLater 단발 anim 콜백은 계속
        # 흘러가지만 (실시간 기반) 일시정지 중에 사용자가 할 일이 거의 없으니 OK.
        if self.paused:
            return Task.cont
        dt = ClockObject.getGlobalClock().getDt()
        # pause 직후 첫 프레임 wall-clock 누적 dt 폭발 cap — 좀비 워프 방지.
        if dt > 0.1:
            dt = 0.1

        # ── 온라인: 내 상태 송신(스로틀) + 상대 아바타 보간/애니 ──────────────
        # 싱글이면 online_mode=False 라 통째로 건너뜀(네트워크 코드 안 탐).
        if self.online_mode:
            self._net_send(dt)
            self._update_remote_avatar(dt)
            self._arena_update(dt)        # 스폰 배리어 카운트다운 + shimmer fade

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
        if self.win.hasPointer(0):
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
            else:
                # 1인칭 yaw + pitch — 위·아래 ±89° (총 178°) 자유 시야.
                # ADS 시 감도 낮춤 → 손/총 좌우 swing 천천히·작게.
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
                if self.keys['w']: mv += forward
                if self.keys['s']: mv -= forward
                if self.keys['d']: mv += right_v
                if self.keys['a']: mv -= right_v
                if mv.length() > 0:
                    mv.normalize()
                    spd_mult = 1.0 + (self.ads_move_factor - 1.0) * self.aim_t
                    self.player_pos += mv * (self.move_speed * spd_mult * dt)
                    # 벽 충돌 해소 (XY 평면) — 박스 안쪽으로 침투했으면 바깥으로 밀어냄.
                    nx, ny = self.level_collider.resolve(
                        self.player_pos.x, self.player_pos.y, PLAYER_RADIUS)
                    self.player_pos.x = nx
                    self.player_pos.y = ny
                if self.keys['space'] and self.on_ground:
                    self.player_vz = self.jump_speed
                    self.on_ground = False

            # 중력은 항상 적용 (무릎자세에서도)
            self.player_vz -= self.gravity * dt
            self.player_pos.z += self.player_vz * dt
            if self.player_pos.z <= 0:
                self.player_pos.z = 0
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
                    # 발소리 템포를 실제 속도에 맞춘다.
                    spd_mult = 1.0 + (self.ads_move_factor - 1.0) * self.aim_t
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
            self.camera.setHpr(self.player_yaw, self.player_pitch, 0)

        # weapon anchor 갱신: hand 본 따라감. 이제 ybot 자체가 head 본 피벗으로
        # pitch 되어 손 본도 같이 회전 → player_pitch 를 따로 더할 필요 없음
        # (더하면 이중 적용).
        if (self.weapon is not None
                and self.right_hand_joint is not None
                and not self.right_hand_joint.isEmpty()):
            # 총은 손 본(=몸의 일부)을 그대로 따라감 → 몸과 완전히 같은 축으로 회전.
            self.weapon_anchor.setPos(self.right_hand_joint.getPos(self.render))
            self.weapon_anchor.setHpr(self.right_hand_joint.getHpr(self.render))

        # 좀비 AI tick — 페이드아웃 끝난 시체는 노드 정리 후 목록에서 제거.
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

        # (F 정화/복원 상호작용 제거 — 좀비는 죽으면 페이드아웃되어 사라짐)

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
    # 인자 없음 → 기존 그대로 싱글(100% 보존). '--online' → 멀티(릴레이 접속).
    # '--p2' → 아레나 스폰 B(0,15) 로 시작(상대는 인자 없이 스폰 A). 한 명만 --p2.
    online = '--online' in sys.argv
    spawn_b = '--p2' in sys.argv
    ZombieGame(online=online, spawn_b=spawn_b).run()
