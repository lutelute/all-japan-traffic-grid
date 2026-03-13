"""OD demand generation for UXsim traffic simulation.

Provides convenience wrappers around :meth:`uxsim.World.adddemand_area2area`
that accept geographic coordinates in degrees and handle the conversion to
meters using :data:`src.config.COEF_DEGREE_TO_METER`.

Includes predefined origin–destination pairs for common Japanese regions
(currently Tokyo metropolitan area) to bootstrap simulation runs without
manual OD matrix construction.
"""

import logging

from uxsim import World

from src.config import COEF_DEGREE_TO_METER

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_area_demand(
    W: World,
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
    t_start: float = 0,
    t_end: float = 3600,
    volume: float = 5000,
    radius_deg: float = 0.05,
) -> None:
    """Add area-to-area demand using geographic coordinates.

    Wraps :meth:`uxsim.World.adddemand_area2area`, converting longitude/
    latitude in degrees to the metre-based coordinate system used internally
    by the UXsim World.

    Parameters
    ----------
    W:
        UXsim World object (must already have nodes and links added).
    origin_lon:
        Longitude of the origin zone centre, in degrees.
    origin_lat:
        Latitude of the origin zone centre, in degrees.
    dest_lon:
        Longitude of the destination zone centre, in degrees.
    dest_lat:
        Latitude of the destination zone centre, in degrees.
    t_start:
        Start time of the demand window in seconds.  Defaults to ``0``.
    t_end:
        End time of the demand window in seconds.  Defaults to ``3600``
        (1 hour).
    volume:
        Total number of vehicles generated in the ``[t_start, t_end]``
        window.  Defaults to ``5000``.
    radius_deg:
        Radius of origin and destination zones in degrees.
        ``0.05`` degrees ≈ 4.5 km at Japan's latitude.

    Raises
    ------
    ValueError
        If *volume* is negative or *t_end* ≤ *t_start*.
    """
    if volume < 0:
        raise ValueError(f"volume must be non-negative, got {volume}")
    if t_end <= t_start:
        raise ValueError(
            f"t_end must be greater than t_start, got t_start={t_start}, "
            f"t_end={t_end}"
        )

    zone_radius = radius_deg * COEF_DEGREE_TO_METER

    W.adddemand_area2area(
        origin_lon * COEF_DEGREE_TO_METER,  # ox
        origin_lat * COEF_DEGREE_TO_METER,  # oy
        zone_radius,                         # oz (origin zone radius)
        dest_lon * COEF_DEGREE_TO_METER,     # dx
        dest_lat * COEF_DEGREE_TO_METER,     # dy
        zone_radius,                         # dz (dest zone radius)
        t_start,
        t_end,
        volume,
    )

    logger.debug(
        "add_area_demand: (%.4f, %.4f) → (%.4f, %.4f), "
        "volume=%d, t=[%d, %d], radius=%.4f°",
        origin_lon,
        origin_lat,
        dest_lon,
        dest_lat,
        volume,
        t_start,
        t_end,
        radius_deg,
    )


def generate_default_demands(W: World, region: str = "tokyo") -> None:
    """Add predefined OD demand pairs for a named region.

    Currently supported regions:

    - ``"tokyo"`` — Major commuter flows in the Tokyo metropolitan area.

    Parameters
    ----------
    W:
        UXsim World object (must already have nodes and links added).
    region:
        Region identifier.  Defaults to ``"tokyo"``.

    Raises
    ------
    ValueError
        If *region* is not recognised.
    """
    region_lower = region.lower()

    dispatchers: dict[str, callable] = {
        "tokyo": get_tokyo_od_pairs,
    }

    if region_lower not in dispatchers:
        available = ", ".join(sorted(dispatchers))
        raise ValueError(
            f"Unknown region '{region}'. Available regions: {available}"
        )

    od_pairs = dispatchers[region_lower]()

    for pair in od_pairs:
        add_area_demand(
            W,
            origin_lon=pair["origin_lon"],
            origin_lat=pair["origin_lat"],
            dest_lon=pair["dest_lon"],
            dest_lat=pair["dest_lat"],
            t_start=pair.get("t_start", 0),
            t_end=pair.get("t_end", 3600),
            volume=pair.get("volume", 5000),
            radius_deg=pair.get("radius_deg", 0.05),
        )

    logger.info(
        "generate_default_demands: added %d OD pairs for region '%s'",
        len(od_pairs),
        region,
    )


# ---------------------------------------------------------------------------
# Predefined OD pairs by region
# ---------------------------------------------------------------------------


def get_tokyo_od_pairs() -> list[dict]:
    """Return predefined Tokyo-area OD pairs with reasonable volumes.

    The pairs model typical weekday morning commuter flows in the Tokyo
    metropolitan area, covering major corridors such as:

    - Saitama → central Tokyo (northbound commuter)
    - Chiba → central Tokyo (eastbound commuter)
    - Yokohama → central Tokyo (southbound commuter)
    - Tama / western suburbs → Shinjuku (westbound commuter)
    - Intra-city flows between major hubs

    Each dict contains keys: ``origin_lon``, ``origin_lat``, ``dest_lon``,
    ``dest_lat``, ``t_start``, ``t_end``, ``volume``, ``radius_deg``.

    Returns
    -------
    list[dict]
        A list of OD-pair dictionaries ready for :func:`add_area_demand`.
    """
    return [
        # Saitama (Omiya) → Tokyo Station
        {
            "origin_lon": 139.6275,
            "origin_lat": 35.9062,
            "dest_lon": 139.7671,
            "dest_lat": 35.6812,
            "t_start": 0,
            "t_end": 3600,
            "volume": 6000,
            "radius_deg": 0.05,
        },
        # Chiba → Tokyo Station
        {
            "origin_lon": 140.1233,
            "origin_lat": 35.6074,
            "dest_lon": 139.7671,
            "dest_lat": 35.6812,
            "t_start": 0,
            "t_end": 3600,
            "volume": 5000,
            "radius_deg": 0.05,
        },
        # Yokohama → Shinagawa / Tokyo
        {
            "origin_lon": 139.6380,
            "origin_lat": 35.4437,
            "dest_lon": 139.7400,
            "dest_lat": 35.6284,
            "t_start": 0,
            "t_end": 3600,
            "volume": 7000,
            "radius_deg": 0.05,
        },
        # Tachikawa (western suburbs) → Shinjuku
        {
            "origin_lon": 139.4140,
            "origin_lat": 35.6983,
            "dest_lon": 139.7003,
            "dest_lat": 35.6894,
            "t_start": 0,
            "t_end": 3600,
            "volume": 4000,
            "radius_deg": 0.04,
        },
        # Kawasaki → Shibuya
        {
            "origin_lon": 139.7172,
            "origin_lat": 35.5308,
            "dest_lon": 139.7015,
            "dest_lat": 35.6580,
            "t_start": 0,
            "t_end": 3600,
            "volume": 4500,
            "radius_deg": 0.04,
        },
        # Funabashi (east Chiba) → Ikebukuro
        {
            "origin_lon": 139.9828,
            "origin_lat": 35.6947,
            "dest_lon": 139.7107,
            "dest_lat": 35.7290,
            "t_start": 0,
            "t_end": 3600,
            "volume": 3500,
            "radius_deg": 0.04,
        },
        # Tokorozawa (north-west) → Ikebukuro
        {
            "origin_lon": 139.4689,
            "origin_lat": 35.7990,
            "dest_lon": 139.7107,
            "dest_lat": 35.7290,
            "t_start": 0,
            "t_end": 3600,
            "volume": 3000,
            "radius_deg": 0.04,
        },
        # Kashiwa (north-east) → Ueno / Tokyo
        {
            "origin_lon": 139.9756,
            "origin_lat": 35.8676,
            "dest_lon": 139.7745,
            "dest_lat": 35.7141,
            "t_start": 0,
            "t_end": 3600,
            "volume": 3000,
            "radius_deg": 0.04,
        },
    ]
