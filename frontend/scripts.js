const API_BASE_URL = "http://127.0.0.1:8000";

// Elementos Predicción
const inputSearchCultivo = document.getElementById("input-search-cultivo");
const dropdownCultivos = document.getElementById("dropdown-cultivos");
const selectCultivoHidden = document.getElementById("select-cultivo");
const inputAnio = document.getElementById("input-anio");
const formPrediccion = document.getElementById("form-prediccion");
const estadoMensaje = document.getElementById("estado-mensaje");

const filaResultados = document.getElementById("fila-resultados");
const valorRendimiento = document.getElementById("valor-rendimiento");
const valorProduccion = document.getElementById("valor-produccion");
const valorPrecio = document.getElementById("valor-precio");

let cultivosDisponibles = [];

// Gráficos Globales
let chartRendimiento = null;
let chartProduccion = null;
let chartPrecio = null;
let chartRiesgo = null;
let chartClima = null;

// Colores de la paleta Glassmorphism
const colors = {
  green: { base: "rgba(16, 185, 129, 0.4)", border: "#10b981", hover: "rgba(16, 185, 129, 0.8)" },
  blue: { base: "rgba(59, 130, 246, 0.4)", border: "#3b82f6", hover: "rgba(59, 130, 246, 0.8)" },
  yellow: { base: "rgba(251, 191, 36, 0.4)", border: "#fbbf24", hover: "rgba(251, 191, 36, 0.8)" },
  white: { base: "rgba(255, 255, 255, 0.6)", border: "#ffffff", hover: "rgba(255, 255, 255, 0.9)" }
};

Chart.defaults.color = "#94a3b8"; // Texto secundario
Chart.defaults.font.family = "'Inter', sans-serif";

// -----------------------------------------------------------------------
// 1. Selector de Cultivos con Buscador
// -----------------------------------------------------------------------
async function cargarCultivos() {
  try {
    const respuesta = await fetch(`${API_BASE_URL}/cultivos`);
    if (!respuesta.ok) throw new Error("No se pudo conectar");
    const datos = await respuesta.json();
    cultivosDisponibles = datos.cultivos;
    renderizarOpciones(cultivosDisponibles);
  } catch (error) {
    estadoMensaje.innerHTML = `<span class="text-danger"><i class="fa-solid fa-triangle-exclamation"></i> Error cargando cultivos. Asegúrate de iniciar el backend.</span>`;
  }
}

function renderizarOpciones(lista) {
  dropdownCultivos.innerHTML = "";
  if (lista.length === 0) {
    dropdownCultivos.innerHTML = `<div class="p-2 text-muted small">No se encontraron resultados</div>`;
    return;
  }
  lista.forEach(cultivo => {
    const div = document.createElement("div");
    div.className = "searchable-select-option";
    div.textContent = cultivo;
    div.onclick = () => {
      selectCultivoHidden.value = cultivo;
      inputSearchCultivo.value = cultivo;
      dropdownCultivos.classList.remove("show");
    };
    dropdownCultivos.appendChild(div);
  });
}

inputSearchCultivo.addEventListener("input", (e) => {
  const term = e.target.value.toLowerCase();
  const filtrados = cultivosDisponibles.filter(c => c.toLowerCase().includes(term));
  renderizarOpciones(filtrados);
  dropdownCultivos.classList.add("show");
});

inputSearchCultivo.addEventListener("focus", () => {
  renderizarOpciones(cultivosDisponibles);
  dropdownCultivos.classList.add("show");
});

// Cerrar dropdown al hacer click afuera
document.addEventListener("click", (e) => {
  if (!e.target.closest('.searchable-select-container')) {
    dropdownCultivos.classList.remove("show");
  }
});

// -----------------------------------------------------------------------
// 2. Lógica Predicción (Vista 1)
// -----------------------------------------------------------------------
formPrediccion.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const cultivo = selectCultivoHidden.value;
  const anioObjetivo = parseInt(inputAnio.value, 10);

  if (!cultivo) {
    estadoMensaje.innerHTML = `<span class="text-warning">Por favor selecciona un cultivo.</span>`;
    return;
  }

  estadoMensaje.innerHTML = `<span class="text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Generando predicción...</span>`;
  filaResultados.style.display = "none";

  const aniosHistoricos = [2020, 2021, 2022, 2023];
  const anios = aniosHistoricos.includes(anioObjetivo) ? aniosHistoricos : [...aniosHistoricos, anioObjetivo];

  try {
    const reqs = anios.map(a => fetch(`${API_BASE_URL}/predecir`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cultivo, anio: a })
    }).then(r => r.json()));
    
    const resultados = await Promise.all(reqs);
    const main = resultados.find((r) => r.anio === anioObjetivo);

    valorRendimiento.textContent = main.rendimiento_kg_ha.toLocaleString("es-PE");
    valorProduccion.textContent = main.produccion_t.toLocaleString("es-PE");
    valorPrecio.textContent = main.precio_chacra_soles_kg.toLocaleString("es-PE");

    filaResultados.style.display = "flex";
    document.getElementById("card-grafico-rendimiento").style.display = "block";
    document.getElementById("card-grafico-produccion").style.display = "block";
    document.getElementById("card-grafico-precio").style.display = "block";

    const labels = anios.map(String);
    const isTarget = (i) => anios[i] === anioObjetivo;

    chartRendimiento = crearGraficoBarras(chartRendimiento, "chart-rendimiento", labels, resultados.map(r => r.rendimiento_kg_ha), colors.green, isTarget);
    chartProduccion = crearGraficoLineasArea(chartProduccion, "chart-produccion", labels, resultados.map(r => r.produccion_t), colors.blue);
    chartPrecio = crearGraficoLineas(chartPrecio, "chart-precio", labels, resultados.map(r => r.precio_chacra_soles_kg), colors.yellow);

    estadoMensaje.innerHTML = `<span class="text-success-custom"><i class="fa-solid fa-check-circle"></i> Predicción exitosa</span>`;
  } catch (error) {
    estadoMensaje.innerHTML = `<span class="text-danger">Error: ${error.message}</span>`;
  }
});

// Helpers de Gráficos (Evitamos pasteles/circulares, usamos barras/líneas)
function crearGraficoBarras(chartObj, canvasId, labels, data, colorObj, highlightCondition) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  if (chartObj) chartObj.destroy();
  return new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: labels.map((_, i) => highlightCondition && highlightCondition(i) ? colorObj.hover : colorObj.base),
        borderColor: colorObj.border,
        borderWidth: 1,
        borderRadius: 4,
        hoverBackgroundColor: colorObj.hover
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" } },
        x: { grid: { display: false } }
      }
    }
  });
}

function crearGraficoLineas(chartObj, canvasId, labels, data, colorObj) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  if (chartObj) chartObj.destroy();
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        data,
        borderColor: colorObj.border,
        backgroundColor: colorObj.base,
        borderWidth: 3,
        pointBackgroundColor: colorObj.hover,
        pointRadius: 5,
        pointHoverRadius: 8,
        tension: 0.3 // curva suave
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" } },
        x: { grid: { display: false } }
      }
    }
  });
}

function crearGraficoLineasArea(chartObj, canvasId, labels, data, colorObj) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  if (chartObj) chartObj.destroy();
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        data,
        borderColor: colorObj.border,
        backgroundColor: colorObj.base,
        fill: true,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 6,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: "rgba(255,255,255,0.05)" } },
        x: { grid: { display: false } }
      }
    }
  });
}


// -----------------------------------------------------------------------
// 3. Vistas Adicionales (Carga diferida al clickear tabs)
// -----------------------------------------------------------------------
document.getElementById('tab-riesgo').addEventListener('shown.bs.tab', async () => {
  if (chartRiesgo) return; // Ya se cargó
  try {
      const res = await fetch(`${API_BASE_URL}/riesgo-rendimiento`);
      // Leemos como texto y reemplazamos NaN por null para evitar crasheos en JSON.parse
      const texto = await res.text();
      const data = JSON.parse(texto.replace(/NaN/g, 'null'));
      
      // Filtrar cultivos sin datos reales (null o 0) para evitar que Math.max falle
      const puntos = data.data
        .filter(d => d.rendimiento_esperado > 0 && d.rendimiento_esperado !== null)
        .map(d => ({ x: d.riesgo || 0, y: d.rendimiento_esperado, cultivo: d.cultivo }));
      
      // Si por alguna razón no hay puntos, usamos 50000 por defecto
      const maxGanancia = puntos.length > 0 ? (Math.max(...puntos.map(p => p.y)) * 1.1) : 50000;
      const maxRiesgo = 100;
      const mitadRiesgo = 50;
      const mitadGanancia = maxGanancia / 2;

      const ctx = document.getElementById("chart-riesgo-rendimiento").getContext("2d");
      chartRiesgo = new Chart(ctx, {
        type: 'scatter',
        data: {
          datasets: [{
            label: 'Cultivos',
            data: puntos,
            backgroundColor: colors.white.base,
            borderColor: colors.white.border,
            pointRadius: 8,
            pointHoverRadius: 12
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.raw.cultivo} (Riesgo: ${ctx.raw.x.toFixed(1)}%, Ganancia: S/ ${ctx.raw.y.toLocaleString('es-PE', {maximumFractionDigits: 0})})`
              }
            },
            annotation: {
              annotations: {
                boxIdeal: {
                  type: 'box', xMin: 0, xMax: mitadRiesgo, yMin: mitadGanancia, yMax: maxGanancia,
                  backgroundColor: 'rgba(16, 185, 129, 0.1)', borderWidth: 0,
                  label: { display: true, content: 'Ideal', position: 'start', color: 'rgba(16, 185, 129, 0.8)' }
                },
                boxArriesgado: {
                  type: 'box', xMin: mitadRiesgo, xMax: maxRiesgo, yMin: mitadGanancia, yMax: maxGanancia,
                  backgroundColor: 'rgba(251, 191, 36, 0.1)', borderWidth: 0,
                  label: { display: true, content: 'Rentable pero Arriesgado', position: 'start', color: 'rgba(251, 191, 36, 0.8)' }
                },
                boxSeguro: {
                  type: 'box', xMin: 0, xMax: mitadRiesgo, yMin: 0, yMax: mitadGanancia,
                  backgroundColor: 'rgba(59, 130, 246, 0.1)', borderWidth: 0,
                  label: { display: true, content: 'Seguro pero poca ganancia', position: 'start', color: 'rgba(59, 130, 246, 0.8)' }
                },
                boxPeligro: {
                  type: 'box', xMin: mitadRiesgo, xMax: maxRiesgo, yMin: 0, yMax: mitadGanancia,
                  backgroundColor: 'rgba(239, 68, 68, 0.1)', borderWidth: 0,
                  label: { display: true, content: 'Peligro (Evitar)', position: 'start', color: 'rgba(239, 68, 68, 0.8)' }
                },
                lineX: { type: 'line', xMin: mitadRiesgo, xMax: mitadRiesgo, borderColor: 'rgba(255,255,255,0.2)', borderWidth: 2, borderDash: [5, 5] },
                lineY: { type: 'line', yMin: mitadGanancia, yMax: mitadGanancia, borderColor: 'rgba(255,255,255,0.2)', borderWidth: 2, borderDash: [5, 5] }
              }
            }
          },
          scales: {
            x: { min: 0, max: maxRiesgo, title: { display: true, text: 'Nivel de Riesgo (%)' }, grid: { color: "rgba(255,255,255,0.05)" } },
            y: { min: 0, max: maxGanancia, title: { display: true, text: 'Ganancia Esperada (S/)' }, grid: { color: "rgba(255,255,255,0.05)" } }
          }
        }
      });
    } catch(e) { console.error("Error cargando riesgo:", e); }
});

document.getElementById('tab-clima').addEventListener('shown.bs.tab', async () => {
  if (chartClima) return; // Ya se cargó
  try {
    const res = await fetch(`${API_BASE_URL}/impacto-climatico`);
    const data = await res.json();
    
    const ctx = document.getElementById("chart-clima").getContext("2d");
    chartClima = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.meses,
        datasets: [
          {
            type: 'line',
            label: 'Temperatura (°C)',
            data: data.temperatura_c,
            borderColor: colors.yellow.border,
            backgroundColor: colors.yellow.hover,
            borderWidth: 3,
            tension: 0.4,
            yAxisID: 'y'
          },
          {
            type: 'bar',
            label: 'Humedad (%)',
            data: data.humedad_relativa_pct,
            backgroundColor: colors.blue.base,
            borderRadius: 4,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          y: { type: 'linear', display: true, position: 'left', grid: { color: "rgba(255,255,255,0.05)" } },
          y1: { type: 'linear', display: true, position: 'right', grid: { display: false } },
          x: { grid: { display: false } }
        }
      }
    });
  } catch(e) { console.error("Error cargando clima:", e); }
});

// -----------------------------------------------------------------------
// 4. Mercado en Vivo (Actualización continua)
// -----------------------------------------------------------------------
let mercadoInterval;
let mapaMercado = null;
let mapaMarcadores = [];

async function actualizarMercado() {
  try {
    const res = await fetch(`${API_BASE_URL}/mercado-vivo`);
    const data = await res.json();
    const container = document.getElementById('ranking-container');
    container.innerHTML = "";
    
    // Coordenadas simuladas aproximadas para regiones de Perú
    const coordenadasRegiones = {
      "Ica": [-14.0667, -75.7333],
      "Lima": [-12.0464, -77.0428],
      "Arequipa": [-16.4090, -71.5375],
      "Piura": [-5.1945, -80.6328],
      "La Libertad": [-8.1091, -79.0215]
    };

    // Inicializar mapa si no existe
    if (!mapaMercado) {
      const mapDiv = document.getElementById('map-container');
      mapDiv.innerHTML = ""; // Limpiar placeholder
      
      mapaMercado = L.map('map-container').setView([-9.1900, -75.0152], 5); // Centro de Perú
      
      // Tile layer oscuro que combina con el glassmorphism
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CartoDB</a>',
        subdomains: 'abcd',
        maxZoom: 19
      }).addTo(mapaMercado);
      
      // Forzar recálculo de tamaño una vez que se muestra
      setTimeout(() => { mapaMercado.invalidateSize(); }, 500);
    } else {
      // Limpiar marcadores viejos
      mapaMarcadores.forEach(m => mapaMercado.removeLayer(m));
      mapaMarcadores = [];
    }

    data.ranking.forEach((item, index) => {
      const div = document.createElement('div');
      div.className = 'ranking-item';
      
      let icon = '<i class="fa-solid fa-minus text-muted"></i>';
      let pinColor = '#94a3b8'; // gris por defecto
      
      if(item.tendencia === 'alza') {
        icon = '<i class="fa-solid fa-arrow-trend-up text-success"></i>';
        pinColor = '#10b981'; // verde
      }
      if(item.tendencia === 'baja') {
        icon = '<i class="fa-solid fa-arrow-trend-down text-danger"></i>';
        pinColor = '#ef4444'; // rojo
      }

      // Añadir marcador al mapa si la región tiene coordenadas
      if (coordenadasRegiones[item.region]) {
        const markerIcon = L.divIcon({
          className: 'custom-map-marker',
          html: `<div style="background-color: ${pinColor}; width: 16px; height: 16px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 10px ${pinColor};"></div>`,
          iconSize: [16, 16],
          iconAnchor: [8, 8]
        });
        
        const marker = L.marker(coordenadasRegiones[item.region], {icon: markerIcon})
          .addTo(mapaMercado)
          .bindPopup(`<b>${item.region}</b><br>Demanda: ${item.demanda_indice}<br>Precio: S/ ${item.precio_promedio.toFixed(2)}`);
          
        mapaMarcadores.push(marker);
      }

      div.innerHTML = `
        <div class="d-flex align-items-center">
          <span class="badge bg-secondary me-3">${index + 1}</span>
          <div>
            <h6 class="mb-0 text-white">${item.region}</h6>
            <small class="text-muted">Demanda: ${item.demanda_indice}</small>
          </div>
        </div>
        <div class="text-end">
          <div class="fw-bold">S/ ${item.precio_promedio.toFixed(2)}</div>
          <small>${icon}</small>
        </div>
      `;
      container.appendChild(div);
    });
  } catch (e) {
    console.error("Error mercado en vivo:", e);
  }
}

document.getElementById('tab-mercado').addEventListener('shown.bs.tab', () => {
  if (!mercadoInterval) {
    actualizarMercado(); // Carga inicial
    mercadoInterval = setInterval(actualizarMercado, 5000); // Actualiza cada 5s
  }
  if (mapaMercado) {
    setTimeout(() => { mapaMercado.invalidateSize(); }, 100);
  }
});

// Si salimos del tab de mercado, podríamos detener el intervalo, pero dejémoslo vivo si el usuario quiere que esté "actualizado al volver".
// Para optimizar recursos, lo apagamos si no está visible:
document.getElementById('tab-mercado').addEventListener('hidden.bs.tab', () => {
  clearInterval(mercadoInterval);
  mercadoInterval = null;
});

// Init
cargarCultivos();