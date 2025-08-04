import os
import requests
import numpy as np
from dotenv import load_dotenv

load_dotenv()

def calcular_rsi(precos, period=14):
    deltas = np.diff(precos)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(precos)
    rsi[:period] = 100. - 100. / (1. + rs)

    for i in range(period, len(precos)):
        delta = deltas[i - 1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta

        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period

        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)

    return rsi

def calcular_stoch_rsi(precos, period=14):
    rsi = calcular_rsi(precos, period)
    stoch_rsi = (rsi - np.min(rsi[-period:])) / (np.max(rsi[-period:]) - np.min(rsi[-period:])) * 100
    k = np.mean(stoch_rsi[-3:])
    d = np.mean(stoch_rsi[-6:])
    return stoch_rsi[-1], k, d

def calcular_mfi(high, low, close, volume, period=14):
    typical_price = (np.array(high) + np.array(low) + np.array(close)) / 3
    money_flow = typical_price * volume
    positive_flow = []
    negative_flow = []

    for i in range(1, len(typical_price)):
        if typical_price[i] > typical_price[i - 1]:
            positive_flow.append(money_flow[i])
            negative_flow.append(0)
        else:
            positive_flow.append(0)
            negative_flow.append(money_flow[i])

    pos_mf = np.sum(positive_flow[-period:])
    neg_mf = np.sum(negative_flow[-period:])
    if neg_mf == 0:
        return [100] * len(close)
    mfi = 100 - (100 / (1 + (pos_mf / neg_mf)))
    return [None] * (len(close) - 1) + [mfi]

def calcular_macd(precos, slow=26, fast=12, signal=9):
    exp1 = np.array(pd.Series(precos).ewm(span=fast, adjust=False).mean())
    exp2 = np.array(pd.Series(precos).ewm(span=slow, adjust=False).mean())
    macd = exp1 - exp2
    signal_line = pd.Series(macd).ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def calcular_obv(close, volume):
    obv = [0]
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv.append(obv[-1] + volume[i])
        elif close[i] < close[i - 1]:
            obv.append(obv[-1] - volume[i])
        else:
            obv.append(obv[-1])
    return obv

def detectar_martelo(open_, high, low, close):
    return close[-1] > open_[-1] and (high[-1] - low[-1]) > 3 * (open_[-1] - close[-1])

def detectar_martelo_invertido(open_, high, low, close):
    return close[-1] > open_[-1] and (high[-1] - open_[-1]) > 2 * (open_[-1] - low[-1])

def detectar_engolfo(open_, high, low, close):
    return close[-1] > open_[-1] and close[-2] < open_[-2] and close[-1] > open_[-2] and open_[-1] < close[-2]

def detectar_estrela_manha(open_, high, low, close):
    return close[-3] < open_[-3] and abs(close[-2] - open_[-2]) < 0.1 * (high[-2] - low[-2]) and close[-1] > open_[-1] and close[-1] > (close[-3] + open_[-3]) / 2

def detectar_estrela_noite(open_, high, low, close):
    return close[-3] > open_[-3] and abs(close[-2] - open_[-2]) < 0.1 * (high[-2] - low[-2]) and close[-1] < open_[-1] and close[-1] < (close[-3] + open_[-3]) / 2

def detectar_tres_soldados_brancos(open_, high, low, close):
    return close[-1] > open_[-1] and close[-2] > open_[-2] and close[-3] > open_[-3]

def detectar_tres_corvos_negros(open_, high, low, close):
    return close[-1] < open_[-1] and close[-2] < open_[-2] and close[-3] < open_[-3]

def detectar_divergencia_rsi(close, rsi):
    if len(close) < 3 or len(rsi) < 3:
        return False, None
    if close[-1] > close[-2] and rsi[-1] < rsi[-2]:
        return True, "baixa"
    if close[-1] < close[-2] and rsi[-1] > rsi[-2]:
        return True, "alta"
    return False, None

def detectar_divergencia_obv(close, obv):
    if len(close) < 3 or len(obv) < 3:
        return False, None
    if close[-1] > close[-2] and obv[-1] < obv[-2]:
        return True, "baixa"
    if close[-1] < close[-2] and obv[-1] > obv[-2]:
        return True, "alta"
    return False, None

def detectar_squeeze_overextension(close):
    bandas = calcular_bollinger_bands(close)
    spread = bandas["upper"][-1] - bandas["lower"][-1]
    release = spread > (np.mean(bandas["upper"][-20:] - bandas["lower"][-20:]) * 1.5)
    direcao = None
    if release:
        if close[-1] > close[-2] > close[-3]:
            direcao = "alta"
        elif close[-1] < close[-2] < close[-3]:
            direcao = "baixa"
        else:
            direcao = "indefinida"
    return spread, release, direcao

def calcular_bollinger_bands(close, window=20, num_std=2):
    series = pd.Series(close)
    mean = series.rolling(window).mean()
    std = series.rolling(window).std()
    upper = mean + (std * num_std)
    lower = mean - (std * num_std)
    return {"upper": upper.values, "lower": lower.values}

def consultar_indice_fear_greed():
    try:
        api_key = os.getenv("FEAR_GREED_API_KEY")
        headers = {
            "Accepts": "application/json",
            "x-api-key": api_key
        }
        url = "https://api.alternative.me/fng/?limit=1"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            valor = int(data["data"][0]["value"])
            classificacao = data["data"][0]["value_classification"]
            return valor, classificacao
        else:
            print(f"[FearGreed] Erro {response.status_code}")
            return None, None
    except Exception as e:
        print(f"[FearGreed] Erro ao consultar índice: {e}")
        return None, None
