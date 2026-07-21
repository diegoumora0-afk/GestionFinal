"""
entrenar_modelo_mensual.py
----------------------------
Entrena el modelo híbrido mensual y compara su desempeño (R²) contra
el modelo anual existente.

Usa dataset_limpio_mensual.csv como entrada.
Guarda modelo_mensual.pkl sin sobrescribir modelo.pkl.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

from modelo_hibrido_mensual import ModeloHibridoMensual

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BACKEND_DIR = BASE_DIR / "backend"

CSV_ENTRADA = DATA_DIR / "dataset_limpio_mensual.csv"
MODELO_SALIDA = BACKEND_DIR / "modelo_mensual.pkl"

VARIABLES_OBJETIVO = ["rendimiento_kg_ha", "produccion_t", "precio_chacra_soles_kg"]
VARIABLES_ENTRADA_CATEGORICAS = ["cultivo"]
VARIABLES_ENTRADA_NUMERICAS = [
    "anio",
    "mes",
    "precipitacion_mm",
    "temp_max_c",
    "temp_min_c",
]


def cargar_datos() -> pd.DataFrame:
    df = pd.read_csv(CSV_ENTRADA)
    columnas_necesarias = (
        VARIABLES_ENTRADA_CATEGORICAS + VARIABLES_ENTRADA_NUMERICAS + VARIABLES_OBJETIVO
        + ["grupo"]
    )
    # Verificar que todas las columnas existen
    disponibles = set(df.columns)
    faltantes = set(columnas_necesarias) - disponibles
    if faltantes:
        print(f"   [WARN] Columnas faltantes: {faltantes}")
        columnas_necesarias = [c for c in columnas_necesarias if c in disponibles]

    df = df[columnas_necesarias].copy()

    # Rellenar NaN en clima con el promedio (no debería haber, pero por seguridad)
    for col in ["precipitacion_mm", "temp_max_c", "temp_min_c"]:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].mean())

    return df


def main():
    print("=" * 60)
    print("ENTRENAMIENTO DE MODELO HÍBRIDO MENSUAL")
    print("=" * 60)

    print("\n1) Cargando dataset mensual...")
    df = cargar_datos()
    print(f"   -> {len(df)} filas totales")
    print(f"   -> {df['cultivo'].nunique()} cultivos")
    print(f"   -> Grupo A: {df[df['grupo'] == 'A']['cultivo'].nunique()} cultivos")
    print(f"   -> Grupo B: {df[df['grupo'] == 'B']['cultivo'].nunique()} cultivos")

    # Para rendimiento, solo usar filas que tienen dato (Grupo A principalmente)
    # Para producción y precio, usar todas las filas
    print("\n2) Preparando datos de entrenamiento...")

    # Filtrar filas que tengan al menos producción o precio
    df_train_full = df.dropna(subset=["produccion_t", "precio_chacra_soles_kg"], how="all")
    print(f"   -> {len(df_train_full)} filas con producción o precio")

    # Para rendimiento, marcar NaN en Grupo B (no tienen rendimiento)
    df_train_full.loc[
        df_train_full["rendimiento_kg_ha"].isna(), "rendimiento_kg_ha"
    ] = np.nan

    print(f"   -> {df_train_full['rendimiento_kg_ha'].notna().sum()} filas con rendimiento")

    # Separar train/test
    print("\n3) Separando train/test (80/20)...")
    df_train, df_test = train_test_split(df_train_full, test_size=0.2, random_state=42)

    # Entrenar modelo de evaluación
    print("\n4) Entrenando modelo híbrido mensual (evaluación)...")
    modelo_eval = ModeloHibridoMensual(
        VARIABLES_OBJETIVO, VARIABLES_ENTRADA_CATEGORICAS, VARIABLES_ENTRADA_NUMERICAS
    )
    modelo_eval.fit(df_train)

    # Evaluar
    print("\n5) Evaluando en conjunto de prueba...")
    metricas = {v: {"pred": [], "real": []} for v in VARIABLES_OBJETIVO}

    for _, fila in df_test.iterrows():
        valores_numericos = {
            c: fila[c] for c in VARIABLES_ENTRADA_NUMERICAS if c not in ("anio", "mes")
        }
        prediccion = modelo_eval.predict_fila(
            fila["cultivo"], int(fila["anio"]), int(fila["mes"]), valores_numericos
        )
        for variable in VARIABLES_OBJETIVO:
            if pd.notna(fila[variable]):
                metricas[variable]["pred"].append(prediccion[variable])
                metricas[variable]["real"].append(fila[variable])

    metricas_finales = {}
    print("\n   Resultados del modelo MENSUAL:")
    for variable in VARIABLES_OBJETIVO:
        if metricas[variable]["real"]:
            mae = mean_absolute_error(metricas[variable]["real"], metricas[variable]["pred"])
            r2 = r2_score(metricas[variable]["real"], metricas[variable]["pred"])
            metricas_finales[variable] = {"MAE": round(mae, 2), "R2": round(r2, 3)}
            print(f"   {variable}: MAE={mae:.2f}  R2={r2:.3f} ({len(metricas[variable]['real'])} muestras)")
        else:
            metricas_finales[variable] = {"MAE": None, "R2": None}
            print(f"   {variable}: Sin datos de prueba")

    # Comparar con modelo anual
    metricas_anual_path = BACKEND_DIR / "modelo_metricas.json"
    if metricas_anual_path.exists():
        with open(metricas_anual_path) as f:
            metricas_anual = json.load(f)
        print("\n   Comparación con modelo ANUAL:")
        print(f"   {'Variable':<30} {'R² Anual':>10} {'R² Mensual':>12} {'Δ':>8}")
        print(f"   {'-'*60}")
        for variable in VARIABLES_OBJETIVO:
            r2_anual = metricas_anual.get("metricas_test", {}).get(variable, {}).get("R2", "N/A")
            r2_mensual = metricas_finales.get(variable, {}).get("R2", "N/A")
            if isinstance(r2_anual, (int, float)) and isinstance(r2_mensual, (int, float)):
                delta = r2_mensual - r2_anual
                signo = "+" if delta >= 0 else ""
                print(f"   {variable:<30} {r2_anual:>10.3f} {r2_mensual:>12.3f} {signo}{delta:>7.3f}")
            else:
                print(f"   {variable:<30} {str(r2_anual):>10} {str(r2_mensual):>12}")

    # Re-entrenar con TODOS los datos
    print("\n6) Re-entrenando con TODOS los datos (producción)...")
    modelo_final = ModeloHibridoMensual(
        VARIABLES_OBJETIVO, VARIABLES_ENTRADA_CATEGORICAS, VARIABLES_ENTRADA_NUMERICAS
    )
    modelo_final.fit(df_train_full)

    # Guardar
    print("\n7) Guardando modelo y metadatos...")
    cultivos_validos = sorted(df_train_full["cultivo"].unique().tolist())
    anios_disponibles = sorted(df_train_full["anio"].unique().tolist())

    # Calcular clima default (promedio de toda la climatología)
    clima_default = {}
    for col in ["precipitacion_mm", "temp_max_c", "temp_min_c"]:
        if col in df_train_full.columns:
            clima_default[col] = float(df_train_full[col].mean())

    paquete_modelo = {
        "modelo": modelo_final,
        "variables_objetivo": VARIABLES_OBJETIVO,
        "cultivos_validos": cultivos_validos,
        "anios_disponibles": anios_disponibles,
        "metricas_test": metricas_finales,
        "clima_default": clima_default,
        "tipo": "mensual",
    }

    BACKEND_DIR.mkdir(exist_ok=True)
    joblib.dump(paquete_modelo, MODELO_SALIDA)
    print(f"   -> Modelo guardado en: {MODELO_SALIDA}")

    resumen_json = BACKEND_DIR / "modelo_mensual_metricas.json"
    with open(resumen_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "metricas_test": metricas_finales,
                "n_filas_entrenamiento": len(df_train_full),
                "n_cultivos": len(cultivos_validos),
                "anios_disponibles": anios_disponibles,
                "tipo": "mensual",
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"   -> Métricas guardadas en: {resumen_json}")

    print("\nListo. El modelo híbrido mensual puede predecir rendimiento, producción")
    print("y precio dado un cultivo, año y mes (incluso futuros), para Ica.")


if __name__ == "__main__":
    main()
