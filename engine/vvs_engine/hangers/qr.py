"""En liten QR-kodare (ISO/IEC 18004): byte-läge, felrättning M, version 1-9 (upp till 180 tecken).

Räcker för etiketternas länk till hängaren. Ingen extern modul: Reed-Solomon över GF(256), placering, de åtta
maskerna med straffpoängen ur standarden, format- och versionsinformation.
"""
from __future__ import annotations

# version: (ec-kodord per block, [(antal block, dataord per block), ...])
_EC_M = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
         6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)])}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46]}
_REMAINDER = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 0, 8: 0, 9: 0}

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs(data: list[int], n: int) -> list[int]:
    g = [1]
    for i in range(n):
        g = [a ^ _mul(b, _EXP[i]) for a, b in zip(g + [0], [0] + g)]
    rem = [0] * n
    for d in data:
        f = d ^ rem[0]
        rem = rem[1:] + [0]
        for j in range(n):
            rem[j] ^= _mul(g[j + 1], f)
    return rem


def _bch(value: int, poly: int, bits: int) -> int:
    v = value << bits
    top = poly.bit_length()
    while v.bit_length() >= top:
        v ^= poly << (v.bit_length() - top)
    return (value << bits) | v


def _codewords(data: bytes) -> tuple[int, list[int]]:
    for ver, (ec, groups) in _EC_M.items():
        cap = sum(n * k for n, k in groups)
        if len(data) + 2 <= cap:          # 4 bitar läge + 8 bitar längd + data + slut
            break
    else:
        raise ValueError("för lång text för en QR-kod version 9 (högst 180 byte)")
    bits = [0, 1, 0, 0] + [int(b) for b in f"{len(data):08b}"]
    for byte in data:
        bits += [int(b) for b in f"{byte:08b}"]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = [0xEC, 0x11]
    while len(words) < cap:
        words.append(pad[(len(words) - len(bits) // 8) % 2])
    blocks, i = [], 0
    for n, k in groups:
        for _ in range(n):
            blocks.append(words[i:i + k])
            i += k
    eccs = [_rs(b, ec) for b in blocks]
    out = []
    for j in range(max(len(b) for b in blocks)):
        out += [b[j] for b in blocks if j < len(b)]
    for j in range(ec):
        out += [e[j] for e in eccs]
    return ver, out


def _base(ver: int):
    n = 17 + 4 * ver
    m = [[None] * n for _ in range(n)]

    def finder(r, c):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r + dr, c + dc
                if 0 <= rr < n and 0 <= cc < n:
                    on = 0 <= dr <= 6 and 0 <= dc <= 6 and (dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4))
                    m[rr][cc] = 1 if on else 0
    finder(0, 0)
    finder(0, n - 7)
    finder(n - 7, 0)
    for i in range(8, n - 8):
        m[6][i] = m[i][6] = 1 if i % 2 == 0 else 0
    pos = _ALIGN[ver]
    for r in pos:
        for c in pos:
            if (r < 9 and c < 9) or (r < 9 and c > n - 10) or (r > n - 10 and c < 9):
                continue                                  # under en sökmarkering
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    m[r + dr][c + dc] = 1 if max(abs(dr), abs(dc)) != 1 else 0
    m[n - 8][8] = 1                                       # mörk modul
    reserved = [[v is not None for v in row] for row in m]
    for i in range(9):                                    # formatinformation
        reserved[8][i] = reserved[i][8] = True
    for i in range(8):
        reserved[8][n - 1 - i] = reserved[n - 1 - i][8] = True
    if ver >= 7:
        for i in range(6):
            for j in range(3):
                reserved[i][n - 11 + j] = reserved[n - 11 + j][i] = True
    return m, reserved


_MASKS = [lambda r, c: (r + c) % 2 == 0, lambda r, c: r % 2 == 0, lambda r, c: c % 3 == 0,
          lambda r, c: (r + c) % 3 == 0, lambda r, c: (r // 2 + c // 3) % 2 == 0,
          lambda r, c: (r * c) % 2 + (r * c) % 3 == 0, lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
          lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0]


def _penalty(m) -> int:
    n = len(m)
    p = 0
    for grid in (m, [list(x) for x in zip(*m)]):
        for row in grid:
            run, prev = 0, None
            for v in row:
                if v == prev:
                    run += 1
                else:
                    if run >= 5:
                        p += run - 2
                    run, prev = 1, v
            if run >= 5:
                p += run - 2
            s = "".join(map(str, row))
            p += 40 * (s.count("10111010000") + s.count("00001011101"))
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                p += 3
    dark = sum(map(sum, m))
    p += 10 * (abs(dark * 20 - n * n * 10) // (n * n))
    return p


def matrix(text: str) -> list[list[int]]:
    """QR-koden som en kvadrat av 0/1 (utan tyst zon)."""
    ver, words = _codewords(text.encode("utf-8"))
    bits = [int(b) for w in words for b in f"{w:08b}"] + [0] * _REMAINDER[ver]
    base, reserved = _base(ver)
    n = len(base)
    order = []
    c, up = n - 1, True
    while c > 0:
        if c == 6:
            c -= 1
        for r in (range(n - 1, -1, -1) if up else range(n)):
            for cc in (c, c - 1):
                if not reserved[r][cc]:
                    order.append((r, cc))
        up = not up
        c -= 2
    best = None
    for k, mask in enumerate(_MASKS):
        m = [row[:] for row in base]
        for (r, cc), b in zip(order, bits):
            m[r][cc] = b ^ (1 if mask(r, cc) else 0)
        for r, cc in order[len(bits):]:
            m[r][cc] = 1 if mask(r, cc) else 0
        fmt = _bch((0b00 << 3) | k, 0x537, 10) ^ 0x5412
        fb = [(fmt >> i) & 1 for i in range(15)]          # bit 0 = minst signifikant
        for i in range(6):
            m[i][8] = fb[i]
        m[7][8], m[8][8], m[8][7] = fb[6], fb[7], fb[8]
        for i in range(9, 15):
            m[8][14 - i] = fb[i]
        for i in range(8):
            m[8][n - 1 - i] = fb[i]
        for i in range(8, 15):
            m[n - 15 + i][8] = fb[i]
        if ver >= 7:
            vb = _bch(ver, 0x1F25, 12)
            for i in range(18):
                b = (vb >> i) & 1
                m[i // 3][n - 11 + i % 3] = b
                m[n - 11 + i % 3][i // 3] = b
        for r in range(n):
            for cc in range(n):
                if m[r][cc] is None:
                    m[r][cc] = 0
        score = _penalty(m)
        if best is None or score < best[0]:
            best = (score, m)
    return best[1]


def svg(text: str, size_mm: float = 30.0) -> str:
    m = matrix(text)
    n = len(m) + 8
    rects = "".join(f'<rect x="{c + 4}" y="{r + 4}" width="1" height="1"/>' for r, row in enumerate(m) for c, v in enumerate(row) if v)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{size_mm}mm" height="{size_mm}mm" '
            f'shape-rendering="crispEdges"><rect width="{n}" height="{n}" fill="#fff"/><g fill="#000">{rects}</g></svg>')
