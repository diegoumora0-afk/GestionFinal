"""
modelo_hibrido_mensual.py
--------------------------
Versión mensual del modelo híbrido: tendencia lineal por cultivo +
Random Forest sobre residuos.

Diferencias con modelo_hibrido.py (anual):
  - Usa `anio + mes/12` como variable temporal continua para la tendencia
  - Soporta `mes` como variable numérica adicional
  - Para rendimiento, entrena solo con filas del Grupo A que tienen ese dato
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

VARIABLES_NO_NEGATIVAS = ["rendimiento_kg_ha", "produccion_t", "precio_chacra_soles_kg"]


class ModeloHibridoMensual:
    def __init__(self, variables_objetivo, variables_categoricas, variables_numericas):
        self.variables_objetivo = variables_objetivo
        self.variables_categoricas = variables_categoricas
        self.variables_numericas = variables_numericas
        self.tendencias = {}  # {cultivo: {variable: (pendiente, intercepto)}}
        self.rf_pipeline = None

    def _tiempo_continuo(self, anio, mes):
        """Convierte año + mes en una variable temporal continua."""
        return anio + (mes - 1) / 12.0

    def _ajustar_tendencias(self, df: pd.DataFrame):
        """Ajusta una regresión lineal simple (tiempo_continuo -> valor) por cada
        combinación cultivo x variable objetivo."""
        for cultivo, grupo in df.groupby("cultivo"):
            self.tendencias[cultivo] = {}
            for variable in self.variables_objetivo:
                sub = grupo.dropna(subset=[variable])
                if len(sub) >= 2:
                    t = sub.apply(lambda f: self._tiempo_continuo(f["anio"], f["mes"]), axis=1)
                    pendiente, intercepto = np.polyfit(t, sub[variable], 1)
                else:
                    pendiente = 0.0
                    intercepto = sub[variable].iloc[0] if len(sub) == 1 else 0.0
                self.tendencias[cultivo][variable] = (pendiente, intercepto)

    def _predecir_tendencia(self, cultivo: str, anio: int, mes: int, variable: str) -> float:
        if cultivo not in self.tendencias:
            return 0.0
        if variable not in self.tendencias[cultivo]:
            return 0.0
        pendiente, intercepto = self.tendencias[cultivo][variable]
        t = self._tiempo_continuo(anio, mes)
        return pendiente * t + intercepto

    def fit(self, df: pd.DataFrame):
        df = df.copy()

        print("   Ajustando tendencias lineales por cultivo (con mes)...")
        self._ajustar_tendencias(df)

        # calcular residuos
        for variable in self.variables_objetivo:
            df[f"residuo_{variable}"] = df.apply(
                lambda fila: (
                    fila[variable]
                    - self._predecir_tendencia(fila["cultivo"], fila["anio"], fila["mes"], variable)
                )
                if pd.notna(fila[variable])
                else np.nan,
                axis=1,
            )

        # Para el entrenamiento del RF, rellenar NaN en residuos con 0
        # (las variables objetivo con NaN no contribuyen al error)
        residuo_cols = [f"residuo_{v}" for v in self.variables_objetivo]
        df[residuo_cols] = df[residuo_cols].fillna(0)

        print("   Entrenando Random Forest sobre los residuos...")
        preprocesador = ColumnTransformer(
            transformers=[
                ("cultivo_onehot", OneHotEncoder(handle_unknown="ignore"), self.variables_categoricas),
            ],
            remainder="passthrough",
        )
        modelo_base = RandomForestRegressor(
            n_estimators=300, min_samples_leaf=2, random_state=42, n_jobs=-1
        )
        self.rf_pipeline = Pipeline(
            steps=[
                ("preprocesamiento", preprocesador),
                ("modelo", MultiOutputRegressor(modelo_base)),
            ]
        )

        X = df[self.variables_categoricas + self.variables_numericas]
        y_residuos = df[residuo_cols]
        self.rf_pipeline.fit(X, y_residuos)

        return self

    def predict_fila(self, cultivo: str, anio: int, mes: int, valores_numericos: dict) -> dict:
        """Predice los valores para UNA fila (cultivo, año, mes, clima)."""
        fila = pd.DataFrame([{"cultivo": cultivo, "anio": anio, "mes": mes, **valores_numericos}])
        residuos_predichos = self.rf_pipeline.predict(
            fila[self.variables_categoricas + self.variables_numericas]
        )[0]

        resultado = {}
        for i, variable in enumerate(self.variables_objetivo):
            tendencia = self._predecir_tendencia(cultivo, anio, mes, variable)
            valor_final = tendencia + residuos_predichos[i]
            if variable in VARIABLES_NO_NEGATIVAS:
                valor_final = max(0.0, valor_final)
            resultado[variable] = valor_final

        return resultado
