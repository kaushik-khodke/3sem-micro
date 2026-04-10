import cv2
import numpy as np
import time
import base64
import os

from detection.detector import Detector
from behavior.loitering import LoiteringDetector
from behavior.conflict_detection import ConflictDetector
from behavior.scoring import ThreatScorer
from behavior.abandoned_object import AbandonedObjectDetector
from utils.drawing import draw_keypoints
import config

# Disable backend audio alert to avoid server beep
config.ENABLE_BEEP = False

class SuspiciousPipeline:
    def __init__(self):
        # Change working directory so models load correctly if any relative paths used in ultralytics
        self.detector = Detector()
        self.loiter_detector = LoiteringDetector()
        self.abandon_detector = AbandonedObjectDetector()
        self.conflict_detector = ConflictDetector()
        self.scorer = ThreatScorer()
        
    def reset(self):
        """Clear temporal states when session starts/restarts"""
        if hasattr(self.loiter_detector, "person_state"):
            self.loiter_detector.person_state.clear()
        if hasattr(self.abandon_detector, "bag_state"):
            self.abandon_detector.bag_state.clear()
        if hasattr(self.conflict_detector, "history"):
            self.conflict_detector.history.clear()
        if hasattr(self.conflict_detector, "person_kp"):
            self.conflict_detector.person_kp.clear()
        if hasattr(self.scorer, "instant_scores"):
            self.scorer.instant_scores.clear()
            
    def process_frame_base64(self, b64_str):
        try:
            # decode base64
            image_bytes = base64.b64decode(b64_str)
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                return None
                
            # Resize to fixed size as in original
            frame = cv2.resize(frame, (config.FRAME_WIDTH, config.FRAME_HEIGHT))
            frame_copy = frame.copy()
            
            # pass frame through detector
            results = self.detector.detect(frame)
            tracked_objects = self.detector.parse_tracked_objects(results)
            
            video_timestamp = time.time()
            
            suspicious_ids = self.loiter_detector.update(tracked_objects)
            suspicious_bags = self.abandon_detector.update(tracked_objects)
            conflict_alert, pair_scores = self.conflict_detector.update(tracked_objects, video_timestamp)
            instant_scores, session_scores = self.scorer.update(
                tracked_objects, suspicious_ids, suspicious_bags, conflict_alert, pair_scores
            )
            
            # Drawing logic ported from main.py
            active_alert = None
            current_alert_state = "NONE"
            if conflict_alert:
                current_alert_state = "CONFLICT"
                active_alert = "POSSIBLE PHYSICAL CONFLICT"
            elif suspicious_bags:
                current_alert_state = "ABANDONED"
                active_alert = "ABANDONED OBJECT DETECTED"
                
            for obj in tracked_objects:
                x1, y1, x2, y2 = obj["bbox"]
                obj_id = obj["id"]
                cls = obj["class"]
                class_name = obj["name"]
                conf = obj["conf"]

                color = (0, 255, 0)
                if obj_id in suspicious_ids or obj_id in suspicious_bags:
                    color = (0, 0, 255)

                label = f"{class_name} ID:{obj_id}"
                if cls == config.PERSON and obj_id in instant_scores:
                    level = self.scorer.get_level(instant_scores[obj_id])
                    session_total = session_scores.get(obj_id, 0)
                    label += f" | Threat: {level} | Session: {session_total}"

                cv2.rectangle(frame_copy, (int(x1), int(y1)), (int(x2), int(y2)), color, config.BOX_THICKNESS)
                cv2.putText(frame_copy, label, (int(x1), int(y1) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, config.FONT_SCALE, color, config.FONT_THICKNESS)

                if config.SHOW_KEYPOINTS and cls == config.PERSON:
                    persons_in_frame = [o for o in tracked_objects if o["class"] == config.PERSON]
                    draw_keypoints(frame_copy, obj, all_persons=persons_in_frame)

            if active_alert:
                overlay = frame_copy.copy()
                cv2.rectangle(overlay, (0, 0), (frame_copy.shape[1], 80), (0, 0, 255), -1)
                cv2.addWeighted(overlay, 0.6, frame_copy, 0.4, 0, frame_copy)
                cv2.putText(frame_copy, active_alert, (50, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)

            panel_width = 350
            h, w, _ = frame_copy.shape
            extended_frame = np.zeros((h, w + panel_width, 3), dtype=np.uint8)
            extended_frame[:, :w] = frame_copy
            extended_frame[:, w:] = (30, 30, 30)

            panel_x = w
            margin_left = 15
            y_offset = 35

            cv2.putText(extended_frame, "THREAT ANALYSIS", (panel_x + margin_left, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            y_offset += 10
            cv2.line(extended_frame,
                    (panel_x + margin_left, y_offset),
                    (panel_x + panel_width - margin_left, y_offset),
                    (100, 100, 100), 1)
            y_offset += 30

            cv2.putText(extended_frame, "ACTIVE THREATS:", (panel_x + margin_left, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
            y_offset += 25

            for pid, score in instant_scores.items():
                level = self.scorer.get_level(score)
                session_total = session_scores.get(pid, 0)
                color = (0, 255, 0)
                if level == "SUSPICIOUS":
                    color = (0, 165, 255)
                elif level == "HIGH":
                    color = (0, 0, 255)

                cv2.putText(extended_frame, f"ID {pid}:", (panel_x + margin_left + 10, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
                cv2.putText(extended_frame, level, (panel_x + margin_left + 70, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
                cv2.putText(extended_frame, f"({score})", (panel_x + margin_left + 185, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
                y_offset += 22
                cv2.putText(extended_frame, f"  Session Total: {session_total}",
                            (panel_x + margin_left + 10, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1)
                y_offset += 28

            # Encode back to base64
            _, buffer = cv2.imencode('.jpg', extended_frame)
            b64_out = base64.b64encode(buffer).decode('utf-8')
            
            return {
                "image": b64_out,
                "active_alert": current_alert_state
            }
        except Exception as e:
            print(f"Error in pipeline: {e}")
            return None
