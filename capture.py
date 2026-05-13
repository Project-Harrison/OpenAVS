"""Headless screenshot capture for OpenAVS UI review.
Renders one frame of each screen state and exits.
Run: uv run python capture.py
"""
import json, os, sys, random
os.environ.setdefault('SDL_VIDEODRIVER', 'cocoa')

import pygame
pygame.init()

W, H = 1380, 800
S    = 1.0
def px(n): return int(n * S)

CHART_W = px(1000)
OX, OY  = px(500), px(400)

display = pygame.display.set_mode((W, H))
screen  = pygame.Surface((W, H))

os.makedirs('screenshots', exist_ok=True)

# ── shared fonts ──────────────────────────────────────────────────────────────
def sys_font(name, size, bold=False):
    return pygame.font.SysFont(name, size, bold=bold)

font = 'helvetica'


# ══════════════════════════════════════════════════════════════════════════════
# 1 — SPLASH
# ══════════════════════════════════════════════════════════════════════════════
def capture_splash():
    BG      = (14,  20,  38)
    CARD    = (22,  32,  58)
    CARD_BD = (42,  62,  100)
    ACCENT  = (40,  150, 225)
    WHITE   = (230, 240, 255)
    MUTED   = (95,  125, 165)
    HOVBG   = (32,  52,  90)
    DIVIDER = (38,  56,  88)
    INP_BG  = (28,  42,  68)
    FOOT_LN = (30,  44,  72)

    fn_title = sys_font(font, px(44), bold=True)
    fn_sub   = sys_font(font, px(11))
    fn_btn   = sys_font(font, px(13))
    fn_input = sys_font(font, px(14))
    fn_hdr   = sys_font(font, px(11), bold=True)
    fn_key   = sys_font(font, px(12))

    # load ports for realistic list
    try:
        with open('data/ports.json') as fh:
            ports = json.load(fh)
        ports.sort(key=lambda p: p['CITY'])
    except Exception:
        ports = [{'CITY': 'Example City', 'COUNTRY': 'Country',
                  'LATITUDE': 0.0, 'LONGITUDE': 0.0, 'STATE': ''}] * 8

    featured = random.sample(ports, min(8, len(ports)))

    # ── right panel first (card drives vertical anchor) ───────────────────────
    FOOTER_Y  = H - px(22)
    RP_W      = px(360)
    RP_CX     = W * 3 // 4
    RP_X      = RP_CX - RP_W // 2
    card_top  = px(92)

    _brand_ty    = card_top + px(26)
    _brand_gy    = _brand_ty   + px(44)
    _brand_liney = _brand_gy   + px(22)
    ctrl_hdr_y   = _brand_liney + px(30)
    CTRL_ROW_H   = px(36)
    ctrl_body_y  = ctrl_hdr_y  + px(28)

    CTRL_ROWS = [
        ('lr',  '',       'Course  ±15°'),
        ('ud',  '',       'Speed  ±2 kts'),
        ('txt', '[ ]',   'Sim Speed'),
        ('txt', 'SPACE',  'Pause / Resume'),
        ('txt', 'ENTER',  'Quit'),
    ]

    spd_hdr_y   = ctrl_body_y + len(CTRL_ROWS) * CTRL_ROW_H + px(44)
    SPD_BTN_W   = px(44)
    SPD_BTN_H   = px(40)
    SPD_BTN_GAP = px(6)
    SPD_Y_BTNS  = spd_hdr_y + px(28)
    _spd_total_w = 6 * SPD_BTN_W + 5 * SPD_BTN_GAP
    _spd_x0     = RP_CX - _spd_total_w // 2
    _spd_rects  = [pygame.Rect(_spd_x0 + i * (SPD_BTN_W + SPD_BTN_GAP),
                               SPD_Y_BTNS, SPD_BTN_W, SPD_BTN_H)
                   for i in range(6)]
    _SPEED_LABELS = ['¼×', '½×', '1×', '2×', '4×', '8×']
    _speed_idx = 2

    zoom_hdr_y  = SPD_Y_BTNS + SPD_BTN_H + px(44)
    ZOOM_BTN_W  = px(44)
    ZOOM_BTN_H  = px(40)
    zoom_btn_y  = zoom_hdr_y  + px(28)
    zoom = 12
    _zrect_minus = pygame.Rect(RP_CX - px(60), zoom_btn_y, ZOOM_BTN_W, ZOOM_BTN_H)
    _zrect_plus  = pygame.Rect(RP_CX + px(16), zoom_btn_y, ZOOM_BTN_W, ZOOM_BTN_H)
    card_bot    = zoom_btn_y + ZOOM_BTN_H + px(46)

    # ── left column, anchored to card top ─────────────────────────────────────
    LEFT_PAD  = px(44)
    INPUT_W   = W // 2 - px(72)
    INPUT_H   = px(44)
    BTN_W     = INPUT_W
    BTN_H     = px(38)
    BTN_GAP   = px(6)
    INPUT_X   = LEFT_PAD
    LC        = LEFT_PAD + INPUT_W // 2
    _TITLE_Y   = card_top + px(26)
    _TAGLINE_Y = _TITLE_Y  + px(52)
    _LABEL_Y   = _TAGLINE_Y + px(26)
    INPUT_Y    = _LABEL_Y   + px(24)
    BTN_X      = LEFT_PAD
    BTN_Y0     = INPUT_Y + INPUT_H + px(14)
    _list_bot  = BTN_Y0 + 8 * (BTN_H + BTN_GAP)

    KEY_COL_W = px(64)
    KEY_CX    = RP_X + KEY_COL_W // 2
    DESC_X    = RP_X + KEY_COL_W + px(10)
    ARR_SZ    = max(6, px(7))

    def _draw_lr(cx, cy, s, col):
        gap = px(4)
        re  = cx - gap // 2
        pygame.draw.polygon(screen, col, [(re-s, cy), (re, cy-s//2), (re, cy+s//2)])
        le  = cx + gap // 2
        pygame.draw.polygon(screen, col, [(le+s, cy), (le, cy-s//2), (le, cy+s//2)])

    def _draw_ud(cx, cy, s, col):
        gap  = px(4)
        cx_u = cx - gap//2 - s//2
        pygame.draw.polygon(screen, col, [(cx_u, cy-s//2), (cx_u-s//2, cy+s//2), (cx_u+s//2, cy+s//2)])
        cx_d = cx + gap//2 + s//2
        pygame.draw.polygon(screen, col, [(cx_d, cy+s//2), (cx_d-s//2, cy-s//2), (cx_d+s//2, cy-s//2)])

    screen.fill(BG)

    # left: context + action
    for _ui, _uline in enumerate([
        'OpenAVS simulates real port traffic using live AIS data.',
        'Each vessel navigates autonomously on a sea routing graph.',
        'Choose a port — you pilot one vessel through the environment.',
    ]):
        _us = fn_sub.render(_uline, True, MUTED)
        screen.blit(_us, (INPUT_X, _TITLE_Y + _ui * px(20)))

    pygame.draw.rect(screen, INP_BG, (INPUT_X, INPUT_Y, INPUT_W, INPUT_H), border_radius=px(5))
    pygame.draw.rect(screen, ACCENT, (INPUT_X, INPUT_Y, INPUT_W, INPUT_H), width=2, border_radius=px(5))
    ph = fn_input.render('type city or country…', True, MUTED)
    screen.blit(ph, (INPUT_X + px(10), INPUT_Y + (INPUT_H - fn_input.get_height()) // 2))

    for i, p in enumerate(featured[:8]):
        r      = pygame.Rect(BTN_X, BTN_Y0 + i * (BTN_H + BTN_GAP), BTN_W, BTN_H)  # noqa: E501
        active = (i == 0)
        pygame.draw.rect(screen, HOVBG if active else CARD, r, border_radius=px(4))
        pygame.draw.rect(screen, ACCENT if active else CARD_BD, r, width=1, border_radius=px(4))
        if active:
            pygame.draw.rect(screen, ACCENT, (r.x, r.y + px(4), px(3), r.height - px(8)), border_radius=px(2))
        state   = p.get('STATE', '')
        country = p.get('COUNTRY', '')
        label   = (f"{p['CITY']},  {state},  {country}" if state else f"{p['CITY']},  {country}")
        lat, lon = p['LATITUDE'], p['LONGITUDE']
        coord   = (f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'}  {abs(lon):.2f}°{'E' if lon >= 0 else 'W'}")
        lbl_s = fn_btn.render(label, True, ACCENT if active else WHITE)
        crd_s = fn_sub.render(coord, True, MUTED)
        screen.blit(lbl_s, (r.x + px(12), r.y + (BTN_H - lbl_s.get_height()) // 2))
        screen.blit(crd_s, (r.right - crd_s.get_width() - px(10), r.y + (BTN_H - crd_s.get_height()) // 2))

    # right card
    pygame.draw.rect(screen, CARD,
        (RP_X - px(12), card_top, RP_W + px(24), card_bot - card_top), border_radius=px(10))
    pygame.draw.rect(screen, CARD_BD,
        (RP_X - px(12), card_top, RP_W + px(24), card_bot - card_top), width=1, border_radius=px(10))

    # branding inside card
    bt = fn_title.render('OpenAVS', True, WHITE)
    screen.blit(bt, (RP_CX - bt.get_width() // 2, _brand_ty))
    bg = fn_btn.render('Open Autonomous Vessel Simulator', True, MUTED)
    screen.blit(bg, (RP_CX - bg.get_width() // 2, _brand_gy))
    pygame.draw.aaline(screen, DIVIDER, (RP_X, _brand_liney), (RP_X + RP_W, _brand_liney))

    ch = fn_hdr.render('CONTROLS', True, MUTED)
    screen.blit(ch, (RP_CX - ch.get_width() // 2, ctrl_hdr_y))
    pygame.draw.aaline(screen, DIVIDER, (RP_X, ctrl_hdr_y + px(16)), (RP_X + RP_W, ctrl_hdr_y + px(16)))

    for i, (kind, lbl, desc) in enumerate(CTRL_ROWS):
        ry  = ctrl_body_y + i * CTRL_ROW_H
        rcy = ry + CTRL_ROW_H // 2
        if kind == 'lr':
            _draw_lr(KEY_CX, rcy, ARR_SZ, ACCENT)
        elif kind == 'ud':
            _draw_ud(KEY_CX, rcy, ARR_SZ, ACCENT)
        else:
            ks = fn_key.render(lbl, True, ACCENT)
            screen.blit(ks, (KEY_CX - ks.get_width() // 2, rcy - ks.get_height() // 2))
        ds = fn_key.render(desc, True, WHITE)
        screen.blit(ds, (DESC_X, rcy - ds.get_height() // 2))

    pygame.draw.aaline(screen, DIVIDER, (RP_X, spd_hdr_y - px(4)), (RP_X + RP_W, spd_hdr_y - px(4)))
    sh = fn_hdr.render('SIM SPEED', True, MUTED)
    screen.blit(sh, (RP_CX - sh.get_width() // 2, spd_hdr_y))
    for i, r in enumerate(_spd_rects):
        active = (i == _speed_idx)
        bg  = ACCENT if active else DIVIDER
        txt = WHITE  if active else MUTED
        pygame.draw.rect(screen, bg, r, border_radius=px(4))
        if not active:
            pygame.draw.rect(screen, CARD_BD, r, width=1, border_radius=px(4))
        ls = fn_btn.render(_SPEED_LABELS[i], True, txt)
        screen.blit(ls, (r.centerx - ls.get_width() // 2, r.centery - ls.get_height() // 2))

    pygame.draw.aaline(screen, DIVIDER, (RP_X, zoom_hdr_y - px(4)), (RP_X + RP_W, zoom_hdr_y - px(4)))
    zh = fn_hdr.render('MAP ZOOM', True, MUTED)
    screen.blit(zh, (RP_CX - zh.get_width() // 2, zoom_hdr_y))
    for btn_r, lbl, at_lim in [(_zrect_minus, '−', False), (_zrect_plus, '+', False)]:
        pygame.draw.rect(screen, DIVIDER, btn_r, border_radius=px(4))
        pygame.draw.rect(screen, CARD_BD, btn_r, width=1, border_radius=px(4))
        ls = fn_hdr.render(lbl, True, WHITE)
        screen.blit(ls, (btn_r.centerx - ls.get_width() // 2, btn_r.centery - ls.get_height() // 2))
    zv = fn_btn.render(str(zoom), True, WHITE)
    screen.blit(zv, (RP_CX - zv.get_width() // 2, zoom_btn_y + (ZOOM_BTN_H - zv.get_height()) // 2))

    # footer
    ft_s = fn_sub.render(
        'projectharrison.org  ·  powered by saurabhn.com', True, MUTED)
    screen.blit(ft_s, (W // 2 - ft_s.get_width() // 2, FOOTER_Y - ft_s.get_height() // 2))

    display.blit(screen, (0, 0))
    pygame.display.flip()
    pygame.image.save(display, 'screenshots/splash.png')
    print('  saved screenshots/splash.png')


# ══════════════════════════════════════════════════════════════════════════════
# 2 — LOADING
# ══════════════════════════════════════════════════════════════════════════════
def capture_loading():
    _L_BG      = (10,  15,  32)
    _L_CARD    = (20,  30,  56)
    _L_CARD_BD = (38,  58,  98)
    _L_ACCENT  = (40,  150, 225)
    _L_WHITE   = (228, 238, 255)
    _L_MUTED   = (88,  118, 162)
    _L_BAR_BG  = (32,  48,  80)
    _L_DONE    = (35,  158, 82)
    _lfont     = sys_font(font, px(12))
    _lfont_hdr = sys_font(font, px(11), bold=True)
    _tfont     = sys_font(font, px(16), bold=True)
    _bfont     = sys_font(font, px(40), bold=True)
    BAR_W      = px(440)
    BAR_H      = px(10)
    CARD_W     = BAR_W + px(64)
    _ROW_H     = px(46)
    CARD_H     = px(80) + 4 * _ROW_H + px(32)
    CARD_X     = W // 2 - CARD_W // 2
    CARD_Y     = H // 2 - CARD_H // 2
    BAR_X      = CARD_X + px(32)

    screen.fill(_L_BG)

    # app branding
    bn = _bfont.render('OpenAVS', True, _L_WHITE)
    screen.blit(bn, (W // 2 - bn.get_width() // 2, CARD_Y - px(72)))
    st = _lfont.render('Open Autonomous Vessel Simulator', True, _L_MUTED)
    screen.blit(st, (W // 2 - st.get_width() // 2, CARD_Y - px(28)))

    # card
    pygame.draw.rect(screen, _L_CARD, (CARD_X, CARD_Y, CARD_W, CARD_H), border_radius=px(10))
    pygame.draw.rect(screen, _L_CARD_BD, (CARD_X, CARD_Y, CARD_W, CARD_H), width=1, border_radius=px(10))

    loc_s = _tfont.render('San Francisco, US', True, _L_WHITE)
    screen.blit(loc_s, (W // 2 - loc_s.get_width() // 2, CARD_Y + px(18)))
    pygame.draw.line(screen, _L_CARD_BD, (CARD_X + px(24), CARD_Y + px(50)),
                     (CARD_X + CARD_W - px(24), CARD_Y + px(50)), 1)

    def draw_bar(label, msg, pct, done, y):
        lbl_s = _lfont_hdr.render(label, True, _L_MUTED)
        screen.blit(lbl_s, (BAR_X, y))
        vc = _L_DONE if done else (_L_ACCENT if pct and pct > 0 else _L_MUTED)
        val_s = _lfont.render(msg, True, vc)
        screen.blit(val_s, (BAR_X + BAR_W - val_s.get_width(), y))
        by = y + px(20)
        pygame.draw.rect(screen, _L_BAR_BG, (BAR_X, by, BAR_W, BAR_H), border_radius=px(5))
        if done:
            pygame.draw.rect(screen, _L_DONE, (BAR_X, by, BAR_W, BAR_H), border_radius=px(5))
        elif pct and pct > 0:
            filled = max(px(8), int(BAR_W * min(pct, 1.0)))
            pygame.draw.rect(screen, _L_ACCENT, (BAR_X, by, filled, BAR_H), border_radius=px(5))

    row_y = CARD_Y + px(60)
    draw_bar('Chart tiles',      'Ready',       1.0, True,  row_y); row_y += _ROW_H
    draw_bar('Vessel positions', '247 vessels', 1.0, True,  row_y); row_y += _ROW_H
    draw_bar('Sea network',      'Scanning…',   0.4, False, row_y); row_y += _ROW_H
    draw_bar('Route planning',   'Waiting…',    0.0, False, row_y)

    display.blit(screen, (0, 0))
    pygame.display.flip()
    pygame.image.save(display, 'screenshots/loading.png')
    print('  saved screenshots/loading.png')


# ══════════════════════════════════════════════════════════════════════════════
# 3 — MAIN UI (chart + sidebar)
# ══════════════════════════════════════════════════════════════════════════════
def capture_main():
    lineColor  = (236, 236, 236)
    lightGrey  = (52,  58,  64)
    SB_BG      = (245, 246, 248)
    SB_BORDER  = (200, 202, 208)
    DIVIDER    = (210, 212, 218)
    BLACK      = (25,  25,  30)
    MUTED      = (110, 115, 125)
    YOU_BG     = (232, 242, 255)
    YOU_ACCENT = (6,   100, 220)
    CARD_BG    = (255, 255, 255)
    CARD_BD    = (218, 220, 226)
    CPA_WARN   = (210, 55,  55)
    SEA_BLUE   = (168, 204, 222)

    SB_START = CHART_W
    SB_L = SB_START + px(14)
    SB_R = W - px(10)

    F_SM  = max(9,  px(11))
    F_MD  = max(10, px(12))
    F_HDR = max(11, px(13))
    f = {
        'sm':  sys_font(font, F_SM),
        'md':  sys_font(font, F_MD),
        'hdr': sys_font(font, F_HDR),
    }

    # chart area
    screen.fill((255, 255, 255))
    # simulate sea tile roughly
    pygame.draw.rect(screen, SEA_BLUE, (0, 0, CHART_W, H))
    # add some land masses (placeholder rectangles)
    pygame.draw.rect(screen, (210, 200, 175), (50, 0, 250, 200))
    pygame.draw.rect(screen, (210, 200, 175), (600, 400, 380, 400))
    pygame.draw.rect(screen, (210, 200, 175), (0, 600, 150, 200))

    # grid lines
    for gy in (px(200), px(400), px(600)):
        pygame.draw.aaline(screen, lineColor, (0, gy), (CHART_W, gy))
    pygame.draw.aaline(screen, lineColor, (OX, 0), (OX, H))
    pygame.draw.circle(screen, lineColor, (OX, OY), px(200), width=1)

    # scale bar
    nm_px = 30
    pygame.draw.aaline(screen, lightGrey, (px(15), px(15)), (px(15) + nm_px, px(15)))
    pygame.draw.aaline(screen, lightGrey, (px(15), px(15)), (px(15), px(13)))
    pygame.draw.aaline(screen, lightGrey, (px(15) + nm_px, px(15)), (px(15) + nm_px, px(13)))
    scale_lbl = f['sm'].render('1 NM', True, lightGrey)
    screen.blit(scale_lbl, (px(15), px(20)))

    # attribution
    _attr = f['sm'].render('projectharrison.org  ·  powered by saurabhn.com', True, (180, 190, 210))
    screen.blit(_attr, (px(10), H - _attr.get_height() - px(8)))

    # fake vessels
    # user vessel (blue dot + leading circle)
    pygame.draw.circle(screen, (6, 100, 220), (OX, OY), px(5))
    pygame.draw.circle(screen, (255, 255, 255), (OX + 80, OY - 40), px(6))
    pygame.draw.circle(screen, (6, 100, 220), (OX + 80, OY - 40), px(5))
    # AIS vessels
    AIS_COLOR = (255, 200, 60)
    for ax, ay in [(320, 280), (580, 350), (720, 500), (200, 520), (450, 180)]:
        pygame.draw.circle(screen, AIS_COLOR, (ax, ay), px(3))
        pygame.draw.circle(screen, (180, 130, 20), (ax, ay), px(3), 1)
        pygame.draw.circle(screen, (255, 255, 255), (ax + 20, ay - 15), px(4))
        pygame.draw.circle(screen, (255, 150, 190), (ax + 20, ay - 15), px(3))

    # sidebar
    pygame.draw.rect(screen, SB_BG, (SB_START, 0, W - SB_START, H))
    pygame.draw.aaline(screen, SB_BORDER, (SB_START, 0), (SB_START, H))

    def draw_divider(y):
        pygame.draw.aaline(screen, DIVIDER, (SB_L - px(4), y), (SB_R, y))
        return y + px(8)

    def draw_row(label, value, y, val_color=None):
        screen.blit(f['sm'].render(label, True, MUTED), (SB_L + px(4), y))
        screen.blit(f['md'].render(value, True, val_color or BLACK), (SB_L + px(72), y))
        return y + px(17)

    # OpenAVS branding at top of sidebar
    y = px(10)
    _sb_title_f = pygame.font.SysFont(font, max(11, px(13)), bold=True)
    _app_surf   = _sb_title_f.render('OpenAVS', True, (6, 100, 220))
    screen.blit(_app_surf, (SB_L, y))
    y += px(18)
    y = draw_divider(y)

    screen.blit(f['hdr'].render('CONTROLS', True, (75, 80, 92)), (SB_L, y))
    y += px(14)

    KEY_COL  = (75, 80, 92)
    DESC_OFF = SB_L + px(56)
    ROW_H    = px(16)

    def draw_lr_arrows(x, y_off, color):
        s   = max(5, px(5))
        gap = max(6, px(6))
        pygame.draw.polygon(screen, color, [(x, y_off + s//2), (x+s, y_off), (x+s, y_off+s)])
        x2 = x + s + gap
        pygame.draw.polygon(screen, color, [(x2+s, y_off+s//2), (x2, y_off), (x2, y_off+s)])

    def draw_ud_arrows(x, y_off, color):
        s   = max(5, px(5))
        gap = max(6, px(6))
        pygame.draw.polygon(screen, color, [(x+s//2, y_off), (x, y_off+s), (x+s, y_off+s)])
        x2 = x + s + gap
        pygame.draw.polygon(screen, color, [(x2+s//2, y_off+s), (x2, y_off), (x2+s, y_off)])

    draw_lr_arrows(SB_L + px(4), y + px(3), KEY_COL)
    screen.blit(f['sm'].render('Course  ±15°', True, BLACK), (DESC_OFF, y))
    y += ROW_H
    draw_ud_arrows(SB_L + px(4), y + px(3), KEY_COL)
    screen.blit(f['sm'].render('Speed   ±2 kts', True, BLACK), (DESC_OFF, y))
    y += ROW_H
    for key_lbl, desc in [('SPACE', 'Pause / Resume'), ('ENTER', 'Quit'), ('[ ]', 'Sim  1×')]:
        screen.blit(f['sm'].render(key_lbl, True, KEY_COL), (SB_L + px(4), y))
        screen.blit(f['sm'].render(desc, True, BLACK), (DESC_OFF, y))
        y += ROW_H

    y += px(5)
    screen.blit(f['sm'].render('STATUS', True, MUTED), (SB_L + px(4), y))
    screen.blit(f['hdr'].render('RUNNING', True, (35, 140, 55)), (SB_L + px(52), y - px(1)))
    spd_surf = f['sm'].render('1×', True, MUTED)
    screen.blit(spd_surf, (SB_R - spd_surf.get_width(), y))
    y += px(16)
    y = draw_divider(y)
    y += px(6)

    # user vessel card
    card_h = px(86)
    card_x, card_w = SB_L - px(6), SB_R - SB_L + px(8)
    pygame.draw.rect(screen, YOU_BG, (card_x, y, card_w, card_h), border_radius=px(5))
    pygame.draw.rect(screen, YOU_ACCENT, (card_x, y, card_w, card_h), width=1, border_radius=px(5))
    pygame.draw.rect(screen, YOU_ACCENT, (card_x, y + px(4), px(4), card_h - px(8)), border_radius=px(2))
    row_y = y + px(8)
    pygame.draw.rect(screen, (6, 100, 220), (SB_L + px(2), row_y + px(1), px(10), px(10)), border_radius=px(2))
    screen.blit(f['hdr'].render('AUG/V TargetBot', True, YOU_ACCENT), (SB_L + px(16), row_y - px(1)))
    badge = f['sm'].render('YOU', True, (255, 255, 255))
    bw = badge.get_width() + px(8)
    bx = SB_R - bw - px(2)
    pygame.draw.rect(screen, YOU_ACCENT, (bx, row_y + px(1), bw, px(13)), border_radius=px(3))
    screen.blit(badge, (bx + px(4), row_y + px(1)))
    row_y += px(18)
    pygame.draw.aaline(screen, DIVIDER, (SB_L - px(2), row_y), (SB_R, row_y))
    row_y += px(6)
    row_y = draw_row('Position', '37.785°N  122.421°W', row_y)
    row_y = draw_row('Course', '045.0°T', row_y)
    row_y = draw_row('Speed', '12.0 kts', row_y)
    y = row_y + px(10)

    # AIS contacts header
    screen.blit(f['hdr'].render('AIS CONTACTS', True, (75, 80, 92)), (SB_L, y))
    y += px(14)
    y = draw_divider(y)

    ais_contacts = [
        ('MAERSK TIGER', (255, 150, 190), '0.42 NM', '8 min', False),
        ('BULK CARRIER', (255, 150, 190), '1.18 NM', '22 min', False),
        ('SANCTIONED V', (220, 50, 50),   '2.50 NM', '45 min', True),
    ]
    for name, ais_col, cpa_str, tcpa_str, sanctioned in ais_contacts:
        card_h = px(86) + px(34)
        pygame.draw.rect(screen, CARD_BG, (card_x, y, card_w, card_h), border_radius=px(5))
        pygame.draw.rect(screen, CARD_BD, (card_x, y, card_w, card_h), width=1, border_radius=px(5))
        row_y = y + px(8)
        pygame.draw.rect(screen, ais_col, (SB_L + px(2), row_y + px(1), px(10), px(10)), border_radius=px(2))
        screen.blit(f['hdr'].render(name[:16], True, BLACK), (SB_L + px(16), row_y - px(1)))
        row_y += px(18)
        pygame.draw.aaline(screen, DIVIDER, (SB_L - px(2), row_y), (SB_R, row_y))
        row_y += px(6)
        row_y = draw_row('Position', '37.831°N  122.380°W', row_y)
        row_y = draw_row('Course', '270.0°T', row_y)
        row_y = draw_row('Speed', '8.5 kts', row_y)
        pygame.draw.aaline(screen, DIVIDER, (SB_L, row_y), (SB_R, row_y))
        row_y += px(5)
        screen.blit(f['sm'].render(f'CPA  {name[:14]}', True, MUTED), (SB_L + px(4), row_y))
        cpa_warn_col = CPA_WARN if float(cpa_str.split()[0]) < 1.0 else BLACK
        cpa_surf = f['md'].render(cpa_str, True, cpa_warn_col)
        screen.blit(cpa_surf, (SB_R - cpa_surf.get_width() - px(2), row_y))
        row_y += px(14)
        screen.blit(f['sm'].render('TCPA', True, MUTED), (SB_L + px(4), row_y))
        tcpa_surf = f['md'].render(tcpa_str, True, BLACK)
        screen.blit(tcpa_surf, (SB_R - tcpa_surf.get_width() - px(2), row_y))
        y = row_y + px(24)

    # back button
    BACK_BTN = pygame.Rect(SB_L - px(6), H - px(44), SB_R - SB_L + px(12), px(32))
    pygame.draw.rect(screen, CARD_BD, BACK_BTN, border_radius=px(5))
    pygame.draw.rect(screen, (200, 202, 208), BACK_BTN, width=1, border_radius=px(5))
    back_lbl = f['sm'].render('← Change Location', True, MUTED)
    screen.blit(back_lbl, (BACK_BTN.centerx - back_lbl.get_width() // 2,
                            BACK_BTN.centery - back_lbl.get_height() // 2))

    display.blit(screen, (0, 0))
    pygame.display.flip()
    pygame.image.save(display, 'screenshots/main.png')
    print('  saved screenshots/main.png')


# ── run all captures ──────────────────────────────────────────────────────────
print('Capturing splash…')
capture_splash()
pygame.time.delay(100)

print('Capturing loading…')
capture_loading()
pygame.time.delay(100)

print('Capturing main UI…')
capture_main()
pygame.time.delay(100)

pygame.quit()
print('Done.')
