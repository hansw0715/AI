# fps_game 진행 상태 (2026-05-20)

Panda3D 1.10.16 기반 1인칭 FPS 프로젝트. Python 3.11.9 / Windows.
실행: 프로젝트 루트에서 `python -m src.main` (또는 `python src/main.py`).

## 모듈 개요

| 파일 | 역할 |
|------|------|
| `src/main.py` | 진입점. ShowBase 초기화, 환경/조명/카메라 near plane 설정, 일시정지 토글 |
| `src/player.py` | 1인칭 컨트롤러 — 마우스룩, 이동, 중력, view bob, ADS, 피격 비네트 |
| `src/weapons.py` | 권총 + 양손 — 발사/재장전/recoil/sway/ADS 모션, 부위별 raycast |
| `src/zombie.py` | 좀비 — 사람형 모델, 추적 AI, 워킹/공격 애니메이션, 부위별 데미지, 체력바, 사망 시퀀스 |
| `src/hands.py` | 손 모델 (주먹 + 팔뚝 + 소매 박스 조립) |
| `src/effects.py` | 피격 파티클 (부위별 개수/색/속도) |
| `src/damage_numbers.py` | 월드 공간 데미지 숫자 — 피격 위치에 빨간 숫자 떠올랐다 페이드 |
| `src/ui.py` | HUD — 크로스헤어, 탄약, HP, 피격 비네트, XP 바, Lv |
| `src/settings_menu.py` | Esc 일시정지 메뉴 — 마우스 감도 슬라이더, Resume/Quit |
| `src/start_screen.py` | 게임 시작 화면 — 타이틀 "Game" + Start/Settings/Controls 패널 |
| `src/level_up.py` | 레벨업 시스템 — XP/레벨 매니저 + 4 장 카드 선택 화면 + 8 특성 풀 |
| `src/physics.py` | 충돌 마스크 상수 + 지면 ray 헬퍼 |

## 구현 완료

### 플레이어 / 카메라 (`src/player.py`)
- 1인칭 카메라 (눈높이 1.55m — 1.7m 는 너무 높아 화면을 팔/총이 차지함)
- 마우스룩: yaw는 player node, pitch는 camera에 분리해 적용. M_relative + `movePointer`로 중앙 고정. pitch ±89° 클램프
- WASD 이동, Shift 달리기(1.5x), Space 점프
- 중력 + 지면 충돌: CollisionRay 위쪽(local +Z 200)에서 아래로 발사. `dt`를 1/30초로 clamp해 첫 프레임 dt 폭주 시 터널링 방지. 스폰 직후 즉시 ground snap
- **ADS (우클릭)**: camLens FOV를 70°→50°로 lerp(0.12s), 마우스 민감도 절반, 권총을 화면 중앙으로 이동. 재장전 중에는 무시
- **체력 시스템**: max_hp=100. 좀비 strike에 맞으면 hp 감소 + 화면 붉은 비네트(alpha 0.55 → 0.8s 페이드)
- **View bob**: 걷기/달리기 시 카메라를 위아래(sin) + 좌우(sin/2) 흔들기. 권총 anchor(`np_anchor`)에 정확히 반대 위상 적용해 권총은 월드에 정지, 화면 안에서는 배경과 함께 흔들리게(GUN_BOB_RATIO = -1.0). 진폭은 보행감만 살아나도록 완화 — WALK Z/X = 0.025/0.015, RUN Z/X = 0.035/0.022 (이전 0.06/0.035, 0.08/0.05 대비 ~42%)

### 권총 / 양손 (`src/weapons.py`)
- 부품: 그립 + 프레임 + 슬라이드(anchor 노드) + 총신 + 탄창 + 머즐 플래시 + 오른손 + 왼손
- 권총 부품 박스 Z-fight 제거 — grip/frame/magazine 볼륨 겹침 해소, slide/barrel 좌표는 ADS calibration 위해 유지. 새 Z 스택: slide[0.0, 0.052] / frame[-0.032, 0.0] / grip[-0.162, -0.032], 탄창 [-0.20, -0.05] 는 grip XY 안에 fully contained 되어 coplanar 표면 없음
- 슬라이드를 scale 없는 anchor로 둠 — 부모 scale이 자식에 곱해져 위치가 어긋나는 문제 회피
- 노드 계층: `camera → np_anchor (view bob) → np_sway (보행 sway) → self.np (권총 루트, ADS/recoil/reload가 점유)`
- 발사 (mouse1):
  - 별도 `CollisionTraverser`로 1회성 raycast
  - from-mask = `HITTABLE_MASK | ZOMBIE_MASK` → 환경/좀비 둘 다 검출
  - 좀비 hit 시 `entry.getNetPythonTag("zombie")` + `"hit_part"`로 부위 역참조 → 부위별 배율 적용
  - 부위별 파티클(`effects.spawn_hit_particles`) — head는 18개 + 흰/빨강 혼합, body 10개, 팔다리 5개
  - 헤드샷 시 크로스헤어 아래 `+15` 숫자 0.35s 표시 후 0.25s 페이드
  - 머즐 플래시 0.04s, 트레이서 0.05s (camera-local), 슬라이드 후퇴(40ms) + 권총 pitch +2° → 복귀
- ADS 시 권총을 우측 hip(`PISTOL_REST_POS`)에서 화면 중앙(`ADS_GUN_POS`)으로 lerp. FOV lerp와 같은 0.12s
- 보행 sway: 권총은 진폭 8%/팔은 42% (ADS 중). 평상시 100%. Shift 달리기 시 진폭 1.25배(이전 1.7배에서 완화) + 주파수 1.5배. 정지/이동 전환은 지수 블렌드(SWAY_BLEND_RATE=8.0). 기본 sway 변위는 GUN X/Z = 0.008/0.005, ARM P/R = 1.2°/0.6° — 이전(0.020/0.012, 3.0°/1.5°) 대비 약 40%로 축소해 조준선 안정
- 탄창 12발, 쿨다운 0.2초
- 재장전 (r): 2.0초 검사 자세 안무 — 권총을 카메라 안쪽으로 끌어와 위로 들고, 탄창 빠짐 → 새 탄창 → 슬라이드 당김. 왼손은 재장전 중 `wrtReparentTo(camera)`로 카메라 자식이 되어 권총 회전과 독립적으로 움직임, 종료 시 `_reset_left_hand`로 강제 복귀. ADS lerp/recoil과 충돌 방지를 위해 시작 시 finish 처리
- 피격 중 재장전 인터럽트(`abort_reload`): Sequence finish + doMethodLater 취소 + 왼손 강제 복귀. ammo는 충전 안 함(패널티)

### 좀비 (`src/zombie.py`)
- 키 1.75m. 부품: 다리 좌우 / 몸통 / 머리 / 팔 좌우, 각 박스. 어깨/엉덩이 pivot 노드로 wrapping해 자연스러운 흔들기
- AI: chasing → windup(0.45s) → strike(0.15s) → recover(0.35s) → cooldown(0.8s) → chasing. ATTACK_RANGE=2.0m 안에 들어오면 멈추고 공격 모션. windup 진입 시 1회만 플레이어 쪽으로 회전(이후 안 따라감, 피하기 가능)
- 워킹 애니메이션: sin 기반 절댓값 setHpr — 다리 좌우 18° + 왼다리 절뚝 bias 6°, 팔은 ARM_FORWARD_BASE_DEG=+90으로 앞을 향한 채 좌우/상하 흔들림, 몸통 sway 6°, 머리 12° 기울임 + 약한 떨림
- 체력 30. 부위별 배율: head 1.5x(2발 처치), body 1.0x(3발), 팔다리 0.5x(6발). 부위별 CollisionSphere에 두 PythonTag("zombie", "hit_part") 부착
- `take_damage(amount, hit_part)` 가 적용된 final_damage 를 반환 (이전엔 반환값 없음) → weapons.py 가 damage 숫자 UI 띄울 때 사용. DAMAGE_MULTIPLIER 는 zombie 내부에 캡슐화 유지
- 체력바: 머리 위 빌보드 카드 2장(배경 + 채우기 pivot — setSx로 왼쪽 정렬 축소). 피격 후 2.5s 풀 알파 → 1.0s 페이드
- 사망: 뒤로 90° 쓰러짐(0.5s) → 페이드(0.6s) → removeNode. 충돌 마스크/PythonTag 즉시 해제해 raycast가 시체 안 잡음
- 매 프레임 hit-flash 색 복원 task가 연사 시 끊기지 않도록 이전 task 제거 후 재발급
- `ZombieManager` 10 웨이브 상태머신 — `idle → spawning → active → intermission → ... → cleared`
  - 웨이브당 좀비 수: `WAVE_COUNTS = [3, 5, 7, 9, 12, 15, 18, 22, 26, 30]`
  - 스폰 위치는 동적 생성 — Ground 범위(X -11~10, Y -10~11) 내 랜덤, 플레이어로부터 최소 6m, 시도 10회 후 마지막 후보 fallback
  - 웨이브 종료 판정은 기존 `_on_zombie_removed` 콜백 재활용 — `active` 중 `len(self.zombies) == 0` 이면 인터미션 진입. 좀비 페이드(0.5+0.6=1.1s) 끝에 콜백이 호출되므로 자연스러운 텀
  - 인터미션은 3초. 카운트다운은 `update(dt)` 안에서 dt 누적 → 일시정지 시 함께 멈춤 (별도 doMethodLater 안 씀)
  - 마지막 웨이브(10) 클리어 시 `cleared` 상태 + VICTORY 표시. 그 후 종료/리스폰 UI 는 별도 작업

### 환경 (`src/main.py`)
- Panda3D 기본 `models/environment` 사용
- `ENVIRONMENT_SCALE = 0.05`. `ENVIRONMENT_POS`는 스케일에 비례해 자동 조정
- 좀비 시인성 위해 Ground/Ground01 메시만 남기고 나머지 자식 제거. 다음 단계에서 나무/바위 등 복원 예정
- `setTwoSided(True)`로 풀/나무 뒷면 렌더링
- AmbientLight + DirectionalLight
- `camLens.setNear(0.05)` — 권총이 카메라 가까이 있어 기본 near=1.0이면 클립됨

### HUD (`src/ui.py`)
- 중앙 크로스헤어 `"+"`
- 우하단 탄약 카운터 `"12 / 12"`, 재장전 중엔 `"Reloading..."`
- 좌하단 HP `"HP 100/100"`
- 피격 비네트 — render2d 전체 카드, `setBin("background", 0)`으로 다른 UI 아래
- 상단 중앙 `"Wave 3 / 10"` (항상) + `"Zombies: 7"` (active 동안만)
- 화면 중앙 인터미션 카운트다운 `"Wave 4 starting in 3..."` (intermission 동안만, 매초 갱신)
- 화면 중앙 `"VICTORY"` (10웨이브 클리어 시)

### 월드 데미지 숫자 (`src/damage_numbers.py`)
- 모든 좀비 피격마다 hit point 월드 위치에 final_damage 숫자가 잠깐 뜨고 위로 떠오르며 페이드. 헤드샷/일반/팔다리 모두 표시 (이전엔 헤드샷만 HUD 중앙에 떴음)
- TextNode + `BillboardEffect.makePointEye()` 로 카메라를 항상 향함, `setLightOff(1)` 로 라이팅 무시 (체력바와 같은 패턴), `setTransparency(MAlpha)` + 매 프레임 task 로 페이드
- 색/크기: 일반은 빨강 `(1.0, 0.2, 0.2)`, 헤드샷만 노란빛 빨강 `(1.0, 0.85, 0.2)` + 크기 1.3 배로 강조
- 수명 0.7초 (HOLD 0.3 + FADE 0.4), 위로 0.8m 떠오름. spawn 시 X/Z 에 ±0.15m jitter → 연사 시 같은 좌표에 겹치는 문제 회피
- task dt 는 effects.py 와 동일하게 `min(_clock.getDt(), 1/30)` 으로 클램프 — 첫 프레임 폭주 시 한 번에 끝까지 페이드되는 것 방지
- weapons.py 호출: `final_damage = hit_zombie.take_damage(BASE_DAMAGE, hit_part=hit_part)` 반환값을 그대로 표시 — DAMAGE_MULTIPLIER 는 zombie 안에 캡슐화

### 시작 화면 (`src/start_screen.py`)
- 부팅 시 환경/조명/카메라만 떠 있는 상태에서 시작 화면 표시. 월드는 메뉴 뒤로 보이게 frameColor 알파 0
- 메인 패널: 타이틀 "Game" + 세로 3 버튼 (Start / Settings / Controls)
- Settings 패널: 마우스 감도 슬라이더(일시정지 메뉴와 동일 사양) + Back. 변경값은 즉시 `player.sensitivity` 반영
- Controls 패널: WASD/Shift/Space/Mouse/L·R Click/R/Esc 매핑 텍스트 + Back
- 게임 상태 플래그: `started=False, paused=False` → 시작 화면. `_begin_game` 가 HUD 표시 + 마우스 캡처(M_relative) + `start_wave(1)` 실행
- 입력 게이트: mouse1/mouse3/R 모두 `main._on_*` 디스패처를 통해 `started and not paused` 조건일 때만 pistol/player 로 전달 — DirectGUI 버튼 클릭으로 들어오는 mouse1 이 사격을 발동시키지 않도록
- Esc 는 시작 화면 동안 무시 — 메뉴 버튼으로 명시적 진입을 강제
- HUD: `hide_gameplay/show_gameplay` 로 시작 화면 동안 크로스헤어/탄약/HP/웨이브 전부 숨김

### 좀비 등장 연출 (땅 파고 올라오기)
- 상태머신을 `waiting → telegraph → emerging → alive → dying → dead` 로 확장. `attack_state` 와 섞지 않고 분리. 각 단계에 `_enter_*` / `_update_*` 헬퍼
- `waiting`: spawn 직후 `spawn_delay = random(0, SPAWN_STAGGER_MAX_SEC)` 동안 안 보임 (root Z 가 `EMERGE_BURIED_Z = -1.9`). 같은 웨이브 N 마리가 한꺼번에 솟지 않도록 분산
- `telegraph` (1.2s): 흙더미 카드 1.4m × 1.4m 가 ground 평면(Z=0.01)에 깔리고 위에서 보임. 시작 시 큰 흙 분수 1 회
- `emerging` (1.5s): root Z 를 ease-out (`1 - (1-t)^2`) 으로 BURIED → GROUND 으로 보간. 양팔은 위로 뻗은 자세로 박제(워킹 anim 건너뜀). 진입 시 큰 흙 분수 1 회 + 0.15s 마다 작은 흙 분수. 흙더미 카드는 `t > 0.3` 시점부터 알파 페이드
- 흙 파티클: `effects.spawn_dirt_burst(base, world_pos, intensity)` — hit-particle 과 같은 task-loop / 빌보드 / 중력 / 알파 페이드 패턴, 위쪽(+Z) 편향 분수. 갈색 3 종 그라데이션 무작위
- 일시정지 호환: 모든 단계 타이머는 `update(dt)` 안에서 누적. `doMethodLater` / `Sequence` 안 씀 → paused / level_up_active 동안 자동 정지
- 피격 / 사망 처리:
  - `waiting/telegraph` 동안 hit-part `IntoCollideMask` 무력화 → raycast 가 묻힌 좀비를 안 잡음 (`_set_hit_parts_active`). emerging 진입 시 마스크 복원 → 머리/상체가 솟는 순간부터 명중 가능
  - emerging 중 hp 0 → `_start_death` 분기로 fall+linger 없이 알파 페이드만 (어색한 자세 회피). 흙더미 카드는 명시적 `removeNode`
  - 체력바: emerging 중 피격받아도 `healthbar_root.show` 호출 안 함 — alive 진입 후 다음 피격 시 정확한 ratio 로 표시
  - `_restore_color` 의 색 복원 조건을 `state == "alive"` → `state not in ("dying", "dead")` 로 확장 — emerging 피격 후 alive 진입 시 빨강 박제 방지
- 웨이브 종료 판정은 그대로 — waiting/telegraph/emerging 좀비도 `self.zombies` 에 남아 있어 자연 카운트, HUD `Zombies: N` 정확

### 레벨업 시스템 (`src/level_up.py`)
- 좀비 처치 시 XP 보상(`ZOMBIE_XP_REWARD = 10`). `Zombie.take_damage` 에서 hp ≤ 0 직전에 `game.level_up.add_xp(...)` 호출 — 사망 시퀀스 트리거 *전* 에 보상 확정
- XP 곡선 (2 차): `xp_to_next(L) = 30 + (L-1) * 20 + (L-1)^2 * 5`. Lv 1→2: 30, 2→3: 55, 3→4: 90, 4→5: 135, 5→6: 190, ..., 9→10: 510. 선형만으로는 후반이 너무 쉬워서 2 차 항으로 가속
- XP 획득 시 `xp_multiplier` 자동 적용 (기본 1.0, "경험치 획득" 특성으로 곱연산 누적)
- 한 번에 여러 레벨업이 가능 — `_pending_levelups` 큐로 처리해 카드 화면을 연속 표시. 카드 한 장 고르면 `consume_card()` 가 다음 단계 결정
- `LevelUpScreen` — DirectFrame 반투명 배경(`frameColor=(0,0,0,0.7)`) + DirectButton 카드 4 장 가로 배치. SettingsMenu 와 동일 패턴
- 희귀도: 카드 1 장당 독립 굴림 — common 50% / rare 30% / epic 15% / legendary 5%. 같은 화면 4 장은 perk 중복 금지, 희귀도 중복 허용
- 희귀도색: 회색 / 파랑 / 보라 / 황금. 카드 frame 배경에 RGB×0.25 로 어두운 색 깔고 텍스트는 풀 색 — 시각적으로 가장 안정적
- 특성 8 개: 데미지 / 연사 속도 / 탄창 크기 / 신속 재장전 / 이동 속도 / 최대 체력 / 즉시 회복 / 경험치 획득. 각 4 단계 효과량 (common/rare/epic/legendary)
- 특성 적용은 `apply(game, amt)` 콜백 — 각 perk 정의에 캡슐화. 직접 `game.pistol.base_damage` / `game.player.walk_speed` 등 인스턴스 속성 가감 (단방향 의존)
- 즉시 회복 전설(`amt=None`)은 풀 회복 — `describe`/`apply` 모두 None 처리 분기

#### 런타임 가변 인스턴스 속성 리팩토링
- `weapons.py`: `BASE_DAMAGE` → `Pistol.base_damage`, `COOLDOWN` → `cooldown_time`, `MAG_SIZE` → `mag_size`, `RELOAD_TIME` → `reload_time`. 모듈 상수는 초기값 source 로만 남음. shoot/reload/HUD 모두 인스턴스 속성 참조
- `player.py`: `WALK_SPEED` → `PlayerController.walk_speed`. `_update_movement` 가 참조
- 재장전 완료 타이머: 기존 `doMethodLater("pistol_reload_finish")` → `update(dt)` 안의 `self._reload_remaining` 카운트다운. `_weapons_update_task` 가 paused / level_up_active 둘 다 게이트하므로 재장전 중 레벨업 떠도 ammo 자동 충전 안 됨

#### main.py / player.py 게이트
- `level_up_active` 플래그 추가 — paused 와 동일하게 player.update / `_weapons_update_task` / `_on_mouse1` / `_on_mouse3` / `_on_reload` 가 모두 스킵
- Esc 토글은 level_up_active 동안 무시 — 카드 선택 강제
- LevelUpScreen show → 마우스 커서 + M_absolute (카드 클릭 가능). 카드 클릭 후 큐 비면 player._capture_mouse() + _first_mouse=True 로 게임 시점 복귀

#### HUD XP UI (`src/ui.py`)
- XP 바: render2d 화면 전폭(X=-1..+1)에 부착. 배경(회색) + 채우기 pivot(왼쪽 정렬 setSx) 패턴 — 좀비 체력바와 동일. 채우기 색은 황금 노란색
- Lv 텍스트: `a2dTopLeft` 좌상단 안쪽 (XP 바 바로 아래)
- `set_xp(level, xp, xp_to_next)` — 폭과 텍스트 동시 갱신. setSx(0) singular 경고 회피 위해 0.001 클램프
- hide/show_gameplay 토글에 xp_bar_bg/fill_pivot/level_text 포함

### 일시정지 + 설정 (`src/settings_menu.py`)
- Esc로 토글. paused 플래그가 True면 player/pistol/zombies update 모두 정지
- 토글 시 마우스 커서 표시 + M_absolute → UI 클릭 가능. resume 시 _first_mouse=True로 첫 프레임 델타 무시
- DirectGUI: PAUSED 타이틀 + 감도 슬라이더(0.025 ~ 0.5, 현재값 라벨) + Resume / Quit 버튼
- 감도 변경 시 `game.player.sensitivity` 실시간 반영

### 충돌 마스크 (`src/physics.py`)
- `GROUND_MASK = bit(1)` — 플레이어 발 ray
- `HITTABLE_MASK = bit(2)` — 권총 raycast 환경
- `ZOMBIE_MASK = bit(3)` — 좀비 부위. 권총 raycast는 from-mask에 `HITTABLE_MASK | ZOMBIE_MASK`
- 환경 모델은 `GROUND_MASK | HITTABLE_MASK` 둘 다

## 안 한 것 / 다음 단계 후보

- **사운드**: 발사음/빈탄창음/재장전음/좀비 신음. wav/ogg 파일 필요
- **명중 hitmarker**: 좀비 맞췄을 때 크로스헤어 깜빡
- **무기 교체 / 추가 무기** (소총, 산탄총 등)
- **벽 충돌**: 현재 지면만 충돌. 벽은 통과됨
- **게임오버 / 리스폰 UI**: hp=0 시점 처리. 10웨이브 클리어 후 VICTORY → 시작 화면 복귀/재시작 흐름도 같이
- **환경 복원**: 나무/대나무/바위/잎/실린더 다시 추가 (현재 시인성 위해 Ground만 남김)
- Bullet 물리 도입은 적/투사체 단계에서 검토 예정

## 주요 튜닝 상수

| 파일 | 상수 | 현재값 | 비고 |
|------|------|--------|------|
| `src/main.py` | `ENVIRONMENT_SCALE` | `0.05` | 0.05~0.15 권장 |
| `src/player.py` | `EYE_HEIGHT` | `1.55` | m, 1인칭 구도용 |
| `src/player.py` | `WALK_SPEED` | `8.0` | m/s |
| `src/player.py` | `RUN_MULTIPLIER` | `1.5` | Shift |
| `src/player.py` | `MOUSE_SENSITIVITY` | `0.075` | 설정 메뉴에서 0.025~0.5 |
| `src/player.py` | `ADS_DEFAULT_FOV` / `ADS_ZOOM_FOV` | `70` / `50` | 도 |
| `src/player.py` | `ADS_SENSITIVITY_MULT` | `0.5` | ADS 중 |
| `src/player.py` | `PLAYER_MAX_HP` | `100` | |
| `src/player.py` | `JUMP_VELOCITY` | `7.5` | |
| `src/player.py` | `GRAVITY` | `20.0` | m/s² |
| `src/weapons.py` | `PISTOL_REST_POS` | `(0.25, 0.9, -0.12)` | 우측 hip |
| `src/weapons.py` | `ADS_GUN_POS` | `(-0.0195, 0.85, -0.013)` | 머즐 플래시 X/Z 가 카메라 광축과 정렬 |
| `src/weapons.py` | `MAG_SIZE` | `12` | |
| `src/weapons.py` | `COOLDOWN` | `0.2` | 초 |
| `src/weapons.py` | `RELOAD_TIME` | `2.0` | 초 |
| `src/weapons.py` | `MAX_RANGE` | `100.0` | m |
| `src/weapons.py` | `BASE_DAMAGE` | `10` | head=15 / body=10 / limb=5 |
| `src/weapons.py` | `RUN_AMPLITUDE_MULT` / `RUN_FREQ_MULT` | `1.25` / `1.5` | 달리기 진폭/주파수 |
| `src/weapons.py` | `GUN_SWAY_X_SCALE` / `GUN_SWAY_Z_SCALE` | `0.008` / `0.005` | 권총 sway 최대 변위 (m) |
| `src/weapons.py` | `ARM_SWAY_P_DEG` / `ARM_SWAY_R_DEG` | `1.2` / `0.6` | 팔 sway 최대 (도) |
| `src/player.py` | `WALK_BOB_AMPLITUDE_Z` / `_X` | `0.025` / `0.015` | 카메라 보빙 (m) |
| `src/player.py` | `RUN_BOB_AMPLITUDE_Z` / `_X` | `0.035` / `0.022` | 달리기 보빙 (m) |
| `src/zombie.py` | `WALK_SPEED` | `1.2` | m/s |
| `src/zombie.py` | `ATTACK_RANGE` / `ATTACK_HIT_RANGE` | `2.0` / `2.2` | m |
| `src/zombie.py` | `ATTACK_DAMAGE` | `10` | |
| `src/zombie.py` | `MAX_HP` | `30` | |
| `src/zombie.py` | `WAVE_COUNTS` | `[3,5,7,9,12,15,18,22,26,30]` | 웨이브당 좀비 수 (인덱스+1 = 웨이브 번호) |
| `src/zombie.py` | `WAVE_INTERMISSION_SEC` | `3.0` | 웨이브 종료 ~ 다음 웨이브 시작 텀 (초) |
| `src/zombie.py` | `WAVE_SPAWN_MIN_DIST_FROM_PLAYER` | `6.0` | 좀비 스폰 시 플레이어 최소 거리 (m) |
| `src/zombie.py` | `WAVE_SPAWN_X_RANGE` / `_Y_RANGE` | `(-11,10)` / `(-10,11)` | Ground 메시 안 좌표 범위 |
| `src/zombie.py` | `TELEGRAPH_SEC` | `1.2` | 흙더미만 보이는 경고 시간 (초) |
| `src/zombie.py` | `EMERGE_SEC` | `1.5` | 좀비가 솟아오르는 시간 (초) |
| `src/zombie.py` | `EMERGE_BURIED_Z` / `EMERGE_GROUND_Z` | `-1.9` / `0.0` | waiting/telegraph 동안 root Z / 솟은 직후 root Z |
| `src/zombie.py` | `SPAWN_STAGGER_MAX_SEC` | `1.5` | 같은 웨이브 내 스폰 무작위 지연 최댓값 (초) |
| `src/zombie.py` | `DIRT_MOUND_HALF_SIZE` | `0.7` | 흙더미 카드 반폭 (m) — 1.4m × 1.4m |
| `src/zombie.py` | `EMERGE_DIRT_PERIOD` / `_INTENSITY` | `0.15` / `0.35` | emerging 중 지속 흙 분출 간격(초) / 개수 배율 |
| `src/effects.py` | `DIRT_PARTICLE_COUNT_BASE` | `14` | intensity=1.0 시 흙 파티클 개수 |
| `src/effects.py` | `DIRT_LIFETIME` | `0.55` | 흙 파티클 수명 (초) |
| `src/level_up.py` | `ZOMBIE_XP_REWARD` | `10` | 좀비 1 마리 처치 XP (xp_multiplier 적용 전) |
| `src/level_up.py` | `XP_BASE` / `XP_PER_LEVEL` / `XP_QUADRATIC` | `30` / `20` / `5` | `xp_to_next(L) = 30 + (L-1)*20 + (L-1)^2*5` (2 차 곡선) |
| `src/level_up.py` | `RARITY_WEIGHTS` | common 50 / rare 30 / epic 15 / legendary 5 | 카드 1 장당 독립 굴림 |
| `src/level_up.py` | 데미지 perk amounts | `(2, 5, 10, 20)` | `base_damage` 가산 |
| `src/level_up.py` | 연사 속도 perk amounts | `(0.05, 0.12, 0.25, 0.45)` | `cooldown_time` 곱연산 감소 비율 |
| `src/level_up.py` | 탄창 perk amounts | `(2, 4, 8, 16)` | `mag_size` + 현재 ammo 동시 증가 |
| `src/level_up.py` | 신속 재장전 perk amounts | `(0.08, 0.18, 0.35, 0.60)` | `reload_time` 곱연산 감소 비율 |
| `src/level_up.py` | 이동 속도 perk amounts | `(0.05, 0.12, 0.25, 0.45)` | `walk_speed` 곱연산 증가 비율 |
| `src/level_up.py` | 최대 체력 perk amounts | `(10, 25, 50, 100)` | `max_hp` 가산 + 현재 hp 동량 증가 |
| `src/level_up.py` | 즉시 회복 perk amounts | `(20, 50, 100, None)` | 정수면 회복 / `None` 이면 풀 회복 |
| `src/level_up.py` | 경험치 perk amounts | `(0.10, 0.25, 0.50, 1.00)` | `xp_multiplier` 곱연산 증가 비율 |
| `src/damage_numbers.py` | `DAMAGE_TEXT_HOLD_SEC` / `_FADE_SEC` | `0.3` / `0.4` | 풀 알파 / 페이드 (초) |
| `src/damage_numbers.py` | `DAMAGE_TEXT_RISE` | `0.8` | 수명 동안 위로 떠오르는 거리 (m) |
| `src/damage_numbers.py` | `DAMAGE_TEXT_SCALE` / `HEADSHOT_SCALE_MULT` | `0.6` / `1.3` | 기본 크기 / 헤드샷 배수 |
| `src/damage_numbers.py` | `DAMAGE_TEXT_JITTER` | `0.15` | spawn 시 X/Z ± 오프셋 (m) |

## 해결됐던 함정들 (재발 방지 메모)

- **첫 프레임 dt 폭주 → 터널링**: 모델 로딩/셰이더 컴파일로 첫 프레임 dt가 1초 가까이 됨. `dt = min(dt, MAX_DT)`로 클램프 + 스폰 시 즉시 ground snap
- **near plane 1.0m 기본값**: 화면에 가까이 둔 1인칭 무기가 통째로 클립됨. `camLens.setNear(0.05)` 필수
- **좁은 기본 FOV (39°h/30°v)**: 카메라에서 가까운 위치의 X/Z 오프셋은 frustum 밖이 되기 쉬움. 무기는 y≥1.0 정도 거리에 둬야 안전 → 현재는 ADS 도입과 함께 `setFov(70)` 적용
- **directional light + dark color**: 1인칭 무기에 라이팅 적용되면 카메라 회전에 따라 거의 검정이 됨. `setLightOff()` + 적당히 밝은 setColor
- **트레이서 잔상**: world 공간에 그리면 카메라가 옆을 지나가며 잔상처럼 보임. **camera-local 공간**에 부착해 해결. raycast가 카메라 정면이라 hit point는 camera-local에서 `(0, distance, 0)`
- **트레이서 시작점**: pistol-local 상수(BARREL_TIP_LOCAL)를 camera-local 부모 트레이서에 그대로 쓰면 안 됨. `self._muzzle_flash.getPos(self.base.camera)`로 변환
- **상대 import + 스크립트 직접 실행**: `python src/main.py` 시 `from .physics import ...` 깨짐. main.py 상단에서 `sys.path` + `__package__` 부트스트랩 보정
- **환경 스케일 ↔ 환경 위치 결합**: setScale만 줄이면 setPos는 월드 단위라 그대로 → 플레이어 스폰 XY가 지형 밖으로. ENVIRONMENT_POS를 스케일에 비례 계산
- **슬라이드에 setScale 직접 부여**: 부모 scale이 자식(barrel/muzzle_flash) 좌표/크기에 곱해져 위치가 어긋남. anchor 노드(no-scale) + 자식 메시 분리 패턴 사용
- **ADS lerp ↔ reload Sequence 노드 충돌**: 둘 다 `self.np`의 pos/hpr을 점유. reload 시작 시 `_current_ads.finish()` + `player.ads_active=False` 강제 해제
- **재장전 중 왼손 박제**: 왼손을 카메라 자식으로 reparent하므로 Sequence 중간에 finish/abort되면 엉뚱한 위치에 남음. Sequence 끝에 `Func(self._reset_left_hand)` 추가 + `abort_reload`에서도 같은 cleanup
- **view bob ↔ ADS lerp ↔ recoil 노드 다툼**: 모두 권총 루트의 pos를 건드림 → 3단 노드 계층(`np_anchor` → `np_sway` → `self.np`)으로 분리해 각각 다른 노드를 점유
- **좀비 어깨 pivot pitch 부호 혼동**: pivot의 +P=+Y(앞), -P=-Y(뒤). 처음 -90을 "앞"으로 잘못 가정해 좀비가 뒷걸음치는 것처럼 보임 → +90으로 뒤집고 windup/strike도 같이 양수 쪽으로
- **사망 시 색 복원 task 잔존**: 사망 후에도 flash 복원이 발동하면 시체에 색 변경 시도 → `_start_death`에서 명시적으로 `taskMgr.remove`
- **사망 좀비 raycast 재히트**: into-mask만 끄고 PythonTag 남기면 인스턴스가 GC 안 됨. mask + tag 둘 다 해제
- **체력바 setSx(0) singular matrix 경고**: 일부 드라이버에서 invert 실패. 0.001로 클램프 (시각적으로 동일)
- **AmbientLight 영향으로 체력바 어두워짐**: 빌보드 카드에 `setLightOff(1)` (priority=1로 부모 setLight override)
- **재장전 중 ADS 진입 시 권총 점프**: ADS lerp가 reload Sequence의 마지막 keyframe과 다른 노드 값으로 종료 → reload 중 ADS 무시(`set_ads`에서 early return)
- **공격 도중 좀비 사망 시 어깨 각도 박제**: `_start_death`에서 `arm_right_pivot.setHpr(0, REST_PITCH, 0)`으로 명시적 리셋
- **ADS 머즐 ↔ 크로스헤어 X/Z 어긋남**: pistol-local 에서 barrel/머즐 플래시가 `(0.0195, *, 0.013)` 만큼 그립 우상단으로 오프셋되어 있어서, `ADS_GUN_POS.x/z` 를 0 으로 두면 화면 중앙에 와도 총구는 크로스헤어 오른쪽-아래에 놓인다. `ADS_GUN_POS = Vec3(-0.0195, 0.85, -0.013)` 로 barrel offset 만큼 음수 보정해 머즐이 카메라 광축에 정확히 오게 함 (raycast 는 카메라 정면이라 명중에는 영향 없음, 순수 시각 정렬)
- **DirectGUI 버튼 클릭 → 전역 mouse1 발동**: 시작 화면의 Start 버튼을 클릭하면 DirectButton 의 클릭 처리와 별개로 전역 `"mouse1"` 이벤트도 함께 발생해 `pistol.shoot` 가 트리거됨. main 에 `_on_mouse1/_on_mouse3/_on_reload` 디스패처를 두고 `started and not paused` 조건에서만 통과시키도록 게이트 (R/우클릭도 동일 패턴)
