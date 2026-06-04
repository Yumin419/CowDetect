import os
import re
from pathlib import Path

def rename_existing_clips(target_dir):
    """
    移除檔案名稱中的 _t{ID} 部分，例如 20260420_000847_t1_v2.mp4 -> 20260420_000847_v2.mp4
    """
    target_path = Path(target_dir)
    if not target_path.exists():
        print(f"錯誤: 資料夾 {target_dir} 不存在")
        return

    print(f"開始掃描資料夾: {target_dir}")
    count = 0
    
    # 遞迴尋找所有 mp4
    for file_path in target_path.rglob("*.mp4"):
        old_name = file_path.name
        # 使用正規表達式匹配 _t 加上一個或多個數字的部分
        new_name = re.sub(r"_t\d+", "", old_name)
        
        if new_name != old_name:
            new_file_path = file_path.parent / new_name
            
            # 處理可能發生的檔案名稱衝突 (例如 t1_v1 跟 t2_v1 都變成 v1)
            # 如果新檔名已存在，則在 v 號前面加上自增索引
            if new_file_path.exists():
                stem = new_file_path.stem
                ext = new_file_path.suffix
                i = 1
                while True:
                    fix_name = f"{stem}_{i}{ext}"
                    new_file_path = file_path.parent / fix_name
                    if not new_file_path.exists():
                        break
                    i += 1
            
            try:
                os.rename(str(file_path), str(new_file_path))
                print(f"  [更名] {old_name} -> {new_file_path.name}")
                count += 1
            except Exception as e:
                print(f"  [錯誤] 無法更名 {old_name}: {e}")

    print(f"\n批次更名完成，共修改 {count} 個檔案。")

if __name__ == "__main__":
    # 分別對 Test (待分類) 與 COW_dataset (已分類) 進行更名
    rename_existing_clips("Test")
    rename_existing_clips("COW_dataset")
