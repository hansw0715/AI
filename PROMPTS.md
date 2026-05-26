# 바이브코딩 프롬프트 기록

> 이 프로젝트의 코드는 **Claude Code (Anthropic Opus 4.7)** 와의 대화를 통해
> 작성되었습니다. 핵심 프롬프트와 구현 결과를 단계별로 정리합니다.

각 단계는 `프롬프트 → 의사결정 → 결과` 흐름으로 기록.

---

## 0. 프로젝트 시작 (이전 세션)

이전 세션에서 다음이 구축되어 있었음 (구현 노트: [`PROGRESS.md`](PROGRESS.md) 참고).

- 1인칭 카메라 + 마우스룩 + WASD + 점프 + 중력
- 권총 모델 (그립/슬라이드/총신/탄창/양손) + 발사 raycast + ADS + 재장전 안무
- 좀비 (사람형 박스 + 워킹 anim + 추적 AI + 공격 상태머신 + 부위별 데미지)
- 10 웨이브 시스템 + 인터미션 카운트다운 + VICTORY
- HUD (크로스헤어 / 탄약 / HP / 피격 비네트)
- 시작 화면, 일시정지 메뉴, 월드 공간 데미지 숫자

---

## 1. 레벨업 시스템 추가

### 프롬프트 요지
> "좀비 FPS 게임에 뱀파이어 서바이버스 스타일의 레벨업 시스템을 추가해줘.
> 좀비 죽일 때마다 XP, 누적되면 레벨업, 4 장의 특성 카드 중 1 장 선택,
> 4 가지 희귀도(common 50% / rare 30% / epic 15% / legendary 5%),
> 8 가지 특성 (데미지 / 연사 / 탄창 / 신속재장전 / 이동속도 / 최대체력 /
> 즉시회복 / 경험치 획득)…"

상세 스펙: XP 곡선, 카드 UI 레이아웃, 특성별 4 단계 효과량, 일시정지 호환,
재장전 doMethodLater 의 paused 무시 문제까지 명시.

### 주요 의사결정
- `LevelUpManager` (XP/큐) + `LevelUpScreen` (DirectGUI) **두 클래스로 분리**.
  특성 적용은 perk 별 `apply(game, amt)` 클로저로 캡슐화 → 직접 인스턴스 속성 가감.
- `weapons.py / player.py` 의 모듈 상수(`BASE_DAMAGE`, `COOLDOWN`, `MAG_SIZE`,
  `RELOAD_TIME`, `WALK_SPEED`)를 **인스턴스 속성으로 리팩토링**.
  특성이 런타임에 가감 가능해짐.
- 재장전 완료 타이머 `doMethodLater("pistol_reload_finish")` → `update(dt)` 안의
  `self._reload_remaining` 카운트다운 으로 변경. `_weapons_update_task` 가
  paused / level_up_active 둘 다 게이트하므로 자동 정지.
- `main.py` 에 `level_up_active` 플래그 추가 — paused 와 동일하게 player.update /
  weapons_update / 입력 핸들러 게이트. Esc 토글은 level_up_active 동안 무시
  (특성 선택 강제).

### 결과 파일
- 신규: `src/level_up.py`
- 수정: `src/weapons.py`, `src/player.py`, `src/zombie.py`, `src/main.py`, `src/ui.py`

---

## 2. XP 곡선 가파르게

### 프롬프트
> "레벨이 오를 수록 레벨업 하기 어려운 식으로 경험치 요구량이 높게 만들어줘."

### 의사결정
선형(`30 + (L-1)*20`) → **2 차 곡선**(`30 + (L-1)*20 + (L-1)^2 * 5`).
`XP_QUADRATIC` 노브로 가속 강도 조절 가능. 0 이면 기존 선형으로 복귀.

| 레벨 | 선형 | 2차 |
|------|------|-----|
| 1→2  | 30 | 30 |
| 5→6  | 110 | 190 |
| 9→10 | 190 | 510 |

### 결과
- 수정: `src/level_up.py` (`xp_to_next` + 상수)

---

## 3. 백업본 생성

### 프롬프트
> "백업본 하나 만들어줘 똑같이 클론시켜서 혹시나 잘못될 떄를 고려해서."

### 의사결정
`venv` 와 `__pycache__` 제외하고 `robocopy` 로 전체 복사
(venv 는 `pip install -r requirements.txt` 로 재생성 가능).

### 결과
`C:/Users/hansw/Desktop/fps_game_2026-05-26/` 생성. 23 파일 + .git 116 파일.

---

## 4. 좀비 등장 연출 (땅 파고 올라오기)

### 프롬프트 요지
> "좀비가 빵 하고 나타나는 대신 두더지처럼 땅을 파고 올라오는 등장 연출을 추가해줘.
> alive 앞에 emerging 단계 추가, 흙더미 텔레그래프 → 솟아오름…
> doMethodLater / Sequence 안 쓰고 update(dt) 누적으로…"

### 주요 의사결정
- 좀비 상태머신 확장: `waiting → telegraph → emerging → alive → dying → dead`.
  `attack_state` 와 섞지 않고 분리.
- 흙 파티클 헬퍼 `effects.spawn_dirt_burst(base, world_pos, intensity)` 추가 —
  hit-particle 과 같은 task-loop / 빌보드 / 중력 / 알파 페이드 패턴이지만
  위쪽(+Z) 편향 분수 + 갈색 그라데이션.
- ease-out 보간(`1 - (1-t)^2`) — 처음엔 빠르게 솟다가 마지막에 천천히 안착.
- 같은 웨이브 N 마리가 한꺼번에 솟지 않도록 `spawn_delay = random(0, 1.5)`
  staggering.
- 모든 타이머는 `update(dt)` 안에서 누적 → paused / level_up_active 와 자동 호환.
- waiting/telegraph 동안 hit-part 마스크 무력화 → raycast 가 묻힌 좀비 안 잡음.
  emerging 진입 시 복원.
- emerging 중 사망 시 `_start_death` 분기로 fall lerp 생략하고 알파 페이드만.

### 결과 파일
- 수정: `src/effects.py` (`spawn_dirt_burst`), `src/zombie.py` (상태 추가),
  `PROGRESS.md`

---

## 5. 권총 부품 Z-fight 제거

### 프롬프트 요지
> "Pistol._build_model() 에서 권총 부품 박스들이 볼륨이 서로 겹쳐서
> Z-fighting 으로 인한 레인보우 색 깜빡임이 발생한다. 부품 위치/크기를 조정해서
> 볼륨 겹침을 제거해라. slide_mesh, barrel, ADS calibration 은 절대 변경 금지…"

### 주요 의사결정
- slide / barrel 좌표는 ADS 정렬 calibration 위해 유지.
- **새 Z 스택**: slide `[0, 0.052]` → frame `[-0.032, 0]` → grip `[-0.162, -0.032]`.
  접촉면은 coplanar 평면 한 장만 → opposite-facing 으로 z-fight 안 일어남.
- 탄창 Z `[-0.20, -0.05]` 로 내리고 XY footprint 를 grip XY 안에 fully contained.
  grip 의 외각면이 mag 위쪽을 가려 coplanar 표면이 생기지 않음.
- 변경한 setPos/setScale 라인마다 인라인 코멘트로 새 extent 표기 → 추후 검증 가능.

### 결과 파일
- 수정: `src/weapons.py` (`_build_model`), `PROGRESS.md` (한 줄 추가)

---

## 6. 한글 폰트

### 증상
> "폰트가 깨지는데 다 네모로 보여서 그거 해결해줘"

레벨업 카드의 한글 텍스트(`기본 / 희귀 / 에픽 / 전설`, `데미지 증가` 등)가
Panda3D 기본 폰트에 글리프 없어서 네모로 표시됨.

### 의사결정
- Windows 맑은 고딕 `C:/Windows/Fonts/malgun.ttf` 를 `loader.loadFont()` 로 동적
  로드 후 `TextNode.setDefaultFont()` 로 전역 등록 → 모든 OnscreenText / DirectGUI
  가 자동으로 한글 지원.
- `Filename.fromOsSpecific()` 으로 Panda3D VFS Unix-style 경로 변환.
- `loadFont` 가 실패 시 `IOError` 던지므로 `try/except` 로 감싸 비-Windows 환경
  fallback 보장.

### 결과 파일
- 수정: `src/main.py` (`__init__` 초입 폰트 로드 블록)

---

## 7. 좀비 추적 버그 픽스

### 증상
> "좀비가 플레이어에게 끝까지 안 다가오는 버그. 가만히 서 있으면 좀비가 공격을 안 함."

### 원인 분석
`Zombie._dist_to_player()` 는 **3D `length()`**, 반면 `_update_chase` 의 정지
조건은 `to_player.z = 0` 으로 **수평 거리 (XY)** 비교. 두 기준이 어긋나서
플레이어가 `Ground01` (Z≈-0.28) 메시 위에 있을 때 좀비-플레이어 사이에 항상
0.28m Z 갭이 생기고, 3D dist 가 XY dist 보다 큼.

- `_update_chase`: XY = 2.0m == ATTACK_RANGE → 정지
- `update(dt)`: 3D = 2.02m > ATTACK_RANGE → windup 진입 실패
- 결과: 좀비가 ATTACK_RANGE 직전에서 영원히 정지

### 의사결정
`_dist_to_player` 를 XY 수평거리(`sqrt(dx² + dy²)`)로 통일. 모든 호출자
(`update`, `_enter_strike`) 가 같은 기준 사용.

### 결과 파일
- 수정: `src/zombie.py` (`_dist_to_player`)

---

## 8. GitHub 업로드 + 기말 제출 정리

### 프롬프트
> "깃허브 hansw0715 계정 속 레포지토리 AI 안에 fps_game 올린 데가 있을텐데
> 거기에 fps_game파일 올려주라"
> + "기말 프로젝트 공지 [평가 기준에 맞춰 깃허브 설정이랑 올렸던 것들 수정]"

### 의사결정
- `git push ai main:fps_game` 으로 `hansw0715/AI` 의 `fps_game` 브랜치에 푸시.
- 평가 기준 충족을 위해 본 `PROMPTS.md` + `README.md` (팀원 표 / 실행 / 스크린샷
  자리 / 주요 코드 설명) 추가.
- main 머지는 PR 만 생성하고 마지막 머지는 사용자가 직접 클릭.
- Public 전환은 GitHub 웹 UI 에서 직접.

---

## 바이브코딩 활용 패턴

이번 프로젝트에서 자주 사용한 프롬프트 구조:

1. **사양 명세형**
   - 기능 한 문장 + 사용자 흐름 + 구체적 매개변수 + 호환 제약을 같이 적음.
   - 예: "레벨업 카드는 4 장, 희귀도는 카드별 독립 굴림, 같은 화면에서 perk 중복
     금지, 일시정지 호환…"
   - 결과: AI 가 한 번에 충분한 구조를 잡아냄. 자잘한 follow-up 불필요.

2. **버그 리포트형**
   - 증상 한 줄 + (필요 시) 재현 조건.
   - 예: "좀비가 끝까지 안 다가오는 버그. 가만히 있으면 공격을 안 함."
   - AI 가 코드 읽고 원인 추적 + 수정. 디버깅을 떠넘기지 않고 핵심 증상만 명확히.

3. **제약 명세형 (좌표 / 인터페이스 보존)**
   - "X 는 절대 변경 금지, Y 는 조정 가능, 성공 기준은 …"
   - 예: 권총 z-fight 수정 시 slide/barrel 좌표는 ADS 정렬 위해 유지하라고 명시.
   - AI 가 calibration 기준을 망가뜨리지 않으면서 자유도 안에서 최적화.

4. **운영 명령형**
   - "백업해줘 / 깃에 올려줘 / 실행시켜봐"
   - 한 줄로 충분. AI 가 알아서 robocopy / git push / 백그라운드 실행.

---

## 부록 — 협업 시 권장 패턴 (이 프로젝트 회고)

- 새 기능은 별도 브랜치(`feat/*`) → PR → 리뷰 → main 머지.
- 큰 리팩토링 (예: 모듈 상수 → 인스턴스 속성) 은 기능 추가와 같은 커밋에 묶지
  말고 분리 커밋 권장 (이번엔 단일 커밋으로 묶어 history 가 다소 큼 — 회고 사항).
- `PROGRESS.md` 에 함정 메모를 누적해두면, 같은 클래스의 버그가 또 생겼을 때
  과거 fix 컨텍스트를 빠르게 회상 가능.
