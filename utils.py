import os
import requests
import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.volume import OnBalanceVolumeIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands
from dotenv import load_dotenv

# Garanta que .env é carregado também quando alguém importar utils direto
load_dotenv()

# === INDICADORES (compat com seu legado) ===

def get_rsi(close):
    return RSIIndicator(close, window=14).rsi()

def get_mfi(high, low, close, volume, window=14):
    typical_price = (high + low + close) / 3
    money_flow = typical_price * volume
    positive_flow = []
    negative_flow = []

    for i in range(1, len(typical_price)):
        if typical_price[i] > typical_price[i - 1]:
            positive_flow.append(money_flow[i])
            negative_flow.append(0)
        elif typical_price[i] < typical_price[i - 1]:
            positive_flow.append(0)
            negative_flow.append(money_flow[i])
        else:
            positive_flow.append(0)
            negative_flow.append(0)

    pos_mf = pd.Series(positive_flow).rolling(window=window).sum()
    neg_mf = pd.Series(negative_flow).rolling(window=window).sum()
    mfi = 100 - (100 / (1 + (pos_mf / neg_mf)))
    return mfi

def get_obv(close, volume):
    return OnBalanceVolumeIndicator(close, volume).on_balance_volume()

def get_macd(close):
    macd = MACD(close)
    hist = macd.macd_diff()
    if hist.iloc[-1] > 0 and hist.iloc[-2] < 0:
        return "bullish"
    elif hist.iloc[-1] < 0 and hist.iloc[-2] > 0:
        return "bearish"
    else:
        return "neutral"

def get_bollinger_bands(close):
    bb = BollingerBands(close, window=20, window_dev=2)
    return bb.bollinger_hband(), bb.bollinger_lband()

# === EVENTOS EXTERNOS ===

def consultar_eventos_cripto(ativo: str):
    """
    CoinMarketCal – requer API key em COINMARKETCAL_API_KEY.
    Retorna lista (ou [] em caso de erro).
    """
    api_key = os.getenv("COINMARKETCAL_API_KEY")
    if not api_key:
        return []
    url = f"https://developers.coinmarketcal.com/v1/events?coins={ativo}&sortBy=date"
    headers = {"x-api-key": api_key, "Accept": "application/json"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
        print(f"[{ativo}] Erro CoinMarketCal: {r.status_code} {r.text[:150]}")
        return []
    except Exception as e:
        print(f"[{ativo}] Erro CoinMarketCal: {e}")
        return []

def consultar_indice_fear_greed():
    """
    Alternative.me – se não tiver chave, tenta mesmo assim (API pública permite sem key).
    Retorna int (0-100) ou None.
    """
    url = "https://api.alternative.me/fng/?limit=1&format=json"
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            dados = r.json()
            return int(dados['data'][0]['value'])
        print(f"[FNG] HTTP {r.status_code}: {r.text[:120]}")
        return None
    except Exception as e:
        print(f"[FNG] Erro: {e}")
        return None
