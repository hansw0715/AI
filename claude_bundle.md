# zombie_game — Claude Project Bundle

학교 그룹 프로젝트 (`hansw0715/AI` GitHub, branch `2693044한승원`).
Mirror's Edge 스타일 1인칭 좀비 슈터 프로토타입.

> **현재 스냅샷 기준:** `backups/20260530-011714-reload-ok/` (zombie_game.py / scene.bam /
> scene.blend / blender_scaffold_reload.py 4종 보존). 이후 작업하다 깨지면 이 백업으로 복귀.

---

## 1. 프로젝트 개요

- **장르:** 1인칭 좀비 슈터
- **엔진:** Panda3D 1.10.16
- **캐릭터:** Mixamo Y Bot 풀바디 (카메라가 head 본에 attach)
- **무기:** 9mm Beretta (Sketchfab), RightHand 본에 attach
- **현재 단계:** Stage 1 — 1인칭 카메라 + 풀바디 + 권총 + 사격(Shoot+슬라이드 후퇴+반동) + 무릎 transition + ESC paused + R **재장전(IK 5단계 + 손등 위 자세)**

## 2. 환경

- OS: Windows 11
- Python: 3.14.5 (`C:\Users\hansw\AppData\Local\Python\pythoncore-3.14-64\`)
- Panda3D: `panda3d>=1.10.16`, `panda3d-gltf>=1.3.0`, `panda3d-blend2bam>=0.26.0`
- Blender: 5.1.2 (`C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`)

### `blend2bam` ↔ Blender 5.x 패치 (재적용 필요)
`blender_scripts/exportgltf.py` 약 309행:
```python
try:
    addon_prefs['allow_embedded_format'] = True
except (TypeError, KeyError):
    pass
```

## 3. 디렉토리 구조

```
C:\Users\hansw\workspace\AI\
├── zombie_game.py              # 메인 (Panda3D, 810 lines)
├── requirements.txt
├── README.md
├── claude_bundle.md            # ← 이 파일
├── assets/
│   ├── ybot/
│   │   ├── scene.bam           # Y Bot 메쉬 + 14개 anim (Reload 포함)
│   │   ├── scene.blend         # Blender 소스
│   │   ├── scene.backup.blend  # reload 작업 전 백업
│   │   └── scene.backup.bam
│   └── weapons/
│       ├── 9mm_pistol.glb / .blend / .bam   # ← 게임이 로드 (127KB)
│       └── animated_pistol.glb / .blend / .bam # 미사용 (Sketchfab view model)
├── backups/
│   └── 20260530-011714-reload-ok/           # Reload 완성 직후 스냅샷
│       ├── zombie_game.py
│       ├── scene.bam / scene.blend
│       └── blender_scaffold_reload.py
└── scripts/
    ├── blender_merge_ybot.py
    ├── blender_add_anims.py
    ├── blender_strip_root.py
    ├── blender_glb_to_blend.py
    ├── blender_scaffold_reload.py   # ← reload anim 스캐폴드 (FK + IK + forearm roll)
    └── peek_glb.py
```

## 4. 입력 매핑

| 입력 | 동작 |
| --- | --- |
| W/S/A/D | 이동 |
| 마우스 | 좌우 yaw만 (상하 고정) |
| Space | 점프 |
| Ctrl | 무릎 transition (StandToKneel ↔ KneelToStand) |
| 좌클릭 | Shoot (hands 단발 + 슬라이드 후퇴 + 캐릭터 뒤로 반동) |
| **R** | **Reload (upper+hands 단발, 1~4=FK + 5=IK + LeftForeArm roll)** |
| F2 | free-cam |
| ESC | paused 메뉴 (Resume / Quit) |
| **I/J/K/L/U/O** | **슬라이드 IK target marker 튜닝 (RightHand local, 2cm step)** |
| **P** | **현재 marker 좌표 dump + 화면 가운데 큰 글씨 3초 overlay** |

## 5. anim 목록 (scene.bam)

`Idle`, `RunForward`, `RunBackward`, `StrafeL`, `StrafeR`, `Jump`,
`KneelIdle`, `StandToKneel`, `KneelToStand`,
`WalkForward`, `WalkBackward`, `Shoot`, `Punch`, **`Reload`**,
`Armature|mixamo.com|Layer0` (무시).

## 6. 핵심 디자인 / Reload 시퀀스

### 6.1 골격 3파트 (`makeSubpart`)
```
lower : Hips + 다리/발               → 항상 locomotion (달리며 reload 가능)
upper : Spine + 자손 (손 제외)       → locomotion (reload 중엔 Reload)
hands : 양손 + 손가락                → Shoot/Reload 단발
```
글로브 패턴: `*Hips`/`*Spine` 좁게, `*Spine*`/`*LeftHand*`/`*RightHand*` 로 exclude.

### 6.2 권총 attach (Mixamo cm 잔재 우회)
- `setScale(self.render, ...)` 로 world 절대 크기 박음 (hand world scale = 0.01).
- `flattenLight()` 로 glTF RootNode self-transform 제거.
- `weapon_anchor` NodePath (self.render 자식) 에 weapon reparent. `_update` 안에서
  `ybot.update(force=True)` 직후 hand 본 world pos+hpr 복사 → 같은 프레임 sync (잔상 방지).
- 최종 값: `SCALE=0.1195`, `POS=(0.0, 0.09, 0.04)`, `HPR=(22.5, -78.2, 108.9)`.

### 6.3 사격 반동 = 카메라 안 흔들림
- ybot 자체를 카메라 -forward 방향 `recoil_back=3cm` 만큼 뒤로 → 팔·손·권총 다 같이 뒤로
- 카메라는 `+forward * recoil_back` 보정 → 시점 절대 위치 고정
- Slide named node 후퇴: `weapon.find('**/Slide')` + 사격 시 `+X` 방향 후퇴 + 지수 감쇠

### 6.4 Reload — v5 IK 5단계 시퀀스 + LeftForeArm roll

**시퀀스 (총 2초, END=60f, FPS=30):**
```
f0   그립 (북엔드)
f12  1) 오른손 총 살짝 기울임 + 왼손 탄창으로  ──── FK PHASES
f22  2) 왼손 탄창 빼기 (아래로)              ──── FK PHASES
f34  3) 왼손 탄창 다시 넣기 (위로)           ──── FK PHASES
f42  4) 오른손 원위치 (총 그립 복귀)          ──── FK PHASES
f48  5) 왼손 슬라이드로 (잡음)                ──── IK build_slide_ik + LFORE roll
f53  5') 슬라이드 당김 + 게임 slide_recoil    ──── IK build_slide_ik + LFORE roll
f57  5'') 그립으로 가는 중간                  ──── IK build_slide_ik + LFORE roll
f60  그립 복귀 (북엔드)
```

**1~4단계 = FK 추가회전.** 그립 포즈에 본별 (axis, deg) 누적. Mixamo 본 로컬 축이 일관 안 돼서
시도-수정 반복으로 잡힌 값들 (`scripts/blender_scaffold_reload.py` 의 `PHASES` 참조).

**5단계 = IK + 손등 위 roll.** FK 회전값으로는 손끝을 특정 위치로 못 보내는 문제 →
`build_slide_ik` 함수가 LeftForeArm 에 2본 IK constraint 임시로 걸어 target 위치로 자세 풀고,
visual matrix 를 `pb.matrix = ...` 로 키프레임 박음 (constraint 제거). 그 다음 LeftForeArm
local Y(길이축) 으로 `SLIDE_FOREARM_ROLL=90°` 추가 회전 → 손등이 위를 향함 (이전까지 손바닥이
위로 가던 문제 해결). LeftHand 만 회전 따로 (IK 체인 밖, `SLIDE_WRIST`).

**IK target = RightHand armature-space 위치 + offset (game 내 P-marker 로 잡음):**
```python
SLIDE_RIGHT        = 8.0    # X (좌우)
SLIDE_FWD          = 20.0   # Y (총신 방향 — Mixamo 본 +Y = 캐릭터 뒤, 사용자 forward = -Y)
SLIDE_UP           = 15.0   # Z (위)
SLIDE_PULL         = 6.0    # 슬라이드 당길 때 -Y
SLIDE_WRIST        = ((1, 0, 0), 20)   # 손목 회전 (IK 가 팔만 풀므로 따로)
SLIDE_FOREARM_ROLL = 90                # LFORE local Y roll → 손등 위
```

**런타임 통합 (`_play_reload_oneshot`):**
- upper+hands 두 파트에 `Reload` 단발. lower 는 locomotion 그대로 (달리며 reload OK, 단
  Section 8 의 흔들림 이슈 있음).
- `dur * 0.88` 시점에 `slide_recoil = slide_recoil_kick` (f53 ≈ 0.88) 동기.
- `back_after` 콜백: `_reload_oneshot=False` + `current_anim='__reload_done__'` sentinel
  → 다음 프레임 `_update_locomotion` 강제 재평가.
- reload 중 Shoot/Ctrl 입력 잠금.

### 6.5 ESC paused 메뉴
`DirectFrame` + Resume/Quit `DirectButton`. paused = `_update` early return + cursor visible
+ absolute mode.

### 6.6 카메라
- head 본 world pos + `eye_forward_offset=0.18m` 시선 방향 + `eye_lateral_offset=0.10m`
  왼쪽 (= 권총 우측 배치, FPS 표준)
- 사격 시 ybot 뒤로 가는 만큼 `+forward * recoil_back` 보정 → 시점 고정
- 1인칭 yaw 만, F2 free-cam 만 pitch 허용

## 7. Reload 자산 재빌드

```powershell
$blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
Set-Location "C:\Users\hansw\workspace\AI"

# (a) Reload 액션 스캐폴드 (FK PHASES + IK build_slide_ik + LFORE roll)
& $blender --background --python "scripts\blender_scaffold_reload.py" -- `
  "assets/ybot/scene.blend" "assets/ybot/scene.blend"

# (b) Reload 의 Hips location 키 제거 (in-place 화)
& $blender --background --python "scripts\blender_strip_root.py" -- `
  "assets/ybot/scene.blend" Reload

# (c) .blend → .bam
python -m blend2bam --blender-dir "C:\Program Files\Blender Foundation\Blender 5.1" `
  "assets/ybot/scene.blend" "assets/ybot/scene.bam"
```

스캐폴드는 메쉬 안 건드림 → 반복 안전. `scene.backup.blend` 백업 보존.

## 8. 알려진 이슈 / TODO

- **Reload 완성 상태.** SLIDE IK + `SLIDE_FOREARM_ROLL=90` 로 손등 위 자세 잡힘.
  좋은 상태가 `backups/20260530-011714-reload-ok/` 에 스냅샷으로 박혀 있음.
  이후 변경하다 깨지면 이 폴더에서 `zombie_game.py`/`scene.bam`/`scene.blend`/
  `blender_scaffold_reload.py` 를 다시 복사.
- **걸으면서 R 누르면 권총·팔이 화면 밖으로 휘둘리는 버그.** RunForward 의 Hips
  회전(Hips location 만 strip 되고 H/P/R 은 그대로) 이 Spine→Arm→Hand 에 전파되는데,
  upper 파트가 Reload(정적 grip 포즈) 라 평소처럼 Spine 자체 sway 로 상쇄 안 됨.
  → 머리는 Hips Z 축 위라 거의 안 움직이는데 손은 앞·옆 거리 때문에 큰 호 →
  카메라(머리 따라감) 기준으로 권총·손이 화면 가장자리로 휘둘림. 가만히 있을 때는
  Reload 모션이 그대로 잘 보임. 접근 후보:
  - (a) reload 중 Hips HPR 을 ref(Idle 캡처값) 으로 ramp lock → 상체 안정, 다리는
    children 이라 자기 swing 그대로 → "행진" 느낌 (실험 결과 카메라/총 안정성은 OK 였음)
  - (b) lower 에 Idle 가중 섞어 Hips 흔들림 dampen (다리 swing 도 함께 줄어듦)
  - (c) 카메라/weapon anchor 만 stabilized frame 에서 sample 하는 보정 (보이는 손/팔은
    여전히 흔들려서 총이 손에서 떨어져 보이는 부작용 — 시도해봤지만 자연스럽지 못함)
  현재 미해결, 다음 세션 과제.
- marker 하네스 (I/J/K/L/U/O/P) 는 튜닝 끝나면 통째 제거 예정.
- 좀비 spawn / AI, 머즐 플래시 / 사격음, 맵 디자인 — 미구현.

## 9. 실행

```powershell
cd C:\Users\hansw\workspace\AI; python zombie_game.py
```

---

# 10. 코드 전문

## 10.1 `zombie_game.py`

```python
"""
zombie_game — Mirror's Edge style 1인칭 좀비 슈터 (Panda3D)
Stage 1: 1인칭 카메라 + Y Bot 풀바디 + 기본 입력.
"""
import random
from math import cos, radians, sin
from pathlib import Path

from direct.actor.Actor import Actor
from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import (
    AmbientLight, CardMaker, ClockObject, DirectionalLight, Filename,
    LineSegs, NodePath, Quat, TextNode, Vec3, Vec4, WindowProperties,
)


SCRIPT_DIR = Path(__file__).parent
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
        self.setBackgroundColor(0.45, 0.6, 0.85)
        self._make_lights()
        self._make_ground()
        self._make_landmarks()

        # 카메라 — 캐릭터 머리 안쪽에서 보더라도 클리핑 안 되게 near 매우 작게.
        # FOV 크면 시야 넓어지고 자기 몸이 작게 보임 (FPS 표준 90~100).
        self.camLens.setNear(0.01)
        self.camLens.setFov(100)

        # 플레이어 상태 (panda3d 표준: Z-up, Y-forward)
        self.player_pos = Vec3(0, 0, 0)  # 발 기준
        self.player_yaw = 0.0            # H (좌우)
        self.player_pitch = 0.0          # P (위아래)
        self.player_vz = 0.0
        self.on_ground = True
        self.head_height = 1.65
        self.move_speed = 6.0
        self.mouse_sens = 0.15
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

        # HUD
        self.hud = OnscreenText(
            text='',
            pos=(-1.7, 0.92), scale=0.045,
            fg=(1, 1, 1, 1), bg=(0, 0, 0, 0.5),
            align=TextNode.ALeft, mayChange=True,
            parent=self.aspect2d,
        )

        # 일시정지 메뉴 (ESC 토글)
        self.paused = False
        self._build_pause_menu()

        # 메인 루프
        self.taskMgr.add(self._update, 'game_update')

        # 진단: Idle 한 프레임 돌고 나서 본 이름/좌표 한 번 출력
        self.taskMgr.doMethodLater(0.3, self._dump_joints, 'dump_joints')

    # --- world setup --------------------------------------------------------

    def _make_lights(self):
        amb = AmbientLight('ambient')
        amb.setColor(Vec4(0.4, 0.4, 0.4, 1))
        self.render.setLight(self.render.attachNewNode(amb))

        dl = DirectionalLight('dir')
        dl.setColor(Vec4(0.85, 0.85, 0.8, 1))
        dlnp = self.render.attachNewNode(dl)
        dlnp.setHpr(45, -55, 0)
        self.render.setLight(dlnp)

    def _make_ground(self):
        cm = CardMaker('ground')
        cm.setFrame(-32, 32, -32, 32)
        gnd = self.render.attachNewNode(cm.generate())
        gnd.setHpr(0, -90, 0)  # XY 평면으로 눕히기
        gnd.setColor(0.55, 0.55, 0.58, 1)

    def _make_landmarks(self):
        # 빈 월드면 이동 감각이 없으니 색깔 막대 몇 개를 흩뿌려서 시각적 단서.
        rng = random.Random(42)
        for i in range(10):
            cm = CardMaker(f'mark_{i}')
            cm.setFrame(-0.4, 0.4, 0, 2.0)
            card = self.render.attachNewNode(cm.generate())
            card.setTwoSided(True)
            card.setPos(rng.uniform(-15, 15), rng.uniform(-15, 15), 0)
            card.setH(rng.uniform(0, 360))
            card.setColor(rng.uniform(0.3, 1), rng.uniform(0.3, 1), rng.uniform(0.3, 1), 1)

    # --- input --------------------------------------------------------------

    def _bind_inputs(self):
        for k in ('w', 'a', 's', 'd', 'space'):
            self.accept(k, self._set_key, [k, True])
            self.accept(f'{k}-up', self._set_key, [k, False])
        self.accept('escape', self._toggle_pause)
        self.accept('mouse1', self._play_shoot_oneshot)
        self.accept('r', self._play_reload_oneshot)
        self.accept('f2', self._toggle_editor)
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

    def _play_shoot_oneshot(self):
        if 'Shoot' not in self.anim_names or self._hands_oneshot or self._reload_oneshot:
            return
        # hands 만 Shoot 자세로 — 다리/상체는 그대로.
        self.ybot.play('Shoot', partName='hands')
        self.recoil_back = self.recoil_shoot_back
        self.slide_recoil = self.slide_recoil_kick
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
        rl = {a: (1.0 if a == 'Reload' else 0.0) for a in self.anim_names}
        self._target_w['upper'] = dict(rl)
        self._target_w['hands'] = dict(rl)
        self._reload_token += 1
        token = self._reload_token
        dur = self.ybot.getDuration('Reload')

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

    def _toggle_editor(self):
        self.editor_mode = not self.editor_mode
        # cursor 상태는 안 바꿈 (양쪽 다 confined+hidden = 무한 회전 가능).
        if self.editor_mode:
            # editor 진입: 현재 카메라 위치/방향에서 시작 → 시각적 점프 없음.
            self.editor_pos = Vec3(self.camera.getPos(self.render))
            self.editor_yaw = self.player_yaw
            self.editor_pitch = self.player_pitch
        self.win.movePointer(0, self._win_cx, self._win_cy)
        self._first_frame = True

    # --- pause menu ---------------------------------------------------------

    def _build_pause_menu(self):
        # 어두운 반투명 배경 + 가운데 PAUSED + Resume/Quit 두 버튼.
        self.pause_frame = DirectFrame(
            frameColor=(0, 0, 0, 0.6),
            frameSize=(-0.5, 0.5, -0.4, 0.4),
            pos=(0, 0, 0),
            parent=self.aspect2d,
        )
        OnscreenText(
            text='PAUSED', pos=(0, 0.22), scale=0.12,
            fg=(1, 1, 1, 1), align=TextNode.ACenter, mayChange=False,
            parent=self.pause_frame,
        )
        DirectButton(
            text='Resume',
            scale=0.08, pos=(0, 0, 0.0),
            command=self._toggle_pause,
            parent=self.pause_frame,
            frameSize=(-3, 3, -0.8, 1.2),
        )
        DirectButton(
            text='Quit',
            scale=0.08, pos=(0, 0, -0.22),
            command=self.userExit,
            parent=self.pause_frame,
            frameSize=(-3, 3, -0.8, 1.2),
        )
        self.pause_frame.hide()

    def _toggle_pause(self):
        self.paused = not self.paused
        props = WindowProperties()
        if self.paused:
            self.pause_frame.show()
            # cursor 보이게 + absolute 모드로 메뉴 클릭 가능.
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)
        else:
            self.pause_frame.hide()
            # 다시 게임으로 — confined + hidden + 첫 프레임 mouse delta 무시.
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

        # 애니메이션 블렌딩 weight 수렴
        self._update_blend(dt)

        # 사격 반동 자연 감쇠 — weapon_anchor 위치에 적용 (카메라엔 영향 없음)
        decay = min(1.0, dt * self.recoil_decay)
        self.recoil_back += (0.0 - self.recoil_back) * decay
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
                # 1인칭은 좌우(yaw)만 — 상하 시점은 고정 (편의 / 멀미 방지).
                # editor (F2 free-cam) 모드에선 위아래도 가능.
                self.player_yaw -= dx * self.mouse_sens

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
                    self.player_pos += mv * (self.move_speed * dt)
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

        # 현재 상태에 맞는 locomotion anim 선택
        self._update_locomotion()

        # 캐릭터 트랜스폼 동기화 (+ Hips XY anchor 보정 + 사격 반동 뒤로 이동).
        # 사격 반동은 캐릭터 전체를 카메라 forward 의 반대 방향으로 살짝 밀어서
        # 팔·손·권총 다 같이 뒤로 빠지게. 카메라는 아래쪽에서 보정해서 시점은 고정.
        yr_recoil = radians(self.player_yaw)
        fwd_recoil = Vec3(-sin(yr_recoil), cos(yr_recoil), 0)
        recoil_offset = fwd_recoil * (-self.recoil_back)
        self.ybot.setPos(self.player_pos + recoil_offset)
        self.ybot.setH(self.player_yaw + 180)
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

        # weapon anchor 갱신: hand 본 따라감. ybot 자체가 사격 반동으로 뒤로 가서
        # hand 본 world 좌표도 자동으로 뒤로 — 추가 offset 불필요.
        if (self.weapon is not None
                and self.right_hand_joint is not None
                and not self.right_hand_joint.isEmpty()):
            self.weapon_anchor.setPos(self.right_hand_joint.getPos(self.render))
            self.weapon_anchor.setHpr(self.right_hand_joint.getHpr(self.render))

        # 카메라 배치
        if self.editor_mode:
            # free-cam: editor_pos / editor_yaw / pitch 그대로 사용
            self.camera.setPos(self.editor_pos)
            self.camera.setHpr(self.editor_yaw, self.editor_pitch, 0)
        else:
            # 카메라를 Head 본 월드 좌표에 부착. 머리 애니메이션 그대로 따라감.
            # 시선 방향(yaw/pitch) 은 마우스 입력 그대로 — head 본의 회전은 무시.
            # 사격 반동(recoil_pitch/back)은 매 프레임 감쇠되며 카메라에 가산.
            if self.head_joint is not None:
                head_w = self.head_joint.getPos(self.render)
                yr = radians(self.player_yaw)
                forward = Vec3(-sin(yr), cos(yr), 0)
                right_v = Vec3(cos(yr), sin(yr), 0)
                # 카메라 시점 고정: ybot 이 recoil_back 만큼 뒤로 가서 head_w 도
                # 같이 뒤로 가있는 상태. +forward * recoil_back 으로 보정 → 카메라
                # 절대 위치는 사격 전과 동일.
                # left lateral offset 추가 → 권총·손이 화면 우측에 보임 (FPS 표준).
                self.camera.setPos(
                    head_w
                    + forward * (self.eye_forward_offset + self.recoil_back)
                    - right_v * self.eye_lateral_offset
                )
            else:
                self.camera.setPos(self.player_pos + Vec3(0, 0, self.head_height))
            self.camera.setHpr(self.player_yaw, self.player_pitch, 0)

        # HUD
        fps = ClockObject.getGlobalClock().getAverageFrameRate()
        self.hud.setText(
            f'anim:  {self.current_anim}'
            f'{"  +Shoot(hands)" if self._hands_oneshot else ""}'
            f'{"  +Reload(upper)" if self._reload_oneshot else ""}\n'
            f'fps:   {fps:.0f}\n'
            f'pos:   ({self.player_pos.x:.1f}, {self.player_pos.y:.1f}, {self.player_pos.z:.1f})\n'
            f'mode:  {"editor[F2]" if self.editor_mode else "fps"}'
            f'{"  KNEEL" if self.kneel_state == "kneel" else ""}'
            f'{"  KNEEL->" if self.kneel_state == "going_down" else ""}'
            f'{"  STAND->" if self.kneel_state == "going_up" else ""}'
        )

        return Task.cont


if __name__ == '__main__':
    ZombieGame().run()
```

## 10.2 `scripts/blender_scaffold_reload.py` — Reload anim 빌드

```python
"""
scene.blend 에 'Reload' 액션을 스캐폴딩 (헤드리스 Blender) — 멀티페이즈 버전.

시퀀스:
  그립 → 오른손으로 총 살짝 기울임 + 왼손 탄창으로 → 빈 탄창 빼서 아래로
       → 왼손 최저(새 탄창 집기) → 탄창 삽입 → 왼손 슬라이드로 → 슬라이드 당김 → 그립 복귀

- 북엔드(f0 / END)는 GRIP_SOURCE_ANIM(기본 Idle) 그립 포즈 → locomotion 과 이음새 없음
- 각 페이즈에서 명시한 본만 그립 포즈에 추가 회전, 나머지 본은 그립 유지
- 오른손(총) tilt 는 '살짝'만 + 끝에서 그립 복귀 → 총이 화면에서 안정적
- 슬라이드 래킹은 게임 코드의 slide_recoil 가 담당 (이 스크립트는 손 모션만)

각 추가 회전은 Mixamo 로컬 축 기준이라 방향이 어긋날 수 있음 → PHASES 의 axis / deg 튜닝.

사용:
  blender --background --python scripts/blender_scaffold_reload.py -- \
      assets/ybot/scene.blend assets/ybot/scene.blend [GRIP_SOURCE_ANIM]
"""
import sys
from math import radians

import bpy
from mathutils import Quaternion, Vector

# --- 튜닝 상수 ---------------------------------------------------------------
FPS = 30
END_FRAME = 60          # 2.0초
PREFIX = 'mixamorig:'

R_HAND = 'RightHand'
L_ARM, L_FORE, L_HAND = 'LeftArm', 'LeftForeArm', 'LeftHand'

LARM_J  = PREFIX + 'LeftArm'
LFORE_J = PREFIX + 'LeftForeArm'
LHAND_J = PREFIX + 'LeftHand'
RHAND_J = PREFIX + 'RightHand'

# 슬라이드 IK target = 그립 RightHand 위치 + 오프셋 (armature cm 단위).
# 게임 안에서 P-marker 로 잡은 RightHand-local 좌표 (10, 16, 4).
SLIDE_RIGHT = 8.0     # X
SLIDE_FWD   = 20.0    # Y
SLIDE_UP    = 15.0    # Z
SLIDE_PULL  = 6.0     # 슬라이드 당길 때 -Y 로 뒤로
SLIDE_WRIST = ((1, 0, 0), 20)        # 손목은 작은 회전만 (이전 좋은 값)
SLIDE_FOREARM_ROLL = 90              # LeftForeArm 길이축 (Y) — 손등 위 향하게

# 페이즈 키프레임. (frame, { 본접미사: ((axis), deg), ... })
# 명시 안 된 본 = 그립 포즈 유지. deg = 그립 포즈에 누적할 로컬 추가 회전.
# 방향/크기가 이상하면 해당 항목의 axis 벡터 / deg 부호·값만 바꾸면 됨.
PHASES = [
    (0,  {}),                                                    # 그립 (북엔드)
    (12, {R_HAND: ((0, 1, 0), 14),
          L_ARM:  ((1, 0, 0), -20), L_FORE: ((1, 0, 0), 38)}),   # 1) 총 기울임 + 왼손 탄창으로
    (22, {R_HAND: ((0, 1, 0), 14),
          L_ARM:  ((1, 0, 0), -32), L_FORE: ((1, 0, 0), 30),
          L_HAND: ((1, 0, 0), -25)}),                            # 2) 탄창 빼기
    (34, {R_HAND: ((0, 1, 0), 14),
          L_ARM:  ((1, 0, 0), -22), L_FORE: ((1, 0, 0), 42),
          L_HAND: ((1, 0, 0), 15)}),                             # 3) 탄창 넣기
    (42, {R_HAND: ((0, 1, 0), 0),
          L_ARM:  ((1, 0, 0), -18), L_FORE: ((1, 0, 0), 44)}),   # 4) 오른손 원위치
    (60, {}),                                                    # 그립 복귀 (북엔드)
    # 5) 슬라이드 페이즈는 build_slide_ik() 가 f48/f53/f57 에 IK 결과로 키 박음
]
# ----------------------------------------------------------------------------

argv = sys.argv
if '--' not in argv:
    raise SystemExit('args required after --')
argv = argv[argv.index('--') + 1:]
in_blend = argv[0]
out_blend = argv[1]
grip_anim = argv[2] if len(argv) > 2 else 'Idle'

bpy.ops.wm.open_mainfile(filepath=in_blend)

scene = bpy.context.scene
scene.render.fps = FPS
scene.frame_start = 0
scene.frame_end = END_FRAME

arm = bpy.data.objects.get('YBot') or next(
    (o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
if arm is None:
    raise SystemExit('No armature found')

bpy.context.view_layer.objects.active = arm
arm.select_set(True)

if not arm.animation_data:
    arm.animation_data_create()
ad = arm.animation_data

for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'


def bind_slot(action):
    """slotted action(Blender 4.4+) 이면 첫 slot 을 active 로 bind."""
    if hasattr(ad, 'action_slot') and ad.action_slot is None and len(action.slots):
        ad.action_slot = action.slots[0]


# --- 1) 그립 포즈 캡처 -------------------------------------------------------
grip_action = bpy.data.actions.get(grip_anim)
if grip_action is None:
    raise SystemExit(f'grip source action {grip_anim!r} not found')

ad.action = grip_action
bind_slot(grip_action)
scene.frame_set(int(grip_action.frame_range[0]))
bpy.context.view_layer.update()

grip = {}
grip_pos = {}                      # armature-space 위치 (IK target 계산용)
for pb in arm.pose.bones:
    grip[pb.name] = (pb.rotation_quaternion.copy(), pb.location.copy())
    grip_pos[pb.name] = pb.matrix.translation.copy()

# --- 2) Reload 액션 생성 -----------------------------------------------------
old = bpy.data.actions.get('Reload')
if old is not None:
    old.use_fake_user = False
    bpy.data.actions.remove(old)

reload_action = bpy.data.actions.new('Reload')
reload_action.use_fake_user = True
ad.action = reload_action
bind_slot(reload_action)


def apply_grip(pb):
    q, loc = grip[pb.name]
    pb.rotation_quaternion = q
    pb.location = loc


def key_bone(pb, frame):
    pb.keyframe_insert(data_path='rotation_quaternion', frame=frame)
    pb.keyframe_insert(data_path='location', frame=frame)


def build_slide_ik(scene):
    """슬라이드 페이즈(f48/f53/f57)를 2본 IK 로 풀어 visual rotation 으로 bake."""
    from mathutils import Vector

    # 진단: grip 포즈에서 LeftHand 본 armature-space 로컬축
    for pb in arm.pose.bones:
        apply_grip(pb)
    bpy.context.view_layer.update()
    lh = arm.pose.bones[LHAND_J]
    print('[axis] LHAND x=', lh.bone.x_axis, ' y=', lh.bone.y_axis,
          ' z=', lh.bone.z_axis, flush=True)

    rhand_p = grip_pos[RHAND_J]
    lhand_p = grip_pos[LHAND_J]
    base = rhand_p + Vector((SLIDE_RIGHT, SLIDE_FWD, SLIDE_UP))   # 슬라이드 잡는 위치
    targets = {
        48: base,                                            # 잡음
        53: base + Vector((0.0, -SLIDE_PULL, -7.0)),         # 뒤로 + 아래로 7cm
        57: base * 0.5 + lhand_p * 0.5,                      # 놓고 그립으로 중간
    }

    tgt = bpy.data.objects.new('SlideIKTarget', None)
    scene.collection.objects.link(tgt)

    lfore = arm.pose.bones[LFORE_J]
    ik = lfore.constraints.new('IK')
    ik.target = tgt
    ik.chain_count = 2
    ik.use_tail = True

    # Pass 1: IK 평가된 visual matrix 수집
    collected = {}
    for f, tpos in targets.items():
        scene.frame_set(f)
        tgt.location = arm.matrix_world @ tpos
        bpy.context.view_layer.update()
        collected[f] = {
            LARM_J:  arm.pose.bones[LARM_J].matrix.copy(),
            LFORE_J: arm.pose.bones[LFORE_J].matrix.copy(),
        }
        lh = arm.pose.bones[LHAND_J].matrix.translation
        print(f'[ik] f{f} target={tpos} -> LeftHand={lh}', flush=True)

    lfore.constraints.remove(ik)
    bpy.data.objects.remove(tgt, do_unlink=True)
    bpy.context.view_layer.update()

    # Pass 2: 전체 본 그립 + 왼팔 IK visual 로 덮어쓰기
    from mathutils import Quaternion, Vector as V
    wrist_axis, wrist_deg = SLIDE_WRIST
    for f, mats in collected.items():
        scene.frame_set(f)
        for pb in arm.pose.bones:
            apply_grip(pb)
        bpy.context.view_layer.update()
        for pb in arm.pose.bones:
            key_bone(pb, f)
        # 부모(LARM) 먼저, update, 그 다음 LFORE
        pb = arm.pose.bones[LARM_J]
        pb.matrix = mats[LARM_J]
        key_bone(pb, f)
        bpy.context.view_layer.update()
        pb = arm.pose.bones[LFORE_J]
        pb.matrix = mats[LFORE_J]
        bpy.context.view_layer.update()
        # forearm 길이축(local Y) 기준 roll 추가 — position 은 유지, 손 회전됨
        roll_q = Quaternion(V((0, 1, 0)), radians(SLIDE_FOREARM_ROLL))
        pb.rotation_quaternion = pb.rotation_quaternion @ roll_q
        key_bone(pb, f)
        bpy.context.view_layer.update()
        # 손목은 IK 체인 밖 → 작은 회전만
        pb = arm.pose.bones[LHAND_J]
        q_grip, _ = grip[LHAND_J]
        pb.rotation_quaternion = q_grip @ Quaternion(V(wrist_axis), radians(wrist_deg))
        key_bone(pb, f)


# --- 3) 페이즈 키프레임 ------------------------------------------------------
for frame, overrides in PHASES:
    # 먼저 전체 본을 그립 포즈로
    for pb in arm.pose.bones:
        apply_grip(pb)
    # 이 페이즈에서 지정된 본만 추가 회전
    for suffix, (axis, deg) in overrides.items():
        pb = arm.pose.bones.get(PREFIX + suffix)
        if pb is None:
            print(f'[scaffold] WARN bone not found: {PREFIX + suffix}', flush=True)
            continue
        q_grip, _ = grip[pb.name]
        pb.rotation_quaternion = q_grip @ Quaternion(Vector(axis), radians(deg))
    # 전체 본 키 (지정 안 된 본은 그립값으로 고정 → 정지)
    for pb in arm.pose.bones:
        key_bone(pb, frame)

# --- 3') 슬라이드 페이즈: 2본 IK 로 풀어서 visual rotation 키 박음 -----------
build_slide_ik(scene)

# --- 4) NLA push down --------------------------------------------------------
for t in list(ad.nla_tracks):
    if t.name == 'Reload':
        ad.nla_tracks.remove(t)
track = ad.nla_tracks.new()
track.name = 'Reload'
track.strips.new('Reload', 0, reload_action)
ad.action = None

bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print('[scaffold] Reload action (multiphase) written OK', flush=True)
```

## 10.3 `scripts/blender_strip_root.py` (Reload 에도 사용)

```python
"""
지정된 액션들에서 mixamorig:Hips 본의 location 키프레임을 모두 제거 — root motion
제거 후 in-place 애니메이션으로 만든다. 캐릭터는 제자리에서 동작하고, 실제 이동은
런타임 코드가 player_pos 로 처리.

원본 위치 키프레임을 그대로 두면 사이클 끝에서 Hips Y 가 갑자기 0 으로 리셋되며,
런타임의 hips anchor 코드가 1 프레임 동안 actor 를 큰 거리만큼 점프시키게 됨 →
카메라가 머리 뒤로 빠지면서 자기 몸이 화면을 덮어 깜빡이는 현상.

사용:
    blender --background --python scripts/blender_strip_root.py -- \
        IN_BLEND action1 action2 ...

Blender 5.1 의 slotted action API 에 대응 (action.fcurves 직접 접근 X,
layers / strips / channelbag 경유).
"""
import sys

import bpy

argv = sys.argv
if '--' not in argv:
    raise SystemExit('args required after --')
argv = argv[argv.index('--') + 1:]
in_blend = argv[0]
target_anims = argv[1:]

print(f'IN_BLEND: {in_blend}', flush=True)
print(f'TARGETS : {target_anims}', flush=True)


def iter_action_fcurves(action):
    """Yield (container, fcurve) for any action format (legacy/slotted)."""
    if hasattr(action, 'fcurves'):
        try:
            for fcu in action.fcurves:
                yield action.fcurves, fcu
            return
        except Exception:
            pass
    # Blender 4.4+ slotted
    for layer in action.layers:
        for strip in layer.strips:
            for slot in action.slots:
                cbag = strip.channelbag(slot)
                if cbag is None:
                    continue
                for fcu in cbag.fcurves:
                    yield cbag.fcurves, fcu


bpy.ops.wm.open_mainfile(filepath=in_blend)

for anim_name in target_anims:
    action = bpy.data.actions.get(anim_name)
    if action is None:
        print(f'WARN: action {anim_name} not found', flush=True)
        continue
    targets = [
        (container, fcu)
        for container, fcu in iter_action_fcurves(action)
        if fcu.data_path == 'pose.bones["mixamorig:Hips"].location'
    ]
    for container, fcu in targets:
        container.remove(fcu)
    print(f'STRIPPED {anim_name}: removed {len(targets)} Hips.location fcurves', flush=True)

bpy.ops.wm.save_mainfile()
print('SAVED', flush=True)
```

## 10.4 다른 scripts (요약)

- **`blender_add_anims.py`** — 기존 scene.blend 에 새 anim FBX 추가 (anim 별 1 NLA track).
- **`blender_glb_to_blend.py`** — .glb import → anim 제거 (옵션 `--keep-anims`/`--remove pattern`)
  → .blend 저장. panda3d-gltf BufferError 우회용.
- **`peek_glb.py`** — .glb JSON 헤더만 파싱해서 nodes / meshes / animations 요약.
- **`blender_merge_ybot.py`** — 처음부터 Y Bot.fbx + 8 anim FBX 머지 (정식 절차).

## 11. requirements.txt

```
panda3d>=1.10.16
panda3d-gltf>=1.3.0
panda3d-blend2bam>=0.26.0
```

---

**끝.** Reload 본체 (FK + IK + LeftForeArm Y-roll 90°) 는 완성 상태이고
`backups/20260530-011714-reload-ok/` 에 보존됨. 남은 과제는 **걸으면서 R 누를 때
RunForward 의 Hips 회전이 상체로 전파되어 권총·팔이 화면 밖으로 휘둘리는 문제** —
가만히 있을 때 reload 모션은 정상.
