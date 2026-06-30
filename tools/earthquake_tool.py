"""
earthquake_tool.py

Fetches real-time earthquake data from the USGS API and cross-references
affected locations with the company occupancy API.

- Monitors the Sacramento / SAC-STATE area (100km radius)
- Only flags earthquakes at magnitude 5.0 or above
- Returns a combined report of quake details + nearby occupied locations
"""

import os
import math
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

# Configuration 

# Sacramento, CA coordinates (centre of our monitoring zone)
SAC_LAT = 38.5816
SAC_LON = -121.4944
RADIUS_KM = 100          # Monitor within 100km of Sacramento
MIN_MAGNITUDE = 5.0      # Only alert on 5.0+ earthquakes

# How far (km) a location must be from the epicentre to be considered "affected"
AFFECTED_RADIUS_KM = 50

# USGS Earthquake API — free, no key required
USGS_URL = (
    "https://earthquake.usgs.gov/fdsnws/event/1/query"
    "?format=geojson"
    f"&minmagnitude={MIN_MAGNITUDE}"
    "&orderby=time"
    "&limit=10"
)

# Company occupancy API (loaded from .env)
OCCUPANCY_API_URL = os.getenv("PEOPLESENSE_OCCUPANCY_API_URL")
OCCUPANCY_API_KEY = os.getenv("PEOPLESENSE_OCCUPANCY_API_KEY")


# Helper: Haversine distance

def _distance_km(lat1, lon1, lat2, lon2):
    """
    Calculate the straight-line distance between two lat/lon points in kilometres.
    Uses the Haversine formula — accurate enough for our use case.
    """
    R = 6371  # Earth's radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Fetch recent earthquakes near Sacramento

def fetch_recent_earthquakes():
    """
    Pulls the latest earthquakes from USGS and filters to those
    within RADIUS_KM of Sacramento in the last 24 hours.

    Returns a list of dicts, each representing one earthquake.
    """
    # Only look at the last 24 hours
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    url = USGS_URL + f"&starttime={since}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"[earthquake_tool] USGS API error: {e}")
        return []

    earthquakes = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates", [])

        if len(coords) < 2:
            continue

        eq_lon, eq_lat = coords[0], coords[1]
        distance = _distance_km(SAC_LAT, SAC_LON, eq_lat, eq_lon)

        # Only include quakes within our monitoring radius
        if distance <= RADIUS_KM:
            earthquakes.append({
                "id": feature.get("id"),
                "magnitude": props.get("mag"),
                "location": props.get("place", "Unknown location"),
                "latitude": eq_lat,
                "longitude": eq_lon,
                "depth_km": coords[2] if len(coords) > 2 else None,
                "time": datetime.fromtimestamp(
                    props.get("time", 0) / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "distance_from_sacramento_km": round(distance, 1),
                "usgs_url": props.get("url", ""),
            })

    return earthquakes


# Step 2: Fetch occupancy data 

def fetch_occupancy():
    """
    Fetches all location occupancy data from the company API.
    Returns a list of location dicts, or empty list on failure.
    """
    if not OCCUPANCY_API_URL or not OCCUPANCY_API_KEY:
        print("[earthquake_tool] Occupancy API credentials not set in .env")
        return []

    try:
        response = requests.get(
            OCCUPANCY_API_URL,
            headers={"x-api-key": OCCUPANCY_API_KEY},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])
    except requests.RequestException as e:
        print(f"[earthquake_tool] Occupancy API error: {e}")
        return []


# Find occupied locations near the epicentre 

def find_affected_locations(eq_lat, eq_lon, occupancy_data):
    """
    Given an earthquake epicentre, returns all locations within
    AFFECTED_RADIUS_KM that have people in them (Occupancy > 0).

    Skips locations with null coordinates or zero occupancy.
    """
    affected = []

    for loc in occupancy_data:
        lat = loc.get("Latitude")
        lon = loc.get("Longitude")

        # Skip entries with missing coordinates
        if not lat or not lon:
            continue

        # Skip empty locations
        occupancy = loc.get("Occupancy", 0) or 0
        if occupancy <= 0:
            continue

        distance = _distance_km(eq_lat, eq_lon, lat, lon)

        if distance <= AFFECTED_RADIUS_KM:
            affected.append({
                "location_id": loc.get("LocationID"),
                "name": loc.get("GroupID", "Unknown"),
                "place": loc.get("PlaceID", "Unknown"),
                "occupancy": occupancy,
                "max_occupancy": loc.get("MaxOccupancy"),
                "scan_mode": loc.get("ScanMode", "UNKNOWN"),
                "distance_from_epicentre_km": round(distance, 1),
                "last_updated": loc.get("Timestamp"),
            })

    # Sort by most people first so the broadcast leads with highest-risk locations
    affected.sort(key=lambda x: x["occupancy"], reverse=True)
    return affected


# Building the full earthquake alert report

def get_earthquake_alert():
    """
    Main entry point. Checks for qualifying earthquakes and returns
    a structured alert report combining quake data + affected occupancy.

    Returns:
        None        — if no qualifying earthquakes found
        dict        — alert report if a qualifying earthquake is detected
    """
    print("[earthquake_tool] Checking USGS for recent earthquakes...")
    earthquakes = fetch_recent_earthquakes()

    if not earthquakes:
        print("[earthquake_tool] No qualifying earthquakes detected.")
        return None

    print(f"[earthquake_tool] {len(earthquakes)} earthquake(s) detected. Fetching occupancy data...")
    occupancy_data = fetch_occupancy()

    # Process the most recent qualifying earthquake first
    eq = earthquakes[0]
    affected_locations = find_affected_locations(
        eq["latitude"], eq["longitude"], occupancy_data
    )

    total_people_at_risk = sum(loc["occupancy"] for loc in affected_locations)

    report = {
        "earthquake": eq,
        "affected_locations": affected_locations,
        "total_locations_affected": len(affected_locations),
        "total_people_at_risk": total_people_at_risk,
        "alert_level": _get_alert_level(eq["magnitude"], total_people_at_risk),
        "broadcast_summary": _build_broadcast_summary(eq, affected_locations, total_people_at_risk),
    }

    print(f"[earthquake_tool] Alert ready — M{eq['magnitude']} quake, "
          f"{len(affected_locations)} locations affected, "
          f"{total_people_at_risk} people at risk.")

    return report


# Determine alert level

def _get_alert_level(magnitude, people_at_risk):
    """
    Returns a simple alert level string based on magnitude and exposure.
    """
    if magnitude >= 6.0 or people_at_risk >= 500:
        return "CRITICAL"
    elif magnitude >= 5.5 or people_at_risk >= 100:
        return "HIGH"
    else:
        return "MODERATE"


# ── Helper: Build a plain-English summary for the Executive Producer ───────────

def _build_broadcast_summary(eq, affected_locations, total_people):
    """
    Builds a plain-English prompt that gets passed to the Executive Producer
    to kick off the news pipeline.
    """
    location_lines = "\n".join(
        f"  - {loc['name']} ({loc['place']}): {loc['occupancy']} people, "
        f"{loc['distance_from_epicentre_km']}km from epicentre"
        for loc in affected_locations[:10]  # Top 10 most populated
    )

    summary = f"""[SHOW: breaking-news] EARTHQUAKE ALERT — IMMEDIATE BROADCAST REQUIRED

A magnitude {eq['magnitude']} earthquake has been detected {eq['distance_from_sacramento_km']}km 
from Sacramento at {eq['time']}.

Location: {eq['location']}
Depth: {eq['depth_km']}km
USGS Reference: {eq['usgs_url']}

AFFECTED LOCATIONS WITH OCCUPANCY ({len(affected_locations)} total, {total_people} people at risk):
{location_lines if location_lines else '  No occupied locations detected within affected radius.'}

Please produce an urgent breaking news broadcast alerting first responders to the above 
occupancy data. Prioritise the locations with the highest number of people. Include guidance 
that first responders should check all listed locations immediately.
"""
    return summary

#Simulation of Earthquake, present this:

def simulate_earthquake_alert():
    """
    Simulates a M5.5 earthquake near Sacramento for testing purposes.
    Bypasses the USGS API and uses fake quake data, but fetches REAL occupancy data.
    """
    fake_earthquake = {
        "id": "test-quake-001",
        "magnitude": 5.5,
        "location": "8km NE of Sacramento, CA",
        "latitude": 38.6200,
        "longitude": -121.4100,
        "depth_km": 10.0,
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "distance_from_sacramento_km": 8.1,
        "usgs_url": "https://earthquake.usgs.gov",
    }

    print("[SIMULATION] Fetching real occupancy data...")
    occupancy_data = fetch_occupancy()
    affected = find_affected_locations(
        fake_earthquake["latitude"],
        fake_earthquake["longitude"],
        occupancy_data
    )

    total_people = sum(loc["occupancy"] for loc in affected)

    return {
        "earthquake": fake_earthquake,
        "affected_locations": affected,
        "total_locations_affected": len(affected),
        "total_people_at_risk": total_people,
        "alert_level": _get_alert_level(fake_earthquake["magnitude"], total_people),
        "broadcast_summary": _build_broadcast_summary(fake_earthquake, affected, total_people),
    }


# ── Quick test ─────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    alert = get_earthquake_alert()
    if alert:
        print("\n=== EARTHQUAKE ALERT ===")
        print(alert["broadcast_summary"])
    else:
        print("No earthquake alerts at this time.")


# # Simulate 5.5 Earthquake
# if __name__ == "__main__":
#     import sys
#     if "simulate" in sys.argv:
#         print("[SIMULATION MODE] Generating fake M5.5 earthquake near Sacramento...")
#         alert = simulate_earthquake_alert()
#     else:
#         alert = get_earthquake_alert()

#     if alert:
#         print("\n=== EARTHQUAKE ALERT ===")
#         print(f"Magnitude: {alert['earthquake']['magnitude']}")
#         print(f"Location: {alert['earthquake']['location']}")
#         print(f"Alert Level: {alert['alert_level']}")
#         print(f"People at risk: {alert['total_people_at_risk']}")
#         print(f"Locations affected: {alert['total_locations_affected']}")
#         print("\n--- BROADCAST SUMMARY ---")
#         print(alert["broadcast_summary"])
#     else:
#         print("No earthquake alerts at this time.")