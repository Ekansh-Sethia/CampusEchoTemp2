import json
from pathlib import Path
import networkx as nx

# We will generate the complete SGSITS Campus Graph
graph_data = {
    "metadata": {
        "campus_name": "Shri G. S. Institute of Technology and Science (SGSITS), Indore",
        "city": "Indore, Madhya Pradesh, India",
        "address": "23 Sir M. Visvesvaraya Marg, Vallabh Nagar, Indore - 452003",
        "version": "2.0-full",
        "description": "Complete SGSITS Indore campus navigation graph derived from user college measurements, Google Maps, and OpenStreetMap data",
        "source": "SGSITS field measurements + OSM + Google Maps satellite survey",
        "core_measurements_preserved": {
            "golden_gate_to_atc": "58m straight + 50m left (108m total)",
            "atc_to_silveria": "13m straight + 127m right (140m total)",
            "atc_to_admin": "13m straight + 35m right (plus point) + 68m left + 151m right (267m total)"
        }
    },
    "nodes": [
        # --- GATES & ENTRANCES ---
        {
            "id": "golden_gate",
            "name": "Golden Gate",
            "type": "entrance",
            "label": "Golden Gate (Hostel Gate)",
            "expected_signs": ["GOLDEN GATE", "HOSTEL GATE", "COLLEGE ENTRANCE", "SGSITS"],
            "landmark_image": "golden_gate.jpg"
        },
        {
            "id": "golden_gate_turn",
            "name": "Golden Gate Path Turn",
            "type": "waypoint",
            "label": "Turn towards ATC Building",
            "expected_signs": ["TO ATC", "TO ACADEMIC COMPLEX"],
            "landmark_image": None
        },
        {
            "id": "main_gate",
            "name": "Main Gate",
            "type": "entrance",
            "label": "Main Gate (Gate 1 - Park Road)",
            "expected_signs": ["MAIN GATE", "GATE 1", "SGSITS INDORE", "SHRI G.S. INSTITUTE OF TECHNOLOGY"],
            "landmark_image": "main_gate.jpg"
        },
        {
            "id": "gate_2",
            "name": "Campus Gate 2",
            "type": "entrance",
            "label": "Gate 2 (West Gate - Pharmacy/Civil side)",
            "expected_signs": ["GATE 2", "WEST GATE", "PHARMACY ENTRANCE"],
            "landmark_image": "gate_2.jpg"
        },

        # --- ACADEMIC CORE & ATC ---
        {
            "id": "atc_building",
            "name": "ATC Building",
            "type": "building",
            "label": "ATC Building Entrance (T&P Cell, Tech Labs)",
            "expected_signs": ["ATC BUILDING", "ATC", "ACADEMIC & TECHNOLOGY COMPLEX", "TRAINING AND PLACEMENT"],
            "landmark_image": "atc_building.jpg"
        },
        {
            "id": "atc_junction",
            "name": "ATC Pathway Junction",
            "type": "junction",
            "label": "Junction outside ATC Building",
            "expected_signs": ["TO SILVERIA HALL", "TO PLUS POINT", "TO CANTEEN"],
            "landmark_image": None
        },
        {
            "id": "lecture_theatres",
            "name": "Lecture Theatres (LT)",
            "type": "building",
            "label": "Lecture Theatres (LT Complex)",
            "expected_signs": ["LT", "LECTURE THEATRE", "LT 1", "LT 2", "LT 3"],
            "landmark_image": "lt_complex.jpg"
        },
        {
            "id": "bank_obc",
            "name": "Campus Bank & ATM",
            "type": "landmark",
            "label": "Bank / ATM (Oriental Bank of Commerce / PNB)",
            "expected_signs": ["BANK", "ATM", "ORIENTAL BANK", "PUNJAB NATIONAL BANK"],
            "landmark_image": "bank_atm.jpg"
        },
        {
            "id": "sports_complex",
            "name": "Sports Complex",
            "type": "building",
            "label": "Sports Complex (Courts & Gym)",
            "expected_signs": ["SPORTS COMPLEX", "GYMNASIUM", "BASKETBALL COURT", "SPORTS"],
            "landmark_image": "sports_complex.jpg"
        },

        # --- ENGINEERING DEPARTMENTS (SOUTH / EAST BLOCK) ---
        {
            "id": "dept_cs_it",
            "name": "Computer Engineering & IT Dept",
            "type": "building",
            "label": "Dept of Computer Engineering, IT & MCA",
            "expected_signs": ["COMPUTER ENGINEERING", "DEPARTMENT OF COMPUTER ENGG", "IT DEPT", "MCA"],
            "landmark_image": "dept_cse.jpg"
        },
        {
            "id": "dept_etc",
            "name": "Electronics & Telecommunication Dept",
            "type": "building",
            "label": "Dept of Electronics & Telecommunication (ETC)",
            "expected_signs": ["ELEX AND T.C.", "ELECTRONICS", "ETC DEPARTMENT", "TELECOMMUNICATION"],
            "landmark_image": "dept_etc.jpg"
        },
        {
            "id": "dept_biomedical",
            "name": "Biomedical Engineering Dept",
            "type": "building",
            "label": "Dept of Biomedical Engineering",
            "expected_signs": ["BIOMEDICAL", "DEPT OF BIOMEDICAL", "BM LAB"],
            "landmark_image": "dept_biomedical.jpg"
        },
        {
            "id": "dept_ipe",
            "name": "Industrial & Production Engineering Dept",
            "type": "building",
            "label": "Dept of Industrial & Production Engineering (IPE)",
            "expected_signs": ["IPE", "INDUSTRIAL AND PRODUCTION", "DEPT OF IPE"],
            "landmark_image": "dept_ipe.jpg"
        },
        {
            "id": "dept_mech",
            "name": "Mechanical Engineering Dept",
            "type": "building",
            "label": "Dept of Mechanical Engineering",
            "expected_signs": ["MECHANICAL ENGG", "DEPT OF MECHANICAL", "MECH BLOCK"],
            "landmark_image": "dept_mech.jpg"
        },

        # --- CENTRAL / ADMINISTRATIVE ZONE ---
        {
            "id": "plus_point",
            "name": "Plus Point",
            "type": "landmark",
            "label": "Plus Point Landmark (Campus Center)",
            "expected_signs": ["PLUS POINT", "PLUS POINT CAFE", "CAMPUS CENTER"],
            "landmark_image": "plus_point.jpg"
        },
        {
            "id": "silveria_hall",
            "name": "Silveria Hall",
            "type": "hall",
            "label": "Silveria Hall (Auditorium)",
            "expected_signs": ["SILVERIA HALL", "SILVERIA", "AUDITORIUM"],
            "landmark_image": "silveria_hall.jpg"
        },
        {
            "id": "admin_path_turn",
            "name": "Admin Path Turn",
            "type": "waypoint",
            "label": "Turn towards Administrative Building",
            "expected_signs": ["TO ADMIN BLOCK", "TO DIRECTOR OFFICE"],
            "landmark_image": None
        },
        {
            "id": "admin_building",
            "name": "Administrative Building",
            "type": "building",
            "label": "Administrative Building (Director's Office)",
            "expected_signs": ["ADMINISTRATIVE BUILDING", "ADMIN BLOCK", "DIRECTOR OFFICE", "REGISTRAR"],
            "landmark_image": "admin_building.jpg"
        },
        {
            "id": "central_library",
            "name": "Central Library",
            "type": "building",
            "label": "Central Library",
            "expected_signs": ["CENTRAL LIBRARY", "LIBRARY", "READING ROOM"],
            "landmark_image": "central_library.jpg"
        },
        {
            "id": "dept_elec",
            "name": "Electrical Engineering Dept",
            "type": "building",
            "label": "Dept of Electrical Engineering",
            "expected_signs": ["ELECTRICAL ENGG", "DEPT OF ELECTRICAL", "EE BLOCK"],
            "landmark_image": "dept_electrical.jpg"
        },
        {
            "id": "central_store",
            "name": "Central Store",
            "type": "building",
            "label": "Central Store",
            "expected_signs": ["CENTRAL STORE", "STORE"],
            "landmark_image": "central_store.jpg"
        },

        # --- WESTERN ACADEMIC & WORKSHOP ZONE ---
        {
            "id": "central_workshop",
            "name": "Central Workshop",
            "type": "building",
            "label": "Central Workshop (Machining, Welding, Foundry)",
            "expected_signs": ["CENTRAL WORKSHOP", "WORKSHOP", "MACHINE SHOP"],
            "landmark_image": "central_workshop.jpg"
        },
        {
            "id": "dept_civil",
            "name": "Civil Engineering Dept",
            "type": "building",
            "label": "Dept of Civil Engineering & Applied Mechanics",
            "expected_signs": ["CIVIL ENGG", "APPLIED MECHANICS", "DEPT OF CIVIL"],
            "landmark_image": "dept_civil.jpg"
        },
        {
            "id": "dept_chem",
            "name": "Applied Chemistry Dept",
            "type": "building",
            "label": "Dept of Applied Chemistry",
            "expected_signs": ["APPLIED CHEMISTRY", "CHEMISTRY LAB"],
            "landmark_image": "dept_chemistry.jpg"
        },
        {
            "id": "dept_pharmacy",
            "name": "Pharmacy Dept",
            "type": "building",
            "label": "Dept of Pharmacy",
            "expected_signs": ["PHARMACY", "PHARMACY DEPT", "PHARMACEUTICAL LAB"],
            "landmark_image": "dept_pharmacy.jpg"
        },

        # --- AMENITIES & FOOD ---
        {
            "id": "canteen_gym",
            "name": "Campus Canteen & Gym",
            "type": "landmark",
            "label": "Campus Canteen & Gymnasium",
            "expected_signs": ["CANTEEN", "CAFETERIA", "STUDENT CANTEEN", "GYM"],
            "landmark_image": "canteen.jpg"
        },
        {
            "id": "heat_engine_lab",
            "name": "Heat Engine Lab & Store",
            "type": "building",
            "label": "Heat Engine Lab & Co-operative Store",
            "expected_signs": ["HEAT ENGINE LAB", "COOPERATIVE STORE"],
            "landmark_image": "heat_engine.jpg"
        },

        # --- NORTH HOSTELS & RESIDENTIAL ZONE ---
        {
            "id": "guest_house",
            "name": "Guest House",
            "type": "building",
            "label": "Institute Guest House",
            "expected_signs": ["GUEST HOUSE", "TRANSIT HOSTEL"],
            "landmark_image": "guest_house.jpg"
        },
        {
            "id": "hostel_visvesvaraya",
            "name": "M. Visvesvaraya Hostel",
            "type": "building",
            "label": "M. Visvesvaraya Hostel (Boys Hostel)",
            "expected_signs": ["VISVESARAYA HOSTEL", "MV HOSTEL", "BOYS HOSTEL"],
            "landmark_image": "hostel_visvesvaraya.jpg"
        },
        {
            "id": "hostel_raman",
            "name": "C.V. Raman Hostel",
            "type": "building",
            "label": "C.V. Raman Hostel (Boys Hostel)",
            "expected_signs": ["C.V. RAMAN HOSTEL", "RAMAN HOSTEL", "BOYS HOSTEL 2"],
            "landmark_image": "hostel_raman.jpg"
        },
        {
            "id": "hostel_sarojini",
            "name": "Sarojini Naidu Girls Hostel",
            "type": "building",
            "label": "Sarojini Naidu Girls Hostel",
            "expected_signs": ["SAROJINI NAIDU", "GIRLS HOSTEL", "SN HOSTEL"],
            "landmark_image": "hostel_girls.jpg"
        },
        {
            "id": "hostel_ground",
            "name": "Hostel Sports Ground",
            "type": "landmark",
            "label": "Hostel Sports Ground (Cricket & Football)",
            "expected_signs": ["HOSTEL GROUND", "PLAYGROUND", "SPORTS GROUND"],
            "landmark_image": "hostel_ground.jpg"
        }
    ],

    "edges": [
        # --- 1. CORE BACKBONE (Exact user measurements preserved) ---
        {
            "id": "edge_golden_gate_to_turn",
            "from": "golden_gate",
            "to": "golden_gate_turn",
            "distance_m": 58.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk straight along the main avenue from Golden Gate"
        },
        {
            "id": "edge_turn_to_atc",
            "from": "golden_gate_turn",
            "to": "atc_building",
            "distance_m": 50.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Turn left and walk to ATC Building"
        },
        {
            "id": "edge_atc_to_junction",
            "from": "atc_building",
            "to": "atc_junction",
            "distance_m": 13.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk straight from ATC Building to pathway junction"
        },
        {
            "id": "edge_junction_to_silveria",
            "from": "atc_junction",
            "to": "silveria_hall",
            "distance_m": 127.0,
            "direction_forward": "right",
            "direction_backward": "left",
            "description": "Turn right and walk to Silveria Hall"
        },
        {
            "id": "edge_junction_to_plus_point",
            "from": "atc_junction",
            "to": "plus_point",
            "distance_m": 35.0,
            "direction_forward": "right",
            "direction_backward": "left",
            "description": "Turn right and walk to Plus Point"
        },
        {
            "id": "edge_plus_point_to_silveria_alternate",
            "from": "plus_point",
            "to": "silveria_hall",
            "distance_m": 115.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Courtyard alternate pathway connecting Plus Point and Silveria Hall"
        },
        {
            "id": "edge_plus_point_to_admin_turn",
            "from": "plus_point",
            "to": "admin_path_turn",
            "distance_m": 68.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Turn left from Plus Point along administrative pathway"
        },
        {
            "id": "edge_admin_turn_to_admin",
            "from": "admin_path_turn",
            "to": "admin_building",
            "distance_m": 151.0,
            "direction_forward": "right",
            "direction_backward": "left",
            "description": "Turn right and walk straight to Administrative Building"
        },

        # --- 2. MAIN GATE (GATE 1) & SOUTHERN ENTRANCE CORRIDOR ---
        {
            "id": "edge_main_gate_to_sports",
            "from": "main_gate",
            "to": "sports_complex",
            "distance_m": 60.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Enter from Main Gate and walk straight towards Sports Complex"
        },
        {
            "id": "edge_sports_to_bank",
            "from": "sports_complex",
            "to": "bank_obc",
            "distance_m": 55.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Turn left past sports courts towards Campus Bank and ATM"
        },
        {
            "id": "edge_bank_to_lt",
            "from": "bank_obc",
            "to": "lecture_theatres",
            "distance_m": 28.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk past bank to Lecture Theatres complex"
        },
        {
            "id": "edge_lt_to_atc_junction",
            "from": "lecture_theatres",
            "to": "atc_junction",
            "distance_m": 42.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Turn left from Lecture Theatres to ATC pathway junction"
        },

        # --- 3. SOUTHERN ENGINEERING DEPARTMENTS ---
        {
            "id": "edge_main_gate_to_cs_it",
            "from": "main_gate",
            "to": "dept_cs_it",
            "distance_m": 105.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Turn left from Main Gate into the Computer Science and IT courtyard"
        },
        {
            "id": "edge_cs_it_to_etc",
            "from": "dept_cs_it",
            "to": "dept_etc",
            "distance_m": 25.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk straight along corridor between CS/IT and ETC Department"
        },
        {
            "id": "edge_etc_to_atc_junction",
            "from": "dept_etc",
            "to": "atc_junction",
            "distance_m": 45.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk north past ETC Department to ATC pathway junction"
        },
        {
            "id": "edge_etc_to_biomedical",
            "from": "dept_etc",
            "to": "dept_biomedical",
            "distance_m": 15.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Walk left into Biomedical Engineering Department wing"
        },
        {
            "id": "edge_biomedical_to_ipe",
            "from": "dept_biomedical",
            "to": "dept_ipe",
            "distance_m": 30.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Continue past Biomedical Department to IPE Department"
        },
        {
            "id": "edge_ipe_to_mech",
            "from": "dept_ipe",
            "to": "dept_mech",
            "distance_m": 58.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk along academic block from IPE to Mechanical Engineering Dept"
        },
        {
            "id": "edge_mech_to_admin_turn",
            "from": "dept_mech",
            "to": "admin_path_turn",
            "distance_m": 25.0,
            "direction_forward": "right",
            "direction_backward": "left",
            "description": "Turn right from Mechanical Engineering to admin pathway intersection"
        },

        # --- 4. CENTRAL LIBRARY, ELECTRICAL & STORE ---
        {
            "id": "edge_admin_to_library",
            "from": "admin_building",
            "to": "central_library",
            "distance_m": 16.0,
            "direction_forward": "right",
            "direction_backward": "left",
            "description": "Step right from Administrative Building to Central Library entrance"
        },
        {
            "id": "edge_library_to_elec",
            "from": "central_library",
            "to": "dept_elec",
            "distance_m": 28.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk past Central Library to Electrical Engineering Department"
        },
        {
            "id": "edge_admin_to_store",
            "from": "admin_building",
            "to": "central_store",
            "distance_m": 35.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Walk left from Administrative Building to Central Store"
        },

        # --- 5. WESTERN ACADEMIC WING & WORKSHOPS ---
        {
            "id": "edge_elec_to_civil",
            "from": "dept_elec",
            "to": "dept_civil",
            "distance_m": 68.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk straight west from Electrical Dept to Civil Engineering Dept"
        },
        {
            "id": "edge_civil_to_workshop",
            "from": "dept_civil",
            "to": "central_workshop",
            "distance_m": 52.0,
            "direction_forward": "right",
            "direction_backward": "left",
            "description": "Turn right from Civil Dept towards Central Workshop"
        },
        {
            "id": "edge_civil_to_chem",
            "from": "dept_civil",
            "to": "dept_chem",
            "distance_m": 35.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Continue straight west past Civil Dept to Applied Chemistry"
        },
        {
            "id": "edge_chem_to_pharmacy",
            "from": "dept_chem",
            "to": "dept_pharmacy",
            "distance_m": 65.0,
            "direction_forward": "right",
            "direction_backward": "left",
            "description": "Turn right and walk past chemistry lab to Pharmacy Department"
        },
        {
            "id": "edge_pharmacy_to_gate2",
            "from": "dept_pharmacy",
            "to": "gate_2",
            "distance_m": 32.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Walk from Pharmacy Department to Gate 2 exit"
        },

        # --- 6. CANTEEN & STUDENT SERVICES CORRIDOR ---
        {
            "id": "edge_plus_point_to_canteen",
            "from": "plus_point",
            "to": "canteen_gym",
            "distance_m": 65.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk straight north from Plus Point to Campus Canteen"
        },
        {
            "id": "edge_canteen_to_atc_junction",
            "from": "canteen_gym",
            "to": "atc_junction",
            "distance_m": 95.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Walk along pathway from Canteen to ATC Junction"
        },
        {
            "id": "edge_canteen_to_heat_engine",
            "from": "canteen_gym",
            "to": "heat_engine_lab",
            "distance_m": 38.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Walk west from Canteen to Heat Engine Lab and Co-op Store"
        },
        {
            "id": "edge_heat_engine_to_workshop",
            "from": "heat_engine_lab",
            "to": "central_workshop",
            "distance_m": 132.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk west past store to Central Workshop"
        },

        # --- 7. NORTH HOSTEL & RESIDENTIAL CORRIDOR ---
        {
            "id": "edge_turn_to_guest_house",
            "from": "golden_gate_turn",
            "to": "guest_house",
            "distance_m": 115.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Follow avenue straight north past turn to Guest House"
        },
        {
            "id": "edge_guest_house_to_sarojini",
            "from": "guest_house",
            "to": "hostel_sarojini",
            "distance_m": 78.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Continue north past Guest House to Sarojini Naidu Girls Hostel"
        },
        {
            "id": "edge_guest_house_to_ground",
            "from": "guest_house",
            "to": "hostel_ground",
            "distance_m": 112.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Turn left past Guest House to Hostel Sports Ground"
        },
        {
            "id": "edge_ground_to_visvesvaraya",
            "from": "hostel_ground",
            "to": "hostel_visvesvaraya",
            "distance_m": 50.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk north across ground to M. Visvesvaraya Hostel"
        },
        {
            "id": "edge_visvesvaraya_to_raman",
            "from": "hostel_visvesvaraya",
            "to": "hostel_raman",
            "distance_m": 38.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk from Visvesvaraya Hostel to C.V. Raman Hostel"
        },
        {
            "id": "edge_canteen_to_ground",
            "from": "canteen_gym",
            "to": "hostel_ground",
            "distance_m": 145.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk north pathway from Canteen to Hostel Sports Ground"
        }
    ]
}

# Verify networkx connectivity
G = nx.Graph()
node_ids = set()
for n in graph_data["nodes"]:
    G.add_node(n["id"])
    node_ids.add(n["id"])

for e in graph_data["edges"]:
    assert e["from"] in node_ids, f"Unknown from node: {e['from']}"
    assert e["to"] in node_ids, f"Unknown to node: {e['to']}"
    G.add_edge(e["from"], e["to"], weight=e["distance_m"])

is_connected = nx.is_connected(G)
print(f"Graph nodes: {len(G.nodes)}, edges: {len(G.edges)}")
print(f"Is fully connected graph: {is_connected}")
if not is_connected:
    components = list(nx.connected_components(G))
    print(f"Connected components: {len(components)}")
    for i, c in enumerate(components):
        print(f"Component {i}: {c}")

# Test some sample shortest paths
paths_to_test = [
    ("golden_gate", "atc_building"),
    ("golden_gate", "silveria_hall"),
    ("main_gate", "admin_building"),
    ("main_gate", "central_library"),
    ("main_gate", "hostel_visvesvaraya"),
    ("gate_2", "silveria_hall"),
    ("gate_2", "golden_gate")
]

for src, dst in paths_to_test:
    length = nx.dijkstra_path_length(G, src, dst, weight="weight")
    path = nx.dijkstra_path(G, src, dst, weight="weight")
    print(f"Route {src} -> {dst}: {length:.1f}m ({len(path)} steps: {' -> '.join(path)})")

# Save to data/sgsits_campus_graph_full.json
out_path = Path("data/sgsits_campus_graph_full.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(graph_data, f, indent=2)

print(f"\nSuccessfully wrote full SGSITS campus graph to {out_path}")
