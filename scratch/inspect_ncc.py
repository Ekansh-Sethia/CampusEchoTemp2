import cv2
import numpy as np

# Print descriptions or quick color / text analysis of NCC and GreenGate
for name in ["NCC.jpg", "GreenGate_ag1.jpg", "GreenGate_ag2.jpg"]:
    img = cv2.imread(f"GS Photos/{name}")
    h, w, c = img.shape
    # sample colors
    mean_color = np.mean(img, axis=(0,1))
    print(f"{name}: shape {w}x{h}, mean BGR: {mean_color.astype(int)}")
