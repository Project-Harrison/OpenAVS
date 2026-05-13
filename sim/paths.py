"""
Runtime path resolution — source vs PyInstaller bundle.

Read-only assets (shapefile, ports, images) come from sys._MEIPASS when
bundled, or the project root when running from source.

Writable data (tile cache, vessel stream) always goes to
~/Library/Application Support/OpenAVS/ so the .app bundle stays read-only.
"""
import os
import sys


def _bundled():
    return getattr(sys, 'frozen', False)


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app_support():
    d = os.path.expanduser('~/Library/Application Support/OpenAVS')
    os.makedirs(d, exist_ok=True)
    return d


def asset(relative_path):
    """Absolute path to a read-only bundled asset."""
    if _bundled():
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(_project_root(), relative_path)


def tile_cache_dir():
    """Writable directory for downloaded map tiles."""
    if _bundled():
        d = os.path.join(_app_support(), 'tile_cache')
    else:
        d = os.path.join(_project_root(), 'assets', 'tile_cache')
    os.makedirs(d, exist_ok=True)
    return d


def stream_path():
    """Path to the per-run vessel stream CSV."""
    if _bundled():
        d = os.path.join(_app_support(), 'database')
    else:
        d = os.path.join(_project_root(), 'database')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'stream')


def config_path():
    """User config file — stores SAURAHBN_AIS key when running as .app."""
    return os.path.join(_app_support(), 'config.json')
