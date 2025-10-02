# -*- coding: utf-8 -*-
import os
import sys
import re
import time
import hashlib
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

from PyQt5.QtCore import pyqtSignal, QThread
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QComboBox, QMessageBox, QProgressBar
)

# --- Mapeo de clases a carpetas (rutas exactas en Windows) ---
CARPETAS = {
    "Fresa": r"C:\Users\MSI LAPTOP\Desktop\Modelo apra clasificar\frutasCarla\Fresa",
    "Higo":  r"C:\Users\MSI LAPTOP\Desktop\Modelo apra clasificar\frutasCarla\Higo",
    "Nuez":  r"C:\Users\MSI LAPTOP\Desktop\Modelo apra clasificar\frutasCarla\Nuez",
}

# --- Configuración de red ---
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 15


# --- Utilidades ---
def asegurar_carpeta(path: str):
    os.makedirs(path, exist_ok=True)

def limpiar_nombre_archivo(nombre: str) -> str:
    # Quitar caracteres no válidos para Windows
    return re.sub(r'[\\/*?:"<>|]+', "_", nombre)

def extension_desde_content_type(content_type: str) -> str:
    if not content_type:
        return ""
    content_type = content_type.lower()
    mapping = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/bmp": "bmp",
        "image/tiff": "tiff",
        "image/svg+xml": "svg",
        "image/x-icon": "ico",
        "image/vnd.microsoft.icon": "ico",
        "image/heic": "heic",
        "image/heif": "heif",
        "image/avif": "avif",
    }
    return mapping.get(content_type, "")

def extension_desde_url(u: str) -> str:
    # Intenta deducir extensión a partir de la URL
    path = urlparse(u).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg", ".ico", ".heic", ".heif", ".avif"):
        if path.endswith(ext):
            return ext.lstrip(".")
    return ""

def hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def normalizar_srcset(srcset: str):
    """
    Toma un atributo srcset y devuelve la URL del candidato con mayor "descriptor" (ancho).
    Ej: "img1.jpg 320w, img2.jpg 640w" -> "img2.jpg"
    """
    try:
        candidates = []
        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue
            bits = part.split()
            url = bits[0]
            w = 0
            if len(bits) > 1 and bits[1].endswith("w"):
                try:
                    w = int(bits[1].replace("w", ""))
                except:
                    w = 0
            candidates.append((w, url))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[-1][1]  # mayor ancho
    except Exception:
        return None

def recolectar_urls_imagenes(html: str, base_url: str):
    soup = BeautifulSoup(html, "lxml")
    urls = set()

    # <img src> y srcset
    for img in soup.find_all("img"):
        src = img.get("src")
        if src:
            urls.add(urljoin(base_url, src))
        srcset = img.get("srcset")
        if srcset:
            mejor = normalizar_srcset(srcset)
            if mejor:
                urls.add(urljoin(base_url, mejor))

    # <source srcset> (dentro de <picture> generalmente)
    for source in soup.find_all("source"):
        srcset = source.get("srcset")
        if srcset:
            mejor = normalizar_srcset(srcset)
            if mejor:
                urls.add(urljoin(base_url, mejor))
        src = source.get("src")
        if src:
            urls.add(urljoin(base_url, src))

    # Enlaces directos a imágenes (<a href="...">)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        absu = urljoin(base_url, href)
        if extension_desde_url(absu):
            urls.add(absu)

    # Filtrado básico por esquema
    urls = {u for u in urls if urlparse(u).scheme in ("http", "https")}
    return list(urls)


# --- Worker en hilo aparte para no congelar la UI ---
class Worker(QThread):
    log = pyqtSignal(str)
    progreso = pyqtSignal(int)    # porcentaje 0..100
    terminado = pyqtSignal(int)   # cantidad descargada

    def __init__(self, url: str, clase: str, carpeta_destino: str, parent=None):
        super().__init__(parent)
        self.url = url.strip()
        self.clase = clase
        self.destino = carpeta_destino
        self._cancel = False

    def cancelar(self):
        self._cancel = True

    def run(self):
        if not self.url:
            self.log.emit("❗ URL vacía.")
            self.terminado.emit(0)
            return
        asegurar_carpeta(self.destino)

        self.log.emit(f"📥 Descargando página: {self.url}")
        try:
            resp = requests.get(self.url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
        except Exception as e:
            self.log.emit(f"❌ Error al obtener la página: {e}")
            self.terminado.emit(0)
            return

        urls = recolectar_urls_imagenes(resp.text, self.url)
        total = len(urls)
        if total == 0:
            self.log.emit("ℹ️ No se encontraron imágenes en la página.")
            self.terminado.emit(0)
            return

        self.log.emit(f"🔎 Imágenes detectadas: {total}")
        hashes_vistos = set()
        descargadas = 0

        for i, img_url in enumerate(urls, start=1):
            if self._cancel:
                self.log.emit("⏹️ Operación cancelada por el usuario.")
                break

            self.progreso.emit(int(i * 100 / total))

            try:
                r = requests.get(img_url, headers=HEADERS, timeout=TIMEOUT, stream=True)
                r.raise_for_status()

                ctype = (r.headers.get("Content-Type") or "").lower()
                if not ctype.startswith("image"):
                    self.log.emit(f"— Omitida (no es imagen): {img_url}")
                    continue

                data = r.content
                h = hash_bytes(data)
                if h in hashes_vistos:
                    self.log.emit(f"— Duplicada (hash repetido): {img_url}")
                    continue
                hashes_vistos.add(h)

                ext = extension_desde_content_type(ctype) or extension_desde_url(img_url) or "jpg"
                ts = time.strftime("%Y%m%d-%H%M%S")
                nombre_base = f"{self.clase}_{ts}_{h[:8]}.{ext}"
                nombre = limpiar_nombre_archivo(nombre_base)
                destino_final = os.path.join(self.destino, nombre)

                with open(destino_final, "wb") as f:
                    f.write(data)

                descargadas += 1
                self.log.emit(f"✅ Guardada: {destino_final}")
            except Exception as e:
                self.log.emit(f"❌ Error con {img_url} -> {e}")

        self.terminado.emit(descargadas)


# --- Ventana principal ---
class Ventana(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scraper de Imágenes - Frutas")
        self.setMinimumWidth(720)

        # Widgets
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Ingrese la URL de la página...")

        self.clase_combo = QComboBox()
        self.clase_combo.addItems(["Fresa", "Higo", "Nuez"])

        self.btn_descargar = QPushButton("Descargar imágenes")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setEnabled(False)

        self.progreso = QProgressBar()
        self.progreso.setRange(0, 100)
        self.progreso.setValue(0)

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        # Layout
        fila1 = QHBoxLayout()
        fila1.addWidget(QLabel("URL:"))
        fila1.addWidget(self.url_edit)

        fila2 = QHBoxLayout()
        fila2.addWidget(QLabel("Clase de fruta:"))
        fila2.addWidget(self.clase_combo)
        fila2.addStretch()
        fila2.addWidget(self.btn_descargar)
        fila2.addWidget(self.btn_cancelar)

        layout = QVBoxLayout(self)
        layout.addLayout(fila1)
        layout.addLayout(fila2)
        layout.addWidget(self.progreso)
        layout.addWidget(QLabel("Registro:"))
        layout.addWidget(self.log)

        # Eventos
        self.btn_descargar.clicked.connect(self.iniciar)
        self.btn_cancelar.clicked.connect(self.cancelar)

        self.worker = None

    def iniciar(self):
        url = self.url_edit.text().strip()
        clase = self.clase_combo.currentText()
        carpeta = CARPETAS[clase]

        # Crear carpeta si no existe
        try:
            asegurar_carpeta(carpeta)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo crear/acceder a la carpeta destino:\n{carpeta}\n{e}")
            return

        self.log.clear()
        self.log.append(f"Clase seleccionada: {clase}")
        self.log.append(f"Carpeta destino: {carpeta}")

        self.worker = Worker(url, clase, carpeta)
        self.worker.log.connect(self.log.append)
        self.worker.progreso.connect(self.progreso.setValue)
        self.worker.terminado.connect(self.fin_descarga)

        self.btn_descargar.setEnabled(False)
        self.btn_cancelar.setEnabled(True)
        self.progreso.setValue(0)

        self.worker.start()

    def cancelar(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancelar()
            self.btn_cancelar.setEnabled(False)

    def fin_descarga(self, cantidad: int):
        self.btn_descargar.setEnabled(True)
        self.btn_cancelar.setEnabled(False)
        self.worker = None
        self.log.append(f"\n📦 Total de imágenes guardadas: {cantidad}")
        if cantidad == 0:
            QMessageBox.information(self, "Finalizado", "No se guardaron imágenes. Revise la URL o el registro.")
        else:
            QMessageBox.information(self, "Finalizado", f"Se guardaron {cantidad} imágenes.")


def main():
    app = QApplication(sys.argv)
    w = Ventana()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
