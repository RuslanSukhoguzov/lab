from LAN import Server,auto_ip
import time

ip = input("Введите ip сети: ")
if not ip:
    ip = auto_ip()
    print("IP-адрес сервера может быть вот такой: ",ip)

server = Server(ip)
server.listen()

print("Сервер запущен. Нажмите Ctrl+C для остановки")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    server.stop()
