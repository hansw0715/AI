# fps_game

Panda3D 기반 1인칭 FPS 좀비 서바이벌 게임. **Vampire Survivors 풍의 레벨업 시스템** + 부위별 데미지 + 두더지처럼 땅을 파고 등장하는 좀비 연출.

> 파이썬 기말 프로젝트 — 바이브코딩 기반 자유 주제

---

## 팀원 및 역할

| 이름 | GitHub | 역할 / 기여 |
|------|--------|------------|
| hansw0715 | [@hansw0715](https://github.com/hansw0715) | _(역할 추후 기입)_ |
| 임우찬 | _(GitHub ID 추후 기입)_ | _(역할 추후 기입)_ |
| 문건녕 | _(GitHub ID 추후 기입)_ | _(역할 추후 기입)_ |

> 협업 흔적은 각 팀원의 작업 브랜치(`feat/*`)와 main 으로 머지된 PR 에서 확인 가능합니다.

---

## 실행 모습

> 스크린샷 / GIF 는 발표 직전에 캡처해서 `assets/` 에 추가하고 아래에 링크합니다.

- ![게임 플레이](assets/gameplay.gif) ← _(녹화 후 추가)_
- ![레벨업 카드](assets/levelup.png) ← _(녹화 후 추가)_
- ![좀비 등장](assets/emerge.png) ← _(녹화 후 추가)_

---

## 기획 요약

평범한 좀비 슈팅에 **로그라이크 성장 루프**를 결합. 한 마리 죽일 때마다 XP 가 누적되고, 레벨업 시 4 장의 특성 카드 중 1 장을 골라 권총·이동·체력 등을 강화한다. 좀비는 한 곳에서 펑 하고 나타나는 대신 흙더미 텔레그래프 → 솟아오름 순으로 등장해 위치 예측 + 긴장감을 준다.

- **장르**: 1인칭 FPS + 로그라이크 성장
- **목표**: 10 웨이브를 클리어. 후반 웨이브로 갈수록 좀비가 늘고 XP 곡선이 가파라져 어떤 특성을 고르느냐가 승패를 가른다.
- **기대 효과**: 단순 사격 반복이 아니라, *내 빌드를 어떻게 키울까* 라는 작은 의사결정이 매 레벨마다 발생.

---

## 주요 기능 / 코드 설명

### 1. 1인칭 권총 시스템 (`src/weapons.py`)
- 그립 / 프레임 / 슬라이드 / 총신 / 탄창 / 양손 부품 박스 조립
- 발사 raycast (부위별 데미지 배율), 머즐 플래시, 트레이서, 슬라이드 후퇴, 반동
- ADS (우클릭 줌), 보행 sway, 검사 자세 재장전 안무 (2.0초)
- **레벨업 호환:** `BASE_DAMAGE / COOLDOWN / MAG_SIZE / RELOAD_TIME` 을 모듈 상수가 아닌 인스턴스 속성으로 보관해 런타임에 강화 가능. 재장전 타이머도 `doMethodLater` 대신 `update(dt)` 카운트다운 — paused / 레벨업 카드 동안 자동 정지.

### 2. 좀비 AI + 등장 연출 (`src/zombie.py`)
- 사람 형태 박스 조립 + 어깨/엉덩이 pivot 워킹 애니메이션
- 추적 → windup → strike → recover 공격 상태머신
- **등장 연출 (waiting → telegraph → emerging → alive)**:
  - 흙더미 카드 1.4m × 1.4m + 갈색 흙 파티클 분수
  - root Z 를 `-1.9` → `0.0` 으로 ease-out 1.5 초 lerp
  - 같은 웨이브 N 마리가 한꺼번에 솟지 않도록 무작위 `spawn_delay` staggering
- 부위별 hit-sphere (`head / body / 팔 / 다리`) + DAMAGE_MULTIPLIER

### 3. 레벨업 시스템 (`src/level_up.py`)
- `LevelUpManager` — XP 누적, 레벨 큐 처리, `xp_multiplier`
- `LevelUpScreen` — DirectGUI 4 카드 화면 + 마우스 모드 토글
- 8 특성: 데미지 / 연사 / 탄창 / 신속 재장전 / 이동 속도 / 최대 체력 / 즉시 회복 / 경험치 획득
- 4 단계 효과량 (common / rare / epic / legendary) — 카드별 독립 굴림
- **XP 곡선**: `30 + (L-1)*20 + (L-1)^2 * 5` (2차) — 후반일수록 가파르게 어려워짐

### 4. HUD / UI (`src/ui.py`)
- 크로스헤어, 탄약, HP, 피격 비네트
- 웨이브 정보 + 인터미션 카운트다운
- 좌상단 `Lv N` + render2d 전폭 노란 XP 바
- 한글 폰트 동적 로드 (맑은 고딕) — 모든 OnscreenText / DirectGUI 자동 적용

### 5. 그 외
- `src/player.py` — 마우스룩, 이동, 점프, 중력, 지면 ray, ADS FOV, view bob
- `src/effects.py` — 피격 파티클 + 흙 분수 파티클 (같은 task-loop 패턴)
- `src/damage_numbers.py` — 월드 공간 데미지 숫자 (빌보드, 페이드)
- `src/start_screen.py`, `src/settings_menu.py` — 시작 / 일시정지 메뉴

---

## 기술 스택

- **언어**: Python 3.11.9
- **엔진**: Panda3D 1.10.16
- **OS**: Windows 10/11
- **에디터 / AI 도구**: VS Code + Claude Code (Anthropic Opus 4.7)

---

## 실행 방법

### 환경 셋업

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

PowerShell 실행 정책 오류가 나면:

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 설치 검증

```powershell
python test_install.py
```

### 실행

```powershell
python -m src.main
```

---

## 조작

| 키 | 동작 |
|----|------|
| WASD | 이동 |
| Shift | 달리기 (1.5x) |
| Space | 점프 |
| Mouse | 시점 |
| Mouse1 | 발사 |
| Mouse3 (우클릭) | ADS (조준) |
| R | 재장전 |
| Esc | 일시정지 / 설정 |

레벨업 카드가 뜨면 4 장 중 한 장을 **클릭**해서 효과를 적용 + 게임 재개.

---

## 디렉토리 구조

```
fps_game/
├── README.md
├── PROGRESS.md           # 상세 구현 노트 + 함정 메모
├── PROMPTS.md            # 바이브코딩 프롬프트 기록
├── requirements.txt
├── test_install.py
├── assets/               # 모델/텍스처/사운드/폰트 (현재 비어 있음)
├── config/
└── src/
    ├── main.py           # 진입점, 상태 플래그(started/paused/level_up_active)
    ├── player.py         # 1인칭 컨트롤러
    ├── weapons.py        # 권총 + 양손
    ├── zombie.py         # 좀비 AI + 등장 연출
    ├── level_up.py       # 레벨업 매니저 + 카드 화면 + 특성 풀
    ├── hands.py
    ├── effects.py        # 피격 파티클 + 흙 분수
    ├── damage_numbers.py
    ├── ui.py             # HUD
    ├── start_screen.py
    ├── settings_menu.py
    └── physics.py
```

---

## 협업 / 브랜치 전략

- `main` : 최종 머지 대상. 모든 변경은 PR 을 거쳐 들어옵니다.
- `feat/*` : 팀원별 작업 브랜치. 예) `feat/level-up-screen`, `feat/zombie-emerge`, `feat/audio`
- PR 제목: `[기능] 한 줄 요약`
- 머지 전 다른 팀원 1 명 이상의 리뷰 권장

---

## 바이브코딩 프롬프트 기록

전체 프롬프트와 단계별 의사결정은 [`PROMPTS.md`](PROMPTS.md) 에서 확인.

---

## 진행 상태 / 다음 단계

세부 구현 노트, 튜닝 상수, 해결됐던 함정들은 [`PROGRESS.md`](PROGRESS.md) 에 정리되어 있습니다.

남은 작업 후보:
- 사운드 (발사음, 좀비 신음, 재장전음)
- 게임오버 / 리스폰 UI
- 벽 충돌 (현재 지면만)
- 환경 복원 (나무/바위 등)
