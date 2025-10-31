import os
import cv2
import pyodbc
import numpy as np
import base64
import threading
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from rapidocr_onnxruntime import RapidOCR
from ultralytics import YOLO

# --- KONFIGURASI ---

# Define SQL Server database connection string.
SQL_SERVER_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=192.9.18.1;"
    "DATABASE=JSTPPSDB;"
    "UID=gapura;"
    "PWD=gapura;"
)

# List of class names that are logos and should be verified by presence, not OCR content.
LOGO_CLASSES = [
    'PML_JISFlag', 'PML_ULMark', 'PML_CU', 'PartBOM_URMark',
    'PartBOM_LogoSA', 'PartBOM_FactoryCode'
]

# --- KUMPULAN QUERY SQL ---
QUERY_INSIDE_LABEL = """
SELECT
    a.Partbom_Partcode AS Partcode, c.PML_CustomerSubPartName AS PartName,
    CASE WHEN c.PML_PartNamePrinted IS NULL OR c.PML_PartNamePrinted = '' THEN b.PartBOM_PartName ELSE c.PML_PartNamePrinted END AS CatNo,
    CAST(b.PartBOM_BoxQty AS INT) AS BoxQty,
    d.R_Type AS RType, b.PartBOM_CompanyName AS CompanyName,
    b.PartBOM_RemarkOnProduct AS CountryMfg, b.PartBOM_FactoryCode AS FactoryCode, b.PartBOM_Voltage AS Voltage,
    b.PartBOM_Current AS CurrentRating, b.PartBOM_Applicable AS Applicable, b.PartBOM_UseInCrimp AS UseInCrimp,
    b.PartBOM_StripLength AS StripLength, c.PML_JISFlag AS JISFlag,
    CASE WHEN c.PML_JISFlag = 1 AND b.PartBOM_CityName = 'JAKARTA' THEN 'PT. J.S.T. INDONESIA JAKARTA PLANT' ELSE '' END AS CompanyPlant,
    b.PartBOM_WireSize AS WireSize, b.PartBOM_ToolDies1 AS ToolDies1, b.PartBOM_ToolDies2 AS ToolDies2,
    b.PartBOM_ToolDies3 AS ToolDies3, b.PartBOM_ToolDies4 AS ToolDies4, b.PartBOM_TrayRemark AS TrayRemark,
    c.PML_ULMark AS ULMark, c.PML_CU AS CUMark, b.PartBOM_URMark AS URMark,
    b.PartBOM_RemarkType AS RemarkType, b.partBOM_Remark AS Remark, b.PartBOM_LogoSA AS CSAMark,
    b.PartBOM_CSARemark AS CSARemark, b.PartBOM_Color AS Color, b.PartBOM_WireStripLen AS WireStripLength,
    CASE WHEN c.PML_ULMark = 0 OR c.PML_ULMark IS NULL THEN '' ELSE b.PartBOM_ULType END AS ULType,
    CASE WHEN c.PML_ULMark = 0 OR c.PML_ULMark IS NULL THEN '' ELSE e.MUL_PrintingWith END AS PrintingWith
FROM VW_GroupCode AS a
INNER JOIN M_PartBOM AS b WITH (NOLOCK) ON b.PartBOM_PartCode = a.Partbom_Partcode
INNER JOIN Tb_MST_PartMasterLabel AS c WITH (NOLOCK) ON c.PML_Partcode = a.Partbom_Partcode
INNER JOIN M_RoHSType AS d WITH (NOLOCK) ON d.R_Code = b.Partbom_Leadfreestatus
LEFT JOIN M_ULType AS e WITH (NOLOCK) ON e.MUL_Type = b.PartBOM_ULType
WHERE a.Partbom_Partcode = ?
"""

QUERY_OUTSIDE_LABEL = """
SELECT
    a.Partbom_Partcode AS Partcode, c.PML_CustomerSubPartName AS PartName,
    CASE WHEN c.PML_PartNamePrinted IS NULL OR c.PML_PartNamePrinted = '' THEN b.PartBOM_PartName ELSE c.PML_PartNamePrinted END AS CatNo,
    CAST(b.PartBOM_BagQty AS INT) AS BoxQty,
    d.R_Type AS RType, b.PartBOM_CompanyName AS CompanyName,
    b.PartBOM_RemarkOnProduct AS CountryMfg, b.PartBOM_FactoryCode AS FactoryCode, c.PML_JISFlag AS JISFlag,
    CASE WHEN c.PML_JISFlag = 1 AND b.PartBOM_CityName = 'JAKARTA' THEN 'PT. J.S.T. INDONESIA JAKARTA PLANT' ELSE '' END AS CompanyPlant
FROM VW_GroupCode AS a
INNER JOIN M_PartBOM AS b WITH (NOLOCK) ON b.PartBOM_PartCode = a.Partbom_Partcode
INNER JOIN Tb_MST_PartMasterLabel AS c WITH (NOLOCK) ON c.PML_Partcode = a.Partbom_Partcode
INNER JOIN M_RoHSType AS d WITH (NOLOCK) ON d.R_Code = b.Partbom_Leadfreestatus
WHERE a.Partbom_Partcode = ?
"""

# --- Inisialisasi & Konfigurasi Path ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "best.pt")
OCR_ENGINE = RapidOCR()

SQL_ALIAS_TO_YOLO_CLASS = {
    'Partcode': 'Partbom_Partcode', 'PartName': 'PML_CustomerSubPartName', 'CatNo': 'CatNo',
    'BoxQty': 'PartBOM_BoxQty', 'RType': 'R_Type', 'CompanyName': 'PartBOM_CompanyName',
    'CountryMfg': 'PartBOM_RemarkOnProduct', 'FactoryCode': 'PartBOM_FactoryCode',
    'Voltage': 'PartBOM_Voltage', 'CurrentRating': 'PartBOM_Current', 'Applicable': 'PartBOM_Applicable',
    'UseInCrimp': 'PartBOM_UseInCrimp', 'StripLength': 'PartBOM_StripLength', 'JISFlag': 'PML_JISFlag',
    'CompanyPlant': 'CompanyPlant', 'WireSize': 'PartBOM_WireSize', 'ToolDies1': 'PartBOM_ToolDies1',
    'ToolDies2': 'PartBOM_ToolDies2', 'ToolDies3': 'PartBOM_ToolDies3', 'ToolDies4': 'PartBOM_ToolDies4',
    'TrayRemark': 'PartBOM_TrayRemark', 'ULMark': 'PML_ULMark', 'ULType': 'PartBOM_ULType',
    'PrintingWith': 'MUL_PrintingWith', 'CUMark': 'PML_CU', 'URMark': 'PartBOM_URMark',
    'RemarkType': 'PartBOM_RemarkType', 'Remark': 'partBOM_Remark', 'CSAMark': 'PartBOM_LogoSA',
    'CSARemark': 'PartBOM_CSARemark', 'Color': 'PartBOM_Color', 'WireStripLength': 'PartBOM_WireStripLen'
}

# --- FUNGSI HELPER ---
def clean_text_for_comparison(text: str) -> str:
    """Clean and standardize text for comparison by removing spaces and making it lowercase."""
    if text is None: return ""
    # Added full-width parentheses and other special chars
    return (
        str(text)
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace(".", "")
        .replace(",", "")
        .replace("（", "")
        .replace("）", "")
        .replace("(", "")
        .replace(")", "")
        .replace(":", "")
        .replace("/", "")
    )

def get_box_center(box_coords):
    x1, y1, x2, y2 = map(int, box_coords)
    return (x1 + x2) // 2, (y1 + y2) // 2

def get_distance(p1, p2):
    """Calculate Euclidean distance between two points."""
    return ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5

def is_point_inside_box(point, box_coords):
    px, py = point
    x1, y1, x2, y2 = map(int, box_coords)
    return x1 <= px <= x2 and y1 <= py <= y2


# --- LOGIKA INTI ---

# Major rewrite of the verification logic for detailed comparison output.
def verify_label_completeness(detected_objects, sql_query):
    """Verify detected objects and return a structured comparison result."""
    partcode_data = next((item for item in detected_objects if item['class_name'].lower() == 'partbom_partcode'), None)
    if not partcode_data or not partcode_data.get('text'):
        return 'DEFECT', [], [{'item': 'Partcode', 'reason': 'Missing', 'db_value': 'N/A', 'ocr_value': 'Not Detected'}]

    partcode_value = str(partcode_data['text']).strip().lstrip('0')
    if not partcode_value:
        return 'DEFECT', [], [{'item': 'Partcode', 'reason': 'Invalid', 'db_value': 'N/A', 'ocr_value': partcode_data.get('text')}]

    conn = None
    try:
        conn = pyodbc.connect(SQL_SERVER_CONN_STR)
        cur = conn.cursor()
        cur.execute(sql_query, partcode_value)
        template_row = cur.fetchone()

        if not template_row:
            return 'DEFECT', [], [{'item': 'Partcode', 'reason': 'Not Found in DB', 'db_value': 'N/A', 'ocr_value': partcode_data.get('text')}]

        colnames = [desc[0] for desc in cur.description]
        template_dict = dict(zip(colnames, template_row))

        # Create a lookup map for detected objects for easier access
        detected_data_map = {item['class_name'].lower(): item.get('text', '') for item in detected_objects}

        matched_results = []
        defect_results = []

        # Iterate through all possible fields based on the master mapping
        for sql_alias, yolo_class in SQL_ALIAS_TO_YOLO_CLASS.items():
            if sql_alias not in template_dict:
                continue # Skip fields not present in the current query (e.g., inside vs outside)

            db_value = template_dict.get(sql_alias)
            ocr_value = detected_data_map.get(yolo_class.lower()) 

            is_required = db_value is not None and str(db_value).strip() not in ['0', '']
            is_detected = ocr_value is not None

            if is_required:
                if not is_detected:
                    defect_results.append({
                        'item': yolo_class, 'reason': 'Missing',
                        'db_value': str(db_value), 'ocr_value': 'Not Detected'
                    })
                else: 
                    db_clean = clean_text_for_comparison(db_value)
                    ocr_clean = clean_text_for_comparison(ocr_value)

                    if yolo_class == 'Partbom_Partcode':
                        db_clean = db_clean.lstrip('0')
                        ocr_clean = ocr_clean.lstrip('0')
                        
                    is_match = (yolo_class in LOGO_CLASSES) or (db_clean == ocr_clean)
                   
                    if is_match:
                        matched_results.append({
                            'item': yolo_class, 'db_value': str(db_value), 'ocr_value': ocr_value
                        })
                    else:
                        defect_results.append({
                            'item': yolo_class, 'reason': 'Mismatch',
                            'db_value': str(db_value), 'ocr_value': ocr_value
                        })
       
        status = 'DEFECT' if defect_results else 'OK'
        return status, matched_results, defect_results

    except pyodbc.Error as error:
        return 'ERROR', [], [{'item': 'Database', 'reason': 'Connection Error', 'db_value': str(error), 'ocr_value': 'N/A'}]
    except Exception as e:
        return 'ERROR', [], [{'item': 'Processing', 'reason': 'Exception', 'db_value': str(e), 'ocr_value': 'N/A'}]
    finally:
        if conn:
            conn.close()

#
# --- FUNGSI UTAMA ---
#
def run_detection_and_verification(image: np.ndarray, yolo_model: YOLO, label_type: str):
    """
    Run detection and verification using the user's proximity analysis logic.
    """
    output_image = image.copy()
    
    # Jalankan YOLO pada gambar yang sudah di-crop
    yolo_results = yolo_model(image, verbose=False)[0]
    class_names = yolo_results.names
   
    # Kumpulkan semua box hasil deteksi YOLO
    all_yolo_boxes = []
    for box in yolo_results.boxes:
        coords = box.xyxy[0].tolist()
        class_id = int(box.cls[0].item())
        class_name = class_names.get(class_id, "Unknown")
        
        # Abaikan 'inside'/'outside' jika terdeteksi lagi di dalam crop
        if class_name.lower() in ['inside', 'outside']:
            continue
            
        all_yolo_boxes.append({
            "coords": coords,
            "class_name": class_name,
            "confidence": box.conf[0].item(),
            "needs_individual_ocr": False # Default ke False
        })

    # Jalankan Logika Analisis Kedekatan
    print("Menganalisis kedekatan objek untuk menentukan strategi OCR...")
    num_boxes = len(all_yolo_boxes)
    for i in range(num_boxes):
        for j in range(i + 1, num_boxes):
            box_a = all_yolo_boxes[i]
            box_b = all_yolo_boxes[j]
            
            x1_a, y1_a, x2_a, y2_a = box_a['coords']
            x1_b, y1_b, x2_b, y2_b = box_b['coords']
            
            cy_a = (y1_a + y2_a) / 2
            cy_b = (y1_b + y2_b) / 2
            avg_height = ((y2_a - y1_a) + (y2_b - y1_b)) / 2

            # Cek kedekatan di sumbu Y (apakah sebaris)
            if abs(cy_a - cy_b) < avg_height * 0.5:
                horizontal_gap = max(x1_a, x1_b) - min(x2_a, x2_b)
                avg_width = ((x2_a - x1_a) + (x2_b - x1_b)) / 2
                
                # Cek kedekatan di sumbu X (apakah berdempetan)
                if horizontal_gap < avg_width * 0.5:
                    all_yolo_boxes[i]['needs_individual_ocr'] = True
                    all_yolo_boxes[j]['needs_individual_ocr'] = True
                    print(f"  -> Terdeteksi: '{box_a['class_name']}' dan '{box_b['class_name']}' berdekatan, akan gunakan OCR individual.")

    # Jalankan OCR Global (pada gambar yang sudah di-crop)
    print("Menjalankan OCR global...")
    ocr_results_full, _ = OCR_ENGINE(image)
    ocr_data = []
    if ocr_results_full:
        for res in ocr_results_full:
            points = np.array(res[0])
            # Koordinat sudah relatif terhadap 'image' (crop)
            x_min, y_min = np.min(points, axis=0)
            x_max, y_max = np.max(points, axis=0)
            ocr_data.append(([x_min, y_min, x_max, y_max], res[1]))

    # Proses setiap box dengan strategi yang sudah ditentukan
    final_detected_objects = []
    all_yolo_boxes.sort(key=lambda box: (box['coords'][1], box['coords'][0]))

    for box in all_yolo_boxes:
        class_name = box['class_name']
        coords = box['coords']
        detected_text = ""

        if class_name in LOGO_CLASSES:
            detected_text = "TERDETEKSI"
        elif box['needs_individual_ocr']:
            # STRATEGI A: OCR Individual (Presisi)
            print(f"  -> Menjalankan OCR individual untuk: {class_name}")
            x1, y1, x2, y2 = map(int, coords)
            box_crop = image[y1:y2, x1:x2]
            if box_crop.size > 0:
                ocr_result_box, _ = OCR_ENGINE(box_crop)
                if ocr_result_box:
                    detected_text = " ".join([res[1] for res in ocr_result_box])
        else:
            # STRATEGI B: OCR Global (Default)
            contained_texts = []
            for ocr_box_coords, ocr_text in ocr_data:
                if is_point_inside_box(get_box_center(ocr_box_coords), coords):
                    contained_texts.append(ocr_text)
            if contained_texts:
                detected_text = " ".join(contained_texts)
        
        fields_to_split_and_remove_colon = [
            'PartBOM_Voltage', 
            'PartBOM_Applicable',
            'PartBOM_StripLength', 
            'PartBOM_WireStripLen'
        ]

        if class_name == 'PartBOM_ULType':
            # Pengecualian 1: Hapus 'CU'
            detected_text = detected_text.replace("CU", "").strip()
        
        elif class_name == 'PartBOM_Current':
            # Pengecualian 2 Hapus teks SEBELUM ':', tapi TETAPKAN ':'
            colon_index = detected_text.find(":")
            if colon_index != -1:
                # Ambil dari ':' (termasuk) sampai akhir, lalu strip
                detected_text = detected_text[colon_index:].strip()

        elif class_name in fields_to_split_and_remove_colon:
            # Logika Default: Jika ada ':', ambil semua teks SETELAH ':' pertama
            if ":" in detected_text:
                detected_text = detected_text.split(":", 1)[-1].strip()
        
        final_detected_objects.append({'class_name': class_name, 'text': detected_text})
       
        # Logika menggambar
        x1, y1, x2, y2 = map(int, coords)
        cv2.rectangle(output_image, (x1, y1), (x2, y2), (255, 0, 0), 2)
        label = f"{class_name}: {detected_text}" if detected_text else class_name
        cv2.putText(output_image, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # 6. Verifikasi hasil
    query_to_use = QUERY_OUTSIDE_LABEL if label_type == 'outside' else QUERY_INSIDE_LABEL
    print(f"Using {label_type.upper()} label query for verification.")

    status, matched, defects = verify_label_completeness(final_detected_objects, query_to_use)
   
    status_color = (0, 255, 0) if status == 'OK' else (0, 0, 255)
    cv2.putText(output_image, f"Status: {status}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2, cv2.LINE_AA)
   
    return output_image, status, matched, defects


# --- KELAS MANAJEMEN KAMERA & APLIKASI FLASK ---
class LabelDetector:
    def __init__(self):
        self.cap = None
        self.thread = None
        self.latest_frame = None
        self.return_frame = None
        self.running = False
        self.yolo_model = None

    def _get_yolo_model(self):
        if self.yolo_model is None:
            self.yolo_model = YOLO(MODEL_PATH)
        return self.yolo_model

    def get_camera(self):
        if self.cap is not None: return {"success": True}
        for i in range(10):
            self.cap = cv2.VideoCapture(i)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                self.start_thread()
                return {"success": True, "message": f"Camera found at index {i}"}
        return {"success": False, "message": "No camera found"}

    def start_thread(self):
        if not self.running and (self.thread is None or not self.thread.is_alive()):
            self.running = True
            self.thread = threading.Thread(target=self._update_frame, daemon=True)
            self.thread.start()

    def stop_thread(self):
        if self.running:
            self.running = False
            if self.thread: self.thread.join()

    def _update_frame(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.latest_frame = frame
                _, buffer = cv2.imencode(".jpg", frame)
                self.return_frame = base64.b64encode(buffer).decode("utf-8")
            time.sleep(0.03)

    def get_frame(self):
        if self.return_frame: return {"success": "success", "frame": self.return_frame}
        return {"success": "noframe", "message": "No frame available"}
       
    def process_image(self):
        if self.latest_frame is None:
            return {"success": False, "message": "No frame from camera to process"}
        try:
            yolo = self._get_yolo_model()
            full_frame = self.latest_frame.copy()

            # Auto-crop logic also determines the label_type
            results = yolo(full_frame, verbose=False)[0]
            inside_box, outside_box = None, None
            inside_conf, outside_conf = 0.0, 0.0
            for box in results.boxes:
                class_name = results.names[int(box.cls[0])].lower()
                confidence = float(box.conf[0])
                if class_name == 'inside' and confidence > inside_conf:
                    inside_box = box.xyxy[0].cpu().numpy().astype(int)
                    inside_conf = confidence
                elif class_name == 'outside' and confidence > outside_conf:
                    outside_box = box.xyxy[0].cpu().numpy().astype(int)
                    outside_conf = confidence
           
            crop_box, label_type = None, 'inside'
            if inside_box is not None:
                crop_box, label_type = inside_box, 'inside'
            elif outside_box is not None:
                crop_box, label_type = outside_box, 'outside'
            else:
                # Jika tidak ada box 'inside' atau 'outside' terdeteksi, default ke 'inside' dan proses seluruh gambar
                print("Peringatan: Tidak ada box 'inside'/'outside' terdeteksi. Memproses seluruh frame sebagai 'inside'.")
                label_type = 'inside' 
           
            cropped_frame = full_frame
            if crop_box is not None:
                x1, y1, x2, y2 = crop_box
                cropped_frame = full_frame[max(0, y1):min(full_frame.shape[0], y2), max(0, x1):min(full_frame.shape[1], x2)]

            if cropped_frame.size == 0:
                return {"success": False, "message": "Auto-crop failed."}
           
            # Jalankan fungsi deteksi/verifikasi yang baru
            output_image, status, matched_results, defect_results = run_detection_and_verification(
                image=cropped_frame,
                yolo_model=yolo,
                label_type=label_type
            )
           
            _, buffer = cv2.imencode(".jpg", output_image)
            encoded_string = base64.b64encode(buffer).decode("utf-8")

            # Tambahkan tipe label yang terdeteksi ke awal list matched_results
            matched_results.insert(0, {
                'item': 'Label Type',
                'db_value': 'N/A (Auto-Detected)',
                'ocr_value': label_type.upper()
            })

            return {
                "success": True,
                "detection_image": encoded_string,
                "status": status,
                "matched_results": matched_results,
                "defect_results": defect_results
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "message": f"An error occurred: {str(e)}"}

# --- ROUTE API FLASK ---
app = Flask(__name__)
CORS(app)
detector = LabelDetector()

@app.route("/api/camera/init", methods=["GET"])
def init_camera():
    return jsonify(detector.get_camera())

@app.route("/api/camera/frame", methods=["GET"])
def get_camera_frame():
    return jsonify(detector.get_frame())

@app.route("/api/process", methods=["GET"])
def process_image_route():
    return jsonify(detector.process_image())

@app.route("/api/camera/close", methods=["GET"])
def close_camera():
    detector.stop_thread()
    if detector.cap and detector.cap.isOpened():
        detector.cap.release()
        detector.cap = None
    return jsonify({"success": True, "message": "Camera closed."})

@app.route("/api/play/pause/frame", methods=["POST"])
def play_pause_frame_route():
    state = request.get_json().get("state", False)
    if state: detector.start_thread()
    else: detector.stop_thread()
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)