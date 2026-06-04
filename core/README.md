# Core Module
此目錄包含系統的核心邏輯。
- `video.py`: 處理影片串流、YOLO 追蹤與虛擬圍籬判定。
- `classify.py`: 負責將擷取後的影片分類為彩色 (COLOR_STABLE) 或紅外線 (IR_MODE)。
- `trainer.py`: 封裝 YOLO 模型的訓練與微調邏輯。