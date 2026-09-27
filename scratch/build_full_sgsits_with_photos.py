import json
from pathlib import Path
import networkx as nx

photos_dir = Path("GS Photos")
all_photos = sorted([p.name for p in photos_dir.glob("*.jpg")])
print(f"Total photos in GS Photos: {len(all_photos)}")

# Full SGSITS Campus Graph with real photos and user confirmations
graph_data = {
    "metadata": {
        "campus_name": "Shri G. S. Institute of Technology and Science (SGSITS), Indore",
        "city": "Indore, Madhya Pradesh, India",
        "address": "23 Sir M. Visvesvaraya Marg, Vallabh Nagar, Indore - 452003",
        "version": "3.0-complete",
        "description": "Complete SGSITS Indore campus navigation graph with user ground-truth measurements, real multi-angle landmark photos, and verified pedestrian routes.",
        "verified_rules": {
            "plus_point_to_canteen_open": True,
            "main_gate_dual_walkways_open": True,
            "gate_2_locked": True,
            "hostels_routed_via_canteen": True
        }
    },
    "nodes": [
        # --- GATES & ENTRANCES ---
        {
            "id": "golden_gate",
            "name": "Golden Gate",
            "type": "entrance",
            "label": "Golden Gate (Hostel Gate)",
            "expected_signs": ["GOLDEN GATE", "HOSTEL GATE", "COLLEGE ENTRANCE", "SGSITS", "GSITS"],
            "landmark_image": "GS Photos/goldenGate_ag1.jpg",
            "landmark_images": [
                "GS Photos/goldenGate_ag1.jpg",
                "GS Photos/GoldenGate_ag2.jpg",
                "GS Photos/GoldenGate_ag3.jpg"
            ],
            "coordinates": {"lat": 22.72620, "lon": 75.87410}
        },
        {
            "id": "golden_gate_turn",
            "name": "Golden Gate Path Turn",
            "type": "waypoint",
            "label": "Turn towards ATC Building",
            "expected_signs": ["TO ATC", "TO ACADEMIC COMPLEX"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.72590, "lon": 75.87370}
        },
        {
            "id": "green_gate",
            "name": "Green Gate (Main Gate)",
            "type": "entrance",
            "label": "Green Gate (Main Entrance - Park Road)",
            "expected_signs": ["MAIN GATE", "GREEN GATE", "SGSITS INDORE", "GATE 1", "SHRI G.S. INSTITUTE OF TECHNOLOGY"],
            "landmark_image": "GS Photos/GreenGate_ag1.jpg",
            "landmark_images": [
                "GS Photos/GreenGate_ag1.jpg",
                "GS Photos/GreenGate_ag2.jpg"
            ],
            "coordinates": {"lat": 22.72473, "lon": 75.87414}
        },
        {
            "id": "pnb_gate",
            "name": "PNB Gate",
            "type": "entrance",
            "label": "PNB Gate (Campus Bank & Sports Entry)",
            "expected_signs": ["PNB GATE", "PUNJAB NATIONAL BANK", "BANK GATE", "ORIENTAL BANK", "SGSITS ENTRY"],
            "landmark_image": "GS Photos/PNBGate_ag1.jpg",
            "landmark_images": [
                "GS Photos/PNBGate_ag1.jpg",
                "GS Photos/PNBGate_ag2.jpg",
                "GS Photos/PNBGate_ag3.jpg",
                "GS Photos/PNBGate_ag4.jpg"
            ],
            "coordinates": {"lat": 22.72510, "lon": 75.87450}
        },

        # --- ACADEMIC CORE & ATC ---
        {
            "id": "atc_building",
            "name": "ATC Building",
            "type": "building",
            "label": "ATC Building (T&P Cell, Tech Labs)",
            "expected_signs": ["ATC BUILDING", "ATC", "ACADEMIC & TECHNOLOGY COMPLEX", "TRAINING AND PLACEMENT"],
            "landmark_image": "GS Photos/Atc.jpg",
            "landmark_images": [
                "GS Photos/Atc.jpg"
            ],
            "coordinates": {"lat": 22.725840, "lon": 75.873201}
        },
        {
            "id": "atc_junction",
            "name": "ATC Pathway Junction",
            "type": "junction",
            "label": "Junction outside ATC Building",
            "expected_signs": ["TO SILVERIA HALL", "TO PLUS POINT", "TO CANTEEN", "TO LT"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.72573, "lon": 75.87315}
        },
        {
            "id": "lecture_theatres",
            "name": "Lecture Theatres (LT)",
            "type": "building",
            "label": "Lecture Theatres (LT Complex)",
            "expected_signs": ["LT", "LECTURE THEATRE", "LT 1", "LT 2", "LT 3", "LT 4"],
            "landmark_image": "GS Photos/LT_ag1.jpg",
            "landmark_images": [
                "GS Photos/LT_ag1.jpg",
                "GS Photos/LT_ag2.jpg",
                "GS Photos/LT_ag3.jpg",
                "GS Photos/LT_ag4.jpg"
            ],
            "coordinates": {"lat": 22.725796, "lon": 75.873575}
        },
        {
            "id": "sports_complex",
            "name": "Sports Complex & Volleyball Turf",
            "type": "landmark",
            "label": "Volleyball Turf & Sports Complex",
            "expected_signs": ["VOLLEYBALL TURF", "GRASS COURT", "SPORTS COMPLEX", "BASKETBALL COURT", "GYMNASIUM"],
            "landmark_image": "GS Photos/Volleyball_ag1.jpg",
            "landmark_images": [
                "GS Photos/Volleyball_ag1.jpg",
                "GS Photos/Volleyball_ag2.jpg",
                "GS Photos/Volleyball_ag3.jpg",
                "GS Photos/Volleyball_ag4.jpg"
            ],
            "coordinates": {"lat": 22.725244, "lon": 75.873701}
        },
        {
            "id": "ncc_unit",
            "name": "NCC Unit & Ground",
            "type": "landmark",
            "label": "NCC Unit & Drill Grounds",
            "expected_signs": ["NCC", "NCC INDORE", "NATIONAL CADET CORPS"],
            "landmark_image": "GS Photos/NCC.jpg",
            "landmark_images": [
                "GS Photos/NCC.jpg"
            ],
            "coordinates": {"lat": 22.72500, "lon": 75.87390}
        },

        # --- ENGINEERING DEPARTMENTS ---
        {
            "id": "dept_cs_it",
            "name": "Computer Engineering & IT Dept",
            "type": "building",
            "label": "Dept of Computer Engineering, IT & MCA",
            "expected_signs": ["DEPARTMENT OF COMPUTER ENGINEERING", "COMPUTER ENGINEERING", "IT DEPT", "MCA"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725121, "lon": 75.873165}
        },
        {
            "id": "dept_etc",
            "name": "Electronics & Telecommunication Dept",
            "type": "building",
            "label": "Dept of Electronics & Telecommunication (ETC)",
            "expected_signs": ["ELEX AND T.C.", "ELECTRONICS", "ETC DEPARTMENT", "TELECOMMUNICATION"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725340, "lon": 75.873161}
        },
        {
            "id": "dept_biomedical",
            "name": "Biomedical Engineering Dept",
            "type": "building",
            "label": "Dept of Biomedical Engineering",
            "expected_signs": ["DEPARTMENT OF BIOMEDICAL ENGINEERING", "BIOMEDICAL ENGINEERING", "BM DEPT", "BM LAB"],
            "landmark_image": "GS Photos/BMDept.jpg",
            "landmark_images": [
                "GS Photos/BMDept.jpg"
            ],
            "coordinates": {"lat": 22.725362, "lon": 75.873020}
        },
        {
            "id": "dept_ei",
            "name": "Electronics & Instrumentation Dept",
            "type": "building",
            "label": "Dept of Electronics & Instrumentation (EI)",
            "expected_signs": ["EI DEPT", "ELECTRONICS AND INSTRUMENTATION", "INSTRUMENTATION ENGG"],
            "landmark_image": "GS Photos/EIDept.jpg",
            "landmark_images": [
                "GS Photos/EIDept.jpg"
            ],
            "coordinates": {"lat": 22.72520, "lon": 75.87310}
        },
        {
            "id": "dept_ipe",
            "name": "Industrial & Production Engineering Dept",
            "type": "building",
            "label": "Dept of Industrial & Production Engineering (IPE)",
            "expected_signs": ["IPE", "INDUSTRIAL AND PRODUCTION", "DEPT OF IPE"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725323, "lon": 75.872728}
        },
        {
            "id": "dept_mech",
            "name": "Mechanical Engineering Dept",
            "type": "building",
            "label": "Dept of Mechanical Engineering",
            "expected_signs": ["MECHANICAL ENGG", "DEPT OF MECHANICAL", "MECH BLOCK"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725238, "lon": 75.872167}
        },

        # --- CENTRAL & ADMINISTRATIVE ---
        {
            "id": "plus_point",
            "name": "Plus Point",
            "type": "landmark",
            "label": "Plus Point Landmark (Campus Center)",
            "expected_signs": ["PLUS POINT", "PLUS POINT CAFE", "CAMPUS CENTER"],
            "landmark_image": "GS Photos/PlusPoint_ag1.jpg",
            "landmark_images": [
                "GS Photos/PlusPoint_ag1.jpg",
                "GS Photos/PlusPoint_ag2.jpg",
                "GS Photos/PlusPoint_ag3.jpg",
                "GS Photos/PlusPoint_ag4.jpg"
            ],
            "coordinates": {"lat": 22.72565, "lon": 75.87280}
        },
        {
            "id": "canteen_gym",
            "name": "Campus Cafe & Canteen",
            "type": "landmark",
            "label": "Campus Cafe, Canteen & Gym",
            "expected_signs": ["CAFE", "CANTEEN", "CAFETERIA", "STUDENT CANTEEN", "GYM"],
            "landmark_image": "GS Photos/Cafe_ag1.jpg",
            "landmark_images": [
                "GS Photos/Cafe_ag1.jpg",
                "GS Photos/Cafe_ag2.jpg",
                "GS Photos/Cafe_ag3.jpg"
            ],
            "coordinates": {"lat": 22.725907, "lon": 75.872207}
        },
        {
            "id": "silveria_hall",
            "name": "Silveria Hall",
            "type": "hall",
            "label": "Silveria Hall (Auditorium)",
            "expected_signs": ["SILVERIA HALL", "SILVERIA", "AUDITORIUM"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.72520, "lon": 75.87200}
        },
        {
            "id": "admin_path_turn",
            "name": "Admin Path Turn",
            "type": "waypoint",
            "label": "Turn towards Administrative Building",
            "expected_signs": ["TO ADMIN BLOCK", "TO DIRECTOR OFFICE"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.72545, "lon": 75.87220}
        },
        {
            "id": "admin_building",
            "name": "Administrative Building",
            "type": "building",
            "label": "Administrative Building (Director's Office)",
            "expected_signs": ["ADMINISTRATIVE BUILDING", "ADMIN BLOCK", "DIRECTOR OFFICE", "REGISTRAR"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725405, "lon": 75.871398}
        },
        {
            "id": "central_library",
            "name": "Central Library",
            "type": "building",
            "label": "Central Library",
            "expected_signs": ["CENTRAL LIBRARY", "LIBRARY", "READING ROOM"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725547, "lon": 75.871371}
        },
        {
            "id": "dept_elec",
            "name": "Electrical Engineering Dept",
            "type": "building",
            "label": "Dept of Electrical Engineering",
            "expected_signs": ["ELECTRICAL ENGG", "DEPT OF ELECTRICAL", "EE BLOCK"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725436, "lon": 75.871104}
        },
        {
            "id": "central_store",
            "name": "Central Store",
            "type": "building",
            "label": "Central Store",
            "expected_signs": ["CENTRAL STORE", "STORE"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725262, "lon": 75.871703}
        },

        # --- WESTERN ACADEMIC & WORKSHOP ZONE ---
        {
            "id": "central_workshop",
            "name": "Central Workshop",
            "type": "building",
            "label": "Central Workshop (Machining, Welding, Foundry)",
            "expected_signs": ["CENTRAL WORKSHOP", "WORKSHOP", "MACHINE SHOP"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725894, "lon": 75.870586}
        },
        {
            "id": "dept_civil",
            "name": "Civil Engineering Dept",
            "type": "building",
            "label": "Dept of Civil Engineering & Applied Mechanics",
            "expected_signs": ["CIVIL ENGG", "APPLIED MECHANICS", "DEPT OF CIVIL"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725457, "lon": 75.870441}
        },
        {
            "id": "dept_chem",
            "name": "Applied Chemistry Dept",
            "type": "building",
            "label": "Dept of Applied Chemistry",
            "expected_signs": ["APPLIED CHEMISTRY", "CHEMISTRY LAB"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725457, "lon": 75.870100}
        },
        {
            "id": "dept_pharmacy",
            "name": "Pharmacy Dept",
            "type": "building",
            "label": "Dept of Pharmacy",
            "expected_signs": ["PHARMACY", "PHARMACY DEPT", "PHARMACEUTICAL LAB"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725984, "lon": 75.869684}
        },
        {
            "id": "heat_engine_lab",
            "name": "Heat Engine Lab & Store",
            "type": "building",
            "label": "Heat Engine Lab & Co-operative Store",
            "expected_signs": ["HEAT ENGINE LAB", "COOPERATIVE STORE"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.725855, "lon": 75.871860}
        },

        # --- NORTH HOSTELS & RESIDENTIAL ---
        {
            "id": "guest_house",
            "name": "Guest House",
            "type": "building",
            "label": "Institute Guest House",
            "expected_signs": ["GUEST HOUSE", "TRANSIT HOSTEL"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.726918, "lon": 75.873579}
        },
        {
            "id": "hostel_visvesvaraya",
            "name": "M. Visvesvaraya Hostel",
            "type": "building",
            "label": "M. Visvesvaraya Hostel (Boys Hostel)",
            "expected_signs": ["VISVESARAYA HOSTEL", "MV HOSTEL", "BOYS HOSTEL"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.727466, "lon": 75.872095}
        },
        {
            "id": "hostel_raman",
            "name": "C.V. Raman Hostel",
            "type": "building",
            "label": "C.V. Raman Hostel (Boys Hostel)",
            "expected_signs": ["C.V. RAMAN HOSTEL", "RAMAN HOSTEL", "BOYS HOSTEL 2"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.727804, "lon": 75.872201}
        },
        {
            "id": "hostel_sarojini",
            "name": "Sarojini Naidu Girls Hostel",
            "type": "building",
            "label": "Sarojini Naidu Girls Hostel",
            "expected_signs": ["SAROJINI NAIDU", "GIRLS HOSTEL", "SN HOSTEL"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.727594, "lon": 75.873734}
        },
        {
            "id": "hostel_ground",
            "name": "Hostel Sports Ground",
            "type": "landmark",
            "label": "Hostel Sports Ground (Cricket & Football)",
            "expected_signs": ["HOSTEL GROUND", "PLAYGROUND", "SPORTS GROUND"],
            "landmark_image": None,
            "landmark_images": [],
            "coordinates": {"lat": 22.727200, "lon": 75.872500}
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

        # --- 2. PLUS POINT TO CANTEEN (Confirmed OPEN by user) ---
        {
            "id": "edge_plus_point_to_canteen",
            "from": "plus_point",
            "to": "canteen_gym",
            "distance_m": 65.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk straight north through open courtyard from Plus Point to Campus Cafe"
        },

        # --- 3. GREEN GATE & PNB GATE (Confirmed BOTH WAYS OPEN by user) ---
        {
            "id": "edge_green_gate_to_sports",
            "from": "green_gate",
            "to": "sports_complex",
            "distance_m": 60.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Enter through Green Gate and walk straight towards Sports Complex & Volleyball Turf"
        },
        {
            "id": "edge_green_gate_to_cs_it",
            "from": "green_gate",
            "to": "dept_cs_it",
            "distance_m": 105.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Turn left from Green Gate into Computer Science & IT avenue"
        },
        {
            "id": "edge_pnb_gate_to_sports",
            "from": "pnb_gate",
            "to": "sports_complex",
            "distance_m": 45.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Enter from PNB Gate and walk straight towards Volleyball Turf"
        },
        {
            "id": "edge_pnb_gate_to_ncc",
            "from": "pnb_gate",
            "to": "ncc_unit",
            "distance_m": 35.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Walk left from PNB Gate towards NCC Unit"
        },
        {
            "id": "edge_ncc_to_sports",
            "from": "ncc_unit",
            "to": "sports_complex",
            "distance_m": 30.0,
            "direction_forward": "right",
            "direction_backward": "left",
            "description": "Walk from NCC Unit to Sports Complex and Volleyball Turf"
        },
        {
            "id": "edge_sports_to_lt",
            "from": "sports_complex",
            "to": "lecture_theatres",
            "distance_m": 65.0,
            "direction_forward": "left",
            "direction_backward": "right",
            "description": "Walk past sports courts towards Lecture Theatres complex"
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

        # --- 4. ENGINEERING DEPARTMENTS ---
        {
            "id": "edge_cs_it_to_ei",
            "from": "dept_cs_it",
            "to": "dept_ei",
            "distance_m": 18.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk straight along corridor to Electronics & Instrumentation Dept"
        },
        {
            "id": "edge_ei_to_etc",
            "from": "dept_ei",
            "to": "dept_etc",
            "distance_m": 15.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk from EI Dept to Electronics & Telecommunication Dept"
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

        # --- 5. CENTRAL LIBRARY, ELECTRICAL & STORE ---
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

        # --- 6. WESTERN ACADEMIC & WORKSHOPS ---
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

        # --- 7. CAFE / CANTEEN CORRIDOR ---
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

        # --- 8. NORTH HOSTELS (Via Canteen route as confirmed by user) ---
        {
            "id": "edge_canteen_to_ground",
            "from": "canteen_gym",
            "to": "hostel_ground",
            "distance_m": 145.0,
            "direction_forward": "straight",
            "direction_backward": "straight",
            "description": "Walk north along hostel avenue from Canteen to Hostel Sports Ground"
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

# Verify that all 28 photos are mapped to nodes
mapped_photos = set()
for n in graph_data["nodes"]:
    for img in n.get("landmark_images", []):
        img_name = Path(img).name
        mapped_photos.add(img_name)

unmapped = set(all_photos) - mapped_photos
print(f"Mapped {len(mapped_photos)} of {len(all_photos)} photos. Unmapped: {unmapped}")

# Save to data/sgsits_campus_graph_full.json
out_path = Path("data/sgsits_campus_graph_full.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(graph_data, f, indent=2)

print(f"Saved complete graph to {out_path}")
