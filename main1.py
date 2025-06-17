# main.py - Robô Trader Pro com painel dinâmico e parâmetros ajustáveis

import streamlit as st
import pandas as pd
import os
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from binance.client import Client
from dotenv import load_dotenv
from technical.indicators import RSI, MACD, EMA
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

# Controles dos Indicadores
st.sidebar.markdown("## Parâmetros dos Indicadores")
rsi_entrada = st.sidebar.slider("RSI - Limite de compra", 10, 50, 30)
rsi_saida = st.sidebar.slider("RSI - Limite de venda", 50, 90, 70)
macd_confirma = st.sidebar.checkbox("MACD precisa confirmar?", value=True)
ema_curto = st.sidebar.slider("Período EMA Curta", 5, 20, 9)
ema_longo = st.sidebar.slider("Período EMA Longa", 15, 50, 21)

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

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "SHIBUSDT"]
log_file = "operacoes_log.csv"

st.title("🤖 Robô Trader Pro - Painel de Controle")
if os.path.exists(log_file):
    df_log = pd.read_csv(log_file)
    st.subheader("📊 Operações Realizadas")
    st.dataframe(df_log[::-1], use_container_width=True)
else:
    st.info("Nenhuma operação registrada ainda.")

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
            volumes = [float(k[5]) for k in klines]
            return closes, times, volumes
        except:
            return None, None, None
    return None, None, None

def analisar_indicadores(symbol):
    closes, _, _ = get_klines(symbol)
    if closes is None or len(closes) == 0:
        return False, False, closes
    rsi = RSI(closes, 14)
    macd_result = MACD(closes, 12, 26, 9)
    macd_line, signal_line, _ = macd_result if len(macd_result) == 3 else ([], [], [])
    ema_short = EMA(closes, ema_curto)
    ema_long = EMA(closes, ema_longo)

    cond_compra = (rsi[-1] < rsi_entrada and ema_short[-1] > ema_long[-1])
    cond_venda = (rsi[-1] > rsi_saida and ema_short[-1] < ema_long[-1])

    if macd_confirma:
        cond_compra &= macd_line[-1] > signal_line[-1]
        cond_venda &= macd_line[-1] < signal_line[-1]

    return cond_compra, cond_venda, closes

def registrar_operacao(horario, moeda, tipo, preco, qtd):
    with open(log_file, "a") as f:
        f.write(f"{horario},{moeda},{tipo},{preco:.2f},{qtd},{rsi_entrada},{rsi_saida},{ema_curto},{ema_longo},{macd_confirma}\n")

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
    for symbol in symbols:
        try:
            cond_compra, cond_venda, closes = analisar_indicadores(symbol)
            preco = closes[-1] if closes else None
            if preco is None:
                continue
            saldo = float(client.get_asset_balance(asset=symbol.replace("USDT", ""))['free']) if symbol != "USDT" else 0
            quantidade = round(10 / preco, 5)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if cond_compra and st.session_state.trading_ativo:
                client.order_market_buy(symbol=symbol, quantity=quantidade)
                registrar_operacao(agora, symbol, "COMPRA", preco, quantidade)
                enviar_alerta(f"🚀 COMPRA: {symbol} a {preco:.2f}")
            elif cond_venda and saldo > 0 and st.session_state.trading_ativo:
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
