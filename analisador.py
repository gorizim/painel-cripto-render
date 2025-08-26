# analisador.py — travas: 1x por candle + near-edge-only | horário BRT (UTC-3)
import os, time, requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from indicadores_tecnicos import (
    calcular_rsi, calcular_stoch_rsi, calcular_mfi,
    calcular_macd, calcular_obv, calcular_bollinger_bands,
    detectar_martelo, detectar_martelo_invertido,
    detectar_engolfo, detectar_estrela_manha, detectar_estrela_noite,
    detectar_tres_soldados_brancos, detectar_tres_corvos_negros,
    detectar_divergencia_rsi, detectar_divergencia_obv,
    detectar_squeeze_overextension,
    # extras
    calcular_atr, calcular_percent_b, calcular_bollinger_width,
    calcular_spread_vs_ma, calcular_volatilidade_pct
)
from utils import consultar_eventos_cripto, consultar_indice_fear_greed

# Garante .env carregado neste fluxo também
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

# ========= flags e config (via ENV)
def _env_flag(name, default="0"):
    val = os.getenv(name, default)
    return str(val).strip().lower() in ("1", "true", "yes", "y")

def _snapshot_on(ativo):
    return _env_flag(f"SNAPSHOT_{str(ativo).upper()}", "0")

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
    near_pct        = float(os.getenv("TARGET_NEAR_PCT", "3.0"))
    cooldown_min    = int(os.getenv("TARGET_COOLDOWN_MIN", "60"))
    send_only       = os.getenv("SEND_ONLY_TARGETS", "1") == "1"
    only_on_new_bar = os.getenv("ONLY_ON_NEW_BAR", "1") == "1"
    near_edge_only  = os.getenv("NEAR_EDGE_ONLY", "1") == "1"
    return near_pct, cooldown_min, send_only, only_on_new_bar, near_edge_only

# ========= fetch Binance com fallback
def _try_fetch_klines(ativo, par, intervalo, base_url):
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
    reentrou_acima  = (c0 > hb0 and c1 <= hb1)
    reentrou_abaixo = (c0 < lb0 and c1 >= lb1)
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
            payload = {
                "text": chunk + suffix,
                "message": chunk + suffix,   # redundância
                "content": chunk + suffix    # redundância
            }
            requests.post(webhook_url, json=payload, timeout=8)
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

    # ===== Indicadores base
    rsi = calcular_rsi(close_prices)
    macd_line, macd_signal, macd_hist = calcular_macd(close_prices)
    obv = calcular_obv(close_prices, volume)
    mavg, hband, lband = calcular_bollinger_bands(close_prices)
    stoch = calcular_stoch_rsi(close_prices)

    # ===== Extras
    atr14 = calcular_atr(high_prices, low_prices, close_prices, window=14)
    bb_width = calcular_bollinger_width(lband, hband)
    percent_b = calcular_percent_b(close_prices, lband, hband)
    spread_vs_ma = calcular_spread_vs_ma(close_prices, mavg)
    vol_pct = calcular_volatilidade_pct(close_prices, window=20)

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
    padroes_txt = ",".join([n for n, ok in [
        ("martelo", pad_martelo),
        ("martelo_invertido", pad_mart_inv),
        ("engolfo", pad_engolfo),
        ("estrela_manha", pad_estrela_man),
        ("estrela_noite", pad_estrela_noi),
        ("tres_soldados", pad_3sold),
        ("tres_corvos", pad_3corvos),
    ] if ok]) or "nenhum"

    # S&O
    _, liberado, direcao = detectar_squeeze_overextension(close_prices)

    # S/R e reentrada
    suporte, resistencia, dist_sup, dist_res = _suporte_resistencia_recent(high_prices, low_prices, close_prices)
    reentrou_acima, reentrou_abaixo = _is_reentrada_bollinger(close_prices, hband, lband)

    # Tendências curtas
    macd_hist_sobe = (_slope(macd_hist, 3) > 0)
    macd_hist_cai  = (_slope(macd_hist, 3) < 0)
    stoch_sobe     = (_slope(stoch, 3) > 0)
    stoch_cai      = (_slope(stoch, 3) < 0)

    def _near(x, alvo, pct):
        return (alvo is not None) and (abs(x - alvo) / max(alvo, 1e-9) <= (pct / 100.0))

    # ===== Travamento “1x por candle”
    allow_send = True
    if only_on_new_bar:
        key_bar = f"{ativo}:{intervalo}"
        last = _LAST_BAR_CLOSE_TS.get(key_bar)
        if last is not None and close_ms == last:
            allow_send = False
        else:
            _LAST_BAR_CLOSE_TS[key_bar] = close_ms

    # ===== Confluências
    criterios_fundo = 0; explic_fundo = []
    if stoch[-1] < 0.2 and stoch_sobe:
        criterios_fundo += 1; explic_fundo.append("StochRSI < 0.2 e subindo")
    if (macd_hist[-1] > 0 and macd_hist[-2] < 0) or macd_hist_sobe:
        criterios_fundo += 1; explic_fundo.append("MACD/hist virando p/ alta")
    if div_rsi and tipo_div_rsi == "alta":
        criterios_fundo += 1; explic_fundo.append("Divergência RSI (alta)")
    if div_obv and tipo_div_obv == "alta":
        criterios_fundo += 1; explic_fundo.append("Divergência OBV (alta)")
    if (pad_martelo or pad_estrela_man or pad_engolfo) and dist_sup < 0.01:
        criterios_fundo += 1; explic_fundo.append("Candle de reversão em suporte ±1%")
    if reentrou_abaixo:
        criterios_fundo += 1; explic_fundo.append("Reentrada acima da banda inferior")

    criterios_topo = 0; explic_topo = []
    if stoch[-1] > 0.8 and stoch_cai:
        criterios_topo += 1; explic_topo.append("StochRSI > 0.8 e caindo")
    if (macd_hist[-1] < 0 and macd_hist[-2] > 0) or macd_hist_cai:
        criterios_topo += 1; explic_topo.append("MACD/hist virando p/ baixa")
    if div_rsi and tipo_div_rsi == "baixa":
        criterios_topo += 1; explic_topo.append("Divergência RSI (baixa)")
    if div_obv and tipo_div_obv == "baixa":
        criterios_topo += 1; explic_topo.append("Divergência OBV (baixa)")
    if (pad_estrela_noi or pad_engolfo or pad_3corvos) and dist_res < 0.01:
        criterios_topo += 1; explic_topo.append("Candle de reversão em resistência ±1%")
    if reentrou_acima:
        criterios_topo += 1; explic_topo.append("Reentrada abaixo da banda superior")

    # ===== Gatilhos (com NEAR edge-only opcional)
    near_buy  = _near(preco_atual, alvo_buy,  near_pct)
    near_sell = _near(preco_atual, alvo_sell, near_pct)

    st_key_buy  = f"{ativo}:{intervalo}:buy"
    st_key_sell = f"{ativo}:{intervalo}:sell"
    prev_near_buy  = _NEAR_STATE.get(st_key_buy, False)
    prev_near_sell = _NEAR_STATE.get(st_key_sell, False)

    def _edge(now_near, prev_near):
        return (now_near and not prev_near) if near_edge_only else now_near

    sinais = []

    # COMPRA
    if _edge(near_buy, prev_near_buy):
        if criterios_fundo >= 3 and _cooldown_ok(ativo, "buy_confluence", cooldown_min):
            sinais.append(f"✅ FUNDO REAL (confluência ≥3) perto do alvo de COMPRA {alvo_buy:.2f} USDT")
            sinais.append("• " + " | ".join(explic_fundo))
        elif _cooldown_ok(ativo, "buy_near", cooldown_min):
            sinais.append(f"🎯 Próximo ao alvo de COMPRA {alvo_buy:.2f} USDT — aguardando confluência (atual {preco_atual:.2f})")

    # VENDA
    if _edge(near_sell, prev_near_sell):
        if criterios_topo >= 3 and _cooldown_ok(ativo, "sell_confluence", cooldown_min):
            sinais.append(f"✅ TOPO REAL (confluência ≥3) perto do alvo de VENDA {alvo_sell:.2f} USDT")
            sinais.append("• " + " | ".join(explic_topo))
        elif _cooldown_ok(ativo, "sell_near", cooldown_min):
            sinais.append(f"🎯 Próximo ao alvo de VENDA {alvo_sell:.2f} USDT — aguardando confluência (atual {preco_atual:.2f})")

    _NEAR_STATE[st_key_buy]  = bool(near_buy)
    _NEAR_STATE[st_key_sell] = bool(near_sell)

    # ===== Complementos opcionais (FG/Eventos controlados por ENV)
    fg_valor = consultar_indice_fear_greed() if os.getenv("INCLUDE_FG", "0") == "1" else None
    eventos_textos = []
    if os.getenv("INCLUDE_EVENTS", "0") == "1":
        try:
            eventos = consultar_eventos_cripto(ativo)
            if isinstance(eventos, list):
                for ev in eventos:
                    if ev.get("impacto") == "alto":
                        titulo = ev.get("titulo") or ev.get("title") or "Evento"
                        data_ev = ev.get("data") or ev.get("date_event") or "data não informada"
                        eventos_textos.append(f"{titulo} ({data_ev})")
                        sinais.append(f"🏛️ Evento: {titulo} em {data_ev}")
        except Exception:
            pass

    # ===== BLOCO para GPT (com extras)
    gpt_block = (
        "[CRYPTO_ANALYTICS]\n"
        f"ativo={ativo}\npar={par.upper()}\nintervalo={intervalo}\n"
        f"ts_brt={_now_brt()}\n"
        f"preco_atual_usdt={preco_atual:.2f}\n"
        f"rsi14={rsi[-1]:.2f}\n"
        f"stochrsi={stoch[-1]:.3f}\n"
        f"stochrsi_trend={'up' if stoch_sobe else ('down' if stoch_cai else 'flat')}\n"
        f"macd_line={macd_line[-1]:.5f}\nmacd_signal={macd_signal[-1]:.5f}\nmacd_hist={macd_hist[-1]:.5f}\n"
        f"macd_trend={'up' if macd_hist_sobe else ('down' if macd_hist_cai else 'flat')}\n"
        f"obv_last={obv[-1]:.0f}\n"
        f"divergencia_rsi={tipo_div_rsi if div_rsi else 'nenhuma'}\n"
        f"divergencia_obv={tipo_div_obv if div_obv else 'nenhuma'}\n"
        f"bollinger_ma={mavg[-1]:.2f}\n"
        f"bollinger_sup={hband[-1]:.2f}\n"
        f"bollinger_inf={lband[-1]:.2f}\n"
        f"bollinger_reentrada={'acima' if reentrou_acima else ('abaixo' if reentrou_abaixo else 'nao')}\n"
        f"atr14={atr14[-1]:.2f}\n"
        f"bb_percent_b={percent_b[-1]:.3f}\n"
        f"bb_width={bb_width[-1]:.2f}\n"
        f"spread_vs_ma_pct={spread_vs_ma[-1]:.2f}\n"
        f"volatilidade_pct20={vol_pct[-1]:.2f}\n"
        f"suporte={suporte:.2f}\nresistencia={resistencia:.2f}\n"
        f"dist_suporte_pct={dist_sup*100:.2f}\n"
        f"dist_resistencia_pct={dist_res*100:.2f}\n"
        f"squeeze_liberado={'true' if liberado else 'false'}\n"
        f"squeeze_direcao={direcao or 'neutra'}\n"
        f"volume_last={volume[-1]:.2f}\n"
        f"volume_media20={(np.mean(volume[-21:-1]) if len(volume)>=21 else np.mean(volume)):.2f}\n"
        f"fg={fg_valor if fg_valor is not None else 'NA'}\n"
        f"target_buy={alvo_buy if alvo_buy is not None else 'NA'}\n"
        f"target_sell={alvo_sell if alvo_sell is not None else 'NA'}\n"
        f"near_pct={near_pct}\n"
        f"criterios_fundo={criterios_fundo}\ncriterios_topo={criterios_topo}\n"
        f"candles_detectados={padroes_txt}\n"
        f"eventos_alto_impacto={' ; '.join(eventos_textos) if eventos_textos else 'nenhum'}\n"
        "[/CRYPTO_ANALYTICS]"
    )

    # ===== SNAPSHOT manual (fora das travas; envia sempre que ligado)
    if _snapshot_on(ativo):
        cab = f"[{ativo}] 📸 SNAPSHOT — {_now_brt()} - Intervalo {intervalo} | Preço: {preco_atual:.2f} USDT"
        _send_text(webhook_url, cab + "\n\n" + gpt_block)

    # ===== Política de envio normal
    if send_only_targets and not any(s.startswith(("✅", "🎯")) for s in sinais):
        print(f"[{ativo}] Sem alvo próximo/confirmado — não enviar (SEND_ONLY_TARGETS=1).")
        return

    if not allow_send:
        print(f"[{ativo}] Candle em formação — alertas suprimidos neste candle (ONLY_ON_NEW_BAR=1).")
        return

    if sinais:
        cab = f"[{ativo}] ⏰ {_now_brt()} - Intervalo {intervalo} | Preço: {preco_atual:.2f} USDT"
        _send_text(webhook_url, cab + "\n\n" + "\n".join(sinais) + "\n\n" + gpt_block)
    else:
        print(f"[{ativo}] Nenhum sinal relevante no momento.")
