from pathlib import Path
from urllib.request import urlopen, Request

# URL del servicio público del Ayuntamiento de Madrid con los datos PM. El archivo contiene medidas de tráfico como intensidad, ocupación o carga
PM_URL = "https://informo.madrid.es/informo/tmadrid/pm.xml"

# Ruta local donde se guarda la descarga dentro de la estructura del proyecto.
OUT_PATH = Path(__file__).resolve().parent.parent / "datos_arguelles" / "pm_live.xml"

def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Se añade User-Agent para evitar posibles bloqueos de la petición HTTP
    req = Request(PM_URL, headers={"User-Agent": "Mozilla/5.0"})
    
    # Descargar el XML de sensores PM
    with urlopen(req, timeout=30) as r:
        data = r.read()
    OUT_PATH.write_bytes(data)
    print("OK descargado:", OUT_PATH)

if __name__ == "__main__":
    main()