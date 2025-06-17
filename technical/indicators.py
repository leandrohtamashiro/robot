import numpy as np

def EMA(prices, period):
    prices = np.array(prices)
    weights = np.exp(np.linspace(-1., 0., period))
    weights /= weights.sum()
    a = np.convolve(prices, weights, mode='full')[:len(prices)]
    a[:period] = a[period]
    return a

def MACD(prices, fast_period=12, slow_period=26, signal_period=9):
    ema_fast = EMA(prices, fast_period)
    ema_slow = EMA(prices, slow_period)
    macd_line = ema_fast - ema_slow
    signal_line = EMA(macd_line, signal_period)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def RSI(prices, period=14):
    prices = np.array(prices)
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)
    for i in range(period, len(prices)):
        delta = deltas[i - 1] if i - 1 < len(deltas) else 0
        upval = max(delta, 0)
        downval = -min(delta, 0)
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)
    return rsi
