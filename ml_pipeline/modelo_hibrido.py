"""
modelo_hibrido.py
-------------------
Modelo híbrido: tendencia lineal por cultivo + Random Forest sobre los
residuos. La tendencia lineal SÍ puede extrapolar hacia años futuros
(sigue la pendiente histórica), mientras que el Random Forest corrige
esa tendencia con patrones no lineales que dependan del cultivo y del
clima.

predicción_final = tendencia_lineal(cultivo, año) + correccion_RF(cultivo, año, clima)
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# Variables que nunca deben ser negativas (tienen sentido físico limitado a >= 0)
VARIABLES_NO_NEGATIVAS = ["rendimiento_kg_ha", "produccion_t", "precio_chacra_soles_kg"]


class ModeloHibrido:
    def __init__(self, variables_objetivo, variables_categoricas, variables_numericas):
        self.variables_objetivo = variables_objetivo
        self.variables_categoricas = variables_categoricas
        self.variables_numericas = variables_numericas
        self.tendencias = {}  # {cultivo: {variable: (pendiente, intercepto)}}
        self.rf_pipeline = None

    def _ajustar_tendencias(self, df: pd.DataFrame):
        """Ajusta una regresión lineal simple (año -> valor) por cada
        combinación cultivo x variable objetivo."""
        for cultivo, grupo in df.groupby("cultivo"):
            self.tendencias[cultivo] = {}
            for variable in self.variables_objetivo:
                sub = grupo.dropna(subset=[variable])
                if len(sub) >= 2:
                    pendiente, intercepto = np.polyfit(sub["anio"], sub[variable], 1)
                else:
                    # con 1 solo dato no se puede ajustar una pendiente: se
                    # asume tendencia plana (pendiente 0) igual al valor conocido
                    pendiente = 0.0
                    intercepto = sub[variable].iloc[0] if len(sub) == 1 else 0.0
                self.tendencias[cultivo][variable] = (pendiente, intercepto)

    def _predecir_tendencia(self, cultivo: str, anio: int, variable: str) -> float:
        if cultivo not in self.tendencias:
            return 0.0
        pendiente, intercepto = self.tendencias[cultivo][variable]
        return pendiente * anio + intercepto

    def fit(self, df: pd.DataFrame):
        df = df.copy()

        print("   Ajustando tendencias lineales por cultivo...")
        self._ajustar_tendencias(df)

        # calcular residuos: lo que la tendencia lineal NO logra explicar
        for variable in self.variables_objetivo:
            df[f"residuo_{variable}"] = df.apply(
                lambda fila: fila[variable]
                - self._predecir_tendencia(fila["cultivo"], fila["anio"], variable),
                axis=1,
            )

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
        y_residuos = df[[f"residuo_{v}" for v in self.variables_objetivo]]
        self.rf_pipeline.fit(X, y_residuos)

        return self

    def predict_fila(self, cultivo: str, anio: int, valores_numericos: dict) -> dict:
        """Predice los valores para UNA fila (cultivo, año, clima)."""
        fila = pd.DataFrame([{"cultivo": cultivo, "anio": anio, **valores_numericos}])
        residuos_predichos = self.rf_pipeline.predict(
            fila[self.variables_categoricas + self.variables_numericas]
        )[0]

        resultado = {}
        for i, variable in enumerate(self.variables_objetivo):
            tendencia = self._predecir_tendencia(cultivo, anio, variable)
            valor_final = tendencia + residuos_predichos[i]
            if variable in VARIABLES_NO_NEGATIVAS:
                valor_final = max(0.0, valor_final)
            resultado[variable] = valor_final

        return resultado