# CowDetect - 乳牛監測與自動化資料管線

基於 YOLO 與 ByteTrack 的智慧乳牛監測系統，專注於長時間監控影片的自動化處理。系統能自動辨識乳牛、建立虛擬圍籬、濾除無效片段，並依據影像特徵自動進行日夜間（IR/Color）分類與歸檔。

## ✨ 核心功能 (Features)

1. **虛擬圍籬與自動擷取 (Virtual Fence)**
   - 整合  YOLO11 與 ByteTrack 進行多目標追蹤。
   - 使用 **IoA (Intersection over Area)** 比例判斷牛隻是否進入感應區，解決邊緣震盪問題。
   - 內建過濾機制：濾除長寬比異常、靜止不動或停留時間過短的無效片段。
   - 長時間停留自動分割（預設停留超過 20 秒自動切分新片段）。

2. **影像特徵自動分類 (Auto Classification)**
   - 自動提取擷取片段的影像特徵。
   - 透過色度中位數 (Chroma Median) 與飽和度 (Saturation P75) 雙重指標，自動區分「日間彩色」與「夜間紅外線 (IR)」模式。
   - 自動將影片搬移並歸檔至對應資料夾，大幅節省人工分類時間。

3. **資料集預處理輔助 (Dataset Tools)**
   - 支援將人工標記工具輸出的座標進行邊界修復（Clamp）。
   - 自動依比例（預設 80/20）分割訓練集與驗證集，並建立符合 YOLO 訓練規範的目錄結構。

## 🚀 快速開始 (Quick Start)

### 1. 環境安裝

若您尚未建立執行環境，請直接執行根目錄下的批次檔進行自動安裝：
```bash
setup_conda.bat
```
或手動啟用環境：
```bash
conda activate cow_env
```

### 2. 執行影片擷取與自動分類

只需一行指令，即可完成「虛擬圍籬分析」、「無效片段過濾」、「短影片擷取」與「日夜間特徵自動分類歸檔」的完整管線：

```bash
python main.py fence --input "your_video.mp4" --model "weights/best.pt" --classify
```
> **提示**：若想在執行時顯示即時視覺化畫面，可加上 `--show` 參數。

## 📚 說明文件 (Documentation)

更詳細的系統設計、演算法原理與進階操作說明，請參閱 `docs/` 目錄下的文件：

- [操作手冊 (OPERATING_MANUAL)](docs/OPERATING_MANUAL.md) - 詳細的指令參數與管線說明。
- [系統演算法設計 (ALGORITHM)](docs/ALGORITHM.md) - 虛擬圍籬狀態機與光照分類演算法解析。
- [系統架構說明 (README_System)](docs/README_System.md) - 模組依賴與架構圖。

## ⚙️ 系統需求

- **作業系統**：Windows / Linux
- **Python**：3.10+
- **核心套件**：`ultralytics`, `opencv-python`, `pytorch` (支援 CUDA 或 CPU)
