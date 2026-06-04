import os
from ultralytics import YOLO

class CowTrainer:
    def __init__(self, data_yaml='configs/cow.yaml'):
        self.data_yaml = data_yaml

    def train_base(self, model_type="weights/yolo11n.pt", epochs=150):
        model = YOLO(model_type)
        return model.train(
            data=self.data_yaml,
            epochs=epochs,
            patience=30,
            imgsz=640,
            project="runs/detect",
            name="yolo11_base",
            lr0=0.001,
            degrees=15.0,
            scale=0.7,
            mosaic=1.0,
            fliplr=0.5
        )

    def finetune(self, weights_path, epochs=100):
        if not os.path.exists(weights_path):
            raise FileNotFoundError(f"找不到微調權重：{weights_path}")
        
        model = YOLO(weights_path)
        return model.train(
            data=self.data_yaml,
            epochs=epochs,
            freeze=10,
            lr0=0.0001,
            cos_lr=True,
            mosaic=0.5,
            mixup=0.1,
            patience=20,
            project='runs/detect',
            name='finetune_cow'
        )
