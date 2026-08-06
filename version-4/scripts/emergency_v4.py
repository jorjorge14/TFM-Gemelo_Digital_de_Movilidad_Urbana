from pathlib import Path
import csv
import traci
import xml.etree.ElementTree as ET
import traci.constants as tc

# Puerto usado para conectar Python con SUMO mediante TraCI. SUMO debe haberse iniciado previamente con el mismo puerto
PORT = 8813

# Identificador del vehículo de emergencia dentro de la simulación
EMERGENCY_ID = "EM1"
# Identificador de la ruta asignada al vehículo de emergencia
EMERGENCY_ROUTE_ID = "EM_ROUTE_1"

# Instante de simulación en el que se introduce el vehículo de emergencia
DEPART_TIME = 500

# Origen y destino del vehículo de emergencia
FROM_EDGE = "238829520"
TO_EDGE = "5990070#1"   #"5989317"   #"5990532"    

# --------------------------------------------------
# Modos de ejecución!!!!
# --------------------------------------------------
# "base"         -> simulación sin prioridad semafórica ni rerouting
# "inteligente" -> simulación con prioridad semafórica y rerouting dinámico
MODE = "inteligente" 

# Tiempo máximo de simulación
SIM_END = 3600

# --------------------------------------------------
# Parámetros de prioridad de los semáforos
# --------------------------------------------------
# Distancia máxima al semáforo a partir de la cual se activa la prioridad
CONTROL_DISTANCE_M = 120.0
# Distancia mínima al semáforo por debajo de la cual se evita intervenir 
MIN_CONTROL_DISTANCE_M = 2.0
# Umbrales para detectar si el vehículo de emergencia se ha quedado prácticamente parado junto a la línea de detención del semáforo
STUCK_DISTANCE_M = 2.5        
STUCK_SPEED_M_S = 0.5
# Tiempo máximo que se permite mantener al vehículo de emergencia en esa situación antes de restaurar el semáforo          
STUCK_TIME_S = 8    
# Tiempo durante el que se evita volver a actuar sobre un semáforo restaurado (tiempo de enfriamiento)           
TLS_COOLDOWN_S = 20            

# --------------------------------------------------
# Parámetros de rerouting
# --------------------------------------------------
# Frecuencia mínima entre recálculos de ruta
REROUTE_EVERY_S = 10
# Distancia mínima al siguiente semáforo para permitir rerouting. Si el vehículo de emergencia ya está cerca de un cruce, se evita modificar su ruta
REROUTE_MIN_TLS_DIST_M = 20.0 

# Rutas donde se almacenan los resultados de las simulaciones para poder analizarlos
BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "resultados"
RESULTS_CSV = RESULTS_DIR / "emergency_results.csv"
PM_XML = BASE_DIR / "datos_arguelles" / "pm_live.xml"

# --------------------------------------------------
# Parámetros para prueba controlada del rerouting (con edge destino "5990070#1")
# --------------------------------------------------
# Para hacer la prueba poner valor a TRUE, sino dejar en FALSE 
FORCE_REROUTING_TEST = True
# Edge futuro de la ruta a la que se asigna un coste muy elevado 
TEST_PENALIZED_EDGE = "43407381#4"
# Tiempo de viaje artificial asignado a esa arista
TEST_EDGE_TRAVEL_TIME_S = 10000.0

# Obtiene la fecha y hora de la captura de datos de tráfico usada en la simulación para el analisis de los resultados
def get_traffic_data_time() -> str:
    try:
        root = ET.parse(PM_XML).getroot()
        fecha = root.find(".//fecha_hora")
        if fecha is not None and fecha.text:
            return fecha.text.strip()
    except Exception as e:
        print(f"No se pudo leer la fecha_hora de pm_live.xml: {e}")
    return ""

# Calcula la ruta más rápida entre dos edges usando el motor de rutas de SUMO. Se utiliza el tipo de vehículo "emergency" para que SUMO tenga en cuenta las características definidas para ese vehículo
def compute_fastest_route(from_edge: str, to_edge: str) -> list[str]:
    result = traci.simulation.findRoute(from_edge, to_edge, vType="emergency")
    edges = list(result.edges)
    if not edges:
        raise RuntimeError(f"No existe ruta entre {from_edge} y {to_edge}")
    return edges


# Inserta el vehículo de emergencia en la simulación con una ruta inicial válida
def insert_emergency_vehicle(current_time: float):
    # Calcular la ruta inicial entre el origen y el destino definidos
    edges = compute_fastest_route(FROM_EDGE, TO_EDGE)
    
    # Crear en SUMO la ruta que seguirá inicialmente el vehículo de emergencia e insertarlo en la simulación
    traci.route.add(EMERGENCY_ROUTE_ID, edges)
    traci.vehicle.add(
        vehID=EMERGENCY_ID,
        routeID=EMERGENCY_ROUTE_ID,
        typeID="emergency",
        depart=str(int(current_time))
    )
    print(f"t={current_time:.0f} Aparece el vehículo de emergencia {EMERGENCY_ID} en la vía")
    print(f"Modo: {MODE}")
    print(f"Ruta inicial: {' -> '.join(edges)}")


# Obtiene la definición de los programas de los semáforos
def get_program_logics(tls_id: str):
    try:
        return traci.trafficlight.getAllProgramLogics(tls_id)
    except Exception:
        return traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)


# Obtiene el identificador del programa de los semáforos
def get_logic_program_id(logic):
    return getattr(logic, "programID", getattr(logic, "_subID", None))


# Obtiene las fases de un programa de los semáforos
def get_logic_phases(logic):
    phases = getattr(logic, "phases", None)
    if phases is not None:
        return phases
    return logic.getPhases()


# Obtiene el estado rojo/amarillo/verde de una fase de cada semáforo
def get_phase_state(phase):
    return getattr(phase, "state", None)


# Busca una fase del semáforo que dé verde al movimiento concreto del vehículo de emergencia
def choose_green_phase_for_link(tls_id: str, link_index: int):
    current_program = traci.trafficlight.getProgram(tls_id)
    logics = get_program_logics(tls_id)
    for logic in logics:
        program_id = get_logic_program_id(logic)
        if program_id != current_program:
            continue
        phases = get_logic_phases(logic)
        for i, phase in enumerate(phases):
            state = get_phase_state(phase)
            if state is None:
                continue
            if (
                0 <= link_index < len(state)
                and state[link_index] in ("G", "g")
            ):
                return i
    # Si el programa actual no contiene una fase favorable (raro), no se interviene sobre el semáforo
    return None


# Configura una prueba controlada para provocar un cambio de ruta
def configure_forced_rerouting_test(current_time: float):
    if not FORCE_REROUTING_TEST:
        return
    current_route = list(
        traci.vehicle.getRoute(EMERGENCY_ID)
    )
    if TEST_PENALIZED_EDGE not in current_route:
        print(
            f"Prueba de rerouting: la arista "
            f"{TEST_PENALIZED_EDGE} no pertenece a la ruta inicial"
        )
        return
    # Utilizar los pesos personalizados del vehículo y, para el resto de aristas, los tiempos agregados de la simulación
    traci.vehicle.setRoutingMode(
        EMERGENCY_ID,
        tc.ROUTING_MODE_AGGREGATED_CUSTOM
    )
    # Asignar un tiempo de viaje artificialmente elevado a una arista futura de la ruta
    traci.vehicle.setAdaptedTraveltime(
        EMERGENCY_ID,
        TEST_PENALIZED_EDGE,
        time=TEST_EDGE_TRAVEL_TIME_S,
        begTime=current_time,
        endTime=SIM_END
    )
    print(
        f"Prueba de rerouting activada: se asignan "
        f"{TEST_EDGE_TRAVEL_TIME_S:.0f} s a la arista "
        f"{TEST_PENALIZED_EDGE}"
    )


# Recalcula dinámicamente la ruta del vehículo de emergencia utilizando los tiempos de viaje actuales de la simulación
def reroute_emergency(current_time: float):
    # Obtener la arista actual del vehículo de emergencia
    current_edge = traci.vehicle.getRoadID(EMERGENCY_ID)
    # No recalcular si no se puede identificar la arista actual o si el vehículo está atravesando un cruce
    if not current_edge or current_edge.startswith(":"):
        return
    # No recalcular si el vehículo ya ha alcanzado la arista de destino
    if current_edge == TO_EDGE:
        return
    # Evitar cambios de ruta cuando el vehículo está muy cerca del siguiente semáforo
    tls_list = traci.vehicle.getNextTLS(EMERGENCY_ID)
    if tls_list:
        distance_to_tls = tls_list[0][2]
        if distance_to_tls <= REROUTE_MIN_TLS_DIST_M:
            return
    try:
        # Obtener únicamente la parte pendiente de la ruta actual
        previous_route = list(
            traci.vehicle.getRoute(EMERGENCY_ID)
        )
        previous_route_index = traci.vehicle.getRouteIndex(
            EMERGENCY_ID
        )
        previous_remaining_route = previous_route[
            previous_route_index:
        ]
        # Recalcular la ruta utilizando los tiempos de viaje actuales y agregados de la red
        traci.vehicle.rerouteTraveltime(
            EMERGENCY_ID,
            currentTravelTimes=True
        )
        # Obtener la nueva ruta pendiente
        new_route = list(
            traci.vehicle.getRoute(EMERGENCY_ID)
        )
        new_route_index = traci.vehicle.getRouteIndex(
            EMERGENCY_ID
        )
        new_remaining_route = new_route[
            new_route_index:
        ]
        # Comprobar si el recálculo ha producido un cambio real
        if new_remaining_route != previous_remaining_route:
            print(f"t={current_time:.0f} Se modifica la ruta según el estado actual del tráfico")
            print("Ruta anterior pendiente: "+ " -> ".join(previous_remaining_route))
            print("Nueva ruta pendiente: "+ " -> ".join(new_remaining_route))
        else:
            print(f"t={current_time:.0f} Se recalcula la ruta")
    except Exception as e:
        print(f"t={current_time:.0f} Ha aparecido un error durante el rerouting: {e}")


# Guarda el estado original de un semáforo antes de modificarlo (solo se guarda la primera vez que se interviene ese semáforo)
def backup_tls_if_needed(tls_id: str, tls_backup: dict):
    if tls_id not in tls_backup:
        tls_backup[tls_id] = {
            "program": traci.trafficlight.getProgram(tls_id),
            "phase": traci.trafficlight.getPhase(tls_id),
        }


# Restaura un semáforo al estado que tenía antes de aplicar prioridad
def restore_tls(tls_id: str, tls_backup: dict, current_time: float):
    if tls_id not in tls_backup:
        return
    try:
        old_program = tls_backup[tls_id]["program"]
        old_phase = tls_backup[tls_id]["phase"]
        traci.trafficlight.setProgram(tls_id, old_program)
        traci.trafficlight.setPhase(tls_id, old_phase)
        print(f"t={current_time:.0f} Se restaura el semáforo {tls_id} -> program={old_program} phase={old_phase}")
    except Exception as e:
        print(f"t={current_time:.0f} Ha aparecido un error al restaurar {tls_id}: {e} !!!")

    # Una vez restaurado, se elimina la copia guardada
    tls_backup.pop(tls_id, None)


# Aplica la prioridad de los semáforos al siguiente semáforo del vehículo de emergencia
def handle_tls_priority(current_time: float, tls_backup: dict, metrics: dict, tls_state: dict):
    # Consultar el siguiente semáforo en la ruta del vehículo de emergencia
    tls_list = traci.vehicle.getNextTLS(EMERGENCY_ID)
    speed = traci.vehicle.getSpeed(EMERGENCY_ID)

    # Si no hay próximo semáforo, se restaura el último semáforo intervenido
    if not tls_list:
        active_tls = tls_state.get("active_tls")
        if active_tls is not None:
            restore_tls(active_tls, tls_backup, current_time)
            tls_state["active_tls"] = None
            tls_state["stuck_tls"] = None
            tls_state["stuck_since"] = None
        return

    # Datos del siguiente semáforo en la ruta del vehículo de emergencia
    tls_id = tls_list[0][0]
    tls_link_index = int(tls_list[0][1])
    dist = tls_list[0][2]
    signal_char = str(tls_list[0][3])

    print(f"t={current_time:.0f} El siguiente semáforo es {tls_id} y el vehículo de emergencia está a {dist:.1f} m")
    # Si el vehículo de emergencia cambia de semáforo, se restaura el semáforo anterior
    active_tls = tls_state.get("active_tls")
    
    if active_tls is not None and active_tls != tls_id:
        restore_tls(active_tls, tls_backup, current_time)
        tls_state["active_tls"] = None
        tls_state["stuck_tls"] = None
        tls_state["stuck_since"] = None

    # Si el semáforo está en el periodo de enfriamiento, no se vuelve a intervenir
    cooldown_until = tls_state.get("cooldown_until", {}).get(tls_id, -1)
    if current_time < cooldown_until:
        return

    # Solo se interviene cuando el vehículo de emergencia está dentro de una ventana útil. Muy lejos no hace falta actuar; demasiado cerca puede generar comportamientos inestables!!
    if dist > CONTROL_DISTANCE_M or dist < MIN_CONTROL_DISTANCE_M:
        return

    # Si el movimiento del vehículo de emergencia ya tiene verde, no se modifica el semáforo
    if signal_char in ("G", "g"):
        return

    # Buscar una fase que proporcione verde al movimiento concreto del vehículo de emergencia
    desired_phase = choose_green_phase_for_link(tls_id, tls_link_index)
    if desired_phase is None:
        print(f"t={current_time:.0f} No se encuentra una fase útil para el semáforo {tls_id} link {tls_link_index}")
        return
    # Guardar el estado original del semáforo antes de modificarlo
    backup_tls_if_needed(tls_id, tls_backup)
    current_phase = traci.trafficlight.getPhase(tls_id)

    # Cambiar de fase solo si la fase actual no es ya la deseada
    if current_phase != desired_phase:
        traci.trafficlight.setPhase(tls_id, desired_phase)
        phase = traci.trafficlight.getPhase(tls_id)
        state = traci.trafficlight.getRedYellowGreenState(tls_id)
        print(f"t={current_time:.0f} Se fuerza la fase {desired_phase} en el semáforo {tls_id} -> phase={phase} state={state}")

        # Para las estadísticas, contabilizar cada semáforo intervenido una sola vez
        if tls_id not in metrics["tls_acted_ids"]:
            metrics["tls_acted_ids"].add(tls_id)
            metrics["tls_actions"] += 1
    # Guardar qué semáforo está siendo controlado actualmente
    tls_state["active_tls"] = tls_id

    # Si el vehículo de emergencia queda prácticamente parado junto al semáforo durante varios segundos, se restaura el semáforo y se aplica un periodo de enfriamiento
    if dist <= STUCK_DISTANCE_M and speed <= STUCK_SPEED_M_S:
        if tls_state.get("stuck_tls") != tls_id:
            tls_state["stuck_tls"] = tls_id
            tls_state["stuck_since"] = current_time
        else:
            stuck_since = tls_state.get("stuck_since")
            if stuck_since is not None and current_time - stuck_since >= STUCK_TIME_S:
                print(f"t={current_time:.0f} Cuidado!!!: El vehículo de emergencia está atascado en el semáforo {tls_id}. Se restaura y se aplica un cooldown")
                restore_tls(tls_id, tls_backup, current_time)
                tls_state.setdefault("cooldown_until", {})[tls_id] = current_time + TLS_COOLDOWN_S
                tls_state["active_tls"] = None
                tls_state["stuck_tls"] = None
                tls_state["stuck_since"] = None
    else:
        tls_state["stuck_tls"] = None
        tls_state["stuck_since"] = None


# Guarda en un CSV las métricas principales del viaje del vehículo de emergencia
def format_csv_value(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}".replace(".", ",")
    return value
def save_results(metrics: dict):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = RESULTS_CSV.exists()

    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";") # Se usa ; para separar por columnas en el excell
        # Si el archivo no existe, se crea primero la cabecera
        if not file_exists:
            writer.writerow([
                "mode",
                "from_edge",
                "to_edge",
                "depart_time_s",
                "arrival_time_s",
                "travel_time_s",
                "waiting_time_s",
                "avg_speed_m_s",
                "distance_m",
                "tls_actions",
                "arrived",
                "traffic_data_time"
            ])
        # Cada ejecución añade una nueva fila al CSV
        writer.writerow([
            metrics["mode"],
            metrics["from_edge"],
            metrics["to_edge"],
            format_csv_value(metrics["depart_time"]),
            format_csv_value(metrics["arrival_time"]),
            format_csv_value(metrics["travel_time"]),
            format_csv_value(metrics["waiting_time"]),
            format_csv_value(metrics["avg_speed"]),
            format_csv_value(metrics["distance"]),
            metrics["tls_actions"],
            metrics["arrived"],
            metrics["traffic_data_time"]
        ])


# Inicializa la estructura donde se almacenan las métricas del viaje
def build_metrics() -> dict:
    return {
        "mode": MODE,
        "from_edge": FROM_EDGE,
        "to_edge": TO_EDGE,
        "traffic_data_time": get_traffic_data_time(),
        "depart_time": None,
        "arrival_time": None,
        "travel_time": None,
        "waiting_time": 0.0,
        "avg_speed": 0.0,
        "distance": 0.0,
        "tls_actions": 0,
        "tls_acted_ids": set(),
        "arrived": False,
        "speed_samples": [],
        "route_segments": [],
        "last_route_distance": 0.0,
        "last_route_edge": None,
    }


# Funcionesn auxiliares para registrar la ruta y que el usuario pueda ver el recorrido de forma práctica
def update_route_summary(
    metrics: dict,
    road_id: str,
    total_distance: float
):
    # Distancia avanzada desde el paso anterior
    distance_delta = max(
        0.0,
        total_distance - metrics["last_route_distance"]
    )
    metrics["last_route_distance"] = total_distance
    # No registrar las aristas internas de los cruces
    if not road_id or road_id.startswith(":"):
        return
    # Consultar el nombre únicamente cuando cambia la arista
    if road_id != metrics["last_route_edge"]:
        street_name = traci.edge.getStreetName(road_id).strip()
        # Algunas aristas importadas desde OSM pueden no tener nombre
        if not street_name:
            street_name = f"Edge {road_id}"
        route_segments = metrics["route_segments"]
        # Agrupar aristas consecutivas que pertenezcan
        # a la misma calle
        if (
            not route_segments
            or route_segments[-1]["street"] != street_name
        ):
            route_segments.append({
                "street": street_name,
                "distance_m": 0.0,
            })
        metrics["last_route_edge"] = road_id
    # Acumular la distancia recorrida en el segmento actual
    if metrics["route_segments"]:
        metrics["route_segments"][-1]["distance_m"] += (
            distance_delta
        )
# Muestra un resumen de las calles recorridas
def print_route_summary(metrics: dict):
    route_segments = metrics.get("route_segments", [])
    print()
    print("=== RUTA SEGUIDA POR EL VEHÍCULO DE EMERGENCIA ===")
    if not route_segments:
        print("No se ha podido obtener la ruta recorrida.")
    else:
        for index, segment in enumerate(
            route_segments,
            start=1
        ):
            street = segment["street"]
            distance = segment["distance_m"]
            print(f"{index}. {street}: aproximadamente {distance:.0f} m"
            )
    print("=============================================")

# Calcula las métricas finales antes de guardar los resultados
def finalize_metrics(metrics: dict):
    # Calcular el tiempo total de viaje
    if metrics["depart_time"] is not None and metrics["arrival_time"] is not None:
        metrics["travel_time"] = metrics["arrival_time"] - metrics["depart_time"]
    # Calcular la velocidad media a partir de las muestras tomadas durante el viaje
    if metrics["speed_samples"]:
        metrics["avg_speed"] = sum(metrics["speed_samples"]) / len(metrics["speed_samples"])
    else:
        metrics["avg_speed"] = 0.0
    # Eliminar campos auxiliares que no se escriben directamente en el CSV
    metrics.pop("tls_acted_ids", None)
    metrics.pop("speed_samples", None)


# Muestra por la terminal un resumen de resultados del viaje del vehículo de emergencia
def print_trip_results(metrics: dict):
    print()
    print("=== RESULTADOS DEL VIAJE ===")
    print(f"Modo: {metrics['mode']}")
    print(f"Origen: {metrics['from_edge']}")
    print(f"Destino: {metrics['to_edge']}")
    print(f"Fecha y hora de los datos de tráfico: {metrics['traffic_data_time']}")
    print(f"Tiempo de salida: {metrics['depart_time']} s")
    print(f"Tiempo de llegada: {metrics['arrival_time']} s")
    print(f"Tiempo total de viaje: {metrics['travel_time']} s")
    print(f"Tiempo de espera acumulado: {metrics['waiting_time']:.1f} s")
    print(f"Velocidad media: {metrics['avg_speed']:.2f} m/s")
    print(f"Distancia recorrida: {metrics['distance']:.1f} m")
    print(f"Semáforos intervenidos: {metrics['tls_actions']}")
    print(f"CSV guardado en: {RESULTS_CSV}")
    print("============================")
    print_route_summary(metrics)
    print()


# Función principal de ejecución del sistema de emergencia
def main():
    # Conectar el script Python con la simulación de SUMO ya iniciada
    traci.init(PORT)
    # Duración de cada paso de simulación (en segundos). Se obtiene de la configuración de SUMO
    step_length = traci.simulation.getDeltaT()
    
    # Variables de control de la simulación
    inserted = False
    arrived_and_saved = False
    last_reroute_t = -1
    
    # Estados originales de los semáforos intervenidos
    tls_backup = {}
    
    # Métricas del viaje del vehículo de emergencia
    metrics = build_metrics()

    # Estado interno del sistema de prioridad de los semáforos
    tls_state = {
        "active_tls": None,
        "stuck_tls": None,
        "stuck_since": None,
        "cooldown_until": {},
    }

    # Bucle principal de simulación
    while traci.simulation.getTime() < SIM_END:
        t = traci.simulation.getTime()

        if not inserted and t >= DEPART_TIME:
            try:
                insert_emergency_vehicle(t)
                inserted = True
            except Exception as e:
                print(f"t={t:.0f} No se ha podido insertar el vehículo de emergencia {e} !!!")

        # Si el vehículo de emergencia está en la simulación, se actualizan sus datos
        if inserted and EMERGENCY_ID in traci.vehicle.getIDList():
            # Registrar el instante real en el que el vehículo entra en la red
            if metrics["depart_time"] is None:
                metrics["depart_time"] = traci.vehicle.getDeparture(
                    EMERGENCY_ID
                )
                last_reroute_t = metrics["depart_time"]

                configure_forced_rerouting_test(
                    metrics["depart_time"]
                )
                
            lane_id = traci.vehicle.getLaneID(EMERGENCY_ID)
            road_id = traci.vehicle.getRoadID(EMERGENCY_ID)
            speed = traci.vehicle.getSpeed(EMERGENCY_ID)
            distance = traci.vehicle.getDistance(EMERGENCY_ID)
            update_route_summary(
                metrics,
                road_id,
                distance
            )
            
            print(f"t={t:.0f} El vehículo de emergencia está en edge={road_id} lane={lane_id}")

            # Acumular el tiempo durante el que el vehículo permanece prácticamente detenido
            if speed < 0.1:
                metrics["waiting_time"] += step_length
            metrics["distance"] = distance
            metrics["speed_samples"].append(speed)

            # En modo inteligente se activan el rerouting y la prioridad semafórica
            if MODE == "inteligente":
                if t - last_reroute_t >= REROUTE_EVERY_S:
                    reroute_emergency(t)
                    last_reroute_t = t

                handle_tls_priority(t, tls_backup, metrics, tls_state)

        traci.simulationStep()

        arrived_ids = traci.simulation.getArrivedIDList()
        if inserted and (EMERGENCY_ID in arrived_ids) and not arrived_and_saved:
            metrics["arrival_time"] = traci.simulation.getTime()
            metrics["arrived"] = True

            finalize_metrics(metrics)
            save_results(metrics)
            print_trip_results(metrics)

            arrived_and_saved = True
            break
    
    # Si la simulación termina antes de que el vehículo de emergencia llegue se guardan igualmente los resultados parciales
    if inserted and not arrived_and_saved:
        metrics["arrival_time"] = traci.simulation.getTime()
        metrics["arrived"] = False

        finalize_metrics(metrics)
        save_results(metrics)

        print()
        print("=== RESULTADOS DEL VIAJE (NO A LLEGADO!!) ===")
        print(f"Modo: {metrics['mode']}")
        print(f"Origen: {metrics['from_edge']}")
        print(f"Destino: {metrics['to_edge']}")
        print(f"Tiempo de salida: {metrics['depart_time']} s")
        print(f"Tiempo final simulado: {metrics['arrival_time']} s")
        print(f"Fecha y hora de los datos de tráfico: {metrics['traffic_data_time']}")
        print(f"Tiempo de espera acumulado: {metrics['waiting_time']:.1f} s")
        print(f"Velocidad media: {metrics['avg_speed']:.2f} m/s")
        print(f"Distancia recorrida: {metrics['distance']:.1f} m")
        print(f"Semáforos intervenidos: {metrics['tls_actions']}")
        print(f"CSV guardado en: {RESULTS_CSV}")
        print("=========================================")
        print()

    # Restaurar cualquier semáforo que pudiera quedar modificado al finalizar
    for tls_id in list(tls_backup.keys()):
        restore_tls(tls_id, tls_backup, traci.simulation.getTime())

    # Cerrar la conexión con SUMO
    traci.close()


if __name__ == "__main__":
    main()