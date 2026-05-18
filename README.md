# fps_game

Panda3D 기반 3D FPS 게임 프로젝트.

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

## 디렉토리 구조

```
fps_game/
├── assets/
│   ├── models/
│   ├── textures/
│   ├── sounds/
│   └── fonts/
├── src/
│   └── __init__.py
├── config/
├── requirements.txt
├── test_install.py
└── README.md
```
