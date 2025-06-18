# main.py - Robô Trader Pro Completo com Tabela de Negociações, Gráficos de Lucro e Indicadores Técnicos

import streamlit as st
import pandas as pd
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from datetime import datetime, timedelta
from binance.client import Client
from dotenv import load_dotenv
from technical.indicators import MACD, RSI
from twilio.rest import Client as TwilioClient
from apscheduler.schedulers.background import BackgroundScheduler
from decimal import Decimal, ROUND_DOWN
from streamlit_autorefresh import st_autorefresh
from decimal import Decimal, ROUND_DOWN

def ajustar_quantidade(symbol, quantidade):
    client = get_binance_client()
    info = client.get_symbol_info(symbol)
    step_size = None
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            step_size = Decimal(f['stepSize'])
            break
    if step_size:
        precision = abs(step_size.as_tuple().exponent)
        quantidade_decimal = Decimal(str(quantidade)).quantize(Decimal(10) ** -precision, rounding=ROUND_DOWN)
        return float(quantidade_decimal)
    return quantidade

st.set_page_config(layout="wide")

# Exibir saldos logo após o título
mostrar_saldos()
sns.set_palette("pastel")
plt.style.use("seaborn-v0_8-pastel")

load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")
DEST_NUMBER = os.getenv("DEST_NUMBER")

twilio = TwilioClient(TWILIO_SID, TWILIO_AUTH)

if "trading_ativo" not in st.session_state:
    st.session_state.trading_ativo = True
if "autorefresh" not in st.session_state:
    st.session_state.autorefresh = True

st.sidebar.title("⚙️ Configurações")
st.session_state.trading_ativo = st.sidebar.toggle("🚦 Robô Ativo", value=st.session_state.trading_ativo)
st.session_state.autorefresh = st.sidebar.toggle("🔄 Autoatualização", value=st.session_state.autorefresh)
intervalo = st.sidebar.selectbox("⏱️ Intervalo de Análise", ["15m", "5m", "1h"], index=0)

# Parâmetros MACD
st.sidebar.markdown("## Parâmetros MACD")
macd_fast = st.sidebar.slider("MACD Fast EMA", 5, 20, 12)
macd_slow = st.sidebar.slider("MACD Slow EMA", 15, 50, 26)
macd_signal = st.sidebar.slider("MACD Signal EMA", 5, 20, 9)

# Parâmetros de Cruzamento de EMA
st.sidebar.markdown("## Estratégia de Cruzamento EMA")
usar_ema_cross = st.sidebar.checkbox("Ativar EMA9 x EMA21", value=True)

# Período para gráficos

# Parâmetros de Stop Loss
st.sidebar.markdown("## Parâmetros de Stop Loss")
stop_loss_percent = st.sidebar.slider("Stop Loss (%)", 1, 20, 5) / 100
st.sidebar.markdown("## Período dos Gráficos")
periodo_grafico = st.sidebar.selectbox("📅 Escolha o Período", ["1h", "24h", "5d", "30d", "1ano"], index=1)

if st.session_state.autorefresh:
    st_autorefresh(interval=30000, key="refresh")

@st.cache_resource(show_spinner=False)
def get_binance_client():
    try:
        c = Client(API_KEY, API_SECRET, requests_params={"timeout": 30})
        c.ping()
        return c
    except:
        return None

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
log_file = "operacoes_log.csv"

def filtrar_periodo(df, periodo):
    agora = datetime.now()
    if 'horario' in df.columns:
        df['horario'] = pd.to_datetime(df['horario'])
    elif 'data' in df.columns:
        df.rename(columns={'data': 'horario'}, inplace=True)
        df['horario'] = pd.to_datetime(df['horario'])
    else:
        st.error("O CSV de log não contém a coluna 'horario' ou 'data'. Corrija o arquivo operacoes_log.csv.")
        return df.iloc[0:0]
    if periodo == "1h":
        inicio = agora - timedelta(hours=1)
    elif periodo == "24h":
        inicio = agora - timedelta(days=1)
    elif periodo == "5d":
        inicio = agora - timedelta(days=5)
    elif periodo == "30d":
        inicio = agora - timedelta(days=30)
    elif periodo == "1ano":
        inicio = agora - timedelta(days=365)
    else:
        inicio = df['horario'].min()
    return df[df['horario'] >= inicio]

def get_klines(symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=100):
    client = get_binance_client()
    if client:
        try:
            intervalo_binance = {
                "15m": Client.KLINE_INTERVAL_15MINUTE,
                "5m": Client.KLINE_INTERVAL_5MINUTE,
                "1h": Client.KLINE_INTERVAL_1HOUR,
            }.get(intervalo, Client.KLINE_INTERVAL_15MINUTE)
            klines = client.get_klines(symbol=symbol, interval=intervalo_binance, limit=limit)
            closes = [float(k[4]) for k in klines]
            times = [datetime.fromtimestamp(int(k[0] / 1000)) for k in klines]
            return closes, times
        except Exception as e:
            st.warning(f"Erro ao obter klines de {symbol}: {e}")
    return None, None

def mostrar_saldos():
    client = get_binance_client()
    if client:
        try:
            saldo_usdt = float(client.get_asset_balance(asset='USDT')['free'])
            saldo_btc = float(client.get_asset_balance(asset='BTC')['free'])
            saldo_eth = float(client.get_asset_balance(asset='ETH')['free'])
            saldo_sol = float(client.get_asset_balance(asset='SOL')['free'])
            saldo_xrp = float(client.get_asset_balance(asset='XRP')['free'])
            saldo_ada = float(client.get_asset_balance(asset='ADA')['free'])

            preco_btc = float(client.get_symbol_ticker(symbol='BTCUSDT')['price'])
            preco_eth = float(client.get_symbol_ticker(symbol='ETHUSDT')['price'])
            preco_sol = float(client.get_symbol_ticker(symbol='SOLUSDT')['price'])
            preco_xrp = float(client.get_symbol_ticker(symbol='XRPUSDT')['price'])
            preco_ada = float(client.get_symbol_ticker(symbol='ADAUSDT')['price'])

            total_btc = saldo_btc * preco_btc
            total_eth = saldo_eth * preco_eth
            total_sol = saldo_sol * preco_sol
            total_xrp = saldo_xrp * preco_xrp
            total_ada = saldo_ada * preco_ada

            total_geral = saldo_usdt + total_btc + total_eth + total_sol + total_xrp + total_ada

            st.markdown(f"## 💰 Total Estimado em USDT: {total_geral:.2f}")
            st.markdown(f"### Saldo detalhado:")
            st.markdown(f"- USDT: {saldo_usdt:.4f} ≈ {saldo_usdt:.2f} USDT")
            st.markdown(f"- BTC: {saldo_btc:.6f} ≈ {total_btc:.2f} USDT")
            st.markdown(f"- ETH: {saldo_eth:.6f} ≈ {total_eth:.2f} USDT")
            st.markdown(f"- SOL: {saldo_sol:.4f} ≈ {total_sol:.2f} USDT")
            st.markdown(f"- XRP: {saldo_xrp:.2f} ≈ {total_xrp:.2f} USDT")
            st.markdown(f"- ADA: {saldo_ada:.2f} ≈ {total_ada:.2f} USDT")
        except Exception as e:
            st.warning(f"Erro ao obter saldos da Binance: {e}")
        st.warning(f"Erro ao obter saldos da Binance: {e}")
    except Exception as e:
        st.warning(f"Erro ao obter saldo USDT: {e}")

if st.session_state.trading_ativo:
    executar_trade()

# Exibição da Tabela de Negociações com Lucro/Prejuízo
st.subheader("📋 Histórico de Negociações do Robô")

if os.path.exists(log_file):
    df_log = pd.read_csv(log_file)
    if 'horario' in df_log.columns:
        df_log['horario'] = pd.to_datetime(df_log['horario'], errors='coerce')
    elif 'data' in df_log.columns:
        df_log.rename(columns={'data': 'horario'}, inplace=True)
        df_log['horario'] = pd.to_datetime(df_log['horario'], errors='coerce')
    else:
        st.info("Nenhuma coluna de data encontrada no log ainda. Aguarde a primeira operação.")
        df_log = pd.DataFrame(columns=["horario", "moeda", "tipo", "preco", "qtd", "macd_fast", "macd_slow", "macd_signal"])

    df_log.dropna(subset=['horario'], inplace=True)
    df_log.sort_values(by='horario', inplace=True)
    df_log.sort_values(by='horario', inplace=True)

    trades = []
    position = {}

    for index, row in df_log.iterrows():
        key = row['moeda']
        if row['tipo'] == 'COMPRA':
            position[key] = {'preco': row['preco'], 'qtd': row['qtd'], 'data': row['horario']}
        elif row['tipo'] == 'VENDA' and key in position:
            compra = position.pop(key)
            stop_loss = compra['preco'] * (1 - stop_loss_percent)
            if row['preco'] < stop_loss:
                lucro = (stop_loss - compra['preco']) * row['qtd']
            else:
                lucro = (row['preco'] - compra['preco']) * row['qtd']
            trades.append({
                'Moeda': key,
                'Data Compra': compra['data'],
                'Preço Compra': compra['preco'],
                'Data Venda': row['horario'],
                'Preço Venda': row['preco'],
                'Quantidade': row['qtd'],
                'Lucro/Prejuízo': lucro
            })

    df_trades = pd.DataFrame(trades)
    if not df_trades.empty:
        st.dataframe(df_trades, use_container_width=True)

        # Gráfico de Lucro/Prejuízo por Operação
        fig3, ax3 = plt.subplots()
        ax3.bar(df_trades['Data Venda'], df_trades['Lucro/Prejuízo'], color=np.where(df_trades['Lucro/Prejuízo']>=0, 'green', 'red'))
        ax3.set_xlabel('Data da Venda')
        ax3.set_ylabel('Lucro/Prejuízo (USDT)')
        ax3.set_title('Lucro/Prejuízo por Operação')
        fig3.autofmt_xdate()
        st.pyplot(fig3)

# Painel de Saldo Total Consolidado por Dia
    st.subheader("📅 Saldo Consolidado Diário")
    if not pd.api.types.is_datetime64_any_dtype(df_log['horario']):
        df_log['horario'] = pd.to_datetime(df_log['horario'], errors='coerce')
    df_log.dropna(subset=['horario'], inplace=True)
    df_log['Dia'] = df_log['horario'].dt.date
    df_log['Lucro'] = df_log.apply(lambda row: row['preco'] * row['qtd'] if row['tipo'] == 'VENDA' else -row['preco'] * row['qtd'], axis=1)
    saldo_diario = df_log.groupby('Dia')['Lucro'].sum().cumsum().reset_index()
    fig4, ax4 = plt.subplots()
    ax4.plot(saldo_diario['Dia'], saldo_diario['Lucro'], marker='o')
    ax4.set_xlabel('Dia')
    ax4.set_ylabel('Lucro Acumulado (USDT)')
    ax4.set_title('Evolução do Saldo Diário')
    fig4.autofmt_xdate()
    st.pyplot(fig4)

# Gráficos de Indicadores por Moeda
st.subheader("📈 MACD, Médias Móveis e RSI por Moeda")

for symbol in symbols:
    closes, times = get_klines(symbol)
    if closes is None or times is None or len(closes) < 3:
        continue
    macd_line, signal_line, _ = MACD(closes, macd_fast, macd_slow, macd_signal)
    rsi_vals = RSI(closes, 14)
    ema9 = pd.Series(closes).ewm(span=9, adjust=False).mean()
    ema21 = pd.Series(closes).ewm(span=21, adjust=False).mean()

    fig, ax = plt.subplots()
    ax.plot(times[-len(ema9):], ema9, linestyle='-', alpha=0.6, label='EMA 9')
    ax.plot(times[-len(ema21):], ema21, linestyle='-', alpha=0.6, label='EMA 21')
    ax.set_xlabel('Data/Hora')
    ax.set_ylabel('Médias Móveis')
    ax.set_title(f'{symbol} - EMA 9 e EMA 21')
    ax.legend()
    fig.autofmt_xdate()
    st.pyplot(fig)

    fig2, ax2 = plt.subplots()
    ax2.plot(times[-len(macd_line):], macd_line, linestyle='--', label='MACD')
    ax2.plot(times[-len(signal_line):], signal_line, linestyle=':', label='Signal')
    ax2.set_xlabel('Data/Hora')
    ax2.set_ylabel('MACD e Signal')
    ax2.set_title(f'{symbol} - MACD vs Signal')
    ax2.legend()
    fig2.autofmt_xdate()
    st.pyplot(fig2)
    

    df_ind = pd.DataFrame({
        'Horário': times[-len(macd_line):],
        'MACD': macd_line,
        'Signal': signal_line,
        'RSI': rsi_vals[-len(macd_line):],
        'EMA 9': ema9[-len(macd_line):],
        'EMA 21': ema21[-len(macd_line):]
    })
    st.dataframe(df_ind, use_container_width=True)
