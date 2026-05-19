import subprocess
from pathlib import Path

# Ruta base del módulo actual del proyecto
ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------
# 1. Descarga del mapa de Argüelles
# Descarga desde OpenStreetMap la red viaria de la zona de estudio y la guarda como mapas/arguelles.osm
# --------------------------------------------------
print("1) Descargando mapa de Argüelles...")
subprocess.run(["python", str(ROOT / "scripts" / "download_arguelles_map.py")], cwd=ROOT / "mapas")


# --------------------------------------------------
# 2. Conversión del mapa OSM a red SUMO
# Convierte el archivo arguelles.osm en una red de SUMO. El resultado se guarda como mapas/arguelles.net.xml
# --------------------------------------------------
print("2) Generando red SUMO...")
subprocess.run(["netconvert", "--osm-files", "arguelles.osm", "-o", "arguelles.net.xml", "--proj.utm"], cwd=ROOT / "mapas")


# --------------------------------------------------
# 3. Generación de tráfico aleatorio
# Genera viajes aleatorios sobre la red de Argüelles. El resultado se guarda como mapas/arguelles.rou.xml
# --------------------------------------------------
print("3) Generando tráfico aleatorio...")
subprocess.run(["python", str(ROOT / "scripts" / "randomTrips.py"), "-n", "arguelles.net.xml", "-o", "arguelles.rou.xml", "-b", "0", "-e", "3600", "-p", "1"], cwd=ROOT / "mapas")



# --------------------------------------------------
# 4. Lanzamiento de la simulación SUMO
# Abre SUMO-GUI usando la configuración de la versión 1, basada en tráfico aleatorio
# --------------------------------------------------
print("4) Lanzando SUMO-GUI...")
subprocess.run(["sumo-gui", "-c", str(ROOT / "configuraciones" / "arguelles_random.sumocfg")], cwd=ROOT)