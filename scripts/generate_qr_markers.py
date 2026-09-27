"""
Generate QR Marker Images for B1 - B5 Indoor Landmarks.
Places generated images in data/qr_markers/ and static/qr_markers/
"""
from pathlib import Path
import qrcode
from PIL import Image, ImageDraw, ImageFont


LANDMARKS = [
    {"id": "B1", "name": "Main Entrance", "zone": "Entrance"},
    {"id": "B2", "name": "Central Corridor", "zone": "Corridor"},
    {"id": "B3", "name": "Computer Lab", "zone": "Lab"},
    {"id": "B4", "name": "Staircase", "zone": "Staircase"},
    {"id": "B5", "name": "Library", "zone": "Library"},
]


def generate_markers():
    root = Path(__file__).parent.parent
    out_dirs = [
        root / "data" / "qr_markers",
        root / "static" / "qr_markers",
    ]
    for d in out_dirs:
        d.mkdir(parents=True, exist_ok=True)

    for lm in LANDMARKS:
        lm_id = lm["id"]
        payload = f'{{"type": "indoor_landmark", "id": "{lm_id}"}}'

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(payload)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        # Create padded canvas with text header and footer
        w, h = qr_img.size
        canvas_h = h + 80
        canvas = Image.new("RGB", (w, canvas_h), "white")
        draw = ImageDraw.Draw(canvas)

        # Header title
        title_text = f"LANDMARK {lm_id}: {lm['name']}"
        draw.text((w // 2, 20), title_text, fill="black", anchor="mm")

        # Paste QR code
        canvas.paste(qr_img, (0, 40))

        # Footer subtitle
        footer_text = f"Zone: {lm['zone']} | Payload: {lm_id}"
        draw.text((w // 2, canvas_h - 20), footer_text, fill="#444444", anchor="mm")

        for d in out_dirs:
            out_file = d / f"{lm_id}.png"
            canvas.save(out_file)
            print(f"Generated QR marker: {out_file}")


if __name__ == "__main__":
    generate_markers()
