import streamlit as st
import pandas as pd
import oracledb
import math
from decouple import config
from streamlit_autorefresh import st_autorefresh
from sqlalchemy import create_engine

# --- Configurações ---
ORACLE_USER = config("ORACLE_USER")
ORACLE_PASS = config("ORACLE_PASS")
ORACLE_DSN = config("ORACLE_DSN")

# Define o layout da página como "wide"
st.set_page_config(layout="wide")

# Função para carregar o CSS externo
def load_css(file_name):
    try:
        # --- MUDANÇA: Especificar encoding UTF-8 ---
        with open(file_name, encoding='utf-8') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"Arquivo de estilo '{file_name}' não encontrado. Por favor, crie-o na mesma pasta (conteúdo no topo deste script).")
    # --- MUDANÇA ADICIONAL: Capturar o erro de decodificação ---
    except UnicodeDecodeError:
        st.error(f"Erro ao decodificar '{file_name}'. Certifique-se de que o arquivo está salvo com codificação UTF-8.")

# Carrega o nosso arquivo de estilo
load_css("style.css")

# Atualiza a página a cada 5 segundos
st_autorefresh(interval=5000, key="data_refresher")

# --- Função de busca de dados ---
@st.cache_data(ttl=5) # Cache de 5 segundos
def fetch_patio_status():
    """Busca o status atual de todos os devices e as motos neles."""
    db_uri = f"oracle+oracledb://{ORACLE_USER}:{ORACLE_PASS}@{ORACLE_DSN}"
    engine = create_engine(db_uri)

    # Query ajustada para focar no grid (sem lat/lon)
    query = """
    SELECT
        d.code AS SENSOR_ID,
        d.spot_status AS STATUS_VAGA,
        m.license AS MOTO_PLACA
    FROM
        devices d
    LEFT JOIN
        motorcycles m ON d.motorcycle_id = m.id
    ORDER BY
        d.code ASC  -- Ordena pelo nome do sensor para um grid consistente
    """
    try:
        df = pd.read_sql(query, engine)
        df.columns = [col.lower() for col in df.columns] # Padroniza para minúsculas
        return df
    except Exception as e:
        st.error(f"Erro ao conectar ou buscar dados no Oracle DB: {e}")
        return pd.DataFrame()

# --- Construção do Dashboard ---
st.title("🏍️ Dashboard de Monitoramento de Pátio - Mottu")

df_patio = fetch_patio_status()

if not df_patio.empty:
    # --- Métricas e Alertas ---
    total_vagas = len(df_patio)
    vagas_disponiveis = len(df_patio[df_patio['status_vaga'] == 'disponivel'])
    vagas_ocupadas = len(df_patio[df_patio['status_vaga'] == 'ocupada'])

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Vagas Monitoradas", total_vagas)
    col2.metric("Vagas Disponíveis", vagas_disponiveis)
    col3.metric("Vagas Ocupadas", vagas_ocupadas)

    st.divider()

    # --- Lógica do Grid de Vagas ---
    st.subheader("Grid de Vagas do Pátio")

    SPOTS_PER_ROW = 8 # Quantas vagas por linha no grid

    # Converte o dataframe para uma lista de dicionários para facilitar o loop
    sensors = df_patio.to_dict('records')

    if not sensors:
        st.warning("Query executada, mas nenhum sensor retornado.")

    # Calcula o número de linhas necessárias
    num_rows = math.ceil(len(sensors) / SPOTS_PER_ROW)

    for i in range(num_rows):
        # Cria as colunas para esta linha
        cols = st.columns(SPOTS_PER_ROW)

        # Pega os sensores para esta linha
        row_sensors = sensors[i*SPOTS_PER_ROW : (i+1)*SPOTS_PER_ROW]

        # Preenche cada coluna com uma vaga
        for j, sensor in enumerate(row_sensors):
            with cols[j]:
                spot_status = sensor.get('status_vaga', 'desconhecido')
                sensor_id = sensor.get('sensor_id')
                moto_placa = sensor.get('moto_placa')

                # Define o estilo CSS e o conteúdo
                if spot_status == 'ocupada':
                    css_class = "spot-ocupada"
                    # Se está ocupada mas sem moto (erro de dados), mostra "Ocupada"
                    # Se tiver moto, mostra a placa
                    content = moto_placa if moto_placa else "Ocupada"
                else:
                    css_class = "spot-disponivel"
                    content = "Disponível"

                # Renderiza o "box" da vaga usando HTML e o CSS
                st.markdown(f"""
                <div class="spot-container {css_class}">
                    <div class="spot-id">{sensor_id}</div>
                    <div class="spot-content">{content}</div>
                </div>
                """, unsafe_allow_html=True)

    st.divider()
    # Mantém a tabela de dados brutos para referência
    st.subheader("Visão Geral (Tabela de Dados)")
    st.dataframe(df_patio, use_container_width=True)

else:
    st.warning("Nenhum dado de dispositivo encontrado. Verifique se o listener está rodando e o banco populado.")

