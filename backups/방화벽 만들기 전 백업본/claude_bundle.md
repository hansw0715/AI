# zombie_game — Claude Project Bundle

학교 그룹 프로젝트 (`hansw0715/AI` GitHub, branch `2693044한승원`).
Mirror's Edge / Valorant 스타일 1인칭 좀비 슈터 + **반전 스토리** — "플레이어 = 바이러스, 적 = 정상 로봇".

> **현재 스냅샷**
> - 레벨: `level.py` 의 **중앙 복도(spine) + 좌/우 방 2쌍(W1·E1, W2·E2) + FINAL** (사다리/H).
>   케이지 시작 + 복도 중앙·FINAL 기둥 엄폐 + 벽 충돌. `build_level` 이 `(collider, level_data)`
>   반환 — `level_data` 는 `start_spawns` + `rooms`(방화벽 위치 + 그 방 spawn).
> - 좀비: 총 14마리 — 초기 복도 정찰병 2 + 방화벽 부수면 방별 스폰 (W1:2 / E1:2 / W2:3 /
>   E2:3 / FINAL:2). HP 100, head/body/other 데미지, Death anim, F 로 Y Bot 변환.
>   **벽 차폐 시야** + **Distance LOD 28m**.
> - 성능: GPU 스키닝(PRC `hardware-animated-vertices` + `matrix-palette`).
> - 플레이어: Y Bot, Valorant 스타일 body 숨김, ADS, ±89° pitch, 8발 ammo, muzzle flash,
>   tracer, 마우스 감도 슬라이더, F2 free-cam.
> - 빌드 파이프라인: blender_split_arms 까지 통합.
>
> **TODO**: `Firewall` 런타임 (도어 갭 막는 파괴형 벽 + 부수면 `level_data['rooms'][i]['spawns']`
> 의 좀비 실제 인스턴스화) — 현재는 `start_spawns` 의 복도 정찰병 2마리만 즉시 스폰. 그 외:
> 케이지 F 탈출, 콘솔 복선 로그, 변환 색 연출, HUD 문구 변질, 반전 리빌, 엔딩 분기.

---

## 1. 한 줄 컨셉 & 핵심 반전

AI 로봇 연구실을 무대로, 플레이어는 **로봇을 조종하는 AI 소프트웨어**가 되어 "악성 바이러스에
감염된 로봇들"을 제압하며 시설을 정화해 나간다 — **고 믿지만**, 사실은 플레이어 자신이
바이러스이고, 멀쩡한 로봇들에게 감염을 퍼뜨리는 과정이다. "전염이 퍼지는 과정"을 게임
플레이로 형상화한 작품.

### 1.1 디자인 코어 (스포일러 ⚠)

| | 플레이어가 믿는 것 (표면) | 실제 진실 |
| --- | --- | --- |
| 나 | 시설을 구하는 정상 AI | **악성 바이러스 본체** |
| 적 | 감염된 위험한 로봇 | **아직 멀쩡한 정상 로봇** |
| F키 "변환" | 감염체를 정상으로 치료 | **정상 로봇을 감염시킴** |
| 시설 전진 | 오염 구역을 정화하며 깊숙이 | **감염을 시설 전체로 확산** |

반전의 힘은 **플레이어가 자기 손으로 반전을 실행하고 있었다**는 데 있다 (컷신 통보가 아님).
모든 디자인 결정은 "표면 해석"과 "진짜 의미" 두 겹이 동시에 성립하도록 잡는다.

### 1.2 플레이어 역할 & 코어 루프

1. 적(=정상 로봇)을 총으로 쏴서 **무력화**(못 움직이게)한다.
2. 무력화된 적 근처에서 **F**를 눌러 "변환"한다 — 표면상 치료, 실제론 감염.
3. 구역의 적을 모두 처리하면 다음 구역으로 가는 **방화벽**이 해제된다 (예정).
4. 구역을 차례로 통과하며 시설 안쪽 = 격리 구역까지 전진한다.

전진 = 전염 확산. 변환된 개체가 늘어나는 것 = 전염 곡선의 시각화.

### 1.3 메커니즘 ↔ 스토리 매핑

- **케이지 시작:** 게임은 플레이어가 케이지(격리체 보관함)에 갇힌 상태에서 시작.
  F로 문을 열고 탈출 → 게임 시작. (표면: 갇혔던 정상 AI 가 풀려남 / 진실: 격리돼 있던
  바이러스가 탈출.)
- **사격 = 무력화:** 적을 죽이는 게 아니라 멈춤. "치료 전 제압"이라는 표면 명분과,
  "감염시키기 전 무력화"라는 진실이 겹친다.
- **F = 변환/감염:** 무력화된 적을 아군/감염체로 전환. 현재는 X Bot → Y Bot dual fade
  (같은 색·실루엣).
- **방화벽 = 구역 경계:** 시설이 감염 확산을 막으려 내린 차단막. 플레이어 입장에선
  "정화를 막는 오염 잠금"으로 읽힌다.

### 1.4 반전 연출 / 복선 (예정)

리빌은 텍스트 통보가 아니라 "돌아보니 단서가 다 있었네" 의 누적으로 터뜨린다.

- 변환된 로봇이 "멀쩡해지는" 게 아니라 미묘하게 **플레이어와 같은 색/실루엣**으로 바뀐다
  (= 복제·전염). 플레이어는 "동료가 됐다"로 해석.
- HUD/시스템 메시지 단어가 후반으로 갈수록 변질: 초반 `PURIFYING...` → 후반 `ASSIMILATING...`
  같은 식.
- 적이 플레이어를 보면 **방어적으로 도망**친다. 플레이어는 "감염돼서 미쳐 날뛴다"로 믿지만,
  사실은 정상이라 위협(바이러스)을 피하는 것.
- 콘솔/연구 로그: 처음엔 "바이러스 격리 성공" → 점차 "격리체가 스스로를 치료자로 인식함"
  류로 진행.

**리빌 시점 (제안, 미확정):** R4 격리 구역 진입 시. 여기 도달하면 시설 중앙 시스템이
플레이어의 정체를 직접 드러내거나, 마지막 로그가 진실을 확정한다.

### 1.5 엔딩 (미확정, 후보)

- **확산 엔딩(나쁨):** 계속 감염을 진행 → 시설 완전 장악.
- **자기희생 엔딩:** 멈추고 스스로를 격리/삭제 → 확산 차단.

### 1.6 톤 & 아트 방향

- 무대: 깨끗한 AI 연구실. 밝은 회색 패널 벽(`level.py` `WALL_COLOR`), 서버실은 좁고 어둡게,
  실험실은 넓게 — 구역마다 공간 성격으로 긴장 리듬을 만든다.
- 시각 모티프: "정상 = 한 색, 감염 = 플레이어 색"의 색 대비. 변환 순간 색이 번지는 연출이
  핵심 시각 장치 (예정).
- 표면 톤은 영웅적 정화 작전, 실제 톤은 조용한 호러. 후반으로 갈수록 단어/색/적 행동이
  표면에서 진실 쪽으로 미끄러진다.

### 1.7 용어 / 네이밍 (코드 일관성용)

코드 식별자는 기존 것을 유지하되, 의미는 아래로 이해할 것:

- 코드의 `Zombie` / "좀비" = 스토리상 **정상 로봇**(플레이어가 감염시킬 대상).
- "변환/convert" = 표면 명칭. 내부 주석엔 "감염(infect)" 의미를 병기해도 됨.
- 플레이어 노출 텍스트(HUD, 콘솔)는 **표면 해석**을 따르고, 후반 변질만 예외.

---

## 2. 프로젝트 개요 (기술)

- **장르:** 1인칭 좀비 슈터 + 반전 스토리
- **엔진:** Panda3D 1.10.16
- **플레이어:** Mixamo Y Bot — head 본 카메라 attach, mesh split (`Alpha_Surface` /
  `Alpha_Surface_Arms`), 1인칭에선 body 숨김 / **팔만 visible**
- **무기:** 9mm Beretta (Sketchfab), RightHand 본 attach, pitch 추적
- **적:** Mixamo X Bot + Not So Scary Zombie Pack — 시야 + **벽 차폐** 기반 추격, 랜덤 4공격,
  HP/Death/Transform 풀 구현
- **레벨:** `level.py` 의 **중앙 복도 + 좌/우 방 2쌍 + FINAL** (사다리/H 구조).
  `build_level` → `(LevelCollider, level_data)` 반환. `level_data` 는 `start_spawns` (게임 시작
  시 즉시 스폰할 복도 정찰병) + `rooms` (방화벽 위치 + 그 방 좀비 스폰 좌표). 벽 = 축정렬 박스
  footprint + 2-sided card. `LevelCollider` 가 충돌 해소(circle vs AABB) + 시야 차폐(segment vs
  AABB) 둘 다 제공. `walls` 가 런타임에 추가/제거 가능 — Firewall 이 도어 갭을 막는 벽을
  끼웠다가 부수면 제거.

## 3. 환경

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

## 4. 디렉토리 구조

```
C:\Users\hansw\workspace\AI\
├── zombie_game.py              # 메인 (Panda3D, ~1525 lines)
├── level.py                    # 레벨 (복도/방/벽/충돌/시야 차폐 + level_data) ~305 lines
├── game_story.md               # 스토리·디자인 문서 (이 번들 §1 의 원본)
├── claude_bundle.md            # ← 이 파일
├── requirements.txt
├── README.md
├── assets/
│   ├── ybot/                   # 플레이어 (Y Bot)
│   │   ├── scene.bam           # mesh + 14 anim, Alpha_Surface 가 body / *_Arms 로 split
│   │   ├── scene.blend
│   │   └── scene.backup.{bam,blend}
│   ├── zombie/                 # 좀비 (X Bot + Not So Scary Pack)
│   │   ├── scene.bam           # X Bot mesh + 7 anim (Idle / Run / Attack1~4 / Death)
│   │   └── scene.blend
│   └── weapons/
│       ├── 9mm_pistol.{glb,blend,bam}      # 현재 사용
│       └── (animated_pistol, mark_23 — 미사용)
├── backups/
│   ├── 20260530-011714-reload-ok/          # Reload 완성 직후
│   ├── 20260530-035325-pre-skin/           # skin 교체 직전 baseline
│   └── 맵 만들기 전 백업본/                # level.py 통합 직전
└── scripts/
    ├── blender_merge_ybot.py               # FBX 머지 → scene.blend
    ├── blender_add_anims.py
    ├── blender_strip_root.py               # Hips XYZ location 제거
    ├── blender_scaffold_reload.py          # Reload anim 빌드 (FK + IK + LFORE roll)
    ├── blender_normalize_bones.py          # mixamorig9: → mixamorig: 정규화
    ├── blender_offset_bone.py              # 본 회전 오프셋 anim 키프레임 bake
    ├── blender_split_arms.py               # Alpha_Surface mesh 를 arm / body 로 split
    ├── blender_glb_to_blend.py
    └── peek_glb.py
```

## 5. 조작 / 입력 매핑

| 입력 | 동작 |
| --- | --- |
| W / S | 전진 / 후진 |
| A / D | 좌 / 우 스트레이프 |
| **마우스** | 좌우 yaw + 상하 pitch (±89°) |
| Space | 점프 |
| Ctrl | 무릎 transition (StandToKneel / KneelToStand) |
| **좌클릭** | Shoot — 0.18s 쿨다운 (~5.5발/초), ammo -1, hit zone 판정 + 데미지 popup |
| **우클릭 (hold)** | ADS — FOV 100°→55° + ybot offset |
| **R** | Reload — 완료 시 ammo = 8 |
| **F** | 가까운 DEAD 좀비 X Bot → Y Bot dual fade 변환 (interact_range 2.5m) |
| F2 | 3인칭 free-cam 토글 (자동으로 body mesh show) |
| ESC | Pause 메뉴 (Resume / Mouse Sensitivity slider 0.02~0.30 / Quit) |
| I/J/K/L/U/O/P | 슬라이드 IK marker 튜닝 하네스 (RightHand-local) |

## 6. 자산

### 6.1 플레이어 (Y Bot) — 14 anim

`Idle, RunForward, RunBackward, StrafeL, StrafeR, Jump, KneelIdle, StandToKneel,
KneelToStand, WalkForward, WalkBackward, Shoot, Punch, Reload` (+ Mixamo container 무시).

### 6.2 좀비 (X Bot + Not So Scary Zombie Pack) — 7 anim

`Idle, Run, Attack1=zombie attack.fbx, Attack2=zombie headbutt.fbx,
Attack3=zombie punching.fbx, Attack4=zombie kicking.fbx, Death`.

### 6.3 무기

`9mm_pistol.bam` — RightHand attach, Slide named node 후퇴, scale 0.1195,
local pos (0, 0.090, 0.040), HPR (22.5, -78.2, 108.9).

## 7. 기술 디자인 (현재 코드 기준)

### 7.1 골격 3파트 + 블렌드

`lower (Hips+다리) / upper (Spine+자손-손) / hands (양손)`. `enableBlend()` + 각 anim 별
`setControlEffect` 로 weight 보간. `_update_blend` 가 매 프레임 `_current_w → _target_w`
지수 평활 (`blend_speed=14.0`).

Reload 는 `scripts/blender_scaffold_reload.py` 가 FK 4단계 + IK 3단계 + LeftForeArm Y-roll
90° 로 합성. SLIDE_RIGHT=8, FWD=20, UP=15 (cm armature).

### 7.2 권총 attach + Shoot + 반동

- `weapon_anchor` (render 자식) 가 매 프레임 `right_hand_joint` 의 world pos+hpr 따라감.
- Shoot: 0.18s 쿨다운, ammo -1, hands subpart 단발 anim, ybot 뒤로 3cm recoil + 카메라
  보정으로 시점 고정, slide named node 후퇴(`slide_recoil_kick=0.4`).
- 8발 탄창 (`ammo_max=8`). R 재장전 완료 시 충전. ammo==0 이면 좌클릭 무반응
  (HUD `EMPTY (R)`).

### 7.3 ADS

우클릭 hold → `aim_t` 0→1 (~110ms ramp). FOV 100°→55° + ybot 을 player-frame
`Vec3(-0.13, 0.05, -0.02)` 만큼 이동 (좌 13 + 앞 5 + 아래 2cm). 카메라는 같은 양 -로
보정 → 손·팔·총 다 같이 이동, 화면 정적.

### 7.4 1인칭 시야 — 마우스 ±89° pitch

```python
self.player_yaw -= dx * self.mouse_sens
self.player_pitch -= dy * self.mouse_sens
self.player_pitch = max(-89.0, min(89.0, self.player_pitch))
```

카메라: `setHpr(player_yaw, player_pitch, 0)`. tracer / 권총 anchor 모두 같은 yaw/pitch.

### 7.5 Valorant 스타일 body 숨김

`Alpha_Surface` (17K verts) 가 단일 mesh 라 그대로는 분리 불가. `blender_split_arms.py` 가
dominant-weight 본이 LeftShoulder/LeftArm/LeftForeArm/LeftHand/Right- 계열인 vertex 만 떼서
`Alpha_Surface_Arms` 로. Alpha_Joints 도 동일. 런타임 `_body_meshes` = `[Alpha_Surface,
Alpha_Joints]` 만 hide/show. F2 진입 시 body 다시 show.

### 7.6 Muzzle flash + Tracer

- Muzzle flash: weapon_anchor parent, 5cm billboard quad, additive blend, 60ms fade.
  hand-local (8cm right + 32cm forward + 8cm up).
- Tracer: render parent, thickness 1 LineSegs, muzzle 위치에서 player_yaw + player_pitch
  방향 30m 직선, 50ms 후 hide.

### 7.7 좀비 AI — 상태머신 + 시야 + 차폐 + LOD

| 상태 | 동작 |
| --- | --- |
| IDLE | Idle loop. `can_see_player()` true 면 CHASE |
| CHASE | Run loop + 추격 이동 (2.5 m/s), 매 프레임 yaw 갱신. 시야 잃으면 IDLE, 거리 < 1.8m 면 ATTACK |
| ATTACK | Attack1~4 중 random 단발. anim 끝나면 거리/시야 재판정 |
| DYING | HP ≤ 0 → Death anim 단발. 끝나면 DEAD |
| DEAD | 마지막 프레임 정지. F interact 가능 (Y Bot 으로 dual fade) |

**시야** (`can_see_player`):
- 평면 거리 < `sight_range=25` AND
- 좌우 시야각 < ±`sight_fov_half=70°` (전체 140°)
- 거리 < 0.5m 면 시야각 무시
- ⭐ **벽 차폐**: `level_collider.segment_blocked(zombie.pos, player.pos)` true 면 False —
  벽 너머 / 기둥 뒤에 숨으면 못 봄. 도어 갭은 wall 박스가 없는 영역이라 자동 통과.

**Distance LOD** (`LOD_DISTANCE = 28.0`):
- 플레이어로부터 28m 너머의 좀비는 `actor.hide()` + AI/anim/render 전부 skip.
- DYING (Death anim 진행 중) / Transform 페이드 중에는 LOD 보류 — anim 끊김 방지.
- CHASE 상태로 LOD'd 되면 IDLE 로 리셋해서 다음 가까워질 때 깔끔하게 시작.

**HP / 데미지 zone** (vertical capsule 히트박스):
- `HIT_TORSO_R=0.20` 안쪽 + `HIT_HEAD_Z=1.45` 이상 → head (20 dmg)
- 안쪽 + Z 낮음 → body (10 dmg)
- `HIT_LIMB_R=0.55` 까지 바깥 → other (5 dmg, 팔/다리)
- `_resolve_shot_hit`: 카메라 ray vs 각 좀비 vertical capsule. 가장 가까운 hit 에 데미지
  + `_spawn_damage_number` (3D billboard text 위로 떠오르며 fade).

**HP bar**:
- 좀비 머리 위 2-card (배경 빨강 + 채우기 초록). 평소 hidden, 데미지 시 풀 알파
  2.5s + 1.5s fade out. `setBillboardPointEye` + `setBin('fixed')` + depth off.

**Transform (F)**:
- 가장 가까운 DEAD + 미변환 좀비 (`interact_range=2.5m`) → `start_transform`.
- X Bot alpha 1→0 / Y Bot alpha 0→1 dual fade 1.2s. Y Bot 은 같은 pos/yaw + Death anim
  마지막 프레임 pose 라 자세 일치.

**충돌**:
- 플레이어 이동 직후 `LevelCollider.resolve(x, y, PLAYER_RADIUS=0.40)`.
- 좀비 CHASE 이동 직후 동일하게 `ZOMBIE_RADIUS=0.45`.

### 7.8 걸으면서 Reload + walk bob

`_update_locomotion`: reload 중 W/S 일 때 lower target 을 `Idle` 로 강제 (RunForward 의
Hips pitch 가 권총·팔 화면 밖으로 빼는 문제 회피). 대신 `_walk_bob_t` ramp + ybot Z 사인파
+ 카메라 보정으로 자기 몸·팔·총만 까딱이는 효과.

### 7.9 Mouse Sensitivity 슬라이더

ESC pause 메뉴 — `DirectSlider` (range 0.02~0.30, value=0.10) + 현재값 표시. 매 변경마다
`_on_sens_change` 가 `self.mouse_sens` 즉시 갱신.

### 7.10 GPU 스키닝 (PRC)

모듈 import 시점 (`ShowBase` 인스턴스 만들기 전) 에 `loadPrcFileData` 로 두 플래그:

```python
loadPrcFileData('', 'hardware-animated-vertices #t')
loadPrcFileData('', 'matrix-palette #t')
```

본 매트릭스만 CPU 계산하고 vertex skinning 은 GPU shader 가 처리. 좀비 다수 (~10K verts/마리
× 14마리 = 140K vertex 변환) 가 CPU 메인 스레드 안 잡아먹음.

## 8. 레벨 / 스토리 디자인 (사다리/H 구조)

`level.py` — 중앙 복도(spine) 가 남→북으로 뻗고 좌/우로 방 2쌍이 가지처럼 붙는다. 복도 끝
북쪽에 마지막 방(출구 전 / 리빌). 모든 단위 m, Panda3D Z-up Y-forward.

```
                ┌────────────────┐
            62  │      FINAL     │   넓은 방, 기둥 2개, 리빌
                │   ← 기둥 ×2 →   │
            47  └────┬──────┬────┘   ← 복도 N 면 통째 개방 → FINAL 진입
                     │ spine│
            39  ┌────┤      ├────┐
                │ W2 │ 복도 │ E2 │   방 2쌍, 좀비 3+3
            27  └────┤ x ∈  ├────┘   ← 도어 y=33 (W,E 양쪽)
                     │[-2.5,│
                     │ 2.5] │
                     │   ●  │       y=23.5 복도 중앙 기둥 (사선 차단)
                     │      │
            20  ┌────┤      ├────┐
                │ W1 │      │ E1 │   방 2쌍, 좀비 2+2
             8  └────┤      ├────┘   ← 도어 y=14 (W,E)
                     │  ●●  │       y=11 복도 정찰병 (start spawn ×2)
                     │      │
                 ┌───┴──────┴───┐
                 │ 케이지 (S/W/E) │   y=0 플레이어 시작 (N 열림)
            -3   └──────────────┘
                                          x →
```

| 구역 | 코드명 | 좌표 (x × y) | 좀비 | 도어 / 방화벽 |
| --- | --- | --- | --- | --- |
| 중앙 복도 | spine | [-2.5, 2.5] × [-3, 47] | 2 (start patrol, 즉시) | — (N면 통째 개방 → FINAL) |
| 좌1 | W1 | [-15, -2.5] × [8, 20] | 2 (지연) | 복도 W면 y=14, 폭 2.4 |
| 우1 | E1 | [2.5, 15] × [8, 20] | 2 (지연) | 복도 E면 y=14, 폭 2.4 |
| 좌2 | W2 | [-15, -2.5] × [27, 39] | 3 (지연) | 복도 W면 y=33, 폭 2.4 |
| 우2 | E2 | [2.5, 15] × [27, 39] | 3 (지연) | 복도 E면 y=33, 폭 2.4 |
| FINAL | FINAL | [-8, 8] × [47, 62] | 2 (지연) | 복도→FINAL S면 x=0, 폭 2.4 |

- 방화벽: 도어 갭은 처음엔 그냥 '뚫린 통로'. 런타임 `Firewall` 이 그 갭을 막는 파괴형 벽을
  `LevelCollider.walls` 에 push 했다가, 부수면 pop 해서 통로가 열리고 그 방 좀비가 그제서야
  스폰. 한꺼번에 14마리가 안 돌아서 과부하 없음.
- 케이지: x=[-1, 1] × y=[-1, 1], S/W/E 3면, **N 열림** (F 게이트는 §10 TODO).
- 엄폐물: 복도 중앙 기둥 `pillar(0, 23.5)` — 시작점에서 FINAL 까지 일직선 사거리 끊음.
  FINAL 안 기둥 `pillar(-3, 54)`, `pillar(3, 54)`.
- 벽: `WALL_HEIGHT=3.0m`, `WALL_THICKNESS=0.30m`, 색 `(0.72, 0.74, 0.78)`.
- 좀비 spawn (모두 yaw=180 남향):
  - start (복도 정찰병, 즉시): `(-1.5, 11)`, `(1.5, 11)`
  - W1: `(-10, 12)`, `(-7, 17)`
  - E1: `(10, 12)`, `(7, 17)`
  - W2: `(-11, 31)`, `(-7, 36)`, `(-10, 35)`
  - E2: `(11, 31)`, `(7, 36)`, `(10, 35)`
  - FINAL: `(-5, 58)`, `(5, 58)`
- Ground: -32~32 X × -8~76 Y (전체 커버).

### 8.1 `level_data` 구조 (build_level 반환)

```python
collider, level_data = build_level(render)
# level_data = {
#     'start_spawns': [(-1.5, 11), (1.5, 11)],
#     'rooms': [
#         {'name': 'W1',
#          'firewall': ('v', -2.5, 12.8, 15.2),    # orient, fixed, lo, hi
#          'spawns':   [(-10, 12), (-7, 17)]},
#         {'name': 'E1',    'firewall': ('v',  2.5, 12.8, 15.2), 'spawns': [...]},
#         {'name': 'W2',    'firewall': ('v', -2.5, 31.8, 34.2), 'spawns': [...]},
#         {'name': 'E2',    'firewall': ('v',  2.5, 31.8, 34.2), 'spawns': [...]},
#         {'name': 'FINAL', 'firewall': ('h', 47.0, -1.2,  1.2), 'spawns': [...]},
#     ],
# }
```

`firewall` 튜플:
- `orient='v'` → x=fixed 인 세로 배리어, y ∈ [lo, hi]
- `orient='h'` → y=fixed 인 가로 배리어, x ∈ [lo, hi]
- 좌표는 각 door 갭과 정확히 일치 (center ± width/2)

### 8.2 방화벽 해제 — 두 방식 (예정, story 의도)

- **콘솔(힌트):** 그 방 적을 다 무력화하면 콘솔이 활성화 → F 상호작용으로 해제. 콘솔 화면에
  복선 로그를 띄운다.
- **부수기:** 방화벽 자체에 HP 부여, 일정 발수로 파괴. 적이 추격하는 압박 상황에서 써야 텐션이
  산다.

방별 어느 방식을 쓸지는 §10 TODO.

## 9. 자산 재빌드

### 9.1 플레이어 (Y Bot) — 14 anim + Reload 스캐폴드 + arms split

```powershell
$blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
$fbx     = "C:\fbx"
Set-Location "C:\Users\hansw\workspace\AI"

# (1) Y Bot + anim → scene.blend
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

# (1a) 본 prefix 정규화
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

# (5) arms/body split (Valorant 스타일)
& $blender --background --python scripts/blender_split_arms.py -- `
  "assets/ybot/scene.blend"

# (6) .blend → .bam
python -m blend2bam --blender-dir "C:\Program Files\Blender Foundation\Blender 5.1" `
  --textures copy "assets/ybot/scene.blend" "assets/ybot/scene.bam"
```

### 9.2 좀비 (X Bot + Zombie Pack)

```powershell
$zp = "C:\Users\hansw\Downloads\Not So Scary Zombie Pack"
& $blender --background --python scripts/blender_merge_ybot.py -- `
  "$zp\X Bot.fbx" "assets/zombie/scene.blend" `
  "Idle=$zp\zombie idle.fbx" "Run=$zp\zombie running.fbx" `
  "Attack1=$zp\zombie attack.fbx" "Attack2=$zp\zombie headbutt.fbx" `
  "Attack3=$zp\zombie punching.fbx" "Attack4=$zp\zombie kicking.fbx" `
  "Death=$zp\zombie death.fbx"

& $blender --background --python scripts/blender_normalize_bones.py -- `
  "assets/zombie/scene.blend"

& $blender --background --python scripts/blender_strip_root.py -- `
  "assets/zombie/scene.blend" Idle Run

python -m blend2bam --blender-dir "C:\Program Files\Blender Foundation\Blender 5.1" `
  --textures copy "assets/zombie/scene.blend" "assets/zombie/scene.bam"
```

## 10. 알려진 이슈 / TODO

### 10.1 인터랙션 (story-bound, 아직 미구현)

- **케이지 F 탈출** — 현재 케이지 N 면이 열려 있어서 그냥 걸어나옴. F 추가 시 N 벽으로
  막고 F 인터랙션으로 게이트 열기. (story §1.3)
- **`Firewall` 런타임 클래스** — `level.py` 가 `level_data['rooms']` 로 각 방의 firewall
  위치 + 그 방 좀비 spawn 좌표를 다 넘겨주는 상태. zombie_game.Firewall 이 도어 갭에
  `Wall` 을 push → 시각용 card (다른 색/이펙트) → 일정 발수로 부수면 `LevelCollider.walls`
  에서 pop + 그 방 좀비 `Zombie` 인스턴스 N마리 spawn. 콘솔/부수기 두 방식은 방 단위로
  나눠서 (§8.2).
- **콘솔 + 복선 로그** — 콘솔(힌트) 방식 방의 콘솔 메쉬 + 그 방 적 다 죽이면 활성화 + F 로
  로그 띄우기.
- **변환 색 연출** — Y Bot replacement 의 색이 플레이어와 동일하게 번지는 시각 장치.
- **HUD 문구 변질** — 초반 `PURIFYING` → 후반 `ASSIMILATING` 식.
- **반전 리빌** — FINAL 방 진입 시 시스템 로그/대사.
- **엔딩 분기** — 확산 vs 자기희생.

### 10.2 기술 부채

- 위·아래 극단 시야 (±60° 이상) 에서 가시 팔 mesh 와 권총 align 미세 차이.
  weapon_anchor pitch 만 따라가고 arm chain 은 anim-driven.
- `shoot_cooldown` / `mouse_sens` 영구 저장 미구현. 매 실행마다 기본값.
- marker 하네스 (I/J/K/L/U/O/P) — 슬라이드 위치 튜닝 끝나면 제거.
- muzzle flash / tracer 가 모든 깊이 위로 그려짐 (`setDepthTest(False)` + `setBin('fixed')`).
  의도된 동작이지만 벽 너머에서도 보임.

## 11. 실행

```powershell
Set-Location C:\Users\hansw\workspace\AI
python zombie_game.py
```

clone 직후도 `pip install -r requirements.txt` 후 위 한 줄로 바로 실행됨 (scene.bam 들이
레포에 포함).

---

## 12. 코드 전문

### 12.1 `level.py`

```python
"""
level.py — zombie_game 연구실 레벨 (방 / 벽 / 충돌).

설계 요약
  - 방(room) = XY 평면의 축정렬 사각형. room_walls() 가 4면 벽을 만들고
    door 위치는 통로(구멍)로 비운다.
  - 벽(Wall) = 얇은 축정렬 박스. 시각용 2-sided card + 충돌용 footprint AABB.
  - 충돌 = 원(플레이어 반지름) vs 박스. LevelCollider.resolve(x, y, r) 가
    벽을 뚫지 못하게 보정한 (x, y) 를 돌려준다.

레이아웃 (남→북, 사다리/H 모양)
  중앙에 긴 복도(spine)가 세로로 뻗고, 그 좌/우로 방이 가지처럼 붙는다.
  복도를 따라 방 2쌍(좌1·우1 / 좌2·우2)을 지나, 복도 끝에서 넓은 마지막
  방(출구 전 / 리빌)으로 이어진다.

방화벽(firewall) / 스폰
  각 방 입구 door 는 처음엔 그냥 '뚫린 통로'로 둔다 (벽이 없는 구간). 방화벽은
  런타임(zombie_game.Firewall)에서 그 door 갭을 막는 파괴형 배리어로 생성되고,
  부수면 통로가 열리며 그 방 좀비가 그제서야 스폰된다. build_level 은 방화벽의
  '위치 스펙'과 '그 방 좀비 스폰 좌표'만 level_data 로 넘긴다 — 즉시 스폰되는 건
  복도 정찰병(start_spawns)뿐이라 한꺼번에 14마리가 돌지 않아 과부하가 없다.

좌표계: Panda3D 표준 Z-up, Y-forward. 모든 단위 m.
사용법: zombie_game.py 의 __init__ 에서 build_level(self.render) 호출.
"""

from math import atan2, degrees, hypot

from panda3d.core import CardMaker


# ── 튜닝 노브 ────────────────────────────────────────────────────────────
WALL_HEIGHT    = 3.0                       # m — 벽 높이
WALL_THICKNESS = 0.30                      # m — 충돌 박스 두께
WALL_COLOR     = (0.72, 0.74, 0.78, 1.0)   # 연구실 패널 느낌 밝은 회색
PLAYER_RADIUS  = 0.40                       # m — 플레이어 충돌 반지름
ZOMBIE_RADIUS  = 0.45                       # m — 좀비 충돌 반지름 (선택)
DOOR_WIDTH     = 2.4                        # m — 통로 폭 (플레이어 통과 여유)


class Wall:
    """축정렬 벽 한 칸. 중심선 (ax,ay)->(bx,by) + 두께 → footprint 박스."""
    __slots__ = ('x0', 'x1', 'y0', 'y1', 'ax', 'ay', 'bx', 'by')

    def __init__(self, ax, ay, bx, by, thickness=WALL_THICKNESS):
        self.ax, self.ay, self.bx, self.by = ax, ay, bx, by
        half = thickness * 0.5
        self.x0 = min(ax, bx) - half
        self.x1 = max(ax, bx) + half
        self.y0 = min(ay, by) - half
        self.y1 = max(ay, by) + half

    def make_card(self, parent):
        """중심선을 따라 세운 2-sided 사각 card 를 parent 아래에 만든다."""
        length = hypot(self.bx - self.ax, self.by - self.ay)
        cm = CardMaker('wall')
        # CardMaker 기본 card 는 XZ 평면(Y=0)에 섬 → bottom/top 이 Z(높이).
        cm.setFrame(-length / 2.0, length / 2.0, 0.0, WALL_HEIGHT)
        np = parent.attachNewNode(cm.generate())
        np.setTwoSided(True)
        np.setPos((self.ax + self.bx) / 2.0, (self.ay + self.by) / 2.0, 0.0)
        # local +X 를 벽 방향으로 정렬. (수평벽 H=0, 수직벽 H=90)
        np.setH(degrees(atan2(self.by - self.ay, self.bx - self.ax)))
        np.setColor(*WALL_COLOR)
        return np


def _add(walls, orient, fixed, a, b):
    """[a,b] 구간 벽 한 칸 추가. orient 'h'=X 따라(고정 y), 'v'=Y 따라(고정 x)."""
    if b - a < 1e-3:
        return
    if orient == 'h':
        walls.append(Wall(a, fixed, b, fixed))
    else:
        walls.append(Wall(fixed, a, fixed, b))


def room_walls(x0, x1, y0, y1, doors=()):
    """방 사각형의 4면 벽 리스트.

    doors: (side, center, width) 들.
      side: 'N'(+Y, y=y1), 'S'(-Y, y=y0), 'E'(+X, x=x1), 'W'(-X, x=x0)
      center: 그 면 위 구멍의 중심 좌표, width: 구멍 폭.
        (N/S 면은 center 가 x 좌표, E/W 면은 center 가 y 좌표)
      width 를 그 면 전체 길이 이상으로 주면 그 면 벽이 통째로 사라짐 (완전 개방).
    """
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

    emit('h', y1, x0, x1, by_side['N'])   # 북
    emit('h', y0, x0, x1, by_side['S'])   # 남
    emit('v', x1, y0, y1, by_side['E'])   # 동
    emit('v', x0, y0, y1, by_side['W'])   # 서
    return walls


def _side_room(x0, x1, y0, y1, open_side):
    """복도에 가지처럼 붙는 방. open_side(복도 쪽 면)는 벽을 만들지 않는다 —
    복도 벽이 그 면을 막아 주고, 복도 벽에 뚫어 둔 door gap 이 통로가 된다.
    덕분에 경계에 벽이 이중으로 겹치지 않는다.

    open_side: 'N' / 'S' / 'E' / 'W' — 비울 면 (복도를 마주보는 면).
    """
    walls = []
    if open_side != 'N':
        _add(walls, 'h', y1, x0, x1)   # 북
    if open_side != 'S':
        _add(walls, 'h', y0, x0, x1)   # 남
    if open_side != 'E':
        _add(walls, 'v', x1, y0, y1)   # 동
    if open_side != 'W':
        _add(walls, 'v', x0, y0, y1)   # 서
    return walls


def pillar(cx, cy, half=0.5):
    """정사각 기둥 = 4 벽. 엄폐물용."""
    return [
        Wall(cx - half, cy - half, cx + half, cy - half),
        Wall(cx - half, cy + half, cx + half, cy + half),
        Wall(cx - half, cy - half, cx - half, cy + half),
        Wall(cx + half, cy - half, cx + half, cy + half),
    ]


class LevelCollider:
    """원(반지름 r) vs 모든 벽 박스 충돌 해소.

    walls 는 런타임에 추가/제거 가능 — Firewall 이 도어 갭을 막는 벽을 append
    했다가 파괴 시 remove 한다.
    """

    def __init__(self, walls):
        self.walls = walls

    def segment_blocked(self, x0, y0, x1, y1):
        """선분 (x0,y0)→(x1,y1) 이 어느 벽 박스든 가로지르면 True.

        좀비 시야 차폐용 — 벽 너머 플레이어를 인지·추격하지 못하게. 표준 slab 방식
        2D 선분 vs AABB 교차 검사. 도어/케이지 N면처럼 '벽이 없는' 구간은 자연히
        통과 (그 영역에 wall 박스 자체가 없음).
        """
        dx = x1 - x0
        dy = y1 - y0
        for w in self.walls:
            t_near = 0.0
            t_far = 1.0
            # X 슬랩
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
            # Y 슬랩
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
        # 코너에서 두 벽에 동시에 끼는 경우를 위해 2패스.
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
                    # 박스 바깥 — 가장 가까운 점에서 바깥쪽으로 밀어냄
                    d = d2 ** 0.5
                    push = radius - d
                    x += (dx / d) * push
                    y += (dy / d) * push
                else:
                    # 중심이 박스 안 — 최소 침투축으로 탈출
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


def build_level(render):
    """레벨을 render 아래에 생성. (collider, level_data) 반환.

    level_data = {
      'start_spawns': [(x, y), ...],   # 게임 시작 시 즉시 스폰 (복도 정찰병)
      'rooms': [
        {'name': 'W1',
         'firewall': (orient, fixed, lo, hi),   # 도어 갭을 막는 방화벽 위치
         'spawns':   [(x, y), ...]},            # 방화벽 부수면 스폰할 좀비
        ...
      ],
    }
      firewall: orient 'v' → x=fixed 세로 배리어, y∈[lo,hi].
                orient 'h' → y=fixed 가로 배리어, x∈[lo,hi].
                (각 door 갭과 정확히 일치 — center±width/2)

    숫자만 바꾸면 방 크기/위치 조정. F2 free-cam 으로 좌표 보면서 튜닝.
    """
    root = render.attachNewNode('level')
    walls = []
    D = DOOR_WIDTH
    h = D / 2.0                # door 갭 반폭

    # 복도(spine) X 범위 — 좌/우 방이 이 벽(x=CX0 / x=CX1)에 door 로 붙는다.
    CX0, CX1 = -2.5, 2.5
    CORRIDOR_W = CX1 - CX0      # 5.0 — 북면 완전 개방용 (door width 로 사용)
    DOOR_Y1 = 14.0             # 방 1쌍 (좌1·우1) door 중심
    DOOR_Y2 = 33.0             # 방 2쌍 (좌2·우2) door 중심
    FINAL_Y = 47.0             # 마지막 방 남벽 (= 복도 끝)

    # ── 중앙 복도 (남 y=-3 → 북 y=47) ─────────────────────────────────────
    walls += room_walls(
        CX0, CX1, -3, FINAL_Y,
        doors=[
            ('W', DOOR_Y1, D), ('W', DOOR_Y2, D),
            ('E', DOOR_Y1, D), ('E', DOOR_Y2, D),
            ('N', 0, CORRIDOR_W),      # 북면 통째 개방 → 마지막 방으로
        ],
    )
    # 시작 케이지(격리체 보관함): 3면. N 열림 (F 게이트는 나중에, story §1.3).
    walls += [
        Wall(-1.0, -1.0,  1.0, -1.0),   # 케이지 S
        Wall(-1.0, -1.0, -1.0,  1.0),   # 케이지 W
        Wall( 1.0, -1.0,  1.0,  1.0),   # 케이지 E
    ]
    # 긴 복도 중간 엄폐 기둥 (방 두 쌍 사이) — 일자 사선 차단.
    walls += pillar(0, 23.5)

    # ── 방 4개 (벽만; 좀비/방화벽은 level_data 로) ─────────────────────────
    walls += _side_room(-15, CX0, 8, 20, open_side='E')   # 좌1
    walls += _side_room(CX1, 15, 8, 20, open_side='W')    # 우1
    walls += _side_room(-15, CX0, 27, 39, open_side='E')  # 좌2
    walls += _side_room(CX1, 15, 27, 39, open_side='W')   # 우2

    # ── 마지막 방 (출구 전 / 리빌). 남벽 door, 북벽=출구(예정) ───────────────
    walls += room_walls(-8, 8, FINAL_Y, 62, doors=[('S', 0, D)])
    walls += pillar(-3, 54)
    walls += pillar(3, 54)

    for w in walls:
        w.make_card(root)

    level_data = {
        # 복도 정찰병 — 케이지에서 좀 떨어진 안쪽(y=11)에 둬서 바로 안 붙음.
        'start_spawns': [(-1.5, 11), (1.5, 11)],
        'rooms': [
            {'name': 'W1', 'firewall': ('v', CX0, DOOR_Y1 - h, DOOR_Y1 + h),
             'spawns': [(-10, 12), (-7, 17)]},
            {'name': 'E1', 'firewall': ('v', CX1, DOOR_Y1 - h, DOOR_Y1 + h),
             'spawns': [(10, 12), (7, 17)]},
            {'name': 'W2', 'firewall': ('v', CX0, DOOR_Y2 - h, DOOR_Y2 + h),
             'spawns': [(-11, 31), (-7, 36), (-10, 35)]},
            {'name': 'E2', 'firewall': ('v', CX1, DOOR_Y2 - h, DOOR_Y2 + h),
             'spawns': [(11, 31), (7, 36), (10, 35)]},
            {'name': 'FINAL', 'firewall': ('h', FINAL_Y, -h, h),
             'spawns': [(-5, 58), (5, 58)]},
        ],
    }
    return LevelCollider(walls), level_data
```

### 12.2 `zombie_game.py`

```python
"""
zombie_game — Mirror's Edge style 1인칭 좀비 슈터 (Panda3D)
Stage 1: 1인칭 카메라 + Y Bot 풀바디 + 기본 입력.
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
    AmbientLight, CardMaker, ClockObject, ColorBlendAttrib, DirectionalLight, Filename,
    LineSegs, NodePath, Quat, TextNode, Vec3, Vec4, WindowProperties, loadPrcFileData,
)

from level import PLAYER_RADIUS, ZOMBIE_RADIUS, build_level

# ── 성능 PRC: GPU 스키닝 ────────────────────────────────────────────────────
# 좀비 14마리 × Mixamo 본 67개 × CPU 정점 변환 매 프레임 = 화각에 좀비 많을 때 FPS 폭락.
# 두 플래그를 같이 켜면 본 매트릭스만 GPU 에 보내고 vertex skinning 은 GPU shader 가 처리:
#   hardware-animated-vertices : vertex animation 을 GPU 로
#   matrix-palette             : 본 매트릭스 팔레트 (per-vertex 최대 4본) 전송 활성화
# ShowBase 인스턴스 만들기 전에 적용돼야 효과 — 모듈 import 시점 (지금) 에 로딩.
loadPrcFileData('', 'hardware-animated-vertices #t')
loadPrcFileData('', 'matrix-palette #t')


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

ZOMBIE_BAM = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'zombie' / 'scene.bam')
)


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

    # 히트박스 = vertical capsule (zombie.pos 의 X/Y, Z 범위 [Z_MIN, Z_MAX]).
    # 안쪽 (TORSO_R 이하) + Z 높음 → head, 안쪽 + Z 낮음 → body. 바깥 (LIMB_R 까지)
    # → other (팔/다리/발 등). 머리는 위쪽, 몸은 가운데, 나머지는 옆쪽 또는 발쪽.
    HIT_TORSO_R     = 0.20
    HIT_LIMB_R      = 0.55
    HIT_Z_MIN       = 0.0
    HIT_Z_MAX       = 1.85
    HIT_HEAD_Z      = 1.45    # 이 이상이면 머리
    DAMAGE = {'head': 20, 'body': 10, 'other': 5}

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

        self.pos = Vec3(spawn_pos)
        self.yaw = yaw
        self.actor.setPos(self.pos)
        self.actor.setH(self.yaw + 180)

        # 튜닝 노브
        self.move_speed       = 2.5    # m/s — 추격 속도
        self.sight_range      = 25.0   # m  — 최대 시야 거리
        self.sight_fov_half   = 70.0   # deg — 시야각의 절반 (전체 140°)
        self.attack_range     = 1.8    # m  — 이 안이면 공격

        self.attack_anims = [a for a in ('Attack1', 'Attack2', 'Attack3', 'Attack4')
                              if a in self.anim_names]

        self.state = self.IDLE
        self.current_anim = None
        self.attack_t = 0.0

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
            if self.death_t <= 0:
                self.state = self.DEAD
            # 위치는 그대로 (이동 안 함)
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

        # transform 적용
        self.actor.setPos(self.pos)
        self.actor.setH(self.yaw + 180)


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
        # level.py 가 render 아래에 방·벽·기둥을 만들고 collider + 좀비 spawn 좌표 반환.
        self.level_collider, self.level_data = build_level(self.render)

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
        self.move_speed = 6.0
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

        # HUD
        self.hud = OnscreenText(
            text='',
            pos=(-1.7, 0.92), scale=0.045,
            fg=(1, 1, 1, 1), bg=(0, 0, 0, 0.5),
            align=TextNode.ALeft, mayChange=True,
            parent=self.aspect2d,
        )

        # 죽은 좀비 옆에 가까이 있으면 뜨는 interact 힌트 (F 키로 X Bot → Y Bot)
        self.interact_text = OnscreenText(
            text='', pos=(0, -0.7), scale=0.07,
            fg=(1, 1, 0.6, 1), bg=(0, 0, 0, 0.6),
            align=TextNode.ACenter, mayChange=True,
            parent=self.aspect2d,
        )
        self.interact_text.hide()
        self._interact_target = None    # 현재 가까이 있는 dead 좀비
        self.interact_range = 2.5       # m

        # 탄창 / 사격
        self.ammo_max = 8
        self.ammo = self.ammo_max
        # 발사 쿨다운 — 이전엔 Shoot anim 끝까지 (~1초+) 막혀서 너무 느렸음.
        # 0.18s = 약 5.5 발/초. 값 줄이면 더 빨라짐 (자동소총 0.1, 권총 0.2 정도).
        self.shoot_cooldown_t = 0.0
        self.shoot_cooldown_dur = 0.18

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

        # 좀비 spawn + damage popup 텍스트 풀
        self.zombies = []
        self._damage_numbers = []     # [{np, t, dur}, ...] — _update 가 animate
        self._spawn_zombies()

        # 메인 루프
        self.taskMgr.add(self._update, 'game_update')

        # 진단: Idle 한 프레임 돌고 나서 본 이름/좌표 한 번 출력
        self.taskMgr.doMethodLater(0.3, self._dump_joints, 'dump_joints')

    def _spawn_zombies(self):
        if not ZOMBIE_BAM.exists():
            print(f'[zombie] BAM not found: {ZOMBIE_BAM}', flush=True)
            return
        # 게임 시작 시엔 복도 정찰병만 (level_data['start_spawns']). 방별 좀비는
        # 그 방의 방화벽이 부서지면 spawn — Firewall 런타임 구현 시 level_data['rooms']
        # 의 spawns 좌표를 그제서야 인스턴스화. 모두 남쪽(플레이어 진입 방향) 향함.
        for x, y in self.level_data['start_spawns']:
            self.zombies.append(Zombie(self, Vec3(x, y, 0), 180))
        print(f'[zombie] spawned {len(self.zombies)} start zombies '
              f'(rooms pending firewall: {len(self.level_data["rooms"])})',
              flush=True)

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
        # level.py 의 5방 라인업 (y=-2 ~ y=70) 을 여유 있게 덮음.
        cm = CardMaker('ground')
        cm.setFrame(-32, 32, -8, 76)
        gnd = self.render.attachNewNode(cm.generate())
        gnd.setHpr(0, -90, 0)  # XY 평면으로 눕히기
        gnd.setColor(0.55, 0.55, 0.58, 1)

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
        if self.paused or self._interact_target is None:
            return
        self._interact_target.start_transform(self)
        self._interact_target = None
        self.interact_text.hide()

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
        """카메라 ray vs 각 좀비 vertical capsule. 안쪽(torso) 이면 Z 따라 head/body,
        바깥(limb) 이면 other. 가장 가까운 hit 에 damage + damage number popup."""
        cam_pos = self.camera.getPos(self.render)
        yr = radians(self.player_yaw)
        pp = radians(self.player_pitch)
        ray_dir = Vec3(-sin(yr) * cos(pp), cos(yr) * cos(pp), sin(pp))
        ray_dir.normalize()

        rd_2d_dot = ray_dir.x * ray_dir.x + ray_dir.y * ray_dir.y
        if rd_2d_dot < 1e-6:
            return    # 수직 ray (위/아래 정확히) — capsule 측면 안 잡힘, skip

        best_t = float('inf')
        best_z = None
        best_zone = None
        best_hit_pos = None
        for z in self.zombies:
            if z.hp <= 0:
                continue
            # ray 와 vertical line (z.pos.x, z.pos.y, *) 사이 최단 거리의 t
            dx = z.pos.x - cam_pos.x
            dy = z.pos.y - cam_pos.y
            t = (dx * ray_dir.x + dy * ray_dir.y) / rd_2d_dot
            if t < 0 or t >= best_t:
                continue
            closest_x = cam_pos.x + ray_dir.x * t
            closest_y = cam_pos.y + ray_dir.y * t
            dxy = ((closest_x - z.pos.x) ** 2 + (closest_y - z.pos.y) ** 2) ** 0.5
            if dxy > Zombie.HIT_LIMB_R:
                continue
            hit_z = cam_pos.z + ray_dir.z * t
            if hit_z < Zombie.HIT_Z_MIN or hit_z > Zombie.HIT_Z_MAX:
                continue
            # zone 분류
            if dxy <= Zombie.HIT_TORSO_R:
                zone = 'head' if hit_z >= Zombie.HIT_HEAD_Z else 'body'
            else:
                zone = 'other'
            best_t = t
            best_z = z
            best_zone = zone
            best_hit_pos = Vec3(closest_x, closest_y, hit_z)

        if best_z is None:
            return
        dmg = Zombie.DAMAGE[best_zone]
        best_z.take_damage(dmg)
        self._spawn_damage_number(best_hit_pos, dmg)
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
        # 어두운 반투명 배경 + PAUSED + Mouse Sensitivity 슬라이더 + Resume/Quit.
        self.pause_frame = DirectFrame(
            frameColor=(0, 0, 0, 0.6),
            frameSize=(-0.55, 0.55, -0.45, 0.45),
            pos=(0, 0, 0),
            parent=self.aspect2d,
        )
        OnscreenText(
            text='PAUSED', pos=(0, 0.30), scale=0.12,
            fg=(1, 1, 1, 1), align=TextNode.ACenter, mayChange=False,
            parent=self.pause_frame,
        )
        OnscreenText(
            text='Mouse Sensitivity', pos=(0, 0.16), scale=0.045,
            fg=(0.9, 0.9, 0.9, 1), align=TextNode.ACenter, mayChange=False,
            parent=self.pause_frame,
        )
        self.sens_slider = DirectSlider(
            range=(0.02, 0.30),
            value=self.mouse_sens,
            pageSize=0.01,
            command=self._on_sens_change,
            parent=self.pause_frame,
            pos=(0, 0, 0.09),
            scale=0.35,
        )
        self.sens_value_text = OnscreenText(
            text=f'{self.mouse_sens:.3f}', pos=(0, 0.02), scale=0.04,
            fg=(1, 1, 0.7, 1), align=TextNode.ACenter, mayChange=True,
            parent=self.pause_frame,
        )
        DirectButton(
            text='Resume',
            scale=0.08, pos=(0, 0, -0.12),
            command=self._toggle_pause,
            parent=self.pause_frame,
            frameSize=(-3, 3, -0.8, 1.2),
        )
        DirectButton(
            text='Quit',
            scale=0.08, pos=(0, 0, -0.32),
            command=self.userExit,
            parent=self.pause_frame,
            frameSize=(-3, 3, -0.8, 1.2),
        )
        self.pause_frame.hide()

    def _on_sens_change(self):
        # DirectSlider command — 매 변경마다 호출. 현재 값 읽어서 mouse_sens 갱신.
        v = self.sens_slider['value']
        self.mouse_sens = v
        self.sens_value_text.setText(f'{v:.3f}')

    def _build_crosshair(self):
        """화면 중앙 십자 조준점 — 중심 gap 있는 + 모양. aspect2d 의 vertical 은 Z."""
        ls = LineSegs('crosshair')
        ls.setThickness(2)
        ls.setColor(1, 1, 1, 0.85)
        s = 0.020  # 바깥 끝 (aspect2d 단위)
        g = 0.005  # 중심 gap
        ls.moveTo(-s, 0, 0); ls.drawTo(-g, 0, 0)
        ls.moveTo(g, 0, 0);  ls.drawTo(s, 0, 0)
        ls.moveTo(0, 0, -s); ls.drawTo(0, 0, -g)
        ls.moveTo(0, 0, g);  ls.drawTo(0, 0, s)
        self.crosshair = self.aspect2d.attachNewNode(ls.create())
        self.crosshair.setLightOff()

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
            self.interact_text.setText('[F] Y Bot 으로 변환')
            self.interact_text.show()
        else:
            self.interact_text.hide()

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
        fps = ClockObject.getGlobalClock().getAverageFrameRate()
        self.hud.setText(
            f'anim:  {self.current_anim}'
            f'{"  +Shoot(hands)" if self._hands_oneshot else ""}'
            f'{"  +Reload(upper)" if self._reload_oneshot else ""}\n'
            f'ammo:  {self.ammo}/{self.ammo_max}'
            f'{"   EMPTY (R)" if self.ammo == 0 else ""}\n'
            f'fps:   {fps:.0f}\n'
            f'pos:   ({self.player_pos.x:.1f}, {self.player_pos.y:.1f}, {self.player_pos.z:.1f})\n'
            f'mode:  {"editor[F2]" if self.editor_mode else "fps"}'
            f'{"  KNEEL" if self.kneel_state == "kneel" else ""}'
            f'{"  KNEEL->" if self.kneel_state == "going_down" else ""}'
            f'{"  STAND->" if self.kneel_state == "going_up" else ""}'
            f'{"  ADS" if self.aim_t > 0.5 else ""}'
        )

        return Task.cont


if __name__ == '__main__':
    ZombieGame().run()
```

### 12.3 `scripts/` (요약)

- **`blender_merge_ybot.py`** — base FBX + anim FBX 머지 → scene.blend (NLA push).
- **`blender_strip_root.py`** — `pose.bones["mixamorig:Hips"].location` fcurve 제거.
- **`blender_scaffold_reload.py`** — Reload 액션 빌드 (FK PHASES + IK build_slide_ik +
  LeftForeArm Y-roll 90°). SLIDE_RIGHT=8, FWD=20, UP=15.
- **`blender_normalize_bones.py`** — `mixamorig9:*` / `mixamorig10:*` → `mixamorig:*`
  정규화 (bone + vertex group).
- **`blender_offset_bone.py`** — 본의 모든 action keyframe 의 rotation_quaternion 에
  quat 오프셋 post-multiply.
- **`blender_add_anims.py`** — 기존 .blend 에 anim FBX 추가.
- **`blender_split_arms.py`** — Alpha_Surface vertex 중 dominant-weight 본이 어깨/팔/손
  계열인 것만 떼서 `_Arms` 메쉬로 분리. Alpha_Joints 도 동일.
- **`blender_glb_to_blend.py`** — .glb → .blend (panda3d-gltf BufferError 우회).
- **`peek_glb.py`** — .glb JSON 헤더 요약.

## 13. requirements.txt

```
panda3d>=1.10.16
panda3d-gltf>=1.3.0
panda3d-blend2bam>=0.26.0
```

---

**끝.** 현재 코드 = 5방 선형 레벨(R0~R4) + 14좀비 (벽 차폐 시야 + Distance LOD + GPU 스키닝)
+ Y Bot 플레이어 (Valorant 스타일 + ADS + ±89° pitch + 8발 ammo + muzzle flash + tracer)
+ HP/Death/Transform 풀 구현. 스토리 인터랙션 (케이지/방화벽/콘솔/리빌/엔딩) 은 §10.1 의
TODO 단계.
