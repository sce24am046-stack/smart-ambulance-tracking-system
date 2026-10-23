import json
import logging
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# In-memory route cache: cache_key -> (timestamp, route_result)
_route_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two coordinates."""
    r = 6371000.0  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def has_moved_significantly(
    lat1: float, lon1: float, lat2: float, lon2: float, threshold_meters: float = 50.0
) -> bool:
    """Check if the vehicle has moved more than threshold_meters."""
    return _haversine_meters(lat1, lon1, lat2, lon2) > threshold_meters


class BaseRoutingProvider:
    """Abstract interface for road and traffic-aware routing engines."""

    name: str = "BaseProvider"
    supports_traffic: bool = False

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        alternatives: bool = True,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class OSRMRoutingProvider(BaseRoutingProvider):
    """
    Open Source Routing Machine (OSRM) provider.
    Provides real street-network routing, accurate turn geometries, and distance/duration estimates.
    Note: Public OSRM demo does not supply real-time dynamic congestion telemetry.
    """

    name: str = "OpenStreetMap / OSRM"
    supports_traffic: bool = False

    def __init__(self, base_url: str = "https://router.project-osrm.org", timeout: float = 3.5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        alternatives: bool = True,
    ) -> Dict[str, Any]:
        # OSRM coordinate syntax is {lon},{lat};{lon},{lat}
        url = (
            f"{self.base_url}/route/v1/driving/"
            f"{origin_lon:.6f},{origin_lat:.6f};{dest_lon:.6f},{dest_lat:.6f}"
            f"?overview=full&geometries=geojson&alternatives={'true' if alternatives else 'false'}"
        )

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ResQPulse-AmbulanceTracker/2.0"},
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    payload = json.loads(resp.read().decode("utf-8"))
                    if payload.get("code") == "Ok" and payload.get("routes"):
                        return self._parse_osrm_response(payload, origin_lat, origin_lon, dest_lat, dest_lon)
        except Exception as exc:
            logger.warning(f"OSRM routing request failed ({exc}). Falling back to internal engine.")

        # Fallback to straight-line interpolation if service is unreachable
        return OfflineFallbackProvider().calculate_route(origin_lat, origin_lon, dest_lat, dest_lon)

    def _parse_osrm_response(
        self, payload: dict, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float
    ) -> Dict[str, Any]:
        raw_routes = payload.get("routes", [])
        routes = []

        for idx, r in enumerate(raw_routes):
            dist_km = round(r.get("distance", 0.0) / 1000.0, 2)
            dur_mins = round(r.get("duration", 0.0) / 60.0, 1)

            # Convert GeoJSON [lon, lat] into Leaflet [lat, lon]
            geom = r.get("geometry", {}).get("coordinates", [])
            lat_lng_polyline = [[c[1], c[0]] for c in geom if len(c) >= 2]

            # Route summary name or street tag
            legs = r.get("legs", [])
            summary_name = legs[0].get("summary", f"Via Major Arterial {idx + 1}") if legs else f"Route Option {idx + 1}"
            if not summary_name.strip():
                summary_name = f"Route Option {idx + 1}"

            routes.append({
                "route_index": idx,
                "geometry": lat_lng_polyline,
                "distance_km": dist_km,
                "duration_minutes": dur_mins,
                "duration_traffic_minutes": None,
                "summary": summary_name,
                "is_recommended": False,
            })

        if not routes:
            return OfflineFallbackProvider().calculate_route(origin_lat, origin_lon, dest_lat, dest_lon)

        # Sort routes by shortest duration
        routes.sort(key=lambda x: x["duration_minutes"])
        routes[0]["is_recommended"] = True

        return {
            "success": True,
            "provider_name": self.name,
            "is_traffic_aware": False,
            "traffic_disclaimer": "Live traffic data unavailable. Displaying standard road routing duration.",
            "traffic_timestamp": None,
            "routes": routes,
            "recommended_route": routes[0],
            "cached": False,
            "calculated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


class TrafficAwareMapboxProvider(BaseRoutingProvider):
    """
    Traffic-aware provider adapter for Mapbox Directions API (with traffic profile).
    Active only when a valid API key is supplied via ROUTING_API_KEY.
    """

    name: str = "Mapbox Driving-Traffic"
    supports_traffic: bool = True

    def __init__(self, api_key: str, timeout: float = 3.5):
        self.api_key = api_key
        self.timeout = timeout

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        alternatives: bool = True,
    ) -> Dict[str, Any]:
        if not self.api_key:
            return OSRMRoutingProvider().calculate_route(origin_lat, origin_lon, dest_lat, dest_lon, alternatives)

        url = (
            f"https://api.mapbox.com/directions/v5/mapbox/driving-traffic/"
            f"{origin_lon:.6f},{origin_lat:.6f};{dest_lon:.6f},{dest_lat:.6f}"
            f"?geometries=geojson&overview=full&alternatives={'true' if alternatives else 'false'}"
            f"&access_token={self.api_key}"
        )

        req = urllib.request.Request(url, headers={"User-Agent": "ResQPulse-AmbulanceTracker/2.0"})

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    routes_raw = data.get("routes", [])
                    if routes_raw:
                        routes = []
                        for idx, r in enumerate(routes_raw):
                            dist_km = round(r.get("distance", 0.0) / 1000.0, 2)
                            dur_mins = round(r.get("duration", 0.0) / 60.0, 1)
                            dur_traffic_mins = round(r.get("duration_typical", dur_mins), 1)

                            geom = r.get("geometry", {}).get("coordinates", [])
                            lat_lng_polyline = [[c[1], c[0]] for c in geom if len(c) >= 2]

                            routes.append({
                                "route_index": idx,
                                "geometry": lat_lng_polyline,
                                "distance_km": dist_km,
                                "duration_minutes": dur_mins,
                                "duration_traffic_minutes": dur_traffic_mins,
                                "summary": f"Traffic-Aware Option {idx + 1}",
                                "is_recommended": False,
                            })

                        routes.sort(key=lambda x: x["duration_traffic_minutes"] or x["duration_minutes"])
                        routes[0]["is_recommended"] = True

                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        return {
                            "success": True,
                            "provider_name": self.name,
                            "is_traffic_aware": True,
                            "traffic_disclaimer": "Live traffic conditions incorporated. Road congestion changes dynamically.",
                            "traffic_timestamp": now_str,
                            "routes": routes,
                            "recommended_route": routes[0],
                            "cached": False,
                            "calculated_at": now_str,
                        }
        except Exception as exc:
            logger.warning(f"Traffic-aware routing query failed: {exc}. Gracefully falling back to OSRM.")

        # Fallback to standard OSRM provider
        return OSRMRoutingProvider().calculate_route(origin_lat, origin_lon, dest_lat, dest_lon, alternatives)


class OfflineFallbackProvider(BaseRoutingProvider):
    """
    Fallback routing generator when external internet / routing services are unreachable.
    Generates a realistic straight-line polyline with intermediate points and Haversine distance.
    """

    name: str = "Straight-line Fallback (Routing Service Unavailable)"
    supports_traffic: bool = False

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        alternatives: bool = False,
    ) -> Dict[str, Any]:
        # Generate 6 intermediate waypoint segments along great circle
        steps = 6
        polyline = []
        for i in range(steps + 1):
            fraction = i / float(steps)
            lat = origin_lat + fraction * (dest_lat - origin_lat)
            lon = origin_lon + fraction * (dest_lon - origin_lon)
            polyline.append([round(lat, 6), round(lon, 6)])

        dist_meters = _haversine_meters(origin_lat, origin_lon, dest_lat, dest_lon)
        dist_km = round(dist_meters / 1000.0, 2)
        # Assumed speed 40 km/h: time = (dist / 40) * 60
        est_minutes = round(max((dist_km / 40.0) * 60.0, 1.0), 1)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        recommended = {
            "route_index": 0,
            "geometry": polyline,
            "distance_km": dist_km,
            "duration_minutes": est_minutes,
            "duration_traffic_minutes": None,
            "summary": "Direct Line (Estimated Road Approximation)",
            "is_recommended": True,
        }

        return {
            "success": True,
            "provider_name": self.name,
            "is_traffic_aware": False,
            "traffic_disclaimer": "Live traffic data unavailable. Route calculated via straight-line distance approximation.",
            "traffic_timestamp": None,
            "routes": [recommended],
            "recommended_route": recommended,
            "cached": False,
            "calculated_at": now_str,
        }


def get_routing_provider(provider_name: Optional[str] = None, api_key: Optional[str] = None) -> BaseRoutingProvider:
    """Factory creating the appropriate routing provider instance."""
    if provider_name is None:
        provider_name = os.getenv("ROUTING_PROVIDER", "osrm").lower()

    if provider_name == "mapbox":
        key = api_key or os.getenv("ROUTING_API_KEY", "")
        return TrafficAwareMapboxProvider(api_key=key)
    elif provider_name == "offline":
        return OfflineFallbackProvider()
    else:
        return OSRMRoutingProvider()


def get_cached_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    provider: Optional[BaseRoutingProvider] = None,
    ttl_seconds: int = 300,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Retrieve route with cache verification.
    Prevents repetitive external API calls on rapid map polling ticks.
    """
    if provider is None:
        provider = get_routing_provider()

    cache_key = f"{origin_lat:.4f}_{origin_lon:.4f}_{dest_lat:.4f}_{dest_lon:.4f}_{provider.name}"
    now = time.time()

    if not force_refresh and cache_key in _route_cache:
        cached_time, cached_result = _route_cache[cache_key]
        if now - cached_time < ttl_seconds:
            result = dict(cached_result)
            result["cached"] = True
            return result

    result = provider.calculate_route(origin_lat, origin_lon, dest_lat, dest_lon)
    _route_cache[cache_key] = (now, result)
    return result


def clear_route_cache():
    """Clear in-memory route cache (useful for testing)."""
    _route_cache.clear()
