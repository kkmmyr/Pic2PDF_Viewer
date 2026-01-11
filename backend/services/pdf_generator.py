import os
import img2pdf
import zipfile
import io
import shutil
from natsort import natsorted
from PIL import Image

def generate_thumbnail(image_data_or_path, output_path):
    try:
        if isinstance(image_data_or_path, bytes):
            img = Image.open(io.BytesIO(image_data_or_path))
        else:
            img = Image.open(image_data_or_path)
            
        # Resize to height 500px, keeping aspect ratio
        base_height = 500
        h_percent = (base_height / float(img.size[1]))
        w_size = int((float(img.size[0]) * float(h_percent)))
        img = img.resize((w_size, base_height), Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary (e.g. for PNG/WebP with transparency)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        img.save(output_path, "JPEG")
        print(f"Generated thumbnail: {output_path}")
    except Exception as e:
        print(f"Failed to generate thumbnail {output_path}: {e}")

class PdfGenerator:
    def __init__(self, output_dir: str, thumbnail_dir: str, images_dir: str, complete_dir: str, progress_callback=None):
        self.output_dir = output_dir
        self.thumbnail_dir = thumbnail_dir
        self.images_dir = images_dir
        self.complete_dir = complete_dir
        self.progress_callback = progress_callback
        self.generated_files = []
        self.moves = [] # List of (src, dst, is_dir)

    def process_zip(self, root: str, zip_filename: str):
        item_name = os.path.splitext(zip_filename)[0]
        zip_path = os.path.join(root, zip_filename)
        
        if not os.path.exists(zip_path):
            return

        if self.progress_callback:
            self.progress_callback(item_name)
            
        pdf_filename = f"{item_name}.pdf"
        output_path = os.path.join(self.output_dir, pdf_filename)
        
        # Thumbnail path
        thumb_filename = f"{item_name}.jpg"
        thumb_path = os.path.join(self.thumbnail_dir, thumb_filename)

        # Images path
        target_images_dir = os.path.join(self.images_dir, item_name)
        os.makedirs(target_images_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                file_list = zf.namelist()
                webp_in_zip = [f for f in file_list if f.lower().endswith('.webp')]
                
                if not webp_in_zip:
                    return

                webp_in_zip = natsorted(webp_in_zip)
                image_data_list = []
                
                # Read all images for PDF
                for i, image_name in enumerate(webp_in_zip):
                    with zf.open(image_name) as image_file:
                        data = image_file.read()
                        image_data_list.append(data)
                        
                        # Generate thumbnail from the first image
                        if i == 0:
                            generate_thumbnail(data, thumb_path)
                        
                        # Save image to images_dir
                        image_out_path = os.path.join(target_images_dir, image_name)
                        os.makedirs(os.path.dirname(image_out_path), exist_ok=True)
                        with open(image_out_path, "wb") as img_f:
                            img_f.write(data)
                
                self._create_pdf_file(image_data_list, output_path)
                
                self.generated_files.append(pdf_filename)
                print(f"Generated from ZIP: {output_path}")
                
                # Schedule move
                target_path = os.path.join(self.complete_dir, zip_filename)
                self.moves.append((zip_path, target_path, False))

        except Exception as e:
            print(f"Failed to generate PDF for ZIP {zip_path}: {e}")

    def process_directory(self, root: str, webp_files: list, is_root: bool):
        folder_name = os.path.basename(root)
        
        if self.progress_callback:
            self.progress_callback(folder_name)

        webp_files = natsorted(webp_files)
        image_paths = [os.path.join(root, f) for f in webp_files]
        pdf_filename = f"{folder_name}.pdf"
        output_path = os.path.join(self.output_dir, pdf_filename)
        
        # Thumbnail path
        thumb_filename = f"{folder_name}.jpg"
        thumb_path = os.path.join(self.thumbnail_dir, thumb_filename)

        # Images path
        target_images_dir = os.path.join(self.images_dir, folder_name)
        os.makedirs(target_images_dir, exist_ok=True)
        
        try:
            # Generate thumbnail from first image
            if image_paths:
                generate_thumbnail(image_paths[0], thumb_path)
            
            # Copy images to images_dir
            for img_path, img_name in zip(image_paths, webp_files):
                dst_path = os.path.join(target_images_dir, img_name)
                shutil.copy2(img_path, dst_path)

            self._create_pdf_file(image_paths, output_path)
            
            self.generated_files.append(pdf_filename)
            print(f"Generated from Folder: {output_path}")
            
            # Schedule move
            if not is_root:
                target_path = os.path.join(self.complete_dir, folder_name)
                self.moves.append((root, target_path, True)) # True = directory
            else:
                # Move individual files
                for f in webp_files:
                    src_file = os.path.join(root, f)
                    dst_file = os.path.join(self.complete_dir, f)
                    self.moves.append((src_file, dst_file, False))
            
        except Exception as e:
            print(f"Failed to generate PDF for folder {root}: {e}")

    def _create_pdf_file(self, images, output_path):
        """Helper to create PDF from image data list or path list"""
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert(images))

    def execute_moves(self):
        for src, dst, is_dir in self.moves:
            try:
                if os.path.exists(dst):
                    # Remove existing target to allow move (overwrite)
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    else:
                        os.remove(dst)
                    print(f"Removed existing target: {dst}")
                
                shutil.move(src, dst)
                print(f"Moved {'folder' if is_dir else 'file'} to: {dst}")
            except Exception as e:
                print(f"Failed to move {src} to {dst}: {e}")

    def run(self, source_dir: str):
        cleanups = []

        for root, dirs, files in os.walk(source_dir, topdown=False):
            # 1. Process ZIP files
            zip_files = [f for f in files if f.lower().endswith('.zip')]
            for zip_filename in zip_files:
                self.process_zip(root, zip_filename)

            # 2. Process Directory (WebP files)
            webp_files = [f for f in files if f.lower().endswith('.webp')]
            if webp_files:
                is_root = (root == source_dir)
                self.process_directory(root, webp_files, is_root)

            # Add to cleanup candidates (if not source_dir)
            if root != source_dir:
                cleanups.append(root)

        # Execute Moves
        self.execute_moves()

        # Execute Cleanups (remove empty directories)
        for folder in cleanups:
            if os.path.exists(folder):
                try:
                    if not os.listdir(folder):
                        os.rmdir(folder)
                        print(f"Removed empty directory: {folder}")
                except Exception as e:
                    print(f"Failed to remove directory {folder}: {e}")
        
        return self.generated_files

def scan_and_generate(source_dir: str, output_dir: str, thumbnail_dir: str, images_dir: str, complete_dir: str, progress_callback=None):
    """
    Wrapper function for backward compatibility.
    Recursively scans source_dir for directories and ZIP files containing WebP images,
    converts them to PDF, saves them to output_dir, and moves source to complete_dir.
    """
    generator = PdfGenerator(output_dir, thumbnail_dir, images_dir, complete_dir, progress_callback)
    return generator.run(source_dir)
