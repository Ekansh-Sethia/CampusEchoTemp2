import json
import math
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("scratch/sgsits_osm_raw.json", "r", encoding="utf-8") as f:
    data = json.load(f)

elements = data.get("elements", [])
nodes = {el["id"]: el for el in elements if el.get("type") == "node"}
ways = {el["id"]: el for el in elements if el.get("type") == "way"}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_way_centroid(way):
    nd_ids = way.get("nodes", [])
    lats = [nodes[nid]["lat"] for nid in nd_ids if nid in nodes]
    lons = [nodes[nid]["lon"] for nid in nd_ids if nid in nodes]
    if lats and lons:
        return sum(lats)/len(lats), sum(lons)/len(lons)
    return None, None

# Find all ways with building tags or campus relevant tags
campus_bldgs = {}
for wid, way in ways.items():
    tags = way.get("tags", {})
    name = tags.get("name")
    if name and any(keyword in name.upper() for keyword in [
        "ATC", "DEPT", "HOSTEL", "CANTEEN", "LIBRARY", "WORKSHOP", 
        "DIRECTOR", "STORE", "SPORT", "PHARMACY", "FACULTY", "GUEST",
        "LAB", "LT", "BANK", "VISVESARAYA", "RAMAN", "SAROJINI"
    ]):
        lat, lon = get_way_centroid(way)
        campus_bldgs[name] = {"id": wid, "lat": lat, "lon": lon, "tags": tags}

print(f"Extracted {len(campus_bldgs)} campus buildings:\n")
for name, info in sorted(campus_bldgs.items()):
    print(f"- {name}: Lat {info['lat']:.6f}, Lon {info['lon']:.6f}")

# Look at roads/footways inside the campus bounding area (lat ~22.723 to 22.727, lon ~75.872 to 75.877)
internal_highways = []
for wid, way in ways.items():
    tags = way.get("tags", {})
    if "highway" in tags:
        lat, lon = get_way_centroid(way)
        if lat and 22.7225 <= lat <= 22.7275 and 75.8715 <= lon <= 75.8775:
            internal_highways.append((wid, tags.get("highway"), tags.get("name", "unnamed internal road"), way.get("nodes", [])))

print(f"\nInternal Campus Road/Path segments: {len(internal_highways)}")
