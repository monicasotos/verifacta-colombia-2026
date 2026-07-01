# Verifacta Colombia 2026

Herramienta de veeduría electoral para la segunda vuelta presidencial del **21 de junio de 2026**. Descarga las actas E14 TRANSMISIÓN de la Registraduría Nacional y las analiza automáticamente con IA para detectar:

- **Tachones**: números tachados, enmendados o con corrector líquido en los campos de votación
- **Inconsistencias aritméticas**: cuando `candidato_1 + candidato_2 + blancos + nulos + no_marcados ≠ suma_total`
- **Firmas faltantes**: alguna de las 6 cajas de jurados vacías en la página 2 del acta

## Requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes)
- API key de Gemini (gratis en [aistudio.google.com](https://aistudio.google.com))

## Instalación

```bash
git clone <repo>
cd verifacta-elecciones
uv sync
```

Crea un archivo `.env` en la raíz del proyecto:

```
GEMINI_API_KEY=tu_api_key_aquí
```

## Uso

### 1. Descargar actas

```bash
# Todos los departamentos (ordenados por población)
uv run verifacta download

# Solo un departamento (código interno API, no DANE)
uv run verifacta download --dept 01          # Antioquia
uv run verifacta download --dept 16          # Bogotá D.C.

# Limitar cantidad y workers
uv run verifacta download --limit 500 -w 2 --delay 1.0
```

Los PDFs se guardan en `downloads/{DPTO}_{MUNI_CODE}_Z{ZONA}_P{PUESTO}_M{MESA}/`.

### 2. Analizar actas con IA

```bash
# Analizar todo lo descargado
uv run verifacta analyze --sample downloads/

# Analizar un departamento específico
uv run verifacta analyze --sample downloads/ --model gemini-2.5-flash -w 10

# Analizar desde un archivo con rutas (una por línea)
uv run verifacta analyze --from-file muestra.txt

# Re-analizar aunque ya estén en la base de datos
uv run verifacta analyze --sample downloads/ --reanalyze
```

### 3. Muestreo proporcional

Para analizar una muestra representativa sin procesar todo:

```bash
# Generar muestra de 1000 actas proporcional a población municipal
uv run verifacta sample --n 1000 --output muestra.txt

# Luego analizar esa muestra
uv run verifacta analyze --from-file muestra.txt -w 10
```

El muestreo usa `departamentos_de_interes.json` para filtrar departamentos.

### 4. Ver resultados

```bash
uv run verifacta report summary        # resumen general
uv run verifacta report flags          # tabla de actas con alertas
uv run verifacta report flags --output alertas.csv   # exportar a CSV
```

### 5. Limpiar archivos corruptos

```bash
uv run verifacta cleanup               # elimina PDFs corruptos (HTML disfrazado)
uv run verifacta cleanup --dry-run     # solo mostrar, sin borrar
```

## Arquitectura

```
src/verifacta/
├── scraper/
│   ├── client.py       # HTTP client async; catálogo de actas desde JSON estático
│   ├── models.py       # Pydantic: Departamento, Municipio, Zona, Puesto, Mesa
│   ├── downloader.py   # Descargas paralelas con prioridad por población
│   └── sampler.py      # Muestreo proporcional por municipio
├── analysis/
│   ├── extractor.py    # PDF → imágenes PNG via pymupdf
│   └── detector.py     # Detección de anomalías via Gemini Vision
├── storage/
│   └── repository.py   # SQLite via SQLAlchemy
└── cli.py              # CLI: download, analyze, sample, cleanup, report
```

## Fuente de datos

El catálogo completo de actas es un JSON estático de ~36MB (~122k actas):

```
https://e14segundavueltapresidente.registraduria.gov.co/assets/temis/divipol_json/allTransmissionCodes.json
```

Se cachea en `scripts/allTransmissionCodes.json` (gitignored). Los PDFs están en:

```
/assets/temis/pdf/{dept}/{muni}/{zona_3dig}/{puesto}/{mesa}/PRE/{hash}.pdf
```

### Códigos de departamento (internos de la API, NO son códigos DANE)

| Código | Departamento    | Código | Departamento        |
|--------|----------------|--------|---------------------|
| 01     | ANTIOQUIA      | 23     | NARIÑO              |
| 03     | ATLÁNTICO      | 24     | RISARALDA           |
| 05     | BOLÍVAR        | 25     | NORTE DE SANTANDER  |
| 07     | BOYACÁ         | 26     | QUINDÍO             |
| 09     | CALDAS         | 27     | SANTANDER           |
| 11     | CAUCA          | 29     | TOLIMA              |
| 15     | CUNDINAMARCA   | 31     | VALLE               |
| 16     | BOGOTÁ D.C.    | 88     | CONSULADOS          |
| 19     | HUILA          |        |                     |

## Bloqueos del CDN (Akamai) — qué hacer

La Registraduría usa Akamai CDN que bloquea requests automatizadas. Si ves errores como `CDN devolvió HTML en vez de PDF`, sigue estos pasos:

### Síntomas
- Los PDFs descargados tienen tamaño muy pequeño (~2-5 KB en vez de ~100-300 KB)
- El comando `cleanup` encuentra cientos o miles de archivos corruptos
- Los errores dicen `ValueError: CDN devolvió HTML en vez de PDF`

### Soluciones

**1. Bajar workers y añadir delay (lo más importante)**
```bash
# Máximo 2-3 workers con pausa de 1 segundo entre requests
uv run verifacta download -w 2 --delay 1.0
```

**2. Descargar de noche o en horas de bajo tráfico**
El CDN es más permisivo cuando hay menos carga. Programar descargas en la madrugada reduce bloqueos notablemente.

**3. Limpiar y re-descargar**
```bash
# Primero identificar corruptos
uv run verifacta cleanup --dry-run

# Luego eliminarlos
uv run verifacta cleanup

# Re-descargar con configuración conservadora
uv run verifacta download -w 2 --delay 1.0
```

El downloader es idempotente: si el archivo ya existe y es válido, lo salta.

**4. Descargar por departamentos en lotes**
En vez de descargar todo de una vez, descargar departamento por departamento con pausas entre lotes:
```bash
uv run verifacta download --dept 01 -w 2 --delay 1.0  # Antioquia
# esperar unos minutos
uv run verifacta download --dept 16 -w 2 --delay 1.0  # Bogotá
```

**5. Verificar si el CDN está bloqueando tu IP**
Si todos los PDFs salen corruptos inmediatamente (sin importar el delay), tu IP puede estar temporalmente bloqueada. Espera 15-30 minutos antes de reintentar.

## Tests

```bash
uv run pytest
```

## Contribuir

Este es un proyecto voluntario de veeduría ciudadana. Si encontrás actas con anomalías, verificá manualmente en el sitio oficial antes de divulgar:
`https://e14segundavueltapresidente.registraduria.gov.co`
