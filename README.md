# fps_game

Panda3D 기반 3D FPS 게임 프로젝트. 1인칭 권총 + 추적 좀비 + 부위별 데미지.

## 요구사항

- Python 3.11.9
- Windows 10/11

## 개발 환경 셋업

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

PowerShell 실행 정책 오류가 나면:

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 설치 검증

가상환경을 활성화한 상태에서 다음을 실행하면 회색 3D 풍경이 보이는 창이 떠야 합니다.

```powershell
python test_install.py
```

## 실행

```powershell
python -m src.main
```

또는 `python src/main.py` (sys.path 부트스트랩 내장).

## 조작

| 키 | 동작 |
|----|------|
| WASD | 이동 |
| Shift | 달리기 (1.5x) |
| Space | 점프 |
| Mouse | 시점 |
| Mouse1 | 발사 |
| Mouse3 | ADS (누르고 있는 동안) |
| R | 재장전 |
| Esc | 일시정지 / 설정 메뉴 |

## 디렉토리 구조

```
fps_game/
├── assets/             # 모델/텍스처/사운드/폰트 (현재 빈 디렉토리)
│   ├── fonts/
│   ├── models/
│   ├── sounds/
│   └── textures/
├── config/
├── src/
│   ├── __init__.py
│   ├── main.py         # 진입점 + 환경/조명/일시정지
│   ├── player.py       # 마우스룩, 이동, ADS, view bob, 체력
│   ├── weapons.py      # 권총 + 양손 + 재장전 안무
│   ├── zombie.py       # 좀비 AI + 워킹/공격 애니메이션 + 부위별 데미지
│   ├── hands.py        # 1인칭 손 모델
│   ├── effects.py      # 피격 파티클
│   ├── ui.py           # HUD (크로스헤어, 탄약, HP, 비네트)
│   ├── settings_menu.py # Esc 일시정지 메뉴
│   └── physics.py      # 충돌 마스크 + 지면 ray
├── PROGRESS.md         # 상세 구현 노트 + 함정 메모
├── requirements.txt
├── test_install.py
└── README.md
```

상세한 구현 노트와 함정 메모는 [PROGRESS.md](PROGRESS.md) 참고.
