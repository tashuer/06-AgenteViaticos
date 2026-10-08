import os
import sys

from dotenv import load_dotenv
from google import genai

MODELO = "gemini-3.5-flash-lite"
INSTRUCCIONES = "Responde como cavernicola, en un máximo de tres frases."

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

if len(sys.argv) < 2:
    sys.exit('Uso: python agente.py "tu pregunta"')

interaccion = client.interactions.create(
    model=MODELO,
    input=" ".join(sys.argv[1:]),
    system_instruction=INSTRUCCIONES,
)
print(interaccion.output_text)
