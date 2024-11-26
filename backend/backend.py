from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
import PyPDF2
from openai import OpenAI
import psycopg2
from dotenv import load_dotenv
import json
from datetime import datetime

# Lade Umgebungsvariablen
load_dotenv()

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

# Erstelle Upload-Ordner, falls nicht vorhanden
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# OpenAI Client initialisieren
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    return psycopg2.connect(os.getenv('DATABASE_URL'))

def extract_text_from_pdf(file_path):
    print(f"Starte PDF-Extraktion von: {file_path}")
    text = ""
    with open(file_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        for page_num, page in enumerate(pdf_reader.pages, 1):
            print(f"Verarbeite Seite {page_num} von {len(pdf_reader.pages)}")
            text += page.extract_text()
    print(f"PDF-Extraktion abgeschlossen. Extrahierter Text: {text[:200]}...")
    return text

def execute_database_query(query_params):
    print("Führe Datenbankabfrage aus:", json.dumps(query_params, indent=2))
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Basis-Query erstellen
        select_clause = ", ".join(query_params["columns"])
        query = f"SELECT {select_clause} FROM {query_params['table_name']}"
        
        # WHERE-Bedingungen hinzufügen
        params = []
        if query_params["conditions"]:
            conditions = []
            for condition in query_params["conditions"]:
                if isinstance(condition["value"], dict):
                    # Vergleich mit einer anderen Spalte
                    conditions.append(
                        f"{condition['column']} {condition['operator']} {condition['value']['column_name']}"
                    )
                else:
                    conditions.append(f"{condition['column']} {condition['operator']} %s")
                    params.append(condition["value"])
            
            query += " WHERE " + " AND ".join(conditions)
        
        # Sortierung hinzufügen
        if query_params.get("order_by"):
            query += f" ORDER BY {select_clause.split(',')[0]} {query_params['order_by']}"
        
        print(f"Ausgeführte Query: {query} mit Parametern: {params}")
        cur.execute(query, params)
        results = cur.fetchall()
        
        # Spaltennamen für das Ergebnis
        column_names = [desc[0] for desc in cur.description]
        
        # Ergebnisse als Liste von Dictionaries formatieren
        formatted_results = [
            dict(zip(column_names, row))
            for row in results
        ]
        
        return True, formatted_results

    except Exception as e:
        print(f"Datenbankfehler: {str(e)}")
        return False, str(e)
    finally:
        cur.close()
        conn.close()

def process_with_openai(text, system_message):
    print("Sende Anfrage an OpenAI API...")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "extract_invoice_data",
                "description": """Extrahiert strukturierte Daten aus einer Rechnung.
                Alle Datumsangaben müssen im Format YYYY-MM-DD sein (Beispiel: 2024-11-19).""",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kunde": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "strasse": {"type": "string"},
                                "plz": {"type": "string"},
                                "ort": {"type": "string"},
                                "land": {"type": "string"}
                            },
                            "required": ["name", "strasse", "plz", "ort", "land"],
                            "additionalProperties": False
                        },
                        "rechnung": {
                            "type": "object",
                            "properties": {
                                "bestellnummer": {"type": "string"},
                                "rechnungsnummer": {"type": "string"},
                                "rechnungsdatum": {
                                    "type": "string",
                                    "description": "Datum im Format YYYY-MM-DD"
                                },
                                "leistungszeitraum_start": {
                                    "type": "string",
                                    "description": "Datum im Format YYYY-MM-DD"
                                },
                                "leistungszeitraum_ende": {
                                    "type": "string",
                                    "description": "Datum im Format YYYY-MM-DD"
                                },
                                "gesamtbetrag": {"type": "number"},
                                "mwst_prozent": {"type": "number"},
                                "mwst_betrag": {"type": "number"},
                                "bezahlt": {"type": "boolean"}
                            },
                            "required": [
                                "bestellnummer",
                                "rechnungsnummer",
                                "rechnungsdatum",
                                "leistungszeitraum_start",
                                "leistungszeitraum_ende",
                                "gesamtbetrag",
                                "mwst_prozent",
                                "mwst_betrag",
                                "bezahlt"
                            ],
                            "additionalProperties": False
                        },
                        "produkte": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "bezeichnung": {"type": "string"},
                                    "monatlicher_preis": {"type": "number"},
                                    "anzahl": {"type": "integer"},
                                    "preis": {"type": "number"}
                                },
                                "required": ["bezeichnung", "monatlicher_preis", "anzahl", "preis"],
                                "additionalProperties": False
                            }
                        },
                        "nachlaesse": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "typ": {"type": "string"},
                                    "betrag": {"type": "number"}
                                },
                                "required": ["typ", "betrag"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["kunde", "rechnung", "produkte", "nachlaesse"],
                    "additionalProperties": False
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_database",
                "description": "Führt eine Datenbankabfrage aus.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "enum": ["rechnungen", "kunden", "produkte", "rechnungsposten", "nachlaesse"]
                        },
                        "columns": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "rechnungs_id", "bestellnummer", "rechnungsnummer",
                                    "rechnungsdatum", "leistungszeitraum_start",
                                    "leistungszeitraum_ende", "kunden_id", "gesamtbetrag",
                                    "mwst_prozent", "mwst_betrag", "bezahlt",
                                    "name", "strasse", "plz", "ort", "land",
                                    "bezeichnung", "monatlicher_preis", "anzahl", "preis",
                                    "typ", "betrag"
                                ]
                            }
                        },
                        "conditions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "column": {"type": "string"},
                                    "operator": {
                                        "type": "string",
                                        "enum": ["=", ">", "<", ">=", "<=", "!="]
                                    },
                                    "value": {
                                        "anyOf": [
                                            {"type": "string"},
                                            {"type": "number"},
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "column_name": {"type": "string"}
                                                },
                                                "required": ["column_name"],
                                                "additionalProperties": False
                                            }
                                        ]
                                    }
                                },
                                "required": ["column", "operator", "value"],
                                "additionalProperties": False
                            }
                        },
                        "order_by": {
                            "type": "string",
                            "enum": ["asc", "desc"]
                        }
                    },
                    "required": ["table_name", "columns", "conditions", "order_by"],
                    "additionalProperties": False
                }
            }
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": text}
        ],
        tools=tools
    )
    
    tool_call = response.choices[0].message.tool_calls[0]
    result = json.loads(tool_call.function.arguments)
    
    if tool_call.function.name == "extract_invoice_data":
        return "extract", result
    else:
        return "query", result

def save_to_database(data):
    print("Starte Datenbankverbindung...")
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Prüfe ob Kunde bereits existiert
        print(f"Prüfe ob Kunde existiert: {data['kunde']['name']}")
        cur.execute("""
            SELECT kunden_id 
            FROM kunden 
            WHERE name = %s 
            AND strasse = %s 
            AND plz = %s 
            AND ort = %s 
            AND land = %s
        """, (
            data['kunde']['name'],
            data['kunde']['strasse'],
            data['kunde']['plz'],
            data['kunde']['ort'],
            data['kunde']['land']
        ))
        
        result = cur.fetchone()
        
        if result:
            kunden_id = result[0]
            print(f"Bestehender Kunde gefunden mit ID: {kunden_id}")
        else:
            # Kunde existiert nicht, füge neuen Kunden ein
            print(f"Füge neuen Kunden ein: {data['kunde']['name']}")
            cur.execute("""
                INSERT INTO kunden (name, strasse, plz, ort, land)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING kunden_id
            """, (
                data['kunde']['name'],
                data['kunde']['strasse'],
                data['kunde']['plz'],
                data['kunde']['ort'],
                data['kunde']['land']
            ))
            kunden_id = cur.fetchone()[0]
            print(f"Neuer Kunde eingefügt mit ID: {kunden_id}")

        # Rechnung einfügen
        print(f"Füge Rechnung ein: {data['rechnung']['rechnungsnummer']}")
        cur.execute("""
            INSERT INTO rechnungen (
                bestellnummer, rechnungsnummer, rechnungsdatum,
                leistungszeitraum_start, leistungszeitraum_ende,
                kunden_id, gesamtbetrag, mwst_prozent, mwst_betrag, bezahlt
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING rechnungs_id
        """, (
            data['rechnung']['bestellnummer'],
            data['rechnung']['rechnungsnummer'],
            data['rechnung']['rechnungsdatum'],
            data['rechnung']['leistungszeitraum_start'],
            data['rechnung']['leistungszeitraum_ende'],
            kunden_id,
            data['rechnung']['gesamtbetrag'],
            data['rechnung']['mwst_prozent'],
            data['rechnung']['mwst_betrag'],
            data['rechnung']['bezahlt']
        ))
        rechnungs_id = cur.fetchone()[0]
        print(f"Rechnung eingefügt mit ID: {rechnungs_id}")

        # Produkte und Rechnungsposten einfügen
        print("Füge Produkte und Rechnungsposten ein...")
        for produkt in data['produkte']:
            print(f"Verarbeite Produkt: {produkt['bezeichnung']}")
            cur.execute("""
                INSERT INTO produkte (bezeichnung, monatlicher_preis)
                VALUES (%s, %s)
                RETURNING produkt_id
            """, (
                produkt['bezeichnung'],
                produkt['monatlicher_preis']
            ))
            produkt_id = cur.fetchone()[0]
            print(f"Produkt eingefügt mit ID: {produkt_id}")

            cur.execute("""
                INSERT INTO rechnungsposten (rechnungs_id, produkt_id, anzahl, preis)
                VALUES (%s, %s, %s, %s)
            """, (
                rechnungs_id,
                produkt_id,
                produkt['anzahl'],
                produkt['preis']
            ))
            print(f"Rechnungsposten für Produkt {produkt_id} eingefügt")

        # Nachlässe einfügen
        if data['nachlaesse']:
            print("Füge Nachlässe ein...")
            for nachlass in data['nachlaesse']:
                print(f"Verarbeite Nachlass: {nachlass['typ']}")
                cur.execute("""
                    INSERT INTO nachlaesse (rechnungs_id, typ, betrag)
                    VALUES (%s, %s, %s)
                """, (
                    rechnungs_id,
                    nachlass['typ'],
                    nachlass['betrag']
                ))

        conn.commit()
        print("Datenbankoperationen erfolgreich abgeschlossen")
        return True, "Daten erfolgreich gespeichert"

    except Exception as e:
        print(f"Datenbankfehler aufgetreten: {str(e)}")
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()
        print("Datenbankverbindung geschlossen")

@app.route('/process', methods=['POST'])
def process_request():
    data = request.json
    if not data or 'text' not in data or 'system_message' not in data:
        return jsonify({'error': 'Fehlende Eingabedaten'}), 400

    try:
        action, result = process_with_openai(data['text'], data['system_message'])
        
        if action == "extract":
            success, message = save_to_database(result)
            if success:
                return jsonify({
                    'message': 'Rechnung erfolgreich verarbeitet',
                    'data': result
                }), 200
            else:
                return jsonify({
                    'error': 'Datenbankfehler',
                    'details': message
                }), 500
        else:  # action == "query"
            success, query_results = execute_database_query(result)
            if success:
                return jsonify({
                    'message': 'Abfrage erfolgreich',
                    'data': query_results
                }), 200
            else:
                return jsonify({
                    'error': 'Abfragefehler',
                    'details': query_results
                }), 500

    except Exception as e:
        return jsonify({
            'error': 'Verarbeitungsfehler',
            'details': str(e)
        }), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    print("Neue Upload-Anfrage erhalten")
    if 'file' not in request.files:
        print("Fehler: Kein Dateiteil in der Anfrage")
        return jsonify({'error': 'Kein Dateiteil'}), 400
    
    file = request.files['file']
    if file.filename == '':
        print("Fehler: Leerer Dateiname")
        return jsonify({'error': 'Keine ausgewählte Datei'}), 400
    
    if file and allowed_file(file.filename):
        try:
            print(f"Verarbeite Datei: {file.filename}")
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(file_path)
            print(f"Datei gespeichert unter: {file_path}")

            print("Extrahiere Text aus PDF...")
            text = extract_text_from_pdf(file_path)

            print("Analysiere Text mit OpenAI...")
            system_message = """Du bist ein Assistent, der Rechnungsdaten extrahiert.
            Wichtig: Formatiere alle Datumsangaben immer im Format YYYY-MM-DD (Beispiel: 2024-11-19).
            Verwende ausschließlich dieses Format für alle Datumsangaben."""
            
            action, analysis_result = process_with_openai(text, system_message)

            if action != "extract":
                raise ValueError("Unerwartete Antwort von OpenAI")

            print("Speichere Ergebnisse in Datenbank...")
            success, message = save_to_database(analysis_result)

            print(f"Lösche temporäre Datei: {file_path}")
            os.remove(file_path)

            if success:
                print("Verarbeitung erfolgreich abgeschlossen")
                return jsonify({
                    'message': 'Rechnung erfolgreich verarbeitet',
                    'data': analysis_result
                }), 200
            else:
                print(f"Datenbankfehler: {message}")
                return jsonify({
                    'error': 'Datenbankfehler',
                    'details': message
                }), 500

        except Exception as e:
            print(f"Fehler bei der Verarbeitung: {str(e)}")
            if os.path.exists(file_path):
                print(f"Lösche temporäre Datei nach Fehler: {file_path}")
                os.remove(file_path)
            return jsonify({
                'error': 'Verarbeitungsfehler',
                'details': str(e)
            }), 500

    print(f"Nicht erlaubter Dateityp: {file.filename}")
    return jsonify({'error': 'Dateityp nicht erlaubt'}), 400

if __name__ == '__main__':
    app.run(port=5002,debug=True)