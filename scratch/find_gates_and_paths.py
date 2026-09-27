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

# Look for gates or barriers
print("--- BARRIERS / GATES ---")
for nid, n in nodes.items():
    tags = n.get("tags", {})
    if "barrier" in tags or "gate" in tags.get("entrance", "") or "gate" in tags.get("name", "").lower():
        print(f"Node {nid}: {n.get('lat')}, {n.get('lon')} - tags: {tags}")

# Check all nodes with names
print("\n--- ALL NAMED NODES IN CAMPUS AREA ---")
for nid, n in nodes.items():
    tags = n.get("tags", {})
    if tags.get("name") and 22.722 <= n.get("lat", 0) <= 22.728 and 75.869 <= n.get("lon", 0) <= 75.877:
        print(f"Named Node {nid} ({n.get('lat')}, {n.get('lon')}): {tags.get('name')} - {tags}")

# Check highways / service roads within campus
print("\n--- CAMPUS HIGHWAY WAYS ---")
campus_ways = []
for wid, w in ways.items():
    tags = w.get("tags", {})
    if "highway" in tags:
        # Check if way passes through campus box
        nd_ids = w.get("nodes", [])
        w_nodes = [nodes[i] for i in nd_ids if i in nodes]
        in_campus = any(22.723 <= n["lat"] <= 22.7275 and 75.8695 <= n["lon"] <= 75.8755 for n in w_nodes)
        if in_campus:
            campus_ways.append((wid, tags, w_nodes))

print(f"Found {len(campus_ways)} campus road/path ways")
for wid, tags, w_nodes in campus_ways[:15]:
    name = tags.get("name", "unnamed")
    hw = tags.get("highway")
    print(f"Way {wid}: {hw} '{name}', {len(w_nodes)} points, from ({w_nodes[0]['lat']:.5f},{w_nodes[0]['lon']:.5f}) to ({w_nodes[-1]['lat']:.5f},{w_nodes[-1]['lon']:.5f})")
