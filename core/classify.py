import cv2
import numpy as np
import os
import shutil
import re
from pathlib import Path

def analyze_video_robust(video_path, num_samples=5):
    """
    結合相關性、通道差與三通道標準差的高強健分析。
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened(): return None
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0: cap.release(); return None
    
    sample_indices = np.linspace(total_frames * 0.1, total_frames * 0.9, num_samples).astype(int)
    results = []
    
    for idx in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret: continue
        
        b, g, r = cv2.split(frame)
        
        # 1. 通道相關性 (IR 應高度同步)
        corr_rg = np.corrcoef(r.flatten(), g.flatten())[0, 1]
        corr_gb = np.corrcoef(g.flatten(), b.flatten())[0, 1]
        avg_corr = (corr_rg + corr_gb) / 2
        
        # 2. 通道間絕對誤差 (MAE)
        avg_diff = np.mean([
            np.mean(np.abs(r.astype(np.float32) - g.astype(np.float32))),
            np.mean(np.abs(g.astype(np.float32) - b.astype(np.float32)))
        ])
        
        # 3. 三通道標準差 (Std) - 判斷顏色偏移程度
        # 即使強光，彩色影像的 R, G, B 平均值仍會有較大標準差
        std_rgb = np.std([np.mean(r), np.mean(g), np.mean(b)])
        
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        results.append({
            'corr': avg_corr, 
            'diff': avg_diff, 
            'std': std_rgb,
            'sat': np.mean(hsv[:, :, 1]), 
            'bright': np.mean(hsv[:, :, 2])
        })
    
    cap.release()
    if not results: return None
    
    return {k: np.mean([r[k] for r in results]) for k in results[0].keys()}

def classify_videos(source_dir, target_base):
    source_path = Path(source_dir)
    target_path = Path(target_base)
    video_files = list(source_path.rglob("*.mp4"))
    print(f"啟動強光補償分類模式，處理 {len(video_files)} 個檔案...")
    
    counts = {"COLOR_STABLE": 0, "IR_MODE": 0, "ERROR": 0}
    
    for video_file in video_files:
        match = re.search(r"(\d{8})[_-](\d{6})", video_file.name)
        yymmdd = match.group(1)[2:] if match else "UNKNOWN"
        
        metrics = analyze_video_robust(video_file)
        if metrics is None: counts["ERROR"] += 1; continue
        
        c, d, std, s, b = metrics['corr'], metrics['diff'], metrics['std'], metrics['sat'], metrics['bright']
        
        # 嚴謹判斷：必須同時滿足高相關性與極低標準差
        is_ir = (c > 0.999 and d < 2.5 and std < 1.5) or (c > 0.995 and d < 4.0 and s < 10.0)
        
        mode = "IR_MODE" if is_ir else "COLOR_STABLE"
        counts[mode] += 1
        print(f"  [分析] {video_file.name[:15]} C:{c:.4f} D:{d:.1f} Std:{std:.1f} -> {mode}")
        
        dest_dir = target_path / mode / yymmdd
        dest_dir.mkdir(parents=True, exist_ok=True)
        try: shutil.move(str(video_file), str(dest_dir / video_file.name))
        except Exception as e: print(f"  搬移失敗: {e}")
        
    print(f"\n分類統計：COLOR: {counts['COLOR_STABLE']}, IR: {counts['IR_MODE']}")

if __name__ == "__main__":
    classify_videos("Test", "COW_dataset")
