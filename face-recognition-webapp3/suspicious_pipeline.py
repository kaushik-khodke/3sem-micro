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


class WeaponDetector:
    """Detects weapons and dangerous objects using standard YOLOv8 model."""
    
    def __init__(self):
        import torch
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"[WeaponDetector] Loading object model: {model_path} on {self.device}")
        self.model = YOLO(model_path)
        if not model_path.endswith(".onnx"):
            self.model.fuse()
        self.model.to(self.device)
        # COCO class names for weapons
        self.weapon_names = {
            config.KNIFE: "KNIFE",
            config.SCISSORS: "SCISSORS",
            config.BASEBALL_BAT: "BAT",
        }
        self.dangerous_names = {
            **self.weapon_names,
            config.BOTTLE: "BOTTLE",
        }
        print(f"[WeaponDetector] Initialized - detecting: {list(self.dangerous_names.values())}")
    
    def detect(self, frame):
        """Run detection and return list of weapon detections."""
        results = self.model(
            frame,
            imgsz=config.WEAPON_IMG_SIZE,  # 640px — higher res for small objects
            conf=0.20,  # lower threshold to catch partially visible weapons
            iou=config.IOU_THRESHOLD,
            classes=config.DANGEROUS_OBJECTS,
            verbose=False,
        )
        
        detections = []
        if results and len(results) > 0:
            boxes = results[0].boxes
            if boxes is not None and len(boxes) > 0:
                xyxy = boxes.xyxy.cpu().numpy()
                classes = boxes.cls.cpu().numpy().astype(int)
                confs = boxes.conf.cpu().numpy()
                
                for i in range(len(classes)):
                    cls_id = classes[i]
                    is_weapon = cls_id in self.weapon_names
                    detections.append({
                        "bbox": tuple(xyxy[i]),
                        "class": cls_id,
                        "name": self.dangerous_names.get(cls_id, f"obj_{cls_id}"),
                        "conf": float(confs[i]),
                        "is_weapon": is_weapon,  # True for knife/scissors/bat
                    })
        return detections


class SuspiciousPipeline:
    def __init__(self):
        import os
        # Ensure we are in the correct directory for model loading
        project_dir = os.path.dirname(os.path.abspath(__file__))
        original_cwd = os.getcwd()
        
        try:
            os.chdir(project_dir)
            self.detector = Detector()
            self.weapon_detector = WeaponDetector()
            self.loiter_detector = LoiteringDetector()
            self.abandon_detector = AbandonedObjectDetector()
            self.conflict_detector = ConflictDetector()
            self.scorer = ThreatScorer()
            
            # Optimization: frame skipping state
            self.frame_count = 0
            self.last_tracked_objects = []
            self.last_suspicious_ids = []
            self.last_suspicious_bags = []
            self.last_conflict_alert = False
            self.last_pair_scores = {}
            self.last_weapon_detections = []
            self.last_instant_scores = {}
            self.last_session_scores = {}
            
            print(f"[SuspiciousPipeline] Initialized successfully (Detect every {config.DETECT_EVERY_N} frames)")
        except Exception as e:
            print(f"[SuspiciousPipeline] INIT ERROR: {e}")
            raise
        finally:
            os.chdir(original_cwd)

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
            
            # === Optimization: Frame Skipping ===
            self.frame_count += 1
            is_detect_frame = (self.frame_count % config.DETECT_EVERY_N == 0)
            
            if is_detect_frame:
                # === Person detection (pose model) ===
                results = self.detector.detect(frame)
                tracked_objects = self.detector.parse_tracked_objects(results)
                
                video_timestamp = time.time()
                
                suspicious_ids = self.loiter_detector.update(tracked_objects)
                suspicious_bags = self.abandon_detector.update(tracked_objects)
                conflict_alert, pair_scores = self.conflict_detector.update(tracked_objects, video_timestamp)
                
                # === Weapon detection (standard model) ===
                weapon_detections = self.weapon_detector.detect(frame)
                
                instant_scores, session_scores = self.scorer.update(
                    tracked_objects, suspicious_ids, suspicious_bags, 
                    conflict_alert, pair_scores, weapons_found=[d for d in weapon_detections if d["is_weapon"]]
                )
                
                # Update cache
                self.last_tracked_objects = tracked_objects
                self.last_suspicious_ids = suspicious_ids
                self.last_suspicious_bags = suspicious_bags
                self.last_conflict_alert = conflict_alert
                self.last_pair_scores = pair_scores
                self.last_weapon_detections = weapon_detections
                self.last_instant_scores = instant_scores
                self.last_session_scores = session_scores
            else:
                # Reuse cached results for smooth UI
                tracked_objects = self.last_tracked_objects
                suspicious_ids = self.last_suspicious_ids
                suspicious_bags = self.last_suspicious_bags
                conflict_alert = self.last_conflict_alert
                pair_scores = self.last_pair_scores
                weapon_detections = self.last_weapon_detections
                instant_scores = self.last_instant_scores
                session_scores = self.last_session_scores

            # Filter weapons for logic below
            weapons_found = [d for d in weapon_detections if d["is_weapon"]]
            dangerous_found = weapon_detections
            
            # Collect ALL active alerts (multiple can fire at once)
            active_alerts = []
            alert_states = []
            
            if weapons_found:
                weapon_names_str = ", ".join(set(w["name"] for w in weapons_found))
                alert_states.append("WEAPON")
                active_alerts.append(("WEAPON DETECTED: " + weapon_names_str, (0, 0, 180)))
            if conflict_alert:
                alert_states.append("CONFLICT")
                active_alerts.append(("POSSIBLE PHYSICAL CONFLICT", (0, 0, 255)))
            if suspicious_bags:
                alert_states.append("ABANDONED")
                active_alerts.append(("ABANDONED OBJECT DETECTED", (0, 80, 255)))
            if suspicious_ids:
                alert_states.append("LOITERING")
                active_alerts.append(("LOITERING DETECTED - SUSPICIOUS BEHAVIOR", (0, 140, 255)))
            
            current_alert_state = "+".join(alert_states) if alert_states else "NONE"
                
            # Draw person detections
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

            # Draw weapon/dangerous object detections
            for det in dangerous_found:
                x1, y1, x2, y2 = det["bbox"]
                name = det["name"]
                conf = det["conf"]
                is_weapon = det["is_weapon"]
                
                if is_weapon:
                    # Bright red pulsing box for weapons
                    color = (0, 0, 255)
                    thickness = 3
                    label = f"!! {name} ({conf:.0%}) !!"
                else:
                    color = (0, 165, 255)  # orange for dangerous objects
                    thickness = 2
                    label = f"{name} ({conf:.0%})"
                
                cv2.rectangle(frame_copy, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)
                
                # Background rectangle for label
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                cv2.rectangle(frame_copy, (int(x1), int(y1) - th - 10), (int(x1) + tw, int(y1)), color, -1)
                cv2.putText(frame_copy, label, (int(x1), int(y1) - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # Alert banner — show ALL active alerts stacked
            if active_alerts:
                banner_h = 40 + 35 * len(active_alerts)
                overlay = frame_copy.copy()
                # Use the most severe color (first alert = highest priority)
                worst_color = active_alerts[0][1]
                cv2.rectangle(overlay, (0, 0), (frame_copy.shape[1], banner_h), worst_color, -1)
                cv2.addWeighted(overlay, 0.6, frame_copy, 0.4, 0, frame_copy)
                
                y_text = 30
                for alert_text, alert_color in active_alerts:
                    # Small colored indicator dot
                    cv2.circle(frame_copy, (25, y_text - 5), 8, alert_color, -1)
                    cv2.putText(frame_copy, alert_text, (42, y_text),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    y_text += 35

            # Side panel
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

            # Show weapon alerts in panel
            if weapons_found:
                cv2.putText(extended_frame, "WEAPONS DETECTED:", (panel_x + margin_left, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                y_offset += 25
                for det in weapons_found:
                    cv2.putText(extended_frame, f"  {det['name']} ({det['conf']:.0%})", 
                                (panel_x + margin_left + 10, y_offset),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    y_offset += 22
                y_offset += 10
                cv2.line(extended_frame,
                        (panel_x + margin_left, y_offset),
                        (panel_x + panel_width - margin_left, y_offset),
                        (100, 100, 100), 1)
                y_offset += 15

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
            import traceback
            traceback.print_exc()
            return None

