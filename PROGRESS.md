# fps_game 진행 상태 (2026-05-19)

Panda3D 1.10.16 기반 1인칭 FPS 프로젝트. Python 3.11.9 / Windows.
실행: 프로젝트 루트에서 `python -m src.main` (또는 `python src/main.py`).

## 구현 완료

### 플레이어 / 카메라 (`src/player.py`)
- 1인칭 카메라 (눈높이 1.7m)
- 마우스룩: yaw는 player node, pitch는 camera에 분리해 적용. M_relative 모드 + `movePointer`로 화면 중앙에 고정. pitch는 ±89°에서 클램프
- WASD 이동, Shift 달리기(1.5x), Space 점프
- 중력 + 지면 충돌: CollisionRay 위쪽(local +Z 200)에서 아래로 발사. `dt`를 1/30초로 clamp해 첫 프레임 dt 폭주 시 터널링 방지. 스폰 직후 즉시 ground snap

### 환경 (`src/main.py`)
- Panda3D 기본 `models/environment` 사용
- `ENVIRONMENT_SCALE = 0.05` (사람 키 기준 자연스러움). 위치(`ENVIRONMENT_POS`)는 스케일에 비례해 자동 조정
- `setTwoSided(True)`로 풀/나무 뒷면 렌더링
- AmbientLight + DirectionalLight
- `camLens.setNear(0.05)` — 권총이 카메라 가까이 있어 기본 near=1.0이면 클립됨

### 권총 (`src/weapons.py`)
- 모델: `models/box` 3개 (슬라이드 + 그립 + 총신)로 조립. `setLightOff()`로 라이팅 무시, setColor 그대로 표시
- 위치: 카메라 기준 `PISTOL_REST_POS = (0.18, 1.0, -0.12)`. 좁은 기본 FOV(39°h/30°v) 안에 들어오도록 튜닝됨
- 발사 (mouse1):
  - 별도 `CollisionTraverser`로 1회성 raycast (player의 매 프레임 traverser와 분리)
  - 사거리 100m, `HITTABLE_MASK`와 매칭
  - 명중 지점에 빨간 sphere 0.5초 (hit marker, world 공간)
  - 머즐 플래시: 노란 sphere 0.04초 (pistol 자식)
  - 트레이서: 노란 LineSegs 0.05초. **camera-local 공간**에 그려서 이동 중 잔상 없음
  - 반동 애니메이션: 뒤로 0.10 → 복귀, 0.1초 (LerpPosInterval + Sequence)
- 탄창 12발, 쿨다운 0.2초
- 재장전 (r): 1.5초. 권총이 아래로 내려갔다 올라옴. 재장전 중엔 발사 불가

### 충돌 마스크 (`src/physics.py`)
- `GROUND_MASK = bit(1)` — 플레이어 발 ray용
- `HITTABLE_MASK = bit(2)` — 총알 raycast용
- 환경 모델은 `GROUND_MASK | HITTABLE_MASK` 둘 다

### HUD (`src/ui.py`)
- 중앙 크로스헤어 `"+"`
- 우하단 탄약 카운터 `"12 / 12"`, 재장전 중엔 `"Reloading..."`
- 모두 `OnscreenText`. 탄약 텍스트는 `a2dBottomRight` 부모 사용

## 안 한 것 / 다음 단계 후보

- **적/타겟 더미** (가장 우선순위 추천): 빨간 박스 몇 개 풍경에 세우고 N발 맞으면 사라짐. 게임 루프(쏘기 → 처치) 첫 완성
- **사운드**: 발사음/빈탄창음/재장전음. wav/ogg 파일 필요
- **명중 hitmarker**: 적 맞췄을 때 크로스헤어 깜빡
- **무기 교체 / 추가 무기**
- **벽 충돌**: 현재 지면만 충돌. 벽은 통과됨
- **view bobbing**: 걸을 때 권총 살짝 흔들림
- Bullet 물리 도입은 적/투사체 단계에서 검토 예정

## 주요 튜닝 상수

| 파일 | 상수 | 현재값 | 비고 |
|------|------|--------|------|
| `src/main.py` | `ENVIRONMENT_SCALE` | `0.05` | 0.05~0.15 권장 |
| `src/player.py` | `WALK_SPEED` | `8.0` | m/s |
| `src/player.py` | `RUN_MULTIPLIER` | `1.5` | Shift |
| `src/player.py` | `MOUSE_SENSITIVITY` | `0.15` | |
| `src/player.py` | `JUMP_VELOCITY` | `7.5` | |
| `src/player.py` | `GRAVITY` | `20.0` | m/s² |
| `src/player.py` | `EYE_HEIGHT` | `1.7` | m |
| `src/weapons.py` | `PISTOL_REST_POS` | `(0.18, 1.0, -0.12)` | 카메라 로컬 (x, y, z) |
| `src/weapons.py` | `MAG_SIZE` | `12` | |
| `src/weapons.py` | `COOLDOWN` | `0.2` | 초 |
| `src/weapons.py` | `RELOAD_TIME` | `1.5` | 초 |
| `src/weapons.py` | `MAX_RANGE` | `100.0` | m |

## 해결됐던 함정들 (재발 방지 메모)

- **첫 프레임 dt 폭주 → 터널링**: 모델 로딩/셰이더 컴파일로 첫 프레임 dt가 1초 가까이 됨. `dt = min(dt, MAX_DT)`로 클램프 + 스폰 시 즉시 ground snap
- **near plane 1.0m 기본값**: 화면에 가까이 둔 1인칭 무기가 통째로 클립됨. `camLens.setNear(0.05)` 필수
- **좁은 기본 FOV (39°h/30°v)**: 카메라에서 가까운 위치의 X/Z 오프셋은 frustum 밖이 되기 쉬움. 무기는 y≥1.0 정도 거리에 둬야 안전
- **directional light + dark color**: 1인칭 무기에 라이팅 적용되면 카메라 회전에 따라 거의 검정이 됨. `setLightOff()` + 적당히 밝은 setColor 권장
- **트레이서 잔상**: world 공간에 그리면 카메라가 옆을 지나가며 잔상처럼 보임. **camera-local 공간**에 부착해 해결. raycast가 카메라 정면이라 hit point는 camera-local에서 `(0, distance, 0)`
- **트레이서 시작점**: pistol-local 상수(BARREL_TIP_LOCAL)를 camera-local 부모 트레이서에 그대로 쓰면 안 됨. `self._muzzle_flash.getPos(self.base.camera)`로 변환
- **상대 import + 스크립트 직접 실행**: `python src/main.py`로 실행 시 `from .physics import ...` 깨짐. main.py 상단에서 `sys.path` + `__package__` 부트스트랩 보정
- **환경 스케일 ↔ 환경 위치 결합**: setScale만 줄이면 setPos는 월드 단위라 그대로 → 플레이어 스폰 XY가 지형 밖으로. ENVIRONMENT_POS를 스케일에 비례 계산
