import argparse
import os
import cv2
import re
from core.trainer import CowTrainer
from core.video import CowDetector, VirtualFence, extract_video_segment
from data_utils.formatter import prepare_yolo_dataset
from data_utils.validator import fix_yolo_labels

def main():
    parser = argparse.ArgumentParser(description="乳牛監測與系統專業模組 (Strict Mode)")
    subparsers = parser.add_subparsers(dest="command", help="執行指令")

    # 1. 資料處理
    data_parser = subparsers.add_parser("data", help="資料預處理")
    data_parser.add_argument("--fix", action="store_true", help="執行標籤修正")
    data_parser.add_argument("--prepare", action="store_true", help="執行資料集分割")
    data_parser.add_argument("--classify", action="store_true", help="執行影像自動分類")

    # 2. 虛擬圍籬
    fence_parser = subparsers.add_parser("fence", help="虛擬圍籬影片分析")
    fence_parser.add_argument("--input", required=True, help="影片路徑或包含影片的資料夾路徑")
    fence_parser.add_argument("--model", required=True, help="模型權重路徑")
    fence_parser.add_argument("--class_id", type=int, default=0, help="類別索引 (預設 0)")
    fence_parser.add_argument("--device", default="cuda", help="使用的裝置 (cpu, cuda, 0, 1...)")
    fence_parser.add_argument("--show", action="store_true", help="是否顯示視覺化即時畫面")
    fence_parser.add_argument("--conf", type=float, default=0.2, help="偵測信心門檻 (預設 0.2)")
    fence_parser.add_argument("--skip", type=int, default=1, help="跳格掃描率 (預設 1)")
    fence_parser.add_argument("--min_aspect", type=float, default=2.0, help="最小長寬比 (預設 2.0)")
    fence_parser.add_argument("--ioa", type=float, default=0.5, help="IoA 判定門檻 (預設 0.5)")
    fence_parser.add_argument("--classify", action="store_true", help="擷取後自動執行影像分類")

    args = parser.parse_args()

    if args.command == "data":
        if args.fix:
            fix_yolo_labels("my_dataset/labels")
        if args.prepare:
            prepare_yolo_dataset()
        if args.classify:
            from core.classify import classify_videos
            print(f"正在分類資料夾: Test")
            classify_videos("Test", "COW_dataset")

    elif args.command == "fence":
        video_list = []
        if os.path.isfile(args.input):
            video_list.append(args.input)
        elif os.path.isdir(args.input):
            for root, dirs, files in os.walk(args.input):
                for f in files:
                    if f.lower().endswith(('.mp4', '.avi', '.mov')):
                        video_list.append(os.path.join(root, f))
        else:
            print(f"錯誤: 找不到輸入路徑 {args.input}")
            return

        if not video_list:
            print(f"資訊: 在 {args.input} 中找不到可處理的影片檔案")
            return

        # 門檻常數 (對標 OPERATING_MANUAL.md)
        MIN_DURATION_SEC = 3.0
        MAX_SEGMENT_SEC = 20.0
        MIN_DISPLACEMENT_PX = 100.0
        PAD_SEC = 3.0

        detector = CowDetector(args.model, class_id=args.class_id, device=args.device)
        roi = [20, 100, 2800, 1500]
        # 提高容忍度
        fence = VirtualFence(roi, patience_frames=90, ioa_threshold=args.ioa)
        output_dir = "Test"
        os.makedirs(output_dir, exist_ok=True)

        print(f"準備處理 {len(video_list)} 部影片... (使用裝置: {args.device}, 門檻: {args.min_aspect})")
        for video_path in video_list:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print(f"  [跳過] 無法開啟影片: {video_path}")
                continue

            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_idx = 0
            seg_count = 0

            raw_base_name = os.path.splitext(os.path.basename(video_path))[0]
            match = re.search(r"(\d{8})-(\d{6})", raw_base_name)
            video_base_name = f"{match.group(1)}_{match.group(2)}" if match else raw_base_name

            print(f"\n[處理中] {video_path}")
            fence.max_segment_frames = int(MAX_SEGMENT_SEC * fps)
            fence.reset()
            last_results = None

            while True:
                ret, frame = cap.read()
                if not ret:
                    events = fence.flush(frame_idx)
                else:
                    if frame_idx % args.skip == 0:
                        results = detector.track(frame, conf=args.conf)
                        events = fence.check_trigger(results, frame_idx)
                        last_results = results
                    else:
                        events = []

                    if args.show:
                        viz_frame = frame.copy()
                        fence.draw(viz_frame, last_results)
                        
                        obj_count = 0
                        if last_results and last_results[0].boxes.id is not None:
                            obj_count = len(last_results[0].boxes.id)
                        cv2.putText(viz_frame, f"Detected: {obj_count} | Aspect: {args.min_aspect}", (50, 100),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3)

                        h, w = viz_frame.shape[:2]
                        display_frame = cv2.resize(viz_frame, (w // 2, h // 2))
                        cv2.imshow("COW Virtual Fence Preview", display_frame)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            print("使用者手動中斷。")
                            cap.release()
                            cv2.destroyAllWindows()
                            return

                for ev in events:
                    etype = ev['event']
                    tid = ev['track_id']
                    start = ev['start_frame']
                    end = ev['end_frame']

                    if etype == 'enter':
                        print(f"  [進入] ID:{tid}")
                    elif etype == 'exit_valid' or etype == 'exit':
                        # 實作長寬比過濾 (Tha_a)
                        avg_aspect = ev.get('avg_aspect', 0.0)
                        if avg_aspect < args.min_aspect:
                            print(f"  [形狀過濾] ID:{tid} 穩定長寬比={avg_aspect:.2f} < {args.min_aspect}")
                            continue
                        
                        # 檢查方向、長度、位移等
                        max_disp = ev.get('max_disp', 0.0)
                        if max_disp < MIN_DISPLACEMENT_PX:
                            print(f"  [靜止略過] ID:{tid} 位移={max_disp:.1f}px")
                            continue

                        seg_count += 1
                        out_p = os.path.join(output_dir, f"{video_base_name}_v{seg_count}.mp4")
                        
                        buffer_frames = int(PAD_SEC * fps)
                        pad_start = max(0, start - buffer_frames)
                        pad_end = min(total_frames - 1, end + buffer_frames)

                        extract_video_segment(video_path, pad_start, pad_end, fps, out_p)
                        print(f"  -> 片段儲存: {out_p} (Aspect: {avg_aspect:.2f})")

                if not ret: break
                frame_idx += 1
            cap.release()
        print("\n所有影片處理完成。")

        if args.classify:
            from core.classify import classify_videos
            print(f"正在自動分類資料夾: {output_dir}")
            classify_videos(output_dir, "COW_dataset")

if __name__ == "__main__":
    main()
