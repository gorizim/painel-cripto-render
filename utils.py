import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
COINMARKETCAL_API_KEY = os.getenv("COINMARKETCAL_API_KEY")

def consultar_eventos_cripto():
    """
    Consulta eventos relevantes usando a API do CoinMarketCal.
    Requer a variável de ambiente COINMARKETCAL_API_KEY definida no .env.
    """
    try:
        headers = {
            'x-api-key': COINMARKETCAL_API_KEY,
            'Accept': 'application/json'
        }
        params = {
            'page': 1,
            'max': 5,
            'coins': 'bitcoin,ethereum,solana,xrp',
            'sortBy': 'hot',
            'verified': 'true'
        }
        url = 'https://developers.coinmarketcal.com/v1/events'
        r = requests.get(url, headers=headers, params=params)

        if r.status_code != 200:
            print(f"[Eventos] Erro na API CoinMarketCal: {r.status_code}")
            return []

        eventos = r.json()
        eventos_filtrados = []
        for ev in eventos:
            data_evento = ev.get('date', '')[:10]
            titulo = ev.get('title', 'Sem título')
            impacto = ev.get('importance', 'low')
            eventos_filtrados.append({
                "titulo": titulo,
                "data": data_evento,
                "impacto": impacto
            })

        return eventos_filtrados
    except Exception as e:
        print(f"[Eventos] Erro: {str(e)}")
        return []

def consultar_indice_fear_greed():
    """
    Consulta o índice de Fear & Greed (Alternative.me).
    Retorna (valor, classificação) ex: (42, 'Fear')
    """
    try:
        r = requests.get("https://api.alternative.me/fng/")
        if r.status_code != 200:
            return None, None

        data = r.json()
        valor = int(data["data"][0]["value"])
        classificacao = data["data"][0]["value_classification"]
        return valor, classificacao
    except:
        return None, None
