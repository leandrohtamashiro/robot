# main.py - Robô Trader Pro Completo com Melhorias

import streamlit as st
import pandas as pd
import os
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from binance.client import Client
from dotenv import load_dotenv
from technical.indicators import MACD, RSI
from twilio.rest import Client as TwilioClient
from decimal import Decimal, ROUND_DOWN
from streamlit_autorefresh import st_autorefresh

# Configuração de Estilo e Layout
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
# Estado inicial de controle da execução
if "trading_ativo" not in st.session_state:
    st.session_state.trading_ativo = True
if "autorefresh" not in st.session_state:
    st.session_state.autorefresh = True

# Sidebar de Configurações
st.sidebar.title("⚙️ Configurações")
st.session_state.trading_ativo = st.sidebar.toggle("🚦 Robô Ativo", value=st.session_state.trading_ativo)
st.session_state.autorefresh = st.sidebar.toggle("🔄 Autoatualização", value=st.session_state.autorefresh)
intervalo = st.sidebar.selectbox("⏱️ Intervalo de Análise", ["15m", "5m", "1h"], index=0)

# Parâmetros MACD
st.sidebar.markdown("## Parâmetros MACD")
macd_fast = st.sidebar.slider("MACD Fast EMA", 5, 20, 12)
macd_slow = st.sidebar.slider("MACD Slow EMA", 15, 50, 26)
macd_signal = st.sidebar.slider("MACD Signal EMA", 5, 20, 9)

# Parâmetros de EMA
st.sidebar.markdown("## Estratégia de Cruzamento EMA")
usar_ema_cross = st.sidebar.checkbox("Ativar EMA9 x EMA21", value=True)

# Parâmetros de Stop Loss
st.sidebar.markdown("## Parâmetros de Stop Loss")
stop_loss_percent = st.sidebar.slider("Stop Loss (%)", 1, 20, 5) / 100

# Período dos Gráficos
st.sidebar.markdown("## Período dos Gráficos")
periodo_grafico = st.sidebar.selectbox("📅 Escolha o Período", ["1h", "24h", "5d", "30d", "1ano"], index=1)

# Auto Refresh
if st.session_state.autorefresh:
    st_autorefresh(interval=30000, key="refresh")
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
log_file = "operacoes_log.csv"

@st.cache_resource(show_spinner=False)
def get_binance_client():
    try:
        c = Client(API_KEY, API_SECRET, requests_params={"timeout": 30})
        c.ping()
        return c
    except:
        return None

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

def get_klines(symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=100):
    client = get_binance_client()
    if client:
        try:
            intervalo_binance = {
                "15m": Client.KLINE_INTERVAL_15MINUTE,
                "5m": Client.KLINE_INTERVAL_5MINUTE,
                "1h": Client.KLINE_INTERVAL_1HOUR
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
    try:
        with open(log_file, "a") as f:
            f.write(f"{horario},{moeda},{tipo},{preco:.2f},{qtd},{macd_fast},{macd_slow},{macd_signal}\n")
    except Exception as e:
        st.warning(f"Erro ao gravar no CSV de operações: {e}")

def enviar_alerta(mensagem):
    try:
        twilio.messages.create(
            body=mensagem,
            from_=TWILIO_NUMBER,
            to=DEST_NUMBER
        )
    except Exception as e:
        st.warning(f"Falha ao enviar alerta via Twilio: {e}")

def executar_trade():
    global usar_ema_cross
    client = get_binance_client()
    if not client:
        st.warning("Erro de conexão com a Binance.")
        return

    try:
        saldo_total = float(client.get_asset_balance(asset='USDT')['free'])
    except Exception as e:
        st.warning(f"Erro ao obter saldo USDT: {e}")
        saldo_total = 0

    for symbol in symbols:
        try:
            cond_compra_macd, cond_venda_macd, closes = analisar_macd(symbol)
            if closes is None or len(closes) < 3:
                continue

            # Análise de cruzamento de EMA
            ema9 = pd.Series(closes).ewm(span=9, adjust=False).mean()
            ema21 = pd.Series(closes).ewm(span=21, adjust=False).mean()
            ema_cross_compra = ema9.iloc[-2] < ema21.iloc[-2] and ema9.iloc[-1] > ema21.iloc[-1]
            ema_cross_venda = ema9.iloc[-2] > ema21.iloc[-2] and ema9.iloc[-1] < ema21.iloc[-1]

            preco = closes[-1]
            quantidade = round(saldo_total / (len(symbols) * preco), 5)
            quantidade = ajustar_quantidade(symbol, quantidade)

            # Verificar valor mínimo notional
            info = client.get_symbol_info(symbol)
            min_notional = None
            for f in info['filters']:
                if f['filterType'] == 'MIN_NOTIONAL':
                    min_notional = float(f['minNotional'])
                    break
            if min_notional and (quantidade * preco) < min_notional:
                st.warning(f"Quantidade insuficiente para {symbol}. Valor abaixo do mínimo notional.")
                continue

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Compra
            if (cond_compra_macd or (usar_ema_cross and ema_cross_compra)) and st.session_state.trading_ativo:
                client.order_market_buy(symbol=symbol, quantity=quantidade)
                registrar_operacao(agora, symbol, "COMPRA", preco, quantidade)
                enviar_alerta(f"🚀 COMPRA: {symbol} a {preco:.2f}")

            # Venda
            if (cond_venda_macd or (usar_ema_cross and ema_cross_venda)) and st.session_state.trading_ativo:
                saldo_moeda = float(client.get_asset_balance(asset=symbol.replace("USDT", ""))['free'])
                quantidade_venda = ajustar_quantidade(symbol, saldo_moeda)
                if quantidade_venda > 0:
                    client.order_market_sell(symbol=symbol, quantity=quantidade_venda)
                    registrar_operacao(agora, symbol, "VENDA", preco, quantidade_venda)
                    enviar_alerta(f"🔻 VENDA: {symbol} a {preco:.2f}")

        except Exception as e:
            st.warning(f"Erro ao processar trade de {symbol}: {e}")

if st.session_state.trading_ativo:
    executar_trade()
# Exibição de Saldos das Moedas
client = get_binance_client()
if client:
    try:
        saldo_usdt = float(client.get_asset_balance(asset='USDT')['free'])
        saldo_btc = float(client.get_asset_balance(asset='BTC')['free'])
        saldo_eth = float(client.get_asset_balance(asset='ETH')['free'])
        saldo_sol = float(client.get_asset_balance(asset='SOL')['free'])
        saldo_xrp = float(client.get_asset_balance(asset='XRP')['free'])
        saldo_ada = float(client.get_asset_balance(asset='ADA')['free'])

        st.markdown("## 💰 Saldos Atuais na Binance:")
        st.markdown(f"- USDT: {saldo_usdt:.4f}")
        st.markdown(f"- BTC: {saldo_btc:.6f}")
        st.markdown(f"- ETH: {saldo_eth:.6f}")
        st.markdown(f"- SOL: {saldo_sol:.4f}")
        st.markdown(f"- XRP: {saldo_xrp:.2f}")
        st.markdown(f"- ADA: {saldo_ada:.2f}")
    except Exception as e:
        st.warning(f"Erro ao obter saldos: {e}")

# Exibição do Histórico de Negociações
st.subheader("📋 Histórico de Negociações do Robô")
if os.path.exists(log_file):
    df_log = pd.read_csv(log_file)
    df_log['horario'] = pd.to_datetime(df_log['horario'], errors='coerce')
    df_log.dropna(subset=['horario'], inplace=True)
    df_log.sort_values(by='horario', inplace=True)

    st.dataframe(df_log, use_container_width=True)

    # Lucro por Operação
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
        st.subheader("📈 Lucro/Prejuízo por Operação")
        fig3, ax3 = plt.subplots()
        ax3.bar(df_trades['Data Venda'], df_trades['Lucro/Prejuízo'],
                color=np.where(df_trades['Lucro/Prejuízo'] >= 0, 'green', 'red'))
        ax3.set_xlabel('Data da Venda')
        ax3.set_ylabel('Lucro/Prejuízo (USDT)')
        ax3.set_title('Lucro/Prejuízo por Operação')
        fig3.autofmt_xdate()
        st.pyplot(fig3)

        # Saldo Diário
        st.subheader("📅 Saldo Consolidado Diário")
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

# Gráficos de Indicadores Técnicos por Moeda
st.subheader("📊 Indicadores Técnicos por Moeda")
for symbol in symbols:
    closes, times = get_klines(symbol)
    if closes is None or times is None or len(closes) < 3:
        continue

    macd_line, signal_line, _ = MACD(closes, macd_fast, macd_slow, macd_signal)
    rsi_vals = RSI(closes, 14)
    ema9 = pd.Series(closes).ewm(span=9, adjust=False).mean()
    ema21 = pd.Series(closes).ewm(span=21, adjust=False).mean()

    # Gráfico de EMAs
    fig, ax = plt.subplots()
    ax.plot(times[-len(ema9):], ema9, linestyle='-', label='EMA 9')
    ax.plot(times[-len(ema21):], ema21, linestyle='-', label='EMA 21')
    ax.set_title(f'{symbol} - EMA 9 e EMA 21')
    ax.legend()
    fig.autofmt_xdate()
    st.pyplot(fig)

    # Gráfico de MACD
    fig2, ax2 = plt.subplots()
    ax2.plot(times[-len(macd_line):], macd_line, linestyle='--', label='MACD')
    ax2.plot(times[-len(signal_line):], signal_line, linestyle=':', label='Signal')
    ax2.set_title(f'{symbol} - MACD vs Signal')
    ax2.legend()
    fig2.autofmt_xdate()
    st.pyplot(fig2)

    # Tabela de Indicadores
    df_ind = pd.DataFrame({
        'Horário': times[-len(macd_line):],
        'MACD': macd_line,
        'Signal': signal_line,
        'RSI': rsi_vals[-len(macd_line):],
        'EMA 9': ema9[-len(macd_line):],
        'EMA 21': ema21[-len(macd_line):]
    })
    st.dataframe(df_ind, use_container_width=True)
