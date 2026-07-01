"""
Detecta anomalías en actas E14 usando Gemini Vision o GPT-4 Vision.

Analiza cada acta en un solo call: extrae votos, verifica consistencia,
detecta tachones y verifica firmas de jurados. Asigna severidad.
"""
import base64
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .extractor import pdf_to_images

load_dotenv()

logger = logging.getLogger(__name__)

PROMPT = """Eres un auditor electoral analizando un acta E14 de escrutinio de Colombia.
Se te dan las imágenes de las dos páginas del acta.

CONTEXTO IMPORTANTE sobre el formato del acta:
Por ley colombiana, los espacios vacíos a la IZQUIERDA de los números deben rellenarse con
símbolos de seguridad (X, *, +, O, líneas, puntos, etc.) para impedir que se añadan dígitos
después. Esto es NORMAL y obligatorio. Por ejemplo, si un candidato obtuvo 9 votos, el campo
puede verse como "XX9", "**9", "OO9", "++++9", etc. Estos rellenos NO son tachones.

ESTRATEGIA: antes de evaluar cualquier campo, observa el patrón de relleno que usa el jurado
en TODO el formulario. Cada persona tiene un estilo consistente: siempre usa X, o siempre usa *,
o siempre usa rayas, etc. Una vez identificado ese estilo, úsalo como referencia — si en un campo
aparece algo que NO encaja con ese patrón, ahí puede haber una modificación real.

Un TACHÓN es algo completamente distinto: es cuando alguien dibuja ENCIMA de un número o
símbolo ya escrito para cambiar su valor. Ejemplos de tachones reales:
- Una raya horizontal o diagonal cruzando un dígito (tachado clásico)
- Corrector líquido (tipex/liquid paper) aplicado sobre un número, con otro número encima
- Un dígito escrito encima o al lado de otro para modificarlo
- Una raya vertical trazada sobre un símbolo de relleno (*) para convertirlo en otro dígito (ej: * → 0 o 1)
- Cualquier modificación visible sobre un número ya escrito

CASO ESPECIAL — dígito añadido ENCIMA de un relleno (fraude grave):
El jurado escribe legítimamente "***9" (9 votos). Después, alguien escribe un dígito (p.ej. "1")
encima de uno de los asteriscos, convirtiendo "***9" en algo que visualmente parece "1**9" o "109".
Señales de este fraude:
- Uno de los símbolos de relleno tiene trazos extra que lo hacen parecer un dígito numérico
- El estilo de un símbolo es inconsistente con los demás del mismo campo o del formulario
- Un dígito "sobresale" visualmente entre los rellenos uniformes
- El número resultante es incongruente con los demás campos del acta
Este caso SIEMPRE es tachón con severidad "grave", incluso si el relleno subyacente sigue visible.

En resumen: los RELLENOS uniformes a la izquierda son normales. Cualquier trazo SOBRE un relleno
o dígito ya escrito — incluyendo dígitos escritos encima de rellenos — es un tachón.

NIVELES DE SEVERIDAD — asigna uno de estos valores a "severidad":
- "grave": tachones o modificaciones en los campos de CANDIDATOS (candidato_1, candidato_2)
            o en el campo SUMA TOTAL; O más de 2 firmas de jurado completamente ausentes.
- "moderado": inconsistencia aritmética (los votos no suman el total declarado);
              tachones en blancos, nulos o no_marcados;
              1 o 2 firmas de jurado faltantes.
- "leve": una firma en el cuadro equivocado (presente pero mal ubicada);
          anomalías menores que no afectan el conteo de votos.
- null: sin ninguna anomalía.

Extrae la siguiente información y responde SOLO con un objeto JSON válido, sin texto adicional:

{
  "votos": {
    "candidato_1": <número entero o null si no se puede leer>,
    "candidato_2": <número entero o null si no se puede leer>,
    "blancos": <número entero o null>,
    "nulos": <número entero o null>,
    "no_marcados": <número entero o null>,
    "suma_total": <número entero que aparece en el campo SUMA TOTAL del acta, o null>
  },
  "consistencia_ok": <true si candidato_1 + candidato_2 + blancos + nulos + no_marcados == suma_total, false si no cuadra, null si no se puede calcular>,
  "tachones": <true SOLO si ves modificaciones sobre dígitos ya escritos (tachado, corrector, sobreescritura). Los rellenos de seguridad a la izquierda (X, *, +, O, etc.) NO cuentan como tachones.>,
  "tachon_campos": <lista de strings con los campos que tienen modificaciones reales, ej: ["candidato_1", "blancos"]. Vacío [] si no hay tachones.>,
  "firmas_faltantes": <true si alguna de las 6 cajas de firma de jurados en la página 2 está completamente vacía>,
  "firmas_detalle": <string describiendo cuántas y cuáles firmas faltan o están mal ubicadas, o null si todo está correcto>,
  "severidad": <"grave" | "moderado" | "leve" | null según los criterios definidos arriba>,
  "observaciones": <string con cualquier otra anomalía notable, o null>
}

Sé preciso al leer los números — los rellenos de seguridad a la izquierda se ignoran, solo lees los dígitos reales.
"""


class AnomalyResult:
    """Resultado del análisis de una acta."""

    def __init__(self, raw: dict):
        self.votos = raw.get("votos", {})
        self.consistencia_ok = raw.get("consistencia_ok")
        self.tachones = raw.get("tachones", False)
        self.tachon_campos = raw.get("tachon_campos", [])
        self.firmas_faltantes = raw.get("firmas_faltantes", False)
        self.firmas_detalle = raw.get("firmas_detalle")
        self.severidad = raw.get("severidad")
        self.observaciones = raw.get("observaciones")

    @property
    def flagged(self) -> bool:
        return bool(
            self.consistencia_ok is False
            or self.tachones
            or self.firmas_faltantes
        )

    def to_dict(self) -> dict:
        return {
            "votos": self.votos,
            "consistencia_ok": self.consistencia_ok,
            "tachones": self.tachones,
            "tachon_campos": self.tachon_campos,
            "firmas_faltantes": self.firmas_faltantes,
            "firmas_detalle": self.firmas_detalle,
            "severidad": self.severidad,
            "observaciones": self.observaciones,
            "flagged": self.flagged,
        }


async def _analyze_gemini(pdf_path: Path, model: str) -> AnomalyResult:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY no configurada en .env")

    client = genai.Client(api_key=api_key)
    images = pdf_to_images(pdf_path)
    if not images:
        raise ValueError(f"PDF vacío: {pdf_path}")

    parts: list = [PROMPT]
    for img_bytes in images:
        parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))

    response = await client.aio.models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )

    return _parse_response(response.text)


async def _analyze_openai(pdf_path: Path, model: str) -> AnomalyResult:
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY no configurada en .env")

    client = AsyncOpenAI(api_key=api_key)
    images = pdf_to_images(pdf_path)
    if not images:
        raise ValueError(f"PDF vacío: {pdf_path}")

    content: list = [{"type": "text", "text": PROMPT}]
    for img_bytes in images:
        b64 = base64.b64encode(img_bytes).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
        })

    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_object"},
        temperature=0,
    )

    return _parse_response(response.choices[0].message.content)


def _parse_response(text: str) -> AnomalyResult:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return AnomalyResult(json.loads(text))


async def analyze_pdf(pdf_path: Path, model: str = "gemini-2.5-flash") -> AnomalyResult:
    """
    Analiza un acta E14 con Gemini Vision o GPT Vision.

    Dispatch automático: modelos que empiezan con "gpt-" usan OpenAI,
    el resto usa Gemini.
    """
    if model.startswith("gpt-"):
        return await _analyze_openai(pdf_path, model)
    return await _analyze_gemini(pdf_path, model)
