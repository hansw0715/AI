# zombie_game

Mirror's Edge 스타일 1인칭 좀비 슈터 프로토타입 (Panda3D).
풀바디 Mixamo Y Bot 캐릭터를 그대로 두고 카메라를 머리 본에 attach해서 — 아래 보면 자기 몸/다리, 옆 보면 어깨가 보이는 시점. 9mm 권총을 RightHand 본에 부착해서 사격 / 슬라이드 후퇴 / 5단계 IK 재장전까지 동작.

> 이전 ursina 기반 FPS 프로토타입은 `zombie_game_ursina.py` 로 보존 (참고용).
> 메인 코드는 `zombie_game.py` (Panda3D 직접 사용).

## 조작

| 입력 | 동작 |
| --- | --- |
| W / S | 전진 / 후진 (Run) |
| A / D | 좌 / 우 스트레이프 |
| 마우스 | 좌우 시선 (yaw) — 상하 고정 (멀미 방지) |
| Space | 점프 |
| Ctrl | 무릎 자세 토글 (StandToKneel ↔ KneelToStand) |
| 좌클릭 | Shoot — hands 단발 + 슬라이드 후퇴 + 캐릭터 뒤로 반동 |
| **R** | **Reload — upper + hands 단발 (FK 1~4단계 + IK 슬라이드 5단계)** |
| F2 | 3인칭 free-cam 토글 (디버그용) |
| ESC | Pause 메뉴 (Resume / Quit) |
| I / J / K / L / U / O | 슬라이드 IK target marker 튜닝 (RightHand-local, 2cm step — 임시 하네스) |
| P | 현재 marker 좌표 dump + 화면 가운데 큰 글씨 3초 overlay |

## 실행

```powershell
pip install -r requirements.txt
python zombie_game.py
```

`assets/ybot/scene.bam` + `assets/weapons/9mm_pistol.bam` 이 이미 레포에 포함되어 있어서 위 두 줄이면 끝.

## 의존성

- **Python 3.11+** (테스트 환경: 3.14.3)
- **panda3d** ≥ 1.10.16 — 런타임 엔진
- **panda3d-gltf** ≥ 1.3.0 — bam 의 glTF 자산 import
- **panda3d-blend2bam** ≥ 0.26.0 — 자산 재빌드용 (런타임 불필요)
- **Blender 5.1+** — 자산 재빌드용 (런타임 불필요)

`assets/ybot/scene.bam` 가 정상이면 Blender 와 blend2bam 은 설치 안 해도 됨.

### `blend2bam` ↔ Blender 5.x 패치 (재적용 필요)

`blend2bam` 0.26.0 은 Blender 5.x 의 glTF exporter 옵션 키 변경으로 깨짐. pip 설치 후 다음 파일을 패치:

```
{python_site_packages}/blend2bam/blender_scripts/exportgltf.py
```

약 309 행:

```python
try:
    addon_prefs['allow_embedded_format'] = True
except (TypeError, KeyError):
    pass
```

`pip install --force-reinstall` 하면 다시 깨지니까 재적용 필요.

## 자산 — Mixamo

게임에 들어간 13 개 애니메이션 중 12 개는 [Mixamo](https://www.mixamo.com) 에서 무료로 받음. 1 개 (Reload) 는 Blender 스크립트가 Idle 그립 포즈에서 직접 빌드. Adobe 계정만 있으면 다 받을 수 있음.

### 필요한 파일

1. **Y Bot** (캐릭터)
   - Mixamo → CHARACTERS → "Y Bot" 검색 → **DOWNLOAD** → FBX Binary, **Without Animation**, T-Pose
   - 저장명: `Y Bot.fbx`

2. **애니메이션** — Y Bot 을 선택한 상태에서 ANIMATIONS 탭에서 검색 후 각각 다운로드.
   FBX Binary / 30 fps / **Without Skin** / In Place 옵션은 체크하지 않아도 됨 (어차피 본 프로젝트가 root motion 을 제거함).

   | 검색 키워드 | 저장명 | 게임 내 이름 |
   | --- | --- | --- |
   | Pistol Idle | `pistol idle.fbx` | Idle, Shoot |
   | Pistol Run | `pistol run.fbx` | RunForward |
   | Pistol Run Backward | `pistol run backward.fbx` | RunBackward |
   | Pistol Strafe (왼쪽) | `pistol strafe (2).fbx` | StrafeL |
   | Pistol Strafe (오른쪽) | `pistol strafe.fbx` | StrafeR |
   | Pistol Jump | `pistol jump.fbx` | Jump |
   | Pistol Kneeling Idle | `pistol kneeling idle.fbx` | KneelIdle |
   | Pistol Stand To Kneel | `pistol stand to kneel.fbx` | StandToKneel |
   | Pistol Kneel To Stand | `pistol kneel to stand.fbx` | KneelToStand |
   | Pistol Walk | `pistol walk.fbx` | WalkForward |
   | Pistol Walk Backward | `pistol walk backward.fbx` | WalkBackward |
   | Punching | `Punching.fbx` | Punch (현재 미사용 — 빌드만 함) |

   > 참고: 본 프로젝트는 Mixamo 의 *Pistol_Handgun Locomotion Pack* 파일명을 그대로 사용했다. 같은 모션을 다른 이름으로 받았다면 빌드 명령어의 경로만 맞춰주면 됨.

3. **Reload** 는 다운로드 안 함 — `scripts/blender_scaffold_reload.py` 가 Idle 의 grip 포즈에서 FK 4 단계 + 2 본 IK 슬라이드 3 키프레임 + LeftForeArm Y-roll 90° 를 직접 합성해서 만든다.

### 자산 재빌드

다운받은 12 개 FBX 를 한 폴더에 모은 뒤 (예: `C:\fbx\`):

```powershell
$blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
$fbx     = "C:\fbx"
Set-Location "C:\Users\hansw\workspace\AI"

# (1) Y Bot + 12 개 anim FBX → 단일 scene.blend 머지
& $blender --background --python scripts/blender_merge_ybot.py -- `
  "$fbx\Y Bot.fbx" `
  "assets/ybot/scene.blend" `
  "Idle=$fbx\pistol idle.fbx" `
  "RunForward=$fbx\pistol run.fbx" `
  "RunBackward=$fbx\pistol run backward.fbx" `
  "StrafeL=$fbx\pistol strafe (2).fbx" `
  "StrafeR=$fbx\pistol strafe.fbx" `
  "Jump=$fbx\pistol jump.fbx" `
  "KneelIdle=$fbx\pistol kneeling idle.fbx" `
  "Shoot=$fbx\pistol idle.fbx" `
  "WalkForward=$fbx\pistol walk.fbx" `
  "WalkBackward=$fbx\pistol walk backward.fbx" `
  "StandToKneel=$fbx\pistol stand to kneel.fbx" `
  "KneelToStand=$fbx\pistol kneel to stand.fbx" `
  "Punch=$fbx\Punching.fbx"

# (2) locomotion 액션들에서 Hips 본 location 키프레임 제거 (in-place 화)
& $blender --background --python scripts/blender_strip_root.py -- `
  "assets/ybot/scene.blend" RunForward RunBackward StrafeL StrafeR Jump WalkForward WalkBackward

# (3) Reload 액션 스캐폴드 (FK PHASES + IK build_slide_ik + LFORE roll)
& $blender --background --python scripts/blender_scaffold_reload.py -- `
  "assets/ybot/scene.blend" "assets/ybot/scene.blend"

# (4) Reload 의 Hips location 도 strip
& $blender --background --python scripts/blender_strip_root.py -- `
  "assets/ybot/scene.blend" Reload

# (5) .blend → .bam 변환
python -m blend2bam --blender-dir "C:\Program Files\Blender Foundation\Blender 5.1" `
  "assets/ybot/scene.blend" "assets/ybot/scene.bam"
```

스캐폴드는 메쉬 안 건드림 → 반복 안전. `assets/ybot/scene.backup.{blend,bam}` 가 reload 작업 이전 baseline 백업. `backups/` 폴더에는 두 시점 스냅샷 보존 (자세한 건 `claude_bundle.md` 참조).

### 캐릭터 교체 (Y Bot → 다른 Mixamo 캐릭터)

Mixamo 의 다른 캐릭터로 교체할 때는 (1) 단계의 `"$fbx\Y Bot.fbx"` 자리에 새 캐릭터 FBX 경로만 넣고 위 전체를 다시 실행. 본 이름이 `mixamorig:*` 표준이라 anim 들이 자동 바인딩됨. 단:

- 새 캐릭터의 손 크기·자세에 따라 `zombie_game.py` 의 `WEAPON_LOCAL_POS / HPR / SCALE` (38~40 행) 재튜닝 필요할 수 있음. F2 디버그 카메라 + 슬라이드 marker 키 (I/J/K/L/U/O/P) 로 잡으면 됨.
- 키가 다르면 `eye_forward_offset` / `head_height` 도 미세조정.
- `SLIDE_RIGHT / FWD / UP` (`blender_scaffold_reload.py` 40~42 행) 도 손 크기 다르면 재조정 후 스캐폴드 재실행.

## 파일 구조

```
.
├── zombie_game.py             # 메인 게임 (Panda3D, ~810 lines)
├── zombie_game_ursina.py      # 이전 ursina 프로토타입 (legacy)
├── requirements.txt
├── README.md                  # ← 이 파일
├── claude_bundle.md           # Claude Project 용 풀 스냅샷 (코드 전문 + 디자인 메모)
├── assets/
│   ├── ybot/
│   │   ├── scene.bam          # Y Bot 메쉬 + 14 개 anim (Reload 포함), 게임이 직접 로드
│   │   ├── scene.blend        # Blender 소스 (재빌드용)
│   │   ├── scene.backup.bam   # reload 작업 전 baseline
│   │   └── scene.backup.blend
│   └── weapons/
│       ├── 9mm_pistol.{glb,blend,bam}      # 현재 사용 (Beretta, Sketchfab)
│       ├── animated_pistol.{blend,bam}     # 미사용 (Sketchfab view model — 참고용 보존)
│       └── mark_23.{glb,blend,bam}         # 미사용 (이전 candidate)
├── backups/                   # 작업 스냅샷
│   ├── 20260530-011714-reload-ok/          # Reload 완성 직후
│   └── 20260530-035325-pre-skin/           # Skin 교체 직전
└── scripts/
    ├── blender_merge_ybot.py               # FBX 머지 → scene.blend
    ├── blender_add_anims.py                # 기존 .blend 에 anim 추가
    ├── blender_strip_root.py               # 액션에서 Hips XYZ location 제거
    ├── blender_scaffold_reload.py          # Reload anim 빌드 (FK + IK + roll)
    ├── blender_glb_to_blend.py             # .glb → .blend 변환 (panda3d-gltf 우회용)
    └── peek_glb.py                         # .glb JSON 헤더 요약
```

## 구현 메모

- **카메라**: `mixamorig:Head` 본의 월드 좌표에 매 프레임 attach (0.18 m 전방 + 0.10 m 좌측 오프셋 → 권총 우측 배치, FPS 표준). 시선 yaw 는 마우스 입력 — head 본 자체 회전은 무시. 1인칭은 상하 고정, F2 free-cam 만 pitch 허용.
- **골격 3 파트**: `makeSubpart` 로 lower (Hips + 다리) / upper (Spine + 자손, 손 제외) / hands (양손) 분리. 각 파트에 다른 anim 가능 → 달리며 reload 같은 조합.
- **애니메이션 블렌딩**: `Actor.enableBlend()` + 매 프레임 지수 평활로 weight 수렴. 액션 전환 시 움찔거림 제거.
- **Root motion 제거**: locomotion + Reload 액션의 `mixamorig:Hips` location fcurve 를 Blender 단계에서 통째로 잘라냄. 캐릭터는 제자리에서 뛰고, 실제 이동은 코드가 `player_pos` 로 처리.
- **Hips XY anchor**: 액션 간 rest pose 차이 (Idle Y=-0.94, Shoot Y=-0.89 식) 도 anchor 코드로 보정 → 액션 전환 시 머리가 카메라 안으로 밀려들어와 뒤통수 보이는 버그 차단.
- **사격 반동**: ybot 전체를 카메라 -forward 방향으로 `recoil_back=3cm` 밀고, 카메라엔 같은 양 보정 → 시점 절대 위치 고정. 권총 모델의 `Slide` named node 는 추가로 +X 방향 후퇴.
- **Reload (5 단계)**: Blender 스캐폴드가 Idle grip 포즈에서 FK 4 페이즈 (총 기울임 / 탄창 빼기 / 넣기 / 원위치) + IK 슬라이드 3 키프레임 (잡음 / 당김 / 그립 복귀) + LeftForeArm 길이축 roll 90° (손등 위 향하게) 합성. 런타임은 upper + hands 두 파트만 단발 재생 → lower 는 locomotion 유지.
- **걸으면서 Reload**: lower 가 RunForward/Backward 면 Hips 의 pitch (앞으로 숙임) 가 Spine 으로 전파되어 권총·팔이 화면 아래로 빠짐. 해법: W/S 가 눌렸을 때만 lower target 을 Idle 로 강제 + ybot 에 사인파 Z bob 추가 + 카메라에서 같은 bob 제거 → 자기 몸·팔·총만 까딱이고 화면은 정적.

## 다음 단계

- [x] 손에 무기 메쉬 attach (9mm Beretta)
- [x] ESC pause menu
- [x] Kneel transition state machine
- [x] Reload anim (FK + IK 5단계)
- [ ] 좀비 적 spawn + 단순 AI
- [ ] 층 전환 시스템 (고층 → 저층)
- [ ] 정식 사격 anim (Mixamo "Firing Rifle" 의 Pistol 옵션 등)
- [ ] 머즐 플래시 + 사격음
- [ ] 맵 디자인 (현재는 빈 평면 + 색깔 막대)
- [ ] 슬라이드 marker 하네스 (I/J/K/L/U/O/P) 튜닝 끝나면 통째 제거
