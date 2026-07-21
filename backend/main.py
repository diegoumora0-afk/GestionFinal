"""
main.py
-------
API FastAPI que expone el modelo mensual entrenado (modelo_mensual.pkl)
para predecir, dado un cultivo, año y mes, el rendimiento (kg/ha),
producción (t) y precio en chacra (soles/kg) esperados en la región Ica.
"""

from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
MODELO_PATH = BASE_DIR / "modelo_mensual.pkl"
DATA_DIR = BASE_DIR.parent / "data"

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
        f"No se encontró {MODELO_PATH}. Corre antes: python ml_pipeline/entrenar_modelo_mensual.py"
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
    mes: int = 1  # Mes calendario (1-12), default enero


class PrediccionOutput(BaseModel):
    cultivo: str
    anio: int
    mes: int
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
    mes = max(1, min(12, datos.mes))  # Clamp entre 1 y 12

    if cultivo not in cultivos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Cultivo '{cultivo}' no reconocido. Usa GET /cultivos para ver la lista válida.",
        )

    # Obtener clima específico del mes desde la climatología
    clima_mes = dict(clima_default)  # copia base
    if hasattr(modelo, '_tiempo_continuo'):  # modelo mensual
        # Cargar climatología mensual real
        clim_csv = DATA_DIR / "climatologia_mensual_ica.csv"
        if clim_csv.exists():
            import pandas as pd
            clim = pd.read_csv(clim_csv)
            clim_mes_df = clim[clim['mes'] == mes]
            if not clim_mes_df.empty:
                clima_mes = {
                    'precipitacion_mm': float(clim_mes_df['precipitacion_mm'].mean()),
                    'temp_max_c': float(clim_mes_df['temp_max_c'].mean()),
                    'temp_min_c': float(clim_mes_df['temp_min_c'].mean()),
                }

    resultado = modelo.predict_fila(cultivo, datos.anio, mes, clima_mes)

    return PrediccionOutput(
        cultivo=cultivo,
        anio=datos.anio,
        mes=mes,
        rendimiento_kg_ha=round(float(resultado["rendimiento_kg_ha"]), 2),
        produccion_t=round(float(resultado["produccion_t"]), 2),
        precio_chacra_soles_kg=round(float(resultado["precio_chacra_soles_kg"]), 2),
    )

# --- Nuevos Endpoints (Mockups) ---

import random

@app.get("/riesgo-rendimiento")
def riesgo_rendimiento():
    """Calcula riesgo (CV de ganancia mensual) y rendimiento esperado usando datos mensuales."""
    import pandas as pd
    import numpy as np

    # Preferir dataset mensual, fallback al anual
    csv_mensual = DATA_DIR / "dataset_limpio_mensual.csv"
    csv_anual = DATA_DIR / "dataset_limpio.csv"
    csv_path = csv_mensual if csv_mensual.exists() else csv_anual

    if not csv_path.exists():
        return {"data": []}

    df = pd.read_csv(csv_path)

    # Calcular ganancia = producción * precio (valor bruto mensual)
    df['ganancia'] = df['produccion_t'].fillna(0) * df['precio_chacra_soles_kg'].fillna(0)

    datos = []
    for cultivo, group in df.groupby('cultivo'):
        # Filtrar filas con ganancia real
        g = group[group['ganancia'] > 0]
        if len(g) < 2:
            continue

        mean_ganancia = g['ganancia'].mean()
        std_ganancia = g['ganancia'].std()
        mean_precio = g['precio_chacra_soles_kg'].mean()
        prod_total = g['produccion_t'].sum()
        grupo = g['grupo'].iloc[0] if 'grupo' in g.columns else 'A'
        n_meses_activos = len(g)

        if pd.isna(mean_ganancia) or mean_ganancia <= 0:
            continue

        # Riesgo = Coeficiente de Variación (%) acotado
        if pd.isna(std_ganancia) or std_ganancia == 0:
            riesgo = 5.0
        else:
            cv = (std_ganancia / mean_ganancia) * 100
            riesgo = min(max(cv, 5.0), 95.0)

        datos.append({
            "cultivo": cultivo,
            "riesgo": round(float(riesgo), 1),
            "rendimiento_esperado": round(float(mean_ganancia), 2),
            "precio_promedio": round(float(mean_precio), 2),
            "produccion_total": round(float(prod_total), 1),
            "grupo": grupo,
            "meses_activos": int(n_meses_activos),
        })

    return {"data": datos}

@app.get("/impacto-climatico")
def impacto_climatico():
    """Devuelve el perfil climático mensual real de Ica (SENAMHI: Ocucaje + San Camilo)."""
    meses_nombres = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    
    clim_csv = DATA_DIR / "climatologia_mensual_ica.csv"
    if clim_csv.exists():
        import pandas as pd
        clim = pd.read_csv(clim_csv)
        # Promediar las dos estaciones por mes
        clim_prom = clim.groupby('mes')[['precipitacion_mm', 'temp_max_c', 'temp_min_c']].mean().reset_index()
        clim_prom = clim_prom.sort_values('mes')
        
        temperatura = [round(float(v), 1) for v in clim_prom['temp_max_c']]
        temp_min = [round(float(v), 1) for v in clim_prom['temp_min_c']]
        precipitacion = [round(float(v * 30), 2) for v in clim_prom['precipitacion_mm']]  # diario -> mensual
    else:
        # Fallback simulado
        temperatura = [28, 29, 27, 24, 21, 18, 17, 18, 19, 21, 24, 26]
        temp_min = [17, 18, 17, 15, 12, 10, 10, 10, 10, 11, 13, 15]
        precipitacion = [2, 3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1]

    return {
        "meses": meses_nombres,
        "temperatura_c": temperatura,
        "temp_min_c": temp_min,
        "precipitacion_mm": precipitacion
    }
