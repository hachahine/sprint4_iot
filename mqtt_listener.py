import paho.mqtt.client as mqtt
import oracledb
import json
from decouple import config

# --- Configurações ---
ORACLE_USER = config("ORACLE_USER")
ORACLE_PASS = config("ORACLE_PASS")
ORACLE_DSN = config("ORACLE_DSN")
MQTT_BROKER = 'test.mosquitto.org'
MQTT_TOPIC = "iot/devices/status" 

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Listener conectado ao MQTT Broker!")
        client.subscribe(MQTT_TOPIC)
        print(f"Inscrito no tópico: {MQTT_TOPIC}")
    else:
        print(f"Falha na conexão com MQTT, código: {rc}\n")

def on_message(client, userdata, msg):
    """Callback para ATUALIZAR o status do device no Oracle DB."""
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
        
        device_code = data.get('device_code')
        status = data.get('status')
        distancia = data.get('distancia')
        # --- REMOVIDO: Leitura de lat/lon ---
        # lat = data.get('latitude')
        # lon = data.get('longitude')

        if not device_code:
            print("Mensagem recebida sem device_code. Ignorando.")
            return

        # --- LÓGICA PRINCIPAL MODIFICADA ---
        # Atualiza apenas status, distance e timestamp
        cursor.execute(
            """
            UPDATE devices 
            SET 
                spot_status = :1, 
                distance = :2, 
                reading_timestamp = SYSTIMESTAMP
            WHERE 
                code = :3
            """,
            (status, distancia, device_code)
        )
        db_conn.commit()
        
        # Lógica para remover moto_id se disponível permanece
        if status == 'disponivel':
            cursor.execute(
                """
                UPDATE devices SET motorcycle_id = NULL WHERE code = :1
                """,
                (device_code,)
            )
            db_conn.commit()

        print(f"Device {device_code} atualizado: Status={status}")

    except json.JSONDecodeError:
        print(f"Payload não é um JSON válido: {payload}")
    except Exception as e:
        print(f"Erro ao processar mensagem ou atualizar banco: {e}")

# --- Conexão com o Banco de Dados ---
try:
    db_conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASS, dsn=ORACLE_DSN)
    cursor = db_conn.cursor()
    print("Listener conectado ao Oracle DB com sucesso.")
except Exception as e:
    print(f"Erro fatal ao conectar ao Oracle DB: {e}")
    exit()

# --- Configuração do Cliente MQTT ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="OracleListenerServiceNoGeo")
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, 1883, 60)

print("Listener MQTT iniciado. Aguardando mensagens...")
client.loop_forever()
