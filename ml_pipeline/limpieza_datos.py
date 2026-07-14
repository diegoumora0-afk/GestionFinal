"""
limpieza_datos.py
------------------
Limpia y cruza los datos de MIDAGRI (siembras, cosecha, producción,
rendimiento, precio por región y cultivo) con los datos climáticos de
SENAMHI (Ocucaje y San Camilo, ambas estaciones de la región Ica).

MIDAGRI: 4 archivos, uno por campaña agrícola (2019-20, 2020-21, 2021-22,
         2022-23). Cada archivo tiene 5 hojas resumen: 'siembras', 'cosecha',
         'producción', 'rdto', 'precio'. Cada hoja está organizada en bloques
         repetidos de 26 filas (Nacional + 25 regiones) x ~10 cultivos.

SENAMHI: 2 archivos con series diarias (AÑO, MES, DIA, PRECIPITACION,
         TEMP_MAXIMA, TEMP_MINIMA) de 1965/66 a 2014. Como no hay años en
         común con MIDAGRI (2020-2023), se calcula el promedio climático
         "típico" por mes (climatología), y ese promedio se usa como
         variable de clima para todos los años de MIDAGRI, ya que representa
         el patrón climático habitual de la región Ica.

Salida: data/dataset_limpio.csv y backend/agropredict.db (tabla 'cultivos_ica')
"""

import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuración de rutas
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BACKEND_DIR = BASE_DIR / "backend"

MIDAGRI_FILES = [
    DATA_DIR / "midagri_1.xls",
    DATA_DIR / "midagri_2.xls",
    DATA_DIR / "midagri_3.xlsx",
    DATA_DIR / "midagri_4.xlsx",
]
SENAMHI_FILES = {
    "Ocucaje": DATA_DIR / "senamhi_1.xlsx",
    "San Camilo": DATA_DIR / "senamhi_2.xlsx",
}

REGION_OBJETIVO = "Ica"

# Hojas resumen de MIDAGRI y su nombre de variable / unidad
SHEETS_MIDAGRI = {
    "siembras": ("superficie_sembrada_ha", "ha"),
    "cosecha": ("superficie_cosechada_ha", "ha"),
    "producción": ("produccion_t", "t"),
    "rdto": ("rendimiento_kg_ha", "kg/ha"),
    "precio": ("precio_chacra_soles_kg", "soles/kg"),
}

REGIONES_VALIDAS = {
    "Nacional", "Amazonas", "Áncash", "Apurímac", "Arequipa", "Ayacucho",
    "Cajamarca", "Callao", "Cusco", "Huancavelica", "Huánuco", "Ica",
    "Junín", "La Libertad", "Lambayeque", "Lima", "Lima Metropolitana",
    "Loreto", "Madre de Dios", "Moquegua", "Pasco", "Piura", "Puno",
    "San Martín", "Tacna", "Tumbes", "Ucayali",
}


def extraer_anio_de_titulo(df: pd.DataFrame) -> int:
    """Busca el año en las primeras filas de texto de la hoja (fila 0 o 1)."""
    for fila in range(min(3, len(df))):
        texto = str(df.iloc[fila, 0])
        match_campania = re.search(r"(20\d{2})[-/](\d{2,4})", texto)
        if match_campania:
            segundo = match_campania.group(2)
            if len(segundo) == 2:
                anio = int(match_campania.group(1)[:2] + segundo)
            else:
                anio = int(segundo)
            return anio
        match_simple = re.search(r"(20\d{2})", texto)
        if match_simple:
            return int(match_simple.group(1))
    raise ValueError("No se encontró año en las primeras filas de la hoja")


def parsear_hoja_resumen(path_excel: Path, nombre_hoja: str) -> pd.DataFrame:
    """
    Parsea una hoja resumen de MIDAGRI (siembras/cosecha/producción/rdto/precio).
    Estas hojas están organizadas en bloques repetidos:
        fila 0:        título con el año, ej "... según región, 2020 (kg/ha)"
        fila header:   'Región', cultivo_1, cultivo_2, ... cultivo_10
        26 filas:       Nacional + 25 regiones
        (filas en blanco)
        siguiente bloque...

    Devuelve un DataFrame largo (tidy) con columnas: region, cultivo, valor, anio
    """
    df = pd.read_excel(path_excel, sheet_name=nombre_hoja, header=None)
    anio = extraer_anio_de_titulo(df)

    # localizar todas las filas de encabezado de bloque ("Región" en columna 0)
    header_rows = [
        i for i in range(len(df)) if str(df.iloc[i, 0]).strip() == "Región"
    ]

    registros = []
    for header_row in header_rows:
        cultivos = df.iloc[header_row, 1:].dropna().tolist()
        n_cultivos = len(cultivos)

        # las siguientes filas hasta 26 (Nacional + 25 regiones)
        bloque = df.iloc[header_row + 1 : header_row + 27, : n_cultivos + 1]

        for _, fila in bloque.iterrows():
            region = str(fila.iloc[0]).strip()
            if region not in REGIONES_VALIDAS:
                continue
            for j, cultivo in enumerate(cultivos):
                valor = fila.iloc[j + 1]
                registros.append(
                    {
                        "anio": anio,
                        "region": region,
                        "cultivo": str(cultivo).strip(),
                        "valor": pd.to_numeric(valor, errors="coerce"),
                    }
                )

    return pd.DataFrame(registros)


def cargar_midagri_ica() -> pd.DataFrame:
    """Carga y cruza las 5 hojas resumen de los 4 archivos MIDAGRI,
    filtrando solo la región Ica, y arma una tabla ancha:
    anio | cultivo | superficie_sembrada_ha | superficie_cosechada_ha | ...
    """
    tablas_por_variable = {}

    for nombre_hoja, (nombre_variable, _unidad) in SHEETS_MIDAGRI.items():
        partes = []
        for archivo in MIDAGRI_FILES:
            print(f"  Leyendo {archivo.name} -> hoja '{nombre_hoja}'")
            df_hoja = parsear_hoja_resumen(archivo, nombre_hoja)
            partes.append(df_hoja)

        df_variable = pd.concat(partes, ignore_index=True)
        df_variable = df_variable[df_variable["region"] == REGION_OBJETIVO]
        df_variable = df_variable.rename(columns={"valor": nombre_variable})
        df_variable = df_variable.drop(columns=["region"])
        tablas_por_variable[nombre_variable] = df_variable

    # combinar las 5 variables en una sola tabla ancha (join por anio + cultivo)
    nombres = list(tablas_por_variable.keys())
    resultado = tablas_por_variable[nombres[0]]
    for nombre in nombres[1:]:
        resultado = resultado.merge(
            tablas_por_variable[nombre], on=["anio", "cultivo"], how="outer"
        )

    return resultado


def cargar_climatologia_senamhi():
    """
    Lee los archivos SENAMHI de Ocucaje y San Camilo (series diarias),
    reemplaza los valores -99.9 (dato faltante SENAMHI) por NaN, y calcula
    el promedio climático típico (climatología) por estación:
    precipitación media diaria, temperatura máxima media y temperatura
    mínima media, junto con su versión mensual.
    """
    filas_resumen = []
    filas_mensuales = []

    for estacion, path in SENAMHI_FILES.items():
        print(f"  Leyendo estación {estacion} ({path.name})")
        df = pd.read_excel(path, sheet_name="Hoja1", header=0)
        df = df.rename(
            columns={
                "AÑO": "anio",
                "MES": "mes",
                "DIA": "dia",
                "PRECIPITACION ACUMULADA": "precipitacion_mm",
                "TEMPERATURA MAXIMA": "temp_max_c",
                "TEMPERATURA MINIMA": "temp_min_c",
            }
        )

        # -99.9 es el código de dato faltante de SENAMHI
        for col in ["precipitacion_mm", "temp_max_c", "temp_min_c"]:
            df[col] = df[col].replace(-99.9, np.nan)

        # climatología mensual (promedio de cada mes a través de todos los años)
        clim_mensual = (
            df.groupby("mes")[["precipitacion_mm", "temp_max_c", "temp_min_c"]]
            .mean()
            .reset_index()
        )
        clim_mensual["estacion"] = estacion
        filas_mensuales.append(clim_mensual)

        # climatología anual (promedio general de toda la serie)
        resumen = {
            "estacion": estacion,
            "precipitacion_mm_prom": df["precipitacion_mm"].mean(),
            "temp_max_c_prom": df["temp_max_c"].mean(),
            "temp_min_c_prom": df["temp_min_c"].mean(),
        }
        filas_resumen.append(resumen)

    climatologia_anual = pd.DataFrame(filas_resumen)
    climatologia_mensual = pd.concat(filas_mensuales, ignore_index=True)

    return climatologia_anual, climatologia_mensual


def main():
    print("1) Procesando archivos MIDAGRI (región Ica)...")
    midagri_ica = cargar_midagri_ica()
    print(f"   -> {len(midagri_ica)} filas (anio x cultivo) para Ica")

    print("2) Procesando archivos SENAMHI (Ocucaje y San Camilo)...")
    clim_anual, clim_mensual = cargar_climatologia_senamhi()
    print(clim_anual)

    # Promedio climático de Ica = promedio de las 2 estaciones (Ocucaje + San Camilo)
    clima_ica = {
        "precipitacion_mm_prom_ica": clim_anual["precipitacion_mm_prom"].mean(),
        "temp_max_c_prom_ica": clim_anual["temp_max_c_prom"].mean(),
        "temp_min_c_prom_ica": clim_anual["temp_min_c_prom"].mean(),
    }
    print("3) Climatología típica combinada de Ica:", clima_ica)

    print("4) Cruzando MIDAGRI (Ica) con climatología típica...")
    dataset_final = midagri_ica.copy()
    for col, val in clima_ica.items():
        dataset_final[col] = val

    # limpieza final: quitar cultivos sin ningún dato numérico útil
    columnas_numericas = [
        "superficie_sembrada_ha",
        "superficie_cosechada_ha",
        "produccion_t",
        "rendimiento_kg_ha",
        "precio_chacra_soles_kg",
    ]
    dataset_final = dataset_final.dropna(subset=columnas_numericas, how="all")
    dataset_final = dataset_final.sort_values(["cultivo", "anio"]).reset_index(drop=True)

    print(f"5) Dataset final: {dataset_final.shape[0]} filas, {dataset_final.shape[1]} columnas")

    # ---- Guardar CSV ----
    csv_out = DATA_DIR / "dataset_limpio.csv"
    dataset_final.to_csv(csv_out, index=False, encoding="utf-8-sig")
    print(f"6) CSV guardado en: {csv_out}")

    # ---- Guardar climatología mensual también (útil para análisis exploratorio) ----
    clim_mensual_out = DATA_DIR / "climatologia_mensual_ica.csv"
    clim_mensual.to_csv(clim_mensual_out, index=False, encoding="utf-8-sig")
    print(f"7) Climatología mensual guardada en: {clim_mensual_out}")

    # ---- Guardar en SQLite ----
    BACKEND_DIR.mkdir(exist_ok=True)
    db_path = BACKEND_DIR / "agropredict.db"
    conn = sqlite3.connect(db_path)
    dataset_final.to_sql("cultivos_ica", conn, if_exists="replace", index=False)
    clim_mensual.to_sql("climatologia_mensual_ica", conn, if_exists="replace", index=False)
    conn.close()
    print(f"8) Base de datos SQLite actualizada en: {db_path}")

    print("\nListo. Vista previa del dataset final:")
    print(dataset_final.head(15).to_string())


if __name__ == "__main__":
    main()
