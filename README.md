# zombie_game

Mirror's Edge 스타일 1인칭 좀비 슈터 프로토타입 (Panda3D).
풀바디 Mixamo Y Bot 캐릭터를 그대로 두고 카메라를 머리 본에 attach해서 — 아래 보면 자기 몸/다리, 옆 보면 어깨가 보이는 시점.

> 이전 ursina 기반 FPS 프로토타입은 `zombie_game_ursina.py` 로 보존 (참고용).
> 메인 코드는 `zombie_game.py` (Panda3D 직접 사용).

## 조작

| 입력 | 동작 |
| --- | --- |
| W / S | 전진 / 후진 (Run) |
| A / D | 좌 / 우 스트레이프 |
| 마우스 | 시선 (yaw / pitch) |
| Space | 점프 |
| Ctrl | 무릎 자세 토글 (Kneel) |
| 좌클릭 | Shoot (현재는 카메라 반동만, 별도 사격 애니 없음) |
| F | Punch |
| F2 | 3인칭 디버그 카메라 토글 |
| ESC | 종료 |

## 실행

```powershell
pip install -r requirements.txt
python zombie_game.py
```

`assets/ybot/scene.bam` 이 이미 레포에 포함되어 있어서 위 두 줄이면 끝.

## 의존성

- **Python 3.11+** (테스트 환경: 3.14.3)
- **panda3d** ≥ 1.10.16 — 런타임 엔진
- **panda3d-gltf** ≥ 1.3.0 — bam 의 glTF 자산 import
- **panda3d-blend2bam** ≥ 0.26.0 — 자산 재빌드용 (런타임 불필요)
- **Blender 5.1+** — 자산 재빌드용 (런타임 불필요)

`assets/ybot/scene.bam` 가 정상이면 Blender 와 blend2bam 은 설치 안 해도 됨.

## 자산 — Mixamo

게임에 들어간 9 개 애니메이션은 모두 [Mixamo](https://www.mixamo.com) 에서 무료로 받을 수 있다. Adobe 계정만 있으면 됨.

### 필요한 파일

1. **Y Bot** (캐릭터)
   - Mixamo 첫 화면 → CHARACTERS → "Y Bot" 검색 → **DOWNLOAD** → FBX Binary, **Without Animation**, T-Pose
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
   | Punching | `Punching.fbx` | Punch |

   > 참고: 본 프로젝트는 Mixamo 의 *Pistol_Handgun Locomotion Pack* 파일명을 그대로 사용했다. 같은 모션을 다른 이름으로 받았다면 빌드 명령어의 경로만 맞춰주면 됨.

### 자산 재빌드

다운받은 9 개 FBX 를 한 폴더에 모은 뒤 (예: `C:\fbx\`):

```powershell
$blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
$fbx     = "C:\fbx"

# (1) Y Bot + 8 개 anim FBX 를 단일 scene.blend 로 머지
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
  "Punch=$fbx\Punching.fbx"

# (2) locomotion 액션들에서 Hips 본 location 키프레임 제거 (사이클 끝 깜빡임 방지)
& $blender --background --python scripts/blender_strip_root.py -- `
  "assets/ybot/scene.blend" RunForward RunBackward StrafeL StrafeR Jump

# (3) .blend → .bam 변환
blend2bam --blender-dir "C:\Program Files\Blender Foundation\Blender 5.1" `
  "assets/ybot/scene.blend" "assets/ybot/scene.bam"
```

## 파일 구조

```
.
├── zombie_game.py             # 메인 게임 (Panda3D)
├── zombie_game_ursina.py      # 이전 ursina 프로토타입 (legacy)
├── requirements.txt
├── README.md
├── assets/
│   └── ybot/
│       ├── scene.bam          # 9 개 anim + 메쉬, 게임이 직접 로드
│       └── scene.blend        # Blender 소스 (재빌드용)
└── scripts/
    ├── blender_merge_ybot.py  # FBX 머지 → scene.blend
    └── blender_strip_root.py  # 액션에서 Hips XYZ location 제거
```

## 구현 메모

- **카메라**: `mixamorig:Head` 본의 월드 좌표에 매 프레임 attach (0.22 m 전방 오프셋). 시선 yaw/pitch 는 마우스 입력 — head 본 자체 회전은 무시.
- **애니메이션 블렌딩**: `Actor.enableBlend()` + 매 프레임 지수 평활로 weight 수렴. 액션 전환 시 움찔거림 제거.
- **Root motion 제거**: locomotion 애니들의 `mixamorig:Hips` location fcurve 를 Blender 단계에서 통째로 잘라냄. 캐릭터는 제자리에서 뛰고, 실제 이동은 코드가 `player_pos` 로 처리.
- **Hips XY anchor**: 액션 간 rest pose 차이 (Idle Y=-0.94, Shoot Y=-0.89 식) 도 anchor 코드로 보정 → 액션 전환 시 머리가 카메라 안으로 밀려들어와 뒤통수 보이는 버그 차단.
- **사격 반동**: Shoot 애니 자체에 팔 움직임이 없어서 카메라 pitch 킥 + 전방 오프셋 감소로 시뮬레이션. 지수 감쇠로 자연 복귀.

## 다음 단계

- [ ] 손에 무기 메쉬 attach (mark_23 등)
- [ ] 좀비 적 spawn + 단순 AI
- [ ] 층 전환 시스템 (고층 → 저층)
- [ ] 정식 권총 발사 애니 (Mixamo "Firing Rifle" 의 Pistol 옵션 등) — 현재의 카메라 반동만 의존하는 사격을 대체
