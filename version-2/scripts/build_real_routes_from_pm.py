import math
import random
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import sumolib


# -------------------------
# Rutas del proyecto
# Se construyen rutas relativas a la raíz del proyecto para evitar problemas de ejecución desde distintas ubicaciones
# -------------------------
ROOT = Path(__file__).resolve().parent.parent
NET_PATH = ROOT / "mapas" / "arguelles.net.xml"
MAP_CSV = ROOT / "datos_arguelles" / "sensores_mapeados.csv"
PM_XML = ROOT / "datos_arguelles" / "pm_live.xml"

FLOWS_OUT = ROOT / "mapas" / "arguelles_real_flows.xml"
ROUTES_OUT = ROOT / "mapas" / "arguelles_real_routes.rou.xml"

# Ruta a duarouter (herramienta de SUMO para generar rutas)
DUAROUTER_EXE = r"C:\Program Files (x86)\Eclipse\Sumo\bin\duarouter.exe"

# -------------------------
# Parámetros de simulación
# -------------------------
SIM_DURATION_S = 3600           # Duración total de la simulación (segundos)
INTERVAL_S = 300                # Tamaño de cada intervalo temporal (5 min)

MAX_SENSORS = None              # Limitar sensores (None = usar todos)

GLOBAL_SCALE = 0.40             # Escala global de demanda (para reducir la intensidad real a un 40 %)
MAX_VEH_PER_FLOW = 60           # Límite máximo de vehículos por sensor e intervalo
USE_ONLY_BORDER_SENSORS = True  # Usar solo sensores de borde para evitar doble conteo

RANDOM_SEED = 42                 


# -------------------------
# Lectura de datos desde pm.xml
# Lee el archivo pm.xml y devuelve un diccionario: idelem -> intensidad (veh/h)
# -------------------------
def parse_pm_intensities(pm_path: Path) -> dict[int, float]:
    
    tree = ET.parse(pm_path)
    root = tree.getroot()

    out = {}
    for pm in root.findall(".//pm"):
        idelem = pm.findtext("idelem")
        intensidad = pm.findtext("intensidad")
        if idelem is None or intensidad is None:
            continue
        try:
            out[int(idelem)] = float(intensidad)
        except ValueError:
            continue
    return out


# -------------------------
# Filtro de edges válidos
# Filtra edges internas de SUMO (las que empiezan por ':'), que no son adecuadas como origen/destino de tráfico
# -------------------------
def is_good_edge(edge) -> bool:

    return not edge.getID().startswith(":")

# -------------------------
# Detección de sensores frontera
# Marca sensores cercanos al borde del área de estudio. Esto ayuda a representar entradas/salidas de tráfico y evita doble conteo
# -------------------------
def mark_border_sensors(net: sumolib.net.Net, df_map: pd.DataFrame) -> pd.DataFrame:

    xs, ys = [], []
    for _, r in df_map.iterrows():
        try:
            x, y = net.convertLonLat2XY(float(r["lon"]), float(r["lat"]))
            xs.append(x)
            ys.append(y)
        except Exception:
            continue
        
    # Si no se pueden calcular coordenadas, marcar todos como borde
    if not xs or not ys:
        df_map["is_border"] = True
        return df_map

    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)

    margin = 120.0  # margen en metros
    border_flags = []
    for _, r in df_map.iterrows():
        try:
            x, y = net.convertLonLat2XY(float(r["lon"]), float(r["lat"]))
            is_border = (
                (x - xmin) < margin or (xmax - x) < margin or
                (y - ymin) < margin or (ymax - y) < margin
            )
        except Exception:
            is_border = False
        border_flags.append(is_border)

    df_map["is_border"] = border_flags
    return df_map


# -------------------------
# Selección de edges destino (sinks)
# Selecciona edges de salida (destinos) cercanas al borde del área.
# -------------------------
def pick_sink_edges(net: sumolib.net.Net, n: int = 30) -> list[str]:
    
    df_map = pd.read_csv(MAP_CSV)

    xs, ys = [], []
    for _, r in df_map.iterrows():
        try:
            x, y = net.convertLonLat2XY(float(r["lon"]), float(r["lat"]))
            xs.append(x)
            ys.append(y)
        except Exception:
            continue

    if not xs or not ys:
        driveable = [e.getID() for e in net.getEdges() if is_good_edge(e)]
        random.shuffle(driveable)
        return driveable[:n]

    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    margin = 150.0

    candidates = []
    for e in net.getEdges():
        if not is_good_edge(e):
            continue
        if e.getLength() < 20:
            continue

        x1, y1 = e.getFromNode().getCoord()
        x2, y2 = e.getToNode().getCoord()

        if (x1 < xmin - margin or x1 > xmax + margin or y1 < ymin - margin or y1 > ymax + margin or
            x2 < xmin - margin or x2 > xmax + margin or y2 < ymin - margin or y2 > ymax + margin):
            candidates.append(e.getID())

    random.shuffle(candidates)
    if len(candidates) >= n:
        return candidates[:n]

    driveable = [e.getID() for e in net.getEdges() if is_good_edge(e)]
    random.shuffle(driveable)
    return (candidates + driveable)[:n]


# -------------------------
# Conversión intensidad → vehículos
# Convierte veh/h a número de vehículos en un intervalo. Aplica una escala global para reducir la demanda a un nivel manejable y un límite máximo por flujo para evitar congestión.
# -------------------------
def intensity_to_vehicles(intensity_vph: float, interval_s: int) -> int:
    
    intensity_vph = max(0.0, intensity_vph) * GLOBAL_SCALE
    expected = intensity_vph * (interval_s / 3600.0)

    base = math.floor(expected)
    frac = expected - base
    n = base + (1 if random.random() < frac else 0)

    n = min(n, MAX_VEH_PER_FLOW)
    return n


# -------------------------
# Escritura flows
# Genera el archivo XML de flows para SUMO. Cada flow representa vehículos desde un sensor hacia un destino.
# -------------------------
def write_flows_xml(flows_path: Path, df: pd.DataFrame, sinks: list[str]) -> int:
    
    flows_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                 'xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">')

    flow_id = 0
    for t in range(0, SIM_DURATION_S, INTERVAL_S):
        begin = t
        end = min(t + INTERVAL_S, SIM_DURATION_S)
        window = end - begin

        for _, r in df.iterrows():
            edge_from = str(r["edge_id"])
            intensity = float(r["intensidad_vph"])

            nveh = intensity_to_vehicles(intensity, window)
            if nveh <= 0:
                continue

            edge_to = random.choice(sinks)

            lines.append(
                f'    <flow id="f{flow_id}" begin="{begin}" end="{end}" number="{nveh}" '
                f'from="{edge_from}" to="{edge_to}" departLane="best" departSpeed="max"/>'
            )
            flow_id += 1

    lines.append("</routes>")
    flows_path.write_text("\n".join(lines), encoding="utf-8")
    return flow_id

# -------------------------
# Ejecución de duarouter. Ejecuta duarouter para convertir flows en rutas completas.
# -------------------------
def run_duarouter(net_path: Path, flows_path: Path, routes_out: Path) -> None:
    routes_out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        DUAROUTER_EXE,
        "-n", str(net_path),
        "-r", str(flows_path),
        "-o", str(routes_out),
        "--ignore-errors", "true",
        "--no-warnings", "true",
        "--no-step-log", "true",
    ]

    print("Ejecutando duarouter...")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)

# -------------------------
# MAIN
# -------------------------
def main():
    random.seed(RANDOM_SEED)

    # 1) Cargar la red de SUMO de la zona de estudio
    net = sumolib.net.readNet(str(NET_PATH))

    # 2) Leer las intensidades de tráfico reales desde el archivo pm.xml
    intens = parse_pm_intensities(PM_XML)
    if not intens:
        raise RuntimeError("No se han leído intensidades del pm.xml.")

    # 3) Cargar el archivo de sensores ya mapeados a edges de SUMO
    df_map = pd.read_csv(MAP_CSV)
    # Limpiar y asegurar tipos correctos en las columnas
    df_map["idelem"] = pd.to_numeric(df_map["idelem"], errors="coerce")
    df_map = df_map.dropna(subset=["idelem", "edge_id"]).copy()
    df_map["idelem"] = df_map["idelem"].astype(int)
    # Asociar a cada sensor su intensidad real en veh/h
    df_map["intensidad_vph"] = df_map["idelem"].map(intens).fillna(0.0)

    # 4) Filtrar sensores asociados a edges válidas de la red. Se eliminan: edges que no existen en la red y edges internas (no aptas como origen/destino)
    ok_rows = []
    for _, r in df_map.iterrows():
        eid = str(r["edge_id"])
        if not net.hasEdge(eid):
            ok_rows.append(False)
            continue
        if is_good_edge(net.getEdge(eid)):
            ok_rows.append(True)
        else:
            ok_rows.append(False)
    df_map = df_map.loc[ok_rows].copy()

    # 5) Identificar sensores situados en el borde de la zona. Esto permite aproximar mejor las entradas y salidas de tráfico
    df_map = mark_border_sensors(net, df_map)
    # Opcional: usar solo sensores de borde para evitar doble conteo
    if USE_ONLY_BORDER_SENSORS:
        df_use = df_map[df_map["is_border"]].copy()
    else:
        df_use = df_map.copy()

    # 6) Limitar número de sensores (útil para pruebas)
    if MAX_SENSORS is not None:
        df_use = df_use.head(int(MAX_SENSORS)).copy()

    print("Sensores con edge válido:", len(df_map))
    print("Sensores usados:", len(df_use), "(border_only =", USE_ONLY_BORDER_SENSORS, ")")

    # 7) Seleccionar edges destino (sinks). Representan posibles salidas del tráfico fuera de la zona
    sinks = pick_sink_edges(net, n=30)
    print("Sinks:", len(sinks))

    # 8) Generar los flows (vehículos) a partir de las intensidades reales. Cada flow indica cuántos vehículos salen de un sensor en cada intervalo
    flows_n = write_flows_xml(FLOWS_OUT, df_use, sinks)
    print("OK flows:", FLOWS_OUT)
    print("Flows generados:", flows_n)
    print("GLOBAL_SCALE =", GLOBAL_SCALE, "| MAX_VEH_PER_FLOW =", MAX_VEH_PER_FLOW)
    print("SIM_DURATION_S =", SIM_DURATION_S, "| INTERVAL_S =", INTERVAL_S)

    # 9) Ejecutar duarouter para convertir los flows en rutas completas. Esto genera los trayectos que seguirán los vehículos en la simulación
    run_duarouter(NET_PATH, FLOWS_OUT, ROUTES_OUT)
    print("OK routes:", ROUTES_OUT)

if __name__ == "__main__":
    main()