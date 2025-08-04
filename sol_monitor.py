from indicadores_tecnicos import analisar_ativos
import time
from datetime import datetime
import pytz

ATIVO = 'SOL'
PAR = 'solusdt'
INTERVALO = '1h'
WEBHOOK_URL = 'https://hook.us2.make.com/bh2qm5th0s9owb6xczw45dq7v0t39e1j'

def executar_monitoramento():
    while True:
        try:
            hora_brasilia = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{ATIVO}] Execução: {hora_brasilia}")
            analisar_ativos(ativo=ATIVO, par=PAR, intervalo=INTERVALO, webhook_url=WEBHOOK_URL)

        except Exception as e:
            print(f"[{ATIVO}] Erro: {str(e)}")

        time.sleep(1800)  # Executa a cada 30 minutos

if __name__ == "__main__":
    executar_monitoramento()
