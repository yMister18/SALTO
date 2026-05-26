import cv2

def test_camera(camera_id=0):
    print(f"Tentando abrir a câmara ID={camera_id} ...")
    cap = cv2.VideoCapture(camera_id)

    if not cap.isOpened():
        print(f"Câmara {camera_id} NÃO abriu.")
        return

    print(f"Câmara {camera_id} aberta com sucesso. Pressione 'q' para sair.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Falha ao ler frame da câmara.")
            break

        cv2.imshow(f'Camera {camera_id}', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("A encerrar...")
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Terminado.")

if __name__ == "__main__":
    # Tenta abrir IDs de 0 a 3 automaticamente
    for cam_id in range(4):
        print(f"\n--------------------\nTeste para Camera ID={cam_id}")
        test_camera(cam_id)
        resp = input("Testar próxima camera? (enter para continuar, n para sair): ")
        if resp.lower().startswith('n'):
            break