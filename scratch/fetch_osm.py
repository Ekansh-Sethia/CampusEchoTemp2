import urllib.request
import urllib.parse
import json
import sys
from pathlib import Path

# Fix stdout encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

bbox = "22.721,75.870,22.728,75.878"

query = f"""
[out:json][timeout:45];
(
  way["building"]({bbox});
  node["amenity"]({bbox});
  node["name"]({bbox});
  way["highway"]({bbox});
  node["barrier"]({bbox});
  way["leisure"]({bbox});
);
out body;
>;
out skel qt;
"""

url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(query)
req = urllib.request.Request(url, headers={"User-Agent": "CampusEchoMapper/1.0"})

try:
    print("Fetching OSM data for SGSITS Indore...")
    with urllib.request.urlopen(req, timeout=35) as resp:
        content = resp.read().decode("utf-8")
        data = json.loads(content)
        
    elements = data.get("elements", [])
    print(f"Total elements fetched: {len(elements)}")
    
    # Save raw data to scratch with utf-8
    out_file = Path("scratch/sgsits_osm_raw.json")
    out_file.parent.mkdir(exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved raw OSM data to {out_file}")

except Exception as e:
    print(f"Error fetching OSM data: {e}")
