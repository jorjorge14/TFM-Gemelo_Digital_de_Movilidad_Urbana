import pandas as pd
import sumolib

# Rutas de entrada y salida.
# NET_PATH apunta a la red SUMO de Argüelles
# SENSORS_CSV contiene los sensores filtrados previamente en Colab
# OUT_CSV será el archivo final con cada sensor asociado a una edge de SUMO
NET_PATH = r"..\mapas\arguelles.net.xml"
SENSORS_CSV = r"..\datos_arguelles\sensores_zona_azul.csv"   
OUT_CSV = r"..\datos_arguelles\sensores_mapeados.csv"

# Cargar la red de SUMO para poder consultar sus edges y coordenadas internas
net = sumolib.net.readNet(NET_PATH)

# Cargar el CSV de sensores
df = pd.read_csv(SENSORS_CSV)

# Asegurar que las columnas numéricas tienen el formato correcto
df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
df["intensidad"] = pd.to_numeric(df["intensidad"], errors="coerce").fillna(0)

# Convertir coordenadas geográficas lon/lat a coordenadas internas de SUMO. Esto es necesario porque la red SUMO no trabaja directamente en WGS84.
def closest_edge_id(lon, lat):
    x, y = net.convertLonLat2XY(lon, lat)
    
    # Buscar el edge más cercano al punto del sensor en un radio de 50 metros. Se toma la primera coincidencia, que corresponde al edge más próximo
    edge, dist = net.getNeighboringEdges(x, y, r=50)[:1][0]  
    return edge.getID(), dist

edge_ids = []
edge_dists = []

# Asociar cada sensor al edge de SUMO más cercano. Si no se encuentra ningun edge cercano, se guarda None.
for _, r in df.iterrows():
    try:
        eid, dist = closest_edge_id(r["lon"], r["lat"])
    except Exception:
        eid, dist = None, None
    edge_ids.append(eid)
    edge_dists.append(dist)

# Añadir al DataFrame el identificador de edge y la distancia al sensor.
df["edge_id"] = edge_ids
df["edge_dist_m"] = edge_dists

# Eliminar sensores que no han podido asociarse a ningun edge.
df_ok = df.dropna(subset=["edge_id"]).copy()

# Guardar el resultado para usarlo después en la generación de rutas.
df_ok.to_csv(OUT_CSV, index=False)
print("Sensores mapeados guardados en:", OUT_CSV)
print("Mapeados:", len(df_ok), " / Total:", len(df))
print(df_ok[["idelem","descripcion","intensidad","edge_id","edge_dist_m"]].head(10))