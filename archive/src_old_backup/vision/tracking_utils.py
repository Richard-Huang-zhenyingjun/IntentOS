"""Tracking Utilities - IoU calculation and detection-to-track matching."""

from typing import List, Tuple
import numpy as np
from vision.object_detector import DetectedObject
from vision.tracking_schema import Track


def bbox_iou(bbox1: Tuple[int, int, int, int], 
             bbox2: Tuple[int, int, int, int]) -> float:
    """
    Calculate Intersection over Union for two bounding boxes
    
    Args:
        bbox1, bbox2: (x, y, width, height)
    
    Returns:
        IoU score [0.0, 1.0]
    """
    x1, y1, w1, h1 = bbox1
    x2, y2, w2, h2 = bbox2
    
    # Convert to (x1, y1, x2, y2) format
    box1 = (x1, y1, x1 + w1, y1 + h1)
    box2 = (x2, y2, x2 + w2, y2 + h2)
    
    # Intersection rectangle
    xi1 = max(box1[0], box2[0])
    yi1 = max(box1[1], box2[1])
    xi2 = min(box1[2], box2[2])
    yi2 = min(box1[3], box2[3])
    
    inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    
    # Union area
    box1_area = w1 * h1
    box2_area = w2 * h2
    union_area = box1_area + box2_area - inter_area
    
    if union_area == 0:
        return 0.0
    
    return inter_area / union_area


def bbox_center_distance(bbox1: Tuple[int, int, int, int],
                         bbox2: Tuple[int, int, int, int]) -> float:
    """Calculate Euclidean distance between bbox centers"""
    x1, y1, w1, h1 = bbox1
    x2, y2, w2, h2 = bbox2
    
    cx1 = x1 + w1 / 2
    cy1 = y1 + h1 / 2
    cx2 = x2 + w2 / 2
    cy2 = y2 + h2 / 2
    
    return np.sqrt((cx1 - cx2)**2 + (cy1 - cy2)**2)


def bbox_size_similarity(bbox1: Tuple[int, int, int, int],
                        bbox2: Tuple[int, int, int, int]) -> float:
    """Calculate size similarity [0.0, 1.0]"""
    area1 = bbox1[2] * bbox1[3]
    area2 = bbox2[2] * bbox2[3]
    
    if area1 == 0 or area2 == 0:
        return 0.0
    
    # Ratio of smaller to larger
    return min(area1, area2) / max(area1, area2)


def match_detections_to_tracks(
    detections: List[DetectedObject],
    tracks: List[Track],
    config: dict
) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    """
    Match detections to existing tracks using IoU + constraints
    
    Returns:
        matches: List of (detection_idx, track_idx) pairs
        unmatched_detections: List of detection indices
        unmatched_tracks: List of track indices
    """
    iou_threshold = config.get('iou_match_threshold', 0.3)
    label_match_required = config.get('label_match_required', True)
    max_bbox_shift = config.get('max_bbox_shift_pixels', 100)
    
    if len(detections) == 0 or len(tracks) == 0:
        return [], list(range(len(detections))), list(range(len(tracks)))
    
    # Build cost matrix (IoU-based, higher is better)
    cost_matrix = np.zeros((len(detections), len(tracks)))
    
    for i, det in enumerate(detections):
        for j, track in enumerate(tracks):
            # Label constraint
            if label_match_required and det.label != track.label:
                cost_matrix[i, j] = 0.0
                continue
            
            # IoU score
            iou = bbox_iou(det.bbox, track.bbox)
            
            # Distance constraint (prevent large jumps)
            distance = bbox_center_distance(det.bbox, track.bbox)
            if distance > max_bbox_shift:
                cost_matrix[i, j] = 0.0
                continue
            
            # Size similarity (prevent drastic size changes)
            size_sim = bbox_size_similarity(det.bbox, track.bbox)
            
            # Combined score (weighted)
            cost_matrix[i, j] = 0.7 * iou + 0.3 * size_sim
    
    # Greedy matching (simple, good enough for Week 2)
    matches = []
    matched_detections = set()
    matched_tracks = set()
    
    # Sort all possible matches by score
    all_matches = []
    for i in range(len(detections)):
        for j in range(len(tracks)):
            if cost_matrix[i, j] >= iou_threshold:
                all_matches.append((i, j, cost_matrix[i, j]))
    
    all_matches.sort(key=lambda x: x[2], reverse=True)
    
    # Greedy assignment
    for det_idx, track_idx, score in all_matches:
        if det_idx not in matched_detections and track_idx not in matched_tracks:
            matches.append((det_idx, track_idx))
            matched_detections.add(det_idx)
            matched_tracks.add(track_idx)
    
    # Unmatched
    unmatched_dets = [i for i in range(len(detections)) if i not in matched_detections]
    unmatched_trks = [j for j in range(len(tracks)) if j not in matched_tracks]
    
    return matches, unmatched_dets, unmatched_trks




