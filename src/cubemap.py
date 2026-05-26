"""Equirectangular HDR → in-memory cubemap Texture.

Panda3D의 `TexturePool.load_cube_map`은 `path_#.ext` 형식의 6장 파일이나
DDS cubemap 단일 파일만 받는다. polyhaven 등 대부분의 HDRI 는 equirect (단일
2:1 파노라마) 라서 직접 변환해야 simplepbr 의 IBL + skybox 에 쓸 수 있다.

face 별 (s, t) → 방향 변환은 OpenGL `GL_ARB_texture_cube_map` spec 그대로:

  Major axis | sc | tc | ma
  +rx        | -rz | -ry | rx
  -rx        | +rz | -ry | rx
  +ry        | +rx | +rz | ry
  -ry        | +rx | -rz | ry
  +rz        | +rx | -ry | rz
  -rz        | -rx | -ry | rz

  s = (sc / |ma| + 1) / 2 ;  t = (tc / |ma| + 1) / 2

GL 의 t 는 bottom-up (t=0 이 텍스처 하단) 이지만 PNMImage 는 top-down
(y=0 이 상단) 이고 Panda3D 가 Texture upload 시 Y-flip 을 수행하므로,
PNMImage y=0 → GL t=1 로 대응. v_my = 2y/H − 1 (∈ [−1, +1], top→−1, bottom→+1)
라 두면 v_my = 1 − 2t 가 성립 → GL 공식의 `1-2t` 항을 v_my 로 치환할 수 있다.
이전 버전은 right/up/fwd basis 가 자의적으로 들어가 있어 skybox 의 좌우/상하
회전이 어긋났음. 본 버전은 spec 그대로.

Panda3D Z-up 좌표계에서 +X=오른쪽, +Y=앞, +Z=위.
"""

from __future__ import annotations

import math

from panda3d.core import Filename, PNMImage, Texture


# (right, up, fwd) — 면 내 픽셀(x, y)에 대해
#   u_my = 2*(x+0.5)/W − 1,  v_my = 2*(y+0.5)/H − 1
# 일 때 방향 = right*u_my + up*v_my + fwd. GL spec 의 (1-2t) 가 v_my 와 동일,
# (1-2s) 가 -u_my 와 동일하므로 아래 basis 는 직접 대입한 형태.
_FACE_BASES = [
    # +X face: direction = (1, 1-2t, 1-2s) = (1, v_my, -u_my)
    (( 0,  0, -1), ( 0,  1,  0), ( 1,  0,  0)),
    # -X face: (-1, 1-2t, 2s-1) = (-1, v_my, u_my)
    (( 0,  0,  1), ( 0,  1,  0), (-1,  0,  0)),
    # +Y face: (2s-1, 1, 2t-1) = (u_my, 1, -v_my)
    (( 1,  0,  0), ( 0,  0, -1), ( 0,  1,  0)),
    # -Y face: (2s-1, -1, 1-2t) = (u_my, -1, v_my)
    (( 1,  0,  0), ( 0,  0,  1), ( 0, -1,  0)),
    # +Z face: (2s-1, 1-2t, 1) = (u_my, v_my, 1)
    (( 1,  0,  0), ( 0,  1,  0), ( 0,  0,  1)),
    # -Z face: (1-2s, 1-2t, -1) = (-u_my, v_my, -1)
    ((-1,  0,  0), ( 0,  1,  0), ( 0,  0, -1)),
]


def equirect_to_cubemap(hdr_path, face_size: int = 128) -> Texture:
    """Equirect HDR 한 장을 읽어 6 face cubemap Texture 로 반환.

    face_size=256 기준 6 × 256² ≈ 393k 픽셀, atan2/asin 포함 한 픽셀당 ~수 µs →
    부팅 한 번 2~4 초. 결과 Texture 는 simplepbr.EnvMap(texture) 와 make_skybox()
    양쪽에 그대로 넘길 수 있음.
    """
    if not isinstance(hdr_path, Filename):
        hdr_path = Filename.fromOsSpecific(str(hdr_path))

    eq = PNMImage()
    if not eq.read(hdr_path):
        raise IOError(f"PNMImage cannot read HDR: {hdr_path}")

    eq_w = eq.getXSize()
    eq_h = eq.getYSize()
    inv2pi = 1.0 / (2.0 * math.pi)
    invpi = 1.0 / math.pi
    half_pi = math.pi * 0.5
    inv_face = 1.0 / face_size

    cubemap = Texture("sky_cubemap_equirect")
    cubemap.setupCubeMap(face_size, Texture.T_unsigned_byte, Texture.F_rgb)

    for face_idx, (right, up, fwd) in enumerate(_FACE_BASES):
        face = PNMImage(face_size, face_size, 3, 255)
        rx, ry, rz = right
        ux, uy, uz = up
        fx, fy, fz = fwd
        for y in range(face_size):
            v = (y + 0.5) * inv_face * 2.0 - 1.0
            for x in range(face_size):
                u = (x + 0.5) * inv_face * 2.0 - 1.0
                # Panda3D Z-up 방향 벡터.
                dx = rx * u + ux * v + fx
                dy = ry * u + uy * v + fy
                dz = rz * u + uz * v + fz
                length = math.sqrt(dx * dx + dy * dy + dz * dz)
                dx /= length
                dy /= length
                dz /= length

                # equirect sample 좌표:
                #   theta = atan2(dy, dx)  — +Z 축 기준 azimuth (∈ [−π, +π])
                #   phi   = asin(dz)        — XY 평면 기준 elevation (∈ [−π/2, +π/2])
                # equirect 표준 (polyhaven 등): 좌→우 = azimuth 0..2π, 상→하 = phi +π/2..−π/2
                theta = math.atan2(dy, dx)
                phi = math.asin(max(-1.0, min(1.0, dz)))

                eu = (theta + math.pi) * inv2pi * eq_w
                ev = (half_pi - phi) * invpi * eq_h

                ex = int(eu) % eq_w
                ey = max(0, min(eq_h - 1, int(ev)))
                color = eq.getXel(ex, ey)
                face.setXel(x, y, color)
        cubemap.load(face, face_idx, 0)

    return cubemap
