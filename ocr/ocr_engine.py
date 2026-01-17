from abc import ABC, abstractmethod
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image
import os
import time

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
        """段落情報を処理してテキスト抽出（フリガナフィルタ付き）"""
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
                print(f"[DEBUG] Skipped (Ruby?): thickness={thickness:.1f} < {threshold:.1f} : {p.contents[:10]}...")
        return normalized

    def _process_words(self, words) -> List[Dict[str, Any]]:
        """単語情報を処理してテキスト抽出（フリガナフィルタ + ソート）"""
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

        # 縦書き/横書き判定
        vertical_count = sum(1 for w in word_info if w['is_vertical'])
        page_is_vertical = vertical_count > len(word_info) / 2
        
        # ソート: 縦書きは右→左、横書きは上→下
        if page_is_vertical:
            word_info.sort(key=lambda w: (-w['center_x'], w['center_y']))
        else:
            word_info.sort(key=lambda w: (w['center_y'], w['center_x']))

        # フリガナフィルタ（厚みベース）
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
                print(f"[DEBUG] Skipped Word (Ruby?): T={info['thickness']:.1f} < {threshold:.1f} : {info['word'].content}")
        return normalized

    def _calculate_thickness(self, box, direction):
        """ボックスの厚み（縦書きならwidth、横書きならheight）を計算"""
        w = box[2] - box[0]
        h = box[3] - box[1]
        return w if direction == 'vertical' else h

    def _convert_words_to_dict(self, words) -> List[Dict[str, Any]]:
        return [{
            "text": word.content,
            "confidence": float(word.rec_score),
            "position": word.points
        } for word in words]

class MangaOCREngine(BaseOCREngine):
    def __init__(self):
        self.detector = None
        self.recognizer = None

    def initialize(self, use_gpu: bool = True):
        # 1. Detection用にYomitoku (PaddleOCR) を初期化
        from yomitoku import OCR
        device = "cuda" if use_gpu else "cpu"
        self.detector = OCR(device=device, visualize=False)
        
        # 2. Recognition用にMangaOCRを初期化
        from manga_ocr import MangaOcr
        # MangaOcrは内部でGPUチェックを行うが、明示的に指定はできない
        self.recognizer = MangaOcr()

    def extract_text(self, img: np.ndarray) -> List[Dict[str, Any]]:
        if self.detector is None or self.recognizer is None:
            raise RuntimeError("MangaOCR engine not initialized")
        
        # 1. 検出 (yomitoku)
        ret = self.detector(img)
        if len(ret) == 3:
            results, _, _ = ret
        else:
            results, _ = ret
            
        ocr_results = []
        
        # results.words (List[Box]) を使用
        if hasattr(results, 'words'):
            words = results.words
            
            # ソート（yomitokuのロジックを流用）
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
                    'is_vertical': direction == 'vertical',
                    'points': pts
                })

            if not word_info:
                return []
                
            # 縦書き/横書き判定
            vertical_count = sum(1 for w in word_info if w['is_vertical'])
            page_is_vertical = vertical_count > len(word_info) / 2
            
            # ソート
            if page_is_vertical:
                word_info.sort(key=lambda w: (-w['center_x'], w['center_y']))
            else:
                word_info.sort(key=lambda w: (w['center_y'], w['center_x']))

            # フリガナフィルタ（厚みベース）
            word_thicknesses = [w['thickness'] for w in word_info]
            if word_thicknesses:
                median_thickness = np.median(word_thicknesses)
                threshold = median_thickness * 0.5
                print(f"[DEBUG] (MangaOCR) Median thickness: {median_thickness}, Threshold: {threshold}")

                # フィルタリング
                filtered_info = []
                for info in word_info:
                    if info['thickness'] > threshold:
                        filtered_info.append(info)
                    else:
                        print(f"[DEBUG] Skipped (Ruby?): T={info['thickness']:.1f} < {threshold:.1f}")

                # 垂直方向のフラグメント結合（文脈確保のため）
                merged_boxes = self._merge_vertical_fragments(filtered_info)

                for box in merged_boxes:
                    # 2. クロップ
                    cropped_pil = self._crop_image(img, box)
                    
                    # 3. 認識 (manga-ocr)
                    try:
                        text = self.recognizer(cropped_pil)
                        
                        ocr_results.append({
                            "text": text,
                            "position": box.tolist(), # Convert numpy array to list
                            "confidence": 1.0 # manga-ocrはスコアを出さないため固定
                        })
                    except Exception as e:
                        print(f"[ERROR] MangaOCR failed for box {box}: {e}")

        return ocr_results

    def _merge_vertical_fragments(self, items: List[Dict]) -> List[np.ndarray]:
        """
        同じ行（垂直方向）にある近接したテキストボックスを結合する。
        manga-ocrは文脈があったほうが精度が高いため、断片化した文字を1つの画像にまとめる。
        """
        if not items:
            return []

        # 1. X座標で大まかに列に分割
        # 縦書きの場合、行はX軸方向に並ぶ。同じ行の文字はX座標がほぼ同じ。
        # まずX中心座標でソート
        sorted_items = sorted(items, key=lambda x: -x['center_x']) # 右から左へ
        
        merged = []
        
        if not sorted_items:
            return []

        current_box_group = [sorted_items[0]]
        
        # 許容するX方向のズレ（行の幅の半分程度）
        # アイテムごとのthicknessがwidth(縦書き時)なので、その平均を使う
        avg_width = np.mean([item['thickness'] for item in sorted_items])
        x_threshold = avg_width * 0.5
        
        # 許容するY方向のギャップ（文字間隔）
        # 大きすぎると次の段落などを巻き込むが、manga-ocrならある程度許容できる
        y_gap_threshold = avg_width * 3.0 

        for i in range(1, len(sorted_items)):
            item = sorted_items[i]
            prev = current_box_group[-1]
            
            # 同じ行か判定 (X座標が近い)
            x_diff = abs(item['center_x'] - prev['center_x'])
            
            if x_diff < x_threshold:
                # 同じ行の可能性がある
                # Y方向の順序チェック（ソート済みではないので、グループ内でYソートが必要だが、
                # ここでは単純に近接チェックを行うため、後でまとめて結合する戦略をとる）
                current_box_group.append(item)
            else:
                # 別の行 -> グループ確定処理へ
                merged.extend(self._process_group_merging(current_box_group, y_gap_threshold))
                current_box_group = [item]
        
        # 最後のグループ
        merged.extend(self._process_group_merging(current_box_group, y_gap_threshold))
        
        return merged

    def _process_group_merging(self, group: List[Dict], y_gap_threshold: float) -> List[np.ndarray]:
        """
        X座標が近いグループ（同じ行の候補）の中で、Y座標順にソートし、
        近接しているものを結合してバウンディングボックスを返す。
        """
        if not group:
            return []
            
        # Y座標順（上から下）にソート
        group.sort(key=lambda x: x['center_y'])
        
        final_boxes = []
        current_merge = [group[0]]
        
        for i in range(1, len(group)):
            item = group[i]
            prev = current_merge[-1]
            
            # Y方向の距離（前の下端 と 今の上端 の差）
            # word.points は [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            # y_maxを取り出す
            prev_y_max = np.max(np.array(prev['points'])[:, 1])
            curr_y_min = np.min(np.array(item['points'])[:, 1])
            
            gap = curr_y_min - prev_y_max
            
            # ギャップが閾値以内なら結合
            # 負の値（オーバーラップ）も結合対象
            if gap < y_gap_threshold:
                current_merge.append(item)
            else:
                # 結合実行
                final_boxes.append(self._merge_points(current_merge))
                current_merge = [item]
                
        # 最後
        final_boxes.append(self._merge_points(current_merge))
        return final_boxes

    def _merge_points(self, items: List[Dict]) -> np.ndarray:
        """複数のアイテムのpointsから包含矩形（4点ポリゴン）を作成"""
        all_points = []
        for item in items:
            all_points.extend(item['points'])
        
        pts = np.array(all_points)
        x_min = np.min(pts[:, 0])
        y_min = np.min(pts[:, 1])
        x_max = np.max(pts[:, 0])
        y_max = np.max(pts[:, 1])
        
        # [x1,y1], [x2,y1], [x2,y2], [x1,y2] の順で矩形作成
        return np.array([
            [x_min, y_min],
            [x_max, y_min],
            [x_max, y_max],
            [x_min, y_max]
        ], dtype=np.float32)

    def _crop_image(self, img: np.ndarray, points: np.ndarray, padding: int = 10) -> Image.Image:
        """ポリゴン座標から画像をクロップしてPIL Imageに変換（パディング付きでハルシネーション抑制）"""
        # バウンディングボックスの最小・最大座標を計算
        x_min = int(np.min(points[:, 0]))
        y_min = int(np.min(points[:, 1]))
        x_max = int(np.max(points[:, 0]))
        y_max = int(np.max(points[:, 1]))
        
        # パディング追加
        h, w = img.shape[:2]
        x_min = max(0, x_min - padding)
        y_min = max(0, y_min - padding)
        x_max = min(w, x_max + padding)
        y_max = min(h, y_max + padding)
        
        # クロップ
        cropped = img[y_min:y_max, x_min:x_max]
        
        # PIL Imageに変換
        # OpenCVはBGR、PILはRGBなので変換が必要
        if len(cropped.shape) == 3 and cropped.shape[2] == 3:
            cropped = cropped[:, :, ::-1] # BGR -> RGB
        
        pil_img = Image.fromarray(cropped)

        # DEBUG: クロップ画像の保存（問題特定用）
        debug_dir = "debug_crops"
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir, exist_ok=True)
        timestamp = str(int(time.time() * 1000))
        pil_img.save(os.path.join(debug_dir, f"crop_{timestamp}.png"))
            
        return pil_img

def get_ocr_engine(name: str) -> BaseOCREngine:
    if name.lower() == 'paddle':
        return PaddleOCREngine()
    elif name.lower() == 'yomitoku':
        return YomitokuEngine()
    elif name.lower() == 'mangaocr':
        return MangaOCREngine()
    else:
        raise ValueError(f"Unknown OCR engine: {name}")
