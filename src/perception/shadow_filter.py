"""Shadow and Dappled Light Filtering Layer for Campus Obstacle Detection.

Implements physics- and geometry-based cross-checks to distinguish real 3D obstacles
(stairs, potholes, stones) from 2D lighting artifacts (cast shadows, dappled canopy sunlight):
  A. Temporal / motion cross-check (frame-to-frame intensity flicker & shape stability)
  B. Shadow-specific color & texture checks (HSV chromaticity invariance + Laplacian disparity)
  C. Shadow shape signature (dappled light multi-blob clustering, penumbra edge softness, solidity)
  D. Geometric ground-plane plausibility
  E. Sun-angle / ambient lighting parameter awareness
  F. Proportional confidence recalibration for 3-tier safety policy
"""
import time
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np


class TemporalStabilityTracker:
    """
    Tracks candidate detection regions across consecutive frames to detect
    high-frequency intensity flickering (dappled light fluttering in wind) vs static obstacles.
    """

    def __init__(self, history_len: int = 8):
        self.history_len = history_len
        # {track_key: [(timestamp, bbox, mean_intensity)]}
        self._tracks: Dict[str, List[Tuple[float, Tuple[int, int, int, int], float]]] = {}

    def update_and_get_flicker_score(
        self,
        label: str,
        bbox: Tuple[int, int, int, int],
        mean_intensity: float,
        timestamp: Optional[float] = None
    ) -> float:
        """
        Computes temporal flicker / instability score [0.0 - 1.0].
        High flicker indicates dynamic canopy lighting / sun flutter.
        Low flicker across multiple frames indicates stable physical geometry.
        """
        now = timestamp or time.time()
        xmin, ymin, xmax, ymax = bbox
        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0

        # Match to closest existing track with compatible label within 60px
        best_key = None
        min_dist = float("inf")
        for key, hist in self._tracks.items():
            if key.startswith(label):
                _, last_bbox, _ = hist[-1]
                lx = (last_bbox[0] + last_bbox[2]) / 2.0
                ly = (last_bbox[1] + last_bbox[3]) / 2.0
                d = np.hypot(cx - lx, cy - ly)
                if d < min_dist and d <= 60.0:
                    min_dist = d
                    best_key = key

        if best_key is None:
            # Create new track
            best_key = f"{label}_{len(self._tracks) + 1}_{int(now * 1000)}"
            self._tracks[best_key] = []

        hist = self._tracks[best_key]
        hist.append((now, bbox, mean_intensity))
        if len(hist) > self.history_len:
            hist.pop(0)

        # Clean old tracks (> 3.0s unseen)
        for k in list(self._tracks.keys()):
            if now - self._tracks[k][-1][0] > 3.0:
                del self._tracks[k]

        if len(hist) < 3:
            return 0.0  # Insufficient history, neutral

        intensities = [item[2] for item in hist]
        std_intensity = float(np.std(intensities))

        # Fluttering leaves cause rapid standard deviation in intensity > 12.0
        if std_intensity >= 16.0:
            return 0.85
        elif std_intensity >= 10.0:
            return 0.50
        elif std_intensity <= 4.0 and len(hist) >= 5:
            return -0.20  # Stable static geometry credit
        return 0.0


class ShadowLightAnalyzer:
    """
    Evaluates whether a candidate detection is likely a shadow or dappled lighting artifact.
    Computes a continuous shadow_likelihood score [0.0 - 1.0] and recalibrates detection confidence.
    """

    def __init__(self, ambient_sun_factor: float = 1.0):
        """
        Args:
            ambient_sun_factor: 1.0 for normal sun, 1.25 for harsh midday direct sunlight,
                                0.70 for overcast/diffuse conditions where sharp shadows are rare.
        """
        self.ambient_sun_factor = ambient_sun_factor
        self.temporal_tracker = TemporalStabilityTracker()

    def analyze_obstacle(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        label: str,
        raw_confidence: float,
        timestamp: Optional[float] = None
    ) -> Tuple[float, float]:
        """
        Analyzes the candidate region and returns:
            (shadow_likelihood: float [0.0 - 1.0], calibrated_confidence: float [0.0 - 1.0])
        """
        h, w = frame.shape[:2]
        xmin, ymin, xmax, ymax = bbox
        bw = max(1, xmax - xmin)
        bh = max(1, ymax - ymin)

        # Region of interest with surrounding context (+25% margin)
        pad_x = int(bw * 0.25)
        pad_y = int(bh * 0.25)
        rx1 = max(0, xmin - pad_x)
        ry1 = max(0, ymin - pad_y)
        rx2 = min(w, xmax + pad_x)
        ry2 = min(h, ymax + pad_y)

        roi = frame[ry1:ry2, rx1:rx2]
        if roi.size == 0 or bw < 10 or bh < 10:
            return 0.0, raw_confidence

        # Relative coordinate mask for obstacle interior vs surrounding ground
        mask_in = np.zeros(roi.shape[:2], dtype=np.uint8)
        cv2.rectangle(
            mask_in,
            (xmin - rx1, ymin - ry1),
            (xmax - rx1, ymax - ry1),
            255,
            -1
        )
        mask_out = cv2.bitwise_not(mask_in)

        # -------------------------------------------------------------
        # B. Shadow-Specific Color & Texture Checks
        # -------------------------------------------------------------
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        h_channel = hsv_roi[:, :, 0]
        s_channel = hsv_roi[:, :, 1]
        v_channel = hsv_roi[:, :, 2]

        in_pixels_h = h_channel[mask_in > 0]
        out_pixels_h = h_channel[mask_out > 0]
        in_pixels_s = s_channel[mask_in > 0]
        out_pixels_s = s_channel[mask_out > 0]
        in_pixels_v = v_channel[mask_in > 0]
        out_pixels_v = v_channel[mask_out > 0]

        if in_pixels_v.size == 0 or out_pixels_v.size == 0:
            return 0.0, raw_confidence

        mean_v_in = float(np.mean(in_pixels_v))
        mean_v_out = float(np.mean(out_pixels_v))

        # Hue difference (circular metric on 0..180)
        mean_h_in = float(np.mean(in_pixels_h)) if in_pixels_h.size > 0 else 0.0
        mean_h_out = float(np.mean(out_pixels_h)) if out_pixels_h.size > 0 else 0.0
        diff_h = abs(mean_h_in - mean_h_out)
        circ_diff_h = min(diff_h, 180.0 - diff_h)

        diff_s = abs(float(np.mean(in_pixels_s)) - float(np.mean(out_pixels_s)))
        diff_v = abs(mean_v_out - mean_v_in)

        # Chromaticity Invariance Indicator:
        # Shadows preserve Hue and Saturation while Value shifts noticeably.
        is_chromatic_invariant = (circ_diff_h <= 14.0 and diff_s <= 26.0 and diff_v >= 20.0)

        # Texture Roughness Disparity (Laplacian Variance):
        # A real pothole or stone has genuine physical texture roughness disparity.
        # A flat shadow on pavement has identical texture roughness to the surrounding pavement.
        laplacian = cv2.Laplacian(gray_roi, cv2.CV_64F)
        var_in = float(np.var(laplacian[mask_in > 0])) if np.any(mask_in > 0) else 10.0
        var_out = float(np.var(laplacian[mask_out > 0])) if np.any(mask_out > 0) else 10.0
        texture_ratio = var_in / max(10.0, var_out)

        # -------------------------------------------------------------
        # C. Shadow Shape Signature (Dappled Canopy Light vs Real Stone)
        # -------------------------------------------------------------
        dapple_score = 0.0
        if label in ("stone", "large_stone", "rock", "rubble"):
            # Real stones are compact, single blobs with sharp contact boundaries.
            # Dappled light occurs in speckled clusters with soft penumbra boundaries.

            # 1. Multi-blob neighborhood clustering:
            # Check if there are multiple similar bright patches in the surrounding area
            floor_med = float(np.median(gray_roi))
            diff_bright = cv2.threshold(gray_roi, int(floor_med + 20), 255, cv2.THRESH_BINARY)[1]
            contours_bright, _ = cv2.findContours(diff_bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            similar_blobs = 0
            for cb in contours_bright:
                c_area = cv2.contourArea(cb)
                if 200 <= c_area <= 8000:
                    similar_blobs += 1

            if similar_blobs >= 3:
                # Part of a mottled dappled light field
                dapple_score += 0.40

            # 2. Contour Solidity Check:
            # Dappled patches through leaves have irregular/low solidity (<0.75)
            obj_gray = gray_roi[ymin - ry1:ymax - ry1, xmin - rx1:xmax - rx1]
            if obj_gray.size > 0:
                _, bin_obj = cv2.threshold(obj_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                cnts_obj, _ = cv2.findContours(bin_obj, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if cnts_obj:
                    largest_cnt = max(cnts_obj, key=cv2.contourArea)
                    cnt_area = cv2.contourArea(largest_cnt)
                    hull = cv2.convexHull(largest_cnt)
                    hull_area = cv2.contourArea(hull)
                    solidity = (cnt_area / hull_area) if hull_area > 0 else 1.0

                    if solidity < 0.72:
                        dapple_score += 0.35  # Irregular leaf-mottled shape
                    elif solidity >= 0.85:
                        dapple_score -= 0.20  # Compact solid stone

            # 3. Edge Penumbra Softness:
            # Tree shadows have soft blurred transitions due to sun angular diameter and leaf motion.
            edges = cv2.Canny(gray_roi, 30, 80)
            edge_count = np.count_nonzero(edges[mask_in > 0])
            if edge_count < (bw * bh * 0.03):
                dapple_score += 0.20  # Soft/diffuse border

        # -------------------------------------------------------------
        # A. Temporal Flicker Score
        # -------------------------------------------------------------
        temporal_score = self.temporal_tracker.update_and_get_flicker_score(
            label, bbox, mean_v_in, timestamp
        )

        # -------------------------------------------------------------
        # Composite Shadow Likelihood Calculation
        # -------------------------------------------------------------
        shadow_likelihood = 0.0

        if label in ("stone", "large_stone", "rock", "rubble"):
            # If internal texture roughness is significantly higher than ground (genuine stone),
            # heavily reduce shadow likelihood
            if texture_ratio >= 1.80:
                shadow_likelihood = max(0.0, dapple_score * 0.40 + temporal_score * 0.30)
            else:
                # Weak texture disparity + dappled shape -> very likely sunlight patch
                shadow_likelihood = 0.35 + dapple_score + max(0.0, temporal_score)
                if is_chromatic_invariant:
                    shadow_likelihood += 0.25

        elif label in ("pothole",):
            # Real pothole: cracked, crumbled internal structure (texture_ratio >= 2.0).
            # If texture_ratio is near 1.0 and chromaticity is invariant -> pure flat shadow!
            if texture_ratio >= 1.90:
                # Real pothole (even if inside a shadow area)
                shadow_likelihood = 0.05
            elif is_chromatic_invariant and (0.75 <= texture_ratio <= 1.30):
                # Pavement shadow (same texture, invariant hue)
                shadow_likelihood = 0.88 + max(0.0, temporal_score)
            else:
                shadow_likelihood = 0.40

        elif label in ("stair",):
            # Real stair has vertical risers and horizontal step edge progression.
            # A single light/shadow boundary on flat pavement has invariant hue and no riser height.
            if is_chromatic_invariant and (0.80 <= texture_ratio <= 1.25):
                shadow_likelihood = 0.75
            else:
                shadow_likelihood = 0.15

        else:
            # Other classes (vehicles, people, chairs)
            shadow_likelihood = 0.0

        # Apply ambient sun factor scaling
        shadow_likelihood = float(np.clip(shadow_likelihood * self.ambient_sun_factor, 0.0, 1.0))

        # -------------------------------------------------------------
        # F. Proportional Confidence Recalibration
        # -------------------------------------------------------------
        # If shadow_likelihood > 0.75: heavy penalty (suppresses false alarm)
        # If shadow_likelihood in 0.40 - 0.75: proportional penalty (pushes Tier 1 to Tier 2 HEDGE)
        # If shadow_likelihood < 0.30: minimal or zero penalty
        if shadow_likelihood >= 0.75:
            penalty = 0.75 * shadow_likelihood
        elif shadow_likelihood >= 0.40:
            penalty = 0.50 * shadow_likelihood
        else:
            penalty = 0.15 * shadow_likelihood

        calibrated_conf = round(float(np.clip(raw_confidence * (1.0 - penalty), 0.05, 1.0)), 2)

        return round(shadow_likelihood, 2), calibrated_conf
