# analisador.py — travas: 1x por candle + near-edge-only | horário BRT (UTC-3)
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from indicadores_tecnicos import (
    calcular_rsi, calcular_stoch_rsi, calcular_mfi,
    calcular_macd, calcular_obv, calcular_bollinger_bands,
    detectar_martelo, detectar_martelo_invertido,
    detectar_engolfo, detectar_estrela_manha, detectar_estrela_noite,
    detectar_tres_soldados_brancos, detectar_tres_corvos_negros,
    detectar_divergencia_rsi, detectar_divergencia_obv,
    detectar_squeeze_overextension,
    # === novos extras ===
    calcular_atr, calcular_percent_b, calcular_bollinger_width,
    calcular_spread_vs_ma, calcular_volatilidade_pct
)
from utils import consultar_eventos_cripto, consultar_indice_fear_greed
import os, time
from dotenv import load_dotenv
load_dotenv()

# ========= utilidades de tempo (BRT)
def _now_brt(fmt="%d/%m/%Y %H:%M:%S"):
    return datetime.now(timezone(timedelta(hours=-3))).strftime(fmt)

# ========= memória simples (processo) p/ cooldown, candle e edge
_LAST_ALERT_TS = {}      # { "ATIVO:tipo": epoch }
_LAST_BAR_CLOSE_TS = {}  # { "ATIVO:INTERVALO": last_close_ms }
_NEAR_STATE = {}         # { "ATIVO:INTERVALO:buy|sell": bool }

def _cooldown_ok(ativo, tipo, minutes):
    if minutes <= 0:
        return True
    k = f"{ativo}:{tipo}"
    now = time.time()
    last = _LAST_ALERT_TS.get(k, 0)
    if (now - last) >= minutes * 60:
        _LAST_ALERT_TS[k] = now
        return True
    return False

# ========= targets e config (via ENV)
def _get_targets(ativo):
    up = ativo.upper()
    buy = os.getenv(f"TARGET_BUY_{up}")
    sell = os.getenv(f"TARGET_SELL_{up}")
    def _parse(x):
        try:
            return float(x) if x and str(x).strip() != "" else None
        except:
            return None
    return _parse(buy), _parse(sell)

def _get_cfg():
    near_pct        = float(os.getenv("TARGET_NEAR_PCT", "3.0"))      # você quer 3.0
    cooldown_min    = int(os.getenv("TARGET_COOLDOWN_MIN", "60"))     # você quer 60
    send_only       = os.getenv("SEND_ONLY_TARGETS", "1") == "1"      # você usa 1
    only_on_new_bar = os.getenv("ONLY_ON_NEW_BAR", "1") == "1"        # NOVO: 1x por candle
    near_edge_only  = os.getenv("NEAR_EDGE_ONLY", "1") == "1"         # NOVO: 🎯 só na ENTRADA
    return near_pct, cooldown_min, send_only, only_on_new_bar, near_edge_only

# ========= flags de SNAPSHOT
def _env_flag(name, default="0"):
    val = os.getenv(name, default)
    return str(val).strip().lower() in ("1","true","yes","y")

def _snapshot_on(ativo):
    up = str(ativo).upper()
    return _env_flag(f"SNAPSHOT_{up}", "0")

# ========= fetch Binance com fallback (mesma lógica)
def _try_fetch_klines(ativo, par, intervalo, base_url):
    url = f"{base_url.rstrip('/')}/api/v3/klines?symbol={par.upper()}&interval={intervalo}&limit=100}"
    # corrigir '}' extra? manter compat c/ versão anterior:
    url = f"{base_url.rstrip('/')}/api/v3/klines?symbol={par.upper()}&interval={intervalo}&limit=100"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r, None
        detalhe = r.text[:200].replace("\n", " ")
        return None, f"[{ativo}] Erro Binance {r.status_code} em {base_url} | Detalhe={detalhe}"
    except Exception as e:
        return None, f"[{ativo}] Erro de rede ao acessar {base_url}: {e}"

def _fetch_candles(ativo, par, intervalo):
    base_env = os.getenv("BINANCE_BASE_URL", "https://data-api.binance.vision").rstrip("/")
    bases = [base_env]
    alt = "https://data-api.binance.vision" if "api.binance.com" in base_env else "https://api.binance.com"
    if alt not in bases:
        bases.append(alt)
    response = None
    last_err = None
    for idx, base in enumerate(bases, start=1):
        response, last_err = _try_fetch_klines(ativo, par, intervalo, base)
        if response is not None:
            if idx > 1:
                print(f"[{ativo}] Fallback OK via {base}")
            break
    if response is None:
        print(f"[{ativo}] Falha final ao obter candles ({par}/{intervalo}). Último erro: {last_err}")
        return None
    return response.json()

# ========= helpers técnicos
def _is_reentrada_bollinger(close, hband, lband):
    c0, c1 = close[-2], close[-1]
    hb0, hb1 = hband[-2], hband[-1]
    lb0, lb1 = lband[-2], lband[-1]
    reentrou_acima  = (c0 > hb0 and c1 <= hb1)   # voltou p/ dentro vindo de cima
    reentrou_abaixo = (c0 < lb0 and c1 >= lb1)   # voltou p/ dentro vindo de baixo
    return reentrou_acima, reentrou_abaixo

def _suporte_resistencia_recent(highs, lows, close):
    resistencia = max(highs[-6:-1])
    suporte     = min(lows[-6:-1])
    dist_res = abs(close[-1] - resistencia) / max(resistencia, 1e-9)
    dist_sup = abs(close[-1] - suporte)     / max(suporte, 1e-9)
    return suporte, resistencia, dist_sup, dist_res

def _slope(series, lookback=3):
    if len(series) < lookback + 1:
        return 0.0
    y = np.array(series[-(lookback+1):], dtype=float)
    x = np.arange(len(y))
    return float(np.polyfit(x, y, 1)[0])

# ========= envio com fragmentação (protege Telegram/Make)
MAX_MSG_LEN = int(os.getenv("MAX_MSG_LEN", "3500"))
def _send_text(webhook_url, texto):
    if not webhook_url:
        print(texto); return
    parts = [texto[i:i+MAX_MSG_LEN] for i in range(0, len(texto), MAX_MSG_LEN)] or [texto]
    for i, chunk in enumerate(parts, 1):
        try:
            suffix = f" (parte {i}/{len(parts)})" if len(parts) > 1 else ""
            requests.post(webhook_url, json={"text": chunk + suffix}, timeout=8)
        except Exception as e:
            print(f"[WEBHOOK] Erro ao enviar: {e}")

# ========= análise principal
def analisar_ativos(ativo, par, intervalo, webhook_url):
    dados = _fetch_candles(ativo, par, intervalo)
    if dados is None:
        return

    # Binance kline: [0] openTime, [1] open, [2] high, [3] low, [4] close, [5] volume, [6] closeTime, ...
    open_prices  = [float(c[1]) for c in dados]
    high_prices  = [float(c[2]) for c in dados]
    low_prices   = [float(c[3]) for c in dados]
    close_prices = [float(c[4]) for c in dados]
    volume       = [float(c[5]) for c in dados]
    preco_atual  = close_prices[-1]
    close_ms     = int(dados[-1][6]) if len(dados[-1]) > 6 else 0  # horário de FECHAMENTO do candle

    near_pct, cooldown_min, send_only_targets, only_on_new_bar, near_edge_only = _get_cfg()
    alvo_buy, alvo_sell = _get_targets(ativo)

    sinais = []

    # ===== Indicadores base
    rsi = calcular_rsi(close_prices)
    macd_line, macd_signal, macd_hist = calcular_macd(close_prices)
    obv = calcular_obv(close_prices, volume)
    mavg, hband, lband = calcular_bollinger_bands(close_prices)
    stoch = calcular_stoch_rsi(close_prices)

    # === Indicadores extras (novos)
    atr14 = calcular_atr(high_prices, low_prices, close_prices, window=14)
    bb_width = calcular_bollinger_width(lband, hband)          # largura absoluta
    percent_b = calcular_percent_b(close_prices, lband, hband) # %B
    spread_vs_ma = calcular_spread_vs_ma(close_prices, mavg)   # (% acima/abaixo da MA) em %
    vol_pct = calcular_volatilidade_pct(close_prices, window=20)  # vol % (janela 20)

    # Divergências
    div_rsi, tipo_div_rsi = detectar_divergencia_rsi(close_prices, rsi)
    div_obv, tipo_div_obv = detectar_divergencia_obv(close_prices, obv)

    # Padrões
    pad_martelo     = detectar_martelo(open_prices, high_prices, low_prices, close_prices)
    pad_mart_inv    = detectar_martelo_invertido(open_prices, high_prices, low_prices, close_prices)
    pad_engolfo     = detectar_engolfo(open_prices, high_prices, low_prices, close_prices)
    pad_estrela_man = detectar_estrela_manha(open_prices, high_prices, low_prices, close_prices)
    pad_estrela_noi = detectar_estrela_noite(open_prices, high_prices, low_prices, close_prices)
    pad_3sold       = detectar_tres_soldados_brancos(open_prices, high_prices, low_prices, close_prices)
    pad_3corvos     = detectar_tres_corvos_negros(open_prices, high_prices, low_prices, close_prices)
    padroes_txt = ",".join([
        n for n, ok in [
            ("martelo", pad_martelo),
            ("martelo_invertido", pad_mart_inv),
            ("engolfo", pad_engolfo),
            ("estrela_manha", p_
