import json
import math
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

with open("scratch/sgsits_osm_raw.json", "r", encoding="utf-8") as f:
    data = json.load(f)

elements = data.get("elements", [])
print(f"Total elements: {len(elements)}")

nodes = {}
ways = []
for el in elements:
    if el.get("type") == "node":
        nodes[el["id"]] = (el.get("lat"), el.get("lon"), el.get("tags", {}))
    elif el.get("type") == "way":
        ways.append(el)

print(f"Nodes: {len(nodes)}, Ways: {len(ways)}")

# Haversine distance in meters
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# Look for SGSITS specific named nodes and ways
print("\n--- SGSITS / CAMPUS NAMED BUILDINGS & AMENITIES ---")
campus_features = []
for el in elements:
    tags = el.get("tags", {})
    name = tags.get("name", "")
    if name:
        campus_features.append((el.get("type"), el.get("id"), name, tags))

for t, eid, name, tags in sorted(campus_features, key=lambda x: x[2]):
    btype = tags.get("building", tags.get("amenity", tags.get("highway", tags.get("leisure", ""))))
    desc = f"{name} ({t} {eid}, type={btype})"
    print(desc)
