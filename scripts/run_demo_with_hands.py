#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import cv2
import time
import math
from ultralytics import YOLO

# Try to import MediaPipe
try:
    import mediapipe as mp
    mp_hands = mp.solutions.hands
    HANDS_AVAILABLE = True
except Exception as e:
    print(f"⚠️  MediaPipe not available: {e}")
    HANDS_AVAILABLE = False

def main():
    print("=" * 70)
    print("INTENT INTERFACE - HAND GESTURE DEMO")
    print("=" * 70)
    
    # Load YOLO
    print("Loading YOLOv8s...")
    model = YOLO('yolov8s.pt')
    print("✅ YOLOv8s loaded")
    
    # Initialize hand detection
    hands = None
    if HANDS_AVAILABLE:
        try:
            hands = mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            print("✅ Hand detector initialized")
        except Exception as e:
            print(f"⚠️  Hand detector failed: {e}")
            hands = None
    else:
        print("⚠️  Running without hand detection (install: pip install mediapipe)")
    
    # Open camera
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    print()
    print("Controls: Q=Quit, SPACE=Pause, H=Toggle hand overlay")
    print("Make pinch gesture (thumb + index finger touch) to confirm")
    print("=" * 70)
    print()
    
    frame_count = 0
    paused = False
    show_hands = True
    
    # Pinch tracking
    pinch_frames = 0
    pinch_required = 6
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            display_frame = frame.copy()
            h, w, _ = frame.shape
            
            hand_detected = False
            pinch_detected = False
            pinch_distance = 0
            detected_objects = []
            
            if not paused:
                # YOLO detection
                try:
                    results = model(frame, verbose=False, conf=0.5)
                    
                    for result in results:
                        boxes = result.boxes
                        for box in boxes:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            conf = float(box.conf[0])
                            cls = int(box.cls[0])
                            label = model.names[cls]
                            
                            # Draw detection
                            cv2.rectangle(display_frame, 
                                        (int(x1), int(y1)), (int(x2), int(y2)),
                                        (255, 255, 0), 2)
                            cv2.putText(display_frame, f"{label} {conf:.2f}",
                                      (int(x1), int(y1-5)),
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
                            
                            detected_objects.append(label)
                except Exception as e:
                    print(f"YOLO error: {e}")
                
                # Hand detection
                if hands is not None and show_hands:
                    try:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        hand_results = hands.process(frame_rgb)
                        
                        if hand_results.multi_hand_landmarks:
                            hand_detected = True
                            
                            for hand_landmarks in hand_results.multi_hand_landmarks:
                                # Get thumb tip (4) and index tip (8)
                                thumb_tip = hand_landmarks.landmark[4]
                                index_tip = hand_landmarks.landmark[8]
                                
                                # Pixel coordinates
                                thumb_x = int(thumb_tip.x * w)
                                thumb_y = int(thumb_tip.y * h)
                                index_x = int(index_tip.x * w)
                                index_y = int(index_tip.y * h)
                                
                                # Calculate pinch distance
                                pinch_distance = math.sqrt(
                                    (thumb_x - index_x)**2 + (thumb_y - index_y)**2
                                )
                                
                                # Pinch threshold (40 pixels)
                                if pinch_distance < 40:
                                    pinch_detected = True
                                    pinch_frames += 1
                                else:
                                    pinch_frames = 0
                                
                                # Draw hand skeleton
                                for landmark in hand_landmarks.landmark:
                                    lx, ly = int(landmark.x * w), int(landmark.y * h)
                                    cv2.circle(display_frame, (lx, ly), 3, (255, 0, 255), -1)
                                
                                # Draw pinch indicators
                                cv2.circle(display_frame, (thumb_x, thumb_y), 10, (0, 255, 0), 2)
                                cv2.circle(display_frame, (index_x, index_y), 10, (0, 255, 0), 2)
                                
                                line_color = (0, 255, 0) if pinch_detected else (255, 255, 0)
                                cv2.line(display_frame, (thumb_x, thumb_y), 
                                       (index_x, index_y), line_color, 3)
                                
                                # Distance text
                                mid_x = (thumb_x + index_x) // 2
                                mid_y = (thumb_y + index_y) // 2
                                cv2.putText(display_frame, f"{pinch_distance:.0f}px",
                                          (mid_x, mid_y - 10),
                                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    except Exception as e:
                        print(f"Hand detection error: {e}")
            
            # UI Overlay
            # Top bar
            cv2.rectangle(display_frame, (0, 0), (640, 60), (40, 40, 40), -1)
            cv2.putText(display_frame, f"Frame: {frame_count} | Objects: {len(detected_objects)}",
                       (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # Hand status
            if hands is not None:
                hand_text = "✓ Hand" if hand_detected else "✗ No Hand"
                hand_color = (0, 255, 0) if hand_detected else (100, 100, 100)
                cv2.putText(display_frame, hand_text, (10, 50),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, hand_color, 2)
                
                # Pinch status
                if hand_detected:
                    if pinch_detected:
                        pinch_text = f"👌 PINCH {pinch_frames}/{pinch_required}"
                        pinch_color = (0, 255, 0)
                    else:
                        pinch_text = "○ Open"
                        pinch_color = (255, 255, 0)
                    cv2.putText(display_frame, pinch_text, (200, 50),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, pinch_color, 2)
                    
                    # Progress bar
                    bar_width = 200
                    bar_filled = int((pinch_frames / pinch_required) * bar_width)
                    cv2.rectangle(display_frame, (420, 35), (420 + bar_width, 55), (60, 60, 60), -1)
                    cv2.rectangle(display_frame, (420, 35), (420 + bar_filled, 55), (0, 255, 0), -1)
                    cv2.rectangle(display_frame, (420, 35), (420 + bar_width, 55), (255, 255, 255), 2)
            
            # Confirmation indicator
            if pinch_frames >= pinch_required:
                cv2.rectangle(display_frame, (150, 200), (490, 280), (0, 200, 0), -1)
                cv2.putText(display_frame, "✓ CONFIRMED!", (180, 250),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)
            
            # Paused indicator
            if paused:
                cv2.putText(display_frame, "PAUSED", (250, 350),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            
            # Show frame
            cv2.imshow('Intent Interface - Hand Gesture Demo', display_frame)
            
            # Controls
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = not paused
                print(f"{'PAUSED' if paused else 'RESUMED'}")
            elif key == ord('h'):
                show_hands = not show_hands
                print(f"Hand overlay: {'ON' if show_hands else 'OFF'}")
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if hands:
            hands.close()
        print(f"\n✅ Demo complete! Frames: {frame_count}")

if __name__ == '__main__':
    main()
