import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

MODELO = "gemini-3.5-flash-lite"
RUTA_INSTRUCCIONES = Path(__file__).parent / "prompts" / "sistema.md"
RUTA_CONOCIMIENTO = Path(__file__).parent / "conocimiento"


def cargar_documentos():
    documentos = []
    for ruta in sorted(RUTA_CONOCIMIENTO.iterdir()):
        if ruta.is_file():
            texto = ruta.read_text(encoding="utf-8").strip()
            documentos.append(f'<documento nombre="{ruta.name}">\n{texto}\n</documento>')
    return "\n\n".join(documentos)


INSTRUCCIONES = (
    RUTA_INSTRUCCIONES.read_text(encoding="utf-8").strip()
    + "\n\n"
    + cargar_documentos()
)

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SALIR = {"salir", "exit", "quit"}


def preguntar(mensaje, anterior_id=None):
    return client.interactions.create(
        model=MODELO,
        input=mensaje,
        system_instruction=INSTRUCCIONES,
        previous_interaction_id=anterior_id,
    )


print('Asistente de viáticos. Escribe "salir" para terminar.\n')

# Si se pasa una pregunta como argumento, es el primer mensaje de la conversación.
mensaje = " ".join(sys.argv[1:]).strip()
anterior_id = None

while True:
    if not mensaje:
        try:
            mensaje = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not mensaje:
            continue
    if mensaje.lower() in SALIR:
        break

    interaccion = preguntar(mensaje, anterior_id)
    anterior_id = interaccion.id
    print(f"\nAsistente: {interaccion.output_text}\n")
    mensaje = ""
