# main.py - Robô Trader Pro com MACD Dinâmico, Gráficos de Desempenho, Análise por Moeda e Railway Ready

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
from streamlit_autorefresh import st_autorefresh

st.set_page_config(layout="wide")
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

# Controles dos Parâmetros MACD
st.sidebar.markdown("## Parâmetros MACD")
macd_fast = st.sidebar.slider("MACD Fast EMA", 5, 20, 12)
macd_slow = st.sidebar.slider("MACD Slow EMA", 15, 50, 26)
macd_signal = st.sidebar.slider("MACD Signal EMA", 5, 20, 9)

# Controle de período para gráficos
st.sidebar.markdown("## Período dos Gráficos")
periodo_grafico = st.sidebar.selectbox(
    "📅 Escolha o Período",
    ["1h", "24h", "5d", "30d", "1ano"],
    index=1
)

if st.session_state.autorefresh:
    st_autorefresh(interval=30000, key="refresh")

@st.cache_resource(show_spinner=False)
def get_binance_client():
    try:
        c = Client(API_KEY, API_SECRET)
        c.ping()
        return c
    except:
        return None

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "IRONUSDT"]
log_file = "operacoes_log.csv"

st.title("🤖 Robô Trader Pro - Análise por Moeda e Railway Ready")

# Funções auxiliares

def filtrar_periodo(df, periodo):
    agora = datetime.now()
    df['horario'] = pd.to_datetime(df['horario'])
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
            }[intervalo]
            klines = client.get_klines(symbol=symbol, interval=intervalo_binance, limit=limit)
            closes = [float(k[4]) for k in klines]
            times = [datetime.fromtimestamp(int(k[0]/1000)) for k in klines]
            return closes, times
        except:
            return None, None
    return None, None

def analisar_macd(symbol):
    closes, _ = get_klines(symbol)
    if closes is None or len(closes) == 0:
        return False, False, closes
    macd_line, signal_line, _ = MACD(closes, macd_fast, macd_slow, macd_signal)
    cruzamento_compra = macd_line[-2] < signal_line[-2] and macd_line[-1] > signal_line[-1]
    cruzamento_venda = macd_line[-2] > signal_line[-2] and macd_line[-1] < signal_line[-1]
    return cruzamento_compra, cruzamento_venda, closes

def registrar_operacao(horario, moeda, tipo, preco, qtd):
    with open(log_file, "a") as f:
        f.write(f"{horario},{moeda},{tipo},{preco:.2f},{qtd},{macd_fast},{macd_slow},{macd_signal}\n")

def enviar_alerta(mensagem):
    twilio.messages.create(
        body=mensagem,
        from_=TWILIO_NUMBER,
        to=DEST_NUMBER
    )

def executar_trade():
    client = get_binance_client()
    if not client:
        st.warning("Erro de conexão com a Binance.")
        return
    saldo_total = float(client.get_asset_balance(asset='USDT')['free'])
    for symbol in symbols:
        try:
            cond_compra, cond_venda, closes = analisar_macd(symbol)
            preco = closes[-1] if closes else None
            if preco is None:
                continue
            quantidade = round(saldo_total / (len(symbols) * preco), 5)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if cond_compra and st.session_state.trading_ativo:
                client.order_market_buy(symbol=symbol, quantity=quantidade)
                registrar_operacao(agora, symbol, "COMPRA", preco, quantidade)
                enviar_alerta(f"🚀 COMPRA: {symbol} a {preco:.2f}")
            elif cond_venda and st.session_state.trading_ativo:
                saldo = float(client.get_asset_balance(asset=symbol.replace("USDT", ""))['free'])
                if saldo > 0:
                    client.order_market_sell(symbol=symbol, quantity=saldo)
                    registrar_operacao(agora, symbol, "VENDA", preco, saldo)
                    enviar_alerta(f"🔻 VENDA: {symbol} a {preco:.2f}")
        except Exception as e:
            st.warning(f"Erro ao processar {symbol}: {e}")

if st.session_state.trading_ativo:
    executar_trade()

st.subheader("💰 Saldo Atual")
client = get_binance_client()
saldo_usdt = float(client.get_asset_balance(asset='USDT')['free']) if client else 0
st.metric("Saldo USDT", f"${saldo_usdt:,.2f}")

if os.path.exists(log_file):
    df_log = pd.read_csv(log_file)
    lucro_total = 0
    for _, row in df_log.iterrows():
        if row['tipo'] == 'VENDA':
            lucro_total += row['preco'] * row['qtd']
        elif row['tipo'] == 'COMPRA':
            lucro_total -= row['preco'] * row['qtd']
    st.metric("Lucro Bruto Estimado", f"${lucro_total:,.2f}")

    df_periodo = filtrar_periodo(df_log, periodo_grafico)
    if not df_periodo.empty:
        df_periodo['saldo'] = df_periodo.apply(
            lambda row: row['preco'] * row['qtd'] if row['tipo'] == 'VENDA' else -row['preco'] * row['qtd'], axis=1
        ).cumsum()
        fig, ax = plt.subplots()
        ax.plot(df_periodo['horario'], df_periodo['saldo'], marker='o')
        ax.set_xlabel('Data/Hora')
        ax.set_ylabel('Lucro Acumulado (USDT)')
        ax.set_title(f'Evolução do Lucro - Últimos {periodo_grafico}')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m %H:%M'))
        fig.autofmt_xdate()
        st.pyplot(fig)

        # Gráfico de Lucro/Perda por Moeda
        df_periodo['lucro'] = df_periodo.apply(
            lambda row: row['preco'] * row['qtd'] if row['tipo'] == 'VENDA' else -row['preco'] * row['qtd'], axis=1
        )
        fig2, ax2 = plt.subplots()
        for symbol in symbols:
            df_symbol = df_periodo[df_periodo['moeda'] == symbol]
            if not df_symbol.empty:
                ax2.plot(df_symbol['horario'], df_symbol['lucro'].cumsum(), label=symbol)
        ax2.set_xlabel('Data/Hora')
        ax2.set_ylabel('Lucro/Prejuízo Acumulado')
        ax2.set_title('Lucro/Perda por Moeda')
        ax2.legend()
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m %H:%M'))
        fig2.autofmt_xdate()
        st.pyplot(fig2)

# Gráficos e Tabela por Moeda
st.subheader("📈 Indicadores Técnicos por Moeda")
for symbol in symbols:
    closes, times = get_klines(symbol)
    if closes is None or times is None:
        continue
    macd_line, signal_line, _ = MACD(closes, macd_fast, macd_slow, macd_signal)
    rsi_vals = RSI(closes, 14)
    min_val = min(closes)
    max_val = max(closes)

    fig, ax = plt.subplots()
    ax.plot(times, closes, label='Preço de Fechamento')
    ax.plot(times[-len(macd_line):], macd_line, linestyle='--', label='MACD')
    ax.plot(times[-len(signal_line):], signal_line, linestyle=':', label='Signal')
    ax.set_xlabel('Data/Hora')
    ax.set_ylabel('Preço (USDT)')
    ax.set_title(f'{symbol} - Preço e MACD')
    ax.legend()
    fig.autofmt_xdate()
    st.pyplot(fig)

    df_ind = pd.DataFrame({
        'Horário': times[-len(macd_line):],
        'MACD': macd_line,
        'Signal': signal_line,
        'RSI': rsi_vals[-len(macd_line):],
        'Min': [min_val]*len(macd_line),
        'Max': [max_val]*len(macd_line)
    })
    st.dataframe(df_ind, use_container_width=True)
