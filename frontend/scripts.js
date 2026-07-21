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
// Helper para capitalizar cultivos (ej. "uva" -> "Uva", "pallar grano seco" -> "Pallar Grano Seco")
function capitalizarCultivo(nombre) {
  if (!nombre) return "";
  return nombre.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
}

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
    const nombreVisible = capitalizarCultivo(cultivo);
    div.textContent = nombreVisible;
    div.onclick = () => {
      selectCultivoHidden.value = cultivo; // Para el backend (minúscula)
      inputSearchCultivo.value = nombreVisible; // Para el usuario (Mayúscula)
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
formPrediccion.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  let cultivo = selectCultivoHidden.value;
  const textoBuscado = inputSearchCultivo.value.trim().toLowerCase();

  // Autoseleccionar si el usuario tipeó el nombre exacto ("uva") pero no dio clic en la lista
  if (!cultivo || cultivo.toLowerCase() !== textoBuscado) {
      const matchExacto = cultivosDisponibles.find(c => c.toLowerCase() === textoBuscado);
      if (matchExacto) {
          cultivo = matchExacto;
          selectCultivoHidden.value = matchExacto;
          inputSearchCultivo.value = capitalizarCultivo(matchExacto);
      }
  }

  const anioInicio = 2020;
  const anioFin = parseInt(inputAnio.value, 10);

  if (!cultivo) {
    estadoMensaje.innerHTML = `<span class="text-warning">Por favor selecciona un cultivo.</span>`;
    return;
  }

  estadoMensaje.innerHTML = `<span class="text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Generando predicciones...</span>`;
  filaResultados.style.display = "none";

  const mesesNombres = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
  const numYears = anioFin - anioInicio + 1;

  try {
    // Fetch predictions for all years and months
    const reqs = [];
    for (let y = anioInicio; y <= anioFin; y++) {
      for (let m = 1; m <= 12; m++) {
        reqs.push(
          fetch(`${API_BASE_URL}/predecir`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cultivo, anio: y, mes: m })
          }).then(r => r.json()).then(data => ({ ...data, anio: y, mes: m }))
        );
      }
    }

    const resultadosMensuales = await Promise.all(reqs);

    let labels = [];
    let dataRendimiento = [];
    let dataProduccion = [];
    let dataPrecio = [];
    
    // Calcular el resumen agregado para el año objetivo final
    const resFinAnio = resultadosMensuales.filter(r => r.anio === anioFin);
    const totalProdFin = resFinAnio.reduce((sum, r) => sum + r.produccion_t, 0);
    const prodValidFin = resFinAnio.filter(r => r.produccion_t > 0);
    const meanRendFin = prodValidFin.length > 0 ? prodValidFin.reduce((sum, r) => sum + r.rendimiento_kg_ha, 0) / prodValidFin.length : 0;
    const meanPrecioFin = prodValidFin.length > 0 ? prodValidFin.reduce((sum, r) => sum + r.precio_chacra_soles_kg, 0) / prodValidFin.length : 0;

    if (numYears > 2) {
      // Agrupar por año (si es mayor a 2 años)
      for (let y = anioInicio; y <= anioFin; y++) {
        const resAnio = resultadosMensuales.filter(r => r.anio === y);
        const prod = resAnio.reduce((sum, r) => sum + r.produccion_t, 0);
        const prodValid = resAnio.filter(r => r.produccion_t > 0);
        const rend = prodValid.length > 0 ? prodValid.reduce((sum, r) => sum + r.rendimiento_kg_ha, 0) / prodValid.length : 0;
        const precio = prodValid.length > 0 ? prodValid.reduce((sum, r) => sum + r.precio_chacra_soles_kg, 0) / prodValid.length : 0;
        
        labels.push(y.toString());
        dataRendimiento.push(rend);
        dataProduccion.push(prod);
        dataPrecio.push(precio);
      }
    } else {
      // Mostrar por meses (si es <= 2 años)
      resultadosMensuales.forEach(r => {
        labels.push(`${mesesNombres[r.mes - 1]} ${r.anio}`);
        dataRendimiento.push(r.rendimiento_kg_ha);
        dataProduccion.push(r.produccion_t);
        dataPrecio.push(r.precio_chacra_soles_kg);
      });
    }

    valorRendimiento.textContent = meanRendFin.toLocaleString("es-PE", {maximumFractionDigits:0});
    valorProduccion.textContent = totalProdFin.toLocaleString("es-PE", {maximumFractionDigits:0});
    valorPrecio.textContent = meanPrecioFin.toLocaleString("es-PE", {maximumFractionDigits:2});

    filaResultados.style.display = "flex";
    document.getElementById("card-grafico-rendimiento").style.display = "block";
    document.getElementById("card-grafico-produccion").style.display = "block";
    document.getElementById("card-grafico-precio").style.display = "block";

    // Destacar el último punto
    const isTarget = (i) => i === (labels.length - 1);

    chartRendimiento = crearGraficoBarras(chartRendimiento, "chart-rendimiento", labels, dataRendimiento, colors.green, isTarget);
    chartProduccion = crearGraficoLineasArea(chartProduccion, "chart-produccion", labels, dataProduccion, colors.blue);
    chartPrecio = crearGraficoLineas(chartPrecio, "chart-precio", labels, dataPrecio, colors.yellow);

    // Update Proyección Regional with the aggregated target year prediction
    actualizarMapaProyeccion(totalProdFin, meanPrecioFin, cultivo);

    estadoMensaje.innerHTML = `<span class="text-success-custom"><i class="fa-solid fa-check-circle"></i> Predicción calculada (${numYears > 2 ? 'Anual' : 'Mensual'})</span>`;
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

// --- Cuadrante Riesgo-Rendimiento (interactivo) ---
let riesgoDataGlobal = []; // Almacena todos los datos para filtrar
let riesgoFilterActivo = 'todos';

function getColorByZone(riesgo, ganancia, mitadRiesgo, mitadGanancia) {
  if (riesgo <= mitadRiesgo && ganancia >= mitadGanancia) return { bg: 'rgba(16, 185, 129, 0.7)', border: '#10b981' }; // Ideal
  if (riesgo > mitadRiesgo && ganancia >= mitadGanancia) return { bg: 'rgba(251, 191, 36, 0.7)', border: '#fbbf24' }; // Rentable-Arriesgado
  if (riesgo <= mitadRiesgo && ganancia < mitadGanancia) return { bg: 'rgba(59, 130, 246, 0.7)', border: '#3b82f6' }; // Seguro-Bajo
  return { bg: 'rgba(239, 68, 68, 0.7)', border: '#ef4444' }; // Evitar
}

function getPointSize(produccionTotal, maxProduccion) {
  const minSize = 6;
  const maxSize = 20;
  if (!produccionTotal || maxProduccion <= 0) return minSize;
  return minSize + (produccionTotal / maxProduccion) * (maxSize - minSize);
}

function renderRiesgoChart(dataPuntos, highlightCultivo = null) {
  const filtrados = riesgoFilterActivo === 'todos'
    ? dataPuntos
    : dataPuntos.filter(d => d.grupo === riesgoFilterActivo);

  const maxGanancia = filtrados.length > 0 ? (Math.max(...filtrados.map(p => p.y)) * 1.15) : 50000;
  const maxRiesgo = 100;
  const mitadRiesgo = 50;
  const mitadGanancia = maxGanancia / 2;
  const maxProduccion = Math.max(...filtrados.map(p => p.produccion_total || 0));

  const bgColors = filtrados.map(p => {
    if (highlightCultivo && p.cultivo.toLowerCase().includes(highlightCultivo.toLowerCase())) {
      return 'rgba(255, 255, 255, 0.95)';
    }
    return getColorByZone(p.x, p.y, mitadRiesgo, mitadGanancia).bg;
  });

  const borderColors = filtrados.map(p => {
    if (highlightCultivo && p.cultivo.toLowerCase().includes(highlightCultivo.toLowerCase())) {
      return '#ffffff';
    }
    return getColorByZone(p.x, p.y, mitadRiesgo, mitadGanancia).border;
  });

  const radii = filtrados.map(p => getPointSize(p.produccion_total, maxProduccion));

  const ctx = document.getElementById("chart-riesgo-rendimiento").getContext("2d");
  if (chartRiesgo) chartRiesgo.destroy();

  chartRiesgo = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [{
        label: 'Cultivos',
        data: filtrados,
        backgroundColor: bgColors,
        borderColor: borderColors,
        borderWidth: 2,
        pointRadius: radii,
        pointHoverRadius: radii.map(r => r + 4),
        pointHoverBorderWidth: 3,
        pointHoverBorderColor: '#ffffff'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 600, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.95)',
          borderColor: 'rgba(255,255,255,0.2)',
          borderWidth: 1,
          titleFont: { size: 14, weight: 'bold' },
          bodyFont: { size: 12 },
          padding: 12,
          displayColors: false,
          callbacks: {
            title: (items) => items[0].raw.cultivo.toUpperCase(),
            label: (ctx) => {
              const d = ctx.raw;
              return [
                `Ganancia promedio: S/ ${d.y.toLocaleString('es-PE', {maximumFractionDigits: 0})}`,
                `Riesgo (CV): ${d.x.toFixed(1)}%`,
                `Precio prom.: S/ ${(d.precio_promedio || 0).toFixed(2)}/kg`,
                `Prod. total: ${(d.produccion_total || 0).toLocaleString('es-PE', {maximumFractionDigits: 0})} t`,
                `Tipo: ${d.grupo === 'A' ? 'Transitorio' : 'Permanente'}`,
                `Meses activos: ${d.meses_activos || '-'}`
              ];
            }
          }
        },
        annotation: {
          annotations: {
            boxIdeal: {
              type: 'box', xMin: 0, xMax: mitadRiesgo, yMin: mitadGanancia, yMax: maxGanancia,
              backgroundColor: 'rgba(16, 185, 129, 0.06)', borderWidth: 0,
              label: { display: true, content: 'IDEAL', position: { x: 'start', y: 'start' }, color: 'rgba(16, 185, 129, 0.5)', font: { size: 13, weight: 'bold' } }
            },
            boxArriesgado: {
              type: 'box', xMin: mitadRiesgo, xMax: maxRiesgo, yMin: mitadGanancia, yMax: maxGanancia,
              backgroundColor: 'rgba(251, 191, 36, 0.06)', borderWidth: 0,
              label: { display: true, content: 'RENTABLE / ARRIESGADO', position: { x: 'start', y: 'start' }, color: 'rgba(251, 191, 36, 0.5)', font: { size: 13, weight: 'bold' } }
            },
            boxSeguro: {
              type: 'box', xMin: 0, xMax: mitadRiesgo, yMin: 0, yMax: mitadGanancia,
              backgroundColor: 'rgba(59, 130, 246, 0.06)', borderWidth: 0,
              label: { display: true, content: 'SEGURO / BAJA GANANCIA', position: { x: 'start', y: 'start' }, color: 'rgba(59, 130, 246, 0.5)', font: { size: 13, weight: 'bold' } }
            },
            boxPeligro: {
              type: 'box', xMin: mitadRiesgo, xMax: maxRiesgo, yMin: 0, yMax: mitadGanancia,
              backgroundColor: 'rgba(239, 68, 68, 0.06)', borderWidth: 0,
              label: { display: true, content: 'EVITAR', position: { x: 'start', y: 'start' }, color: 'rgba(239, 68, 68, 0.5)', font: { size: 13, weight: 'bold' } }
            },
            lineX: { type: 'line', xMin: mitadRiesgo, xMax: mitadRiesgo, borderColor: 'rgba(255,255,255,0.15)', borderWidth: 2, borderDash: [6, 4] },
            lineY: { type: 'line', yMin: mitadGanancia, yMax: mitadGanancia, borderColor: 'rgba(255,255,255,0.15)', borderWidth: 2, borderDash: [6, 4] }
          }
        }
      },
      scales: {
        x: { min: 0, max: maxRiesgo, title: { display: true, text: 'Riesgo (Coeficiente de Variacion %)', font: { size: 13 } }, grid: { color: "rgba(255,255,255,0.05)" } },
        y: { min: 0, max: maxGanancia, title: { display: true, text: 'Ganancia Esperada (S/ por mes)', font: { size: 13 } }, grid: { color: "rgba(255,255,255,0.05)" },
          ticks: { callback: (v) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v }
        }
      },
      onClick: (event, elements) => {
        if (elements.length > 0) {
          const idx = elements[0].index;
          const d = filtrados[idx];
          mostrarDetalleCultivo(d);
        }
      }
    }
  });
}

function mostrarDetalleCultivo(d) {
  const panel = document.getElementById('detalle-cultivo-panel');
  const content = document.getElementById('detalle-cultivo-content');
  panel.style.display = 'block';

  const maxGanancia = riesgoDataGlobal.length > 0 ? Math.max(...riesgoDataGlobal.map(p => p.y)) : 1;
  const mitadRiesgo = 50;
  const mitadGanancia = maxGanancia / 2;
  const zona = getColorByZone(d.x, d.y, mitadRiesgo, mitadGanancia);

  let zonaTexto = '';
  if (d.x <= mitadRiesgo && d.y >= mitadGanancia) zonaTexto = 'Ideal';
  else if (d.x > mitadRiesgo && d.y >= mitadGanancia) zonaTexto = 'Rentable pero Arriesgado';
  else if (d.x <= mitadRiesgo && d.y < mitadGanancia) zonaTexto = 'Seguro, baja ganancia';
  else zonaTexto = 'Evitar';

  content.innerHTML = `
    <div class="mb-3">
      <h5 class="text-white mb-1">${capitalizarCultivo(d.cultivo)}</h5>
      <span class="badge" style="background-color:${zona.bg};color:#fff;">${zonaTexto}</span>
      <span class="badge bg-secondary ms-1">${d.grupo === 'A' ? 'Transitorio' : 'Permanente'}</span>
    </div>
    <div class="row g-2 mb-2">
      <div class="col-6">
        <div class="text-muted small">Ganancia/mes</div>
        <div class="text-white fw-bold">S/ ${d.y.toLocaleString('es-PE', {maximumFractionDigits: 0})}</div>
      </div>
      <div class="col-6">
        <div class="text-muted small">Riesgo (CV)</div>
        <div class="text-white fw-bold">${d.x.toFixed(1)}%</div>
      </div>
    </div>
    <div class="row g-2 mb-2">
      <div class="col-6">
        <div class="text-muted small">Precio prom.</div>
        <div class="text-white fw-bold">S/ ${(d.precio_promedio || 0).toFixed(2)}/kg</div>
      </div>
      <div class="col-6">
        <div class="text-muted small">Prod. total</div>
        <div class="text-white fw-bold">${(d.produccion_total || 0).toLocaleString('es-PE', {maximumFractionDigits: 0})} t</div>
      </div>
    </div>
    <div class="row g-2">
      <div class="col-6">
        <div class="text-muted small">Meses activos</div>
        <div class="text-white fw-bold">${d.meses_activos || '-'} meses</div>
      </div>
    </div>
  `;
}

function renderTopCultivos(dataPuntos) {
  // Score = ganancia / (1 + riesgo/100) → premia alta ganancia y bajo riesgo
  const scored = dataPuntos
    .filter(d => d.y > 0)
    .map(d => ({ ...d, score: d.y / (1 + d.x / 100) }))
    .sort((a, b) => b.score - a.score);

  const top5 = scored.slice(0, 5);
  const container = document.getElementById('top-cultivos-riesgo');
  container.innerHTML = '';

  top5.forEach((d, i) => {
    const zona = getColorByZone(d.x, d.y, 50, (Math.max(...dataPuntos.map(p => p.y)) * 1.15) / 2);
    const div = document.createElement('div');
    div.className = 'ranking-item';
    div.style.cursor = 'pointer';
    div.onclick = () => mostrarDetalleCultivo(d);
    div.innerHTML = `
      <div class="d-flex align-items-center">
        <span class="badge me-2" style="background:${zona.bg};width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:11px;">${i + 1}</span>
        <div>
          <div class="text-white fw-bold">${capitalizarCultivo(d.cultivo)}</div>
          <small class="text-muted">CV: ${d.x.toFixed(0)}% | ${d.grupo === 'A' ? 'Trans.' : 'Perm.'}</small>
        </div>
      </div>
      <div class="text-end">
        <div class="fw-bold text-success">S/ ${d.y.toLocaleString('es-PE', {maximumFractionDigits: 0})}</div>
        <small class="text-muted">/mes</small>
      </div>
    `;
    container.appendChild(div);
  });
}

document.getElementById('tab-riesgo').addEventListener('shown.bs.tab', async () => {
  if (riesgoDataGlobal.length > 0) return; // Ya se cargó
  try {
    const res = await fetch(`${API_BASE_URL}/riesgo-rendimiento`);
    const texto = await res.text();
    const data = JSON.parse(texto.replace(/NaN/g, 'null'));

    riesgoDataGlobal = data.data
      .filter(d => d.rendimiento_esperado > 0 && d.rendimiento_esperado !== null)
      .map(d => ({
        x: d.riesgo || 0,
        y: d.rendimiento_esperado,
        cultivo: d.cultivo,
        precio_promedio: d.precio_promedio || 0,
        produccion_total: d.produccion_total || 0,
        grupo: d.grupo || 'A',
        meses_activos: d.meses_activos || 0
      }));

    renderRiesgoChart(riesgoDataGlobal);
    renderTopCultivos(riesgoDataGlobal);

    // Filtros de grupo
    document.querySelectorAll('.glass-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.glass-filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        riesgoFilterActivo = btn.dataset.filter;
        renderRiesgoChart(riesgoDataGlobal, document.getElementById('riesgo-search').value);
      });
    });

    // Buscador
    document.getElementById('riesgo-search').addEventListener('input', (e) => {
      renderRiesgoChart(riesgoDataGlobal, e.target.value);
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
            label: 'Temp. Máxima (°C) - Calor diurno',
            data: data.temperatura_c,
            borderColor: '#ef4444', // Rojo
            backgroundColor: '#ef4444',
            borderWidth: 3,
            tension: 0.4,
            yAxisID: 'y',
            pointRadius: 4,
            pointBackgroundColor: '#fff'
          },
          {
            type: 'line',
            label: 'Temp. Mínima (°C) - Frío nocturno',
            data: data.temp_min_c,
            borderColor: '#3b82f6', // Azul
            backgroundColor: 'rgba(239, 68, 68, 0.1)', // Fondo semi transparente para el rango térmico
            borderWidth: 3,
            tension: 0.4,
            yAxisID: 'y',
            pointRadius: 4,
            pointBackgroundColor: '#fff',
            fill: 0 // Rellena el espacio hacia el dataset 0 (Temp Máxima)
          },
          {
            type: 'bar',
            label: 'Precipitación (mm) - Lluvia',
            data: data.precipitacion_mm,
            backgroundColor: 'rgba(6, 182, 212, 0.6)', // Cyan semi transparente
            borderColor: '#06b6d4',
            borderWidth: 1,
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
          y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Temperatura (°C)' }, grid: { color: "rgba(255,255,255,0.05)" } },
          y1: { type: 'linear', display: true, position: 'right', title: { display: true, text: 'Precipitación (mm)' }, grid: { display: false } },
          x: { grid: { display: false } }
        }
      }
    });
  } catch(e) { console.error("Error cargando clima:", e); }
});

// -----------------------------------------------------------------------
// 4. Proyección Regional (Distribución Estimada)
// -----------------------------------------------------------------------
let mapaMercado = null;
let mapaMarcadores = [];

// Pesos fijos aproximados de distribución agrícola en la región Ica
const pesosProvincias = {
  "Ica Centro": 0.40,
  "Chincha": 0.20,
  "Pisco": 0.20,
  "Nasca": 0.10,
  "Palpa": 0.10
};

const coordenadasRegiones = {
  "Chincha": [-13.4099, -76.1323],
  "Pisco": [-13.7144, -76.2028],
  "Ica Centro": [-14.0678, -75.7286],
  "Palpa": [-14.5336, -75.1856],
  "Nasca": [-14.8288, -74.9436]
};

function actualizarMapaProyeccion(produccionTotal, precioSoles, cultivoStr) {
  const container = document.getElementById('ranking-container');
  container.innerHTML = "";
  
  if (produccionTotal <= 0) {
    container.innerHTML = `<div class="text-center text-muted">Producción 0 estimada. No hay distribución.</div>`;
    return;
  }

  // Inicializar mapa si no existe
  if (!mapaMercado) {
    const mapDiv = document.getElementById('map-container');
    mapDiv.innerHTML = ""; // Limpiar placeholder
    mapaMercado = L.map('map-container').setView([-14.0678, -75.7286], 9); 
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://carto.com/">CartoDB</a>',
      maxZoom: 19
    }).addTo(mapaMercado);
    setTimeout(() => { mapaMercado.invalidateSize(); }, 500);
  } else {
    mapaMarcadores.forEach(m => mapaMercado.removeLayer(m));
    mapaMarcadores = [];
  }

  // Calcular la distribución y ordenar
  let distribucion = Object.keys(pesosProvincias).map(prov => {
    const prodProvincia = produccionTotal * pesosProvincias[prov];
    const ingresoBruto = prodProvincia * precioSoles * 1000; // t * soles/kg * 1000 = soles
    return {
      provincia: prov,
      peso: pesosProvincias[prov],
      produccion: prodProvincia,
      ingreso: ingresoBruto
    };
  });
  
  distribucion.sort((a, b) => b.produccion - a.produccion);

  distribucion.forEach((item, index) => {
    const div = document.createElement('div');
    div.className = 'ranking-item';
    
    // Añadir marcador al mapa
    if (coordenadasRegiones[item.provincia]) {
      // Tamaño del punto depende del peso
      const size = 12 + (item.peso * 30);
      const markerIcon = L.divIcon({
        className: 'custom-map-marker',
        html: `<div style="background-color: rgba(59, 130, 246, 0.8); width: ${size}px; height: ${size}px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 10px rgba(59, 130, 246, 0.5);"></div>`,
        iconSize: [size, size],
        iconAnchor: [size/2, size/2]
      });
      
      const marker = L.marker(coordenadasRegiones[item.provincia], {icon: markerIcon})
        .addTo(mapaMercado)
        .bindPopup(`<b>${item.provincia}</b><br>Estimado (${cultivoStr}):<br>${item.produccion.toLocaleString('es-PE', {maximumFractionDigits: 1})} t`);
        
      mapaMarcadores.push(marker);
    }

    div.innerHTML = `
      <div class="d-flex align-items-center">
        <span class="badge bg-secondary me-3">${index + 1}</span>
        <div>
          <h6 class="mb-0 text-white">${item.provincia} (${(item.peso * 100).toFixed(0)}%)</h6>
          <small class="text-muted">Prod: ${item.produccion.toLocaleString('es-PE', {maximumFractionDigits: 1})} t</small>
        </div>
      </div>
      <div class="text-end">
        <div class="fw-bold text-success">S/ ${item.ingreso >= 1000000 ? (item.ingreso/1000000).toFixed(2) + 'M' : item.ingreso.toLocaleString('es-PE', {maximumFractionDigits: 0})}</div>
        <small class="text-muted">Ingreso Bruto</small>
      </div>
    `;
    container.appendChild(div);
  });
}

document.getElementById('tab-proyeccion').addEventListener('shown.bs.tab', () => {
  if (mapaMercado) {
    setTimeout(() => { mapaMercado.invalidateSize(); }, 100);
  } else {
      // Inicializar vacío si aún no hay predicción
      const mapDiv = document.getElementById('map-container');
      if (mapDiv.innerHTML.includes("text-center")) {
          mapDiv.innerHTML = "";
          mapaMercado = L.map('map-container').setView([-14.0678, -75.7286], 9); 
          L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://carto.com/">CartoDB</a>',
            maxZoom: 19
          }).addTo(mapaMercado);
      }
  }
});

// Init
cargarCultivos();