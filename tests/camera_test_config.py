import cv2
import json

def get_enabled_rtsp_cameras(config_path="config.json"):
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    cams = []
    for cam in config.get("cameras", []):
        if cam.get("enabled") and cam.get("source_type") == "rtsp":
            cams.append((cam.get("name", f"cam_{cam.get('camera_id')}"), cam["source"]))
    return cams

def test_rtsp_camera(label, rtsp_url):
    print(f"\n--- Testing RTSP Camera '{label}' ---")
    print(f"URL: {rtsp_url}")
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print(f"❌ NÃO foi possível abrir a câmara '{label}' via RTSP.")
        return
    print(f"✅ Câmara '{label}' aberta! Pressione 'q' para sair.")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Falha ao ler frame ou stream fechada.")
            break
        cv2.imshow(f"[RTSP - {label}]", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("A encerrar...")
            break
    cap.release()
    cv2.destroyAllWindows()
    print("Terminado.")

if __name__ == "__main__":
    cameras = get_enabled_rtsp_cameras()
    if not cameras:
        print("Nenhuma câmara RTSP 'enabled:true' no config.json.")
    for label, url in cameras:
        test_rtsp_camera(label, url)
        resp = input("Testar próxima câmara? (enter=sim, n=não): ")
        if resp.lower().startswith('n'):
            break