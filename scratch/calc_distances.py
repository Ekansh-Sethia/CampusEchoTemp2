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
        campus_bldgs[name] = {"lat": lat, "lon": lon}

# Also let's find the position of Silveria Hall and Plus Point!
# Silveria Hall in campus_graph.json is 127m from atc_junction.
# Let's search if Silveria or any other hall is in the way nodes or unnamed ways.
print("--- ALL WAYS IN CAMPUS (including unnamed buildings/ways) ---")
for wid, w in ways.items():
    tags = w.get("tags", {})
    lat, lon = get_way_centroid(w)
    if lat and 22.7245 <= lat <= 22.7265 and 75.8700 <= lon <= 75.8745:
        if "building" in tags:
            print(f"Bldg {wid}: {tags.get('name', 'unnamed')} ({lat:.6f}, {lon:.6f}) - tags: {tags}")

# Compute distance matrix between key buildings
bldg_names = [
    "ATC", "CANTEEN , GYM", "Central Library", "Central Workshop", 
    "DIRECTOR OFFICE", "DEPT OF COMPUTER ENGG,APPLIED PHYSICS,ELEX AND INSTRU. ENGG,MCA",
    "DEPT OF ELECTRICAL ENGG", "DEPT OF CIVIL ENGG AND APPLIED MECHANICS",
    "DEPT OF MECHANICAL ENGG", "Sport Complex", "LT", "M. VISVESARAYA HOSTEL", "SAROJINI NAUDU GIRLS HOSTEL"
]

print("\n--- DISTANCES FROM ATC ---")
atc = campus_bldgs["ATC"]
for b in sorted(campus_bldgs.keys()):
    if b != "ATC":
        d = haversine(atc["lat"], atc["lon"], campus_bldgs[b]["lat"], campus_bldgs[b]["lon"])
        print(f"ATC -> {b}: {d:.1f} m")

print("\n--- DISTANCES FROM DIRECTOR OFFICE (ADMIN BLOCK) ---")
admin = campus_bldgs["DIRECTOR OFFICE"]
for b in sorted(campus_bldgs.keys()):
    if b != "DIRECTOR OFFICE":
        d = haversine(admin["lat"], admin["lon"], campus_bldgs[b]["lat"], campus_bldgs[b]["lon"])
        print(f"Director Office -> {b}: {d:.1f} m")
