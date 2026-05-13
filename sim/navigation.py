import math
from geopy.distance import geodesic
from math import sin, cos, sqrt, atan2, radians, degrees

def bearing(pointA, pointB):
    """
    Calculates the bearing between two points.
    The formulae used is the following:
        ? = atan2(sin(?long).cos(lat2),
                  cos(lat1).sin(lat2) - sin(lat1).cos(lat2).cos(?long))
    :Parameters:
      - `pointA: The tuple representing the latitude/longitude for the
        first point. Latitude and longitude must be in decimal degrees
      - `pointB: The tuple representing the latitude/longitude for the
        second point. Latitude and longitude must be in decimal degrees
    :Returns:
      The bearing in degrees
    :Returns Type:
      float
    """
    if (type(pointA) != tuple) or (type(pointB) != tuple):
        raise TypeError("Only tuples are supported as arguments")

    lat1 = math.radians(pointA[0])
    lat2 = math.radians(pointB[0])

    diffLong = math.radians(pointB[1] - pointA[1])

    x = math.sin(diffLong) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1)
            * math.cos(lat2) * math.cos(diffLong))

    initial_bearing = math.atan2(x, y)

    # Now we have the initial bearing but math.atan2 return values
    # from -180∞ to + 180∞ which is not what we want for a compass bearing
    # The solution is to normalize the initial bearing as shown below

    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360

    return compass_bearing

def arrival(p1, course, dist):
    """
    :summary: given a position, course, and distance find the resultant position
    :param: one (1) position, course, and distance
    :return: latitude and longitude
    """
    # Latitude
    lambda_ = (dist * (math.cos(math.radians(course)))) / 60
    latitude = p1[0] + lambda_

    # Longitude
    midLatitude = (p1[0] + latitude) / 2
    p = dist * (math.sin(math.radians(course)))
    dLongitude = (p / math.cos(math.radians(midLatitude))) / 60
    longitude = p1[1] + dLongitude

    return (latitude, longitude)

def distanceMiddle(p1, p2):
    """
    :param: two (2) positions
    :return: mid-latitude (rhumb line) distance
    """
    constant = 3440
    lat1, lon1, lat2, lon2 = radians(p1[0]), radians(p1[1]), radians(p2[0]), radians(p2[1])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    dist = constant * c

    return dist

def distanceGreat(p1, p2):
    """
    :param: two (2) positions
    :return: great circle distance
    """
    out = geodesic(p1, p2).nautical
    return out

def vectorApplication(initial_vector_degrees_to, initial_velocity, applied_vector_degrees_to, applied_velocity):
    """
    :summary: application of an external force to a vessel
    :param: initial (degrees and velocity) and applied (degrees and velocity) vector
    :return: resultant vector
    """

    initial_rad = radians(initial_vector_degrees_to)
    applied_rad = radians(applied_vector_degrees_to)

    east_quadrant = sin(initial_rad) * initial_velocity + sin(applied_rad) * applied_velocity
    north_quadrant = cos(initial_rad) * initial_velocity + cos(applied_rad) * applied_velocity

    z_rad = atan2(east_quadrant, north_quadrant)
    z_deg = degrees(z_rad)

    resultant_velocity = sqrt(east_quadrant ** 2 + north_quadrant ** 2)
    resultant_degrees_to = z_deg - int(z_deg / 360) * 360
    if resultant_degrees_to < 0: resultant_degrees_to = resultant_degrees_to + 360

    return round(resultant_degrees_to, 4), round(resultant_velocity, 4)

def interfacePosition(origin, p1, x_origin, y_origin, scale):

    """
    :summary: conversion of latitude and longitude of objects to pygame coordinates
    :param: origin of lat and long as tuple. object lat and long as tuple. pygame origin x and y. factor is scale of outcome.
    :return: converted x and y for use in pygame class
    :example: positionAdjustment((35, -135),(36, -134), 500, 400, 1)
    """

    """
    NOTE: this conversion -- may -- only work for western longitude and northern latitude. 
    
    Example of breakdown for western longitude / northern latitude:
    
    Course: 45
    #1 initial position: (34.83736544032709, -135.19834336092435)
    #1 gridded position: 400.16263455967294 499.80165663907565

    Course: 45
    #2 initial position: (34.86176062427803, -135.16861688880377)
    #2 gridded position: 400.138239375722 499.83138311119626
    
    """

    latDiff = (origin[0] - p1[0]) * scale
    longDiff = (origin[1] - p1[1]) * scale

    x_origin -= longDiff
    y_origin += latDiff

    return x_origin, y_origin

def reciprocalCourse(course):
    """
    :param: course in degrees (000 through 359.999...)
    :return: reciprocal course in degrees
    """
    course = course - 180
    if course < 0: course += 360
    if course >= 360: course -= 360
    return course

def changeCourse(course):
    """
    Ensures the course is standardie
    :param: course in degrees (000 through 359.999...)
    :return: course in degrees
    """
    if course < 0: course += 360
    if course >= 360: course -= 360
    return course

