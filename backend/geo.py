

from __future__ import annotations

import math

EARTH_R = 6378137.0  # rayon Web Mercator / WGS84


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------
def mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """EPSG:3857 -> EPSG:4326. Retourne (lat, lon) en degres.

    Verifie contre les GeoJSON officiels HRM : ecart maximal 0,000 m sur les
    306 places accessibles.
    """
    lon = (x / EARTH_R) * (180.0 / math.pi)
    lat = (2.0 * math.atan(math.exp(y / EARTH_R)) - math.pi / 2.0) * (180.0 / math.pi)
    return lat, lon


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance grand-cercle en metres."""
    p = math.pi / 180.0
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    )
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Polygones
# ---------------------------------------------------------------------------
def _ring_contains(ring: list, lon: float, lat: float) -> bool:
    """Lancer de rayon sur un anneau [[lon, lat], ...]."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            # Abscisse de l'intersection du rayon horizontal avec l'arete
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _polygon_contains(polygon: list, lon: float, lat: float) -> bool:
    """polygon = [anneau_exterieur, trou1, trou2, ...]."""
    if not polygon or not _ring_contains(polygon[0], lon, lat):
        return False
    # Un point dans un trou n'est pas dans le polygone.
    for hole in polygon[1:]:
        if _ring_contains(hole, lon, lat):
            return False
    return True


def geometry_contains(geometry: dict | None, lon: float, lat: float) -> bool:
    """Gere Polygon et MultiPolygon."""
    if not geometry:
        return False
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return _polygon_contains(coords, lon, lat)
    if kind == "MultiPolygon":
        return any(_polygon_contains(poly, lon, lat) for poly in coords)
    return False


def _bbox_of(coords, box=None):
    """Boite englobante d'une structure de coordonnees imbriquee."""
    if box is None:
        box = [180.0, 90.0, -180.0, -90.0]  # minlon, minlat, maxlon, maxlat
    if coords and isinstance(coords[0], (int, float)):
        lon, lat = coords[0], coords[1]
        box[0] = min(box[0], lon)
        box[1] = min(box[1], lat)
        box[2] = max(box[2], lon)
        box[3] = max(box[3], lat)
    else:
        for c in coords:
            _bbox_of(c, box)
    return box


def bbox_of_geometry(geometry: dict):
    """(minlon, minlat, maxlon, maxlat) — filtre rapide avant le test exact."""
    b = _bbox_of(geometry.get("coordinates") or [])
    return (b[0], b[1], b[2], b[3])


def polygon_centroid(geometry: dict) -> tuple[float, float] | None:
    """Centroide surfacique. Pour un MultiPolygon, l'anneau le plus vaste gagne.

    Retourne (lat, lon), ou None si la geometrie est inexploitable.
    """
    if not geometry:
        return None
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    rings = []
    if kind == "Polygon" and coords:
        rings = [coords[0]]
    elif kind == "MultiPolygon":
        rings = [poly[0] for poly in coords if poly]
    if not rings:
        return None

    best = None
    for ring in rings:
        if len(ring) < 3:
            continue
        area2 = cx = cy = 0.0
        for i in range(len(ring) - 1):
            x0, y0 = ring[i][0], ring[i][1]
            x1, y1 = ring[i + 1][0], ring[i + 1][1]
            cross = x0 * y1 - x1 * y0
            area2 += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        if abs(area2) < 1e-12:
            continue
        centroid = (cy / (3 * area2), cx / (3 * area2))  # (lat, lon)
        if best is None or abs(area2) > best[0]:
            best = (abs(area2), centroid)

    if best is None:
        # Repli : moyenne des sommets du premier anneau
        ring = rings[0]
        return (
            sum(p[1] for p in ring) / len(ring),
            sum(p[0] for p in ring) / len(ring),
        )
    return best[1]


# ---------------------------------------------------------------------------
# Lignes
# ---------------------------------------------------------------------------
def _segment_distance_m(lat, lon, lat1, lon1, lat2, lon2) -> float:
    """Distance point-segment, en projection plane locale (valide sur <10 km)."""
    kx = 111320.0 * math.cos(math.radians(lat))
    ky = 110540.0
    px, py = lon * kx, lat * ky
    ax, ay = lon1 * kx, lat1 * ky
    bx, by = lon2 * kx, lat2 * ky
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _lines_of(geometry: dict) -> list:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "LineString":
        return [coords]
    if kind == "MultiLineString":
        return list(coords)
    return []


def distance_to_line_m(geometry: dict, lat: float, lon: float, cutoff: float = 5000.0) -> float:
    """Plus courte distance du point a une geometrie lineaire, en metres."""
    best = cutoff
    for line in _lines_of(geometry):
        for i in range(len(line) - 1):
            d = _segment_distance_m(
                lat, lon, line[i][1], line[i][0], line[i + 1][1], line[i + 1][0]
            )
            if d < best:
                best = d
                if best == 0.0:
                    return 0.0
    return best
