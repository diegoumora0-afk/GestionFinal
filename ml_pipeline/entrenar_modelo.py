"""
entrenar_modelo.py
-------------------
Entrena el modelo híbrido (tendencia lineal + Random Forest sobre
residuos) para predecir, dado un cultivo y un año, el rendimiento
(kg/ha), producción (t) y precio en chacra (soles/kg) en la región Ica.

A diferencia de un Random Forest puro, este modelo SÍ puede extrapolar
razonablemente hacia años futuros (2024, 2025, 2026...), porque la
tendencia lineal por cultivo captura la dirección general (sube/baja),
mientras el Random Forest ajusta desviaciones no lineales.
"""

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

from modelo_hibrido import ModeloHibrido

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BACKEND_DIR = BASE_DIR / "backend"

CSV_ENTRADA = DATA_DIR / "dataset_limpio.csv"
MODELO_SALIDA = BACKEND_DIR / "modelo.pkl"

VARIABLES_OBJETIVO = ["rendimiento_kg_ha", "produccion_t", "precio_chacra_soles_kg"]
VARIABLES_ENTRADA_CATEGORICAS = ["cultivo"]
VARIABLES_ENTRADA_NUMERICAS = [
    "anio",
    "precipitacion_mm_prom_ica",
    "temp_max_c_prom_ica",
    "temp_min_c_prom_ica",
]


def cargar_datos() -> pd.DataFrame:
    df = pd.read_csv(CSV_ENTRADA)
    columnas_necesarias = (
        VARIABLES_ENTRADA_CATEGORICAS + VARIABLES_ENTRADA_NUMERICAS + VARIABLES_OBJETIVO
    )
    df = df[columnas_necesarias].copy()
    df = df.dropna(subset=VARIABLES_OBJETIVO)
    return df


def main():
    print("1) Cargando dataset limpio...")
    df = cargar_datos()
    print(f"   -> {len(df)} filas utilizables para entrenamiento")

    print("2) Separando train/test (80/20) para evaluar desempeño...")
    df_train, df_test = train_test_split(df, test_size=0.2, random_state=42)

    print("3) Entrenando modelo híbrido de evaluación (con datos de train)...")
    modelo_eval = ModeloHibrido(
        VARIABLES_OBJETIVO, VARIABLES_ENTRADA_CATEGORICAS, VARIABLES_ENTRADA_NUMERICAS
    )
    modelo_eval.fit(df_train)

    print("4) Evaluando en el conjunto de prueba...")
    metricas = {v: {"errores": [], "reales": []} for v in VARIABLES_OBJETIVO}
    for _, fila in df_test.iterrows():
        valores_numericos = {c: fila[c] for c in VARIABLES_ENTRADA_NUMERICAS if c != "anio"}
        prediccion = modelo_eval.predict_fila(fila["cultivo"], fila["anio"], valores_numericos)
        for variable in VARIABLES_OBJETIVO:
            metricas[variable]["errores"].append(prediccion[variable])
            metricas[variable]["reales"].append(fila[variable])

    metricas_finales = {}
    for variable in VARIABLES_OBJETIVO:
        mae = mean_absolute_error(metricas[variable]["reales"], metricas[variable]["errores"])
        r2 = r2_score(metricas[variable]["reales"], metricas[variable]["errores"])
        metricas_finales[variable] = {"MAE": round(mae, 2), "R2": round(r2, 3)}
        print(f"   {variable}: MAE={mae:.2f}  R2={r2:.3f}")

    print("5) Re-entrenando con TODOS los datos (para producción)...")
    modelo_final = ModeloHibrido(
        VARIABLES_OBJETIVO, VARIABLES_ENTRADA_CATEGORICAS, VARIABLES_ENTRADA_NUMERICAS
    )
    modelo_final.fit(df)

    print("6) Guardando modelo y metadatos...")
    cultivos_validos = sorted(df["cultivo"].unique().tolist())
    anios_disponibles = sorted(df["anio"].unique().tolist())

    paquete_modelo = {
        "modelo": modelo_final,
        "variables_objetivo": VARIABLES_OBJETIVO,
        "cultivos_validos": cultivos_validos,
        "anios_disponibles": anios_disponibles,
        "metricas_test": metricas_finales,
        "clima_default": {
            "precipitacion_mm_prom_ica": float(df["precipitacion_mm_prom_ica"].iloc[0]),
            "temp_max_c_prom_ica": float(df["temp_max_c_prom_ica"].iloc[0]),
            "temp_min_c_prom_ica": float(df["temp_min_c_prom_ica"].iloc[0]),
        },
    }

    BACKEND_DIR.mkdir(exist_ok=True)
    joblib.dump(paquete_modelo, MODELO_SALIDA)
    print(f"   -> Modelo guardado en: {MODELO_SALIDA}")

    resumen_json = BACKEND_DIR / "modelo_metricas.json"
    with open(resumen_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "metricas_test": metricas_finales,
                "n_filas_entrenamiento": len(df),
                "n_cultivos": len(cultivos_validos),
                "anios_disponibles": anios_disponibles,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"   -> Métricas guardadas en: {resumen_json}")

    print("\nListo. El modelo híbrido ya puede predecir rendimiento, producción")
    print("y precio dado un cultivo y un año (incluso años futuros), para Ica.")


if __name__ == "__main__":
    main()