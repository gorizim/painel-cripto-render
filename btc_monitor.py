# btc_monitor.py
from analisador import analisar_ativos
import time
from datetime import datetime
import pytz
import os

ATIVO = 'BTC'
PAR = 'btcusdt'
INTERVALO = '1h'
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

def executar_monitoramento():
    while True:
        try:
            hora_brasilia = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{ATIVO}] Execução: {hora_brasilia}")
            analisar_ativos(ativo=ATIVO, par=PAR, intervalo=INTERVALO, webhook_url=WEBHOOK_URL)
        except Exception as e:
            print(f"[{ATIVO}] Erro: {str(e)}")

        time.sleep(1800)

if __name__ == "__main__":
    executar_monitoramento()
