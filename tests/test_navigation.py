import math
import pytest
from sim.navigation import (
    bearing, arrival, distanceMiddle, distanceGreat,
    vectorApplication, reciprocalCourse, changeCourse, interfacePosition,
)


# ── bearing ───────────────────────────────────────────────────────────────────

def test_bearing_north():
    # due north
    assert bearing((0.0, 0.0), (1.0, 0.0)) == pytest.approx(0.0, abs=0.1)

def test_bearing_east():
    # due east (approx — mid-lat effect is negligible near equator)
    b = bearing((0.0, 0.0), (0.0, 1.0))
    assert b == pytest.approx(90.0, abs=0.5)

def test_bearing_south():
    b = bearing((1.0, 0.0), (0.0, 0.0))
    assert b == pytest.approx(180.0, abs=0.1)

def test_bearing_west():
    b = bearing((0.0, 1.0), (0.0, 0.0))
    assert b == pytest.approx(270.0, abs=0.5)

def test_bearing_requires_tuples():
    with pytest.raises(TypeError):
        bearing([0, 0], (1, 0))

def test_bearing_same_point_is_zero():
    assert bearing((10.0, 20.0), (10.0, 20.0)) == pytest.approx(0.0, abs=0.1)


# ── arrival ───────────────────────────────────────────────────────────────────

def test_arrival_north_one_nm():
    # 1 nm due north from equator → lat increases by ~1/60 degree
    lat, lon = arrival((0.0, 0.0), 0.0, 1.0)
    assert lat == pytest.approx(1 / 60, abs=1e-4)
    assert lon == pytest.approx(0.0, abs=1e-4)

def test_arrival_east_one_nm():
    lat, lon = arrival((0.0, 0.0), 90.0, 1.0)
    assert lat == pytest.approx(0.0, abs=1e-4)
    assert lon > 0

def test_arrival_zero_distance():
    p = (51.5, -0.1)
    assert arrival(p, 45.0, 0.0) == pytest.approx(p, abs=1e-9)

def test_arrival_roundtrip():
    # go 10 nm north then 10 nm south — should be back near start
    p0 = (40.0, -74.0)
    p1 = arrival(p0, 0.0, 10.0)
    p2 = arrival(p1, 180.0, 10.0)
    assert p2[0] == pytest.approx(p0[0], abs=0.01)
    assert p2[1] == pytest.approx(p0[1], abs=0.01)


# ── distances ─────────────────────────────────────────────────────────────────

def test_distance_middle_same_point():
    assert distanceMiddle((0.0, 0.0), (0.0, 0.0)) == pytest.approx(0.0, abs=1e-6)

def test_distance_great_same_point():
    assert distanceGreat((0.0, 0.0), (0.0, 0.0)) == pytest.approx(0.0, abs=1e-6)

def test_distance_middle_vs_great_close_points():
    # for short distances both methods agree within 1%
    p1, p2 = (51.5, -0.1), (51.6, -0.1)
    dm = distanceMiddle(p1, p2)
    dg = distanceGreat(p1, p2)
    assert abs(dm - dg) / dg < 0.01

def test_distance_great_known():
    # London ↔ New York is ~3,015 nm
    london   = (51.5074, -0.1278)
    new_york = (40.7128, -74.0060)
    d = distanceGreat(london, new_york)
    assert 2980 < d < 3060

def test_distance_symmetry():
    p1, p2 = (34.0, 118.0), (35.5, 139.7)
    assert distanceMiddle(p1, p2) == pytest.approx(distanceMiddle(p2, p1), rel=1e-6)
    assert distanceGreat(p1, p2)  == pytest.approx(distanceGreat(p2, p1),  rel=1e-6)


# ── reciprocal / changeCourse ─────────────────────────────────────────────────

@pytest.mark.parametrize("course,expected", [
    (0,   180),
    (90,  270),
    (180, 0),
    (270, 90),
    (45,  225),
])
def test_reciprocal_course(course, expected):
    assert reciprocalCourse(course) == pytest.approx(expected, abs=0.01)

def test_change_course_normalises_negative():
    assert changeCourse(-10) == pytest.approx(350, abs=0.01)

def test_change_course_normalises_over_360():
    assert changeCourse(370) == pytest.approx(10, abs=0.01)

def test_change_course_passthrough():
    assert changeCourse(180) == pytest.approx(180, abs=0.01)


# ── vectorApplication ─────────────────────────────────────────────────────────

def test_vector_same_direction():
    # two vectors in same direction → same heading, summed speed
    hdg, spd = vectorApplication(90.0, 5.0, 90.0, 3.0)
    assert hdg == pytest.approx(90.0, abs=0.1)
    assert spd == pytest.approx(8.0, abs=0.1)

def test_vector_opposing():
    # opposing equal vectors → zero resultant speed
    _, spd = vectorApplication(0.0, 5.0, 180.0, 5.0)
    assert spd == pytest.approx(0.0, abs=1e-4)

def test_vector_perpendicular():
    # 3 kts north + 4 kts east → 5 kts at ~053°
    hdg, spd = vectorApplication(0.0, 3.0, 90.0, 4.0)
    assert spd == pytest.approx(5.0, abs=0.01)
    assert hdg == pytest.approx(math.degrees(math.atan2(4, 3)), abs=0.1)


# ── interfacePosition ────────────────────────────────────────────────────────

def test_interface_position_at_origin():
    x, y = interfacePosition((10.0, 20.0), (10.0, 20.0), 500, 400, 1800)
    assert x == pytest.approx(500, abs=1e-6)
    assert y == pytest.approx(400, abs=1e-6)

def test_interface_position_north_moves_up():
    # vessel north of origin → y decreases (up on screen)
    _, y = interfacePosition((10.0, 20.0), (11.0, 20.0), 500, 400, 1800)
    assert y < 400

def test_interface_position_east_moves_right():
    # vessel east of origin → x increases
    x, _ = interfacePosition((10.0, 20.0), (10.0, 21.0), 500, 400, 1800)
    assert x > 500
