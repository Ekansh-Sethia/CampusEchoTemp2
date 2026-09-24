"""
Landmark and Signboard Fuzzy Matcher for CampusEcho.
Matches OCR text candidates against campus graph expected signage.
"""
from difflib import SequenceMatcher
import re
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from .graph import CampusGraph, Node


class LandmarkMatchResult(BaseModel):
    """Result of matching an OCR text detection against campus landmarks."""
    node_id: str
    node_label: str
    matched_sign: str
    ocr_text: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    ocr_confidence: float = Field(ge=0.0, le=1.0)
    combined_confidence: float = Field(ge=0.0, le=1.0)


class LandmarkMatcher:
    """
    Indexes expected signage from a CampusGraph and fuzzy-matches
    live OCR detections to topological graph nodes.
    """

    def __init__(
        self,
        graph: CampusGraph,
        min_similarity: float = 0.65,
        min_combined_confidence: float = 0.50
    ):
        self.graph = graph
        self.min_similarity = min_similarity
        self.min_combined_confidence = min_combined_confidence
        # {(node_id, expected_sign_normalized): (node, original_sign)}
        self._sign_index: List[Tuple[str, Node, str, Set[str]]] = []
        self._build_index()

    def _build_index(self) -> None:
        """Builds an index of all expected signs from graph nodes."""
        self._sign_index.clear()
        for node_id, node in self.graph.nodes.items():
            for sign in node.expected_signs:
                norm_sign = self._normalize(sign)
                tokens = set(norm_sign.split())
                self._sign_index.append((node_id, node, norm_sign, tokens))

    @staticmethod
    def _normalize(text: str) -> str:
        """Standardizes strings for matching."""
        text = text.upper().strip()
        text = re.sub(r'[^A-Z0-9\s]', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculates a hybrid similarity score considering:
        1. Substring containment (e.g. 'ATC' in 'ATC BUILDING')
        2. SequenceMatcher character-level edit ratio
        3. Token overlap (Jaccard similarity)
        """
        norm1 = self._normalize(text1)
        norm2 = self._normalize(text2)

        if not norm1 or not norm2:
            return 0.0

        if norm1 == norm2:
            return 1.0

        # Substring containment bonus
        if norm1 in norm2 or norm2 in norm1:
            len_ratio = min(len(norm1), len(norm2)) / max(len(norm1), len(norm2))
            # If one is a significant substring of the other (e.g. 'SILVERIA' in 'SILVERIA HALL')
            if len_ratio >= 0.40:
                return max(0.85, len_ratio)

        # Character-level sequence ratio
        seq_ratio = SequenceMatcher(None, norm1, norm2).ratio()

        # Token set overlap
        tokens1 = set(norm1.split())
        tokens2 = set(norm2.split())
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        jaccard = len(intersection) / len(union) if union else 0.0

        # Weighted hybrid that trusts high character sequence similarity
        score = max(seq_ratio, 0.70 * seq_ratio + 0.30 * jaccard)
        return min(1.0, score)

    def match(
        self,
        ocr_text: str,
        ocr_confidence: float = 1.0,
        candidate_node_ids: Optional[List[str]] = None
    ) -> Optional[LandmarkMatchResult]:
        """
        Matches a single OCR text string against indexed campus landmarks.
        If candidate_node_ids is provided, prioritizes/restricts to those nodes.
        """
        best_match: Optional[LandmarkMatchResult] = None
        highest_combined = 0.0

        target_tokens = set(self._normalize(ocr_text).split())

        for node_id, node, norm_sign, sign_tokens in self._sign_index:
            if candidate_node_ids and node_id not in candidate_node_ids:
                continue

            similarity = self.calculate_similarity(ocr_text, norm_sign)
            if similarity < self.min_similarity:
                continue

            # Prioritize candidate nodes (e.g. forward waypoints along current path)
            priority_boost = 1.05 if (candidate_node_ids and node_id in candidate_node_ids) else 1.0
            combined = min(1.0, (similarity * 0.7 + ocr_confidence * 0.3) * priority_boost)

            if combined >= self.min_combined_confidence and combined > highest_combined:
                highest_combined = combined
                best_match = LandmarkMatchResult(
                    node_id=node_id,
                    node_label=node.label,
                    matched_sign=norm_sign,
                    ocr_text=ocr_text,
                    similarity_score=round(similarity, 3),
                    ocr_confidence=round(ocr_confidence, 3),
                    combined_confidence=round(combined, 3)
                )

        return best_match

    def match_best_detection(
        self,
        detections: List,  # List of SignDetection
        candidate_node_ids: Optional[List[str]] = None
    ) -> Optional[LandmarkMatchResult]:
        """
        Finds the highest-confidence landmark match among a list of OCR sign detections.
        """
        best_overall: Optional[LandmarkMatchResult] = None

        for det in detections:
            match = self.match(
                ocr_text=det.text,
                ocr_confidence=det.confidence,
                candidate_node_ids=candidate_node_ids
            )
            if match:
                if best_overall is None or match.combined_confidence > best_overall.combined_confidence:
                    best_overall = match

        return best_overall
