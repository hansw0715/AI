"""소총 총구(muzzle) 위치 튜닝용 마커 하네스 — 게임 중 L 키로 켜고 끔.

zombie_game.py 의 ENABLE_MUZZLE_MARKER = True 면 하네스가 로드되고,
게임 중 L 키로 마커를 활성/비활성(표시/숨김) 토글. 처음엔 비활성(숨김).

조작 (마커 활성 상태에서만)
  L   = 마커 켜기/끄기
  I/K = ±Y(전후)   H/J = ±X(좌우)   U/O = ±Z(상하)   (1cm 단위)
  M   = 현재 위치를 RIFLE_MUZZLE_POS 형식으로 출력
옮긴 자리가 곧 소총 총구(=muzzle flash/tracer 시작점) → 출력값을
weapon_config.RIFLE_MUZZLE_POS 에 박아넣으면 됨.

좌표계: weapon_anchor 로컬(= 오른손 본 world pos+hpr 따라감), m. +Y 가 총신 전방.
"""
from direct.gui.OnscreenText import OnscreenText
from direct.task import Task
from panda3d.core import LineSegs, TextNode, Vec3

from weapon_config import RIFLE_MUZZLE_POS


class MuzzleMarker:
    """game(ZombieGame 인스턴스) 에 마커 노드 + 키바인드를 붙이는 튜닝 하네스."""

    def __init__(self, game, step=0.01):
        self.game = game
        self.node = None
        self.pos = list(RIFLE_MUZZLE_POS)
        self._text = None
        self.active = False   # 처음엔 비활성(숨김). L 로 토글.

        # L = 마커 토글 (하네스가 로드되면 항상 사용 가능).
        game.accept('l', self.toggle)

        anchor = getattr(game, 'weapon_anchor', None)
        rhj = getattr(game, 'right_hand_joint', None)
        if anchor is None or rhj is None or rhj.isEmpty():
            return

        ls = LineSegs()
        ls.setThickness(3)
        size = 0.05  # 5cm 축 길이 (m)
        for color, axis in (
            ((1, 0, 0, 1), Vec3(size, 0, 0)),   # X 빨강 (우)
            ((0, 1, 0, 1), Vec3(0, size, 0)),   # Y 초록 (총신 전방)
            ((0, 0, 1, 1), Vec3(0, 0, size)),   # Z 파랑 (위)
        ):
            ls.setColor(*color)
            ls.moveTo(0, 0, 0)
            ls.drawTo(axis)
        self.node = anchor.attachNewNode(ls.create())
        self.node.setLightOff()
        self.node.setDepthTest(False)   # 총에 가려도 보이게
        self.node.setBin('fixed', 90)
        self.node.setPos(*self.pos)
        self.node.hide()                # 비활성 시작

        binds = {
            'i': (1, step),  'k': (1, -step),   # ±Y (총신 전방)
            'h': (0, -step), 'j': (0, step),    # ±X (좌/우)
            'u': (2, step),  'o': (2, -step),   # ±Z (위아래)
        }
        for key, args in binds.items():
            game.accept(key, self._nudge, list(args))
            game.accept(f'{key}-repeat', self._nudge, list(args))
        game.accept('m', self._dump)
        print('[muzzle-marker] 로드됨. L=켜기/끄기, '
              'I/K=±Y(전후) H/J=±X(좌우) U/O=±Z(상하), M=값 출력', flush=True)

    def toggle(self):
        if self.node is None:
            return
        self.active = not self.active
        if self.active:
            self.node.show()
        else:
            self.node.hide()
        print(f'[muzzle-marker] {"활성" if self.active else "비활성"}', flush=True)

    def _nudge(self, idx, delta):
        if self.node is None or not self.active:
            return
        self.pos[idx] += delta
        self.node.setPos(*self.pos)
        # 소총 muzzle 즉시 갱신 — 레지스트리 + 활성 muzzle flash 시작점.
        d = self.game._weapons.get('rifle')
        if d is not None:
            d['muzzle'] = tuple(self.pos)
        mf = getattr(self.game, 'muzzle_flash', None)
        if mf is not None and self.game.weapon_name == 'rifle':
            mf.setPos(*self.pos)

    def _dump(self):
        if self.node is None or not self.active:
            return
        p = self.pos
        print(f'[muzzle-marker] RIFLE_MUZZLE_POS   = '
              f'({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f})', flush=True)
        txt = (f'RIFLE_MUZZLE_POS\n'
               f'({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f})')
        if self._text is not None:
            self._text.destroy()
        self._text = OnscreenText(
            text=txt, pos=(0, 0.2), scale=0.07,
            fg=(1, 1, 0, 1), bg=(0, 0, 0, 0.85),
            align=TextNode.ACenter, mayChange=False,
            parent=self.game.aspect2d,
        )
        token = self._text

        def _remove(task, t=token):
            if self._text is t:
                self._text.destroy()
                self._text = None
            return Task.done

        self.game.taskMgr.doMethodLater(3.0, _remove, 'muzzle_marker_dump_remove')
