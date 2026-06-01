"""
zombie_game — Mirror's Edge style 1인칭 좀비 슈터 (Panda3D)
Stage 1: 1인칭 카메라 + Y Bot 풀바디 + 기본 입력.
"""
import random
from math import atan2, cos, degrees, radians, sin
from pathlib import Path

from direct.actor.Actor import Actor
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectSlider
from direct.gui.OnscreenImage import OnscreenImage
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import (
    AmbientLight, CardMaker, ClockObject, ColorBlendAttrib, DirectionalLight, Filename,
    LineSegs, NodePath, PerspectiveLens, Quat, Spotlight, TextNode, Vec3, Vec4,
    WindowProperties, loadPrcFileData,
)

from level import (PLAYER_RADIUS, ZOMBIE_RADIUS, WALL_HEIGHT, Wall,
                   IMMUNE_COLOR, LESION_COLOR, build_level)

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
# 배포용은 OFL 라이선스 나눔고딕 (assets/fonts/NanumGothic.ttf). 그게 없으면
# 픽셀 한글 폰트 (OFL 라이선스, x12y12pxMaruMinyaHangul). 게임 톤(sci-fi 픽셀
# HUD)과 어울리고, 한글 + 영문 + 숫자 글리프 다 포함. fallback 은 윈도우 맑은 고딕.
_FONT_BUNDLED = (Path(__file__).parent / 'assets' / 'fonts'
                 / 'x12y12pxMaruMinyaHangul.ttf')
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
# weapon_anchor (hand 본의 world pos+hpr 따라감) 기준 weapon local transform.
# HPR 는 weapon 의 self frame 기준 누적 회전 끝 자세 → 그대로 setHpr 호출 가능.
WEAPON_LOCAL_SCALE = 0.1195
WEAPON_LOCAL_POS   = (0.000, 0.090, 0.040)
WEAPON_LOCAL_HPR   = (22.5, -78.2, 108.9)

ZOMBIE_BAM = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'zombie' / 'scene.bam')
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
    DEATH_SETTLE_DUR = 0.45     # 죽을 때 접지 보정을 0 으로 페이드하는 시간 (sec)
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
        """좀비 머리 위 health bar — 평소 hidden, 데미지 시 show + fade out."""
        # 배경 (빨강) — 풀 너비 1m
        cm_bg = CardMaker('hp_bg')
        cm_bg.setFrame(-0.5, 0.5, -0.04, 0.04)
        self.hp_bg = self.actor.attachNewNode(cm_bg.generate())
        self.hp_bg.setColor(0.5, 0.08, 0.08, 0.85)
        self.hp_bg.setZ(2.0)
        self.hp_bg.setBillboardPointEye()
        self.hp_bg.setLightOff()
        self.hp_bg.setTransparency(True)
        self.hp_bg.setBin('fixed', 80)
        self.hp_bg.setDepthTest(False)
        self.hp_bg.setDepthWrite(False)
        self.hp_bg.hide()
        # 채우기 (초록) — 좌측 정렬, hp_ratio 만큼 setSx 로 너비 조정
        cm_f = CardMaker('hp_fill')
        cm_f.setFrame(0, 1, -0.04, 0.04)
        self.hp_fill = self.actor.attachNewNode(cm_f.generate())
        self.hp_fill.setColor(0.2, 0.95, 0.25, 1.0)
        self.hp_fill.setPos(-0.5, 0, 2.0)
        self.hp_fill.setBillboardPointEye()
        self.hp_fill.setLightOff()
        self.hp_fill.setTransparency(True)
        self.hp_fill.setBin('fixed', 81)
        self.hp_fill.setDepthTest(False)
        self.hp_fill.setDepthWrite(False)
        self.hp_fill.hide()

    def take_damage(self, amount):
        if self.hp <= 0:
            return
        self.hp = max(0, self.hp - amount)
        # 바 표시 + 풀 알파 + ratio 갱신
        self.hp_bar_t = self.hp_bar_show_dur + self.hp_bar_fade_dur
        self.hp_bg.show()
        self.hp_fill.show()
        self.hp_bg.setColorScale(1, 1, 1, 1)
        self.hp_fill.setColorScale(1, 1, 1, 1)
        ratio = max(0.001, self.hp / self.hp_max)
        self.hp_fill.setSx(ratio)
        if self.hp <= 0:
            # Death anim 단발 + crossfade. 끝나면 마지막 프레임 (바닥) 에서 정지.
            self.state = self.DYING
            self.hp_bg.hide()
            self.hp_fill.hide()
            if 'Death' in self.anim_names:
                self._play('Death', loop=False)
                self.death_t = self.actor.getDuration('Death')
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
        self.game.take_core_damage(10)

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
        busy = (self.state == self.DYING or self.transform_t > 0)
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
            return   # 완전히 죽어서 마지막 프레임 정지 — 아무것도 안 함

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
            # 위치(X/Y)는 그대로 (이동 안 함)
            return

        # HP bar fade — show_dur 동안 풀 알파, fade_dur 동안 1→0 lerp, 끝나면 hide
        if self.hp_bar_t > 0:
            self.hp_bar_t -= dt
            if self.hp_bar_t <= 0:
                self.hp_bg.hide()
                self.hp_fill.hide()
            elif self.hp_bar_t < self.hp_bar_fade_dur:
                alpha = self.hp_bar_t / self.hp_bar_fade_dur
                self.hp_bg.setColorScale(1, 1, 1, alpha)
                self.hp_fill.setColorScale(1, 1, 1, alpha)

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
    def __init__(self):
        super().__init__()

        # 윈도우/마우스
        props = WindowProperties()
        props.setTitle('zombie_game')
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_confined)
        self.win.requestProperties(props)
        self.disableMouse()  # ShowBase 기본 마우스-카메라 비활성

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
        self.level_collider, self.level_data = build_level(
            self.render, draw_wall_cards=not kit_available)
        self.kit_root = None
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
        self.aim_t = 0.0              # 0=hip / 1=ADS 보간 (지수 ramp)
        self.aim_speed = 9.0          # 1/sec — 클수록 빠른 전환 (~110ms)
        # ADS 시 ybot 전체를 player-frame 으로 이 만큼 이동, 카메라는 같은 양 보정.
        # 결과: 손·팔·총 다 같이 이 지점으로 이동, 시점(world background) 정적.
        # 단위 m. (X=우/좌, Y=앞/뒤, Z=위/아래). 현재: 좌 13cm + 앞 5cm + 아래 2cm.
        self.ads_body_offset = Vec3(-0.13, 0.05, -0.02)
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
        self.mouse_sens = 0.10    # 기본값 — ESC pause 메뉴 슬라이더로 0.02~0.30 조정
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

        # 모든 locomotion anim 을 양쪽 파트에서 항상 loop — weight 가 0 이어도
        # 내부 time 은 흐르고, 보이는 건 _current_w 가 결정. 액션 전환 시 시작
        # 프레임이 갑자기 튀지 않게 함.
        self._loop_anim_set = {
            'Idle', 'RunForward', 'RunBackward', 'StrafeL', 'StrafeR',
            'KneelIdle', 'Jump',
            # Walk* 도 loop 만 깔아둠 — 현재 코드에선 미사용이지만 추후 Shift+이동
            # 같은 걸 붙일 때 시작 프레임이 튀지 않게 미리 돌려 둠.
            'WalkForward', 'WalkBackward',
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
        if self.right_hand_joint is not None and WEAPON_PATH.exists():
            self.weapon = self.loader.loadModel(WEAPON_PATH)
            # glTF RootNode self-transform 우회용 평탄화 (slide/trigger 보존).
            self.weapon.flattenLight()
            # weapon anchor — hand 본의 위치만 매 프레임 복사하고 회전은 무시한다.
            # 이렇게 하면 weapon 의 H/P/R 축이 world 축과 정렬되어 직관적으로 회전
            # 가능 (hand 본의 자체 회전이 weapon 의 회전축을 비틀어서 H 와 R 이
            # 같은 효과를 내는 문제 해결). 단점: 손 자세 변해도 weapon 자세는
            # 고정 — base orientation 잡는 단계엔 오히려 편함. 자세 다 잡힌 후
            # hand 본 회전도 같이 따라가게 하려면 anchor 의 setHpr 도 매 프레임
            # hand 회전으로 갱신하면 됨.
            self.weapon_anchor = self.render.attachNewNode('weapon_anchor')
            self.weapon.reparentTo(self.weapon_anchor)
            self.weapon.setScale(WEAPON_LOCAL_SCALE)
            self.weapon.setPos(*WEAPON_LOCAL_POS)
            self.weapon.setHpr(*WEAPON_LOCAL_HPR)
            self.weapon.setTwoSided(True)
            # anchor 갱신은 _update 안에서 ybot.update(force=True) 직후에 호출 —
            # 별도 task 로 두면 frame order 가 어긋나서 1프레임 lag (잔상) 발생.
            print(f'[zombie_game] weapon attached to {rhand_name}', flush=True)

            # Slide 노드 (사격 시 후퇴 효과용). flattenLight 가 named node 는
            # 보존하므로 find 로 찾을 수 있음. 모델의 총신 축이 X 라서 -X 방향 후퇴.
            self.slide_node = self.weapon.find('**/Slide')
            if self.slide_node.isEmpty():
                self.slide_node = None
                print('[weapon] Slide node not found', flush=True)
            else:
                self.slide_rest_x = self.slide_node.getX()
                print(f'[weapon] Slide found, rest X = {self.slide_rest_x:.3f}',
                      flush=True)
            # 슬라이드 후퇴 상태
            self.slide_recoil = 0.0
            self.slide_recoil_kick = 0.4   # 모델 local units (음수 X 로 후퇴)
            self.slide_recoil_decay = 14.0 # 1/sec — 클수록 빠른 복귀

        else:
            self.weapon = None
            print(f'[zombie_game] WARN weapon not loaded '
                  f'(rhand={rhand_name}, glb_exists={WEAPON_PATH.exists()})',
                  flush=True)

        # 슬라이드 위치 marker (RightHand 본 좌표계 — armature cm 단위) — 임시 하네스
        if self.right_hand_joint is not None and not self.right_hand_joint.isEmpty():
            ls = LineSegs()
            ls.setThickness(3)
            size = 5.0  # 5cm 축 길이
            for color, axis in (
                ((1, 0, 0, 1), Vec3(size, 0, 0)),   # X 빨강
                ((0, 1, 0, 1), Vec3(0, size, 0)),   # Y 초록 (총신 방향 추정)
                ((0, 0, 1, 1), Vec3(0, 0, size)),   # Z 파랑 (위 추정)
            ):
                ls.setColor(*color)
                ls.moveTo(0, 0, 0)
                ls.drawTo(axis)
            self.slide_marker = self.right_hand_joint.attachNewNode(ls.create())
            self.slide_marker.setLightOff()
            self._marker_pos = [0.0, 0.0, 0.0]
            self.slide_marker.setPos(0, 0, 0)
            print('[marker] axes: red=X green=Y blue=Z. I/K=±Y, J/L=±X, U/O=±Z, P=dump',
                  flush=True)
        else:
            self.slide_marker = None
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
        self.sfx_reload = self._load_sfx('Reload.wav')

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
        # 실제 재생 시간(_reload_play_dur)을 타이머에 사용. 과한 워핑은 클램프로 방지.
        self._reload_play_dur = (self.ybot.getDuration('Reload')
                                 if 'Reload' in self.anim_names else 0.0)
        if self.sfx_reload is not None and 'Reload' in self.anim_names:
            snd_len = self.sfx_reload.length()
            anim_len = self.ybot.getDuration('Reload')
            if snd_len > 0.05 and anim_len > 0.05:
                rate = max(0.6, min(1.6, anim_len / snd_len))
                for _pp in ('upper', 'hands'):
                    self.ybot.setPlayRate(rate, 'Reload', partName=_pp)
                self._reload_play_dur = anim_len / rate
                print('[sfx] reload synced: snd=%.2fs anim=%.2fs rate=%.2f -> %.2fs'
                      % (snd_len, anim_len, rate, self._reload_play_dur), flush=True)

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
        # level.py 의 5방 라인업 (y=-2 ~ y=70) 을 여유 있게 덮음.
        cm = CardMaker('ground')
        cm.setFrame(-32, 32, -8, 76)
        gnd = self.render.attachNewNode(cm.generate())
        gnd.setHpr(0, -90, 0)        # XY 평면으로 눕히기 — 법선 +Z 위
        gnd.setColor(0.55, 0.55, 0.58, 1)

        # 천장 — 같은 XY 풋프린트 / z = WALL_HEIGHT 에 놓고 법선은 아래(-Z) 향함.
        # setHpr(0, 90, 0) 으로 P=+90 → 카드 법선이 -Z 로 뒤집힘 → 아래에서 비추는
        # 플래시 빛만 받음. 색은 바닥보다 어둡게 (실내 천장 톤).
        cm_c = CardMaker('ceiling')
        cm_c.setFrame(-32, 32, -8, 76)
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
        self.accept('mouse1', self._play_shoot_oneshot)
        self.accept('mouse3', self._set_aim, [True])
        self.accept('mouse3-up', self._set_aim, [False])
        self.accept('r', self._play_reload_oneshot)
        self.accept('f', self._on_interact)
        self.accept('f2', self._toggle_editor)
        self.accept('f3', self._toggle_debug)
        # Ctrl 토글 — Panda3D 에선 'control' 단독 이벤트가 안 들어오므로 lcontrol/
        # rcontrol 만 바인딩 (left/right 둘 다 잡힘)
        for k in ('lcontrol', 'rcontrol'):
            self.accept(k, self._toggle_kneel)
        # 슬라이드 위치 marker 튜닝 키 (임시 하네스)
        step = 2.0  # 2cm armature unit
        marker_binds = {
            'i': (1, step),  'k': (1, -step),   # ±Y (총신 방향)
            'j': (0, -step), 'l': (0, step),    # ±X (좌우)
            'u': (2, step),  'o': (2, -step),   # ±Z (위아래)
        }
        for key, args in marker_binds.items():
            self.accept(key, self._nudge_marker, list(args))
            self.accept(f'{key}-repeat', self._nudge_marker, list(args))
        self.accept('p', self._dump_marker)

    def _set_key(self, k, v):
        self.keys[k] = v

    def _set_aim(self, on):
        # 우클릭 hold — ADS on/off. 재장전 transition 중에도 그대로 받음
        # (사용자가 R + 우클릭 동시 누르는 흔치 않은 케이스 그냥 허용).
        self.aiming = on

    def _on_interact(self):
        # F 키 — 가까이 있는 dead 좀비 가 있으면 Y Bot 으로 transform 시작.
        # 표면 라벨은 "정화/복원", 실제로는 한 개체를 더 감염(동화)시키는 행위.
        if self.paused or self._interact_target is None:
            return
        self._interact_target.start_transform(self)
        self._interact_target = None
        self.interact_frame.hide()
        self.purified += 1          # "정화 완료" 카운터 (= 감염시킨 수)

    # --- slide marker tuning harness (조정 끝나면 제거) -----------------------

    def _nudge_marker(self, idx, delta):
        if self.slide_marker is None:
            return
        self._marker_pos[idx] += delta
        self.slide_marker.setPos(*self._marker_pos)

    def _dump_marker(self):
        if self.slide_marker is None:
            return
        p = self._marker_pos
        print(f'[marker] RightHand-local X={p[0]:.2f} Y={p[1]:.2f} Z={p[2]:.2f}',
              flush=True)
        # 화면 가운데 큰 글씨로 3초 — 이전 표시 있으면 교체
        txt = (f'MARKER (RightHand-local)\n'
               f'SLIDE_RIGHT = {p[0]:.2f}\n'
               f'SLIDE_FWD   = {p[1]:.2f}\n'
               f'SLIDE_UP    = {p[2]:.2f}')
        if hasattr(self, '_marker_text') and self._marker_text is not None:
            self._marker_text.destroy()
        self._marker_text = OnscreenText(
            text=txt, pos=(0, 0.2), scale=0.07,
            fg=(1, 1, 0, 1), bg=(0, 0, 0, 0.85),
            align=TextNode.ACenter, mayChange=False,
            parent=self.aspect2d,
        )
        token = self._marker_text
        def _remove(task, t=token):
            if self._marker_text is t:
                self._marker_text.destroy()
                self._marker_text = None
            return Task.done
        self.taskMgr.doMethodLater(3.0, _remove, 'marker_dump_remove')

    # --- weapon tuning harness (조정 끝나면 통째로 제거) -------------------


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

    def _target_anim(self):
        """현재 상태(공중/무릎/이동방향)에 맞는 loop anim 이름."""
        if self.kneel_state == 'going_down' and 'StandToKneel' in self.anim_names:
            return 'StandToKneel'
        if self.kneel_state == 'going_up' and 'KneelToStand' in self.anim_names:
            return 'KneelToStand'
        if self.kneel_state == 'kneel' and 'KneelIdle' in self.anim_names:
            return 'KneelIdle'
        if not self.on_ground and 'Jump' in self.anim_names:
            return 'Jump'
        fwd = self.keys['w'] - self.keys['s']
        rgt = self.keys['d'] - self.keys['a']
        if fwd > 0 and 'RunForward' in self.anim_names:
            return 'RunForward'
        if fwd < 0 and 'RunBackward' in self.anim_names:
            return 'RunBackward'
        if rgt > 0 and 'StrafeR' in self.anim_names:
            return 'StrafeR'
        if rgt < 0 and 'StrafeL' in self.anim_names:
            return 'StrafeL'
        return 'Idle'

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
        if self._reload_oneshot and target in ('RunForward', 'RunBackward'):
            target = 'Idle'
        # ADS + 이동 시 lower 까지 Idle 강제 → Hips rotation 사라져서 상체로 전파 안 됨
        # → 팔 완전 정지. (다리는 어차피 hidden, body slide 만 발생)
        if self.aim_t > 0.5 and target in ('RunForward', 'RunBackward',
                                            'StrafeL', 'StrafeR'):
            target = 'Idle'
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

    def _resolve_shot_hit(self):
        """카메라 ray vs 각 좀비의 본 기반 히트박스(머리 구 + 몸통/사지 캡슐).
        가장 가까운 hit 의 zone 으로 damage + damage number popup."""
        cam_pos = self.camera.getPos(self.render)
        yr = radians(self.player_yaw)
        pp = radians(self.player_pitch)
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

        if best_barrier is not None:
            best_barrier.hit()
            return
        if best_z is None:
            return
        dmg = Zombie.DAMAGE[best_zone]
        was_alive = best_z.hp > 0
        best_z.take_damage(dmg)
        if was_alive and best_z.hp <= 0:
            self._on_zombie_killed(best_zone == 'head')
        self._spawn_hit_particle(best_hit_pos)
        self._spawn_damage_number(best_hit_pos, dmg)
        # 히트마커 펄스 — 0.18s 표시. 명중 표시는 항상 빨강.
        self.hitmarker.show()
        self._hitmarker_t = 0.18
        self.hitmarker.setColorScale(*HUD_TINT_RED)
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

    def _on_zombie_killed(self, headshot):
        """좀비 처치 시 호출 — 킬 카운트 + 콤보 단계 갱신 + 킬 사운드."""
        self.kills += 1
        # 직전 킬 5초 이내 + 이번이 헤드샷이면 단계 상승(최대 5), 아니면 1로 리셋.
        if headshot and self._combo_window > 0.0:
            self._kill_tier = min(self._kill_tier + 1, 5)
        else:
            self._kill_tier = 1
        self._combo_window = self.kill_combo_dur
        self._play_kill_sound(self._kill_tier)

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

    def _play_shoot_oneshot(self):
        if self.paused:
            return
        if self.ammo <= 0:
            return  # 빈 탄창 — 발사 안 함 (R 로 재장전)
        if self.shoot_cooldown_t > 0:
            return  # 발사 간격 쿨다운
        if 'Shoot' not in self.anim_names or self._reload_oneshot:
            return
        self.ammo -= 1
        self.shoot_cooldown_t = self.shoot_cooldown_dur
        if self.sfx_shot_pool:
            self.sfx_shot_pool[self._sfx_shot_i].play()
            self._sfx_shot_i = (self._sfx_shot_i + 1) % len(self.sfx_shot_pool)
        # 히트 판정 — 카메라 위치에서 yaw+pitch 방향으로 ray, 각 좀비의 3 zone
        # (head/body/foot) sphere 와 교차 검사. 가장 가까운 zone 에 damage.
        self._resolve_shot_hit()
        # hands 만 Shoot 자세로 — 다리/상체는 그대로.
        self.ybot.play('Shoot', partName='hands')
        self.recoil_back = self.recoil_shoot_back
        self.slide_recoil = self.slide_recoil_kick
        # Muzzle flash — anchor 에 parent 라 위치는 자동. show + timer 만.
        if self.muzzle_flash is not None:
            self.muzzle_flash_t = self.muzzle_flash_dur
            self.muzzle_flash.setScale(self.muzzle_flash_base_scale)
            self.muzzle_flash.show()
            # Tracer — muzzle 위치에서 카메라가 보는 방향 (yaw + pitch)
            self.tracer.setPos(self.muzzle_flash.getPos(self.render))
            self.tracer.setHpr(self.player_yaw, self.player_pitch, 0)
            self.tracer.show()
            self.tracer_t = self.tracer_dur
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
        if ('Reload' not in self.anim_names or self._reload_oneshot
                or self.kneel_state in ('going_down', 'going_up')):
            return
        # upper + hands 두 파트만 단발 (lower 는 locomotion 유지 → 달리며 재장전)
        self.ybot.play('Reload', partName='upper')
        self.ybot.play('Reload', partName='hands')
        self._reload_oneshot = True
        if self.sfx_reload is not None:
            self.sfx_reload.play()
        rl = {a: (1.0 if a == 'Reload' else 0.0) for a in self.anim_names}
        self._target_w['upper'] = dict(rl)
        self._target_w['hands'] = dict(rl)
        self._reload_token += 1
        token = self._reload_token
        dur = self._reload_play_dur   # 사운드와 동기화된 실제 재생 시간

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
            self.ammo = self.ammo_max   # 탄창 충전
            # upper/hands 를 다음 프레임에 locomotion 으로 강제 재평가시키는 sentinel
            self.current_anim = '__reload_done__'
            return Task.done

        self.taskMgr.doMethodLater(back_after, _back, 'reload_return')

    def _update_blend(self, dt):
        # 지수 평활: 각 파트마다 current_w 를 target_w 쪽으로 비례 수렴.
        alpha = min(1.0, dt * self.blend_speed)
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

    def take_core_damage(self, amount):
        """좀비 공격 → 코어 무결성 깎기. 0 이 되면 게임오버 훅(현재 미구현)."""
        self.core_integrity = max(0, self.core_integrity - amount)

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

        # 우하단 — 정화 카트리지 ("탄약"). 라벨(상) / 큰 숫자(중) / cart row(하).
        # 카트리지 단독 칸을 3× 키우고 간격은 거의 붙여 magazine 한 덩어리처럼.
        # 칸이 커진 만큼 cart row 자체와 숫자/라벨도 위로 올려 화면 하단 클리핑 회피.
        self.hud_ammo_lbl = OnscreenText(
            text=s['ammo_lbl'][0], pos=(-0.05, 0.390), scale=0.036,
            fg=HUD_CYAN_DIM, align=TextNode.ARight, mayChange=True, parent=BR)
        self.hud_ammo_num = OnscreenText(
            text='8', pos=(-0.05, 0.215), scale=0.130,
            fg=HUD_WHITE, align=TextNode.ARight, mayChange=True, parent=BR)
        n = self.ammo_max
        seg_w, gap = 0.090, 0.00006      # 단독 칸 3×, 간격 사실상 0 (이전 1/5)
        seg_h = seg_w * (400 / 336)      # cart 종횡비 보존
        span = n * seg_w + (n - 1) * gap
        # cart row: 숫자 아래, 우측 정렬. z=0.080 → 화면 하단 클리핑 회피.
        x_right = -0.06
        x0 = x_right - span + seg_w * 0.5
        cart_z = 0.080
        self.hud_ammo_on = []
        self.hud_ammo_off = []
        for i in range(n):
            cx = x0 + i * (seg_w + gap)
            on = self._hud_img('cart-on.png', pos=(cx, 0, cart_z),
                               scale=(seg_w * 0.5, 1, seg_h * 0.5),
                               parent=BR)
            off = self._hud_img('cart-off.png', pos=(cx, 0, cart_z),
                                scale=(seg_w * 0.5, 1, seg_h * 0.5),
                                parent=BR, hidden=True)
            self.hud_ammo_on.append(on)
            self.hud_ammo_off.append(off)

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
            (self.hud_ammo_lbl,  'ammo_lbl',  HUD_CYAN_DIM),
            (self.hud_map_lbl,   'zone_lbl',  HUD_CYAN_DIM),
        ]

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

        # 카트리지 — i < ammo 면 cart-on 표시, 아니면 cart-off. 큰 숫자도 갱신.
        self.hud_ammo_num.setText(str(self.ammo))
        for i in range(self.ammo_max):
            lit = i < self.ammo
            if lit:
                self.hud_ammo_on[i].show()
                self.hud_ammo_off[i].hide()
            else:
                self.hud_ammo_on[i].hide()
                self.hud_ammo_off[i].show()
        if self.ammo == 0:
            self.hud_ammo_num.setFg(HUD_RED)
        elif not glitching:
            self.hud_ammo_num.setFg(HUD_WHITE)

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

        # 웨이브 모드 HUD — 총 처치 수 + 현재 웨이브/남은 적
        alive = sum(1 for z in self.zombies if z.hp > 0)
        self.hud_kills_num.setText(f'{self.kills:02d}')
        if self.wave_active:
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

        # 애니메이션 블렌딩 weight 수렴
        self._update_blend(dt)

        # 사격 반동 자연 감쇠 — weapon_anchor 위치에 적용 (카메라엔 영향 없음)
        decay = min(1.0, dt * self.recoil_decay)
        self.recoil_back += (0.0 - self.recoil_back) * decay

        # 발사 쿨다운 감쇠
        if self.shoot_cooldown_t > 0:
            self.shoot_cooldown_t -= dt

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

        self.ybot.setPos(self.player_pos + recoil_offset
                         + Vec3(0, 0, bob_z) + ads_offset_world)
        # 일단 pitch=0 으로 세팅 → 아래에서 shoulder 피벗 트릭으로 pitch 적용.
        self.ybot.setHpr(self.player_yaw + 180, 0, 0)
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
            self.ybot.setHpr(self.player_yaw + 180, -self.player_pitch, 0)
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
            self.weapon_anchor.setPos(self.right_hand_joint.getPos(self.render))
            self.weapon_anchor.setHpr(self.right_hand_joint.getHpr(self.render))

        # 좀비 AI tick
        for z in self.zombies:
            z.update(dt, self.player_pos)

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

        # Interact proximity — 가장 가까운 DEAD + 아직 transform 안 한 좀비 찾기
        self._interact_target = None
        best_d = self.interact_range
        for z in self.zombies:
            if z.state != Zombie.DEAD or z.transformed or z.transform_t > 0:
                continue
            d = (z.pos - self.player_pos).length()
            if d < best_d:
                best_d = d
                self._interact_target = z
        if self._interact_target is not None:
            self.interact_frame.show()
        else:
            self.interact_frame.hide()

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
    ZombieGame().run()
