"""
AIS overlay — Saurabhn bbox endpoint:
  GET https://api.saurabhn.com/v1/positions/latest
      ?min_lat=…&max_lat=…&min_lon=…&max_lon=…
  Auth: X-API-Key (SAURAHBN_AIS env var or ../react/.env)
Capped at 2000 results per query — use exact viewport bounds.
"""
import json
import os
import threading
import requests
from typing import List, Dict, Any
from . import paths as _paths

_BASE_URL = 'https://api.saurabhn.com/v1/positions/latest'
_TIMEOUT  = 12

_lock    = threading.Lock()
_vessels: List[Dict[str, Any]] = []
_loading = False


def _load_token() -> str:
    token = os.environ.get('SAURAHBN_AIS', '').strip()
    if token:
        return token
    env_path = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     '..', '..', 'react', '.env'))
    try:
        with open(env_path) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('SAURAHBN_AIS='):
                    return line.split('=', 1)[1].strip()
    except Exception as e:
        print(f'  [ais] could not read {env_path}: {e}')
    try:
        with open(_paths.config_path()) as fh:
            return json.load(fh).get('SAURAHBN_AIS', '')
    except Exception:
        pass
    return ''


def _fetch(lat_min: float, lat_max: float,
           lon_min: float, lon_max: float) -> None:
    global _vessels, _loading
    token = _load_token()
    if not token:
        print('  [ais] SAURAHBN_AIS not found — AIS overlay disabled')
        _loading = False
        return

    params = {
        'min_lat': round(lat_min, 6),
        'max_lat': round(lat_max, 6),
        'min_lon': round(lon_min, 6),
        'max_lon': round(lon_max, 6),
    }
    print(f'  [ais] bbox {lat_min:.3f}–{lat_max:.3f}°N  '
          f'{lon_min:.3f}–{lon_max:.3f}°E…')

    try:
        r = requests.get(
            _BASE_URL,
            headers={'X-API-Key': token},
            params=params,
            timeout=_TIMEOUT,
        )
        print(f'  [ais] HTTP {r.status_code}')
        if r.status_code != 200:
            print(f'  [ais] {r.text[:200]}')
            return
        d = r.json()
    except Exception as e:
        print(f'  [ais] fetch error: {e}')
        return
    finally:
        _loading = False

    results = []
    for p in d.get('positions', []):
        lat = p.get('lat')
        lon = p.get('lon')
        if lat is None or lon is None:
            continue
        imo_raw = p.get('imo') or 0
        results.append({
            'name':         (p.get('shipname') or '—').strip() or '—',
            'mmsi':         str(p.get('mmsi') or '—'),
            'imo':          str(imo_raw) if imo_raw else '—',
            'lat':          float(lat),
            'lon':          float(lon),
            'speed':        p.get('speed'),
            'course':       p.get('course'),
            'heading':      p.get('heading'),
            'flag':         p.get('flag_mid') or '',
            'is_sanctioned': bool(p.get('is_sanctioned')),
        })

    if len(results) >= 1990:
        print(f'  [ais] cap hit — subsampling {len(results)} → {len(results) // 2}')
        results = results[::2]

    with _lock:
        _vessels = results
    print(f'  [ais] {len(results)} vessels in area')


def fetch_async(lat_min: float, lat_max: float,
                lon_min: float, lon_max: float) -> None:
    """Non-blocking bbox fetch; results via get_vessels()."""
    global _loading
    _loading = True
    threading.Thread(
        target=_fetch,
        args=(lat_min, lat_max, lon_min, lon_max),
        daemon=True,
    ).start()


def is_loading() -> bool:
    return _loading


def vessel_count() -> int:
    with _lock:
        return len(_vessels)


def get_vessels() -> List[Dict[str, Any]]:
    with _lock:
        return list(_vessels)
