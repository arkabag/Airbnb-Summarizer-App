from haversine import haversine
import pandas as pd
import pyproj
from polygon_geohasher import polygon_geohasher
from geolib import geohash
import sys
import math

_EARTH_RADIUS_KM = 6378.1

def calculate_speed(lat1, long1, lat2, long2, time1, time2):
    """
    Function to fill a time-sorted dataset with speed based on its displacement and time difference.
    :param lat1:
    :param long1:
    :param lat2:
    :param long2:
    :param time1:
    :param time2:
    :return: the Series of speed values
    """
    frame = {'lat1': lat1, 'long1': long1, 'lat2': lat2, 'long2': long2, 'time1': time1, 'time2': time2}
    result = pd.DataFrame(frame)
    result['speed'] = result.apply(lambda x: device_speed(x['lat1'], x['long1'], x['lat2'], x['long2'], x['time1'], x['time2']), axis=1)
    return result['speed']


def distance_great_circle(lat1: float, long1: float, lat2: float, long2: float):
    """
    Calculates the great-circle distance between two (lat, lon)s on earth using haversine method of calculation
    :param lat1: latitude of origin
    :param long1: longitude of origin
    :param lat2: latitude of destination
    :param long2: longitude of destination
    :return: the distance in meters
    """
    origin = (lat1, long1)
    destination = (lat2, long2)
    return haversine(origin, destination, 'm')


def device_speed(lat1: float, long1: float, lat2: float, long2: float, time1, time2):
    """
    Calculates the speed of travel between two points
    :param lat1: latitude of origin
    :param long1: longitude of origin
    :param lat2: latitude of destination
    :param long2: longitude of destination
    :param time1: datetime stamp of origin time
    :param time2: datetime stamp of destination time
    :return: the speed in Km/hr
    """
    origin = (lat1, long1)
    destination = (lat2, long2)
    distance_km = haversine(origin, destination)
    if time1 == time2:
        # return float('inf') # Causes problem with the UI
        return 1000000000
    else:
        duration_hr = (time2 - time1).total_seconds() / 3600.0
        return distance_km / duration_hr

def area_bounding_box(lat_span, long_span):
    """
    Calculates the area of the bounding box for a given latitude span and longitude span
    :param lat_span: span of latitude
    :param long_span: span of longitude
    :return: area in Km^2
    """
    origin = (0.0, 0.0)
    destination = (lat_span, 0.0)
    height_km = haversine(origin, destination)

    origin = (0.0, 0.0)
    destination = (0.0, long_span)
    width_km = haversine(origin, destination)

    return height_km * width_km


def forward_bearing(lat1: float, long1: float, lat2: float, long2: float):
    geodesic = pyproj.Geod(ellps='WGS84')
    fwd_azimuth, back_azimuth, distance = geodesic.inv(long1, lat1, long2, lat2)
    # print(fwd_azimuth, back_azimuth, distance)
    return fwd_azimuth, distance


def calculate_bounding_box(lat_long_list):
    min_lat = sys.float_info.max
    min_lon = sys.float_info.max
    max_lat = -sys.float_info.max
    max_lon = -sys.float_info.max

    for row in lat_long_list:
        lat = row['value'][0]
        lon = row['value'][1]

        if lat > max_lat:
            max_lat = lat
        if lat < min_lat:
            min_lat = lat
        if lon > max_lon:
            max_lon = lon
        if lon < min_lon:
            min_lon = lon

    return ([min_lat, min_lon], [max_lat, max_lon])


def geohash_to_bounds(geohash):
    poly_bounds = polygon_geohasher.geohash_to_polygon(geohash).bounds
    return ([poly_bounds[1], poly_bounds[0]], [poly_bounds[3], poly_bounds[2]])


def are_neighbors(geohash1, geohash2):
    neighbors = geohash.neighbours(geohash1)
    return geohash2 in [neighbors.n, neighbors.ne, neighbors.e, neighbors.se, neighbors.s, neighbors.sw, neighbors.w, neighbors.nw]


def neighbors_of(geohash_code):
    neighbors = geohash.neighbours(geohash_code)
    return [neighbors.n, neighbors.ne, neighbors.e, neighbors.se, neighbors.s, neighbors.sw, neighbors.w, neighbors.nw]

def geohash_bounding_box(geohash_code):
    return geohash.bounds(geohash_code)

def has_enough_precision(number):
    abs_number = math.fabs(number)
    formatted = "{:.7f}".format(abs_number - int(abs_number)).rstrip('0')
    return len(formatted) > 4


def point_to_wkt(lat, lon):
    return f"POINT ({lon} {lat})"


def circle_to_wkt(center_lat, center_lon, radius_km):
    poly_wkt = 'POLYGON (('
    for angle_deg in range(0, 390, 30):
        bearing = angle_deg * math.pi / 180.0  # Bearing is degrees converted to radians.

        lat1 = math.radians(center_lat)  # Current lat point converted to radians
        lon1 = math.radians(center_lon)  # Current long point converted to radians

        lat2 = math.asin(math.sin(lat1) * math.cos(radius_km / _EARTH_RADIUS_KM) +
                         math.cos(lat1) * math.sin(radius_km / _EARTH_RADIUS_KM) * math.cos(bearing))

        lon2 = lon1 + math.atan2(math.sin(bearing) * math.sin(radius_km / _EARTH_RADIUS_KM) * math.cos(lat1),
                                 math.cos(radius_km / _EARTH_RADIUS_KM) - math.sin(lat1) * math.sin(lat2))

        lat2 = math.degrees(lat2)
        lon2 = math.degrees(lon2)

        if angle_deg == 0:
            poly_wkt += f"{lon2} {lat2}"
        else:
            poly_wkt += f", {lon2} {lat2}"

    poly_wkt += '))'
    return poly_wkt
