from pathlib import Path

def fix_yolo_labels(label_dir):
    label_path = Path(label_dir)
    fixed_count = 0
    
    files = list(label_path.glob("*.txt"))
    for label_file in files:
        with open(label_file, "r") as f:
            lines = f.readlines()
        
        new_lines = []
        modified = False
        for line in lines:
            parts = line.strip().split()
            if len(parts) != 5: continue
            
            cls = parts[0]
            coords = [min(1.0, max(0.0, float(x))) for x in parts[1:]]
            
            orig_coords = [float(x) for x in parts[1:]]
            if any(abs(o - n) > 1e-6 for o, n in zip(orig_coords, coords)):
                modified = True
            
            new_lines.append(f"{cls} {' '.join(map(str, coords))}\n")
        
        if modified:
            with open(label_file, "w") as f:
                f.writelines(new_lines)
            fixed_count += 1
            
    print(f"標籤修正完成：共檢查 {len(files)} 檔案，修正 {fixed_count} 個。")
