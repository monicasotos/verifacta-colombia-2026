# Verifacta Colombia 2026

Proyecto de veeduría electoral: descarga y análisis de actas E14 de la Registraduría Nacional para detectar tachones (números enmendados), inconsistencias aritméticas y firmas faltantes en los resultados de la segunda vuelta presidencial del 21 de junio de 2026.

## Comandos esenciales

```bash
# Instalar dependencias
uv sync

# Correr tests
uv run pytest

# CLI principal
uv run verifacta --help

# Descargar actas (todos los departamentos, 10 workers paralelos)
uv run verifacta download
uv run verifacta download --dept 01          # solo Antioquia (código interno API)
uv run verifacta download --limit 100 -w 20  # 100 actas con 20 workers

# Analizar actas con Gemini Vision
uv run verifacta analyze --sample downloads/
uv run verifacta analyze --sample sample_files/ANTIOQUIA_TURBO_Z03_P02_M1/
```

## Arquitectura

```
src/verifacta/
├── scraper/
│   ├── client.py       # httpx async; departamentos hardcodeados, JSON estático para actas
│   ├── models.py       # Pydantic: Departamento, Municipio, Zona, Puesto, Mesa
│   ├── downloader.py   # Orquesta descargas paralelas; skip si archivo ya existe
│   └── sampler.py      # Muestreo proporcional por municipio para análisis
├── analysis/
│   ├── extractor.py    # PDF → imágenes PNG via pymupdf
│   └── detector.py     # Detección de anomalías via Gemini Vision (votos + tachones + firmas)
├── storage/
│   └── repository.py   # SQLite via sqlalchemy (pendiente)
└── cli.py              # CLI typer: download, analyze, report
```

## Fuente de datos

- **Catálogo de actas**: JSON estático `allTransmissionCodes.json` (~36MB, ~122k actas)
  - URL: `https://e14segundavueltapresidente.registraduria.gov.co/assets/temis/divipol_json/allTransmissionCodes.json`
  - Se cachea localmente en `scripts/allTransmissionCodes.json` (gitignored)
  - Tiene dos secciones: `status3` (13 actas pendientes) y `status11` (121,890 disponibles)
- **PDFs**: `https://e14segundavueltapresidente.registraduria.gov.co/assets/temis/pdf/{dept}/{muni}/{zona}/{puesto}/{mesa}/PRE/{hash}.pdf`
- **Sin GraphQL ni auth**: el sitio bloquea requests automáticas al CDN intermitentemente

## Convenciones

- **Carpeta de descarga**: `downloads/{DPTO}_{MUNI_CODE}_Z{ZONA}_P{PUESTO}_M{MESA}/`
  - Ej: `downloads/ANTIOQUIA_280_Z03_P02_M1/`
  - `MUNI_CODE` es el código interno de la API (no el código DANE)
- **Nombre de archivo**: preservar el hash original del servidor
- **Skip idempotente**: si el archivo ya existe, no re-descargar
- **Prioridad de descarga**: departamentos ordenados por población (Bogotá primero)
- **Códigos de departamento**: internos de la API (NO son DANE). Ej: Antioquia=01, Bogotá=16, Valle=31

## Tipos de actas E14

Cada mesa tiene (potencialmente) dos versiones:
- **TRANSMISIÓN**: blanco/negro, nombre hash — versión digitalizada (descargamos estas)
- **CLAVEROS**: a color con fotos de candidatos, nombre `E14_PRE_*.pdf` — no disponibles aún

## Detección de anomalías (Gemini Vision)

Una sola llamada por acta analiza ambas páginas y retorna JSON con:
1. Votos por candidato + totales
2. **Consistencia**: `candidato_1 + candidato_2 + blancos + nulos + no_marcados == suma_total`
3. **Tachones**: números tachados, enmendados o con corrector
4. **Firmas faltantes**: alguna de las 6 cajas de jurados en página 2 vacía

## Variables de entorno (.env)

```
GEMINI_API_KEY=...    # requerido para analyze
OPENAI_API_KEY=...    # alternativa (usar gpt-5.4)
```

## Scripts de referencia

```
scripts/
├── 100_municipios_mas_poblados.csv   # referencia para muestreo
└── allTransmissionCodes.json         # caché local del catálogo (gitignored, ~36MB)
```