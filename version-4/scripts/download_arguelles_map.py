import osmnx as ox
from shapely.geometry import Polygon

# Permite exportar correctamente la red descargada a formato OSM XML. SUMO trabaja bien a partir de archivos .osm, que después pueden convertirse a una red .net.xml mediante netconvert
ox.settings.all_oneway = True

# Coordenadas que delimitan la zona de estudio en Argüelles.
# Cada punto se define como (longitud, latitud), siguiendo el formato usado por OSMnx
zona_coords = [
    (-3.725290, 40.432520),
    (-3.719366, 40.435115),
    (-3.716179, 40.430848),
    (-3.713025, 40.426596),
    (-3.710715, 40.423434),
    (-3.713325, 40.421769),
    (-3.716485, 40.424959),
    (-3.718561, 40.425441),
]

# Creación del polígono que representa el área geográfica de trabajo. Este polígono se usa para recortar la red viaria descargada desde OpenStreetMap.
polygon = Polygon(zona_coords)

# Descarga de la red viaria contenida dentro del polígono.
#   network_type="drive" limita la red a vías aptas para circulación de vehículos.
#   simplify=False mantiene la geometría original con más detalle
G = ox.graph_from_polygon(
    polygon,
    network_type="drive",
    simplify=False
)

# Guardado de la red descargada en formato OSM. Este archivo será la entrada para generar la red de SUMO de la zona.
ox.save_graph_xml(G, filepath="arguelles.osm")

print("Red OSM recortada correctamente")