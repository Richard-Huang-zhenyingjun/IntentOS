#!/usr/bin/env python3
"""
Complete Intent Interface Demo with Live Camera
Integrates all Week 1-9 components with direct camera access
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import cv2
import time
import numpy as np

def main():
    print("=" * 70)
    print("INTENT INTERFACE - COMPLETE LIVE DEMO (Week 1-9)")
    print("=" * 70)
    print()
    
    # Step 1: Open camera directly (we know this works!)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Cannot open camera")
        return
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    print("✅ Camera opened")
    
    # Step 2: Initialize object detector (YOLO for real object recognition!)
    detector_available = False
    detector = None
    
    # Try YOLO first for real object recognition
    try:
        from ultralytics import YOLO
        detector = YOLO('yolov8s.pt')  # Auto-downloads if needed (~22MB)
        detector_available = 'yolo'
        print("✅ YOLOv8 small model loaded (80 object classes)")
    except ImportError:
        print("⚠️  ultralytics not installed. Install with: pip install ultralytics")
        print("   Falling back to contour detector...")
        try:
            from vision.object_detector import ContourObjectDetector
            detector = ContourObjectDetector({
                'min_confidence': 0.5,
                'min_area_pixels': 1000,
                'max_detections': 10
            }, seed=42)
            print("✅ Contour detector loaded (generic objects only)")
            detector_available = 'contour'
        except Exception as e:
            print(f"❌ No detector available: {e}")
            print("   Running in camera-only mode")
    
    # Step 3: Initialize tracker
    tracker_available = False
    if detector_available:
        try:
            from vision.object_tracker import ObjectTracker
            tracker = ObjectTracker({
                'track_max_age_frames': 30,
                'track_min_hits': 3,
                'iou_match_threshold': 0.3,
                'track_new_confidence_threshold': 0.6
            }, seed=42)
            print("✅ Object tracker initialized")
            tracker_available = True
        except Exception as e:
            print(f"⚠️  Tracker not available: {e}")
    
    # Step 4: Initialize affordance engine
    affordances_available = False
    if tracker_available:
        try:
            from affordances.affordance_engine import AffordanceEngine
            affordance_engine = AffordanceEngine({
                'enabled': True,
                'max_affordance_options': 2
            }, seed=42)
            print("✅ Affordance engine initialized")
            affordances_available = True
        except Exception as e:
            print(f"⚠️  Affordances not available: {e}")
    
    print()
    
    # Show detection mode
    if detector_available == 'yolo':
        print("🎯 Detection Mode: YOLOv8 (recognizes 80 object types)")
        print("   Person, phone, laptop, cup, chair, etc.")
    elif detector_available == 'contour':
        print("⚠️  Detection Mode: Contour-based (generic objects only)")
        print("   To enable object recognition:")
        print("   pip install ultralytics")
    else:
        print("⚠️  No detector available - camera only")
    
    print()
    print("Controls:")
    print("  Q - Quit")
    print("  SPACE - Pause/Resume")
    print("  D - Toggle detection boxes")
    print()
    print("=" * 70)
    print()
    
    # State
    frame_count = 0
    paused = False
    show_detections = True
    detected_objects = []
    tracked_objects = []
    current_affordances = None
    
    fps_start = time.time()
    fps_frames = 0
    current_fps = 0
    
    try:
        while True:
            # Read frame
            ret, frame = cap.read()
            if not ret:
                print("❌ Failed to read frame")
                break
            
            frame_count += 1
            fps_frames += 1
            
            # Calculate FPS
            if fps_frames >= 30:
                fps_end = time.time()
                current_fps = fps_frames / (fps_end - fps_start)
                fps_start = fps_end
                fps_frames = 0
            
            if not paused:
                # Step 1: Object Detection
                if detector_available:
                    try:
                        if detector_available == 'yolo':
                            # YOLO detection (real object recognition!)
                            results = detector(frame, verbose=False, conf=0.5)
                            detected_objects = []
                            
                            # Convert YOLO results to our format
                            from vision.camera_stream import DetectedObject
                            for result in results:
                                boxes = result.boxes
                                for i in range(len(boxes)):
                                    box = boxes[i]
                                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                                    conf = float(box.conf[0])
                                    cls = int(box.cls[0])
                                    label = result.names[cls]
                                    
                                    # Convert to (x, y, w, h) format
                                    detected_objects.append(DetectedObject(
                                        detection_id=f"det_{frame_count}_{i}",
                                        label=label,
                                        bbox=(int(x1), int(y1), int(x2-x1), int(y2-y1)),
                                        confidence=conf,
                                        center_point=(int((x1+x2)/2), int((y1+y2)/2)),
                                        area=int((x2-x1)*(y2-y1))
                                    ))
                        
                        elif detector_available == 'contour':
                            # Contour detection (generic objects)
                            from vision.camera_stream import CameraFrame
                            camera_frame = CameraFrame(
                                image=frame,
                                frame_id=frame_count,
                                timestamp=time.time(),
                                width=frame.shape[1],
                                height=frame.shape[0],
                                fps=current_fps
                            )
                            detection_result = detector.detect(camera_frame)
                            detected_objects = detection_result.objects if hasattr(detection_result, 'objects') else []
                    except Exception as e:
                        print(f"Detection error: {e}")
                        detected_objects = []
                
                # Step 2: Tracking
                if tracker_available and detected_objects:
                    try:
                        track_result = tracker.update(detected_objects, timestamp=time.time())
                        tracked_objects = track_result.tracked_objects if hasattr(track_result, 'tracked_objects') else []
                    except Exception as e:
                        print(f"Tracking error: {e}")
                        tracked_objects = []
                
                # Step 3: Affordances (if we have a tracked object)
                if affordances_available and tracked_objects:
                    try:
                        # Get primary tracked object
                        primary = tracked_objects[0] if tracked_objects else None
                        if primary:
                            affordances = affordance_engine.compute(
                                scoped_object=primary,  # Pass the whole TrackedObject
                                ambiguity=False,  # No ambiguity in simple demo
                                frame_id=frame_count,
                                timestamp=time.time(),
                                frame=frame,
                                bbox=primary.bbox
                            )
                            current_affordances = affordances
                    except Exception as e:
                        print(f"Affordance error: {e}")
                        current_affordances = None
            
            # === DRAW UI ===
            display_frame = frame.copy()
            
            # Top bar - Status
            cv2.rectangle(display_frame, (0, 0), (640, 50), (40, 40, 40), -1)
            
            status_text = f"FPS: {current_fps:.1f} | Frame: {frame_count}"
            cv2.putText(display_frame, status_text, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            objects_text = f"Objects: {len(tracked_objects)}"
            cv2.putText(display_frame, objects_text, (450, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            
            # Draw detection boxes
            if show_detections and detected_objects:
                for obj in detected_objects:
                    x, y, w, h = obj.bbox
                    # Detection box (thin, cyan)
                    cv2.rectangle(display_frame, 
                                (int(x), int(y)), (int(x+w), int(y+h)),
                                (255, 255, 0), 1)
                    
                    # Label
                    label = f"{obj.label} {obj.confidence:.2f}"
                    cv2.putText(display_frame, label,
                              (int(x), int(y-5)),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            
            # Draw tracking boxes
            if show_detections and tracked_objects:
                for i, track in enumerate(tracked_objects):
                    x, y, w, h = track.bbox
                    
                    # Primary object (green, thick)
                    if i == 0:
                        color = (0, 255, 0)
                        thickness = 3
                    else:
                        color = (100, 255, 100)
                        thickness = 2
                    
                    cv2.rectangle(display_frame,
                                (int(x), int(y)), (int(x+w), int(y+h)),
                                color, thickness)
                    
                    # Track ID
                    track_label = f"Track {track.track_id}: {track.label}"
                    cv2.putText(display_frame, track_label,
                              (int(x), int(y-25)),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            # Bottom bar - Affordances
            if current_affordances and hasattr(current_affordances, 'options'):
                if current_affordances.options:
                    cv2.rectangle(display_frame, (0, 430), (640, 480), (0, 100, 0), -1)
                    
                    # Primary tracked object
                    if tracked_objects:
                        obj_label = tracked_objects[0].label
                        cv2.putText(display_frame, f"Focused: {obj_label}",
                                  (10, 455), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    # Affordances
                    action = current_affordances.options[0].title if current_affordances.options else "None"
                    cv2.putText(display_frame, f"Action: {action}",
                              (10, 475), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
            
            # Paused indicator
            if paused:
                cv2.putText(display_frame, "PAUSED", (270, 240),
                          cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            
            # Show frame
            cv2.imshow('Intent Interface - Complete Demo (Press Q to quit)', display_frame)
            
            # Keyboard controls
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = not paused
                print(f"\n{'⏸️  PAUSED' if paused else '▶️  RESUMED'}")
            elif key == ord('d'):
                show_detections = not show_detections
                print(f"\nDetection boxes: {'ON' if show_detections else 'OFF'}")
            
            # Print status every 60 frames
            if frame_count % 60 == 0:
                if tracked_objects:
                    print(f"\n[Frame {frame_count}] Tracking {len(tracked_objects)} objects")
                    for track in tracked_objects[:3]:  # Show first 3
                        print(f"  - {track.label} (ID: {track.track_id}, age: {track.age_frames})")
                else:
                    print(f"\n[Frame {frame_count}] No objects detected")
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted")
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        
        elapsed = time.time() - fps_start
        print("\n" + "=" * 70)
        print("Demo Summary:")
        print(f"  Total frames: {frame_count}")
        print(f"  Duration: {elapsed:.1f}s")
        print(f"  Average FPS: {frame_count/elapsed if elapsed > 0 else 0:.1f}")
        print("=" * 70)
        print("\n✅ Demo complete!")

if __name__ == '__main__':
    main()

