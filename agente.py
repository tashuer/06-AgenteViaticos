import csv
import json
import os
import sys
import unicodedata
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from google import genai

MODELO = "gemini-3.5-flash-lite"
RUTA_INSTRUCCIONES = Path(__file__).parent / "prompts" / "sistema.md"
RUTA_CONOCIMIENTO = Path(__file__).parent / "conocimiento"
RUTA_GASTOS = RUTA_CONOCIMIENTO / "gastos.csv"
RUTA_SOLICITUDES = Path(__file__).parent / "solicitudes.csv"
CAMPOS_SOLICITUD = [
    "radicado", "fecha_registro", "empleado", "ciudad", "fecha_salida",
    "noches", "motivo", "estado",
]
ESTADO_SOLICITUD = "Pendiente de aprobación del jefe inmediato"
MAX_VUELTAS = 5


def cargar_documentos():
    documentos = []
    for ruta in sorted(RUTA_CONOCIMIENTO.iterdir()):
        if ruta.is_file() and ruta.suffix == ".md":
            texto = ruta.read_text(encoding="utf-8").strip()
            documentos.append(f'<documento nombre="{ruta.name}">\n{texto}\n</documento>')
    return "\n\n".join(documentos)


def normalizar(texto):
    sin_tildes = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return sin_tildes.casefold().strip()


def sumar_gastos(area=None, estado=None):
    filas = 0
    total = 0
    with open(RUTA_GASTOS, encoding="utf-8", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            if area and normalizar(fila["area"]) != normalizar(area):
                continue
            if estado and normalizar(fila["estado"]) != normalizar(estado):
                continue
            filas += 1
            total += int(fila["valor_cop"])
    return {"filas": filas, "total_cop": total}


def registrar_solicitud(empleado, ciudad, fecha_salida, noches, motivo):
    existe = RUTA_SOLICITUDES.exists()
    consecutivo = 1
    if existe:
        with open(RUTA_SOLICITUDES, encoding="utf-8", newline="") as archivo:
            consecutivo += sum(1 for _ in csv.DictReader(archivo))
    radicado = f"S-{consecutivo:03d}"
    with open(RUTA_SOLICITUDES, "a", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_SOLICITUD)
        if not existe:
            escritor.writeheader()
        escritor.writerow({
            "radicado": radicado,
            "fecha_registro": date.today().isoformat(),
            "empleado": empleado,
            "ciudad": ciudad,
            "fecha_salida": fecha_salida,
            "noches": int(noches),
            "motivo": motivo,
            "estado": ESTADO_SOLICITUD,
        })
    return {"radicado": radicado}


FUNCIONES = {
    "sumar_gastos": sumar_gastos,
    "registrar_solicitud": registrar_solicitud,
}

HERRAMIENTAS = [
    {
        "type": "function",
        "name": "sumar_gastos",
        "description": (
            "Cuenta y suma los gastos registrados en gastos.csv. Úsala siempre que "
            "pregunten cuántos gastos hay o cuánto suman en total, opcionalmente "
            "filtrando por área y/o por estado. Devuelve el número de gastos y el "
            "total en pesos colombianos (COP). No sirve para registrar solicitudes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "area": {
                    "type": "string",
                    "description": "Área del empleado, por ejemplo Ventas u Operaciones. Omítelo para incluir todas las áreas.",
                },
                "estado": {
                    "type": "string",
                    "description": "Estado del gasto: Aprobado, Pendiente o Rechazado. Omítelo para incluir todos los estados.",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "registrar_solicitud",
        "description": (
            "Registra una solicitud de viaje nueva y devuelve su radicado. Úsala solo "
            "cuando el empleado pida registrar o radicar una solicitud y ya tengas los "
            "cinco datos. No la uses para consultar gastos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "empleado": {"type": "string", "description": "Nombre completo del empleado que viaja."},
                "ciudad": {"type": "string", "description": "Ciudad de destino del viaje."},
                "fecha_salida": {"type": "string", "description": "Fecha de salida en formato AAAA-MM-DD."},
                "noches": {"type": "integer", "description": "Número de noches del viaje."},
                "motivo": {"type": "string", "description": "Motivo del viaje."},
            },
            "required": ["empleado", "ciudad", "fecha_salida", "noches", "motivo"],
        },
    },
]


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
        tools=HERRAMIENTAS,
        previous_interaction_id=anterior_id,
    )


def ejecutar_herramienta(llamada):
    funcion = FUNCIONES.get(llamada.name)
    es_error = False
    try:
        if funcion is None:
            raise ValueError(f"Herramienta desconocida: {llamada.name}")
        resultado = funcion(**llamada.arguments)
    except Exception as error:
        resultado = {"error": str(error)}
        es_error = True
    print(f"[herramienta] {llamada.name}({llamada.arguments}) -> {resultado}")
    return {
        "type": "function_result",
        "call_id": llamada.id,
        "name": llamada.name,
        "result": json.dumps(resultado, ensure_ascii=False),
        "is_error": es_error,
    }


def responder(mensaje, anterior_id=None):
    interaccion = preguntar(mensaje, anterior_id)
    for _ in range(MAX_VUELTAS):
        llamadas = [p for p in interaccion.steps or [] if p.type == "function_call"]
        if not llamadas:
            break
        resultados = [ejecutar_herramienta(llamada) for llamada in llamadas]
        interaccion = preguntar(resultados, interaccion.id)
    return interaccion


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

    interaccion = responder(mensaje, anterior_id)
    anterior_id = interaccion.id
    print(f"\nAsistente: {interaccion.output_text}\n")
    mensaje = ""
