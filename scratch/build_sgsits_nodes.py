import json
import math
from pathlib import Path

# Load raw OSM data
with open("scratch/sgsits_osm_raw.json", "r", encoding="utf-8") as f:
    osm_data = json.load(f)

# Helper for haversine distance
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return round(2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)

# Full SGSITS Campus Graph
# Incorporating the user's verified measurements for the core spine + OSM/Google Maps measured distances
nodes = [
    # --- ENTRANCE GATES ---
    {
        "id": "golden_gate",
        "name": "Golden Gate",
        "type": "entrance",
        "label": "Golden Gate (Hostel Gate)",
        "expected_signs": ["GOLDEN GATE", "HOSTEL GATE", "COLLEGE ENTRANCE", "SGSITS"],
        "landmark_image": "golden_gate.jpg",
        "coordinates": {"lat": 22.72620, "lon": 75.87410}
    },
    {
        "id": "golden_gate_turn",
        "name": "Golden Gate Path Turn",
        "type": "waypoint",
        "label": "Turn towards ATC Building",
        "expected_signs": ["TO ATC", "TO ACADEMIC COMPLEX"],
        "landmark_image": None,
        "coordinates": {"lat": 22.72590, "lon": 75.87370}
    },
    {
        "id": "main_gate",
        "name": "SGSITS Main Gate",
        "type": "entrance",
        "label": "Main Gate (Gate 1 - Park Road)",
        "expected_signs": ["MAIN GATE", "GATE 1", "SGSITS INDORE", "SHRI G.S. INSTITUTE OF TECHNOLOGY"],
        "landmark_image": "main_gate.jpg",
        "coordinates": {"lat": 22.72473, "lon": 75.87414}
    },
    {
        "id": "gate_2",
        "name": "Campus Gate 2",
        "type": "entrance",
        "label": "Gate 2 (West Gate - Civil/Pharmacy side)",
        "expected_signs": ["GATE 2", "WEST GATE", "PHARMACY ENTRANCE"],
        "landmark_image": "gate_2.jpg",
        "coordinates": {"lat": 22.72486, "lon": 75.86993}
    },

    # --- ACADEMIC CORE ---
    {
        "id": "atc_building",
        "name": "ATC Building",
        "type": "building",
        "label": "ATC Building (T&P Cell, Tech Labs)",
        "expected_signs": ["ATC BUILDING", "ATC", "ACADEMIC & TECHNOLOGY COMPLEX", "TRAINING AND PLACEMENT"],
        "landmark_image": "atc_building.jpg",
        "coordinates": {"lat": 22.725840, "lon": 75.873201}
    },
    {
        "id": "atc_junction",
        "name": "ATC Pathway Junction",
        "type": "junction",
        "label": "Junction outside ATC Building",
        "expected_signs": ["TO SILVERIA HALL", "TO PLUS POINT", "TO CANTEEN"],
        "landmark_image": None,
        "coordinates": {"lat": 22.72573, "lon": 75.87315}
    },
    {
        "id": "lecture_theatres",
        "name": "Lecture Theatres (LT)",
        "type": "building",
        "label": "Lecture Theatres (LT Complex)",
        "expected_signs": ["LT", "LECTURE THEATRE", "LT 1", "LT 2", "LT 3"],
        "landmark_image": "lt_complex.jpg",
        "coordinates": {"lat": 22.725796, "lon": 75.873575}
    },
    {
        "id": "bank_obc",
        "name": "Campus Bank & ATM",
        "type": "landmark",
        "label": "Bank / ATM (Oriental Bank of Commerce)",
        "expected_signs": ["BANK", "ATM", "ORIENTAL BANK", "PUNJAB NATIONAL BANK"],
        "landmark_image": "bank_atm.jpg",
        "coordinates": {"lat": 22.725740, "lon": 75.873831}
    },
    {
        "id": "sports_complex",
        "name": "Sports Complex",
        "type": "building",
        "label": "Sports Complex (Badminton, Basketball & Gym)",
        "expected_signs": ["SPORTS COMPLEX", "GYMNASIUM", "BASKETBALL COURT", "SPORTS"],
        "landmark_image": "sports_complex.jpg",
        "coordinates": {"lat": 22.725244, "lon": 75.873701}
    },
    {
        "id": "dept_cs_it",
        "name": "Computer Engineering & IT Dept",
        "type": "building",
        "label": "Dept of Computer Engineering, IT & MCA",
        "expected_signs": ["COMPUTER ENGINEERING", "DEPARTMENT OF COMPUTER ENGG", "IT DEPT", "MCA"],
        "landmark_image": "dept_cse.jpg",
        "coordinates": {"lat": 22.725121, "lon": 75.873165}
    },
    {
        "id": "dept_etc",
        "name": "Electronics & Telecommunication Dept",
        "type": "building",
        "label": "Dept of Electronics and Telecommunication (ETC)",
        "expected_signs": ["ELEX AND T.C.", "ELECTRONICS", "ETC DEPARTMENT", "TELECOMMUNICATION"],
        "landmark_image": "dept_etc.jpg",
        "coordinates": {"lat": 22.725340, "lon": 75.873161}
    },
    {
        "id": "dept_biomedical",
        "name": "Biomedical Engineering Dept",
        "type": "building",
        "label": "Dept of Biomedical Engineering",
        "expected_signs": ["BIOMEDICAL", "DEPT OF BIOMEDICAL", "BM LAB"],
        "landmark_image": "dept_biomedical.jpg",
        "coordinates": {"lat": 22.725362, "lon": 75.873020}
    },
    {
        "id": "dept_ipe",
        "name": "Industrial & Production Engineering Dept",
        "type": "building",
        "label": "Dept of Industrial and Production Engineering (IPE)",
        "expected_signs": ["IPE", "INDUSTRIAL AND PRODUCTION", "DEPT OF IPE"],
        "landmark_image": "dept_ipe.jpg",
        "coordinates": {"lat": 22.725323, "lon": 75.872728}
    },
    {
        "id": "dept_mech",
        "name": "Mechanical Engineering Dept",
        "type": "building",
        "label": "Dept of Mechanical Engineering",
        "expected_signs": ["MECHANICAL ENGG", "DEPT OF MECHANICAL", "MECH BLOCK"],
        "landmark_image": "dept_mech.jpg",
        "coordinates": {"lat": 22.725238, "lon": 75.872167}
    },

    # --- CENTRAL / ADMINISTRATIVE ZONE ---
    {
        "id": "plus_point",
        "name": "Plus Point",
        "type": "landmark",
        "label": "Plus Point Landmark (Campus Center)",
        "expected_signs": ["PLUS POINT", "PLUS POINT CAFE", "CAMPUS CENTER"],
        "landmark_image": "plus_point.jpg",
        "coordinates": {"lat": 22.72565, "lon": 75.87280}
    },
    {
        "id": "silveria_hall",
        "name": "Silveria Hall",
        "type": "hall",
        "label": "Silveria Hall (Auditorium)",
        "expected_signs": ["SILVERIA HALL", "SILVERIA", "AUDITORIUM"],
        "landmark_image": "silveria_hall.jpg",
        "coordinates": {"lat": 22.72520, "lon": 75.87200}
    },
    {
        "id": "admin_path_turn",
        "name": "Admin Path Turn",
        "type": "waypoint",
        "label": "Turn towards Administrative Building",
        "expected_signs": ["TO ADMIN BLOCK", "TO DIRECTOR OFFICE"],
        "landmark_image": None,
        "coordinates": {"lat": 22.72545, "lon": 75.87220}
    },
    {
        "id": "admin_building",
        "name": "Administrative Building",
        "type": "building",
        "label": "Administrative Building (Director's Office)",
        "expected_signs": ["ADMINISTRATIVE BUILDING", "ADMIN BLOCK", "DIRECTOR OFFICE", "REGISTRAR"],
        "landmark_image": "admin_building.jpg",
        "coordinates": {"lat": 22.725405, "lon": 75.871398}
    },
    {
        "id": "central_library",
        "name": "Central Library",
        "type": "building",
        "label": "Central Library",
        "expected_signs": ["CENTRAL LIBRARY", "LIBRARY", "READING ROOM"],
        "landmark_image": "central_library.jpg",
        "coordinates": {"lat": 22.725547, "lon": 75.871371}
    },
    {
        "id": "dept_elec",
        "name": "Electrical Engineering Dept",
        "type": "building",
        "label": "Dept of Electrical Engineering",
        "expected_signs": ["ELECTRICAL ENGG", "DEPT OF ELECTRICAL", "EE BLOCK"],
        "landmark_image": "dept_electrical.jpg",
        "coordinates": {"lat": 22.725436, "lon": 75.871104}
    },
    {
        "id": "central_store",
        "name": "Central Store",
        "type": "building",
        "label": "Central Store",
        "expected_signs": ["CENTRAL STORE", "STORE"],
        "landmark_image": "central_store.jpg",
        "coordinates": {"lat": 22.725262, "lon": 75.871703}
    },

    # --- WESTERN ACADEMIC & WORKSHOP ZONE ---
    {
        "id": "central_workshop",
        "name": "Central Workshop",
        "type": "building",
        "label": "Central Workshop (Machining, Welding, Foundry)",
        "expected_signs": ["CENTRAL WORKSHOP", "WORKSHOP", "MACHINE SHOP"],
        "landmark_image": "central_workshop.jpg",
        "coordinates": {"lat": 22.725894, "lon": 75.870586}
    },
    {
        "id": "dept_civil",
        "name": "Civil Engineering Dept",
        "type": "building",
        "label": "Dept of Civil Engineering and Applied Mechanics",
        "expected_signs": ["CIVIL ENGG", "APPLIED MECHANICS", "DEPT OF CIVIL"],
        "landmark_image": "dept_civil.jpg",
        "coordinates": {"lat": 22.725457, "lon": 75.870441}
    },
    {
        "id": "dept_chem",
        "name": "Applied Chemistry Dept",
        "type": "building",
        "label": "Dept of Applied Chemistry",
        "expected_signs": ["APPLIED CHEMISTRY", "CHEMISTRY LAB"],
        "landmark_image": "dept_chemistry.jpg",
        "coordinates": {"lat": 22.725457, "lon": 75.870100}
    },
    {
        "id": "dept_pharmacy",
        "name": "Pharmacy Dept",
        "type": "building",
        "label": "Dept of Pharmacy",
        "expected_signs": ["PHARMACY", "PHARMACY DEPT", "PHARMACEUTICAL LAB"],
        "landmark_image": "dept_pharmacy.jpg",
        "coordinates": {"lat": 22.725984, "lon": 75.869684}
    },

    # --- AMENITIES & FOOD ---
    {
        "id": "canteen_gym",
        "name": "Campus Canteen & Gym",
        "type": "landmark",
        "label": "Campus Canteen & Gymnasium",
        "expected_signs": ["CANTEEN", "CAFETERIA", "STUDENT CANTEEN", "GYM"],
        "landmark_image": "canteen.jpg",
        "coordinates": {"lat": 22.725907, "lon": 75.872207}
    },
    {
        "id": "heat_engine_lab",
        "name": "Heat Engine Lab & Store",
        "type": "building",
        "label": "Heat Engine Lab & Co-operative Store",
        "expected_signs": ["HEAT ENGINE LAB", "COOPERATIVE STORE"],
        "landmark_image": "heat_engine.jpg",
        "coordinates": {"lat": 22.725855, "lon": 75.871860}
    },

    # --- NORTH RESIDENTIAL / HOSTEL ZONE ---
    {
        "id": "guest_house",
        "name": "Guest House",
        "type": "building",
        "label": "Institute Guest House",
        "expected_signs": ["GUEST HOUSE", "TRANSIT HOSTEL"],
        "landmark_image": "guest_house.jpg",
        "coordinates": {"lat": 22.726918, "lon": 75.873579}
    },
    {
        "id": "hostel_visvesvaraya",
        "name": "M. Visvesvaraya Hostel",
        "type": "building",
        "label": "M. Visvesvaraya Hostel (Boys Hostel)",
        "expected_signs": ["VISVESARAYA HOSTEL", "MV HOSTEL", "BOYS HOSTEL"],
        "landmark_image": "hostel_visvesvaraya.jpg",
        "coordinates": {"lat": 22.727466, "lon": 75.872095}
    },
    {
        "id": "hostel_raman",
        "name": "C.V. Raman Hostel",
        "type": "building",
        "label": "C.V. Raman Hostel (Boys Hostel)",
        "expected_signs": ["C.V. RAMAN HOSTEL", "RAMAN HOSTEL", "BOYS HOSTEL 2"],
        "landmark_image": "hostel_raman.jpg",
        "coordinates": {"lat": 22.727804, "lon": 75.872201}
    },
    {
        "id": "hostel_sarojini",
        "name": "Sarojini Naidu Girls Hostel",
        "type": "building",
        "label": "Sarojini Naidu Girls Hostel",
        "expected_signs": ["SAROJINI NAIDU", "GIRLS HOSTEL", "SN HOSTEL"],
        "landmark_image": "hostel_girls.jpg",
        "coordinates": {"lat": 22.727594, "lon": 75.873734}
    },
    {
        "id": "hostel_ground",
        "name": "Hostel Sports Ground",
        "type": "landmark",
        "label": "Hostel Sports Ground (Cricket & Football)",
        "expected_signs": ["HOSTEL GROUND", "PLAYGROUND", "SPORTS GROUND"],
        "landmark_image": "hostel_ground.jpg",
        "coordinates": {"lat": 22.727200, "lon": 75.872500}
    }
]

print(f"Total SGSITS nodes mapped: {len(nodes)}")
