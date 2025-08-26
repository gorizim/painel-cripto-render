import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volume import OnBalanceVolumeIndicator
from ta.volatility import BollingerBands

# === Indicadores Técnicos (básicos) ===

def calcular_rsi(close, window=14):
    return RSIIndicator(pd.Series(close), window=window).rsi().tolist()

def calcular_stoch_rsi(close, window=14):
    rsi = pd.Series(calcular_rsi(close, window))
    stoch_rsi = (rsi - rsi.rolling(window).min()) / (rsi.rolling(window).max() - rsi.rolling(window).min())
    return stoch_rsi.fillna(0).tolist()

def calcular_mfi(high, low, close, volume, window=14):
    tp = (np.array(high) + np.array(low) + np.array(close)) / 3
    raw_money_flow = tp * np.array(volume)
    direction = np.sign(np.diff(tp, prepend=tp[0]))
    pos_flow = np.where(direction > 0, raw_money_flow, 0)
    neg_flow = np.where(direction < 0, raw_money_flow, 0)
    pos_sum = pd.Series(pos_flow).rolling(window).sum()
    neg_sum = pd.Series(neg_flow).rolling(window).sum()
    mfi = 100 - (100 / (1 + (pos_sum / neg_sum)))
    return mfi.fillna(50).tolist()

def calcular_macd(close):
    macd = MACD(pd.Series(close))
    return macd.macd().tolist(), macd.macd_signal().tolist(), macd.macd_diff().tolist()

def calcular_obv(close, volume):
    obv = OnBalanceVolumeIndicator(pd.Series(close), pd.Series(volume))
    return obv.on_balance_volume().tolist()

def calcular_bollinger_bands(close, window=20, std=2):
    bb = BollingerBands(pd.Series(close), window=window, window_dev=std)
    return bb.bollinger_mavg().tolist(), bb.bollinger_hband().tolist(), bb.bollinger_lband().tolist()

# === Candlestick Patterns (versões simples/robustas) ===

def detectar_martelo(open_, high, low, close):
    for o, h, l, c in zip(open_, high, low, close):
        corpo = abs(c - o)
        sombra_inferior = (o if c > o else c) - l
        sombra_superior = h - (c if c > o else o)
        if corpo > 0 and sombra_inferior > corpo and sombra_superior < corpo:
            return True
    return False

def detectar_martelo_invertido(open_, high, low, close):
    for o, h, l, c in zip(open_, high, low, close):
        corpo = abs(c - o)
        sombra_superior = h - (c if c > o else o)
        sombra_inferior = (o if c > o else c) - l
        if corpo > 0 and sombra_superior > corpo and sombra_inferior < corpo:
            return True
    return False

def detectar_engolfo(open_, high, low, close):
    for i in range(1, len(close)):
        bull_now = close[i] > open_[i]
        bear_prev = close[i-1] < open_[i-1]
        bull_engulf_prev = (open_[i] < close[i-1]) and (close[i] > open_[i-1])
        if bull_now and bear_prev and bull_engulf_prev:
            return True
    return False

def detectar_estrela_manha(open_, high, low, close):
    for i in range(2, len(close)):
        if close[i-2] < open_[i-2] and abs(close[i-1] - open_[i-1]) / max(open_[i-1], 1e-9) < 0.005 and close[i] > open_[i] and close[i] > close[i-2]:
            return True
    return False

def detectar_estrela_noite(open_, high, low, close):
    for i in range(2, len(close)):
        if close[i-2] > open_[i-2] and abs(close[i-1] - open_[i-1]) / max(open_[i-1], 1e-9) < 0.005 and close[i] < open_[i] and close[i] < close[i-2]:
            return True
    return False

def detectar_tres_soldados_brancos(open_, high, low, close):
    for i in range(2, len(close)):
        if close[i] > open_[i] and close[i-1] > open_[i-1] and close[i-2] > open_[i-2]:
            return True
    return False

def detectar_tres_corvos_negros(open_, high, low, close):
    for i in range(2, len(close)):
        if close[i] < open_[i] and close[i-1] < open_[i-1] and close[i-2] < open_[i-2]:
            return True
    return False

# === Divergências ===

def detectar_divergencia_rsi(close, rsi):
    if len(close) < 5 or len(rsi) < 5:
        return False, None
    if close[-1] > close[-3] and rsi[-1] < rsi[-3]:
        return True, "baixa"
    if close[-1] < close[-3] and rsi[-1] > rsi[-3]:
        return True, "alta"
    return False, None

def detectar_divergencia_obv(close, obv):
    if len(close) < 5 or len(obv) < 5:
        return False, None
    if close[-1] > close[-3] and obv[-1] < obv[-3]:
        return True, "baixa"
    if close[-1] < close[-3] and obv[-1] > obv[-3]:
        return True, "alta"
    return False, None

# === Squeeze & Overextension (S&O) ===

def detectar_squeeze_overextension(close, window=20):
    prices = pd.Series(close)
    rolling_mean = prices.rolling(window=window).mean()
    rolling_std = prices.rolling(window=window).std()
    upper_band = rolling_mean + 2 * rolling_std
    lower_band = rolling_mean - 2 * rolling_std
    spread = upper_band - lower_band

    spread_now = spread.iloc[-1]
    spread_anterior = spread.iloc[-5:-1].mean()

    liberado = spread_now > spread_anterior * 1.2  # explosão confirmada
    direcao = None

    if liberado:
        direcao = "alta" if close[-1] > rolling_mean.iloc[-1] else "baixa"

    return spread_now, liberado, direcao

# === Extras: ATR, %B, largura BB, spread vs MA, volatilidade % ===

def calcular_atr(high, low, close, window=14):
    h = pd.Series(high, dtype=float)
    l = pd.Series(low, dtype=float)
    c = pd.Series(close, dtype=float)
    prev_close = c.shift(1)
    tr = pd.concat([
        (h - l).abs(),
        (h - prev_close).abs(),
        (l - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=window).mean()
    return atr.fillna(method="bfill").tolist()

def calcular_percent_b(close, bb_lower, bb_upper):
    c = pd.Series(close, dtype=float)
    lower = pd.Series(bb_lower, dtype=float)
    upper = pd.Series(bb_upper, dtype=float)
    width = (upper - lower).replace(0, 1e-9)
    percent_b = (c - lower) / width
    return percent_b.clip(lower=-1e9, upper=1e9).tolist()

def calcular_bollinger_width(bb_lower, bb_upper):
    lower = pd.Series(bb_lower, dtype=float)
    upper = pd.Series(bb_upper, dtype=float)
    return (upper - lower).tolist()

def calcular_spread_vs_ma(close, ma):
    c = pd.Series(close, dtype=float)
    m = pd.Series(ma, dtype=float).replace(0, 1e-9)
    return ((c - m) / m * 100.0).tolist()

def calcular_volatilidade_pct(close, window=20):
    c = pd.Series(close, dtype=float)
    ret = c.pct_change()
    vol = ret.rolling(window).std() * (window ** 0.5) * 100.0  # anualização simples
    return vol.fillna(method="bfill").tolist()
