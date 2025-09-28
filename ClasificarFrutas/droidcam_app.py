import cv2
import time
import requests

def check_connection():
    """Verificar si DroidCam está accesible"""
    try:
        response = requests.get("http://192.168.1.9:4747", timeout=5)
        if response.status_code == 200:
            print("✅ DroidCam está accesible via web")
            return True
    except:
        print("❌ No se puede acceder a DroidCam via web")
        return False

def main():
    print("🔍 Verificando conexión con DroidCam...")
    
    # Primero verificar conexión básica
    if not check_connection():
        print("\n🔧 Solución de problemas:")
        print("1. ✅ ¿DroidCam está EJECUTÁNDOSE en tu celular? (Debe decir 'Active')")
        print("2. ✅ ¿Ambos en la MISMA red WiFi?")
        print("3. 🔄 Reinicia DroidCam en el celular")
        print("4. 🔄 Reinicia el WiFi en ambos dispositivos")
        print("5. 🛡️ Desactiva el firewall temporalmente")
        return
    
    print("🚀 Intentando conectar video...")
    
    # Diferentes opciones de conexión para probar
    video_sources = [
        "http://192.168.1.9:4747/video",
        "http://192.168.1.9:4747/mjpegfeed?640x480",
        "http://192.168.1.9:4747/mjpegfeed?320x240"
    ]
    
    cap = None
    for source in video_sources:
        print(f"🔗 Probando: {source}")
        cap = cv2.VideoCapture(source)
        time.sleep(2)
        
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"✅ ¡Conectado! Resolución: {frame.shape[1]}x{frame.shape[0]}")
                break
            else:
                cap.release()
                cap = None
        else:
            cap = None
    
    if cap is None:
        print("❌ No se pudo conectar con ninguna opción de video")
        print("\n🎯 Prueba esto:")
        print("1. En DroidCam ve a Settings → Video Settings")
        print("2. Cambia 'Video Resolution' a 640x480 o menor")
        print("3. Activa 'Use MJPG Camera Feed'")
        print("4. Reinicia DroidCam")
        return
    
    # Mostrar video
    print("🎥 Mostrando video... Presiona 'q' para salir")
    cv2.namedWindow('Cámara Celular', cv2.WINDOW_NORMAL)
    
    try:
        while True:
            ret, frame = cap.read()
            if ret:
                cv2.imshow('Cámara Celular', frame)
            else:
                print("⚠️ Error en frame")
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        print("⏹️ Detenido por usuario")
    
    cap.release()
    cv2.destroyAllWindows()
    print("👋 Programa terminado")

if __name__ == "__main__":
    main()