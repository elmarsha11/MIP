/* Tablero de MIP. Sin librerias externas. */

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
/* El tablero corre de dos formas con el MISMO codigo:
   - contra el servidor local, pidiendo datos por HTTP
   - dentro de un HTML autonomo, leyendo los datos incrustados en la pagina
   Una sola funcion decide cual. Duplicar el frontend seria garantizar que las
   dos versiones diverjan. */
const ESTATICO = typeof window.DATOS_MIP !== "undefined";
const api = (r) =>
  ESTATICO ? Promise.resolve(leerIncrustado(r)) : fetch("/api/" + r).then((x) => x.json());

function leerIncrustado(ruta) {
  const D = window.DATOS_MIP;
  if (ruta.startsWith("territorio/")) {
    const nombre = decodeURIComponent(ruta.slice("territorio/".length));
    return D.territorios[nombre] || { total: 0, ubicadas: 0, recuadro: null, entidades: [] };
  }
  if (ruta.startsWith("resumen-municipio/")) {
    const nombre = decodeURIComponent(ruta.slice("resumen-municipio/".length));
    return (D.resumenes || {})[nombre] || {};
  }
  if (ruta.startsWith("municipio/")) {
    const nombre = decodeURIComponent(ruta.slice("municipio/".length));
    return D.fichas[nombre] || { error: "Municipio inexistente" };
  }
  return {
    resumen: D.resumen, municipios: D.municipios, turnos: D.turnos,
    "costo-turnos": D.costo_turnos, revision: D.revision, comercial: D.comercial,
    parametros: D.parametros, territorio: D.territorio, acciones: [], tareas: [],
  }[ruta] ?? [];
}
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
     territorio: verTerritorio, impacto: verImpacto, comercial: verComercial,
     revision: verRevision, acciones: verAcciones }[vista] || (() => {}))();
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
  const [f, r] = await Promise.all([
    api("municipio/" + encodeURIComponent(nombre)),
    api("resumen-municipio/" + encodeURIComponent(nombre)),
  ]);
  $("#ficha-titulo").textContent = nombre;
  $("#ficha-cuerpo").innerHTML = `
    <p class="nota">${esc(f.id_municipio)}
      ${f.sitio_oficial ? `· <a href="${esc(f.sitio_oficial)}" target="_blank" rel="noopener">${esc(f.sitio_oficial)}</a>` : "· sin sitio oficial"}
      ${f.sitio_sin_https === 1 ? ' · <span class="etiqueta alerta">sin HTTPS</span>' : ""}</p>

    ${r && r.municipio ? resumenMunicipio(r) : ""}

    <h3>Evidencia detallada</h3>
    <p class="nota">Cada variable con su cita textual, verificada contra la fuente.</p>
    ${f.hallazgos.map(fichaHallazgo).join("")}

    <h3>URLs descubiertas (${f.urls_detalle.length})</h3>
    ${f.urls_detalle.map(fichaUrl).join("")}

    ${ESTATICO ? `
      <p class="nota" style="margin-top:20px">Esta es una foto fechada. Para volver a
        investigar este municipio hay que abrir el tablero con el servidor.</p>`
    : `
      <div class="barra" style="margin-top:20px">
        <button class="boton primario" data-accion="descubrir_municipio" data-m="${esc(nombre)}">Redescubrir URLs</button>
        <button class="boton" data-accion="extraer_municipio" data-m="${esc(nombre)}">Volver a extraer (usa IA)</button>
      </div>`}`;

  $$("#ficha-cuerpo [data-accion]").forEach((b) =>
    b.addEventListener("click", () => lanzarAccion(b.dataset.accion, b.dataset.m))
  );
  $("#panel-ficha").classList.remove("oculta");
  $("#fondo").classList.remove("oculta");
}

/* La ficha como la leeria una persona, no como la guarda una base.
   Todo lo que no se sabe se dice, con el motivo. ADR-0009: el vacio se muestra. */
function resumenMunicipio(r) {
  const falta = (motivo) => `<span class="etiqueta">sin dato</span>
    <span class="origen"> ${esc(motivo || "")}</span>`;

  const conEvidencia = (d) =>
    d.valor
      ? `<strong>${esc(d.valor)}</strong>${d.detalle ? " · " + esc(d.detalle) : ""}
         ${d.url ? `<div class="origen"><a href="${esc(d.url)}" target="_blank" rel="noopener">ver fuente</a>
            ${d.fragmento ? `— <em>"${esc(d.fragmento.slice(0, 90))}"</em>` : ""}</div>` : ""}`
      : falta(d.motivo);

  const p = r.poblacion, s = r.salud, e = r.educacion, t = r.transporte;
  const canalEtiqueta = s.turnos_canal
    ? etiquetaCanal(s.turnos_canal)
    : '<span class="etiqueta">sin dato</span>';

  return `
  <div class="resumen">
    <h3>Población</h3>
    <p><strong>${numero(p.total)}</strong> habitantes
      <span class="origen">· ${esc(p.fuente)}</span></p>
    <p class="origen">Mujeres / varones / viviendas: ${esc(p.falta)}</p>

    <h3>Autoridades</h3>
    <table><tbody>
      <tr><td>Intendente</td><td>${conEvidencia(r.autoridades.intendente)}</td></tr>
      <tr><td>Secretarías</td><td>${conEvidencia(r.autoridades.secretarias)}</td></tr>
      <tr><td>Concejo Deliberante</td><td>${conEvidencia(r.autoridades.concejales)}</td></tr>
    </tbody></table>

    <h3>Educación — ${e.total} establecimientos</h3>
    ${e.total
      ? `<table><tbody>${Object.entries(e.por_nivel).map(([nivel, n]) =>
          `<tr><td>${esc(nivel)}</td><td class="num"><strong>${n}</strong></td></tr>`).join("")}
         </tbody></table><p class="origen">${esc(e.fuente)}</p>`
      : `<p>${falta("El municipio no fue censado todavía")}</p>`}

    <h3>Salud</h3>
    <table><tbody>
      <tr><td>Hospitales</td><td>${s.hospitales.length
        ? s.hospitales.map((h) => `<strong>${esc(h.nombre || "(sin nombre)")}</strong>
            ${h.direccion ? `<span class="origen"> · ${esc(h.direccion)}</span>` : ""}`).join("<br>")
        : falta("Sin hospital registrado en OpenStreetMap")}</td></tr>
      <tr><td>CAPS / salas</td><td><strong>${s.caps}</strong>
        ${s.caps_nombrados.length ? `<div class="origen">${s.caps_nombrados.map(esc).join(" · ")}</div>` : ""}</td></tr>
      <tr><td>Farmacias</td><td>${s.farmacias}</td></tr>
      <tr><td><strong>Turnos médicos</strong></td><td>${canalEtiqueta}
        ${s.turnos_evidencia ? `<div class="origen"><em>"${esc(s.turnos_evidencia.slice(0, 100))}"</em>
          ${s.turnos_url ? `<a href="${esc(s.turnos_url)}" target="_blank" rel="noopener"> ver fuente</a>` : ""}</div>` : ""}</td></tr>
    </tbody></table>

    <h3>Gestión digital</h3>
    <table><tbody>
      ${Object.entries(r.digital).map(([etiqueta, d]) =>
        `<tr><td>${esc(etiqueta)}</td><td>${conEvidencia(d)}</td></tr>`).join("")}
    </tbody></table>

    <h3>Transporte público</h3>
    <table><tbody>
      <tr><td>Tren</td><td>${t.estaciones_tren.length
        ? t.estaciones_tren.map((x) => `<strong>${esc(x.nombre || "estación")}</strong>`).join(" · ")
        : falta("Sin estación registrada en OpenStreetMap")}</td></tr>
      <tr><td>Colectivo urbano</td><td>${falta(t.falta)}</td></tr>
    </tbody></table>
  </div>`;
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

/* ---------------------------------------------------------------- Territorio */
/* El mapa se dibuja como SVG con las coordenadas reales, sin librerias ni tiles
   externos. No hay callejero de fondo, pero se ve la distribucion territorial
   —donde estan los CAPS respecto de los barrios— que es lo que sirve para
   decidir. Y funciona sin internet, que es requisito del HTML autonomo. */

const COLOR_CAPA = {
  "Salud": "#d9614c",
  "Educación": "#4a9eda",
  "Gobierno y seguridad": "#d99a3c",
  "Territorio": "#8b98a8",
  "Cultura y comunidad": "#3fb27f",
};
let TERRITORIO = null;
let CAPAS_VISIBLES = new Set(Object.keys(COLOR_CAPA));

async function verTerritorio() {
  const resumen = await api("territorio");
  const selector = $("#territorio-municipio");

  if (!resumen.municipios || !resumen.municipios.length) {
    $("#mapa-caja").innerHTML =
      '<p class="nota">Todavía no se censó ningún municipio. Corré: ' +
      '<code>python src/territorio/censo.py --all</code></p>';
    $("#territorio-lista").innerHTML = "";
    return;
  }

  if (!selector.options.length) {
    selector.innerHTML = resumen.municipios
      .map((m) => `<option value="${esc(m.municipio)}">${esc(m.municipio)} — ${m.total_entidades} entidades</option>`)
      .join("");
    selector.addEventListener("change", () => pintarTerritorio(selector.value));
  }
  await pintarTerritorio(selector.value || resumen.municipios[0].municipio);
}

async function pintarTerritorio(municipio) {
  TERRITORIO = await api("territorio/" + encodeURIComponent(municipio));
  $("#territorio-cuenta").textContent =
    `${TERRITORIO.total} entidades · ${TERRITORIO.ubicadas} ubicadas`;
  dibujarMapa();
  listarEntidades();
}

function dibujarMapa() {
  const caja = TERRITORIO.recuadro;
  if (!caja) {
    $("#mapa-caja").innerHTML = '<p class="nota">Sin entidades ubicadas.</p>';
    return;
  }
  const ANCHO = 900, ALTO = 520, MARGEN = 24;
  // Corrige la deformacion por latitud: a -35° un grado de longitud mide
  // bastante menos que uno de latitud. Sin esto el municipio sale estirado.
  const latMedia = (caja.lat_min + caja.lat_max) / 2;
  const factorLon = Math.cos((latMedia * Math.PI) / 180);
  const anchoGeo = Math.max((caja.lon_max - caja.lon_min) * factorLon, 1e-6);
  const altoGeo = Math.max(caja.lat_max - caja.lat_min, 1e-6);
  const escala = Math.min((ANCHO - 2 * MARGEN) / anchoGeo, (ALTO - 2 * MARGEN) / altoGeo);
  const desplX = (ANCHO - anchoGeo * escala) / 2;
  const desplY = (ALTO - altoGeo * escala) / 2;

  const px = (e) => desplX + (e.longitud - caja.lon_min) * factorLon * escala;
  const py = (e) => desplY + (caja.lat_max - e.latitud) * escala;  // norte arriba

  const visibles = TERRITORIO.entidades.filter(
    (e) => e.latitud != null && CAPAS_VISIBLES.has(e.capa)
  );
  // Los barrios van al fondo: son el contexto sobre el que se leen los servicios.
  visibles.sort((a, b) => (a.capa === "Territorio" ? -1 : 0) - (b.capa === "Territorio" ? -1 : 0));

  const puntos = visibles.map((e, i) => {
    const r = e.capa === "Territorio" ? 3 : 5;
    return `<circle class="punto" cx="${px(e).toFixed(1)}" cy="${py(e).toFixed(1)}" r="${r}"
      fill="${COLOR_CAPA[e.capa] || "#888"}" fill-opacity="${e.capa === "Territorio" ? 0.5 : 0.85}"
      data-i="${i}"><title>${esc(e.nombre || e.tipo)}</title></circle>`;
  }).join("");

  $("#mapa-caja").innerHTML = `
    <svg viewBox="0 0 ${ANCHO} ${ALTO}" role="img" aria-label="Mapa de ${esc(TERRITORIO.municipio)}">
      <rect width="${ANCHO}" height="${ALTO}" fill="transparent"/>
      ${puntos}
    </svg>
    <div class="leyenda">
      ${Object.entries(COLOR_CAPA).map(([capa, color]) => `
        <label class="${CAPAS_VISIBLES.has(capa) ? "activa" : ""}" data-capa="${esc(capa)}">
          <span class="bolita" style="background:${color}"></span>${esc(capa)}
        </label>`).join("")}
    </div>
    <div id="mapa-detalle">Pasá el mouse por un punto, o hacé click para ver su ficha.</div>`;

  $$("#mapa-caja .leyenda label").forEach((l) =>
    l.addEventListener("click", () => {
      const capa = l.dataset.capa;
      CAPAS_VISIBLES.has(capa) ? CAPAS_VISIBLES.delete(capa) : CAPAS_VISIBLES.add(capa);
      dibujarMapa();
    })
  );
  $$("#mapa-caja .punto").forEach((c) =>
    c.addEventListener("click", () => mostrarEntidad(visibles[+c.dataset.i]))
  );
}

function mostrarEntidad(e) {
  $("#mapa-detalle").innerHTML = `
    <strong>${esc(e.nombre || "(sin nombre)")}</strong> · ${esc(e.tipo)}
    ${e.direccion ? " · " + esc(e.direccion) : ""}
    ${e.telefono ? " · " + esc(e.telefono) : ""}
    ${e.url_fuente ? ` · <a href="${esc(e.url_fuente)}" target="_blank" rel="noopener">verificar en OpenStreetMap</a>` : ""}`;
}

function listarEntidades() {
  const porCapa = {};
  for (const e of TERRITORIO.entidades) (porCapa[e.capa] ||= []).push(e);

  $("#territorio-lista").innerHTML = Object.entries(porCapa)
    .map(([capa, entidades]) => {
      const porTipo = {};
      for (const e of entidades) (porTipo[e.tipo] ||= []).push(e);
      return `
        <div class="grupo">
          <h3><span class="bolita" style="background:${COLOR_CAPA[capa] || "#888"}"></span>
            ${esc(capa)} (${entidades.length})</h3>
          ${Object.entries(porTipo).sort((a, b) => b[1].length - a[1].length).map(([tipo, grupo]) => `
            <p class="subtitulo">${esc(tipo)} (${grupo.length})</p>
            ${grupo.slice(0, 40).map((e) => `
              <div class="evidencia">
                <div><strong>${esc(e.nombre || "(sin nombre)")}</strong>
                  ${e.direccion ? `<span class="origen"> · ${esc(e.direccion)}</span>` : ""}</div>
                ${e.telefono || e.web ? `<div class="origen">${esc(e.telefono || "")} ${esc(e.web || "")}</div>` : ""}
                ${e.url_fuente ? `<div class="origen"><a href="${esc(e.url_fuente)}" target="_blank" rel="noopener">${esc(e.url_fuente)}</a></div>` : ""}
              </div>`).join("")}
            ${grupo.length > 40 ? `<p class="nota">… y ${grupo.length - 40} más (ver CSV)</p>` : ""}
          `).join("")}
        </div>`;
    }).join("");
}

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

/* ---------------------------------------------------------------- Comercial */
let COMERCIAL = null;

async function verComercial() {
  if (!COMERCIAL) COMERCIAL = await api("comercial");
  const d = COMERCIAL;

  if (!d.disponible) {
    $("#comercial-contenido").innerHTML =
      '<p class="nota">Todavía no se analizó. Corré <code>python src/oportunidades/motor.py --all</code>.</p>';
    return;
  }

  const filtro = $("#comercial-producto");
  if (!filtro.options.length) {
    filtro.innerHTML =
      `<option value="">Todos los productos (${d.total} oportunidades)</option>` +
      d.productos.map((p) =>
        `<option value="${esc(p.producto)}">${esc(p.producto)} — ${p.municipios} municipios</option>`
      ).join("");
    filtro.addEventListener("change", pintarComercial);
  }
  pintarComercial();
}

function pintarComercial() {
  const d = COMERCIAL;
  const producto = $("#comercial-producto").value;

  // El filtro esconde las oportunidades de otros productos, pero NO recalcula el
  // potencial: el orden sigue siendo el del municipio completo. Si se reordenara
  // por el subconjunto filtrado, el ranking cambiaria segun lo que se esta
  // mirando y dejaria de servir para decidir a quien visitar.
  const municipios = d.municipios
    .map((m) => ({
      ...m,
      visibles: producto ? m.oportunidades.filter((o) => o.producto === producto) : m.oportunidades,
    }))
    .filter((m) => m.visibles.length);

  $("#comercial-cuenta").textContent =
    `${municipios.reduce((n, m) => n + m.visibles.length, 0)} oportunidades en ${municipios.length} municipios`;

  $("#comercial-contenido").innerHTML = municipios.map((m) => `
    <div class="evidencia">
      <div><strong>${esc(m.municipio)}</strong>
        <span class="etiqueta">potencial ${m.puntaje}</span></div>
      ${m.visibles.map((o) => `
        <div style="margin-top:10px">
          <div><span class="etiqueta ${o.friccion === "alta" ? "mal" : "alerta"}">${esc(o.friccion)}</span>
            <strong>${esc(o.producto)}</strong></div>
          <div class="origen">${esc(o.problema)}</div>
          <div class="cita">“${esc(o.cita)}”</div>
          <div class="origen"><a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.url)}</a></div>
        </div>`).join("")}
    </div>`).join("");
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

if (ESTATICO) {
  document.querySelector('[data-vista="acciones"]').remove();
  document.body.classList.add("estatico");
  descargasLocales();
}

/* Sin servidor, los CSV se arman en el navegador. Sigue funcionando sin internet. */
function descargasLocales() {
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="/api/exportar/"]');
    if (!a) return;
    e.preventDefault();
    const cual = a.getAttribute("href").split("/").pop().replace(".csv", "");
    const D = window.DATOS_MIP;
    const filas = {
      municipios: D.municipios,
      turnos: [...D.turnos.digitales.map((f) => ({ ...f, grupo: "con canal digital" })),
               ...D.turnos.sin_digital.map((f) => ({ ...f, grupo: "sin canal digital (probado)" }))],
      revision: D.revision,
      "costo-turnos": D.costo_turnos.municipios || [],
      territorio: Object.values(D.territorios || {}).flatMap((t) => t.entidades || []),
    }[cual] || [];
    if (!filas.length) return alert("Nada para exportar.");
    const cols = Object.keys(filas[0]);
    const csv = [cols.join(",")]
      .concat(
        filas.map((f) =>
          cols.map((c) => `"${String(f[c] ?? "").replace(/"/g, '""')}"`).join(",")
        )
      )
      .join("\n");
    // BOM al principio para que Excel en Windows no rompa los acentos.
    const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv" }));
    const link = Object.assign(document.createElement("a"), { href: url, download: `mip_${cual}.csv` });
    link.click();
    URL.revokeObjectURL(url);
  });
}

verPanel();
