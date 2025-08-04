import threading
import btc_monitor
import eth_monitor
import xrp_monitor
import sol_monitor

def iniciar_monitor(monitor_func, nome):
    print(f"[{nome}] Inicializando...")
    monitor_func()

if __name__ == "__main__":
    threads = []

    threads.append(threading.Thread(target=iniciar_monitor, args=(btc_monitor.executar_monitoramento, "BTC")))
    threads.append(threading.Thread(target=iniciar_monitor, args=(eth_monitor.executar_monitoramento, "ETH")))
    threads.append(threading.Thread(target=iniciar_monitor, args=(xrp_monitor.executar_monitoramento, "XRP")))
    threads.append(threading.Thread(target=iniciar_monitor, args=(sol_monitor.executar_monitoramento, "SOL")))

    for t in threads:
        t.start()

    for t in threads:
        t.join()
