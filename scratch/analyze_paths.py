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

# Look at all ways tagged with highway=service, footway, path, pedestrian
path_ways = []
for wid, w in ways.items():
    tags = w.get("tags", {})
    if "highway" in tags:
        nd_ids = w.get("nodes", [])
        w_nodes = [nodes[i] for i in nd_ids if i in nodes]
        # check if in campus bounds
        in_campus = [n for n in w_nodes if 22.7245 <= n["lat"] <= 22.7285 and 75.8690 <= n["lon"] <= 75.8750]
        if len(in_campus) >= 2:
            path_ways.append((wid, tags, w_nodes))

print(f"Found {len(path_ways)} walkable/service pathways inside campus:\n")
for wid, tags, w_nodes in path_ways:
    hw_type = tags.get("highway")
    name = tags.get("name", "unnamed")
    total_len = 0.0
    for i in range(len(w_nodes)-1):
        total_len += haversine(w_nodes[i]["lat"], w_nodes[i]["lon"], w_nodes[i+1]["lat"], w_nodes[i+1]["lon"])
    print(f"Way {wid} ({hw_type}, '{name}'): length {total_len:.1f}m, {len(w_nodes)} pts, start ({w_nodes[0]['lat']:.5f}, {w_nodes[0]['lon']:.5f}), end ({w_nodes[-1]['lat']:.5f}, {w_nodes[-1]['lon']:.5f})")
