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
| `src/ui.py` | HUD — 크로스헤어, 탄약, HP, 피격 비네트, 헤드샷 데미지 숫자 |
| `src/settings_menu.py` | Esc 일시정지 메뉴 — 마우스 감도 슬라이더, Resume/Quit |
| `src/physics.py` | 충돌 마스크 상수 + 지면 ray 헬퍼 |

## 구현 완료

### 플레이어 / 카메라 (`src/player.py`)
- 1인칭 카메라 (눈높이 1.55m — 1.7m 는 너무 높아 화면을 팔/총이 차지함)
- 마우스룩: yaw는 player node, pitch는 camera에 분리해 적용. M_relative + `movePointer`로 중앙 고정. pitch ±89° 클램프
- WASD 이동, Shift 달리기(1.5x), Space 점프
- 중력 + 지면 충돌: CollisionRay 위쪽(local +Z 200)에서 아래로 발사. `dt`를 1/30초로 clamp해 첫 프레임 dt 폭주 시 터널링 방지. 스폰 직후 즉시 ground snap
- **ADS (우클릭)**: camLens FOV를 70°→50°로 lerp(0.12s), 마우스 민감도 절반, 권총을 화면 중앙으로 이동. 재장전 중에는 무시
- **체력 시스템**: max_hp=100. 좀비 strike에 맞으면 hp 감소 + 화면 붉은 비네트(alpha 0.55 → 0.8s 페이드)
- **View bob**: 걷기/달리기 시 카메라를 위아래(sin) + 좌우(sin/2) 흔들기. 권총 anchor(`np_anchor`)에 정확히 반대 위상 적용해 권총은 월드에 정지, 화면 안에서는 배경과 함께 흔들리게(GUN_BOB_RATIO = -1.0)

### 권총 / 양손 (`src/weapons.py`)
- 부품: 그립 + 프레임 + 슬라이드(anchor 노드) + 총신 + 탄창 + 머즐 플래시 + 오른손 + 왼손
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
- 보행 sway: 권총은 진폭 8%/팔은 42% (ADS 중). 평상시 100%. Shift 달리기 시 진폭 1.7배 + 주파수 1.5배. 정지/이동 전환은 지수 블렌드(SWAY_BLEND_RATE=8.0)
- 탄창 12발, 쿨다운 0.2초
- 재장전 (r): 2.0초 검사 자세 안무 — 권총을 카메라 안쪽으로 끌어와 위로 들고, 탄창 빠짐 → 새 탄창 → 슬라이드 당김. 왼손은 재장전 중 `wrtReparentTo(camera)`로 카메라 자식이 되어 권총 회전과 독립적으로 움직임, 종료 시 `_reset_left_hand`로 강제 복귀. ADS lerp/recoil과 충돌 방지를 위해 시작 시 finish 처리
- 피격 중 재장전 인터럽트(`abort_reload`): Sequence finish + doMethodLater 취소 + 왼손 강제 복귀. ammo는 충전 안 함(패널티)

### 좀비 (`src/zombie.py`)
- 키 1.75m. 부품: 다리 좌우 / 몸통 / 머리 / 팔 좌우, 각 박스. 어깨/엉덩이 pivot 노드로 wrapping해 자연스러운 흔들기
- AI: chasing → windup(0.45s) → strike(0.15s) → recover(0.35s) → cooldown(0.8s) → chasing. ATTACK_RANGE=2.0m 안에 들어오면 멈추고 공격 모션. windup 진입 시 1회만 플레이어 쪽으로 회전(이후 안 따라감, 피하기 가능)
- 워킹 애니메이션: sin 기반 절댓값 setHpr — 다리 좌우 18° + 왼다리 절뚝 bias 6°, 팔은 ARM_FORWARD_BASE_DEG=+90으로 앞을 향한 채 좌우/상하 흔들림, 몸통 sway 6°, 머리 12° 기울임 + 약한 떨림
- 체력 30. 부위별 배율: head 1.5x(2발 처치), body 1.0x(3발), 팔다리 0.5x(6발). 부위별 CollisionSphere에 두 PythonTag("zombie", "hit_part") 부착
- 체력바: 머리 위 빌보드 카드 2장(배경 + 채우기 pivot — setSx로 왼쪽 정렬 축소). 피격 후 2.5s 풀 알파 → 1.0s 페이드
- 사망: 뒤로 90° 쓰러짐(0.5s) → 페이드(0.6s) → removeNode. 충돌 마스크/PythonTag 즉시 해제해 raycast가 시체 안 잡음
- 매 프레임 hit-flash 색 복원 task가 연사 시 끊기지 않도록 이전 task 제거 후 재발급
- `ZombieManager.spawn_initial_wave()` — 플레이어 스폰 주위 5마리

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
- 헤드샷 데미지 숫자 — 크로스헤어 아래 `+15` 노란색, 0.35s 유지 + 0.25s 페이드 + 살짝 위로 떠오름. 매 헤드샷마다 새 OnscreenText → 동시 다발 지원

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
- **좀비 wave 시스템**: 초기 5마리 다 처치하면 다음 wave 자동 스폰
- **게임오버 / 리스폰 UI**: hp=0 시점 처리
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
| `src/weapons.py` | `ADS_GUN_POS` | `(0.0, 0.85, -0.10)` | 화면 중앙 |
| `src/weapons.py` | `MAG_SIZE` | `12` | |
| `src/weapons.py` | `COOLDOWN` | `0.2` | 초 |
| `src/weapons.py` | `RELOAD_TIME` | `2.0` | 초 |
| `src/weapons.py` | `MAX_RANGE` | `100.0` | m |
| `src/weapons.py` | `BASE_DAMAGE` | `10` | head=15 / body=10 / limb=5 |
| `src/zombie.py` | `WALK_SPEED` | `1.2` | m/s |
| `src/zombie.py` | `ATTACK_RANGE` / `ATTACK_HIT_RANGE` | `2.0` / `2.2` | m |
| `src/zombie.py` | `ATTACK_DAMAGE` | `10` | |
| `src/zombie.py` | `MAX_HP` | `30` | |

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
