import streamlit as st
import pandas as pd
import math
import paho.mqtt.client as mqtt
import time
from decouple import config
from streamlit_autorefresh import st_autorefresh
from sqlalchemy import create_engine

# variaveis de ambiente
ORACLE_USER = config("ORACLE_USER")
ORACLE_PASS = config("ORACLE_PASS")
ORACLE_DSN = config("ORACLE_DSN")
MQTT_BROKER = 'test.mosquitto.org'
MQTT_PORT = 1883
DB_URI = f"oracle+oracledb://{ORACLE_USER}:{ORACLE_PASS}@{ORACLE_DSN}"



st.set_page_config(layout="wide")

# carregar o css do projeto
def load_css(file_name):
    try:
        with open(file_name, encoding='utf-8') as file:
            st.markdown(f'<style>{file.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"Arquivo de estilo '{file_name}' não encontrado. Crie 'style.css' na mesma pasta.")
    except UnicodeDecodeError:
        st.error(f"Erro ao decodificar '{file_name}'. Salve como UTF-8.")

load_css("style.css")


# refresh na pagina a cada 10 segundos
st_autorefresh(interval=5000, key="data_refresher")


if 'selected_sensor' not in st.session_state:
    st.session_state.selected_sensor = None



@st.cache_data(ttl=5)
def fetch_patio_status() -> pd.DataFrame:
    """Busca o status atual de todos os devices"""

    engine = create_engine(DB_URI)
    query = """
    SELECT
        d.code AS SENSOR_ID,
        d.spot_status AS STATUS_VAGA,
        d.id_yard AS PATIO_ID,
        y.name AS NOME_PATIO,
        m.license AS MOTO_PLACA
    FROM
        devices d
    LEFT JOIN
        yards y ON d.id_yard = y.id
    LEFT JOIN
        motorcycles m ON d.motorcycle_id = m.id
    ORDER BY
        y.name, d.code
    """

    try:
        df = pd.read_sql(query, engine)
        df.columns = [col.lower() for col in df.columns]
        df['nome_patio'] = df['nome_patio'].astype(str).fillna('Pátio Desconhecido')
        return df

    except Exception as e:
        st.error(f"Erro ao conectar ou buscar dados no Oracle DB: {e}")
        return pd.DataFrame()



def enviar_comando_mqtt(device_id, comando):
    """conecta, envia um comando e desconecta do MQTT."""

    target_topic = f"iot/devices/{device_id}/comando"
    client = None

    try:
        client_id_cmd = f"streamlit_cmd_{int(time.time())}_{device_id}"
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id_cmd)
        # Timeout de conexão curto para não travar o app
        client.connect(MQTT_BROKER, MQTT_PORT, 10) 
        client.loop_start()
        result = client.publish(target_topic, comando)
        # Timeout curto para publicação
        result.wait_for_publish(timeout=3) 
        client.loop_stop()

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            st.toast(f"Comando '{comando}' enviado para {device_id}!", icon="✅")
            print(f"Comando '{comando}' enviado para '{target_topic}'")

        else:
            st.error(f"Falha ao enviar comando para {device_id} (rc={result.rc})")
            print(f"Falha ao enviar comando para {target_topic} (rc={result.rc})")

    except Exception as e:
        st.error(f"Erro ao conectar/enviar comando MQTT: {e}")
        print(f"Erro MQTT: {e}")

    finally:
        if client and client.is_connected():
            try:
                client.disconnect()

            except: 
                pass 

# dashboard
st.title("Dashboard de Monitoramento de Pátio - Mottu")



df_all_patios = fetch_patio_status()

if not df_all_patios.empty:

    # seletor de patio
    lista_patios = sorted(df_all_patios['nome_patio'].unique().tolist())
    patio_selecionado = st.sidebar.selectbox("Selecione o Pátio:", lista_patios)

    # filtra os dados para o patio selecionado
    if patio_selecionado and patio_selecionado != 'Pátio Desconhecido':
        df_patio = df_all_patios[df_all_patios['nome_patio'] == patio_selecionado].copy()
    else:
        st.warning("Selecione um pátio específico na barra lateral para visualizar o grid.")
        st.stop() 

    # exibe o titulo e as metricas do patio selecionado
    st.header(f"Status do: {patio_selecionado}")
    total_vagas_patio = len(df_patio)
    vagas_disponiveis = len(df_patio[df_patio['status_vaga'] == 'disponivel'])
    vagas_ocupadas = len(df_patio[df_patio['status_vaga'] == 'ocupada'])

    col1, col2, col3 = st.columns(3)
    col1.metric("Sensores Ativos no Pátio", total_vagas_patio)
    col2.metric("Vagas Disponíveis", vagas_disponiveis)
    col3.metric("Vagas Ocupadas", vagas_ocupadas)

    st.divider()

    # logica e renderizacao do grid fixo
    st.subheader("Layout do Pátio")

    LAYOUT_TOTAL_VAGAS = 12
    VAGAS_POR_LINHA = 6


    sensores_no_patio = {sensor['sensor_id']: sensor for sensor in df_patio.to_dict('records')}
    ids_sensores_ordenados = sorted(sensores_no_patio.keys())

    # variaveis para controlar o desenho do grid
    num_linhas_layout = math.ceil(LAYOUT_TOTAL_VAGAS / VAGAS_POR_LINHA)
    sensor_idx = 0 

    # loop para desenhar as linhas e colunas do grid
    for i in range(num_linhas_layout):
        cols = st.columns(VAGAS_POR_LINHA) 
        for j in range(VAGAS_POR_LINHA):
            with cols[j]: 
                vaga_layout_idx = i * VAGAS_POR_LINHA + j 

                if sensor_idx < len(ids_sensores_ordenados):
                    sensor_id_atual = ids_sensores_ordenados[sensor_idx]
                    sensor = sensores_no_patio[sensor_id_atual]
                    spot_status = sensor.get('status_vaga', 'desconhecido')
                    moto_placa = sensor.get('moto_placa')

                    if spot_status == 'ocupada':
                        css_class = "spot-ocupada"
                        content = moto_placa if moto_placa else "Ocupada"
                    else:
                        css_class = "spot-disponivel"
                        content = "Disponível"

                    st.markdown(f"""
                        <div class="spot-container {css_class}" style="margin-bottom: 5px;">
                            <div class="spot-id">{sensor_id_atual}</div>
                            <div class="spot-content">{content}</div>
                        </div>
                    """, unsafe_allow_html=True)

                    button_key = f"select_btn_{patio_selecionado}_{sensor_id_atual}"
                    if st.button("Selecionar", key=button_key, use_container_width=True):
                        st.session_state.selected_sensor = sensor_id_atual
                        st.rerun() 

                    sensor_idx += 1 

                else:
                    st.markdown(f"""
                    <div class="spot-container spot-vazia">
                         <div class="spot-content">Vaga {vaga_layout_idx + 1}</div>
                    </div>
                    """, unsafe_allow_html=True)

    st.divider()

    # comandos
    if st.session_state.selected_sensor:
        st.subheader(f"Comandos para: {st.session_state.selected_sensor}")
        cmd_cols = st.columns(5) 

        with cmd_cols[0]:
            if st.button("Alerta com buzzer", key=f"cmd_alert_{st.session_state.selected_sensor}"):
                enviar_comando_mqtt(st.session_state.selected_sensor, "1")

        with cmd_cols[1]:
            if st.button("🟢 LED Verde", key=f"cmd_green_{st.session_state.selected_sensor}"):
                enviar_comando_mqtt(st.session_state.selected_sensor, "led_verde")

        with cmd_cols[2]:
            if st.button("🔴 LED Vermelho", key=f"cmd_red_{st.session_state.selected_sensor}"):
                enviar_comando_mqtt(st.session_state.selected_sensor, "led_vermelho")

        with cmd_cols[3]:
            if st.button("⚫ Desligar LED", key=f"cmd_off_{st.session_state.selected_sensor}"):
                enviar_comando_mqtt(st.session_state.selected_sensor, "led_off")

        with cmd_cols[4]:
            if st.button("Limpar Seleção", key=f"cmd_clear_{st.session_state.selected_sensor}"):
                st.session_state.selected_sensor = None
                st.rerun() 

    else:
        st.info("Clique no botão 'Selecionar' de uma vaga acima para habilitar os comandos.")


else:
    st.warning("Nenhum dado de dispositivo encontrado no banco. Verifique o listener MQTT e os scripts SQL.")

