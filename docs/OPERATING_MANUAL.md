# 乳牛監測與自動化資料管線 操作手冊 (Operating Manual)

本手冊詳述目前系統的所有可用指令與操作流程，涵蓋從「長時影片擷取」到「特徵自動分類歸檔」的完整資料流。

---

## 1. 環境配置 (Environment Setup)

在執行任何指令前，請確保已載入正確的 Python 執行環境。

```bash
# 若尚未建立環境，請直接執行批次檔自動安裝
setup_conda.bat

# 手動啟用 conda 環境
conda activate cow_env
```

> **首次執行 `fence` 指令注意事項**
> Ultralytics 的多目標追蹤功能依賴 `lap` 套件（Linear Assignment Problem 求解器）。
> 若環境中尚未安裝，程式會在第一次執行時自動下載安裝，並顯示以下警告：
> ```
> WARNING requirements: Restart runtime or rerun command for updates to take effect
> ```
> 此時**直接重新執行同一指令**即可，`lap` 已安裝完成，不會再觸發下載。
> 另外，PyTorch 在同一台機器上首次執行時需要 5–15 秒冷啟動（編譯 kernel cache），
> 屬於正常現象，讓程式自行跑完即可。

---

## 2. 核心管線一：虛擬圍籬與自動擷取 (Virtual Fence)

**使用情境**：擁有一批長時間原始監控影片，需系統自動過濾無效空白時段，將「乳牛通過感應區」的動作精準剪輯為短影片。

### 常用指令

**A. 處理單一影片**
```bash
python main.py fence --input "your_video.mp4" --model "weights/best.pt" --class_id 19
```

**B. 批次處理整個資料夾**（系統會自動遞迴掃描底下的所有 mp4/avi/mov 檔案）
```bash
python main.py fence --input "your_video_folder/" --model "weights/best.pt" --class_id 19
```

**C. 擷取後自動分類**（New! 處理完畢後自動執行影像光照特徵分類）
```bash
python main.py fence --input "your_video_folder/" --model "weights/best.pt" --classify --show
```

### 關鍵參數

| 參數 | 說明 |
|---|---|
| `--input` | 單一檔案路徑或資料夾路徑 |
| `--model` | YOLO 權重檔路徑（`weights/yolo11n.pt` 或微調後的 `.pt`） |
| `--class_id` | **重要**。官方模型須加 `--class_id 19` (牛)；自訓練模型依其索引（通常為 0） |
| `--ioa` | **New!** IoA 判定門檻（預設 0.5）。數值越高，牛隻進入區域的面積比例需越多才觸發 |
| `--classify` | **New!** 擷取後自動執行影像自動分類歸檔 |

### 輸出位置

擷取成功的影片儲存於 **`Test/`** 資料夾，供後續自動分類器直接讀取。  
檔名格式：`{原始影片名稱}_v{seg_count}.mp4`

---

### 虛擬圍籬運作機制（詳述）

#### 機制一：多目標個體追蹤（per-track 狀態機）

**解決方式**：改用 `model.track(persist=True)` 取得唯一 `track_id`。`VirtualFence` 內部為每個 `track_id` 獨立維護 `{start_frame, aspects, max_disp, lost_frames}` 等狀態。

#### 機制二：IoA 比例空間判定 (New!)

**問題**：舊版以「中心點」判定。當牛隻邊緣進入區域、或模型預測框出現微小震盪時，中心點可能在邊界反覆跳動，造成片段被切碎或重複觸發。

**解決方式**：改用 **IoA (Intersection over Area)** 比例。
- 系統計算「牛隻邊界框」與「偵測區域 (ROI)」的重疊面積。
- 當 **重疊面積 / 牛隻面積 >= `--ioa` 門檻** 時，判定為有效在場。
- 預設 0.5 代表牛隻至少有一半進入區域才開始記錄，大幅提升邊緣偵測的穩定性。

#### 機制三：長時間停留自動分段 (Segment Splitting)

**解決方式**：引入 `MAX_SEGMENT_SEC = 20`。當同一個體在 ROI 內停留達到此閾值時，立即發出 `segment_split` 並儲存當前片段，隨後重置計時基準。

#### 機制四：靜止過濾 (Displacement Filter)

**解決方式**：追蹤全段的最大位移 `max_disp`。在輸出前判斷：
```
max_disp < MIN_DISPLACEMENT_PX (100px) → [靜止略過]，不儲存
```

---

#### 過濾器執行順序總覽

| 順序 | 條件 | 日誌標記 | 結果 |
|---|---|---|---|
| 1 | 長寬比穩定性 (P75) < `--min_aspect` | `[形狀過濾]` | 丟棄 |
| 2 | 最大位移 < 100px | `[靜止略過]` | 丟棄 |
| 通過 | 全部條件滿足 | `-> 片段儲存` | 存入 `Test/` |

### 調整參數位置（`main.py`）

```python
MIN_DURATION_SEC   = 3.0  # 最短停留時間（秒）
MAX_SEGMENT_SEC    = 20.0 # 最長單段時間（秒），超過自動分割
MIN_DISPLACEMENT_PX = 100.0 # 最小有效位移（像素）
patience_frames    = 90   # 漏偵測容忍畫格數（約 3 秒 @ 30fps）
PAD_SEC            = 3.0  # 片段前後緩衝時間（秒）
```

---

## 3. 核心管線二：物理特徵自動分類 (Feature Classification)

**使用情境**：`fence` 指令已執行完畢，`Test/` 資料夾內累積了短影片，需系統依據影像光照特徵自動區分「日間彩色模式 / 夜間紅外線模式」並完成歸檔。

### 常用指令

```bash
python main.py data --classify
```

### 運作邏輯與輸出

- **讀取機制**：以遞迴方式（`rglob`）掃描 `Test/` 資料夾下所有 `.mp4` 檔案，包含任意深度的子資料夾。
- **分類機制**：抽取影片中間畫格，同時計算兩項特徵：
  - `chroma_median`：R/G/B 三通道兩兩差值的中位數（IR 影像三通道幾乎相等，值接近 0）
  - `sat_p75`：HSV 飽和度的第 75 百分位數（IR 影像飽和度極低）
  - 判定條件：`chroma_median < 8.0 AND sat_p75 < 35.0` → IR 模式，否則 Color 模式
- **輸出位置（實體搬移）**：分類完成後影片從 `Test/` **移走**，存入：
  - 紅外線/夜視片段：`COW_dataset/IR_MODE/YYMMDD/`
  - 一般彩色片段：`COW_dataset/COLOR_STABLE/YYMMDD/`

> 分類器使用 `shutil.move`，執行後 `Test/` 內的原始檔案會消失。
> 若需保留原始片段，請將 `classify_test.py` 第 98 行的 `shutil.move` 改為 `shutil.copy2`。

---

## 4. 完整資料管線流程

```
原始監控影片（長時）
        ↓
python main.py fence --input "..." --model "..." --class_id 19
        ↓  [過濾：折返 / 過短 / 靜止]
Test/
  ├── 20260420_010847_t1_v1.mp4   ← 個體 1，第 1 段
  ├── 20260420_010847_t1_v2.mp4   ← 個體 1，第 2 段（分割）
  └── 20260420_010847_t2_v1.mp4   ← 個體 2，第 1 段
        ↓
python main.py data --classify (或在 fence 指令直接加上 --classify)
        ↓  [chroma_median + sat_p75 雙判據]
COW_dataset/
  ├── IR_MODE/260420/*.mp4
  └── COLOR_STABLE/260420/*.mp4
```

---

## 5. 輔助管線：資料集預處理 (Dataset Formatting)

**使用情境**：將人工標記（Label Studio）匯出的資料轉換為 YOLO 可用的標準格式以供模型微調。

### 常用指令

**A. 標籤座標修正**  
若標記工具輸出的 Bounding Box 出現超界（> 1.0 或 < 0.0）等格式錯誤，可使用此指令自動修復：
```bash
python main.py data --fix
```
*(系統將針對 `my_dataset/labels/` 內的 `.txt` 進行校正)*

**B. 資料集自動分割**  
將清洗完畢的資料集，以 80%（訓練集）與 20%（驗證集）的比例隨機切分，並建立 YOLO 規範的目錄結構：
```bash
python main.py data --prepare
```
