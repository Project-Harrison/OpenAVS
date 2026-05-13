import json
import math
import random
import time
from concurrent.futures import ThreadPoolExecutor as _PoolEx, as_completed as _ac
from . import navigation
from . import tiles
from . import ais_vessels
from . import graph as _graph_module
from . import paths as _paths
from shapely.geometry import Point as _ShapePoint
from shapely.strtree import STRtree as _ShapeSTRtree
import pygame
pygame.init()


# ── port loader ───────────────────────────────────────────────────────────────

def _load_ports(path):
    try:
        with open(path) as fh:
            data = json.load(fh)
        seen, ports = set(), []
        for p in data:
            lat, lon = p.get('LATITUDE'), p.get('LONGITUDE')
            if lat is None or lon is None:
                continue
            key = (p['CITY'].strip().lower(), p.get('COUNTRY', '').strip().lower())
            if key not in seen:
                seen.add(key)
                ports.append(p)
        ports.sort(key=lambda p: p['CITY'])
        print(f'  ports: {len(ports)} loaded')
        return ports
    except Exception as e:
        print(f'  ports: {e}')
        return []


# ── live AIS CPA engine ───────────────────────────────────────────────────────

def _compute_live_cpa(live_ais, ctrl):
    """Dead-reckon each live AIS vessel against ctrl for 60 minutes; store CPA/TCPA."""
    for la in live_ais:
        try:
            if navigation.distanceGreat(la['pos'], ctrl.p1) > 25:
                la['cpa'] = None
                la['tcpa'] = None
                continue
        except Exception:
            continue
        p1_dr, p2_dr = ctrl.p1, la['pos']
        cpas = []
        for i in range(1, 61):
            p1_dr = navigation.arrival(p1_dr, ctrl.course, ctrl.speed / 60)
            p2_dr = navigation.arrival(p2_dr, la.get('heading', la['course']), la['speed'] / 60)
            try:
                cpas.append(navigation.distanceMiddle(p1_dr, p2_dr))
            except Exception:
                cpas.append(9999.0)
        if cpas:
            la['cpa']  = min(cpas)
            la['tcpa'] = cpas.index(la['cpa']) + 1


# ── CPA/TCPA math (flat-earth, positions in nm, velocities in nm/min) ─────────

def _cpa_tcpa_nm(p1x, p1y, v1x, v1y, p2x, p2y, v2x, v2y):
    """Returns (cpa_nm, tcpa_min). Negative tcpa means already past CPA."""
    rx, ry = p2x - p1x, p2y - p1y
    vx, vy = v2x - v1x, v2y - v1y
    vv = vx * vx + vy * vy
    if vv < 1e-12:
        return math.sqrt(rx * rx + ry * ry), 0.0
    tcpa = -(rx * vx + ry * vy) / vv
    if tcpa < 0:
        return math.sqrt(rx * rx + ry * ry), tcpa
    return math.sqrt((rx + vx * tcpa) ** 2 + (ry + vy * tcpa) ** 2), tcpa


# ── water centering ───────────────────────────────────────────────────────────

def _recenter_on_water(surf, origin, NS, OX, OY, CHART_W, H, max_frac=0.45):
    """
    Shift the map origin toward the centroid of sea pixels in surf.
    Clamped so the original port pixel stays within max_frac of the viewport.
    Returns the potentially adjusted (lat, lon) origin.
    """
    step = 8
    cx_sum, cy_sum, n_sea = 0, 0, 0
    n_total = 0
    for x in range(0, CHART_W, step):
        for y in range(0, H, step):
            r, g, b = surf.get_at((x, y))[:3]
            n_total += 1
            if b > 140 and b > r and (b - r) > 20:
                cx_sum += x
                cy_sum += y
                n_sea  += 1

    if n_sea == 0:
        return origin
    sea_fraction = n_sea / max(1, n_total)
    if sea_fraction > 0.90:
        return origin  # already mostly sea — no adjustment needed

    sea_cx = cx_sum / n_sea
    sea_cy = cy_sum / n_sea

    # dx/dy: how far to shift the chart (screen pixels)
    dx = sea_cx - OX
    dy = sea_cy - OY

    max_dx = CHART_W * max_frac
    max_dy = H        * max_frac
    dx = max(-max_dx, min(max_dx, dx))
    dy = max(-max_dy, min(max_dy, dy))

    if abs(dx) < 20 and abs(dy) < 20:
        return origin

    dlat = -dy / NS   # y increases downward, lat northward
    dlon =  dx / NS   # x increases eastward
    return (origin[0] + dlat, origin[1] + dlon)


# ── API key dialog ────────────────────────────────────────────────────────────

def _request_api_key(display, screen, W, H, px):
    BG      = (14,  20,  38)
    CARD    = (22,  32,  58)
    CARD_BD = (42,  62,  100)
    ACCENT  = (40,  150, 225)
    WHITE   = (230, 240, 255)
    MUTED   = (95,  125, 165)
    INP_BG  = (28,  42,  68)
    INP_BD  = (60,  90,  140)
    ERR_COL = (220, 80,  80)

    fn_title = pygame.font.SysFont('helvetica', px(28), bold=True)
    fn_sub   = pygame.font.SysFont('helvetica', px(12))
    fn_inp   = pygame.font.SysFont('helvetica', px(14))
    fn_btn   = pygame.font.SysFont('helvetica', px(13), bold=True)
    fn_attr  = pygame.font.SysFont('helvetica', px(30), bold=True)

    CARD_W  = min(px(520), W - px(80))
    CARD_H  = px(300)
    CARD_X  = (W - CARD_W) // 2
    CARD_Y  = (H - CARD_H) // 2

    INP_PAD  = px(20)
    INP_X    = CARD_X + INP_PAD
    INP_W    = CARD_W - 2 * INP_PAD
    INP_H    = px(42)
    INP_Y    = CARD_Y + px(130)

    BTN_W   = (INP_W - px(12)) // 2
    BTN_H   = px(40)
    BTN_Y   = INP_Y + INP_H + px(20)
    BTN_SAVE_X = INP_X
    BTN_SKIP_X = INP_X + BTN_W + px(12)

    rect_inp      = pygame.Rect(INP_X, INP_Y, INP_W, INP_H)
    rect_save     = pygame.Rect(BTN_SAVE_X, BTN_Y, BTN_W, BTN_H)
    rect_skip     = pygame.Rect(BTN_SKIP_X, BTN_Y, BTN_W, BTN_H)

    key_text  = ''
    cursor_on = True
    last_blink = time.monotonic()
    show_error = False
    active     = True

    while active:
        dt = time.monotonic()
        if dt - last_blink > 0.55:
            cursor_on  = not cursor_on
            last_blink = dt

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_RETURN:
                    if key_text.strip():
                        _save_api_key(key_text.strip())
                    active = False
                elif ev.key == pygame.K_ESCAPE:
                    active = False
                elif ev.key == pygame.K_BACKSPACE:
                    key_text = key_text[:-1]
                    show_error = False
                else:
                    if ev.unicode and ev.unicode.isprintable():
                        key_text += ev.unicode
                        show_error = False
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                mx, my = ev.pos
                if rect_save.collidepoint(mx, my):
                    if key_text.strip():
                        _save_api_key(key_text.strip())
                        active = False
                    else:
                        show_error = True
                elif rect_skip.collidepoint(mx, my):
                    active = False

        screen.fill(BG)

        # card
        pygame.draw.rect(screen, CARD,    pygame.Rect(CARD_X, CARD_Y, CARD_W, CARD_H), border_radius=px(10))
        pygame.draw.rect(screen, CARD_BD, pygame.Rect(CARD_X, CARD_Y, CARD_W, CARD_H), width=1, border_radius=px(10))

        # title
        t_title = fn_title.render('AIS API Key', True, WHITE)
        screen.blit(t_title, (CARD_X + (CARD_W - t_title.get_width()) // 2, CARD_Y + px(28)))

        # subtitle
        lines = [
            'Live AIS vessel data requires a Saurabhn API key.',
            'Get yours free at  saurabhn.com',
        ]
        for i, ln in enumerate(lines):
            ts = fn_sub.render(ln, True, MUTED)
            screen.blit(ts, (CARD_X + (CARD_W - ts.get_width()) // 2, CARD_Y + px(72) + i * px(18)))

        # input box
        inp_col = ERR_COL if show_error else (ACCENT if rect_inp.collidepoint(pygame.mouse.get_pos()) else INP_BD)
        pygame.draw.rect(screen, INP_BG,  rect_inp, border_radius=px(6))
        pygame.draw.rect(screen, inp_col, rect_inp, width=2, border_radius=px(6))

        display_text = key_text + ('|' if cursor_on else ' ')
        t_key = fn_inp.render(display_text or ' ', True, WHITE)
        screen.blit(t_key, (rect_inp.x + px(10), rect_inp.y + (INP_H - t_key.get_height()) // 2))

        if not key_text:
            t_ph = fn_inp.render('Paste your API key here…', True, MUTED)
            screen.blit(t_ph, (rect_inp.x + px(10), rect_inp.y + (INP_H - t_ph.get_height()) // 2))

        if show_error:
            t_err = fn_sub.render('Please enter a key or click Skip.', True, ERR_COL)
            screen.blit(t_err, (INP_X, BTN_Y - px(16)))

        # Save button
        mx, my = pygame.mouse.get_pos()
        save_col = (60, 170, 255) if rect_save.collidepoint(mx, my) else ACCENT
        pygame.draw.rect(screen, save_col, rect_save, border_radius=px(6))
        t_save = fn_btn.render('Save & Continue', True, (255, 255, 255))
        screen.blit(t_save, (rect_save.centerx - t_save.get_width() // 2,
                              rect_save.centery - t_save.get_height() // 2))

        # Skip button
        skip_col = (38, 56, 88) if rect_skip.collidepoint(mx, my) else (28, 42, 68)
        pygame.draw.rect(screen, skip_col, rect_skip, border_radius=px(6))
        pygame.draw.rect(screen, CARD_BD,  rect_skip, width=1, border_radius=px(6))
        t_skip = fn_btn.render('Skip for now', True, MUTED)
        screen.blit(t_skip, (rect_skip.centerx - t_skip.get_width() // 2,
                              rect_skip.centery - t_skip.get_height() // 2))

        # attribution
        t_ph = fn_attr.render('projectharrison.org', True, WHITE)
        t_sr = fn_attr.render('saurabhn.com',        True, MUTED)
        _ay2 = H - px(14)
        _ay1 = _ay2 - t_sr.get_height() - px(8)
        screen.blit(t_ph, (px(20), _ay1))
        screen.blit(t_sr, (px(20), _ay2))

        display.blit(screen, (0, 0))
        pygame.display.flip()


def _save_api_key(key: str) -> None:
    path = _paths.config_path()
    try:
        with open(path) as fh:
            cfg = json.load(fh)
    except Exception:
        cfg = {}
    cfg['SAURAHBN_AIS'] = key
    with open(path, 'w') as fh:
        json.dump(cfg, fh, indent=2)
    print(f'  [ais] API key saved to {path}')


# ── location picker ───────────────────────────────────────────────────────────

def _select_location(display, screen, W, H, px, ports, initial_speed_idx=2):
    # ── colors (dark navy theme) ──────────────────────────────────────────────
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

    fn_sub   = pygame.font.SysFont('helvetica', px(11))
    fn_btn   = pygame.font.SysFont('helvetica', px(13))
    fn_input = pygame.font.SysFont('helvetica', px(14))
    fn_hdr   = pygame.font.SysFont('helvetica', px(11), bold=True)
    fn_key   = pygame.font.SysFont('helvetica', px(12))
    fn_attr  = pygame.font.SysFont('helvetica', px(30), bold=True)

    _SPEED_LABELS_LOC = ['¼×', '½×', '1×', '2×', '4×', '8×']
    _speed_idx = initial_speed_idx

    _random_featured = random.sample(ports, min(8, len(ports)))

    def _filter(q):
        if not q:
            return _random_featured[:8]
        ql = q.lower()
        return [p for p in ports
                if ql in p['CITY'].lower() or ql in p['COUNTRY'].lower()][:8]

    query     = ''
    filtered  = _filter('')
    sel_idx   = 0
    cursor_on = True
    last_blink = time.monotonic()

    fn_title = pygame.font.SysFont('helvetica', px(44), bold=True)

    # ── layout — right panel first (card drives vertical anchor) ──────────────
    FOOTER_Y  = H - px(22)
    RP_W      = px(360)
    RP_CX     = W * 3 // 4
    RP_X      = RP_CX - RP_W // 2
    card_top  = px(92)         # card vertically centred

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

    zoom_hdr_y  = SPD_Y_BTNS + SPD_BTN_H + px(44)
    ZOOM_BTN_W  = px(44)
    ZOOM_BTN_H  = px(40)
    zoom_btn_y  = zoom_hdr_y  + px(28)
    ZOOM_MIN    = 8
    ZOOM_MAX    = 17
    zoom        = 12
    _zrect_minus = pygame.Rect(RP_CX - px(60), zoom_btn_y, ZOOM_BTN_W, ZOOM_BTN_H)
    _zrect_plus  = pygame.Rect(RP_CX + px(16), zoom_btn_y, ZOOM_BTN_W, ZOOM_BTN_H)
    card_bot    = zoom_btn_y + ZOOM_BTN_H + px(46)   # content-driven height

    # ── layout — left column, anchored to card top ────────────────────────────
    LEFT_PAD  = px(44)
    INPUT_W   = W // 2 - px(72)
    INPUT_H   = px(44)
    BTN_W     = INPUT_W
    BTN_H     = px(38)
    BTN_GAP   = px(6)
    INPUT_X   = LEFT_PAD
    LC        = LEFT_PAD + INPUT_W // 2
    _TITLE_Y   = card_top + px(26)   # align left title with card branding
    _TAGLINE_Y = _TITLE_Y  + px(52)
    _LABEL_Y   = _TAGLINE_Y + px(26)
    INPUT_Y    = _LABEL_Y   + px(24)
    BTN_X      = LEFT_PAD
    BTN_Y0     = INPUT_Y + INPUT_H + px(14)
    _list_bot  = BTN_Y0 + 8 * (BTN_H + BTN_GAP)

    # ── polygon arrow helpers ─────────────────────────────────────────────────
    KEY_COL_W = px(64)
    KEY_CX    = RP_X + KEY_COL_W // 2
    DESC_X    = RP_X + KEY_COL_W + px(10)
    ARR_SZ    = max(6, px(7))

    def _draw_lr(cx, cy, s, col):
        gap = px(4)
        re  = cx - gap // 2
        pygame.draw.polygon(screen, col, [
            (re - s, cy), (re, cy - s // 2), (re, cy + s // 2)])
        le  = cx + gap // 2
        pygame.draw.polygon(screen, col, [
            (le + s, cy), (le, cy - s // 2), (le, cy + s // 2)])

    def _draw_ud(cx, cy, s, col):
        gap  = px(4)
        cx_u = cx - gap // 2 - s // 2
        pygame.draw.polygon(screen, col, [
            (cx_u,            cy - s // 2),
            (cx_u - s // 2,   cy + s // 2),
            (cx_u + s // 2,   cy + s // 2)])
        cx_d = cx + gap // 2 + s // 2
        pygame.draw.polygon(screen, col, [
            (cx_d,            cy + s // 2),
            (cx_d - s // 2,   cy - s // 2),
            (cx_d + s // 2,   cy - s // 2)])

    selected = None
    while selected is None:
        now = time.monotonic()
        if now - last_blink > 0.5:
            cursor_on = not cursor_on
            last_blink = now

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_BACKSPACE:
                    query = query[:-1]
                    filtered = _filter(query)
                    sel_idx = 0
                elif ev.key == pygame.K_RETURN and filtered:
                    selected = filtered[sel_idx]
                elif ev.key == pygame.K_UP:
                    sel_idx = max(0, sel_idx - 1)
                elif ev.key == pygame.K_DOWN:
                    sel_idx = min(len(filtered) - 1, sel_idx + 1)
                elif ev.key == pygame.K_ESCAPE:
                    query = ''
                    filtered = _filter('')
                    sel_idx = 0
                elif ev.unicode and ev.unicode.isprintable():
                    query += ev.unicode
                    filtered = _filter(query)
                    sel_idx = 0
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if _zrect_minus.collidepoint(ev.pos):
                    zoom = max(ZOOM_MIN, zoom - 1)
                if _zrect_plus.collidepoint(ev.pos):
                    zoom = min(ZOOM_MAX, zoom + 1)
                for i, r in enumerate(_spd_rects):
                    if r.collidepoint(ev.pos):
                        _speed_idx = i
                for i, p in enumerate(filtered):
                    r = pygame.Rect(BTN_X, BTN_Y0 + i * (BTN_H + BTN_GAP), BTN_W, BTN_H)
                    if r.collidepoint(ev.pos):
                        selected = p

        mx, my = pygame.mouse.get_pos()
        screen.fill(BG)

        # ── left-column: context + action ────────────────────────────────────
        for _ui, _uline in enumerate([
            'OpenAVS simulates real port traffic using live AIS data.',
            'Each vessel navigates autonomously on a sea routing graph.',
            'Choose a port — you pilot one vessel through the environment.',
        ]):
            _us = fn_sub.render(_uline, True, MUTED)
            screen.blit(_us, (INPUT_X, _TITLE_Y + _ui * px(20)))

        pygame.draw.rect(screen, INP_BG,
                         (INPUT_X, INPUT_Y, INPUT_W, INPUT_H), border_radius=px(5))
        pygame.draw.rect(screen, ACCENT,
                         (INPUT_X, INPUT_Y, INPUT_W, INPUT_H), width=2, border_radius=px(5))
        text_y = INPUT_Y + (INPUT_H - fn_input.get_height()) // 2
        if query:
            q_surf = fn_input.render(query + ('|' if cursor_on else ''), True, WHITE)
            screen.blit(q_surf, (INPUT_X + px(10), text_y))
        else:
            ph = fn_input.render('type city or country…', True, MUTED)
            screen.blit(ph, (INPUT_X + px(10), text_y))

        for i, p in enumerate(filtered):
            r      = pygame.Rect(BTN_X, BTN_Y0 + i * (BTN_H + BTN_GAP), BTN_W, BTN_H)
            hover  = r.collidepoint(mx, my)
            active = (i == sel_idx)
            pygame.draw.rect(screen, HOVBG if (hover or active) else CARD,
                             r, border_radius=px(4))
            pygame.draw.rect(screen, ACCENT if (hover or active) else CARD_BD,
                             r, width=1, border_radius=px(4))
            if active:
                pygame.draw.rect(screen, ACCENT,
                    (r.x, r.y + px(4), px(3), r.height - px(8)), border_radius=px(2))
            state   = p.get('STATE', '')
            country = p.get('COUNTRY', '')
            label   = (f"{p['CITY']},  {state},  {country}" if state
                       else f"{p['CITY']},  {country}")
            lat, lon = p['LATITUDE'], p['LONGITUDE']
            coord   = (f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'}  "
                       f"{abs(lon):.2f}°{'E' if lon >= 0 else 'W'}")
            lbl_s = fn_btn.render(label, True, ACCENT if (hover or active) else WHITE)
            crd_s = fn_sub.render(coord, True, MUTED)
            screen.blit(lbl_s, (r.x + px(12), r.y + (BTN_H - lbl_s.get_height()) // 2))
            screen.blit(crd_s, (r.right - crd_s.get_width() - px(10),
                                r.y + (BTN_H - crd_s.get_height()) // 2))

        if not filtered and query:
            nf = fn_sub.render('No ports found', True, MUTED)
            screen.blit(nf, (LC - nf.get_width() // 2, BTN_Y0 + px(10)))

        # ── right panel card ──────────────────────────────────────────────────
        pygame.draw.rect(screen, CARD,
            (RP_X - px(12), card_top, RP_W + px(24), card_bot - card_top),
            border_radius=px(10))
        pygame.draw.rect(screen, CARD_BD,
            (RP_X - px(12), card_top, RP_W + px(24), card_bot - card_top),
            width=1, border_radius=px(10))

        # app branding inside card
        bt_surf = fn_title.render('OpenAVS', True, WHITE)
        screen.blit(bt_surf, (RP_CX - bt_surf.get_width() // 2, _brand_ty))
        bg_surf = fn_btn.render('Open Autonomous Vessel Simulator', True, MUTED)
        screen.blit(bg_surf, (RP_CX - bg_surf.get_width() // 2, _brand_gy))
        pygame.draw.aaline(screen, DIVIDER,
            (RP_X, _brand_liney), (RP_X + RP_W, _brand_liney))

        # controls section
        ch = fn_hdr.render('CONTROLS', True, MUTED)
        screen.blit(ch, (RP_CX - ch.get_width() // 2, ctrl_hdr_y))
        pygame.draw.aaline(screen, DIVIDER,
            (RP_X, ctrl_hdr_y + px(16)), (RP_X + RP_W, ctrl_hdr_y + px(16)))

        for i, (kind, lbl, desc) in enumerate(CTRL_ROWS):
            ry  = ctrl_body_y + i * CTRL_ROW_H
            rcy = ry + CTRL_ROW_H // 2
            if kind == 'lr':
                _draw_lr(KEY_CX, rcy, ARR_SZ, ACCENT)
            elif kind == 'ud':
                _draw_ud(KEY_CX, rcy, ARR_SZ, ACCENT)
            else:
                ks = fn_key.render(lbl, True, ACCENT)
                screen.blit(ks, (KEY_CX - ks.get_width() // 2,
                                 rcy - ks.get_height() // 2))
            ds = fn_key.render(desc, True, WHITE)
            screen.blit(ds, (DESC_X, rcy - ds.get_height() // 2))

        # sim speed section
        pygame.draw.aaline(screen, DIVIDER,
            (RP_X, spd_hdr_y - px(4)), (RP_X + RP_W, spd_hdr_y - px(4)))
        sh = fn_hdr.render('SIM SPEED', True, MUTED)
        screen.blit(sh, (RP_CX - sh.get_width() // 2, spd_hdr_y))
        for i, r in enumerate(_spd_rects):
            active = (i == _speed_idx)
            hover  = r.collidepoint(mx, my)
            bg  = ACCENT if active else (HOVBG if hover else DIVIDER)
            txt = WHITE  if active else (WHITE if hover else MUTED)
            pygame.draw.rect(screen, bg, r, border_radius=px(4))
            if not active:
                pygame.draw.rect(screen, CARD_BD, r, width=1, border_radius=px(4))
            ls = fn_btn.render(_SPEED_LABELS_LOC[i], True, txt)
            screen.blit(ls, (r.centerx - ls.get_width() // 2,
                             r.centery - ls.get_height() // 2))

        # map zoom section
        pygame.draw.aaline(screen, DIVIDER,
            (RP_X, zoom_hdr_y - px(4)), (RP_X + RP_W, zoom_hdr_y - px(4)))
        zh = fn_hdr.render('MAP ZOOM', True, MUTED)
        screen.blit(zh, (RP_CX - zh.get_width() // 2, zoom_hdr_y))
        for btn_r, lbl, at_lim in [
            (_zrect_minus, '−', zoom <= ZOOM_MIN),
            (_zrect_plus,  '+', zoom >= ZOOM_MAX),
        ]:
            hover = btn_r.collidepoint(mx, my) and not at_lim
            pygame.draw.rect(screen, HOVBG if hover else DIVIDER,
                             btn_r, border_radius=px(4))
            pygame.draw.rect(screen, ACCENT if hover else CARD_BD,
                             btn_r, width=1, border_radius=px(4))
            tc = WHITE if (not at_lim) else MUTED
            ls = fn_hdr.render(lbl, True, tc)
            screen.blit(ls, (btn_r.centerx - ls.get_width() // 2,
                             btn_r.centery - ls.get_height() // 2))
        zv = fn_btn.render(str(zoom), True, WHITE)
        screen.blit(zv, (RP_CX - zv.get_width() // 2,
                         zoom_btn_y + (ZOOM_BTN_H - zv.get_height()) // 2))

        # ── footer: attribution ───────────────────────────────────────────────
        ft_s = fn_attr.render(
            'projectharrison.org  ·  saurabhn.com',
            True, WHITE)
        screen.blit(ft_s, (W // 2 - ft_s.get_width() // 2,
                           FOOTER_Y - ft_s.get_height() // 2))

        display.blit(screen, (0, 0))
        pygame.display.flip()
        pygame.time.delay(16)

    return {
        'name':      f"{selected['CITY']}, {selected['COUNTRY']}",
        'origin':    (float(selected['LATITUDE']), float(selected['LONGITUDE'])),
        'zoom':      zoom,
        'speed_idx': _speed_idx,
    }


# ── main run ──────────────────────────────────────────────────────────────────

def run(make_sim, speed):

    # ── one-time scale/window setup ───────────────────────────────────────────
    pygame.display.init()
    desktops = pygame.display.get_desktop_sizes()
    DW, DH   = desktops[0] if desktops else (1920, 1080)
    S = max(min(DW * 0.90 / 1380, DH * 0.90 / 800), 1.0)

    def px(n): return int(n * S)

    W, H     = px(1380), px(800)
    CHART_W  = px(1000)
    OX, OY   = px(500), px(400)
    NS_BASE  = 1800 * S
    SB_START = CHART_W
    SB_L     = SB_START + px(14)
    SB_R     = W - px(10)

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

    font  = 'helvetica'
    F_SM  = max(9,  px(11))
    F_MD  = max(10, px(12))
    F_HDR = max(11, px(13))

    def make_fonts():
        return {
            'sm':  pygame.font.SysFont(font, F_SM),
            'md':  pygame.font.SysFont(font, F_MD),
            'hdr': pygame.font.SysFont(font, F_HDR),
        }

    icon = pygame.image.load(_paths.asset('assets/images/thumbnail.png'))
    pygame.display.set_icon(icon)
    display = pygame.display.set_mode((W, H))
    screen  = pygame.Surface((W, H))
    pygame.display.set_caption('OpenAVS')

    ports  = _load_ports(_paths.asset('data/ports.json'))

    if not ais_vessels._load_token():
        _request_api_key(display, screen, W, H, px)

    # ── back-button rect (bottom of sidebar, computed once) ───────────────────
    BACK_BTN    = pygame.Rect(SB_L - px(6), H - px(44),
                               SB_R - SB_L + px(12), px(32))
    AIS_KEY_BTN = pygame.Rect(SB_L - px(6), H - px(82),
                               SB_R - SB_L + px(12), px(28))
    _ais_configured = bool(ais_vessels._load_token())

    # ── arrow drawing helpers ─────────────────────────────────────────────────
    def draw_lr_arrows(x, y, color):
        s = max(5, px(5))
        gap = max(6, px(6))
        # ← left arrow
        pygame.draw.polygon(screen, color, [
            (x,         y + s // 2),
            (x + s,     y),
            (x + s,     y + s),
        ])
        # → right arrow
        x2 = x + s + gap
        pygame.draw.polygon(screen, color, [
            (x2 + s,    y + s // 2),
            (x2,        y),
            (x2,        y + s),
        ])
        return x + 2 * s + gap  # end x

    def draw_ud_arrows(x, y, color):
        s = max(5, px(5))
        gap = max(6, px(6))
        # ↑ up arrow
        pygame.draw.polygon(screen, color, [
            (x + s // 2, y),
            (x,          y + s),
            (x + s,      y + s),
        ])
        # ↓ down arrow
        x2 = x + s + gap
        pygame.draw.polygon(screen, color, [
            (x2 + s // 2, y + s),
            (x2,          y),
            (x2 + s,      y),
        ])
        return x + 2 * s + gap

    _SPEED_LEVELS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
    _SPEED_LABELS = ['¼×', '½×', '1×', '2×', '4×', '8×']
    _speed_idx    = 2   # default 1×

    # ── restart loop ──────────────────────────────────────────────────────────
    restart = True
    while restart:
        restart      = False
        running      = True
        paused       = False
        want_restart = False

        # ── location selection ────────────────────────────────────────────────
        loc    = _select_location(display, screen, W, H, px, ports, _speed_idx)
        origin = loc['origin']
        zoom   = loc['zoom']
        _speed_idx = loc['speed_idx']
        NS     = NS_BASE * (2 ** (zoom - 12))

        # exact viewport bounds — API caps at 2000, don't waste it on off-screen area
        _lat_max_vp = origin[0] + OY / NS
        _lat_min_vp = origin[0] - (H  - OY) / NS
        _lon_min_vp = origin[1] - OX / NS
        _lon_max_vp = origin[1] + (CHART_W - OX) / NS
        ais_vessels.fetch_async(
            _lat_min_vp, _lat_max_vp,
            _lon_min_vp, _lon_max_vp,
        )

        # ── loading screen ────────────────────────────────────────────────────
        _L_BG      = (10,  15,  32)
        _L_CARD    = (20,  30,  56)
        _L_CARD_BD = (38,  58,  98)
        _L_ACCENT  = (40,  150, 225)
        _L_WHITE   = (228, 238, 255)
        _L_MUTED   = (88,  118, 162)
        _L_BAR_BG  = (32,  48,  80)
        _L_DONE    = (35,  158, 82)
        _lfont      = pygame.font.SysFont(font, px(12))
        _lfont_hdr  = pygame.font.SysFont(font, px(11), bold=True)
        _lfont_attr = pygame.font.SysFont(font, px(16))
        _tfont      = pygame.font.SysFont(font, px(16), bold=True)
        _bfont      = pygame.font.SysFont(font, px(40), bold=True)
        BAR_W      = px(440)
        BAR_H      = px(10)
        CARD_W     = BAR_W + px(64)
        _SECTIONS  = 4  # max sections (tiles, AIS, network, routes)
        _ROW_H     = px(46)
        CARD_H     = px(80) + _SECTIONS * _ROW_H + px(32)
        CARD_X     = W // 2 - CARD_W // 2
        CARD_Y     = H // 2 - CARD_H // 2
        BAR_X      = CARD_X + px(32)

        def _draw_loading(tile_msg, tile_pct, nav_msg=None, nav_pct=None,
                          route_msg=None, route_pct=None):
            screen.fill(_L_BG)

            # app name
            bn = _bfont.render('OpenAVS', True, _L_WHITE)
            screen.blit(bn, (W // 2 - bn.get_width() // 2, CARD_Y - px(72)))
            st = _lfont.render('Open Autonomous Vessel Simulator', True, _L_MUTED)
            screen.blit(st, (W // 2 - st.get_width() // 2, CARD_Y - px(28)))
            _at_s = _lfont_attr.render('projectharrison.org  ·  saurabhn.com', True, _L_MUTED)
            screen.blit(_at_s, (W // 2 - _at_s.get_width() // 2,
                                H - _at_s.get_height() - px(14)))

            # card background
            pygame.draw.rect(screen, _L_CARD,
                             (CARD_X, CARD_Y, CARD_W, CARD_H), border_radius=px(10))
            pygame.draw.rect(screen, _L_CARD_BD,
                             (CARD_X, CARD_Y, CARD_W, CARD_H),
                             width=1, border_radius=px(10))

            # location name inside card
            loc_s = _tfont.render(loc['name'], True, _L_WHITE)
            screen.blit(loc_s, (W // 2 - loc_s.get_width() // 2, CARD_Y + px(18)))
            pygame.draw.line(screen, _L_CARD_BD,
                             (CARD_X + px(24), CARD_Y + px(50)),
                             (CARD_X + CARD_W - px(24), CARD_Y + px(50)), 1)

            def _draw_bar(label, msg, pct, is_done, shimmer, y):
                lbl_s = _lfont_hdr.render(label, True, _L_MUTED)
                screen.blit(lbl_s, (BAR_X, y))
                val_col = _L_DONE if is_done else (_L_ACCENT if pct and pct > 0 else _L_MUTED)
                val_s   = _lfont.render(msg, True, val_col)
                screen.blit(val_s, (BAR_X + BAR_W - val_s.get_width(), y))
                by = y + px(20)
                pygame.draw.rect(screen, _L_BAR_BG, (BAR_X, by, BAR_W, BAR_H), border_radius=px(5))
                if is_done:
                    pygame.draw.rect(screen, _L_DONE, (BAR_X, by, BAR_W, BAR_H), border_radius=px(5))
                elif shimmer:
                    sx = int((time.monotonic() % 1.0) * (BAR_W - px(100)))
                    pygame.draw.rect(screen, _L_ACCENT,
                                     (BAR_X + sx, by, px(100), BAR_H), border_radius=px(5))
                elif pct and pct > 0:
                    filled = max(px(8), int(BAR_W * min(pct, 1.0)))
                    pygame.draw.rect(screen, _L_ACCENT, (BAR_X, by, filled, BAR_H), border_radius=px(5))

            row_y = CARD_Y + px(60)

            # ── tile section ──────────────────────────────────────────────────
            _draw_bar('Chart tiles', tile_msg, tile_pct, tile_pct >= 1.0, False, row_y)
            row_y += _ROW_H

            # ── AIS section ───────────────────────────────────────────────────
            if ais_vessels.is_loading():
                dots = '.' * (1 + int(time.monotonic() * 2) % 3)
                _draw_bar('Vessel positions', f'loading{dots}', None, False, True, row_y)
            else:
                cnt     = ais_vessels.vessel_count()
                ais_msg = f'{cnt} vessels' if cnt else 'none in area'
                _draw_bar('Vessel positions', ais_msg, 1.0, bool(cnt), False, row_y)
            row_y += _ROW_H

            # ── sea network section ───────────────────────────────────────────
            if nav_msg is not None:
                done_n = nav_pct is not None and nav_pct >= 1.0
                _draw_bar('Sea network', nav_msg, nav_pct, done_n, False, row_y)
                row_y += _ROW_H

                # ── route planning section ────────────────────────────────────
                if route_msg is not None:
                    done_r = route_pct is not None and route_pct >= 1.0
                    _draw_bar('Route planning', route_msg, route_pct, done_r, False, row_y)

            display.blit(screen, (0, 0))
            pygame.display.flip()
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    raise SystemExit

        def loading_progress(msg, pct):
            _draw_loading(msg, pct)

        _draw_loading('Preparing…', 0.0)

        print('Loading map tiles…')
        chart_bg = tiles.build_background(
            origin, CHART_W, H, OX, OY, NS, zoom,
            progress_cb=loading_progress)

        # Shift origin toward sea centroid if the initial view is mostly land
        _adj_origin = _recenter_on_water(chart_bg, origin, NS, OX, OY, CHART_W, H)
        if _adj_origin != origin:
            origin = _adj_origin
            print(f'Recentered on water → {origin[0]:.4f}, {origin[1]:.4f}')
            chart_bg = tiles.build_background(
                origin, CHART_W, H, OX, OY, NS, zoom,
                progress_cb=lambda msg, pct: _draw_loading('Recentering…', pct))

        # wait for AIS if still in flight — keep screen live
        while ais_vessels.is_loading():
            _draw_loading('Ready', 1.0)
            pygame.time.delay(80)

        args, controlBot = make_sim(origin)

        # ── sea/land helpers (pixel-sample the rendered chart_bg) ─────────────
        def _chart_is_sea(lat, lon):
            x, y = navigation.interfacePosition(origin, (lat, lon), OX, OY, NS)
            x, y = int(x), int(y)
            if not (0 <= x < CHART_W and 0 <= y < H):
                return True
            r, g, b = chart_bg.get_at((x, y))[:3]
            return b > 140 and b > r and (b - r) > 20

        def _would_dock(la):
            """True if the vessel's next dead-reckoned position is on land."""
            next_pos = navigation.arrival(la['pos'], la['course'], la['speed'] / 60)
            return not _chart_is_sea(next_pos[0], next_pos[1])

        # Ensure ownship starts in water; spiral-search if not
        if not _chart_is_sea(controlBot.p1[0], controlBot.p1[1]):
            _step  = 4.0 / NS
            _found = False
            for _r in range(1, 200):
                for _dx in range(-_r, _r + 1):
                    for _dy in range(-_r, _r + 1):
                        if abs(_dx) != _r and abs(_dy) != _r:
                            continue
                        _tla = controlBot.p1[0] + _dy * _step
                        _tlo = controlBot.p1[1] + _dx * _step
                        if _chart_is_sea(_tla, _tlo):
                            controlBot.p1 = (_tla, _tlo)
                            _found = True
                            break
                    if _found:
                        break
                if _found:
                    break

        # ── sea-network filter pass — shown on loading screen ─────────────────
        _all_av  = ais_vessels.get_vessels()
        _n_total = max(len(_all_av), 1)
        live_ais   = []
        static_ais = []
        docked_ais = []
        _draw_loading('Ready', 1.0, 'Scanning…', 0.0)
        for _i, _av in enumerate(_all_av):
            if _i % max(1, _n_total // 60) == 0:
                _draw_loading('Ready', 1.0,
                              f'Scanning  {_i} / {_n_total}',
                              _i / _n_total)
            _spd = float(_av.get('speed') or 0)
            _lat = float(_av['lat'])
            _lon = float(_av['lon'])
            if not _chart_is_sea(_lat, _lon):
                continue
            if _spd > 5:
                _hdg = float(_av.get('heading') or _av.get('course') or 0)
                live_ais.append({
                    'name':          _av['name'],
                    'mmsi':          _av['mmsi'],
                    'pos':           (_lat, _lon),
                    'course':        _hdg,
                    'speed':         _spd,
                    'is_sanctioned': bool(_av.get('is_sanctioned')),
                    'cpa':           None,
                    'tcpa':          None,
                    'minute':        0,
                })
            else:
                static_ais.append(_av)

        _n_land    = _n_total - len(live_ais) - len(static_ais)
        _scan_done = (f'{len(live_ais)} moving  ·  {len(static_ais)} static'
                      + (f'  ·  {_n_land} on land' if _n_land else ''))
        _draw_loading('Ready', 1.0, _scan_done, 1.0)

        # ── Spawn ownship at sea centroid, oriented toward AIS cluster ────────
        _sc_xs, _sc_ys, _sc_n = 0, 0, 0
        for _spx in range(0, CHART_W, 8):
            for _spy in range(0, H, 8):
                _sr, _sg, _sb = chart_bg.get_at((_spx, _spy))[:3]
                if _sb > 140 and _sb > _sr and (_sb - _sr) > 20:
                    _sc_xs += _spx
                    _sc_ys += _spy
                    _sc_n  += 1
        if _sc_n > 0:
            _sea_lat = origin[0] + (OY - _sc_ys / _sc_n) / NS
            _sea_lon = origin[1] + (_sc_xs / _sc_n - OX) / NS
            if _chart_is_sea(_sea_lat, _sea_lon):
                controlBot.p1 = (_sea_lat, _sea_lon)

        if live_ais:
            _cl_lat = sum(la['pos'][0] for la in live_ais) / len(live_ais)
            _cl_lon = sum(la['pos'][1] for la in live_ais) / len(live_ais)
            try:
                controlBot.course = navigation.bearing(
                    controlBot.p1, (_cl_lat, _cl_lon))
            except Exception:
                pass

        controlBot.speed = 12

        # ── Build ocean routing graph from chart_bg pixel map ─────────────────
        _gr_lat_min = origin[0] - (H - OY) / NS
        _gr_lat_max = origin[0] + OY / NS
        _gr_lon_min = origin[1] - OX / NS
        _gr_lon_max = origin[1] + (CHART_W - OX) / NS
        _gr_cols, _gr_rows = 50, 40
        _draw_loading('Ready', 1.0, _scan_done, 1.0, 'Building graph…', 0.02)
        _G, _G_lats, _G_lons = _graph_module.build_graph(
            _chart_is_sea,
            _gr_lat_min, _gr_lat_max, _gr_lon_min, _gr_lon_max,
            n_cols=_gr_cols, n_rows=_gr_rows,
        )
        print(f'  routing graph: {len(_G)} sea nodes')
        _draw_loading('Ready', 1.0, _scan_done, 1.0,
                      f'Graph: {len(_G)} nodes', 0.10)

        # Snap ownship to the nearest verified sea graph node — more reliable
        # than the pixel-centroid, which can land on a thin land strip.
        _snap = _graph_module.find_nearest_sea_node(
            controlBot.p1[0], controlBot.p1[1], _G_lats, _G_lons, _G)
        if _snap:
            controlBot.p1 = _graph_module.node_to_latlon(
                _snap[0], _snap[1], _G_lats, _G_lons)

        # ── Assign A* routes + behavior state to each live AIS vessel ─────────
        _n_rv = max(len(live_ais), 1)

        def _init_vessel_route(la):
            start = _graph_module.find_nearest_sea_node(
                la['pos'][0], la['pos'][1], _G_lats, _G_lons, _G)
            if start is None:
                la['waypoints'] = []
            else:
                goal = _graph_module.pick_destination(
                    start[0], start[1], la['course'],
                    _G_lats, _G_lons, _G, _gr_rows, _gr_cols)
                if goal and goal != start:
                    path = _graph_module.astar(_G, start, goal, _G_lats, _G_lons)
                    la['waypoints'] = [
                        _graph_module.node_to_latlon(r, c, _G_lats, _G_lons)
                        for r, c in path]
                else:
                    la['waypoints'] = []
            la['wp_idx']             = 0
            la['network_heading']    = la['course']
            la['heading']            = la['course']
            la['intended_heading']   = la['course']
            la['heading_bias']       = 0.0
            la['alter_until_clear']  = False
            la['traffic_alter_deg']  = 0.0
            la['random_alter_deg']   = 0.0
            la['random_alter_until'] = 0.0
            la['next_random_check']  = time.monotonic() + random.uniform(5, 45)
            la['max_turn_rate']      = 8.0  # deg / sim-tick
            la['shore_hits']         = 0

        with _PoolEx(max_workers=8) as _rv_ex:
            _rv_futs = [_rv_ex.submit(_init_vessel_route, la) for la in live_ais]
            _rv_done = 0
            for _rv_f in _ac(_rv_futs):
                _rv_done += 1
                if _rv_done % max(1, _n_rv // 25) == 0:
                    _draw_loading('Ready', 1.0, _scan_done, 1.0,
                                  f'Routing  {_rv_done} / {_n_rv}',
                                  0.10 + 0.88 * _rv_done / _n_rv)

        _draw_loading('Ready', 1.0, _scan_done, 1.0,
                      f'{len(live_ais)} vessels routed', 1.0)
        pygame.time.delay(600)

        # Pre-pick 3 random live vessels to use as sidebar placeholders until
        # CPA computation runs for the first time
        _cpa_placeholders = (random.sample(live_ais, min(3, len(live_ais)))
                             if live_ais else [])

        _cpa_tick        = 0
        _strtree         = None
        _strtree_t       = 0.0   # wall-clock time of last STRtree rebuild
        _cpa_behavior_t  = 0.0   # wall-clock time of last behavior CPA run
        _ctrl_docked     = False

        # ── inner helpers (re-created each restart so closures see new vars) ──

        def draw_divider(f, y, x0=None, x1=None):
            pygame.draw.aaline(screen, DIVIDER,
                               (x0 if x0 is not None else SB_L - px(4), y),
                               (x1 if x1 is not None else SB_R, y))
            return y + px(8)

        def draw_row(f, label, value, y, val_color=None):
            screen.blit(f['sm'].render(label, True, MUTED),
                        (SB_L + px(4), y))
            screen.blit(f['md'].render(value, True, val_color or BLACK),
                        (SB_L + px(72), y))
            return y + px(17)

        def blit_backed(surf, pos, pad=None, bg=(255, 255, 255, 185)):
            p = pad if pad is not None else px(3)
            backing = pygame.Surface(
                (surf.get_width() + 2 * p, surf.get_height() + 2 * p),
                pygame.SRCALPHA)
            backing.fill(bg)
            screen.blit(backing, (pos[0] - p, pos[1] - p))
            screen.blit(surf, pos)

        def displayVessel(x, y, bot):
            fv = pygame.font.SysFont(font, F_MD)
            if bot.minutes.minute % 6 == 0:
                pygame.draw.circle(screen, bot.color, (x, y), max(2, px(2)))
                screen.blit(fv.render(str(bot.minutes.minute), True, lightGrey),
                            (x - px(20), y - px(5)))
            else:
                pygame.draw.circle(screen, lightGrey, (x, y), max(1, px(1)))

        AIS_COLOR = (255, 200, 60)

        def handle_event(ev):
            nonlocal running, paused, want_restart, _speed_idx, _ais_configured
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_LEFT:         controlBot.course -= 15
                if ev.key == pygame.K_RIGHT:        controlBot.course += 15
                if ev.key == pygame.K_UP:           controlBot.speed  += 2
                if ev.key == pygame.K_DOWN:         controlBot.speed  -= 2
                if ev.key == pygame.K_SPACE:        paused = not paused
                if ev.key == pygame.K_RETURN:       running = False
                if ev.key == pygame.K_LEFTBRACKET:  _speed_idx = max(0, _speed_idx - 1)
                if ev.key == pygame.K_RIGHTBRACKET: _speed_idx = min(len(_SPEED_LEVELS) - 1, _speed_idx + 1)
                if ev.key == pygame.K_F12:
                    import os as _os
                    _os.makedirs('screenshots', exist_ok=True)
                    pygame.image.save(display, 'screenshots/frame.png')
                    print('screenshot → screenshots/frame.png')
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if BACK_BTN.collidepoint(ev.pos):
                    want_restart = True
                    running = False
                elif AIS_KEY_BTN.collidepoint(ev.pos):
                    _request_api_key(display, screen, W, H, px)
                    _ais_configured = bool(ais_vessels._load_token())
                    if _ais_configured:
                        ais_vessels.fetch_async(
                            _lat_min_vp, _lat_max_vp,
                            _lon_min_vp, _lon_max_vp,
                        )

        def tick_delay(ms):
            remaining = max(ms, 0)
            while remaining > 0:
                pygame.time.delay(min(16, remaining))
                remaining -= 16
                for ev in pygame.event.get():
                    handle_event(ev)

        # viewport bounds (computed once per area selection)
        lat_max_vp = _lat_max_vp
        lat_min_vp = _lat_min_vp
        lon_min_vp = _lon_min_vp
        lon_max_vp = _lon_max_vp

        # ── outer loop — runs once per restart to stamp the static scene ──────
        while running:
            screen.fill((255, 255, 255))
            screen.blit(chart_bg, (0, 0))
            f = make_fonts()

            for gy in (px(200), px(400), px(600)):
                pygame.draw.aaline(screen, lineColor, (0, gy), (CHART_W, gy))
            pygame.draw.aaline(screen, lineColor, (OX, 0), (OX, H))
            pygame.draw.circle(screen, lineColor, (OX, OY), px(200), width=1)

            lat_lbl = f"{abs(origin[0]):.3f} {'N' if origin[0] >= 0 else 'S'}"
            lon_lbl = f"{abs(origin[1]):.3f} {'E' if origin[1] >= 0 else 'W'}"
            blit_backed(f['sm'].render(lat_lbl, True, lightGrey), (px(940), px(385)))
            blit_backed(f['sm'].render(lon_lbl, True, lightGrey), (px(510), px(785)))

            _f_mkt  = pygame.font.SysFont(font, max(20, px(28)), bold=True)
            _s_ph   = _f_mkt.render('projectharrison.org', True, (10, 10, 10))
            _s_sr   = _f_mkt.render('saurabhn.com',        True, (10, 10, 10))
            _mkt_x  = px(14)
            _mkt_y2 = H - px(14)
            _mkt_y1 = _mkt_y2 - _s_sr.get_height() - px(44)
            screen.blit(_s_ph, (_mkt_x, _mkt_y1))
            screen.blit(_s_sr, (_mkt_x, _mkt_y2 - _s_sr.get_height()))
            pygame.draw.rect(screen, SB_BG, (SB_START, 0, W - SB_START, H))
            pygame.draw.aaline(screen, SB_BORDER, (SB_START, 0), (SB_START, H))

            display.blit(screen, (0, 0))
            pygame.display.update()

            # ── inner simulation loop ─────────────────────────────────────────
            while running:
                for ev in pygame.event.get():
                    handle_event(ev)

                if paused:
                    pygame.time.delay(16)
                    continue

                # simulation vessels
                nm_px = NS * 0.01666667
                for vessel in args:
                    coord = navigation.interfacePosition(
                        origin, vessel.p1, OX, OY, NS)

                    pygame.draw.aaline(screen, lightGrey,
                                       (px(15), px(15)), (px(15) + nm_px, px(15)))
                    pygame.draw.aaline(screen, lightGrey,
                                       (px(15), px(15)), (px(15), px(13)))
                    pygame.draw.aaline(screen, lightGrey,
                                       (px(15) + nm_px, px(15)),
                                       (px(15) + nm_px, px(13)))
                    blit_backed(f['sm'].render('1 NM', True, lightGrey),
                                (px(15), px(20)))

                    displayVessel(int(coord[0]), int(coord[1]), vessel)
                    if vessel is controlBot:
                        _nxt = navigation.arrival(
                            vessel.p1, vessel.course,
                            vessel.speed * (vessel.interval / 60))
                        if _chart_is_sea(_nxt[0], _nxt[1]):
                            _ctrl_docked = False
                            if vessel.behavior: vessel.behavior.go(vessel)
                            vessel.advance(vessel)
                        else:
                            _ctrl_docked = True
                    else:
                        if vessel.behavior: vessel.behavior.go(vessel)
                        vessel.advance(vessel)

                # ── behavior engine (STRtree CPA + random captain, 1 Hz) ─────
                _now_rt = time.monotonic()

                if live_ais and _now_rt - _strtree_t > 2.0:
                    _strtree   = _ShapeSTRtree(
                        [_ShapePoint(la['pos'][1], la['pos'][0]) for la in live_ais])
                    _strtree_t = _now_rt

                if _strtree and live_ais and _now_rt - _cpa_behavior_t > 1.0:
                    _cpa_behavior_t = _now_rt
                    _SAFE_CPA  = 0.3    # nm
                    _LOOKAHEAD = 10.0   # minutes (600 s)
                    _QR_DEG    = 2.0 / 60.0   # 2 nm query radius in degrees

                    for _bi, _bla in enumerate(live_ais):
                        if _bla['speed'] < 1.0:
                            continue
                        # Nearby vessel query
                        _qp   = _ShapePoint(_bla['pos'][1], _bla['pos'][0])
                        _idxs = _strtree.query(_qp.buffer(_QR_DEG),
                                               predicate='intersects')
                        # Flatten to plain list (shapely 2.x returns array)
                        try:
                            _idxs = list(_idxs)
                        except Exception:
                            _idxs = []

                        # Convert self to Cartesian nm
                        _la_lat_r = math.radians(_bla['pos'][0])
                        _p1x = _bla['pos'][1] * math.cos(_la_lat_r) * 60
                        _p1y = _bla['pos'][0] * 60
                        _bh_r = math.radians(_bla.get('heading', _bla['course']))
                        _v1x  = _bla['speed'] * math.sin(_bh_r) / 60
                        _v1y  = _bla['speed'] * math.cos(_bh_r) / 60

                        _threat     = False
                        _min_tcpa   = float('inf')
                        _min_cpa_v  = float('inf')
                        for _jj in _idxs:
                            if _jj == _bi or _jj >= len(live_ais):
                                continue
                            _oth     = live_ais[_jj]
                            _o_lat_r = math.radians(_oth['pos'][0])
                            _p2x = _oth['pos'][1] * math.cos(_o_lat_r) * 60
                            _p2y = _oth['pos'][0] * 60
                            _oh_r = math.radians(_oth.get('heading', _oth['course']))
                            _v2x  = _oth['speed'] * math.sin(_oh_r) / 60
                            _v2y  = _oth['speed'] * math.cos(_oh_r) / 60
                            _cpa_v, _tcpa_v = _cpa_tcpa_nm(
                                _p1x, _p1y, _v1x, _v1y,
                                _p2x, _p2y, _v2x, _v2y)
                            if 0 < _tcpa_v < _LOOKAHEAD and _cpa_v < _SAFE_CPA:
                                if _tcpa_v < _min_tcpa:
                                    _min_tcpa, _min_cpa_v = _tcpa_v, _cpa_v
                                    _threat = True

                        if _threat:
                            _bla['traffic_alter_deg'] = min(
                                45.0, 10.0 + (_SAFE_CPA - _min_cpa_v) * 30.0)
                            _bla['alter_until_clear'] = True
                        else:
                            _bla['alter_until_clear'] = False
                            _bla['traffic_alter_deg'] = 0.0

                        # Random captain decision (per-vessel wall-clock interval)
                        if _now_rt >= _bla.get('next_random_check', 0.0):
                            _bla['next_random_check'] = (
                                _now_rt + random.uniform(30, 90))
                            if random.random() < 0.03:
                                _bla['random_alter_deg']   = random.uniform(-25, 25)
                                _bla['random_alter_until'] = (
                                    _now_rt + random.uniform(60, 300))

                # ── advance live AIS vessels with behavior layers ──────────────
                _still_moving = []
                for la in live_ais:
                    # 1 — Waypoint tracking → network_heading
                    _wps  = la.get('waypoints', [])
                    _wp_i = la.get('wp_idx', 0)
                    if _wps and _wp_i < len(_wps):
                        _wp = _wps[_wp_i]
                        # Cheap box-distance check (≈0.5 nm threshold)
                        if (abs(la['pos'][0] - _wp[0]) < 0.008 and
                                abs(la['pos'][1] - _wp[1]) < 0.012):
                            _wp_i = min(_wp_i + 1, len(_wps) - 1)
                            la['wp_idx'] = _wp_i
                            _wp = _wps[_wp_i]
                        try:
                            la['network_heading'] = navigation.bearing(
                                la['pos'], _wp)
                        except Exception:
                            pass

                    # 2 — Build intended_heading (priority: traffic > random > network)
                    _net      = la.get('network_heading', la['course'])
                    _intended = _net
                    if _now_rt < la.get('random_alter_until', 0.0):
                        _intended = (_net + la.get('random_alter_deg', 0)) % 360
                    if la.get('alter_until_clear'):
                        _intended = (_net + la.get('traffic_alter_deg', 0)) % 360

                    # 3 — Shore guard: cascade of fallbacks before going static
                    _shore_guard_fired = False
                    _nxt_pos = navigation.arrival(
                        la['pos'], _intended, la['speed'] / 60)
                    if not _chart_is_sea(_nxt_pos[0], _nxt_pos[1]):
                        _shore_guard_fired = True
                        _intended = _net
                        _nxt_pos  = navigation.arrival(
                            la['pos'], _intended, la['speed'] / 60)
                        if not _chart_is_sea(_nxt_pos[0], _nxt_pos[1]):
                            # Try skipping to next waypoint for a fresh angle
                            _sg_found = False
                            if _wps and _wp_i + 1 < len(_wps):
                                try:
                                    _sk_hdg = navigation.bearing(
                                        la['pos'], _wps[_wp_i + 1])
                                    _sk_pos = navigation.arrival(
                                        la['pos'], _sk_hdg, la['speed'] / 60)
                                    if _chart_is_sea(_sk_pos[0], _sk_pos[1]):
                                        la['wp_idx'] = _wp_i + 1
                                        _intended = _sk_hdg
                                        la['network_heading'] = _sk_hdg
                                        _nxt_pos  = _sk_pos
                                        _sg_found = True
                                except Exception:
                                    pass
                            if not _sg_found:
                                # Sweep ±30° … ±180° from network_heading
                                for _sg_off in range(30, 181, 30):
                                    for _sg_sign in (1, -1):
                                        _sg_hdg = (_net + _sg_sign * _sg_off) % 360
                                        _sg_pos = navigation.arrival(
                                            la['pos'], _sg_hdg, la['speed'] / 60)
                                        if _chart_is_sea(_sg_pos[0], _sg_pos[1]):
                                            _intended = _sg_hdg
                                            _nxt_pos  = _sg_pos
                                            _sg_found = True
                                            break
                                    if _sg_found:
                                        break
                            if not _sg_found:
                                la['shore_hits'] += 1
                                # Count open 45° cardinal directions
                                _sg_open = sum(
                                    1 for _h in range(8)
                                    if _chart_is_sea(*navigation.arrival(
                                        la['pos'], _h * 45, la['speed'] / 60)))
                                if _sg_open > 2:
                                    # Not truly surrounded — freeze this tick,
                                    # advance waypoint so next tick tries new angle
                                    if _wps and _wp_i + 1 < len(_wps):
                                        la['wp_idx'] = _wp_i + 1
                                    _nxt_pos = la['pos']
                                # else ≤2 open: surrounded/U-turn required →
                                #   _nxt_pos stays on land, step 6 → static

                    la['intended_heading'] = _intended

                    # 4 — Slew actual heading toward intended (turn-rate limited)
                    _delta = ((_intended - la.get('heading', la['course']) + 540) % 360) - 180
                    _mtr   = la.get('max_turn_rate', 8.0)
                    la['heading'] = (la.get('heading', la['course'])
                                     + max(-_mtr, min(_mtr, _delta))) % 360

                    # 5 — Heading jitter (bounded random walk, render-time only)
                    la['heading_bias'] = (la.get('heading_bias', 0.0) * 0.98
                                          + random.gauss(0, 0.5))
                    la['heading_bias'] = max(-2.5, min(2.5, la['heading_bias']))

                    # 6 — Advance position using actual heading (not bias)
                    if _chart_is_sea(_nxt_pos[0], _nxt_pos[1]):
                        if not _shore_guard_fired:
                            la['shore_hits'] = 0
                        la['pos']    = _nxt_pos
                        la['minute'] = (la['minute'] + 1) % 60
                        _still_moving.append(la)
                    else:
                        if la['shore_hits'] >= 8:
                            docked_ais.append({
                                'lat':           la['pos'][0],
                                'lon':           la['pos'][1],
                                'heading':       la.get('heading', la['course']),
                                'is_sanctioned': la['is_sanctioned'],
                                'name':          la['name'],
                            })
                        else:
                            _still_moving.append(la)
                live_ais[:] = _still_moving
                _cpa_tick += 1
                if _cpa_tick % 30 == 0:
                    _compute_live_cpa(live_ais, controlBot)


                # AIS contacts — static (speed ≤ 5 kts, anchored/moored; pre-filtered)
                for av in static_ais:
                    ax, ay = navigation.interfacePosition(
                        origin, (float(av['lat']), float(av['lon'])), OX, OY, NS)
                    ax, ay = int(ax), int(ay)
                    if 0 <= ax < CHART_W and 0 <= ay < H:
                        if av['is_sanctioned']:
                            dot_col, rim_col = (220, 50, 50), (140, 30, 30)
                        else:
                            dot_col, rim_col = AIS_COLOR, (180, 130, 20)
                        pygame.draw.circle(screen, dot_col, (ax, ay), max(3, px(3)))
                        pygame.draw.circle(screen, rim_col, (ax, ay), max(3, px(3)), 1)

                # AIS contacts — docked (hit shore repeatedly — static yellow line, bow-to-stern)
                for dv in docked_ais:
                    ax, ay = navigation.interfacePosition(
                        origin, (dv['lat'], dv['lon']), OX, OY, NS)
                    ax, ay = int(ax), int(ay)
                    if 0 <= ax < CHART_W and 0 <= ay < H:
                        _hl    = max(8, px(10))
                        _hdg_r = math.radians(dv['heading'])
                        _dx    = math.sin(_hdg_r) * _hl
                        _dy    = -math.cos(_hdg_r) * _hl
                        _col   = (220, 50, 50) if dv['is_sanctioned'] else AIS_COLOR
                        pygame.draw.line(screen, _col,
                            (int(ax - _dx), int(ay + _dy)),
                            (int(ax + _dx), int(ay - _dy)),
                            max(2, px(2)))

                # AIS contacts — live (speed > 3 kts, dead-reckoned each tick) — trail dots
                for la in live_ais:
                    ax, ay = navigation.interfacePosition(
                        origin, la['pos'], OX, OY, NS)
                    ax, ay = int(ax), int(ay)
                    if 0 <= ax < CHART_W and 0 <= ay < H:
                        dot_col = (220, 50, 50) if la['is_sanctioned'] else (30, 60, 140)
                        if la['minute'] % 6 == 0:
                            pygame.draw.circle(screen, dot_col, (ax, ay), max(2, px(2)))
                        else:
                            pygame.draw.circle(screen, lightGrey, (ax, ay), max(1, px(1)))

                display.blit(screen, (0, 0))
                # crosshair through ownship — drawn to display so it never accumulates
                _ucx, _ucy = navigation.interfacePosition(
                    origin, controlBot.p1, OX, OY, NS)
                _ucx, _ucy = int(_ucx), int(_ucy)
                if 0 <= _ucx < CHART_W and 0 <= _ucy < H:
                    pygame.draw.line(display, YOU_ACCENT, (0, _ucy), (CHART_W, _ucy), 1)
                    pygame.draw.line(display, YOU_ACCENT, (_ucx, 0), (_ucx, H), 1)
                # leading-point circles drawn to display only — never accumulate on screen trail
                for vessel in args:
                    cx, cy = navigation.interfacePosition(
                        origin, vessel.p1, OX, OY, NS)
                    cx, cy = int(cx), int(cy)
                    if 0 <= cx < CHART_W and 0 <= cy < H:
                        pygame.draw.circle(display, (255, 255, 255), (cx, cy), max(6, px(6)))
                        pygame.draw.circle(display, vessel.color,   (cx, cy), max(5, px(5)))
                        pygame.draw.circle(display, (255, 255, 255), (cx, cy), max(5, px(5)), 1)
                for la in live_ais:
                    cx, cy = navigation.interfacePosition(
                        origin, la['pos'], OX, OY, NS)
                    cx, cy = int(cx), int(cy)
                    if 0 <= cx < CHART_W and 0 <= cy < H:
                        dot_col = (220, 50, 50) if la['is_sanctioned'] else (30, 60, 140)
                        pygame.draw.circle(display, (255, 255, 255), (cx, cy), max(4, px(4)))
                        pygame.draw.circle(display, dot_col,         (cx, cy), max(3, px(3)))
                pygame.display.flip()

                # ── sidebar ───────────────────────────────────────────────────
                pygame.draw.rect(screen, SB_BG, (SB_START, 0, W - SB_START, H))
                pygame.draw.aaline(screen, SB_BORDER, (SB_START, 0), (SB_START, H))

                tick_delay(max(10, int((speed // 10000) / _SPEED_LEVELS[_speed_idx])))

                # app name in sidebar header
                y = px(10)
                _sb_title = pygame.font.SysFont(font, max(11, px(13)), bold=True)
                _app_surf = _sb_title.render('OpenAVS', True, YOU_ACCENT)
                screen.blit(_app_surf, (SB_L, y))
                y += px(18)
                y = draw_divider(f, y)

                screen.blit(f['hdr'].render('CONTROLS', True, (75, 80, 92)),
                            (SB_L, y))
                y += px(14)

                KEY_COL    = (75, 80, 92)
                KEY_OFF    = SB_L + px(4)
                DESC_OFF   = SB_L + px(56)
                ROW_H      = px(16)

                # ← → Course
                draw_lr_arrows(KEY_OFF, y + px(3), KEY_COL)
                screen.blit(f['sm'].render('Course  ±15°', True, BLACK), (DESC_OFF, y))
                y += ROW_H

                # ↑ ↓ Speed
                draw_ud_arrows(KEY_OFF, y + px(3), KEY_COL)
                screen.blit(f['sm'].render('Speed   ±2 kts', True, BLACK), (DESC_OFF, y))
                y += ROW_H

                # SPACE / ENTER / [ ]
                for key_lbl, desc in [('SPACE', 'Pause / Resume'),
                                      ('ENTER', 'Quit'),
                                      ('[ ]',  f'Sim  {_SPEED_LABELS[_speed_idx]}')]:
                    screen.blit(f['sm'].render(key_lbl, True, KEY_COL), (KEY_OFF, y))
                    screen.blit(f['sm'].render(desc, True, BLACK), (DESC_OFF, y))
                    y += ROW_H

                y += px(5)
                if paused:
                    status_label, status_color = 'PAUSED', CPA_WARN
                elif _ctrl_docked:
                    status_label, status_color = 'DOCKED', (90, 130, 180)
                else:
                    status_label, status_color = 'RUNNING', (35, 140, 55)
                screen.blit(f['sm'].render('STATUS', True, MUTED),
                            (SB_L + px(4), y))
                screen.blit(f['hdr'].render(status_label, True, status_color),
                            (SB_L + px(52), y - px(1)))
                spd_surf = f['sm'].render(_SPEED_LABELS[_speed_idx], True, MUTED)
                screen.blit(spd_surf, (SB_R - spd_surf.get_width(), y))
                y += px(16)
                y = draw_divider(f, y)
                y += px(6)

                # vessel cards
                for number, item in enumerate(args):
                    if number > 2:
                        break

                    is_user = (item is controlBot)
                    n_cpa   = len(item.cpa) if item.cpa else 0
                    card_h  = px(86) + n_cpa * px(34)
                    card_x  = SB_L - px(6)
                    card_w  = SB_R - SB_L + px(8)
                    card_bg = YOU_BG   if is_user else CARD_BG
                    card_bd = YOU_ACCENT if is_user else CARD_BD

                    pygame.draw.rect(screen, card_bg,
                        (card_x, y, card_w, card_h), border_radius=px(5))
                    pygame.draw.rect(screen, card_bd,
                        (card_x, y, card_w, card_h), width=1, border_radius=px(5))

                    if is_user:
                        pygame.draw.rect(screen, YOU_ACCENT,
                            (card_x, y + px(4), px(4), card_h - px(8)),
                            border_radius=px(2))

                    row_y = y + px(8)
                    pygame.draw.rect(screen, item.color,
                        (SB_L + px(2), row_y + px(1), px(10), px(10)),
                        border_radius=px(2))

                    name_color = YOU_ACCENT if is_user else BLACK
                    screen.blit(f['hdr'].render(item.name, True, name_color),
                                (SB_L + px(16), row_y - px(1)))

                    if is_user:
                        badge = f['sm'].render('YOU', True, (255, 255, 255))
                        bw    = badge.get_width() + px(8)
                        bx    = SB_R - bw - px(2)
                        pygame.draw.rect(screen, YOU_ACCENT,
                            (bx, row_y + px(1), bw, px(13)), border_radius=px(3))
                        screen.blit(badge, (bx + px(4), row_y + px(1)))

                    row_y += px(18)
                    pygame.draw.aaline(screen, DIVIDER,
                                       (SB_L - px(2), row_y), (SB_R, row_y))
                    row_y += px(6)

                    lat = f"{abs(round(item.p1[0], 3))}°{'N' if item.p1[0] >= 0 else 'S'}"
                    lon = f"{abs(round(item.p1[1], 3))}°{'E' if item.p1[1] >= 0 else 'W'}"
                    row_y = draw_row(f, 'Position', f"{lat}  {lon}", row_y)
                    row_y = draw_row(f, 'Course',   f"{round(item.course, 1)}°T", row_y)
                    row_y = draw_row(f, 'Speed',    f"{round(item.speed, 1)} kts", row_y)

                    if item.cpa:
                        for ci, cpa_val in enumerate(item.cpa):
                            try:
                                tcpa_val   = item.tcpa[ci]
                                other_name = item.cpaName[ci] if item.cpaName else '?'
                                cpa_str    = (f"{round(cpa_val, 2)} NM"
                                              if cpa_val >= 0 else '…')
                                tcpa_str   = (f"{round(tcpa_val)} min"
                                              if cpa_val >= 0 else '…')
                                warn_col   = CPA_WARN if cpa_val < 1.0 else BLACK

                                pygame.draw.aaline(screen, DIVIDER,
                                                   (SB_L, row_y), (SB_R, row_y))
                                row_y += px(5)
                                screen.blit(
                                    f['sm'].render(
                                        f"CPA  {other_name[:14]}", True, MUTED),
                                    (SB_L + px(4), row_y))
                                cpa_surf = f['md'].render(cpa_str, True, warn_col)
                                screen.blit(cpa_surf,
                                    (SB_R - cpa_surf.get_width() - px(2), row_y))
                                row_y += px(14)
                                screen.blit(
                                    f['sm'].render('TCPA', True, MUTED),
                                    (SB_L + px(4), row_y))
                                tcpa_surf = f['md'].render(tcpa_str, True, BLACK)
                                screen.blit(tcpa_surf,
                                    (SB_R - tcpa_surf.get_width() - px(2), row_y))
                                row_y += px(14)
                            except Exception:
                                pass

                    y = row_y + px(10)

                # ── AIS contacts (top 3 by CPA; placeholders while computing) ──
                ranked = sorted(
                    (la for la in live_ais if la['cpa'] is not None),
                    key=lambda x: x['cpa'])[:3]
                _calculating = not ranked
                _display_ais = ranked if ranked else _cpa_placeholders[:3]

                if _display_ais:
                    hdr_lbl = ('AIS CONTACTS  —  calculating…'
                               if _calculating else 'AIS CONTACTS')
                    screen.blit(f['hdr'].render(hdr_lbl, True, (75, 80, 92)),
                                (SB_L, y))
                    y += px(14)
                    y = draw_divider(f, y)
                    for la in _display_ais:
                        ais_col = (220, 50, 50) if la['is_sanctioned'] else (30, 60, 140)
                        if _calculating:
                            cpa_str  = '— NM'
                            tcpa_str = 'Calculating…'
                            cpa_col  = MUTED
                        else:
                            cpa_col  = CPA_WARN if la['cpa'] < 1.0 else BLACK
                            cpa_str  = f"{round(la['cpa'], 2)} NM"
                            tcpa_str = f"{round(la['tcpa'])} min"
                        card_h = px(86) + px(34)
                        card_x = SB_L - px(6)
                        card_w = SB_R - SB_L + px(8)

                        pygame.draw.rect(screen, CARD_BG,
                            (card_x, y, card_w, card_h), border_radius=px(5))
                        pygame.draw.rect(screen, CARD_BD,
                            (card_x, y, card_w, card_h), width=1, border_radius=px(5))

                        row_y = y + px(8)
                        pygame.draw.rect(screen, ais_col,
                            (SB_L + px(2), row_y + px(1), px(10), px(10)),
                            border_radius=px(2))
                        screen.blit(f['hdr'].render(la['name'][:16], True, BLACK),
                                    (SB_L + px(16), row_y - px(1)))

                        row_y += px(18)
                        pygame.draw.aaline(screen, DIVIDER,
                                           (SB_L - px(2), row_y), (SB_R, row_y))
                        row_y += px(6)

                        lat = f"{abs(round(la['pos'][0], 3))}°{'N' if la['pos'][0] >= 0 else 'S'}"
                        lon = f"{abs(round(la['pos'][1], 3))}°{'E' if la['pos'][1] >= 0 else 'W'}"
                        _disp_hdg = (la.get('heading', la['course'])
                                     + la.get('heading_bias', 0)) % 360
                        row_y = draw_row(f, 'Position', f"{lat}  {lon}", row_y)
                        row_y = draw_row(f, 'Heading',  f"{round(_disp_hdg, 1)}°T", row_y)
                        row_y = draw_row(f, 'Speed',    f"{round(la['speed'], 1)} kts", row_y)

                        pygame.draw.aaline(screen, DIVIDER, (SB_L, row_y), (SB_R, row_y))
                        row_y += px(5)
                        screen.blit(f['sm'].render(
                            f"CPA  {controlBot.name[:14]}", True, MUTED),
                            (SB_L + px(4), row_y))
                        cpa_surf = f['md'].render(cpa_str, True, cpa_col)
                        screen.blit(cpa_surf,
                            (SB_R - cpa_surf.get_width() - px(2), row_y))
                        row_y += px(14)
                        screen.blit(f['sm'].render('TCPA', True, MUTED),
                                    (SB_L + px(4), row_y))
                        tcpa_surf = f['md'].render(tcpa_str, True,
                                                   MUTED if _calculating else BLACK)
                        screen.blit(tcpa_surf,
                            (SB_R - tcpa_surf.get_width() - px(2), row_y))
                        row_y += px(14)

                        y = row_y + px(10)

                # ── AIS key button ────────────────────────────────────────────
                mx, my = pygame.mouse.get_pos()
                ais_hover = AIS_KEY_BTN.collidepoint(mx, my)
                _ais_bg   = (50, 80, 140) if ais_hover else (38, 60, 110)
                pygame.draw.rect(screen, _ais_bg, AIS_KEY_BTN, border_radius=px(4))
                pygame.draw.rect(screen, (80, 110, 170), AIS_KEY_BTN,
                                 width=1, border_radius=px(4))
                _dot_col = (60, 210, 100) if _ais_configured else (200, 70, 70)
                pygame.draw.circle(screen, _dot_col,
                                   (AIS_KEY_BTN.x + px(12), AIS_KEY_BTN.centery),
                                   max(4, px(4)))
                _lbl_ais = f['sm'].render('AIS Key', True, (200, 225, 255))
                screen.blit(_lbl_ais, (AIS_KEY_BTN.x + px(22),
                                       AIS_KEY_BTN.centery - _lbl_ais.get_height() // 2))

                # ── back button ───────────────────────────────────────────────
                hover   = BACK_BTN.collidepoint(mx, my)
                btn_col = (30, 125, 255) if hover else YOU_ACCENT
                pygame.draw.rect(screen, btn_col, BACK_BTN, border_radius=px(4))
                pygame.draw.rect(screen, (120, 180, 255), BACK_BTN,
                                 width=1, border_radius=px(4))
                # small left arrow polygon inside button
                as_ = max(4, px(4))
                ax  = BACK_BTN.x + px(10)
                ay  = BACK_BTN.centery
                pygame.draw.polygon(screen, (255, 255, 255), [
                    (ax,        ay),
                    (ax + as_,  ay - as_ // 2),
                    (ax + as_,  ay + as_ // 2),
                ])
                lbl = f['hdr'].render('Area Selection', True, (255, 255, 255))
                screen.blit(lbl, (ax + as_ + px(7),
                                  BACK_BTN.centery - lbl.get_height() // 2))

        if want_restart:
            restart = True

    pygame.quit()
