# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/images',      'assets/images'),
        ('assets/shapefiles',  'assets/shapefiles'),
        ('data',               'data'),
    ],
    hiddenimports=[
        'shapely.geometry',
        'shapely.strtree',
        'geopy.distance',
        'shapefile',
        'pygame',
        'pygame._sdl2',
        'pygame.font',
        'pygame.image',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OpenAVS',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=False,
    icon='assets/images/OpenAVS.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='OpenAVS',
)

app = BUNDLE(
    coll,
    name='OpenAVS.app',
    icon='assets/images/OpenAVS.icns',
    bundle_identifier='org.projectharrison.openavs',
    info_plist={
        'NSPrincipalClass':      'NSApplication',
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleName':          'OpenAVS',
        'NSAppleScriptEnabled':  False,
    },
)
