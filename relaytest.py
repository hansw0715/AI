"""
relaytest.py — 게임 붙이기 전에 TCP 릴레이 서버만 먼저 검증하는 텍스트 채팅 툴.

릴레이는 raw 바이트 중계기라 텍스트로도 그대로 테스트된다. 게임의 20바이트
바이너리 프레임 대신 사람이 읽을 수 있는 글자를 주고받아 동작을 눈으로 확인.

사용:
    터미널 2개에서 각각  python relaytest.py
    한쪽에 글자 치고 Enter → 반대쪽 '[상대]' 로 떠야 정상.
    종료: /quit 입력 또는 Ctrl+C.

확인 포인트:
  1) A 에서 친 글자가 B 에 뜨나? (반대도)
  2) ⭐ 자기가 친 게 자기한테 '[상대]' 로 돌아오지 '않아야' 한다.
     돌아오면 서버가 echo 하는 버그 → 게임에선 내 아바타가 유령처럼 겹침.
     (이 스크립트는 내가 친 건 '[나]' 로만 로컬 출력하고, 서버에서 온 것만
      '[상대]' 로 출력한다. 그러니 '[상대]' 에 내 문장이 보이면 = echo 버그.)
  3) 터미널 3개째 붙이면 거절/끊김 되나? (서버가 1방 2슬롯이면 3번째는 막혀야 함)
"""
import socket
import sys
import threading

HOST = "37.16.31.147"
PORT = 8080


def recv_loop(sock):
    """서버에서 오는 바이트를 그대로 받아 '[상대]' 로 출력. 끊기면 알림."""
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                print('\n[연결종료] 서버/상대가 연결을 끊음.', flush=True)
                break
            text = data.decode('utf-8', errors='replace')
            # 줄바꿈 정리해서 보기 좋게
            print(f'[상대] {text.rstrip()}', flush=True)
    except OSError as e:
        print(f'\n[수신오류] {e}', flush=True)


def main():
    print(f'[접속시도] {HOST}:{PORT} ...', flush=True)
    try:
        sock = socket.create_connection((HOST, PORT), timeout=5.0)
    except OSError as e:
        # 3번째 터미널이거나 서버 다운이면 보통 여기로 (거절/타임아웃).
        print(f'[접속실패] {e}', flush=True)
        print('  → 서버가 안 떠 있거나, 이미 2명이 차서 거절됐을 수 있음.', flush=True)
        return
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print('[접속성공] 글자 치고 Enter. 종료는 /quit', flush=True)

    threading.Thread(target=recv_loop, args=(sock,), daemon=True).start()

    try:
        for line in sys.stdin:
            line = line.rstrip('\n')
            if line == '/quit':
                break
            # 내가 친 건 로컬에서만 '[나]' 로 보여줌 — 서버로는 그대로 전송.
            # 서버가 echo 안 하면 이 문장은 '[상대]' 로 다시 안 떠야 정상.
            print(f'[나] {line}', flush=True)
            try:
                sock.sendall((line + '\n').encode('utf-8'))
            except OSError as e:
                print(f'[송신오류] {e}', flush=True)
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sock.close()
        except OSError:
            pass
        print('[종료]', flush=True)


if __name__ == '__main__':
    main()
