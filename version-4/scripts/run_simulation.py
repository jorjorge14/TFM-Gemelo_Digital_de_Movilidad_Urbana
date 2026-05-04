import subprocess
import time
from pathlib import Path

# Ruta base de la versión actual del proyecto
ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------
# 1. Mapeo de sensores a edges de SUMO
# Asocia cada sensor real de tráfico con la edge más cercana de la red SUMO. El resultado se guarda en datos_arguelles/sensores_mapeados.csv
# --------------------------------------------------
print("1) Mapeando sensores...")
subprocess.run(["python", "map_sensors_to_edges.py"], cwd=ROOT / "scripts")

# --------------------------------------------------
# 2. Descarga de datos reales de tráfico
# Descarga el archivo pm.xml del Ayuntamiento de Madrid con las medidas actualizadas de los sensores de tráfico. El resultado se guarda como datos_arguelles/pm_live.xml
# --------------------------------------------------
print("2) Descargando datos reales...")
subprocess.run(["python", "fetch_pm_xml.py"], cwd=ROOT / "scripts")

# --------------------------------------------------
# 3. Generación de rutas a partir de datos reales
# Convierte las intensidades medidas por los sensores en flujos de vehículos y posteriormente genera rutas reales completas mediante duarouter.
# --------------------------------------------------
print("3) Generando tráfico real...")
subprocess.run(["python", "build_real_routes_from_pm.py"], cwd=ROOT / "scripts")


# --------------------------------------------------
# 4. Lanzamiento de la simulación SUMO
# Se abre SUMO-GUI usando la configuración de Argüelles. El parámetro --remote-port permite que otro script controle la simulación desde Python mediante TraCIprint("4) Lanzando SUMO...")
# --------------------------------------------------
sumo_cmd = [
    r"C:\Program Files (x86)\Eclipse\Sumo\bin\sumo-gui.exe",
    "-c",
    str(ROOT / "configuraciones" / "arguelles_real.sumocfg"),
    "--remote-port",
    "8813"
]
# Se lanza SUMO como proceso independiente para que siga abierto mientras se ejecuta el sistema de control del vehículo de emergencia.
subprocess.Popen(sumo_cmd)

# Pequeña espera para dar tiempo a que SUMO-GUI termine de arrancar antes de intentar conectarse desde TraCI
time.sleep(5)

# --------------------------------------------------
# 5. Ejecución del sistema de vehículo de emergencia
# El script se conecta a SUMO por TraCI, introduce el vehículo de emergencia, aplica la prioridad semafórica y registra resultados.
# --------------------------------------------------
print("5) Ejecutando vehículo de emergencia...")
subprocess.run(["python", "scripts/emergency_v4.py"], cwd=ROOT)

