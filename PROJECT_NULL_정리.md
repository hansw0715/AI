# PROJECT NULL — 프로젝트 정리 (Claude Project 지식 파일)

> 이 문서 하나로 게임 전체를 파악할 수 있도록 정리한 단일 지식 파일입니다.
> 코드 위치는 `파일명:줄번호` 형식으로 표기했습니다. 메인 코드는 전부 `zombie_game.py` 한 파일에 있습니다.

---

## 1. 게임 개요

**PROJECT NULL** — Panda3D로 만든 **1인칭 슈터(FPS)** 게임.

- *미러스 엣지* 스타일 시점: 1인칭이지만 풀바디 캐릭터(Mixamo Y Bot)를 그대로 두고 카메라를 머리 본(bone)에 붙여서, 아래를 보면 자기 몸·다리, 옆을 보면 어깨가 보인다.
- 9mm 권총을 RightHand 본에 부착해 사격 / 슬라이드 후퇴 / 재장전까지 동작.

### 게임 모드
- **솔로 플레이** — AI 봇과 1:1 대결 / 웨이브(좀비) 모드
- **멀티플레이** — TCP 릴레이 서버를 통한 인터넷 1:1 PvP (이름 입력 → 양쪽 준비완료 → 10킬 선취 승리)

### 핵심 메커닉
- 무기 2종: **9mm 권총 + 소총** (반동·탄퍼짐·재장전 모션 각각 다름)
- **부위별 데미지** — 본에 붙인 정밀 히트박스로 헤드샷(2방 처치)/몸통/팔다리 구분
- 발로란트식 탄 퍼짐, 슬라이드 재장전, 킬 콤보 사운드
- 적 AI는 시야 기반(거리·각도·벽 차폐)으로 인지·추격·공격

### 한 줄 소개
> "공유기 설정 없이 친구와 인터넷으로 붙는, 미러스 엣지 시점의 1:1 FPS — 헤드샷 2방이면 끝나는 빠른 라운드제 슈터."

---

## 2. 이름의 의미 — 왜 "PROJECT NULL"인가

`null`은 프로그래밍에서 *값이 없음 / 비어 있음*을 뜻한다. 이를 코드네임으로 삼아:
- **"공식적으로 존재하지 않는, 기록에서 지워진 프로젝트"** 라는 뉘앙스
- 개발자(프로그래머) 정체성을 담은 위트 — "이름 없는 프로젝트 = Null Project"
- 시작 화면에서 `NULL`을 경고색(레드)으로 강조

> ※ 이전엔 SF 격리시설 컨셉 문구(CONTAINMENT PROTOCOL / ISOLATE THE BREACH 등)가 있었으나, 실제 FPS 내용과 무관한 장식이라 모두 제거함. 현재 메뉴 문구:
> - 캡션: `FIRST-PERSON SHOOTER`
> - 타이틀: `PROJECT NULL`
> - 태그라인: `AIM · SHOOT · WIN`
> - 푸터: `© NULL PROJECT`

---

## 3. 실행 방법

```
# 최초 1회 (라이브러리 설치)
pip install panda3d>=1.10.16 panda3d-gltf>=1.3.0

# 실행
python play_online.py
```

- 윈도우에서는 `1_INSTALL.bat`(최초 1회) → `2_PLAY.bat`(실행) 더블클릭으로도 가능.
- `play_online.py`가 진입점: UTF-8 로그 재설정 후 `zombie_game.ZombieGame().run()`으로 시작 메뉴를 띄운다.
- 멀티: 메뉴에서 '멀티플레이' → 이름 입력 → 둘 다 '준비완료'. **같은 시간에 함께 켜야 매칭**된다.
- QUIT / 창 닫기는 정상 종료이며 더 이상 `crash_log.txt`를 남기지 않는다.

---

## 4. 프로젝트 구조

폴더: `...\카카오톡 받은 파일\Null Project\`

| 파일 | 역할 |
|---|---|
| `zombie_game.py` | **메인 게임 전체** (Panda3D, 약 51만 자) |
| `play_online.py` | 배포용 진입점 (UTF-8 설정 + 메뉴 시작) |
| `level.py` | 레벨/충돌(Wall, LevelCollider), 상수(PLAYER_RADIUS 등) |
| `kit_map.py` | 맵 생성 |
| `weapon_config.py` | 무기 설정 |
| `enemy_health.py` / `player_health.py` | 체력 관련 |
| `muzzle_marker.py` | 총구 위치 디버그 마커 |
| `assets/`, `Sound/`, `kenney_particle-pack/` | 모델·사운드·파티클 |
| `1_INSTALL.bat`, `2_PLAY.bat` | 윈도우 실행 배치 |
| `requirements.txt` | 의존성 (panda3d, panda3d-gltf) |

> 릴레이 서버는 **별도 프로젝트**(`C:\Users\한승원\tcp-relay\`)이며 Fly.io에 배포됨. (6장 참고)

---

## 5. 핵심 시스템 3가지

### 5-1. 멀티플레이 — TCP 릴레이 + 클라이언트 권위 상태 동기화

서버는 게임 로직을 모르고, **한쪽 바이트를 그대로 반대쪽으로 전달**만 한다(dumb byte pump). 둘 다 서버로 바깥 방향 접속 → 포트포워딩 없이 인터넷 PvP 가능.

| 내용 | 위치 |
|---|---|
| 릴레이 주소 상수 (`RELAY_HOST="37.16.31.147"`, `RELAY_PORT=8080`) | `zombie_game.py:341` |
| 패킷 포맷 (`NET_STATE_FMT`, struct 고정 바이너리) | `zombie_game.py:369` |
| 릴레이 접속 `_connect_relay` (TCP_NODELAY) | `zombie_game.py:8812` |
| 수신 데몬 스레드 `_net_recv_loop` (프레이밍) | `zombie_game.py:8832` |
| 송신 `_net_send` (45Hz 스로틀) | `zombie_game.py:8882` |
| **스냅샷 보간(핵심)** `_update_remote_avatar` | `zombie_game.py:8929` |
| 멀티 초기 셋업 `_setup_online` | `zombie_game.py:6631` |
| nonce 스폰 자동배정 | `zombie_game.py:1713` |

- **패킷**: 위치/시점 + 무기 인덱스 + 재장전 플래그 + 발사 카운터 + 누적 피해/사망 + nonce + 이름 + (축구) 공·점수·킥. 고정 길이라 TCP 스트림에서 정확히 한 프레임씩 잘라 언패킹.
- **스냅샷 보간**: 받은 위치를 도착 시각과 함께 버퍼에 쌓고, 상대를 `REMOTE_INTERP_DELAY`(0.12초) 과거 시점으로 렌더하며 두 스냅샷 사이를 선형 보간 → 순간이동/끊김 제거. 6m 넘게 점프하면 텔레포트(리스폰)로 보고 즉시 스냅.
- **nonce 트릭**: 릴레이가 역할을 못 정하므로 두 클라가 세션 랜덤 nonce를 비교 — 큰 쪽=스폰 A, 작은 쪽=스폰 B로 대칭 자동 배정.

```python
# 송신 — 45Hz 스로틀 후 고정 바이트 전송 (zombie_game.py:8882)
self._net_send_t += dt
if self._net_send_t < (1.0 / NET_SEND_HZ):
    return
pkt = struct.pack(NET_STATE_FMT, self.player_pos.x, self.player_pos.y, ...)
self._sock.sendall(pkt)

# 스냅샷 보간 — 0.12초 과거 시점을 감싸는 두 스냅샷 사이 보간 (zombie_game.py:8929)
render_t = time.monotonic() - REMOTE_INTERP_DELAY
al = (render_t - a[0]) / span
ipos = Vec3(a[1]+(b[1]-a[1])*al, a[2]+(b[2]-a[2])*al, a[3]+(b[3]-a[3])*al)
```

### 5-2. 적 AI — 시야 기반 유한 상태 기계(FSM)

A*/네비메시 같은 길찾기는 쓰지 않고, 매 프레임 플레이어 방향으로 직진 + 벽 충돌 해소.

| 내용 | 위치 |
|---|---|
| 좀비 클래스 전체 `class Zombie` | `zombie_game.py:504` |
| 히트박스 정의 `HITBOX_SPEC` | `zombie_game.py:524` |
| 본 캡슐 빌드 `_build_hitboxes` (exposeJoint) | `zombie_game.py:660` |
| 광선-히트 판정 `hit_test` | `zombie_game.py:686` |
| 시야 판정 `can_see_player` | `zombie_game.py:866` |
| **상태머신** `update` (IDLE/CHASE/ATTACK) | `zombie_game.py:917` |

```
IDLE --(플레이어를 봄)--> CHASE --(근접)--> ATTACK
  ^                          |                |
  +--(시야 잃음)<------------+<---(공격 끝)---+
                take_damage -> DYING -> DEAD
```

- **시야 판정 3단계**: ① 거리(25m 이내) ② 시야각(정면 ±70°) ③ 벽 차폐(직선에 벽 있으면 못 봄).
- **본 기반 히트박스**: Mixamo 스켈레톤의 실제 본에 캡슐/구를 붙여(`exposeJoint`) 월드 좌표를 매 프레임 추적 → 어떤 자세든 정확히 부위 판정. 헤드샷 50 데미지(100HP → 2방 사망).
- **거리 LOD**: 28m 너머의 적은 `hide()` + 업데이트 스킵으로 비용 0.

### 5-3. 플레이어 애니메이션 — 골격 3분할 + 가중치 블렌딩

| 내용 | 위치 |
|---|---|
| Y Bot 생성 + 골격 3분할 (`makeSubpart`) | `zombie_game.py:1885~1918` |
| 블렌드 활성 + 로코모션 루프 깔기 | `zombie_game.py:1922~1966` |
| 이동 애니 선택 `_target_anim` | `zombie_game.py:3580` |
| 로코모션 적용 `_update_locomotion` | `zombie_game.py:3597` |
| **가중치 수렴(핵심)** `_update_blend` | `zombie_game.py:4060` |
| 발사 단발 `_fire_weapon` 내부 | `zombie_game.py:3966` |
| 재장전 단발 `_play_reload_oneshot` | `zombie_game.py:4015` |

- **골격 3분할**: `lower`(다리/발, 항상 이동) / `upper`(척추~상체) / `hands`(양손). → "다리는 달리면서 손은 재장전" 같은 조합 가능.
- **블렌딩**: `enableBlend()`로 여러 애니를 동시에 돌리고 weight로 섞음. 모든 로코모션 애니를 weight 0으로라도 항상 loop → 전환 시 시작 프레임 안 튐.
- **가중치 수렴**: 각 파트·애니의 현재 weight를 목표 weight로 지수 평활(`setControlEffect`). "지금 무슨 애니"가 아니라 "각 애니 가중치를 부드럽게 밀어준다"가 핵심.
- 소총 장착 시 `_loco_anim`이 자동으로 `Rifle*` 변형으로 치환.

```python
# 골격 3분할 (zombie_game.py:1905)
self.ybot.makeSubpart('lower', includeJoints=['*Hips'],
                      excludeJoints=['*Spine*','*LeftHand*','*RightHand*'])
self.ybot.makeSubpart('upper', includeJoints=['*Spine'], ...)
self.ybot.makeSubpart('hands', includeJoints=['*LeftHand*','*RightHand*'])

# 가중치 지수 평활 (zombie_game.py:4060)
alpha = min(1.0, dt * speed)
new = cur + (tgt - cur) * alpha
self.ybot.setControlEffect(a, new, partName=p)
```

---

## 6. 릴레이 서버 — Fly.io 배포

> 서버 소스: `C:\Users\한승원\tcp-relay\` (`server.py`, `Dockerfile`, `fly.toml`)
> 사용 사이트: **Fly.io** (https://fly.io)

- **server.py** (asyncio 표준 라이브러리만, ~110줄): 방 1개·슬롯 2개(A=첫 접속, B=둘째). 한쪽 바이트를 `peer.write(chunk)`로 그대로 전달, 파싱 안 함. 3번째 접속 거절, 한쪽 끊기면 방 리셋.
- **Dockerfile**: `python:3.12-slim` + `server.py` 한 개 (의존성 없음).
- **fly.toml**: 앱 `tcp-relay-1v1`, 리전 `nrt`(도쿄), `protocol="tcp"`, `min_machines_running=1`(항상 1대 — 방 상태가 메모리에 있어 2대면 매칭 실패).
- **전용 IPv4 필요**: raw TCP는 공유 IP 불가 → 전용 IPv4($2/월) 할당. 최종 주소 **`37.16.31.147:8080`**.
- 계정: `hansw_0715@naver.com`. 배포: `tcp-relay` 폴더에서 `flyctl deploy`. 로그: `flyctl logs`. (윈도우에서 flyctl은 `& "$env:USERPROFILE\.fly\bin\flyctl.exe"` 풀 경로로 호출)

```python
# server.py 핵심 — 받은 바이트를 상대에게 그대로 전달
async def handle(reader, writer):
    slot = room.claim(writer)          # 첫 접속=A(0), 둘째=B(1)
    if slot is None:
        await close_writer(writer); return
    while True:
        chunk = await reader.read(65536)
        if not chunk: break
        peer = room.peer(slot)
        if peer is not None:
            peer.write(chunk); await peer.drain()
```

---

## 7. 빠른 참조 (요약표)

| 시스템 | 방식 | 핵심 함수 |
|---|---|---|
| 멀티플레이 | TCP 릴레이 + 상태 동기화 | `_net_send` / `_net_recv_loop` / `_update_remote_avatar` |
| 적 AI | 시야 기반 5-상태 FSM | `can_see_player` / `Zombie.update` / `hit_test` |
| 플레이어 애니 | 골격 3분할 + 가중치 블렌딩 | `makeSubpart` / `_update_blend` / `_target_anim` |
| 서버 | Fly.io dumb byte-pump relay | `server.py handle()` |
