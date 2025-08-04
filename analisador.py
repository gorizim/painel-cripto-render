import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from indicadores_tecnicos import (
    calcular_rsi, calcular_stoch_rsi, calcular_mfi,
    calcular_macd, calcular_obv,
    detectar_martelo, detectar_martelo_invertido,
    detectar_engolfo, detectar_estrela_manha, detectar_estrela_noite,
    detectar_tres_soldados_brancos, detectar_tres_corvos_negros,
    detectar_divergencia_rsi, detectar_divergencia_obv,
    detectar_squeeze_overextension, consultar_indice_fear_greed
)
from utils import consultar_eventos_cripto
import os
from dotenv import load_dotenv

load_dotenv()

def analisar_ativos(ativo, par, intervalo, webhook_url):
    url = f"https://api.binance.com/api/v3/klines?symbol={par.upper()}&interval={intervalo}&limit=100"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"[{ativo}] Erro ao obter dados da Binance: {response.status_code}")
        return

    dados = response.json()
    open_prices = [float(c[1]) for c in dados]
    high_prices = [float(c[2]) for c in dados]
    low_prices = [float(c[3]) for c in dados]
    close_prices = [float(c[4]) for c in dados]
    volume = [float(c[5]) for c in dados]

    sinais = []

    # RSI e divergência
    rsi = calcular_rsi(close_prices)
    divergencia_rsi, tipo_div = detectar_divergencia_rsi(close_prices, rsi)
    if divergencia_rsi:
        sinais.append(f"📈 Divergência de RSI detectada ({tipo_div})")

    # OBV e divergência
    obv = calcular_obv(close_prices, volume)
    divergencia_obv, tipo_obv = detectar_divergencia_obv(close_prices, obv)
    if divergencia_obv:
        if tipo_obv == "baixa":
            sinais.append("📉 OBV caindo com preço subindo – distribuição silenciosa")
        else:
            sinais.append("📈 Divergência de OBV detectada (alta)")

    # MACD
    macd, sinal, histograma = calcular_macd(close_prices)
    if histograma[-1] > 0 and histograma[-2] < 0:
        sinais.append("💥 Cruzamento MACD: Bullish")
    elif histograma[-1] < 0 and histograma[-2] > 0:
        sinais.append("🔻 Cruzamento MACD: Bearish")

    # Squeeze e Overextension
    spread, liberado, direcao = detectar_squeeze_overextension(close_prices)
    if liberado:
        if direcao == "alta":
            sinais.append("📊 Squeeze liberado com expansão para cima")
        elif direcao == "baixa":
            sinais.append("📊 Squeeze liberado com expansão para baixo")
        else:
            sinais.append("📊 Squeeze liberado (direção indefinida)")

    # Candlestick patterns
    if detectar_martelo(open_prices, high_prices, low_prices, close_prices):
        sinais.append("🔍 Padrão de martelo detectado")
    if detectar_martelo_invertido(open_prices, high_prices, low_prices, close_prices):
        sinais.append("🔍 Padrão de martelo invertido detectado")
    if detectar_engolfo(open_prices, high_prices, low_prices, close_prices):
        sinais.append("🔍 Engolfo de alta detectado")
    if detectar_estrela_manha(open_prices, high_prices, low_prices, close_prices):
        sinais.append("🔍 Estrela da manhã detectada")
    if detectar_estrela_noite(open_prices, high_prices, low_prices, close_prices):
        sinais.append("🔍 Estrela da noite detectada")
    if detectar_tres_soldados_brancos(open_prices, high_prices, low_prices, close_prices):
        sinais.append("🔍 Três soldados brancos detectado")
    if detectar_tres_corvos_negros(open_prices, high_prices, low_prices, close_prices):
        sinais.append("🔍 Três corvos negros detectado")

    # Fear & Greed Index
    fg_valor, fg_class = consultar_indice_fear_greed()
    if fg_valor is not None:
        sinais.append(f"📊 Sentimento do mercado: {fg_valor} ({fg_class})")

    # 🎯 EVENTOS DO DIA
    eventos = consultar_eventos_cripto()
    for ev in eventos:
        if ev["impacto"] == "alto":
            sinais.append(f"🏛️ Evento: {ev['titulo']} em {ev['data']}")

    # 🚨 Alerta principal se houver forte confluência
    if len([s for s in sinais if "📈" in s or "📉" in s or "💥" in s or "🔻" in s]) >= 4:
        sinais.insert(0, "🚨 Reversão provável (4 ou mais sinais)")

    # Enviar alerta se houver qualquer sinal
    if sinais:
        texto = f"[{ativo}] ⏰ {datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')} - Intervalo {intervalo}\n\n"
        texto += "\n".join(sinais)
        try:
            requests.post(webhook_url, json={"text": texto})
        except Exception as e:
            print(f"[{ativo}] Erro ao enviar webhook: {e}")
    else:
        print(f"[{ativo}] Nenhum sinal relevante no momento.")
