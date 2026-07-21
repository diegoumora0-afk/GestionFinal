"""
limpieza_datos_mensual.py
--------------------------
Expande el dataset de granularidad anual a mensual, usando las hojas
individuales de cada cultivo dentro de los archivos MIDAGRI.

Cada hoja de cultivo contiene "Cuadros" con datos mensuales desglosados
por región. Este script:
  1. Clasifica cada cultivo en Grupo A (transitorio, 5 cuadros) o
     Grupo B (permanente/semipermanente, 2-3 cuadros).
  2. Extrae la fila de Ica de cada cuadro mensual.
  3. Mapea los meses al mes calendario real (ej: siembra usa Ago→Jul).
  4. Cruza con climatología mensual de SENAMHI (Ocucaje + San Camilo).
  5. Genera data/dataset_limpio_mensual.csv

Deja intacto el dataset_limpio.csv anual existente.
"""

import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuración de rutas
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

MIDAGRI_FILES = [
    (DATA_DIR / "midagri_1.xls", "2019-20"),
    (DATA_DIR / "midagri_2.xls", "2020-21"),
    (DATA_DIR / "midagri_3.xlsx", "2021-22"),
    (DATA_DIR / "midagri_4.xlsx", "2022-23"),
]

CLIMATOLOGIA_CSV = DATA_DIR / "climatologia_mensual_ica.csv"
REGION_OBJETIVO = "Ica"

# Hojas que NO son cultivos individuales (son resumen o categoría)
HOJAS_EXCLUIR = {
    "Indice", "siembras", "cosecha", "producción", "rdto", "precio",
    "TRANSITORIOS", "PERMANENTES", "SEMIPERMAMENTES", "PASTOS FORRAJEROS",
    "Tabla",
}

# Mapeo de abreviatura de mes a número de mes calendario
MES_A_NUM = {
    "Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Ago": 8, "Set": 9, "Oct": 10, "Nov": 11, "Dic": 12,
}

# Palabras clave para identificar cada tipo de cuadro
TIPO_CUADRO = {
    "siembra": "Superficie sembrada",
    "cosecha": "Superficie cosechada",
    "produccion": "Producción mensual",
    "rendimiento": "Rendimiento promedio mensual",
    "precio": "Precio promedio en chacra mensual",
}


def encontrar_cuadros(df: pd.DataFrame) -> list:
    """
    Recorre todas las celdas del DataFrame buscando títulos de 'Cuadro'.
    Devuelve una lista de dicts con info de cada cuadro encontrado.
    """
    cuadros = []
    for i in range(len(df)):
        for j in range(min(len(df.columns), 21)):
            val = str(df.iloc[i, j]).strip() if pd.notna(df.iloc[i, j]) else ""
            if "Cuadro" not in val:
                continue
            if "mensual" not in val.lower() and "chacra de" not in val.lower():
                # Es un cuadro resumen anual, no mensual - lo saltamos
                if "Producción," in val and "superficie" in val.lower():
                    continue  # Cuadro resumen (Grupo B tiene uno de estos)
                continue

            # Determinar tipo de cuadro
            tipo = None
            for clave, patron in TIPO_CUADRO.items():
                if patron.lower() in val.lower():
                    tipo = clave
                    break

            # Extraer nombre del cultivo
            nombre = None
            m = re.search(r"mensual de (.+?),?\s*según", val, re.IGNORECASE)
            if m:
                nombre = m.group(1).strip()

            cuadros.append({
                "fila_titulo": i,
                "col_titulo": j,
                "titulo": val,
                "tipo": tipo,
                "nombre_cultivo": nombre,
            })

    return cuadros


def extraer_anio_de_cuadro(titulo: str) -> Optional[int]:
    """Extrae el año de un título de cuadro como 'Año: 2022' o 'Campaña agrícola: 2021/2022'."""
    # Buscar "Campaña agrícola: YYYY/YYYY"
    m = re.search(r"[Cc]ampaña\s+agrícola:\s*(20\d{2})[/-](\d{2,4})", titulo)
    if m:
        segundo = m.group(2)
        if len(segundo) == 2:
            return int(m.group(1)[:2] + segundo)
        return int(segundo)
    # Buscar "Año: YYYY"
    m = re.search(r"[Aa]ño:\s*(20\d{2})", titulo)
    if m:
        return int(m.group(1))
    # Buscar cualquier año 20XX
    m = re.search(r"(20\d{2})", titulo)
    if m:
        return int(m.group(1))
    return None


def extraer_fila_ica(df: pd.DataFrame, fila_titulo: int) -> Optional[dict]:
    """
    Dado un DataFrame y la fila del título de un cuadro, busca la fila de
    headers (con 'Región') y luego la fila de 'Ica', extrayendo los 12
    valores mensuales con sus meses reales.
    """
    # Buscar fila de headers (la que contiene 'Región' en columna 0)
    fila_header = None
    for i in range(fila_titulo + 1, min(fila_titulo + 5, len(df))):
        val = str(df.iloc[i, 0]).strip() if pd.notna(df.iloc[i, 0]) else ""
        if val == "Región":
            fila_header = i
            break

    if fila_header is None:
        return None

    # Leer encabezados de meses (columnas 2 en adelante, col 1 es Total/Promedio)
    meses_header = []
    for j in range(2, min(len(df.columns), 14)):
        val = str(df.iloc[fila_header, j]).strip() if pd.notna(df.iloc[fila_header, j]) else ""
        if val in MES_A_NUM:
            meses_header.append((j, MES_A_NUM[val]))

    if not meses_header:
        return None

    # Buscar la fila de Ica (dentro de las siguientes ~30 filas)
    for i in range(fila_header + 1, min(fila_header + 30, len(df))):
        val = str(df.iloc[i, 0]).strip() if pd.notna(df.iloc[i, 0]) else ""
        if val == REGION_OBJETIVO:
            valores = {}
            for col_idx, mes_num in meses_header:
                v = df.iloc[i, col_idx]
                valores[mes_num] = pd.to_numeric(v, errors="coerce")
            return valores

    return None


def determinar_anio_siembra(mes_num: int, anio_campania: int) -> int:
    """
    Para siembras (campaña agrícola Ago→Jul): los meses Ago-Dic pertenecen
    al primer año de la campaña, los meses Ene-Jul al segundo año.
    Ej: Campaña 2021/2022 -> Ago 2021, Sep 2021, ..., Dic 2021, Ene 2022, ..., Jul 2022
    """
    # anio_campania es el segundo año (ej: 2022 para campaña 2021/2022)
    if mes_num >= 8:  # Ago-Dic pertenecen al año anterior
        return anio_campania - 1
    return anio_campania


def procesar_hoja_cultivo(path_excel: Path, nombre_hoja: str) -> list:
    """
    Procesa una hoja individual de cultivo y extrae los datos mensuales
    de la fila de Ica para cada cuadro encontrado.
    Devuelve una lista de registros (dicts).
    """
    df = pd.read_excel(path_excel, sheet_name=nombre_hoja, header=None)
    cuadros = encontrar_cuadros(df)

    if not cuadros:
        return []

    # Determinar nombre canónico del cultivo y grupo
    nombre_cultivo = cuadros[0].get("nombre_cultivo") or nombre_hoja
    tipos_encontrados = {c["tipo"] for c in cuadros if c["tipo"]}
    tiene_siembra = "siembra" in tipos_encontrados
    grupo = "A" if tiene_siembra else "B"

    # Extraer datos mensuales por tipo de cuadro
    datos_por_tipo = {}
    for cuadro in cuadros:
        tipo = cuadro["tipo"]
        if tipo is None:
            continue

        anio = extraer_anio_de_cuadro(cuadro["titulo"])
        if anio is None:
            continue

        valores_ica = extraer_fila_ica(df, cuadro["fila_titulo"])
        if valores_ica is None:
            continue

        datos_por_tipo[tipo] = {"anio": anio, "valores": valores_ica}

    if not datos_por_tipo:
        return []

    # Construir registros mensuales
    registros = []

    # Determinar los meses disponibles desde producción o precio (año calendario)
    ref_tipo = "produccion" if "produccion" in datos_por_tipo else "precio"
    if ref_tipo not in datos_por_tipo:
        return []

    anio_calendario = datos_por_tipo[ref_tipo]["anio"]

    for mes_num in range(1, 13):
        fila = {
            "cultivo": nombre_cultivo,
            "anio": anio_calendario,
            "mes": mes_num,
            "grupo": grupo,
            "superficie_sembrada_ha": None,
            "superficie_cosechada_ha": None,
            "produccion_t": None,
            "rendimiento_kg_ha": None,
            "precio_chacra_soles_kg": None,
        }

        # Producción
        if "produccion" in datos_por_tipo:
            fila["produccion_t"] = datos_por_tipo["produccion"]["valores"].get(mes_num)

        # Precio
        if "precio" in datos_por_tipo:
            fila["precio_chacra_soles_kg"] = datos_por_tipo["precio"]["valores"].get(mes_num)

        # Solo para Grupo A:
        if grupo == "A":
            if "cosecha" in datos_por_tipo:
                fila["superficie_cosechada_ha"] = datos_por_tipo["cosecha"]["valores"].get(mes_num)

            if "rendimiento" in datos_por_tipo:
                fila["rendimiento_kg_ha"] = datos_por_tipo["rendimiento"]["valores"].get(mes_num)

            if "siembra" in datos_por_tipo:
                # Los meses de siembra van por campaña agrícola
                # El mes_num aquí se refiere al mes calendario, necesitamos encontrar
                # si ese mes aparece en los datos de siembra
                fila["superficie_sembrada_ha"] = datos_por_tipo["siembra"]["valores"].get(mes_num)

        # Verificar que la fila tiene al menos un dato útil (producción o precio > 0)
        tiene_dato = False
        for col in ["produccion_t", "precio_chacra_soles_kg"]:
            v = fila[col]
            if v is not None and not np.isnan(v) and v > 0:
                tiene_dato = True
                break

        if tiene_dato:
            registros.append(fila)

    return registros


def cargar_climatologia_mensual() -> pd.DataFrame:
    """
    Lee la climatología mensual de Ica (Ocucaje + San Camilo) y promedia
    ambas estaciones para obtener un valor único por mes.
    """
    df = pd.read_csv(CLIMATOLOGIA_CSV)
    # Promediar las dos estaciones por mes
    clim = (
        df.groupby("mes")[["precipitacion_mm", "temp_max_c", "temp_min_c"]]
        .mean()
        .reset_index()
    )
    return clim


def main():
    print("=" * 60)
    print("EXPANSIÓN DE DATASET: ANUAL → MENSUAL")
    print("=" * 60)

    # 1. Cargar climatología mensual
    print("\n1) Cargando climatología mensual de Ica (SENAMHI)...")
    clim_mensual = cargar_climatologia_mensual()
    print(clim_mensual.to_string(index=False))

    # 2. Procesar cada archivo MIDAGRI
    todos_los_registros = []

    for path_excel, campania in MIDAGRI_FILES:
        print(f"\n2) Procesando {path_excel.name} (campaña {campania})...")
        xls = pd.ExcelFile(path_excel)

        hojas_cultivo = [h for h in xls.sheet_names if h not in HOJAS_EXCLUIR]
        print(f"   -> {len(hojas_cultivo)} hojas de cultivos individuales")

        procesados = 0
        errores = 0
        for hoja in hojas_cultivo:
            try:
                registros = procesar_hoja_cultivo(path_excel, hoja)
                todos_los_registros.extend(registros)
                if registros:
                    procesados += 1
            except Exception as e:
                errores += 1
                print(f"   [ERROR] Hoja '{hoja}': {e}")

        print(f"   -> {procesados} cultivos con datos mensuales de Ica, {errores} errores")

    # 3. Construir DataFrame
    print(f"\n3) Construyendo dataset mensual...")
    df = pd.DataFrame(todos_los_registros)

    if df.empty:
        print("   [ERROR] No se extrajeron datos. Revisar estructura de archivos MIDAGRI.")
        return

    print(f"   -> {len(df)} filas antes de limpiar")

    # 4. Cruzar con climatología mensual
    print("4) Cruzando con climatología mensual de Ica...")
    df = df.merge(clim_mensual, on="mes", how="left")

    # 5. Ordenar y limpiar
    df = df.sort_values(["cultivo", "anio", "mes"]).reset_index(drop=True)

    # Estadísticas
    n_cultivos = df["cultivo"].nunique()
    n_grupo_a = df[df["grupo"] == "A"]["cultivo"].nunique()
    n_grupo_b = df[df["grupo"] == "B"]["cultivo"].nunique()
    n_anios = df["anio"].nunique()

    print(f"\n5) Estadísticas del dataset mensual:")
    print(f"   -> {len(df)} filas totales")
    print(f"   -> {n_cultivos} cultivos ({n_grupo_a} Grupo A, {n_grupo_b} Grupo B)")
    print(f"   -> {n_anios} años: {sorted(df['anio'].unique())}")
    print(f"   -> Columnas: {list(df.columns)}")

    # 6. Guardar CSV
    csv_out = DATA_DIR / "dataset_limpio_mensual.csv"
    df.to_csv(csv_out, index=False, encoding="utf-8-sig")
    print(f"\n6) Dataset guardado en: {csv_out}")

    # 7. Mostrar vista previa
    print("\nVista previa (primeras 20 filas):")
    print(df.head(20).to_string(index=False))

    # 8. Comparación con dataset anual
    csv_anual = DATA_DIR / "dataset_limpio.csv"
    if csv_anual.exists():
        df_anual = pd.read_csv(csv_anual)
        print(f"\nComparación con dataset anual:")
        print(f"   Anual:  {len(df_anual)} filas, {df_anual['cultivo'].nunique()} cultivos")
        print(f"   Mensual: {len(df)} filas, {n_cultivos} cultivos")
        print(f"   Factor de expansión: {len(df) / len(df_anual):.1f}x")


if __name__ == "__main__":
    main()
