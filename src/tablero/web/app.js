/* Tablero de MIP. Sin librerias externas. */

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const api = (r) => fetch("/api/" + r).then((x) => x.json());
const esc = (t) =>
  String(t ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const numero = (n) => (n == null ? "—" : Number(n).toLocaleString("es-AR"));
const plata = (n) => (n == null ? "—" : "$" + Number(n).toLocaleString("es-AR"));

const CANALES_DIGITALES = ["web", "whatsapp", "telegram", "app", "email"];
let MUNICIPIOS = [];

/* ---------------------------------------------------------------- Navegación */
$$("#pestanas button").forEach((b) =>
  b.addEventListener("click", () => {
    $$("#pestanas button").forEach((x) => x.classList.remove("activa"));
    b.classList.add("activa");
    $$(".vista").forEach((v) => v.classList.add("oculta"));
    $("#vista-" + b.dataset.vista).classList.remove("oculta");
    cargarVista(b.dataset.vista);
  })
);

function cargarVista(vista) {
  ({ panel: verPanel, municipios: verMunicipios, turnos: verTurnos,
     impacto: verImpacto, revision: verRevision, acciones: verAcciones }[vista] || (() => {}))();
}

/* -------------------------------------------------------------------- Panel */
async function verPanel() {
  const r = await api("resumen");
  const cobertura = Math.round((r.con_sitio_oficial / r.municipios) * 100);
  $("#tarjetas").innerHTML = `
    ${tarjeta(numero(r.municipios), "Municipios relevados", numero(r.poblacion_total) + " habitantes")}
    ${tarjeta(r.con_sitio_oficial + "/" + r.municipios, "Con sitio oficial", cobertura + "% de cobertura", "buena")}
    ${tarjeta(numero(r.urls_descubiertas), "URLs con evidencia", "Todas con cita y fecha")}
    ${tarjeta(numero(r.hallazgos_verificados), "Datos verificados", "Cita comprobada contra la fuente")}
    ${tarjeta(r.turnos_digitales, "Ya resolvieron turnos", "Tienen canal digital", "buena")}
    ${tarjeta(r.turnos_sin_digital, "Prospectos con evidencia", "Ausencia probada por cita", "alerta")}
    ${tarjeta(r.turnos_sin_datos, "Sin datos de turnos", "No investigado o sin rastro")}
    ${tarjeta(r.pendientes_revision, "Para revisar a ojo", "Antes de ir a una propuesta", "alerta")}
  `;
  const sinHttps = r.sitios_sin_https || [];
  $("#pie-panel").innerHTML = sinHttps.length
    ? `Sin HTTPS: <strong>${sinHttps.map(esc).join(", ")}</strong>. Un portal sin TLS no puede
       tener pagos seguros ni turnos con datos de salud: es señal de nivel Básico.`
    : "";
}

const tarjeta = (cifra, rotulo, detalle, clase = "") =>
  `<div class="tarjeta ${clase}"><div class="cifra">${cifra}</div>
   <div class="rotulo">${rotulo}</div><div class="detalle">${detalle}</div></div>`;

/* --------------------------------------------------------------- Municipios */
async function verMunicipios() {
  if (!MUNICIPIOS.length) MUNICIPIOS = await api("municipios");
  pintarMunicipios();
}

["#buscar", "#filtro-canal", "#filtro-sitio"].forEach((s) =>
  $(s).addEventListener("input", pintarMunicipios)
);

function pintarMunicipios() {
  const texto = $("#buscar").value.toLowerCase().trim();
  const canal = $("#filtro-canal").value;
  const sitio = $("#filtro-sitio").value;

  const filas = MUNICIPIOS.filter((m) => {
    if (texto && !m.municipio.toLowerCase().includes(texto)) return false;
    const digital = CANALES_DIGITALES.includes(m.canal_turnos);
    if (canal === "digital" && !digital) return false;
    if (canal === "sin_digital" && !["telefono", "presencial"].includes(m.canal_turnos)) return false;
    if (canal === "sin_datos" && m.canal_turnos) return false;
    if (sitio === "si" && !m.sitio_oficial) return false;
    if (sitio === "no" && m.sitio_oficial) return false;
    if (sitio === "sin_https" && m.sitio_sin_https !== 1) return false;
    return true;
  });

  $("#tabla-municipios tbody").innerHTML = filas
    .map((m) => `
      <tr data-municipio="${esc(m.municipio)}">
        <td><strong>${esc(m.municipio)}</strong>
            ${m.sitio_sin_https === 1 ? ' <span class="etiqueta alerta">sin HTTPS</span>' : ""}</td>
        <td class="num">${numero(m.poblacion)}</td>
        <td>${m.sitio_oficial
              ? `<span class="etiqueta ok">sí</span>`
              : `<span class="etiqueta mal">no encontrado</span>`}</td>
        <td class="num">${m.urls}</td>
        <td class="num">${m.variables_con_evidencia}</td>
        <td>${etiquetaCanal(m.canal_turnos)}</td>
      </tr>`)
    .join("") || `<tr><td colspan="6" class="nota">Sin resultados.</td></tr>`;

  $$("#tabla-municipios tbody tr[data-municipio]").forEach((tr) =>
    tr.addEventListener("click", () => abrirFicha(tr.dataset.municipio))
  );
}

function etiquetaCanal(c) {
  if (!c) return '<span class="etiqueta">sin datos</span>';
  const clase = CANALES_DIGITALES.includes(c) ? "ok" : "alerta";
  return `<span class="etiqueta ${clase}">${esc(c)}</span>`;
}

/* -------------------------------------------------------------------- Ficha */
async function abrirFicha(nombre) {
  const f = await api("municipio/" + encodeURIComponent(nombre));
  $("#ficha-titulo").textContent = nombre;
  $("#ficha-cuerpo").innerHTML = `
    <p class="nota">${esc(f.id_municipio)} · ${numero(f.poblacion)} habitantes
      ${f.sitio_oficial ? `· <a href="${esc(f.sitio_oficial)}" target="_blank" rel="noopener">${esc(f.sitio_oficial)}</a>` : "· sin sitio oficial"}</p>

    <h3>Variables (${f.hallazgos.filter((h) => h.estado === "verificado").length} con evidencia)</h3>
    ${f.hallazgos.map(fichaHallazgo).join("")}

    <h3>URLs descubiertas (${f.urls_detalle.length})</h3>
    ${f.urls_detalle.map(fichaUrl).join("")}

    <div class="barra" style="margin-top:20px">
      <button class="boton primario" data-accion="descubrir_municipio" data-m="${esc(nombre)}">Redescubrir URLs</button>
      <button class="boton" data-accion="extraer_municipio" data-m="${esc(nombre)}">Volver a extraer (usa IA)</button>
    </div>`;

  $$("#ficha-cuerpo [data-accion]").forEach((b) =>
    b.addEventListener("click", () => lanzarAccion(b.dataset.accion, b.dataset.m))
  );
  $("#panel-ficha").classList.remove("oculta");
  $("#fondo").classList.remove("oculta");
}

function fichaHallazgo(h) {
  const verificado = h.estado === "verificado";
  const clase = verificado ? (h.valor === "no" || h.valor === "presencial" || h.valor === "telefono" ? "alerta" : "ok") : "";
  return `
    <div style="margin-bottom:12px">
      <strong>${esc(h.variable)}</strong>
      <span class="etiqueta ${clase}">${esc(h.valor)}</span>
      ${verificado ? `<span class="etiqueta">${esc(h.confianza)}</span>` : ""}
      ${h.estado === "cita_rechazada" ? '<span class="etiqueta mal">cita rechazada</span>' : ""}
      ${h.fragmento ? `
        <div class="evidencia">
          <div class="cita">“${esc(h.fragmento)}”</div>
          <div class="origen">
            ${h.url ? `<a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.url)}</a><br>` : ""}
            ${esc(h.fecha)} · ${esc(h.tipo_fuente || "")} ${h.modelo ? "· " + esc(h.modelo) : "· sin IA, probado por Fase 3"}
          </div>
        </div>` : ""}
      ${h.detalle ? `<div class="nota">${esc(h.detalle)}</div>` : ""}
    </div>`;
}

const fichaUrl = (u) => `
  <div class="evidencia">
    <div><span class="etiqueta">${esc(u.tipo)}</span>
      <span class="etiqueta ${u.confianza === "Alta" ? "ok" : ""}">${esc(u.confianza)}</span></div>
    <div class="origen"><a href="${esc(u.url)}" target="_blank" rel="noopener">${esc(u.url)}</a></div>
    ${u.titulo_fragmento ? `<div class="cita">“${esc(u.titulo_fragmento)}”</div>` : ""}
    <div class="origen">origen: ${esc(u.fuente_query)}</div>
  </div>`;

$("#cerrar-ficha").addEventListener("click", cerrarFicha);
$("#fondo").addEventListener("click", cerrarFicha);
document.addEventListener("keydown", (e) => e.key === "Escape" && cerrarFicha());
function cerrarFicha() {
  $("#panel-ficha").classList.add("oculta");
  $("#fondo").classList.add("oculta");
}

/* ------------------------------------------------------------------- Turnos */
async function verTurnos() {
  const t = await api("turnos");
  $("#turnos-contenido").innerHTML =
    grupoTurnos("Ya resolvieron", "Tienen canal digital de turnos. No son prospectos para esto.", t.digitales) +
    grupoTurnos("Prospectos con evidencia", "Ausencia probada con cita textual: hoy hay que llamar o ir.", t.sin_digital) +
    `<div class="grupo"><h3>Sin datos (${t.sin_datos.length})</h3>
      <p class="subtitulo">No investigado, o el portal no habla de salud. ADR-0009: el vacío se muestra como vacío.</p>
      <p class="nota">${t.sin_datos.map((m) => esc(m.municipio)).join(" · ")}</p></div>`;
}

const grupoTurnos = (titulo, subtitulo, filas) => `
  <div class="grupo">
    <h3>${titulo} (${filas.length})</h3>
    <p class="subtitulo">${subtitulo}</p>
    ${filas.map((f) => `
      <div class="evidencia">
        <div><strong>${esc(f.municipio)}</strong> · ${numero(f.poblacion)} hab ·
          ${etiquetaCanal(f.valor)}</div>
        <div class="cita">“${esc(f.fragmento)}”</div>
        ${f.url ? `<div class="origen"><a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.url)}</a></div>` : ""}
      </div>`).join("") || '<p class="nota">Ninguno.</p>'}
  </div>`;

/* ------------------------------------------------------------------ Impacto */
async function verImpacto() {
  const [c, params] = await Promise.all([api("costo-turnos"), api("parametros")]);
  if (!c.disponible) {
    $("#impacto-contenido").innerHTML = '<p class="nota">Falta correr Fase 4.</p>';
    return;
  }
  $("#impacto-contenido").innerHTML = `
    <div class="aviso">
      <h4>Leer esto antes de usar los números</h4>
      <ul>${c.advertencias.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
    </div>

    <div class="tarjetas">
      ${tarjeta(c.municipios.length, "Municipios con ausencia probada", "Solo entran los que tienen cita")}
      ${tarjeta(plata(c.total_min), "Costo social anual (piso)", "Con el valor hora más bajo defendible")}
      ${tarjeta(plata(c.total_max), "Costo social anual (techo)", "Con los supuestos más altos")}
    </div>

    <h3>Techo de precio por municipio</h3>
    <p class="nota">Cuánto puede justificar pagar cada uno, dado el valor que se le devuelve.
      El 10% es una decisión comercial de UDS, no un resultado del modelo.</p>
    <table><thead><tr>
      <th>Municipio</th><th class="num">Hab.</th><th>Canal hoy</th>
      <th class="num">Costo social anual</th><th class="num">Techo mensual</th>
    </tr></thead><tbody>
      ${c.municipios.map((m) => `<tr>
        <td><strong>${esc(m.municipio)}</strong></td>
        <td class="num">${numero(m.poblacion)}</td>
        <td>${etiquetaCanal(m.canal_actual)}</td>
        <td class="num">${plata(m.costo_min)} — ${plata(m.costo_max)}</td>
        <td class="num">${plata(m.techo_mensual_min)} — ${plata(m.techo_mensual_max)}</td>
      </tr>`).join("")}
    </tbody></table>
    <div class="barra" style="margin-top:12px">
      <a class="boton" href="/api/exportar/costo-turnos.csv">Exportar CSV</a>
    </div>

    <h3>Qué medir primero</h3>
    <p class="nota">El rango es ancho porque hay supuestos sin fuente. El modelo sabe dónde
      está la incertidumbre y cómo cerrarla.</p>
    ${c.sensibilidad.map((s) => `
      <div class="evidencia">
        <div><strong>${s.factor}×</strong> ${esc(s.parametro)}</div>
        <div class="origen">${esc(s.como_cerrarlo)}</div>
      </div>`).join("")}

    <h3>Parámetros y su procedencia</h3>
    ${params.map((p) => `
      <div class="evidencia">
        <div><strong>${esc(p.nombre)}</strong> = ${esc(p.valor)} ${esc(p.unidad)}
          <span class="etiqueta ${p.afirmable ? "ok" : "alerta"}">${esc(p.tipo)}</span></div>
        <div class="origen">${esc(p.fuente)}</div>
      </div>`).join("")}`;
}

/* ----------------------------------------------------------------- Revisión */
async function verRevision() {
  const filas = await api("revision");
  $("#revision-contenido").innerHTML = filas.length
    ? filas.map((f) => `
        <div class="evidencia">
          <div><strong>${esc(f.municipio)}</strong> · ${esc(f.variable)}
            <span class="etiqueta ${f.motivo === "cita_rechazada" ? "mal" : "alerta"}">${esc(f.motivo)}</span></div>
          <div class="origen">${esc(f.detalle)}</div>
          ${f.fragmento ? `<div class="cita">“${esc(f.fragmento)}”</div>` : ""}
          ${f.url ? `<div class="origen"><a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.url)}</a></div>` : ""}
        </div>`).join("")
    : '<p class="nota">Nada pendiente.</p>';
}

/* ---------------------------------------------------------------- Acciones */
async function verAcciones() {
  const lista = await api("acciones");
  $("#acciones-contenido").innerHTML = lista
    .filter((a) => !a.requiere_municipio)
    .map((a) => `
      <div class="evidencia">
        <div><strong>${esc(a.titulo)}</strong>
          ${a.consume_ia ? '<span class="etiqueta alerta">usa cuota de IA</span>' : ""}</div>
        <div class="origen">~${a.minutos_estimados} min</div>
        <button class="boton primario" data-accion="${esc(a.id)}" style="margin-top:8px">Ejecutar</button>
      </div>`).join("") +
    '<p class="nota">Las acciones por municipio están dentro de cada ficha.</p>';

  $$("#acciones-contenido [data-accion]").forEach((b) =>
    b.addEventListener("click", () => lanzarAccion(b.dataset.accion, null))
  );
  refrescarTareas();
}

async function lanzarAccion(accion, municipio) {
  const r = await fetch("/api/accion", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accion, municipio }),
  }).then((x) => x.json());

  if (r.error) return alert(r.error);
  cerrarFicha();
  $$("#pestanas button").forEach((x) => x.classList.remove("activa"));
  document.querySelector('[data-vista="acciones"]').classList.add("activa");
  $$(".vista").forEach((v) => v.classList.add("oculta"));
  $("#vista-acciones").classList.remove("oculta");
  await verAcciones();
  seguirTarea(r.tarea_id);
}

async function refrescarTareas() {
  const t = await api("tareas");
  $("#tareas-contenido").innerHTML = t.length
    ? t.map((x) => `
        <div class="evidencia">
          <div><strong>${esc(x.titulo)}</strong> ${x.municipio ? "· " + esc(x.municipio) : ""}
            <span class="etiqueta ${x.estado === "terminada" ? "ok" : x.estado === "fallo" ? "mal" : "alerta"}">${esc(x.estado)}</span></div>
          <div class="origen">inició ${esc(x.iniciada)}${x.fin ? " · terminó " + esc(x.fin) : ""}</div>
          <button class="boton" data-tarea="${esc(x.id)}" style="margin-top:6px">Ver salida</button>
        </div>`).join("")
    : '<p class="nota">Todavía no se ejecutó nada.</p>';
  $$("#tareas-contenido [data-tarea]").forEach((b) =>
    b.addEventListener("click", () => seguirTarea(b.dataset.tarea))
  );
}

let temporizador = null;
async function seguirTarea(id) {
  clearInterval(temporizador);
  const pre = $("#salida-tarea");
  pre.classList.remove("oculta");
  const tic = async () => {
    const t = await api("tarea/" + id);
    pre.textContent = (t.salida || []).join("\n") || "Arrancando…";
    pre.scrollTop = pre.scrollHeight;
    if (t.estado !== "corriendo") {
      clearInterval(temporizador);
      MUNICIPIOS = [];               // la base cambió: se relee
      refrescarTareas();
    }
  };
  await tic();
  temporizador = setInterval(tic, 1500);
}

verPanel();
