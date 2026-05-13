
---

# OpenAVS — Open Autonomous Vessel Simulator

A simulator for Maritime Autonomous Surface Ships (MASS).
Loads real AIS positions for a chosen port, runs the surrounding traffic as autonomous vessels on a routing graph, and lets you take manual control of one vessel.

## What it does

1. Downloads recent terrestrial AIS positions for a selected area, when available.
2. Loads a minimal tileset of navigational information (shoreline, geofence, marks).
3. Generates a routing graph constrained to the sea area outside the shoreline.
4. Runs other vessels as autonomous agents on that graph, with CPA-based collision avoidance.
5. Lets you pilot one vessel manually through the same environment.

## Who it's for

Shows what traffic density at a working port actually looks like.

A starting point for experimenting with autonomous vessel behavior in a real geographic context.


## How it works

Each autonomous vessel follows a grid network built inside the sea polygon, with edges weighted by distance to open water.
Vessels react to nearby traffic using CPA/TCPA calculations and alter to starboard when a threat is detected.
A second layer adds small random course changes to approximate real-world helm behavior.
The manually controlled vessel uses the same physics and operates in the same environment as the autonomous ones.

## Scope and limitations

This is an early implementation intended to demonstrate the idea, not to model any specific autonomy stack or comply with COLREGS in full. Behavior is approximate: avoidance is starboard-only rather than rule-aware, vessel dynamics are simplified, and AIS data is used as a snapshot rather than a live feed. It is not suitable for training, navigation, or operational use.

---

## Setup

### 1 — Install dependencies

```bash
uv sync
```

### 2 — Download the coastline shapefile

`assets/shapefiles/World/goas_v01.shp` (122 MB) is not stored in git. Download the VLIZ Global Oceans and Seas v1.0 shapefile and place all component files in `assets/shapefiles/World/`:

```
https://www.vliz.be/en/imis?dasid=5168
```

Required files: `goas_v01.shp`, `goas_v01.shx`, `goas_v01.dbf`, `goas_v01.prj`, `goas_v01.cpg`

### 3 — Set API key

Requires one environment variable:

```
SAURAHBN_AIS=sdr_live_…        # Saurabhn AIS API key
```

The key is read from the environment, or automatically from `../react/.env` if present.

### 4 — Run

```bash
uv run python main.py
```

---

## Startup Flow

### 1 — Port Selection Screen

Dark-themed port picker. Left column: 3-line usage guide, search box, and port list (type city or country to filter; click or press `Enter` to select). Right panel card (centered in the right half) contains:

- **CONTROLS** — vessel control key reference with drawn polygon arrows
- **SIM SPEED** — 6 speed presets (¼× ½× 1× 2× 4× 8×), also adjustable with `[` / `]` during simulation
- **MAP ZOOM** — `−` / `+` buttons; range 8–17; controls the tile zoom level of the chart assembled at load time

Speed and zoom selections persist if you return to this screen from inside the simulation.

Footer: `projectharrison.org · powered by saurabhn.com`

### 2 — Loading Screen

Four animated progress bars:

- **Chart tiles** — CartoDB base download/composite → OpenSeaMap nav-mark overlay → shapefile coastline outlines → water-centering pass
- **Vessel positions** — live AIS fetch with shimmer while in-flight
- **Sea network** — 50×40 routing graph built from pixel-sampled chart
- **Route planning** — parallel A* route calculation for each vessel (8-thread pool)

### 3 — Simulation

Begins when all steps complete. The player spawns near the selected port in open water (spiral search if the default spawn is on land).

---

## Controls

| Key | Action |
|---|---|
| `←` / `→` | Course ±15° |
| `↑` / `↓` | Speed ±2 knots |
| `[` / `]` | Sim speed slower / faster |
| `SPACE` | Pause / Resume |
| `ENTER` | Quit simulation |
| `F12` | Save screenshot to `screenshots/frame.png` |
| Back button (sidebar) | Return to port selection |

---

## Chart System

The chart is rendered once at startup into a static `pygame.Surface` and never redrawn. It is built bottom-up:

| Layer | Source | Notes |
|---|---|---|
| Sea fill | `SEA_COLOR (168, 204, 222)` | Fallback base |
| CartoDB base | `basemaps.cartocdn.com/rastertiles/voyager_nolabels` | Full-color raster tiles, cached locally |
| OpenSeaMap nav marks | `tiles.openseamap.org/seamark` | Transparent PNG overlay — buoys, lights, traffic separation schemes |
| Shapefile coastlines | `assets/shapefiles/World/goas_v01.shp` — VLIZ GOAS v1.0 | Ocean basin polygons drawn as `aalines` outlines on top |

Tiles are downloaded in parallel (up to 16 threads) and cached in `assets/tile_cache/`. Subsequent runs at the same location load instantly from cache.

### Water Centering

After the initial chart render, `_recenter_on_water()` samples every 8th pixel, computes the centroid of all sea-colored pixels, and shifts the chart origin toward that centroid — capped at 45% of the viewport. If the shift exceeds 20px, the chart is rebuilt from cached tiles with the new origin. This prevents port selections that open on mostly-land views (e.g., an inland port surrounded by a peninsula).

### Sea/Land Detection

`_chart_is_sea(lat, lon)` pixel-samples the rendered `chart_bg` surface using the equirectangular projection. A pixel is sea if `b > 140 and b > r and (b − r) > 20`. This is used by the routing graph builder, the vessel shore guard, and the TargetBot spawn search.

---

## Simulation Vessels

| Vessel | Color | Behavior |
|---|---|---|
| AUG/V TargetBot | Red | Player-controlled |

`make_sim()` in `main.py` constructs the vessel list. `supporting.segregate()` spaces them apart before the simulation begins. TargetBot spawns at the selected port; if that point is on land, a spiral outward search finds the nearest sea pixel.

---

## Live AIS Overlay

**Source:** Saurabhn AIS API — `GET /v1/positions/latest`

```
GET https://api.saurabhn.com/v1/positions/latest
    ?min_lat=…&max_lat=…&min_lon=…&max_lon=…
X-API-Key: <SAURAHBN_AIS>
```

- Bounding box is the exact visible viewport — no margin
- API cap is **2000 vessels per call**; if hit (`≥1990` results), the list is spatially subsampled by half (`results[::2]`)
- Fetched once per area selection in a background daemon thread
- Each vessel record stores: `name`, `mmsi`, `imo`, `lat`, `lon`, `speed`, `course`, `heading`, `flag`, `is_sanctioned`

### Rendering

| Condition | Color | Behavior |
|---|---|---|
| Sanctioned | Red | Static dot at reported position |
| Speed ≤ 5 kts | Amber | Static dot — anchored/moored |
| Speed > 5 kts | Pink | **Dead-reckoned** — advances each sim tick |

Vessels with speed > 5 kts are extracted into the `live_ais` list. Every sim tick they advance one minute using the navigation engine and the multi-layer behavior system described below. Their trail dots accumulate on `screen`; the leading dot is drawn to `display` (ephemeral, never accumulates).

### Trail Dots

Each live vessel leaves a dot every simulation tick:

- **Every 6 minutes** — colored dot (pink or red) at 2px
- **All other ticks** — 1px grey dot

---

## AIS Vessel Routing & Behavior

This is the core of the simulation. Every live AIS vessel runs a four-layer autonomous navigation stack.

### Layer 0 — A* Network Routing

At load time, a 50×40 grid of sea nodes is sampled over the viewport using `_chart_is_sea()`. Nodes are connected in 8 directions with nautical-mile edge costs. A* pathfinding (`graph.py`) produces a waypoint list from each vessel's starting position toward a destination projected in its reported course direction.

Route computation is parallelized across 8 threads. Progress is shown on the loading screen.

Each vessel tracks:
- `waypoints` — list of (lat, lon) path nodes from A*
- `wp_idx` — index of the current target waypoint
- `network_heading` — bearing from current position to current waypoint; updated every tick when within ~0.5 nm of a waypoint node

### Layer 1 — Heading Jitter

Each tick a small random walk bias is added to the rendered heading:

```
heading_bias = heading_bias * 0.98 + gauss(0, 0.5)
heading_bias = clamp(heading_bias, −2.5°, +2.5°)
```

The bias is **render-only** — it is never fed back into position integration.

### Layer 2 — Traffic Avoidance (STRtree CPA)

A Shapely `STRtree` spatial index of all live AIS vessel positions is rebuilt every 2 seconds. Every 1 second, each vessel queries the index for neighbors within 2 nm. For each close neighbor, flat-earth CPA/TCPA is computed from relative position and velocity vectors:

```
tcpa = −(relpos · relvel) / |relvel|²
cpa  = |relpos + relvel × tcpa|
```

If `cpa < 0.3 nm` and `0 < tcpa < 10 min`, the vessel applies a starboard alteration:

```
alter_deg = min(45°, 10° + (0.3 − cpa) × 30°)
```

The alteration remains active (`alter_until_clear`) until CPA improves above the safe threshold.

### Layer 3 — Random Captain Decisions

Every 30–90 seconds, there is a 3% probability that a vessel makes a random heading change of ±25° lasting 60–300 seconds.

### Heading Priority Stack

Each tick, `intended_heading` is built from:

1. `network_heading` (from A* waypoints) — baseline
2. Override with random captain alteration (if active)
3. Override with traffic avoidance alteration (if active — highest priority)

### Turn Rate Slew

The vessel's actual `heading` slews toward `intended_heading` at a maximum rate of 8°/tick.

### Shore Guard (Cascade)

Before each position advance, the computed next position is checked against `_chart_is_sea()`. If it is land, a cascade of fallbacks runs in order:

1. **Network heading** — fall back from the modified intended heading to the raw A* heading
2. **Next waypoint bearing** — skip to the next waypoint node and compute a bearing from there; if clear, advance the waypoint index and use that heading
3. **360° sweep** — try headings at ±30°, ±60°, ..., ±180° from network heading in order of proximity; use the first that leads to sea
4. **Surrounded check** — sample 8 cardinal/intercardinal directions; if ≤2 are open, the vessel goes static. If >2 are open but all sweep angles failed, freeze position for one tick and advance the waypoint index

Vessels that go static are moved to `static_ais` and rendered as color-coded fixed dots for the remainder of the session.

---

## CPA Engine

### Simulation Vessels (stream-based)

Each simulation vessel writes a CSV row to `database/stream` every tick:
```
voyage_id, vessel_name, timestamp, lat, lon, course, speed
```

The `aware()` method reads the last N rows and dead-reckons all vessel pairs forward to find minimum separation. Results are stored as `cpa[]` and `tcpa[]` lists on each vessel object.

### Live AIS vs. TargetBot

Every 30 simulation ticks, `_compute_live_cpa()` projects each live AIS vessel and TargetBot forward 60 minutes and finds the minimum separation distance. Only vessels within 25 nm of TargetBot are evaluated. Results are sorted by CPA and displayed in the sidebar AIS Contacts section.

---

## Navigation Engine (`navigation.py`)

All positional math uses real maritime formulas:

| Function | Method |
|---|---|
| Position advance | Mid-latitude dead reckoning |
| Great circle distance | `geopy.geodesic` in nautical miles |
| Rhumb-line distance | Haversine formula |
| True bearing | `atan2` on lat/lon deltas |
| Chart projection | Equirectangular: `x = ox − (origin_lon − lon) × NS`, `y = oy + (origin_lat − lat) × NS` |

`NS` (nautical-miles-to-pixels scale) is `NS_BASE × 2^(zoom−12)` where `NS_BASE = 1800 × S` and `S` is the DPI scaling factor.

---

## Behavior System (`behavior.py`)

Behavior classes are named after Pac-Man ghost AI (Japanese originals):

| Class | Japanese | Meaning | Status |
|---|---|---|---|
| `Oikake` | 追いかけ | "to pursue" | Implemented |
| `Machibuse` | 待ち伏せ | "to ambush" | Defined, unassigned |
| `Otoboke` | おとぼけ | "feigning ignorance" | Defined, unassigned |

`Oikake` computes the bearing from the chasing vessel to TargetBot and steers toward it with aggression factor 12.5.

---

## Rendering Architecture

pygame-ce on macOS uses a Metal-backed hardware display surface. Blitting SRCALPHA surfaces directly onto the hardware surface produces black rectangles instead of transparency.

**Two-surface rendering:**
- `display` — hardware surface, never drawn to directly
- `screen` — plain software surface, all rendering targets this
- `display.blit(screen, (0,0))` + `pygame.display.flip()` before every frame push

Leading-point circles for simulation vessels and AIS vessels are drawn directly to `display` after the screen blit and before `flip()` — this keeps them ephemeral so they do not accumulate on the persistent vessel trail.

---

## Sidebar

Redrawn every simulation tick. Sections top-to-bottom:

1. **Controls** — keyboard shortcut reference with drawn polygon arrows
2. **Status** — `RUNNING` (green) / `PAUSED` (red)
3. **Vessel cards** (up to 3) — position, course, speed, CPA/TCPA per vessel pair. Player vessel highlighted with blue accent bar and `YOU` badge. CPA values turn red below 1.0 nm
4. **AIS Contacts** — live AIS vessels within 25 nm of TargetBot, sorted by CPA (closest first). Shows vessel name, CPA distance, and TCPA in minutes. Shows placeholder cards with `Calculating…` until the first CPA compute cycle (30 ticks). CPA turns red below 1.0 nm
5. **Area Selection button** — returns to port search without restarting pygame

---

## Stream Database (`database/stream`)

Flat CSV written every simulation tick. Each row:

```
voyage_id, vessel_name, timestamp, lat, lon, course, speed
```

- Truncated at startup each run (prevents I/O lockup from accumulated history)
- Used exclusively for inter-vessel CPA awareness of the simulation vessels
- Not persisted between runs

---

## File Structure

```
ShipSimulator/
├── main.py                    # Entry point — make_sim() factory, calls interface.run()
├── sim/
│   ├── autonomous.py          # Vessel class — position, dead reckoning, CPA, stream I/O
│   ├── behavior.py            # Autonomous behavior classes (Oikake/Machibuse/Otoboke)
│   ├── navigation.py          # Maritime math: DR, haversine, great circle, bearing, projection
│   ├── interface.py           # pygame render loop, port picker, loading screen, AIS behavior stack
│   ├── graph.py               # Ocean routing graph — 50×40 sea-node grid, A* pathfinding
│   ├── tiles.py               # Chart builder — CartoDB + OpenSeaMap + shapefile coastlines
│   ├── ais_vessels.py         # Live AIS fetch (Saurabhn bbox API), background thread, vessel store
│   ├── locations.py           # Legacy named areas (superseded by ports.json picker)
│   └── supporting.py          # Voyage ID generator, vessel segregation utility
├── capture.py                 # Headless screenshot renderer (splash / loading / main)
├── data/
│   ├── layer.geojson          # NGA worldwide navigation lights (11,381 features)
│   └── ports.json             # World port database (~4,700 unique ports with lat/lon)
├── assets/
│   ├── images/m.png           # Window / dock icon
│   ├── shapefiles/World/      # VLIZ GOAS v1.0 shapefile (download separately — 122 MB)
│   └── tile_cache/            # Cached map tiles — downloaded on first run per location
├── database/
│   └── stream                 # Per-tick vessel state CSV, cleared on startup
├── pyproject.toml             # uv project — Python 3.13, pinned dependencies
└── .venv/                     # Virtual environment
```

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pygame-ce` | ≥ 2.5.7 | Rendering, event loop, input, font, image |
| `geopy` | ≥ 2.4.1 | Geodesic (great circle) distance |
| `requests` | ≥ 2.34.0 | CartoDB + OpenSeaMap tile download, Saurabhn AIS API |
| `pyshp` | ≥ 3.0.3 | Shapefile reader (no GDAL/geopandas dependency) |
| `shapely` | ≥ 2.1.2 | STRtree spatial index for CPA traffic avoidance |

Managed with [uv](https://github.com/astral-sh/uv). Python 3.13.

---

## Known Limitations

- **GOAS shapefile resolution** — 10 ocean basin polygons; coarse at zoom 12. CartoDB tiles provide the accurate land/sea rendering; the shapefile adds outline strokes only.
- **A* grid resolution** — 50×40 nodes over the viewport. Vessels clipping narrow passages is possible; the shore guard cascade handles recovery.
- **AIS 2000-vessel cap** — Saurabhn API returns at most 2000 positions per bbox. Dense areas are spatially subsampled by half when the cap is hit.
- **AIS fetched once** — no periodic refresh. Dead reckoning continues indefinitely from the snapshot.
- **CPA range limit** — live AIS vessels beyond 25 nm of TargetBot are tracked but not evaluated for CPA.
