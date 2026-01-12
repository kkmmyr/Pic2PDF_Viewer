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
        ret = self.ocr(img)
        if len(ret) == 3:
            results, _, _ = ret
        else:
            results, _ = ret
        
        # Use paragraphs if available for better reading order
        if hasattr(results, 'paragraphs') and len(results.paragraphs) > 0:
            return self._process_paragraphs(results.paragraphs)
        elif hasattr(results, 'words'):
            return self._process_words(results.words)
        
        return []

    def _process_paragraphs(self, paragraphs) -> List[Dict[str, Any]]:
        thicknesses = []
        for p in paragraphs:
            thicknesses.append(self._calculate_thickness(p.box, p.direction))
            
        if not thicknesses:
            print("[DEBUG] No thicknesses calculated.")
            return []

        median_thickness = np.median(thicknesses)
        threshold = median_thickness * 0.5
        print(f"[DEBUG] Median thickness: {median_thickness}, Threshold: {threshold}")
        
        normalized = []
        for p in paragraphs:
            thickness = self._calculate_thickness(p.box, p.direction)
            if thickness > threshold:
                normalized.append({
                    "text": p.contents,
                    "confidence": 1.0, 
                    "position": p.box
                })
            else:
                print(f"[DEBUG] Skipped (Ruby?): thickness={thickness} < {threshold} : {p.contents[:10]}...")
        return normalized

    def _process_words(self, words) -> List[Dict[str, Any]]:
        word_info = []
        for word in words:
            pts = np.array(word.points)
            x_min, y_min = np.min(pts, axis=0)
            x_max, y_max = np.max(pts, axis=0)
            w = x_max - x_min
            h = y_max - y_min
            
            direction = getattr(word, 'direction', 'vertical')
            thickness = w if direction == 'vertical' else h
            
            center_x = (x_min + x_max) / 2
            center_y = (y_min + y_max) / 2
            
            word_info.append({
                'word': word,
                'thickness': thickness,
                'center_x': center_x,
                'center_y': center_y,
                'is_vertical': direction == 'vertical'
            })
        
        if not word_info:
            return []

        # Sort words
        vertical_count = sum(1 for w in word_info if w['is_vertical'])
        page_is_vertical = vertical_count > len(word_info) / 2
        
        if page_is_vertical:
            # Sort by X desc (-x), then Y asc (y)
            word_info.sort(key=lambda w: (-w['center_x'], w['center_y']))
        else:
            # Sort by Y asc (y), then X asc (x)
            word_info.sort(key=lambda w: (w['center_y'], w['center_x']))

        # Filter by thickness
        word_thicknesses = [w['thickness'] for w in word_info]
        if not word_thicknesses:
            return self._convert_words_to_dict([w['word'] for w in word_info])

        median_thickness = np.median(word_thicknesses)
        threshold = median_thickness * 0.5
        print(f"[DEBUG] (Words) Median thickness: {median_thickness}, Threshold: {threshold}")
        
        normalized = []
        for info in word_info:
            if info['thickness'] > threshold:
                word = info['word']
                normalized.append({
                    "text": word.content,
                    "confidence": float(word.rec_score),
                    "position": word.points
                })
            else:
                print(f"[DEBUG] Skipped Word (Ruby?): T={info['thickness']} < {threshold} : {info['word'].content}")
        return normalized

    def _calculate_thickness(self, box, direction):
        w = box[2] - box[0]
        h = box[3] - box[1]
        return w if direction == 'vertical' else h

    def _convert_words_to_dict(self, words) -> List[Dict[str, Any]]:
        return [{
            "text": word.content,
            "confidence": float(word.rec_score),
            "position": word.points
        } for word in words]

def get_ocr_engine(name: str) -> BaseOCREngine:
    if name.lower() == 'paddle':
        return PaddleOCREngine()
    elif name.lower() == 'yomitoku':
        return YomitokuEngine()
    else:
        raise ValueError(f"Unknown OCR engine: {name}")
