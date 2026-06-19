"""
배포용 진입 스크립트 — 친구가 더블클릭으로 실행하는 시작점.
원본 zombie_game.py 는 건드리지 않고, 여기서:
  1) stdout/stderr 를 UTF-8 로 재설정 (한글 print 의 cp1252 인코딩 크래시 방지)
  2) 시작 화면(메뉴)부터 띄운다 — 메뉴에서 솔로(AI 대결/웨이브) / 멀티(이름 입력 후
     준비완료) 를 직접 고른다.
  3) 시작 중 예외가 나면 스크립트 옆 crash_log.txt 에 기록(친구가 보내줄 수 있게)
스폰 위치(A/B)는 zombie_game 이 자동 배정한다.
"""
import sys
import os
import traceback

# 한글 로그가 Windows 기본 코드페이지(cp1252/cp949)로 인코딩되며 죽는 것 방지.
for _name in ('stdout', 'stderr'):
    _stream = getattr(sys, _name, None)
    if _stream is not None:
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def _crash_log_path():
    base = os.path.dirname(sys.executable if getattr(sys, 'frozen', False)
                           else os.path.abspath(__file__))
    return os.path.join(base, 'crash_log.txt')


try:
    import zombie_game
    # 시작 메뉴부터(menu=True 기본). 솔로/멀티는 메뉴에서 선택.
    zombie_game.ZombieGame().run()
except (SystemExit, KeyboardInterrupt):
    # QUIT / 창 닫기 = 정상 종료. 크래시 로그를 남기지 않는다.
    raise
except BaseException:
    try:
        with open(_crash_log_path(), 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)
    except Exception:
        pass
    raise
