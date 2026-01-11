from abc import ABC, abstractmethod
import numpy as np
from typing import List, Tuple, Dict, Any, Optional

class BaseOCREngine(ABC):
    @abstractmethod
    def initialize(self, use_gpu: bool = True):
        pass

    @abstractmethod
    def extract_text(self, img: np.ndarray) -> List[Dict[str, Any]]:
        """
        Extract text from an image.
        Returns a list of dictionaries with keys:
            - text: str
            - confidence: float
            - position: List[List[int]] (4 points: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]])
        """
        pass

class PaddleOCREngine(BaseOCREngine):
    def __init__(self):
        self.ocr = None

    def initialize(self, use_gpu: bool = True):
        from paddleocr import PaddleOCR
        # show_log=False to reduce noise
        self.ocr = PaddleOCR(use_angle_cls=True, lang='japan', use_gpu=use_gpu, show_log=False)

    def extract_text(self, img: np.ndarray) -> List[Dict[str, Any]]:
        if self.ocr is None:
            raise RuntimeError("OCR engine not initialized")
        
        result = self.ocr.ocr(img)
        return self._normalize_result(result)

    def _normalize_result(self, result):
        if not result or not isinstance(result, list) or len(result) == 0:
            return []

        normalized = []
        
        # PaddleX / Dict format
        if isinstance(result[0], dict) and 'rec_texts' in result[0]:
            data = result[0]
            texts = data.get('rec_texts', [])
            scores = data.get('rec_scores', [])
            polys = data.get('rec_polys', [])
            for text, score, poly in zip(texts, scores, polys):
                box = poly.tolist() if hasattr(poly, 'tolist') else poly
                normalized.append({
                    "text": text,
                    "confidence": float(score),
                    "position": box
                })
        
        # Standard PaddleOCR format
        elif isinstance(result[0], list):
            lines = [line for line in result[0] if line]
            for line in lines:
                box = line[0]
                text, score = line[1]
                normalized.append({
                    "text": text,
                    "confidence": float(score),
                    "position": box
                })
                
        return normalized

class YomitokuEngine(BaseOCREngine):
    def __init__(self):
        self.ocr = None

    def initialize(self, use_gpu: bool = True):
        from yomitoku import OCR
        device = "cuda" if use_gpu else "cpu"
        # visualize=False to avoid window popup or extra processing
        self.ocr = OCR(device=device, visualize=False)

    def extract_text(self, img: np.ndarray) -> List[Dict[str, Any]]:
        if self.ocr is None:
            raise RuntimeError("OCR engine not initialized")
            
        # Yomitoku returns (results, vis_img)
        # results is OCRSchema with .words list
        results, _ = self.ocr(img)
        
        normalized = []
        if hasattr(results, 'words'):
            for word in results.words:
                # word.points is [[x1,y1], [x2,y2]...]
                normalized.append({
                    "text": word.content,
                    "confidence": float(word.rec_score), # Using recognition score
                    "position": word.points
                })
                
        return normalized

def get_ocr_engine(name: str) -> BaseOCREngine:
    if name.lower() == 'paddle':
        return PaddleOCREngine()
    elif name.lower() == 'yomitoku':
        return YomitokuEngine()
    else:
        raise ValueError(f"Unknown OCR engine: {name}")
