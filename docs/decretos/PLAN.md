# Plan: Decretos Presidenciales — Duque, Petro, De la Espriella

> Estado: **PR0 (spike) y PR1 (esqueleto + metadata) completados**, ver
> sección 2 y 5. Este documento cubre la Fase 1 (descarga estructurada +
> persistencia). El dashboard de Streamlit y la clasificación por tipo de
> decreto se detallan a alto nivel pero se planearán en documentos/PRs aparte
> cuando lleguemos a esa fase.

## 0. Objetivo

Descargar y estructurar los decretos presidenciales firmados por **Iván Duque**,
**Gustavo Petro** y **Abelardo de la Espriella**, mapeados por presidente, como
base para (más adelante) comparar volumen de decretos en el tiempo y,
eventualmente, clasificarlos por tipo/tema.

Este es un sub-proyecto independiente del análisis de actas E14, dentro del
mismo repo. No comparten dominio de datos, pero sí convenciones de ingeniería
(uv, pytest, httpx, SQLite, CLI con typer, descarga idempotente con reintentos).

## 1. Investigación inicial de la fuente — hallazgos

Se probaron cuatro fuentes candidatas. Resultado:

| Fuente | URL | Estado observado | Notas |
|---|---|---|---|
| **Presidencia — Normativa** | `dapre.presidencia.gov.co/normativa/decretos` | 🔴 Bloqueada | SharePoint detrás de **F5 Distributed Cloud Bot Defense** (cookies `TS*`, challenge JS ofuscado). `curl`/`httpx` simples reciben una página vacía con solo el script de challenge. Es la fuente "oficial" que mencionaste y la más limpia en estructura (menú por tipo de norma: Decretos, Leyes, Resoluciones...), pero requiere ejecutar JS real. |
| **Diario Oficial (Imprenta Nacional)** | `svrpubindc.imprenta.gov.co/diario` | 🟢 Accesible | Sin protección anti-bot (200 OK directo). Es la fuente **legal autoritativa** — todo decreto se publica ahí. Contra: es una app JSF/PrimeFaces con estado de sesión (`jsessionid`) y `ViewState` en los formularios de búsqueda, así que el scraper tiene que simular POSTs con el token vigente en vez de simples GETs. Más trabajo de integración, pero nada exótico. |
| **SUIN-Juriscol** (Min. Justicia) | `suin-juriscol.gov.co` | 🟡 Sin confirmar | Timeout/conexión reseteada en la prueba (puede ser transitorio). Es el consolidado jurídico nacional, con vistas de documento limpias (viewDocument.asp?ruta=Decretos/{id}) y metadata estructurada (fecha, "expedida por"). Vale la pena reintentar en el spike. |
| **Archivo legado Presidencia** | `wp.presidencia.gov.co/sitios/normativa/decretos/{año}/...` | 🟡 Sin confirmar | La página nueva redirige "Normas anteriores" ahí, pero el host no respondió en la prueba (puede estar caído, o ser un dominio viejo intermitente). Organizado por año/mes en URLs — atractivo si funciona, pero probablemente no cubre 2025-2026 (parece un archivo pre-migración, se vio un path con `/2015/`).

**Conclusión:** no hay una fuente trivialmente scrapeable por HTTP plano. La
página que mencionaste (`dapre.presidencia.gov.co/normativa`) es la más
completa pero la más protegida.

## 2. Spike de scraping — resuelto ✅

**Veredicto: Playwright con Chromium real pasa el challenge de F5 de forma
consistente**, sin necesidad de trucos extra (mismo user-agent/viewport que
cualquier navegador de escritorio). No hizo falta caer al plan B (Diario
Oficial).

Hallazgos concretos:

- **Patrón de URL determinístico**, sin buscador ni paginación necesaria:
  ```
  https://dapre.presidencia.gov.co/normativa/decretos-{año}/decretos-{mes-en-español}-{año}
  ```
  Confirmado funcionando para `decretos-2018/decretos-agosto-2018` (era
  Duque) y `decretos-2022/decretos-agosto-2022` (transición Duque→Petro). Un
  mes sin contenido publicado (probado con `decretos-2026/decretos-agosto-2026`)
  responde 200 con una página vacía, no un error — hay que tratar "0
  decretos" como resultado válido, no como fallo.
- **Estructura del listado**, estable y fácil de parsear (usamos
  BeautifulSoup, no Playwright, para esta parte — así queda testeable sin
  red):
  ```html
  <li class="dfwp-item">
    <div class="item link-item">
      <a href="https://dapre.presidencia.gov.co/normativa/normativa/DECRETO 1665 DEL 31 DE AGOSTO DE 2018.pdf">
        DECRETO 1665 DEL 31 DE AGOSTO DE 2018
      </a>
      <div class="description">Por medio del cual se hace un nombramiento ordinario de ...</div>
    </div>
  </li>
  ```
  Número y fecha completa salen del texto del link con una regex; el título
  vive en `.description`. Nada de esto depende de JS una vez la página ya
  renderizó — solo hace falta Playwright para pasar el challenge inicial y
  obtener el HTML final.
- No hizo falta usar el Diario Oficial ni SUIN-Juriscol — quedan como
  referencia en la tabla de la sección 1 por si el sitio de Presidencia
  cambia de protección más adelante.

## 3. Modelo de datos

```
Presidente
  slug            str   # "duque" | "petro" | "de-la-espriella"
  nombre          str
  fecha_inicio    date
  fecha_fin       date | None   # None = periodo en curso

Decreto
  numero          int
  anio            int          # la numeración de decretos reinicia cada año en Colombia,
                                # así que la clave natural es (anio, numero), no numero solo
  fecha_firma     date
  titulo          str          # "por el cual se..."
  presidente_slug str          # derivado de fecha_firma, no asignado a mano
  url_origen      str          # URL de donde se listó/enlazó
  url_pdf         str
  path_local      str | None   # ruta al PDF persistido
  hash_archivo    str | None   # para detectar re-descargas/cambios
  fecha_descarga  datetime | None
```

Los presidentes se mapean a partir de la fecha de firma del decreto contra los
rangos de fecha, no por asignación manual — así el mismo código sirve para
sumar más presidentes en el futuro sin tocar la lógica de descarga.

**Fechas de periodo (a confirmar/ajustar):**
- Duque: 2018-08-07 → 2022-08-07
- Petro: 2022-08-07 → 2026-08-07
- De la Espriella: 2026-08-07 → *(en curso)*

## 4. Arquitectura (implementada en PR1)

Mismo repo, nuevo subpaquete espejo del ya existente para E14, para mantener
convenciones consistentes:

```
src/verifacta/decretos/
├── models.py         # Pydantic: Presidente, Decreto
├── presidentes.py     # tabla de periodos + presidente_para_fecha(fecha) / presidente_por_slug(slug)
├── client.py          # DecretosClient (Playwright) + parse_decretos_html() (BeautifulSoup, pura/testeable)
├── repository.py      # SQLAlchemy: tabla `decretos`, upsert_many idempotente por (anio, numero)
└── sync.py            # orquesta: client -> mapea a presidente -> repository
```

CLI (extiende el `verifacta` existente, no un binario nuevo):

```bash
uv run verifacta decretos sync-mes --year 2018 --month 8   # metadata de un mes/año (PR1, ya funciona)
uv run verifacta decretos stats                             # conteo de decretos por presidente
```

Comandos que faltan y llegan en PR2/PR3 (documentados aquí para no perder el
hilo, no implementados todavía): `decretos sync --presidente duque` (barrer
todo un periodo iterando meses) y `decretos stats --interval week|month|quarter`
(agregación temporal para el futuro gráfico de Streamlit).

**Persistencia de PDFs** (a partir de PR2), mismo espíritu que
`downloads/{DPTO}_{MUNI}_...`:

```
decretos/{presidente_slug}/{anio}/{numero}.pdf
```

**Base de datos:** `results/decretos.db`, **separada** de
`results/verifacta.db` (el de E14) — decisión tomada en PR1: son dos
dominios sin relación (mesas de votación vs. normativa presidencial), y
compartir el archivo solo hubiera acoplado sus esquemas sin ningún beneficio
real. Cada uno con su propio `Repository`.

## 5. Fases y PRs propuestos (empezar chico, siempre con algo funcional)

- **PR0 — Spike de fuente de datos.** ✅ Completado, ver sección 2.
- **PR1 — Esqueleto + metadata (sin PDFs todavía).** ✅ Completado.
  `src/verifacta/decretos/` (`models.py`, `presidentes.py`, `client.py`,
  `repository.py`, `sync.py`) + CLI (`verifacta decretos sync-mes`,
  `verifacta decretos stats`) + 20 tests (mapeo de fechas, parseo de HTML
  con fixture real, upsert idempotente en SQLite).

  Validado con datos reales end-to-end:
  - `sync-mes --year 2018 --month 8` → 92 decretos de Duque + 66 sin mapear
    (decretos del 1-6 de agosto de 2018, previos a su posesión — de Santos,
    fuera de alcance, el mapper correctamente los deja sin presidente en vez
    de asignarlos mal).
  - `sync-mes --year 2022 --month 8` → confirma la transición: los primeros
    días de agosto 2022 se suman a Duque (187 acumulado) y el resto a Petro
    (83) — la lógica de "presidente por fecha de firma, no por asignación
    manual" funciona en el mes de transición real, que era el caso límite
    más importante de validar.
  - `sync-mes --year 2026 --month 8` → 0 decretos, sin error (la página
    existe pero está vacía — esperado, ver nota sobre De la Espriella en la
    sección 6).
- **PR2 — Descarga y persistencia de PDFs.** ✅ Código completo y validado a
  pequeña escala; **falta correr la barrida histórica completa** (queda como
  siguiente paso, ver sección 6).
  - `client.download_pdf()`: reusa las cookies de sesión que ya dejó
    `fetch_month` al pasar el challenge — confirmado por spike que
    `context.request.get()` funciona directo sin abrir una página por PDF
    (mucho más rápido que Playwright completo por archivo).
  - `downloader.download_all()`: descarga en paralelo (semáforo, default 3
    workers) los decretos sin `path_local` en el repo. Doble idempotencia:
    filtra en SQL los que ya tienen `path_local`, y además chequea si el
    archivo ya existe en disco (por si la DB quedó desincronizada) — ambos
    caminos verificados con datos reales.
  - **Orden: del más reciente al más antiguo** (a pedido explícito), tanto
    en `meses_del_periodo()` (sync de metadata) como en
    `pendientes_de_descarga()` (cola de descarga de PDFs) — así una corrida
    parcial o con `--limit` deja lo más reciente ya disponible primero.
  - `decretos sync --presidente <slug>`: sincroniza metadata de **todos**
    los meses del periodo (antes solo había `sync-mes` para un mes suelto),
    reusando un solo browser Playwright en vez de uno por mes.
  - `decretos download-pdfs [--presidente] [--limit] [--workers]`: descarga
    los PDFs pendientes. `decretos/{presidente_slug}/{anio}/{numero}.pdf`.
  - Validado end-to-end: sync de agosto 2018 (158 decretos) → descarga de 5
    PDFs reales → verificado que un segundo run no re-descarga (ni por DB ni
    por disco, probados los dos casos por separado).
- **PR3 — Comando de stats en CLI.** Conteos por presidente agregados por
  semana/mes/trimestre desde SQLite (sin UI todavía) — esto es la base de
  datos exacta que va a consumir el gráfico de Streamlit, así que separarlo
  de la UI nos deja probarlo con `pytest` antes de tocar Streamlit.
- **PR4 — (a definir en su propio doc) Sección Streamlit.** Gráfico
  comparativo con selector de intervalo (día/semana/mes/trimestre) + botón
  "actualizar datos" que dispare una descarga incremental (solo decretos
  nuevos desde el último sync guardado).
- **PR5 — (futuro, fuera de alcance ahora) Clasificación de decretos** por
  tipo/tema vía LLM (nombramientos, ambiente, economía, defensa, etc.),
  reusando el patrón de `analysis/detector.py`.

## 6. Riesgos / preguntas abiertas

- **Botón "actualizar" en Streamlit en vivo:** si el spike termina en
  Playwright (navegador real), una actualización disparada desde un botón de
  Streamlit va a ser más lenta y pesada que un `httpx.get` — probablemente
  necesite correr como job de fondo en vez de bloquear el request de
  Streamlit. Se decide en el PR4 cuando sepamos qué ganó el spike.
- **Fecha de inicio de gobierno de De la Espriella:** asumida 2026-08-07 por
  ser la fecha constitucional de posesión; ajustar si hay una fecha real
  distinta.
- **Volumen esperado:** sin datos aún de cuántos decretos por gobierno (para
  Duque/Petro son ~4 años cada uno). Esto sale del spike/PR1 y determina si
  la descarga completa (PR2) toma minutos u horas.
- **Numeración de decretos por año:** confirmar en el spike que efectivamente
  reinicia cada año (asumido por convención colombiana) — afecta la clave
  primaria `(anio, numero)`.

## 7. Fuera de alcance por ahora

- Clasificación por tipo/tema de decreto (PR5, mencionado pero no planeado en
  detalle).
- Comparación con Leyes, Resoluciones, Directivas u otros tipos de norma —
  solo Decretos por ahora.
- Cualquier presidente antes de Duque.
