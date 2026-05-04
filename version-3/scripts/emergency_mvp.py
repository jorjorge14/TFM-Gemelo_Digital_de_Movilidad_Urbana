import traci

# Puerto usado para conectar Python con SUMO mediante TraCI. SUMO debe haberse iniciado previamente con el mismo puerto
PORT = 8813

# Identificador del vehículo de emergencia dentro de la simulación
EMERGENCY_ID = "EM1"

# Instante de simulación en el que se introduce el vehiculo de emergencia
DEPART_TIME = 60

# Distancia máxima al semáforo a partir de la cual se activa la prioridad
CONTROL_DISTANCE_M = 100.0  

def main():
    
    # Conectar el script Python con la simulación de SUMO ya iniciada
    traci.init(PORT)

    # Variable para asegurar que la ambulancia solo se inserta una vez
    inserted = False

    # Ejecutar la simulación hasta el segundo 1800
    while traci.simulation.getTime() < 1800:
        t = traci.simulation.getTime()

        # Insertar la ambulancia cuando se alcanza el instante definido
        if not inserted and t >= DEPART_TIME:
            vehs = traci.vehicle.getIDList()
            
            # Se toma la ruta de un vehículo ya existente como ruta inicial. Esto permite introducir rápidamente el vehiculo de emergencia en una ruta válida sin definir manualmente un recorrido nuevo
            if vehs:
                route = traci.vehicle.getRoute(vehs[0])

                traci.vehicle.add(EMERGENCY_ID, routeID="", typeID="emergency", depart=str(int(t)))
                traci.vehicle.setRoute(EMERGENCY_ID, route)

                inserted = True
                print(f"t={t:.0f} inserto la ambulancia {EMERGENCY_ID}")

        # Una vez insertada la ambulancia, se consulta su posición y su próximo semáforo
        if inserted and EMERGENCY_ID in traci.vehicle.getIDList():
            lane_id = traci.vehicle.getLaneID(EMERGENCY_ID)
            print(f"t={t:.0f} voy por el carril {lane_id}")

            # Obtener información sobre el siguiente semáforo que encontrará la ambulancia
            tls = traci.vehicle.getNextTLS(EMERGENCY_ID)
            if tls:
                tls_id = tls[0][0]
                dist = tls[0][2]  # distancia en metros hasta el semafóro

                print(f"t={t:.0f} el siguiente TLS es {tls_id} y estoy a {dist:.1f} m")

                # Si la ambulancia está suficientemente cerca del cruce, se fuerza la fase 0 del semáforo.
                # En esta versión MVP se asume que la fase 0 favorece el paso del vehículo de emergencia!!
                if dist <= CONTROL_DISTANCE_M:
                    traci.trafficlight.setPhase(tls_id, 0)
                    
                    # Se consulta la fase aplicada para comprobar el cambio
                    phase = traci.trafficlight.getPhase(tls_id)
                    state = traci.trafficlight.getRedYellowGreenState(tls_id)
                    print(f"t={t:.0f} fuerzo fase 0 en {tls_id} -> phase={phase} state={state}")

        # Avanzar un paso de simulación
        traci.simulationStep()

    # Cerrar la conexión con SUMO al finalizar
    traci.close()

if __name__ == "__main__":
    main()