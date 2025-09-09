from LAN import Client,auto_ip
import time

ip = input("Введите ip сервера: ")
if not ip:
    ip = auto_ip()
    print(f"Автоматически определён ip: {ip}")

client = Client(ip)
if client.connect():
    print("Клиент подключен. Команды:")
    print("1 - Синхронизировать файл")
    print("2 - Выйти")
    
    while True:
        command = input("Введите команду: ")
        if command == "1":
            filename = input("Введите имя файла: ")
            client.sync_file(filename)
        elif command == "2":
            break
        else:
            print("Неизвестная команда")
    
    client.disconnect()