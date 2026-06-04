import shutil
import random
from pathlib import Path

def prepare_yolo_dataset(base_dir="my_dataset", output_dir="datasets/cow", split_ratio=0.8):
    base_path = Path(base_dir)
    image_dirs = [base_path / "images" / d for d in ["MORNING", "NIGHT", "WEIGHT"]]
    label_dir = base_path / "labels"

    out_path = Path(output_dir)
    for split in ["train", "val"]:
        (out_path / split / "images").mkdir(parents=True, exist_ok=True)
        (out_path / split / "labels").mkdir(parents=True, exist_ok=True)

    data_pairs = []
    for img_dir in image_dirs:
        for img_path in img_dir.glob("*.jpg"):
            label_path = label_dir / (img_path.stem + ".txt")
            if label_path.exists():
                data_pairs.append((img_path, label_path))

    random.seed(42)
    random.shuffle(data_pairs)
    idx = int(len(data_pairs) * split_ratio)
    
    _copy(data_pairs[:idx], out_path / "train")
    _copy(data_pairs[idx:], out_path / "val")
    print(f"資料集準備完成：訓練 {idx} 張, 驗證 {len(data_pairs)-idx} 張")

def _copy(data_list, target_path):
    for img, lbl in data_list:
        shutil.copy(img, target_path / "images" / img.name)
        shutil.copy(lbl, target_path / "labels" / lbl.name)
