from pathlib import Path
import sumolib

# -------------------------
# Rutas del proyecto
# -------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
NET_PATH = BASE_DIR / "mapas" / "arguelles.net.xml"

def main():
    # Obtener todas las edges de la red
    net = sumolib.net.readNet(str(NET_PATH))
    edges = net.getEdges()

    print(f"Total de edges: {len(edges)}")
    print()

    # Mostrar por pantalla los identificadores de las edges. Se ignoran las edges internas, que en SUMO empiezan por ":"
    for edge in edges:
        edge_id = edge.getID()
        if not edge_id.startswith(":"):
            print(edge_id)

if __name__ == "__main__":
    main()