#!/usr/bin/env python3
"""Complete demo with direct YOLO integration"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import cv2
import time
import math
from ultralytics import YOLO

# Try to import MediaPipe (optional)
try:
    import mediapipe as mp
    mp_hands = mp.solutions.hands
    HANDS_AVAILABLE = True
except (ImportError, AttributeError) as e:
    print(f"⚠️  MediaPipe not available: {e}")
    HANDS_AVAILABLE = False
    mp_hands = None
    mp = None

def main():
    print("=" * 70)
    print("INTENT INTERFACE - SIMPLE YOLO DEMO")
    print("=" * 70)
    
    # Load YOLO
    print("Loading YOLOv8...")
    model = YOLO('yolov8s.pt')  # Using YOLOv8s for better accuracy
    print("✅ YOLOv8s loaded")
    
    # Initialize MediaPipe Hands (optional)
    if HANDS_AVAILABLE:
        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        print("✅ Hand detector initialized")
    else:
        hands = None
        print("⚠️  Running without hand detection (MediaPipe unavailable)")
    
    # Open camera
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    # Initialize tracker
    try:
        from vision.object_tracker import ObjectTracker
        from vision.camera_stream import DetectedObject
        
        tracker = ObjectTracker({
            'track_max_age_frames': 30,
            'track_min_hits': 3,
            'iou_match_threshold': 0.3
        }, seed=42)
        tracker_available = True
        print("✅ Tracker initialized")
    except Exception as e:
        print(f"⚠️  Tracker not available: {e}")
        tracker_available = False
    
    # Initialize affordances
    try:
        from affordances.affordance_engine import AffordanceEngine
        affordance_engine = AffordanceEngine({'enabled': True, 'max_affordance_options': 2}, seed=42)
        affordances_available = True
        print("✅ Affordances initialized")
    except Exception as e:
        print(f"⚠️  Affordances not available: {e}")
        affordances_available = False
    
    print()
    print("Features:")
    print("  ✓ YOLOv8s object detection (80 classes)")
    if HANDS_AVAILABLE:
        print("  ✓ Hand tracking with pinch detection")
    else:
        print("  ✗ Hand tracking (MediaPipe unavailable)")
    print("  ✓ Object tracking with persistent IDs")
    print()
    print("Controls: Q=Quit, SPACE=Pause, D=Toggle boxes")
    print("=" * 70)
    print()
    
    frame_count = 0
    paused = False
    show_boxes = True
    hand_detected = False
    pinch_detected = False
    pinch_distance = 0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            display_frame = frame.copy()
            
            if not paused:
                # Detect hands and pinch (if available)
                hand_detected = False
                pinch_detected = False
                pinch_distance = 0
                
                if HANDS_AVAILABLE and hands is not None:
                    # Convert frame to RGB for MediaPipe
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    hand_results = hands.process(frame_rgb)
                    
                    if hand_results.multi_hand_landmarks:
                        hand_detected = True
                        
                        for hand_landmarks in hand_results.multi_hand_landmarks:
                            # Get thumb tip (landmark 4) and index tip (landmark 8)
                            thumb_tip = hand_landmarks.landmark[4]
                            index_tip = hand_landmarks.landmark[8]
                            
                            # Convert to pixel coordinates
                            h, w, _ = frame.shape
                            thumb_x, thumb_y = int(thumb_tip.x * w), int(thumb_tip.y * h)
                            index_x, index_y = int(index_tip.x * w), int(index_tip.y * h)
                            
                            # Calculate distance between thumb and index
                            pinch_distance = math.sqrt((thumb_x - index_x)**2 + (thumb_y - index_y)**2)
                            
                            # Pinch detected if distance < 40 pixels
                            if pinch_distance < 40:
                                pinch_detected = True
                            
                            # Draw hand landmarks
                            if show_boxes:
                                # Draw all hand points
                                for landmark in hand_landmarks.landmark:
                                    x, y = int(landmark.x * w), int(landmark.y * h)
                                    cv2.circle(display_frame, (x, y), 3, (255, 0, 255), -1)
                                
                                # Draw thumb and index specifically
                                cv2.circle(display_frame, (thumb_x, thumb_y), 8, (0, 255, 0), 2)
                                cv2.circle(display_frame, (index_x, index_y), 8, (0, 255, 0), 2)
                                cv2.line(display_frame, (thumb_x, thumb_y), (index_x, index_y), 
                                        (0, 255, 0) if pinch_detected else (255, 255, 0), 2)
                                
                                # Show distance
                                mid_x, mid_y = (thumb_x + index_x) // 2, (thumb_y + index_y) // 2
                                cv2.putText(display_frame, f"{pinch_distance:.0f}px", 
                                           (mid_x, mid_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                                           0.5, (255, 255, 255), 2)
                
                # Run YOLO detection
                results = model(frame, verbose=False, conf=0.5)
                
                # Convert to DetectedObject format
                detected_objects = []
                for result in results:
                    boxes = result.boxes
                    for i, box in enumerate(boxes):
                        # Get box coordinates
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        conf = float(box.conf[0])
                        cls = int(box.cls[0])
                        label = model.names[cls]
                        
                        # Create DetectedObject
                        if tracker_available:
                            det_obj = DetectedObject(
                                detection_id=f"det_{frame_count}_{i}",
                                label=label,
                                bbox=(int(x1), int(y1), int(x2-x1), int(y2-y1)),
                                confidence=conf,
                                center_point=(int((x1+x2)/2), int((y1+y2)/2)),
                                area=int((x2-x1)*(y2-y1))
                            )
                            detected_objects.append(det_obj)
                        
                        # Draw detection box
                        if show_boxes:
                            cv2.rectangle(display_frame, 
                                        (int(x1), int(y1)), (int(x2), int(y2)),
                                        (255, 255, 0), 2)
                            cv2.putText(display_frame, f"{label} {conf:.2f}",
                                      (int(x1), int(y1-5)),
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                
                # Track objects
                tracked_objects = []
                if tracker_available and detected_objects:
                    try:
                        track_result = tracker.update(detected_objects, timestamp=time.time())
                        tracked_objects = track_result.tracked_objects if hasattr(track_result, 'tracked_objects') else []
                        
                        # Draw tracking boxes
                        if show_boxes:
                            for i, track in enumerate(tracked_objects):
                                x, y, w, h = track.bbox
                                color = (0, 255, 0) if i == 0 else (100, 255, 100)
                                thickness = 3 if i == 0 else 2
                                
                                cv2.rectangle(display_frame,
                                            (int(x), int(y)), (int(x+w), int(y+h)),
                                            color, thickness)
                                cv2.putText(display_frame, f"Track {track.track_id}: {track.label}",
                                          (int(x), int(y-25)),
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    except Exception as e:
                        print(f"Tracking error: {e}")
                
                # Generate affordances for primary object
                current_affordances = None
                if affordances_available and tracked_objects:
                    try:
                        primary = tracked_objects[0]
                        affordances = affordance_engine.compute(
                            scoped_object=primary,
                            ambiguity=False,
                            frame_id=frame_count,
                            timestamp=time.time(),
                            frame=frame,
                            bbox=primary.bbox
                        )
                        current_affordances = affordances
                    except Exception as e:
                        pass  # Some categories don't have affordances
            
            # Draw UI
            # Top bar
            cv2.rectangle(display_frame, (0, 0), (640, 50), (40, 40, 40), -1)
            cv2.putText(display_frame, f"Frame: {frame_count}",
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display_frame, f"Obj: {len(detected_objects) if not paused else '?'}",
                       (200, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            
            # Hand status (right side of top bar) - only if hands available
            if not paused and HANDS_AVAILABLE:
                hand_status = "✓ Hand" if hand_detected else "✗ Hand"
                hand_color = (0, 255, 0) if hand_detected else (100, 100, 100)
                cv2.putText(display_frame, hand_status, (320, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, hand_color, 2)
                
                # Pinch status
                if hand_detected:
                    pinch_status = "PINCH!" if pinch_detected else "Open"
                    pinch_color = (0, 255, 0) if pinch_detected else (255, 255, 0)
                    cv2.putText(display_frame, pinch_status, (480, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, pinch_color, 2)
            
            # Bottom bar - affordances
            if current_affordances and hasattr(current_affordances, 'options') and current_affordances.options:
                cv2.rectangle(display_frame, (0, 430), (640, 480), (0, 100, 0), -1)
                
                if tracked_objects:
                    cv2.putText(display_frame, f"Focused: {tracked_objects[0].label}",
                              (10, 455), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    action = current_affordances.options[0].title
                    cv2.putText(display_frame, f"Action: {action}",
                              (10, 475), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
            
            # Paused indicator
            if paused:
                cv2.putText(display_frame, "PAUSED", (250, 240),
                          cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            
            cv2.imshow('Intent Interface - YOLO Demo', display_frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = not paused
            elif key == ord('d'):
                show_boxes = not show_boxes
            
            # Print status every 60 frames
            if frame_count % 60 == 0 and tracked_objects:
                print(f"[Frame {frame_count}] Tracking {len(tracked_objects)} objects")
                for track in tracked_objects[:3]:
                    print(f"  - {track.label} (ID: {track.track_id}, age: {track.age_frames})")
    
    finally:
        if HANDS_AVAILABLE and hands is not None:
            hands.close()
        cap.release()
        cv2.destroyAllWindows()
        print(f"\n✅ Demo complete! Frames: {frame_count}")

if __name__ == '__main__':
    main()

