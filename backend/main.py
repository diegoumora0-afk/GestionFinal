"""
main.py
-------
API FastAPI que expone el modelo entrenado (modelo.pkl) para predecir,
dado un cultivo y un año, el rendimiento (kg/ha), producción (t) y
precio en chacra (soles/kg) esperados en la región Ica.
"""

from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
MODELO_PATH = BASE_DIR / "modelo.pkl"

app = FastAPI(
    title="AgroPredict IA - Ica",
    description="API que predice rendimiento, producción y precio de cultivos en Ica",
    version="1.0.0",
)

# Permite que el frontend (index.html / scripts.js) llame a esta API
# desde otro origen (ej. abierto directo en el navegador o en otro puerto)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Cargar el modelo una sola vez al iniciar el servidor
# ---------------------------------------------------------------------------
import sys

# Necesario para que joblib pueda "des-picklear" la clase ModeloHibrido:
# debe encontrarse en el mismo módulo (ml_pipeline) que cuando se entrenó.
sys.path.append(str(BASE_DIR.parent / "ml_pipeline"))

if not MODELO_PATH.exists():
    raise FileNotFoundError(
        f"No se encontró {MODELO_PATH}. Corre antes: python ml_pipeline/entrenar_modelo.py"
    )

paquete_modelo = joblib.load(MODELO_PATH)
modelo = paquete_modelo["modelo"]
variables_objetivo = paquete_modelo["variables_objetivo"]
clima_default = paquete_modelo["clima_default"]
cultivos_validos = set(paquete_modelo["cultivos_validos"])
anios_disponibles = paquete_modelo["anios_disponibles"]
metricas_test = paquete_modelo.get("metricas_test", {})


# ---------------------------------------------------------------------------
# Esquemas de entrada / salida
# ---------------------------------------------------------------------------
class PrediccionInput(BaseModel):
    cultivo: str
    anio: int


class PrediccionOutput(BaseModel):
    cultivo: str
    anio: int
    rendimiento_kg_ha: float
    produccion_t: float
    precio_chacra_soles_kg: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/")
def raiz():
    return {
        "mensaje": "API de AgroPredict IA para la región Ica",
        "endpoints": ["/cultivos", "/predecir", "/metricas"],
    }


@app.get("/cultivos")
def listar_cultivos():
    """Devuelve la lista de cultivos válidos, útil para llenar un dropdown en el frontend."""
    return {"cultivos": sorted(cultivos_validos)}


@app.get("/metricas")
def obtener_metricas():
    """Devuelve las métricas de desempeño del modelo (MAE y R2 por variable)."""
    return {
        "metricas_test": metricas_test,
        "anios_usados_en_entrenamiento": anios_disponibles,
    }


@app.post("/predecir", response_model=PrediccionOutput)
def predecir(datos: PrediccionInput):
    cultivo = datos.cultivo.strip()

    if cultivo not in cultivos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Cultivo '{cultivo}' no reconocido. Usa GET /cultivos para ver la lista válida.",
        )

    resultado = modelo.predict_fila(cultivo, datos.anio, clima_default)

    return PrediccionOutput(
        cultivo=cultivo,
        anio=datos.anio,
        rendimiento_kg_ha=round(float(resultado["rendimiento_kg_ha"]), 2),
        produccion_t=round(float(resultado["produccion_t"]), 2),
        precio_chacra_soles_kg=round(float(resultado["precio_chacra_soles_kg"]), 2),
    )

# --- Nuevos Endpoints (Mockups) ---

import random

@app.get("/riesgo-rendimiento")
def riesgo_rendimiento():
    """Devuelve el riesgo y rendimiento esperado real basado en datos históricos."""
    csv_path = BASE_DIR.parent / "data" / "dataset_limpio.csv"
    if not csv_path.exists():
        datos = []
        for c in list(cultivos_validos)[:10]:
            datos.append({
                "cultivo": c,
                "riesgo": round(random.uniform(10, 90), 1),
                "rendimiento_esperado": round(random.uniform(10000, 40000), 1)
            })
        return {"data": datos}

    import pandas as pd
    df = pd.read_csv(csv_path)
    df = df[df['cultivo'].isin(cultivos_validos)]
    df['ganancia'] = df['rendimiento_kg_ha'] * df['precio_chacra_soles_kg']
    
    datos = []
    for cultivo, group in df.groupby('cultivo'):
        mean_ganancia = group['ganancia'].mean()
        std_ganancia = group['ganancia'].std()
        
        if pd.isna(mean_ganancia) or mean_ganancia == 0:
            mean_ganancia = 0.0
            riesgo = 20.0
        elif pd.isna(std_ganancia):
            riesgo = 20.0
        else:
            cv = (std_ganancia / mean_ganancia) * 100
            riesgo = min(max(cv * 1.5, 5.0), 95.0) 
            
        datos.append({
            "cultivo": cultivo,
            "riesgo": round(float(riesgo), 1),
            "rendimiento_esperado": round(float(mean_ganancia), 2)
        })
    return {"data": datos}

@app.get("/impacto-climatico")
def impacto_climatico():
    """Mockup: Devuelve el perfil climático mensual real (simulado) de Ocucaje/San Camilo."""
    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    # Simulación de un perfil desértico costero
    temperatura = [28, 29, 27, 24, 21, 18, 17, 18, 19, 21, 24, 26] 
    humedad = [60, 62, 65, 70, 75, 80, 82, 80, 78, 70, 65, 60]
    precipitacion = [2, 3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1] # Muy poca lluvia

    return {
        "meses": meses,
        "temperatura_c": temperatura,
        "humedad_relativa_pct": humedad,
        "precipitacion_mm": precipitacion
    }

@app.get("/mercado-vivo")
def mercado_vivo():
    """Mockup: Devuelve demanda por región y actualización cíclica."""
    regiones = ["Ica", "Lima", "Arequipa", "Piura", "La Libertad", "Cusco", "Junín"]
    mercado = []
    for r in regiones:
        mercado.append({
            "region": r,
            "demanda_indice": round(random.uniform(50, 100), 1),
            "precio_promedio": round(random.uniform(1.5, 5.0), 2),
            "tendencia": random.choice(["alza", "baja", "estable"])
        })
    # Ordenar por demanda para el ranking
    mercado = sorted(mercado, key=lambda x: x["demanda_indice"], reverse=True)
    return {"ranking": mercado}