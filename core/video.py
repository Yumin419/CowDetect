import math
import os
import cv2
import numpy as np
from ultralytics import YOLO

class CowDetector:
    def __init__(self, model_path, class_id=0, device='cuda'):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"找不到模型權重：{model_path}")
        self.model = YOLO(model_path)
        self.class_id = class_id
        self.device = device

    def track(self, frame, conf=0.2):
        """
        使用 YOLO tracking 模式。
        """
        return self.model.track(
            frame, persist=True,
            conf=conf, classes=[self.class_id],
            verbose=False, device=self.device,
            imgsz=1280, agnostic_nms=True,
            augment=True,
            tracker="configs/custom_tracker.yaml"
        )


class VirtualFence:
    """
    雙向虛擬圍籬，支持長寬比過濾。
    """

    def __init__(self, roi, patience_frames=30, max_segment_frames=None, ioa_threshold=0.5):
        self.roi = roi
        self.patience_frames = patience_frames
        self.max_segment_frames = max_segment_frames
        self.ioa_threshold = ioa_threshold
        self.midpoint_x = (roi[0] + roi[2]) / 2
        # track_id -> {start_frame, entry_side, last_x, lost_frames, aspect_ratios, ...}
        self.tracks = {}

    def draw(self, frame, results=None):
        x1, y1, x2, y2 = self.roi
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 0), 3)
        cv2.line(frame, (int(self.midpoint_x), y1), (int(self.midpoint_x), y2), (0, 0, 255), 4)
        cv2.putText(frame, "DETECTION ZONE", (x1 + 10, y1 + 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 0), 3)

        if results:
            for result in results:
                if result.boxes.id is not None:
                    boxes = result.boxes.xyxy.cpu().numpy()
                    ids = result.boxes.id.cpu().numpy()
                    confs = result.boxes.conf.cpu().numpy()
                    for box, track_id, conf in zip(boxes, ids, confs):
                        bx1, by1, bx2, by2 = map(int, box)
                        is_in = self.is_inside([bx1, by1, bx2, by2])
                        color = (0, 255, 0) if is_in else (0, 165, 255)
                        cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, 4)
                        
                        w, h = bx2 - bx1, by2 - by1
                        aspect = w / h if h > 0 else 0
                        label = f"ID:{int(track_id)} {conf:.2f} A:{aspect:.1f}"
                        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
                        cv2.rectangle(frame, (bx1, by1 - th - 15), (bx1 + tw, by1), color, -1)
                        cv2.putText(frame, label, (bx1, by1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        return frame

    def reset(self):
        self.tracks.clear()

    def _side(self, x):
        return 'left' if x < self.midpoint_x else 'right'

    def _get_stable_aspect(self, aspects):
        """
        取長寬比分位數，排除因模型震盪產生的極端值。
        取 75 分位數 (P75)，因為乳牛應在多數時間呈現橫向。
        """
        if not aspects: return 0
        return float(np.percentile(aspects, 75))

    def check_trigger(self, results, frame_idx):
        events = []
        active_ids_in_roi = set()

        for result in results:
            if result.boxes.id is None:
                continue
            ids = result.boxes.id.tolist()
            for box, raw_id in zip(result.boxes, ids):
                track_id = int(raw_id)
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2

                if not self.is_inside([x1, y1, x2, y2]):
                    continue

                active_ids_in_roi.add(track_id)
                w, h = x2 - x1, y2 - y1
                current_aspect = w / h if h > 0 else 0

                if track_id not in self.tracks:
                    entry_side = self._side(cx)
                    self.tracks[track_id] = {
                        'start_frame': frame_idx,
                        'entry_side': entry_side,
                        'last_x': cx,
                        'last_seen_frame': frame_idx,
                        'lost_frames': 0,
                        'entry_cx': cx,
                        'entry_cy': cy,
                        'max_disp': 0.0,
                        'aspects': [current_aspect]
                    }
                    events.append({
                        'event': 'enter',
                        'track_id': track_id,
                        'start_frame': frame_idx,
                        'end_frame': None,
                        'entry_side': entry_side,
                        'exit_side': None,
                        'max_disp': 0.0,
                    })
                else:
                    state = self.tracks[track_id]
                    state['last_x'] = cx
                    state['last_seen_frame'] = frame_idx
                    state['lost_frames'] = 0
                    state['aspects'].append(current_aspect)

                    disp = math.hypot(cx - state['entry_cx'], cy - state['entry_cy'])
                    if disp > state['max_disp']:
                        state['max_disp'] = disp

                    if self.max_segment_frames is not None:
                        elapsed = frame_idx - state['start_frame']
                        if elapsed >= self.max_segment_frames:
                            stable_asp = self._get_stable_aspect(state['aspects'])
                            events.append({
                                'event': 'segment_split',
                                'track_id': track_id,
                                'start_frame': state['start_frame'],
                                'end_frame': frame_idx,
                                'entry_side': state['entry_side'],
                                'exit_side': None,
                                'max_disp': state['max_disp'],
                                'avg_aspect': stable_asp
                            })
                            state['start_frame'] = frame_idx
                            state['entry_side'] = self._side(cx)
                            state['entry_cx'] = cx
                            state['entry_cy'] = cy
                            state['max_disp'] = 0.0
                            state['aspects'] = [current_aspect]

        to_remove = []
        for track_id, state in self.tracks.items():
            if track_id in active_ids_in_roi:
                continue
            state['lost_frames'] += 1
            if state['lost_frames'] >= self.patience_frames:
                end_frame = state['last_seen_frame']
                exit_side = self._side(state['last_x'])
                stable_asp = self._get_stable_aspect(state['aspects'])
                events.append({
                    'event': 'exit_valid',
                    'track_id': track_id,
                    'start_frame': state['start_frame'],
                    'end_frame': end_frame,
                    'entry_side': state['entry_side'],
                    'exit_side': exit_side,
                    'max_disp': state['max_disp'],
                    'avg_aspect': stable_asp
                })
                to_remove.append(track_id)

        for track_id in to_remove:
            del self.tracks[track_id]

        return events

    def flush(self, frame_idx):
        events = []
        for track_id, state in self.tracks.items():
            stable_asp = self._get_stable_aspect(state['aspects'])
            events.append({
                'event': 'exit_valid',
                'track_id': track_id,
                'start_frame': state['start_frame'],
                'end_frame': state['last_seen_frame'],
                'entry_side': state['entry_side'],
                'exit_side': self._side(state['last_x']),
                'max_disp': state['max_disp'],
                'avg_aspect': stable_asp
            })
        self.tracks.clear()
        return events

    def is_inside(self, box):
        bx1, by1, bx2, by2 = box
        rx1, ry1, rx2, ry2 = self.roi
        
        # Calculate intersection
        ix1 = max(bx1, rx1)
        iy1 = max(by1, ry1)
        ix2 = min(bx2, rx2)
        iy2 = min(by2, ry2)
        
        if ix2 <= ix1 or iy2 <= iy1:
            return False
            
        inter_area = (ix2 - ix1) * (iy2 - iy1)
        box_area = (bx2 - bx1) * (by2 - by1)
        
        if box_area <= 0:
            return False
            
        ioa = inter_area / box_area
        return ioa >= self.ioa_threshold


def extract_video_segment(video_path, start_frame, end_frame, fps, output_path):
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    current = start_frame
    while current <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break
        out.write(frame)
        current += 1
    cap.release()
    out.release()
