import threading
import time

print("[INÍCIO] Iniciando painel_main.py", flush=True)

try:
    import btc_monitor
    print("[IMPORT] btc_monitor OK", flush=True)
except Exception as e:
    print("[IMPORT ERROR] btc_monitor:", e, flush=True)

try:
    import eth_monitor
    print("[IMPORT] eth_monitor OK", flush=True)
except Exception as e:
    print("[IMPORT ERROR] eth_monitor:", e, flush=True)

try:
    import xrp_monitor
    print("[IMPORT] xrp_monitor OK", flush=True)
except Exception as e:
    print("[IMPORT ERROR] xrp_monitor:", e, flush=True)

try:
    import sol_monitor
    print("[IMPORT] sol_monitor OK", flush=True)
except Exception as e:
    print("[IMPORT ERROR] sol_monitor:", e, flush=True)

def iniciar_monitor(monitor_func, nome):
    print(f"[{nome}] Inicializando monitoramento...", flush=True)
    try:
        monitor_func()
    except Exception as e:
        print(f"[{nome}] ERRO ao iniciar monitoramento:", e, flush=True)

if __name__ == "__main__":
    print("[MAIN] Executando painel principal...", flush=True)

    threads = [
        threading.Thread(target=iniciar_monitor, args=(btc_monitor.executar_monitoramento, "BTC")),
        threading.Thread(target=iniciar_monitor, args=(eth_monitor.executar_monitoramento, "ETH")),
        threading.Thread(target=iniciar_monitor, args=(xrp_monitor.executar_monitoramento, "XRP")),
        threading.Thread(target=iniciar_monitor, args=(sol_monitor.executar_monitoramento, "SOL")),
    ]

    for t in threads:
        t.start()

    print("[MAIN] Todas as threads foram iniciadas", flush=True)

    while True:
        print("[PAINEL] Painel rodando... ✅", flush=True)
        time.sleep(300)
