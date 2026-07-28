import subprocess
import time
from pathlib import Path

# Ruta base de la versión actual del proyecto
ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------
# 1. Descarga del mapa de Argüelles
# Descarga desde OpenStreetMap la red viaria de la zona de estudio y la guarda como mapas/arguelles.osm
# --------------------------------------------------
print("1) Descargando mapa de Argüelles...")
subprocess.run(["python", str(ROOT / "scripts" / "download_arguelles_map.py")], cwd=ROOT / "mapas", check=True)


# --------------------------------------------------
# 2. Conversión del mapa OSM a red SUMO
# Convierte el archivo arguelles.osm en una red de SUMO. El resultado se guarda como mapas/arguelles.net.xml
# --------------------------------------------------
print("2) Generando red SUMO...")
subprocess.run(["netconvert", "--osm-files", "arguelles.osm", "-o", "arguelles.net.xml", "--proj.utm", "--output.street-names", "true"], cwd=ROOT / "mapas", check=True)


# --------------------------------------------------
# 3. Mapeo de sensores a edges de SUMO
# Asocia cada sensor real de tráfico con la edge más cercana de la red SUMO. El resultado se guarda en datos_arguelles/sensores_mapeados.csv
# --------------------------------------------------
print("3) Mapeando sensores...")
subprocess.run(["python", "map_sensors_to_edges.py"], cwd=ROOT / "scripts", check=True)


# --------------------------------------------------
# 4. Descarga de datos reales de tráfico
# Descarga el archivo pm.xml del Ayuntamiento de Madrid con las medidas actualizadas de los sensores de tráfico. El resultado se guarda como datos_arguelles/pm_live.xml
# --------------------------------------------------
print("4) Descargando datos reales...")
subprocess.run(["python", "download_traffic_data.py"], cwd=ROOT / "scripts", check=True)


# --------------------------------------------------
# 5. Generación de rutas a partir de datos reales
# Convierte las intensidades medidas por los sensores en flujos de vehículos y posteriormente genera rutas reales completas mediante duarouter.
# --------------------------------------------------
print("5) Generando tráfico real...")
subprocess.run(["python", "build_real_routes_from_pm.py"], cwd=ROOT / "scripts", check=True)


# --------------------------------------------------
# 6. Lanzamiento de la simulación SUMO
# Se abre SUMO-GUI usando la configuración de la versión 4. El parámetro --remote-port permite que otro script controle la simulación desde Python mediante TraCI.
# --------------------------------------------------
print("6) Lanzando SUMO-GUI...")
subprocess.Popen(["sumo-gui", "-c", str(ROOT / "configuraciones" / "arguelles_real.sumocfg"), "--remote-port", "8813"], cwd=ROOT)
# Pequeña espera para dar tiempo a que SUMO-GUI termine de arrancar antes de intentar conectarse desde TraCI
time.sleep(5)


# --------------------------------------------------
# 7. Ejecución del sistema de vehículo de emergencia
# El script se conecta a SUMO por TraCI, introduce el vehículo de emergencia, aplica prioridad semafórica, realiza rerouting y registra resultados.
# --------------------------------------------------
print("7) Ejecutando vehículo de emergencia...")
subprocess.run(["python", "emergency_v4.py"], cwd=ROOT / "scripts", check=True)