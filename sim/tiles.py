import math
import os
import shapefile
import pygame
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from . import paths as _paths

SEA_URL    = 'https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png'
CARTO_URL  = 'https://a.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png'
HEADERS    = {'User-Agent': 'ShipSimulator/1.0 (MSTEM Capstone - educational)'}
TIMEOUT    = 8
_SHP_PATH  = 'assets/shapefiles/World/goas_v01.shp'

SEA_COLOR     = (168, 204, 222)
LAND_COLOR    = (228, 224, 182)
OUTLINE_COLOR = (110, 140, 165)


def _lat_lon_to_tile(lat, lon, z):
    n     = 2 ** z
    tx    = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    ty    = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return tx, min(max(ty, 0), n - 1)


def _tile_nw(tx, ty, z):
    n     = 2 ** z
    lon   = tx / n * 360.0 - 180.0
    lat_r = math.atan(math.sinh(math.pi * (1.0 - 2.0 * ty / n)))
    return math.degrees(lat_r), lon


def _to_px(lat, lon, origin, ox, oy, ns):
    return int(ox - (origin[1] - lon) * ns), int(oy + (origin[0] - lat) * ns)


def _draw_shapefile(surf, origin, ox, oy, ns, chart_w, chart_h):
    surf.fill(LAND_COLOR)  # background = land; ocean polygons painted on top

    try:
        sf = shapefile.Reader(_paths.asset(_SHP_PATH))
    except Exception as e:
        print(f'  shapefile load failed: {e}')
        surf.fill(SEA_COLOR)
        return

    vp_lat_max = origin[0] + oy / ns
    vp_lat_min = origin[0] - (chart_h - oy) / ns
    vp_lon_min = origin[1] - ox / ns
    vp_lon_max = origin[1] + (chart_w - ox) / ns
    margin = max(chart_w, chart_h) / ns * 0.5
    vp_lat_max += margin;  vp_lat_min -= margin
    vp_lon_max += margin;  vp_lon_min -= margin

    CLAMP = max(chart_w, chart_h) * 8

    visible_rings = []

    for shape_rec in sf.shapeRecords():
        shape = shape_rec.shape

        if hasattr(shape, 'bbox') and len(shape.bbox) == 4:
            lon_min, lat_min, lon_max, lat_max = shape.bbox
            if lon_max < vp_lon_min or lon_min > vp_lon_max:
                continue
            if lat_max < vp_lat_min or lat_min > vp_lat_max:
                continue

        parts = list(shape.parts) + [len(shape.points)]

        for i in range(len(parts) - 1):
            ring = shape.points[parts[i]:parts[i + 1]]
            pts  = [_to_px(lat, lon, origin, ox, oy, ns) for lon, lat in ring]
            pts  = [(max(-CLAMP, min(chart_w + CLAMP, p[0])),
                     max(-CLAMP, min(chart_h + CLAMP, p[1]))) for p in pts]

            if any(0 <= p[0] < chart_w and 0 <= p[1] < chart_h for p in pts):
                if len(pts) >= 3:
                    pygame.draw.polygon(surf, SEA_COLOR, pts)
                visible_rings.append(pts)

    for pts in visible_rings:
        if len(pts) >= 2:
            pygame.draw.aalines(surf, OUTLINE_COLOR, True, pts)


def _cache_path(z, tx, ty):
    return os.path.join(_paths.tile_cache_dir(), f'sea_{z}_{tx}_{ty}.png')


def _carto_cache_path(z, tx, ty):
    return os.path.join(_paths.tile_cache_dir(), f'carto_{z}_{tx}_{ty}.png')


def _download(z, tx, ty):
    path = _cache_path(z, tx, ty)
    if os.path.exists(path):
        return True
    url = SEA_URL.format(z=z, x=tx, y=ty)
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            with open(path, 'wb') as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f'    seamark tile {z}/{tx}/{ty}: {e}')
    return False


def _dl_carto(z, tx, ty):
    path = _carto_cache_path(z, tx, ty)
    if os.path.exists(path):
        return True
    url = CARTO_URL.format(z=z, x=tx, y=ty)
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            with open(path, 'wb') as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f'    carto tile {z}/{tx}/{ty}: {e}')
    return False


def _load_tile(z, tx, ty):
    path = _cache_path(z, tx, ty)
    if not os.path.exists(path):
        return None
    try:
        return pygame.image.load(path).convert_alpha()
    except Exception:
        return None


def _load_carto(z, tx, ty):
    path = _carto_cache_path(z, tx, ty)
    if not os.path.exists(path):
        return None
    try:
        return pygame.image.load(path).convert()
    except Exception:
        return None


def _draw_coastlines(surf, origin, ox, oy, ns, chart_w, chart_h):
    try:
        sf = shapefile.Reader(_paths.asset(_SHP_PATH))
    except Exception as e:
        print(f'  coastline outlines failed: {e}')
        return

    vp_lat_max = origin[0] + oy / ns
    vp_lat_min = origin[0] - (chart_h - oy) / ns
    vp_lon_min = origin[1] - ox / ns
    vp_lon_max = origin[1] + (chart_w - ox) / ns
    margin = max(chart_w, chart_h) / ns * 0.5
    vp_lat_max += margin;  vp_lat_min -= margin
    vp_lon_max += margin;  vp_lon_min -= margin

    CLAMP = max(chart_w, chart_h) * 8

    for shape_rec in sf.shapeRecords():
        shape = shape_rec.shape
        if hasattr(shape, 'bbox') and len(shape.bbox) == 4:
            lon_min, lat_min, lon_max, lat_max = shape.bbox
            if lon_max < vp_lon_min or lon_min > vp_lon_max:
                continue
            if lat_max < vp_lat_min or lat_min > vp_lat_max:
                continue
        parts = list(shape.parts) + [len(shape.points)]
        for i in range(len(parts) - 1):
            ring = shape.points[parts[i]:parts[i + 1]]
            pts = [_to_px(lat, lon, origin, ox, oy, ns) for lon, lat in ring]
            pts = [(max(-CLAMP, min(chart_w + CLAMP, p[0])),
                    max(-CLAMP, min(chart_h + CLAMP, p[1]))) for p in pts]
            if any(0 <= p[0] < chart_w and 0 <= p[1] < chart_h for p in pts):
                if len(pts) >= 2:
                    pygame.draw.aalines(surf, OUTLINE_COLOR, True, pts)


def build_background(origin, chart_w, chart_h, ox, oy, ns, zoom,
                     progress_cb=None):
    def notify(msg, pct=0.0):
        if progress_cb:
            progress_cb(msg, pct)

    _paths.tile_cache_dir()  # ensure writable cache dir exists
    surf = pygame.Surface((chart_w, chart_h))

    notify('Rendering chart…', 0.02)
    surf.fill(SEA_COLOR)

    lat_top    = origin[0] + oy / ns
    lat_bottom = origin[0] - (chart_h - oy) / ns
    lon_left   = origin[1] - ox / ns
    lon_right  = origin[1] + (chart_w - ox) / ns

    tx0, ty0 = _lat_lon_to_tile(lat_top,    lon_left,  zoom)
    tx1, ty1 = _lat_lon_to_tile(lat_bottom, lon_right, zoom)
    n = 2 ** zoom
    tx0 = max(0, tx0 - 1);  tx1 = min(n - 1, tx1 + 1)
    ty0 = max(0, ty0 - 1);  ty1 = min(n - 1, ty1 + 1)

    tile_coords = [(tx, ty)
                   for tx in range(tx0, tx1 + 1)
                   for ty in range(ty0, ty1 + 1)]

    # ── CartoDB base layer (accurate land/sea colors) ─────────────────────────
    carto_missing = [(zoom, tx, ty) for tx, ty in tile_coords
                     if not os.path.exists(_carto_cache_path(zoom, tx, ty))]

    if carto_missing:
        notify(f'Downloading {len(carto_missing)} base tiles…', 0.05)
        print(f'  downloading {len(carto_missing)} CartoDB tiles...')
        with ThreadPoolExecutor(max_workers=16) as ex:
            futs = [ex.submit(_dl_carto, *job) for job in carto_missing]
            done = 0
            for _ in as_completed(futs):
                done += 1
                pct = 0.05 + 0.55 * done / len(carto_missing)
                notify(f'Base tiles… {done}/{len(carto_missing)}', pct)
        print(f'    {len(carto_missing)}/{len(carto_missing)} carto — done')
    else:
        notify(f'Loading {len(tile_coords)} cached base tiles…', 0.60)
        print(f'  {len(tile_coords)} CartoDB tiles loaded from cache.')

    n_tiles = len(tile_coords)
    for i, (tx, ty) in enumerate(tile_coords):
        lat_nw, lon_nw = _tile_nw(tx,     ty,     zoom)
        lat_se, lon_se = _tile_nw(tx + 1, ty + 1, zoom)

        px_l = int(ox - (origin[1] - lon_nw) * ns)
        px_t = int(oy + (origin[0] - lat_nw) * ns)
        px_r = int(ox - (origin[1] - lon_se) * ns)
        px_b = int(oy + (origin[0] - lat_se) * ns)

        tw = max(1, px_r - px_l)
        th = max(1, px_b - px_t)

        carto = _load_carto(zoom, tx, ty)
        if carto:
            surf.blit(pygame.transform.smoothscale(carto, (tw, th)), (px_l, px_t))

        if i % 3 == 0:
            notify('Compositing base…', 0.60 + 0.15 * (i + 1) / n_tiles)

    # ── OpenSeaMap nav-mark overlay ───────────────────────────────────────────
    sea_missing = [(zoom, tx, ty) for tx, ty in tile_coords
                   if not os.path.exists(_cache_path(zoom, tx, ty))]

    if sea_missing:
        notify(f'Downloading {len(sea_missing)} nav tiles…', 0.75)
        print(f'  downloading {len(sea_missing)} OpenSeaMap tiles...')
        with ThreadPoolExecutor(max_workers=16) as ex:
            futs = [ex.submit(_download, *job) for job in sea_missing]
            done = 0
            for _ in as_completed(futs):
                done += 1
                pct = 0.75 + 0.20 * done / len(sea_missing)
                notify(f'Nav tiles… {done}/{len(sea_missing)}', pct)
        print(f'    {len(sea_missing)}/{len(sea_missing)} seamark — done')
    else:
        notify(f'Loading {len(tile_coords)} nav tiles…', 0.95)
        print(f'  {len(tile_coords)} OpenSeaMap tiles loaded from cache.')

    for i, (tx, ty) in enumerate(tile_coords):
        lat_nw, lon_nw = _tile_nw(tx,     ty,     zoom)
        lat_se, lon_se = _tile_nw(tx + 1, ty + 1, zoom)

        px_l = int(ox - (origin[1] - lon_nw) * ns)
        px_t = int(oy + (origin[0] - lat_nw) * ns)
        px_r = int(ox - (origin[1] - lon_se) * ns)
        px_b = int(oy + (origin[0] - lat_se) * ns)

        tw = max(1, px_r - px_l)
        th = max(1, px_b - px_t)

        sea = _load_tile(zoom, tx, ty)
        if sea:
            surf.blit(pygame.transform.smoothscale(sea, (tw, th)), (px_l, px_t))

        if i % 3 == 0:
            notify('Compositing…', 0.95 + 0.04 * (i + 1) / n_tiles)

    print('  drawing coastline outlines...')
    _draw_coastlines(surf, origin, ox, oy, ns, chart_w, chart_h)
    notify('Ready', 1.0)
    return surf.convert()
