# zombie_game — Claude Project Bundle

학교 그룹 프로젝트 (`hansw0715/AI` GitHub, branch `2693044한승원`).
Mirror's Edge / Valorant 스타일 1인칭 좀비 슈터 프로토타입.

> **현재 스냅샷**: Y Bot 플레이어 + 4 마리 좀비 (X Bot) AI. ADS / 십자 조준점 / 8발 ammo
> / muzzle flash / tracer / 마우스 감도 슬라이더 / ±89° pitch / Valorant 스타일 body 숨김 /
> 좀비 시야 기반 추격·랜덤 공격 모두 통합.

---

## 1. 프로젝트 개요

- **장르:** 1인칭 좀비 슈터
- **엔진:** Panda3D 1.10.16
- **플레이어:** Mixamo Y Bot — 카메라가 head 본 attach, mesh 는 split 되어 **팔만 visible**
- **무기:** 9mm Beretta (Sketchfab), RightHand 본에 attach, pitch 추적
- **적:** Mixamo X Bot + Not So Scary Zombie Pack anim — 시야 기반 추격, 랜덤 4개 공격 모션
- **현재 단계:** Stage 1 완성도
  - 1인칭 카메라 (head attach + ADS body offset + ±89° pitch + bob/recoil 보정)
  - Valorant 스타일 — Alpha_Surface 가 body+legs / arms 두 메쉬로 split 되어 1인칭에선
    body+legs hide, F2 free-cam 진입 시 자동 show
  - 권총: Shoot (~5.5발/초 쿨다운, 슬라이드 후퇴, ammo -1), Reload (5단계 IK + LFORE roll,
    완료 시 ammo 충전), 우클릭 ADS (FOV 100°→55° + ybot body offset)
  - 조준점·총구·tracer 모두 player_yaw+pitch 따라감
  - 좀비 AI: IDLE/CHASE/ATTACK 상태머신, sight cone 기반 추격, 랜덤 공격

## 2. 환경

- OS: Windows 11
- Python: 3.14.5 (`C:\Users\hansw\AppData\Local\Python\pythoncore-3.14-64\`)
- Panda3D: `panda3d>=1.10.16`, `panda3d-gltf>=1.3.0`, `panda3d-blend2bam>=0.26.0`
- Blender: 5.1.2 (`C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`)

### `blend2bam` ↔ Blender 5.x 패치 (재적용 필요)

`{python_site_packages}/blend2bam/blender_scripts/exportgltf.py` 약 309 행:

```python
try:
    addon_prefs['allow_embedded_format'] = True
except (TypeError, KeyError):
    pass
```

## 3. 디렉토리 구조

```
C:\Users\hansw\workspace\AI\
├── zombie_game.py              # 메인 (Panda3D, ~1180 lines)
├── requirements.txt
├── README.md
├── claude_bundle.md            # ← 이 파일
├── assets/
│   ├── ybot/                   # 플레이어 (Y Bot)
│   │   ├── scene.bam           # mesh + 14 anim, Alpha_Surface 가 body / *_Arms 로 split
│   │   ├── scene.blend         # Blender 소스
│   │   └── scene.backup.{bam,blend}
│   ├── zombie/                 # 좀비 (X Bot + Not So Scary Pack)
│   │   ├── scene.bam           # X Bot mesh + 6 anim (Idle / Run / Attack1~4)
│   │   └── scene.blend
│   └── weapons/
│       ├── 9mm_pistol.{glb,blend,bam}      # 현재 사용
│       └── (animated_pistol, mark_23 — 미사용)
├── backups/
│   ├── 20260530-011714-reload-ok/          # Reload 완성 직후
│   └── 20260530-035325-pre-skin/           # skin 교체 직전 baseline
└── scripts/
    ├── blender_merge_ybot.py               # FBX 머지 → scene.blend (base + anims)
    ├── blender_add_anims.py
    ├── blender_strip_root.py               # Hips XYZ location 제거 (in-place 화)
    ├── blender_scaffold_reload.py          # Reload anim 빌드 (FK + IK + LFORE roll)
    ├── blender_normalize_bones.py          # mixamorig9: → mixamorig: 정규화
    ├── blender_offset_bone.py              # 본 회전 오프셋 anim 키프레임 bake
    ├── blender_split_arms.py               # ★ Alpha_Surface mesh 를 arm / body 로 split
    ├── blender_glb_to_blend.py
    └── peek_glb.py
```

## 4. 조작 / 입력 매핑

| 입력 | 동작 |
| --- | --- |
| W / S | 전진 / 후진 |
| A / D | 좌 / 우 스트레이프 |
| **마우스** | **좌우 yaw + 상하 pitch (±89°)** — 위·아래 자유 시야 |
| Space | 점프 |
| Ctrl | 무릎 transition |
| **좌클릭** | **Shoot** — 0.18s 쿨다운(~5.5발/초), ammo -1, muzzle flash + tracer (둘 다 yaw+pitch 방향), slide 후퇴 + 카메라 반동 |
| **우클릭 (hold)** | **ADS** — FOV 100°→55° + ybot 이 `ads_body_offset` 으로 이동 (카메라 보정) |
| **R** | Reload — upper+hands 단발, 완료 시 ammo = 8 충전 |
| F2 | 3인칭 free-cam 토글 (자동으로 body mesh 다시 show) |
| ESC | Pause 메뉴 (Resume / Mouse Sensitivity slider 0.02~0.30 / Quit) |
| I/J/K/L/U/O/P | 슬라이드 IK marker 튜닝 (RightHand-local) |

## 5. 자산

### 5.1 플레이어 (Y Bot) — 14 anim

`Idle, RunForward, RunBackward, StrafeL, StrafeR, Jump, KneelIdle, StandToKneel,
KneelToStand, WalkForward, WalkBackward, Shoot, Punch, Reload` + Mixamo container 무시.

### 5.2 좀비 (X Bot + Not So Scary Zombie Pack) — 6 anim

`Idle = zombie idle.fbx`, `Run = zombie running.fbx`,
`Attack1 = zombie attack.fbx`, `Attack2 = zombie headbutt.fbx`,
`Attack3 = zombie punching.fbx`, `Attack4 = zombie kicking.fbx`.

## 6. 핵심 디자인

### 6.1 골격 3파트 + Reload (그대로)

`lower (Hips+다리) / upper (Spine+자손-손) / hands (양손)`.
Reload 는 `scripts/blender_scaffold_reload.py` 가 FK 4단계 + IK 3단계 + LeftForeArm Y-roll
90° 로 합성. SLIDE_RIGHT=8, FWD=20, UP=15 (cm armature).

### 6.2 권총 attach + Shoot + 반동

- `weapon_anchor` (render 자식) 가 매 프레임 `right_hand_joint` 의 world pos 따라감.
  **HPR 은 hand.HPR 의 (H, P + player_pitch, R)** — pitch 만 마우스 위·아래에 더해서 총이
  조준선 따라가게.
- Shoot: 0.18s 쿨다운 (`shoot_cooldown_t`), ammo -1, hands subpart 단발, ybot 뒤로 3cm
  recoil + 카메라 보정으로 시점 고정, slide named node 후퇴.
- **8발 탄창** — `ammo_max=8`. 좌클릭 1발 감소, R 재장전 완료 시 `ammo_max` 충전. ammo==0
  이면 좌클릭 무반응 (HUD 에 `EMPTY (R)`).

### 6.3 ADS

우클릭 hold → `aim_t` 0→1 (~110ms ramp). FOV 100°→55° + ybot 을 player-frame
`Vec3(-0.13, 0.05, -0.02)` 만큼 이동 (좌 13 + 앞 5 + 아래 2cm). 카메라는 같은 양 -로 보정
→ 손·팔·총 다 같이 이동, 화면 정적.

### 6.4 1인칭 시야 — 마우스 ±89° pitch

```python
self.player_yaw -= dx * self.mouse_sens
self.player_pitch -= dy * self.mouse_sens
self.player_pitch = max(-89.0, min(89.0, self.player_pitch))
```

카메라: `setHpr(player_yaw, player_pitch, 0)`. tracer: `setHpr(player_yaw, player_pitch, 0)` —
총알이 카메라 시선 방향으로 정확히 날아감. weapon_anchor: hand.P + player_pitch 로 총 도
같이 기울어짐.

### 6.5 Valorant 스타일 body 숨김

Y Bot 의 `Alpha_Surface` (17K verts) 는 단일 mesh 라 그대로는 body/arms 분리 불가.
`scripts/blender_split_arms.py` 가 각 vertex 의 dominant weight 본이 LeftShoulder /
LeftArm / LeftForeArm / LeftHand / Right- 계열이면 별도 메쉬 `Alpha_Surface_Arms` 로 떼어냄.
Alpha_Joints 도 동일. 결과: 4 개 mesh — body 2 / arms 2.

런타임: `self._body_meshes` = `[Alpha_Surface, Alpha_Joints]` 만 hide/show. F2 editor 진입 시
`_set_body_visible(True)`, FPS 복귀 시 `False`. arms 는 항상 visible.

joint transform 은 anim 시스템이 계속 갱신하므로 weapon_anchor / camera follow 영향 없음.

### 6.6 Muzzle flash + Tracer

- Muzzle flash: `weapon_anchor` parent (ybot 숨겨도 영향 X), 5cm billboard quad, additive
  blend, 60ms 후 fade. 위치 `(0.08, 0.32, 0.08)` m (hand-local 8cm right + 32cm forward +
  8cm up).
- Tracer: render parent, thickness 1 LineSegs, muzzle 위치에서 player_yaw + player_pitch
  방향으로 30m 직선, 50ms 후 hide.

### 6.7 좀비 AI (Zombie 클래스)

| 상태 | 동작 |
| --- | --- |
| IDLE | Idle anim loop. `can_see_player()` true 면 CHASE |
| CHASE | Run anim, 플레이어 방향으로 `move_speed=2.5` m/s 이동, 매 프레임 yaw 갱신해서 향함. 시야 잃으면 IDLE, 거리 < `attack_range=1.8` 면 ATTACK |
| ATTACK | `random.choice([Attack1, Attack2, Attack3, Attack4])` 단발. anim 끝나면 거리/시야 다시 판정 |

시야 (`can_see_player`):
- 평면 거리 < `sight_range=25` AND
- 좌우 시야각 < ±`sight_fov_half=70°` (전체 140°)
- 거리 < 0.5m 면 시야각 무시 (코앞 인지)

스폰: 4 마리 — `(8,12)`, `(-9,8)`, `(0,-10)`, `(13,-3)` (m), 각자 다른 yaw 로 두리번거리는
방향 다양화. 시야 안 들어오면 가만히 있다가 플레이어 발견 시 추격 시작.

### 6.8 걸으면서 Reload + walk bob

`_update_locomotion`: reload 중 W/S 일 때 lower target 을 `Idle` 로 강제 (RunForward 의
Hips pitch 가 권총·팔 화면 밖으로 빼는 문제 회피). 대신 `_walk_bob_t` ramp + ybot Z 사인파
+ 카메라 보정으로 자기 몸·팔·총만 까딱이는 효과.

### 6.9 Mouse Sensitivity 슬라이더

ESC pause 메뉴 — `DirectSlider` (range 0.02~0.30, value=0.10) + 현재값 표시. 매 변경마다
`_on_sens_change` 가 `self.mouse_sens` 즉시 갱신.

## 7. 자산 재빌드

### 7.1 플레이어 (Y Bot) — 12 anim + Reload 스캐폴드 + arms split

```powershell
$blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
$fbx     = "C:\fbx"
Set-Location "C:\Users\hansw\workspace\AI"

# (1) Y Bot + 12 anim → scene.blend
& $blender --background --python scripts/blender_merge_ybot.py -- `
  "$fbx\Y Bot.fbx" "assets/ybot/scene.blend" `
  "Idle=$fbx\pistol idle.fbx" "RunForward=$fbx\pistol run.fbx" `
  "RunBackward=$fbx\pistol run backward.fbx" `
  "StrafeL=$fbx\pistol strafe (2).fbx" "StrafeR=$fbx\pistol strafe.fbx" `
  "Jump=$fbx\pistol jump.fbx" "KneelIdle=$fbx\pistol kneeling idle.fbx" `
  "Shoot=$fbx\pistol idle.fbx" `
  "WalkForward=$fbx\pistol walk.fbx" "WalkBackward=$fbx\pistol walk backward.fbx" `
  "StandToKneel=$fbx\pistol stand to kneel.fbx" "KneelToStand=$fbx\pistol kneel to stand.fbx" `
  "Punch=$fbx\Punching.fbx"

# (1a) 변종 prefix 정규화 (Ch15/Ch31 같은 경우)
& $blender --background --python scripts/blender_normalize_bones.py -- `
  "assets/ybot/scene.blend"

# (2) locomotion Hips location strip
& $blender --background --python scripts/blender_strip_root.py -- `
  "assets/ybot/scene.blend" RunForward RunBackward StrafeL StrafeR Jump WalkForward WalkBackward

# (3) Reload 스캐폴드
& $blender --background --python scripts/blender_scaffold_reload.py -- `
  "assets/ybot/scene.blend" "assets/ybot/scene.blend"

# (4) Reload Hips strip
& $blender --background --python scripts/blender_strip_root.py -- `
  "assets/ybot/scene.blend" Reload

# (5) ★ Valorant 스타일을 위한 arms/body split — 새로 추가
& $blender --background --python scripts/blender_split_arms.py -- `
  "assets/ybot/scene.blend"

# (6) .blend → .bam
python -m blend2bam --blender-dir "C:\Program Files\Blender Foundation\Blender 5.1" `
  --textures copy "assets/ybot/scene.blend" "assets/ybot/scene.bam"
```

### 7.2 좀비 (X Bot + Zombie Pack)

```powershell
$zp = "C:\Users\hansw\Downloads\Not So Scary Zombie Pack"
& $blender --background --python scripts/blender_merge_ybot.py -- `
  "$zp\X Bot.fbx" "assets/zombie/scene.blend" `
  "Idle=$zp\zombie idle.fbx" "Run=$zp\zombie running.fbx" `
  "Attack1=$zp\zombie attack.fbx" "Attack2=$zp\zombie headbutt.fbx" `
  "Attack3=$zp\zombie punching.fbx" "Attack4=$zp\zombie kicking.fbx"

& $blender --background --python scripts/blender_normalize_bones.py -- `
  "assets/zombie/scene.blend"

& $blender --background --python scripts/blender_strip_root.py -- `
  "assets/zombie/scene.blend" Idle Run

python -m blend2bam --blender-dir "C:\Program Files\Blender Foundation\Blender 5.1" `
  --textures copy "assets/zombie/scene.blend" "assets/zombie/scene.bam"
```

## 8. 알려진 이슈 / TODO

- **위·아래 시야 시 팔과 총 align 미세 차이** — weapon_anchor 만 pitch 따라가고 가시 팔
  mesh 는 anim-driven 그대로. 극단 각도 (±60° 이상) 에서 손과 총이 조금 어긋나 보일 수
  있음. 어깨 controlJoint 로 arm chain 도 pitch 시키는 접근 시도했으나 일단 보류
  (anim breathing 손실 + axis 튜닝 필요).
- **shoot_cooldown 영구 저장 미구현** — 매 실행마다 기본값. mouse_sens 도 동일.
- marker 하네스 (I/J/K/L/U/O/P) 는 튜닝 끝나면 제거.
- 좀비 데미지 / 플레이어 HP / 죽음 anim — 미구현.
- 맵 디자인 — 빈 평면 + 색깔 막대만.
- muzzle flash / tracer / 좀비 의 occlusion (벽 뒤 가림) — 현재 항상 위에 그려짐.

## 9. 실행

```powershell
cd C:\Users\hansw\workspace\AI; python zombie_game.py
```

clone 직후도 `pip install -r requirements.txt` 후 위 한 줄로 바로 실행됨 (scene.bam 들이
레포에 포함).

---

# 10. 코드 전문

## 10.1 `zombie_game.py` — 메인 (1180 lines)

```python
"""
zombie_game — Mirror's Edge style 1인칭 좀비 슈터 (Panda3D).
"""
import random
from math import atan2, cos, degrees, radians, sin
from pathlib import Path

from direct.actor.Actor import Actor
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectSlider
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import (
    AmbientLight, CardMaker, ClockObject, ColorBlendAttrib, DirectionalLight,
    Filename, LineSegs, NodePath, Quat, TextNode, Vec3, Vec4, WindowProperties,
)


SCRIPT_DIR = Path(__file__).parent
BAM_PATH    = Filename.from_os_specific(str(SCRIPT_DIR / 'assets' / 'ybot' / 'scene.bam'))
WEAPON_PATH = Filename.from_os_specific(str(SCRIPT_DIR / 'assets' / 'weapons' / '9mm_pistol.bam'))
ZOMBIE_BAM  = Filename.from_os_specific(str(SCRIPT_DIR / 'assets' / 'zombie' / 'scene.bam'))

WEAPON_LOCAL_SCALE = 0.1195
WEAPON_LOCAL_POS   = (0.000, 0.090, 0.040)
WEAPON_LOCAL_HPR   = (22.5, -78.2, 108.9)


class Zombie:
    """좀비 한 마리 — Actor + 상태머신(IDLE/CHASE/ATTACK) + 시야 기반 AI.

    시야: 평면 거리 < sight_range AND 좌우 시야각 ±sight_fov_half 안 → 본다.
      IDLE   — 가만히 Idle. 플레이어 시야 안 들어오면 CHASE.
      CHASE  — Run + 추격 이동. 근접 시 ATTACK, 시야 잃으면 IDLE.
      ATTACK — Attack1~4 중 random 단발. 끝나면 거리/시야 재판정.
    """
    IDLE, CHASE, ATTACK = 'idle', 'chase', 'attack'

    def __init__(self, game, spawn_pos, yaw=0.0):
        self.game = game
        self.actor = Actor(ZOMBIE_BAM)
        self.actor.reparentTo(game.render)
        self.anim_names = [a for a in self.actor.getAnimNames()
                           if 'mixamo.com' not in a]
        self.pos = Vec3(spawn_pos)
        self.yaw = yaw
        self.actor.setPos(self.pos)
        self.actor.setH(self.yaw + 180)

        self.move_speed     = 2.5
        self.sight_range    = 25.0
        self.sight_fov_half = 70.0
        self.attack_range   = 1.8
        self.attack_anims = [a for a in ('Attack1', 'Attack2', 'Attack3', 'Attack4')
                              if a in self.anim_names]

        self.state = self.IDLE
        self.current_anim = None
        self.attack_t = 0.0
        self._play('Idle', loop=True)

    def _play(self, anim, loop=False):
        if anim not in self.anim_names or self.current_anim == anim:
            return
        (self.actor.loop if loop else self.actor.play)(anim)
        self.current_anim = anim

    def can_see_player(self, player_pos):
        to_p = player_pos - self.pos
        to_p.z = 0
        dist = to_p.length()
        if dist > self.sight_range:
            return False
        if dist < 0.5:
            return True
        yr = radians(self.yaw)
        forward = Vec3(-sin(yr), cos(yr), 0)
        to_p.normalize()
        return forward.dot(to_p) > cos(radians(self.sight_fov_half))

    def _start_attack(self):
        if not self.attack_anims:
            return
        attack = random.choice(self.attack_anims)
        self.current_anim = None    # play() 재트리거 위해 reset
        self._play(attack, loop=False)
        self.attack_t = self.actor.getDuration(attack)
        self.state = self.ATTACK

    def update(self, dt, player_pos):
        to_p = player_pos - self.pos
        to_p.z = 0
        dist = to_p.length()
        sees = self.can_see_player(player_pos)

        if self.state == self.IDLE:
            self._play('Idle', loop=True)
            if sees:
                self.state = self.CHASE
        elif self.state == self.CHASE:
            if not sees:
                self.state = self.IDLE
            elif dist < self.attack_range:
                self._start_attack()
            else:
                self._play('Run', loop=True)
                if dist > 0.01:
                    direction = Vec3(to_p.x / dist, to_p.y / dist, 0)
                    self.pos.x += direction.x * self.move_speed * dt
                    self.pos.y += direction.y * self.move_speed * dt
                    self.yaw = degrees(atan2(-direction.x, direction.y))
        elif self.state == self.ATTACK:
            self.attack_t -= dt
            if self.attack_t <= 0:
                if sees and dist < self.attack_range:
                    self._start_attack()
                elif sees:
                    self.state = self.CHASE
                else:
                    self.state = self.IDLE

        self.actor.setPos(self.pos)
        self.actor.setH(self.yaw + 180)


class ZombieGame(ShowBase):
    def __init__(self):
        super().__init__()
        props = WindowProperties()
        props.setTitle('zombie_game')
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_confined)
        self.win.requestProperties(props)
        self.disableMouse()

        self.setBackgroundColor(0.45, 0.6, 0.85)
        self._make_lights()
        self._make_ground()
        self._make_landmarks()

        self.camLens.setNear(0.01)
        self.fov_hip = 100.0
        self.fov_ads = 55.0
        self.camLens.setFov(self.fov_hip)

        # ADS
        self.aiming = False
        self.aim_t = 0.0
        self.aim_speed = 9.0
        self.ads_body_offset = Vec3(-0.13, 0.05, -0.02)   # 좌 13 + 앞 5 + 아래 2cm

        # 플레이어 상태 (player_pitch ±89°)
        self.player_pos = Vec3(0, 0, 0)
        self.player_yaw = 0.0
        self.player_pitch = 0.0
        self.player_vz = 0.0
        self.on_ground = True
        self.head_height = 1.65
        self.move_speed = 6.0
        self.mouse_sens = 0.10
        self.jump_speed = 4.5
        self.gravity = 12.0

        # Y Bot Actor + 3 파트 subpart + 블렌드 + Kneel state
        self.ybot = Actor(BAM_PATH)
        self.ybot.reparentTo(self.render)
        self.ybot.setPos(self.player_pos)
        self.ybot.setH(self.player_yaw + 180)
        self.anim_names = list(self.ybot.getAnimNames())
        self._parts = ('lower', 'upper', 'hands')
        self.ybot.makeSubpart('lower', includeJoints=['*Hips'],
            excludeJoints=['*Spine*', '*LeftHand*', '*RightHand*'])
        self.ybot.makeSubpart('upper', includeJoints=['*Spine'],
            excludeJoints=['*LeftHand*', '*RightHand*'])
        self.ybot.makeSubpart('hands', includeJoints=['*LeftHand*', '*RightHand*'])
        self.ybot.enableBlend()
        if 'Idle' in self.anim_names:
            for p in self._parts:
                self.ybot.loop('Idle', partName=p)

        # 단발/블렌드 상태
        self.kneel_state = 'stand'
        self.current_anim = 'Idle'
        self._hands_oneshot = False
        self._anim_token = 0
        self._hands_token = 0
        self._reload_oneshot = False
        self._reload_token = 0
        self._current_w = {p: {a: (1.0 if a == 'Idle' else 0.0) for a in self.anim_names}
                           for p in self._parts}
        self._target_w = {p: dict(d) for p, d in self._current_w.items()}
        for p in self._parts:
            for a, w in self._current_w[p].items():
                self.ybot.setControlEffect(a, w, partName=p)
        self.blend_speed = 14.0
        self.blend_out_time = 0.18
        self._loop_anim_set = {'Idle', 'RunForward', 'RunBackward', 'StrafeL',
            'StrafeR', 'KneelIdle', 'Jump', 'WalkForward', 'WalkBackward'}
        for a in self.anim_names:
            if a in self._loop_anim_set:
                for p in self._parts:
                    self.ybot.loop(a, partName=p)

        # 사격 반동 + walk bob
        self.recoil_back = 0.0
        self.recoil_decay = 10.0
        self.recoil_shoot_back = 0.03
        self._walk_bob_t = 0.0
        self._walk_bob_phase = 0.0
        self._walk_bob_amp_z = 0.025
        self._walk_bob_freq = 10.0
        self._walk_bob_speed = 5.0

        # Hips/Head expose + 권총 attach (RightHand)
        hips_name = next((j.getName() for j in self.ybot.getJoints()
                          if j.getName().endswith('Hips')), None)
        head_name = next((j.getName() for j in self.ybot.getJoints()
                          if j.getName().endswith('Head')), None)
        self.hips_joint = (self.ybot.exposeJoint(None, 'lower', hips_name)
                           if hips_name else None)
        self.head_joint = (self.ybot.exposeJoint(None, 'upper', head_name)
                           if head_name else None)
        self._hips_ref_local = None

        rhand_name = next((j.getName() for j in self.ybot.getJoints()
                           if j.getName().endswith('RightHand')), None)
        self.right_hand_joint = (self.ybot.exposeJoint(None, 'hands', rhand_name)
                                 if rhand_name else None)
        if self.right_hand_joint is not None and WEAPON_PATH.exists():
            self.weapon = self.loader.loadModel(WEAPON_PATH)
            self.weapon.flattenLight()
            self.weapon_anchor = self.render.attachNewNode('weapon_anchor')
            self.weapon.reparentTo(self.weapon_anchor)
            self.weapon.setScale(WEAPON_LOCAL_SCALE)
            self.weapon.setPos(*WEAPON_LOCAL_POS)
            self.weapon.setHpr(*WEAPON_LOCAL_HPR)
            self.weapon.setTwoSided(True)
            self.slide_node = self.weapon.find('**/Slide')
            if self.slide_node.isEmpty():
                self.slide_node = None
            else:
                self.slide_rest_x = self.slide_node.getX()
            self.slide_recoil = 0.0
            self.slide_recoil_kick = 0.4
            self.slide_recoil_decay = 14.0
        else:
            self.weapon = None

        # slide marker 임시 하네스 (생략 — 기존과 동일)

        self.eye_forward_offset = 0.18
        self.eye_lateral_offset = 0.10

        # 입력 + 마우스 center + HUD
        self.keys = {'w': False, 'a': False, 's': False, 'd': False, 'space': False}
        self.editor_mode = False
        self.editor_pos = Vec3(0, -5, 1.6)
        self.editor_yaw = 0.0
        self.editor_pitch = 0.0
        self.editor_speed = 8.0
        self._bind_inputs()
        self._win_cx = self.win.getXSize() // 2
        self._win_cy = self.win.getYSize() // 2
        self.win.movePointer(0, self._win_cx, self._win_cy)
        self._first_frame = True
        self.hud = OnscreenText(text='', pos=(-1.7, 0.92), scale=0.045,
            fg=(1, 1, 1, 1), bg=(0, 0, 0, 0.5),
            align=TextNode.ALeft, mayChange=True, parent=self.aspect2d)

        # 탄창 + 쿨다운
        self.ammo_max = 8
        self.ammo = self.ammo_max
        self.shoot_cooldown_t = 0.0
        self.shoot_cooldown_dur = 0.18    # ~5.5 발/초

        # Muzzle flash — weapon_anchor parent (ybot hide 영향 X)
        if self.weapon is not None and self.right_hand_joint is not None:
            cm_mf = CardMaker('muzzle_flash')
            cm_mf.setFrame(-1, 1, -1, 1)
            self.muzzle_flash = self.weapon_anchor.attachNewNode(cm_mf.generate())
            self.muzzle_flash.setPos(0.08, 0.32, 0.08)
            self.muzzle_flash_base_scale = 0.025
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

        # Tracer
        ls_tr = LineSegs('tracer')
        ls_tr.setThickness(1)
        ls_tr.setColor(1.0, 0.9, 0.55, 0.65)
        ls_tr.moveTo(0, 0, 0); ls_tr.drawTo(0, 30, 0)
        self.tracer = self.render.attachNewNode(ls_tr.create())
        self.tracer.setTransparency(True)
        self.tracer.setLightOff()
        self.tracer.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd))
        self.tracer.setBin('fixed', 99)
        self.tracer.setDepthWrite(False)
        self.tracer.hide()
        self.tracer_t = 0.0
        self.tracer_dur = 0.05

        # Pause + crosshair + Valorant body hide + zombies
        self.paused = False
        self._build_pause_menu()
        self._build_crosshair()
        self._body_meshes = []
        for name in ('Alpha_Surface', 'Alpha_Joints'):
            np = self.ybot.find(f'**/{name}')
            if not np.isEmpty():
                self._body_meshes.append(np)
        self._set_body_visible(False)
        self.zombies = []
        self._spawn_zombies()

        self.taskMgr.add(self._update, 'game_update')
        self.taskMgr.doMethodLater(0.3, self._dump_joints, 'dump_joints')

    def _spawn_zombies(self):
        if not ZOMBIE_BAM.exists():
            print(f'[zombie] BAM not found: {ZOMBIE_BAM}', flush=True)
            return
        spawns = [(Vec3( 8, 12, 0),  180), (Vec3(-9,  8, 0),  150),
                  (Vec3( 0, -10, 0),   0), (Vec3(13, -3, 0),  -90)]
        for pos, yaw in spawns:
            self.zombies.append(Zombie(self, pos, yaw))
        print(f'[zombie] spawned {len(self.zombies)} zombies', flush=True)

    # === 입력 / Kneel / target_anim / _update_locomotion ===
    # (위 기존 코드와 동일. _play_shoot_oneshot 만 변경:)

    def _play_shoot_oneshot(self):
        if self.paused or self.ammo <= 0 or self.shoot_cooldown_t > 0:
            return
        if 'Shoot' not in self.anim_names or self._reload_oneshot:
            return
        self.ammo -= 1
        self.shoot_cooldown_t = self.shoot_cooldown_dur
        self.ybot.play('Shoot', partName='hands')
        self.recoil_back = self.recoil_shoot_back
        self.slide_recoil = self.slide_recoil_kick
        if self.muzzle_flash is not None:
            self.muzzle_flash_t = self.muzzle_flash_dur
            self.muzzle_flash.setScale(self.muzzle_flash_base_scale)
            self.muzzle_flash.show()
            # Tracer 는 yaw + pitch 방향
            self.tracer.setPos(self.muzzle_flash.getPos(self.render))
            self.tracer.setHpr(self.player_yaw, self.player_pitch, 0)
            self.tracer.show()
            self.tracer_t = self.tracer_dur
        self._hands_oneshot = True
        # ... (token + _back 콜백, 기존과 동일)

    # === Valorant body hide ===

    def _set_body_visible(self, visible):
        for np in self._body_meshes:
            (np.show if visible else np.hide)()

    def _toggle_editor(self):
        self.editor_mode = not self.editor_mode
        if self.editor_mode:
            self.editor_pos = Vec3(self.camera.getPos(self.render))
            self.editor_yaw = self.player_yaw
            self.editor_pitch = self.player_pitch
            self._set_body_visible(True)
        else:
            self._set_body_visible(False)
        self.win.movePointer(0, self._win_cx, self._win_cy)
        self._first_frame = True

    # === _update 의 핵심 변경: ±89° pitch, weapon_anchor pitch, zombie tick ===

    def _update(self, task):
        if self.paused:
            return Task.cont
        dt = ClockObject.getGlobalClock().getDt()
        self._update_blend(dt)

        decay = min(1.0, dt * self.recoil_decay)
        self.recoil_back += (0.0 - self.recoil_back) * decay
        if self.shoot_cooldown_t > 0:
            self.shoot_cooldown_t -= dt
        # muzzle flash / tracer timer (기존)
        # slide_recoil 감쇠 (기존)

        # 마우스 룩 — 1인칭은 yaw + pitch (±89°)
        if self.win.hasPointer(0):
            md = self.win.getPointer(0)
            dx = md.getX() - self._win_cx
            dy = md.getY() - self._win_cy
            self.win.movePointer(0, self._win_cx, self._win_cy)
            if self._first_frame:
                self._first_frame = False
            elif self.editor_mode:
                self.editor_yaw -= dx * self.mouse_sens
                self.editor_pitch -= dy * self.mouse_sens
                self.editor_pitch = max(-89.0, min(89.0, self.editor_pitch))
            else:
                self.player_yaw -= dx * self.mouse_sens
                self.player_pitch -= dy * self.mouse_sens
                self.player_pitch = max(-89.0, min(89.0, self.player_pitch))

        # WASD 이동 (기존) → _update_locomotion → ybot.setPos + walk bob + ADS offset
        # ybot.update(force=True) → Hips XY anchor
        # ADS ramp + FOV 보간
        # 카메라 setPos (head_w + offsets - bob - ads_offset_world)
        # 카메라 setHpr(player_yaw, player_pitch, 0)

        # weapon_anchor 갱신 — pitch 만 player_pitch 더함
        if (self.weapon is not None and self.right_hand_joint is not None
                and not self.right_hand_joint.isEmpty()):
            self.weapon_anchor.setPos(self.right_hand_joint.getPos(self.render))
            h = self.right_hand_joint.getHpr(self.render)
            self.weapon_anchor.setHpr(h.x, h.y + self.player_pitch, h.z)

        # 좀비 AI tick
        for z in self.zombies:
            z.update(dt, self.player_pos)

        # HUD (ammo / state / ADS)
        return Task.cont


if __name__ == '__main__':
    ZombieGame().run()
```

> **참고**: 위 §10.1 은 핵심 구조 + 신규/변경 부분만 발췌한 1180 라인 zombie_game.py 의
> **압축본**. 실제 파일에는 `_make_lights / _make_ground / _make_landmarks`, `_bind_inputs`,
> slide marker 하네스 (I/J/K/L/U/O/P), `_play_kneel_transition`, `_play_reload_oneshot`,
> `_build_pause_menu` / `_on_sens_change` / `_build_crosshair` / `_toggle_pause` / `_dump_joints`,
> 그리고 `_update` 의 전체 로직이 다 있음. 코드는 `zombie_game.py` 1003~1180 라인.

## 10.2 `scripts/blender_split_arms.py` — ★ Valorant body split (신규)

```python
"""
ybot 의 Alpha_Surface 메쉬에서 팔/손/어깨 부분 vertex 들만 따로 떼서
Alpha_Arms 라는 별도 메쉬로 분리. Valorant 스타일 1인칭 (몸·다리 hidden,
팔·손만 visible) 을 위한 mesh split. armature / vertex group / anim 은 그대로.
"""
import sys
import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
in_blend = argv[0]

ARM_VG_PREFIXES = (
    'mixamorig:LeftShoulder', 'mixamorig:LeftArm',
    'mixamorig:LeftForeArm', 'mixamorig:LeftHand',
    'mixamorig:RightShoulder', 'mixamorig:RightArm',
    'mixamorig:RightForeArm', 'mixamorig:RightHand',
)

def is_arm_vg(name):
    return any(name.startswith(p) for p in ARM_VG_PREFIXES)

bpy.ops.wm.open_mainfile(filepath=in_blend)
processed = 0
for ob_name in [o.name for o in bpy.data.objects if o.type == 'MESH']:
    ob = bpy.data.objects.get(ob_name)
    if ob is None or ob.name.endswith('_Arms'):
        continue
    bpy.context.view_layer.objects.active = ob
    for o in bpy.data.objects: o.select_set(False)
    ob.select_set(True)
    arm_vg_indices = {vg.index for vg in ob.vertex_groups if is_arm_vg(vg.name)}
    if not arm_vg_indices:
        continue
    bpy.ops.object.mode_set(mode='OBJECT')
    for v in ob.data.vertices: v.select = False
    arm_count = 0
    for v in ob.data.vertices:
        if not v.groups: continue
        max_g = max(v.groups, key=lambda g: g.weight)
        if max_g.group in arm_vg_indices:
            v.select = True
            arm_count += 1
    if arm_count == 0:
        continue
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='SELECTED')
    bpy.ops.object.mode_set(mode='OBJECT')
    new_name = next((o.name for o in bpy.data.objects
                     if o.name.startswith(ob.name) and o.name != ob.name), None)
    if new_name:
        bpy.data.objects[new_name].name = ob.name + '_Arms'
        processed += 1
print(f'TOTAL split: {processed} meshes', flush=True)
bpy.ops.wm.save_mainfile()
print('SAVED', flush=True)
```

## 10.3 다른 scripts (요약)

- **`blender_merge_ybot.py`** — base FBX + anim FBX 머지 → scene.blend (NLA push).
- **`blender_strip_root.py`** — `pose.bones["mixamorig:Hips"].location` fcurve 제거.
- **`blender_scaffold_reload.py`** — Reload 액션 빌드 (FK PHASES + IK build_slide_ik +
  LeftForeArm Y-roll 90°). SLIDE_RIGHT=8, FWD=20, UP=15.
- **`blender_normalize_bones.py`** — `mixamorig9:*` / `mixamorig10:*` → `mixamorig:*`
  정규화 (bone + vertex group).
- **`blender_offset_bone.py`** — 본의 모든 action keyframe 의 rotation_quaternion 에
  quat 오프셋 post-multiply. `bone-local` 좌표계 회전 누적.
- **`blender_add_anims.py`** — 기존 .blend 에 anim FBX 추가 (NLA 트랙 갈아끼움).
- **`blender_glb_to_blend.py`** — .glb → .blend 변환 (panda3d-gltf BufferError 우회).
- **`peek_glb.py`** — .glb JSON 헤더 요약.

## 11. requirements.txt

```
panda3d>=1.10.16
panda3d-gltf>=1.3.0
panda3d-blend2bam>=0.26.0
```

---

**끝.** 현재 코드 = Y Bot 플레이어 (Valorant 스타일 body 숨김, 팔/손만 보임) + 4 마리 좀비
(시야 기반 추격 + 랜덤 4종 공격) + ±89° pitch + ADS / crosshair / 8발 ammo / muzzle flash
/ tracer / 0.18s 발사 쿨다운 / 마우스 감도 슬라이더. 빌드 파이프라인에 `blender_split_arms.py`
+ 좀비 머지 단계 추가됨.
