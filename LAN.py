""" ЛОКАЛЬНЫЙ СЕРВЕР
Настраивает локальный сервер для обмена файлами между подключёнными пользователями и хостом для приложений BGear
"""

import socket
import ifaddr

import threading

import os
import json
import hashlib

def auto_ip():
    """Автоопределение IP сети
    Автоматически определяет IP-адрес подключённой к ПК сети
    
    Возвращает:
        IP-format: IP-адрес Wi-Fi подключения
    """
    ips = []
    adapters = ifaddr.get_adapters()
    for adapter in adapters:
        for ip in adapter.ips:
            if str(ip).count(".")==3:
                ips.append(str(ip.ip))
    return ips[-2] # Я чувствую, что из всех возможных ip, этот принадлежит подключённому WiFi


class Server:
    
    def __init__(self,address = auto_ip(),port = 2000, report = True, data_dir="BGearLAN/Data/Server"):
        
        self.report = report
        
        self.address = address
        self.port = port
        
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        self.clients = []
        self.running = False
        

        self.server = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        self.server.bind((self.address,self.port))
        
        self.lock = threading.Lock()
    
    def listen(self,max_connects_count = 3):
        """Прослушивание
        Запускает сервер в режиме прослушивания

        Пргументы:
            max_connects_count (int, optional): Максимальное число подключений
        """
        
        self.server.listen(max_connects_count)
        self.running = True
        if self.report:
            print("Сервер начал прослушивание")
        
        accept_thread = threading.Thread(target=self._accept_clients)
        accept_thread.daemon = True
        accept_thread.start()
        if self.report:
            print(f"● Сервер активен")
        
    def _accept_clients(self):
        """Принятие клиентов
        Принимает новые подключения в отдельном потоке
        """
        while self.running:
            try:
                conn,addr = self.server.accept()
                if self.report:
                    print(f"Подключен клиент: {addr}")
                    
                client_socket = conn

                with self.lock:
                    self.clients.append({
                        "socket":client_socket,
                        "address":addr,
                        "thread":None
                    })
                
                
                client_thread = threading.Thread(
                    target = self._handle_client,
                    args = (client_socket, addr)
                )
                client_thread.daemon = True
                client_thread.start()
                
                with self.lock:
                    for client in self.clients:
                        if client["address"] == addr:
                            client["thread"] = client_thread
                
            except OSError:
                break
    
    def _handle_client(self,conn,addr):
        """Обработка данных клиента
        Обрабатывает данные определённого подключённого клиента
        Аргументы:
            conn (socket): Сокет клиента
            addr (str): IP-адрес клиента
        """
        try:
            with conn:
                while self.running:
                    try:
                        
                        conn.settimeout(1.0)
                                            
                        data = conn.recv(1024)
                        if not data:
                            break
                        if self.report:
                            print(f"Получены данные от клиента {addr}")
                        
                        message = data.decode()
                        print(f"Команда от {addr}: {message}")
                        
                        if message.startswith("SYNC_REQUEST:"):
                            self._handle_sync_request(conn,message)
                        elif message.startswith("GET_FILE:"):
                            self._send_file(conn, message)
                        elif message.startswith("SEND_FILE:"):
                            self._receive_file(conn, message)
                        else:
                            conn.sendall("UNKNOWN_COMMAND".encode())
                        
                    except socket.timeout:
                        continue
                    except ConnectionResetError:
                        if self.report:
                            print(f"Клиент {addr} разорвал соединение")
                        break
                    except Exception as er:
                        if self.report:
                            print(f"Ошибка подключения клиента {addr}: {er}")
                        break
        
        finally:
            with self.lock:
                self.clients = [cli for cli in self.clients if cli["address"] != addr]
            if self.report:
                print(f"Клиент {addr} отключён")
    
    def _handle_sync_request(self,conn,message):
        """Синхронизация
        Обработка запроса на синхронизацию файлов
       
        Аргументы:
            conn (socket): Подключённый клиент
            message (string): Команда клиента
        """
        
        try:
            # SYNC_REQUEST:имя_файла
            filename = message.split(':',1)[1]
            filepath = os.path.join(self.data_dir,filename)
            
            if os.path.exists(filepath):
                # Сбор информации о файле
                file_info = {
                    'exists':True,
                    'size':os.path.getsize(filepath),
                    'modified':os.path.getmtime(filepath),
                    'hash':self._get_file_hash(filepath)
                }
                # Отправка информации о существующем файле
                conn.sendall(json.dumps(file_info).encode())
                if self.report:
                    print(f"Отправлена информация о файле {filename}")
                
            else:
                # Файл не найден на сервере
                conn.sendall(json.dumps({"exists":False}).encode())
                if self.report:
                    print(f"Файл {filename} не найден на сервере")
                
        except Exception as er:
            conn.sendall(json.dumps({"error":str(er)}).encode())
            
    def _send_file(self,conn,message):
        """Отправка файла
        Отправляет файл с сервера клиенту

        Аргументы:
            conn (socket): Подключённый клиент
            message (str): Команда клиента
        """
        
        try:
            filename = message.split(":",1)[1]
            filepath = os.path.join(self.data_dir,filename)
            
            if os.path.exists(filepath):
                with self.lock:
                    # Отправка размера файла
                    file_size = os.path.getsize(filepath)
                    conn.sendall(f"FILE_SIZE:{file_size}".encode())
                    
                    # Ожидание подтверждения
                    ack = conn.recv(1024).decode()
                    if ack == "READY":
                        # Отправка файла
                        with open(filepath, 'rb') as file:
                            sended = 0
                            while True:
                                data = file.read(4*2**23)
                                if not data:
                                    break
                                conn.sendall(data)
                                if self.report:
                                    sended += len(data)
                                    print(f"Отправлено {sended/file_size*100*100000//1/100000}%")
                if self.report:
                    print(f"Файл {filename} успешно отправлен клиенту")

            else:
                conn.sendall("FILE_NOT_FOUND".encode())
        
        except Exception as er:
            conn.sendall(f"ERROR:{str(er)}".encode())
            
    def _receive_file(self,conn,message):
        """Получение файла
        Принимает файл от клиента

        Аргументы:
            conn (socket): Подключеный клиент
            message (str): Команда клиента
        """
        
        try:
            # SEND_FILE:filename:filesize
            mes_parts = message.split(':')
            filename = mes_parts[1]
            file_size = int(mes_parts[2])
            
            filepath = os.path.join(self.data_dir,filename)
            
            # Подтверждение готовности
            conn.sendall("READY".encode())
            
            # Принятие файла
            recv_file_size = 0
            with open(filepath,'wb') as file:
                while recv_file_size < file_size:
                    data = conn.recv(min(4*2**23,file_size-recv_file_size))
                    if not data:
                        break
                    file.write(data)
                    recv_file_size += len(data)
                    if self.report:
                        print(f"Получено {recv_file_size/file_size*100*100000//1/100000}%")
            
            if self.report:
                print(f"Файл {filename} получен")
            conn.sendall("FILE_RECEIVED".encode())
            
        except Exception as er:
            conn.sendall(f"ERROR:{str(er)}".encode())
            
    def _get_file_hash(self,filepath):
        """Проверка целостности
        Вычисление хэша файла для проверки его целостности
        
        Аргументы:
            filepath (str): Путь к файлу
        """
        
        hash_md5 = hashlib.md5()
        with open(filepath,"rb") as file:
            for chunk in iter(lambda: file.read(4096),b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
            
    def stop(self):
        """Остановка сервера
        Полностью останавливает сервер
        """
        self.running = False
        for conn,addr,thread in self.clients:
            thread.stop()
            conn.close()
        self.server.close()
        if self.report:
            print(f"Сервер отключён")
        
        
    
class Client:
    
    def __init__(self,server_address = auto_ip(),server_port = 2000,report=True,data_dir="BGearLAN/Data/Client"):
        
        self.report = report
        
        self.serv_addr = server_address
        self.serv_port = server_port
        self.connected = False
        
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        self.client = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        
    def connect(self):
        """Подключение
        Подключение к серверу с заданным адресом
        """
        try:
            self.client.connect((self.serv_addr,self.serv_port))
            self.connected = True
            if self.report:
                print(f"Успешное подключение к серверу {(self.serv_addr,self.serv_port)}")
            
            if self.report:
                print(f"● Вы подключены к серверу")
            
            return True
        except Exception as er:
            if self.report:
                print(f"Подключение не удалось. Ошибка: {er}")
            return False
    
    
    def sync_file(self,filename):
        """Синхронизация файлов
        Синхронизирует файлы клиента с файлами сервера

        Аргументы:
            filename (str): Путь к синхронизируемому файлу
        """
        
        if not self.connected:
            if self.report:
                print("Нет подключения к серверу")
                return False
            return False
            
        try:
            # Запрос информации о файле на сервере
            self.client.sendall(f"SYNC_REQUEST:{filename}".encode())
            
            # Получение ответа от сервера
            response = self.client.recv(1024).decode()
            serv_info = json.loads(response)
            
            local_path = os.path.join(self.data_dir,filename)
            
            if serv_info.get("error"):
                if self.report:
                    print(f"Ошибка сервера: {serv_info['error']}")
                return False

            if not serv_info["exists"]:
                # Файл отсутствует на сервере
                # Инициируется отправка файла на сервер
                if os.path.exists(local_path):
                    if self.report:
                        print("Отправка файла на сервер")
                    return self._send_file_to_server(filename)
                else:
                    if self.report:
                        print(f"Файла не существует")
                    return False
            
            if os.path.exists(local_path):
                local_hash = self._get_file_hash(local_path)
                if local_hash == serv_info["hash"]:
                    if self.report:
                        print("Синхронизации не требуется")
                    return True
                else:
                    # Выбор новейшей версии файла
                    local_mtime = os.path.getmtime(local_path)
                    if local_mtime > serv_info['modified']:
                        if self.report:
                            print("Отправка версии клиента")
                        self._send_file_to_server(filename)
                    else:
                        if self.report:
                            print("Получение версии сервера")
                        self._get_file_from_server(filename)
            
            else:
                if self.report:
                    print("Получение файла с сервера")
                self._get_file_from_server(filename)
    
            return True
    
        except Exception as er:
            if self.report:
                print(f"Ошибка синхронизации: {er}")
            return False
    
    def _send_file_to_server(self,filename):
        """Отправка файла на сервер
        Отправляет версию файла клиента на сервер

        Аргументы:
            filename (str): Имя отправляемого файла
        """
        
        local_path = os.path.join(self.data_dir,filename)
        
        if not os.path.exists(local_path):
            if self.report:
                print("Файл не существует")
            return False
        
        file_size = os.path.getsize(local_path)
        self.client.sendall(f"SEND_FILE:{filename}:{file_size}".encode())
        
        # Ожидание подтверждения от сервера
        response = self.client.recv(1024).decode()
        if self.report:
            print(f"Ответ сервера на SEND_FILE: {response}")
        if response == "READY":
            # Отправка файла на сервер
            with open(local_path,'rb') as file:
                sended = 0
                while True:
                    data = file.read(4*2**23)
                    if not data:
                        break
                    self.client.sendall(data)
                    if self.report:
                        sended += len(data)
                        print(f"Отправлено {sended/file_size*100*100000//1/100000}%")
                    
                    
            # Ожидание подтверждения получения файла сервером
            ack = self.client.recv(1024).decode()
            if self.report:
                print(f"Подтверждение от сервера:{ack}")
            if ack == "FILE_RECEIVED":
                if self.report:
                    print("Файл получен сервером")
                return True
        
        if self.report:
            print("Ошибка отправки файла")
        return False

    def _get_file_from_server(self,filename):
        """Установка файла с сервера

        Аргументы:
            filename (str): Имя получаемого файла
        """
        
        self.client.sendall(f"GET_FILE:{filename}".encode())
        
        # Получение размера файла
        response = self.client.recv(1024).decode()
        if response.startswith("FILE_SIZE:"):
            file_size = int(response.split(":")[1])
            
            # Подтверждение готовности
            self.client.sendall("READY".encode())
            
            # Принятие файла
            local_path = os.path.join(self.data_dir,filename)
            recv_file_size = 0
            
            with open(local_path,'wb') as file:
                while recv_file_size < file_size:
                    data = self.client.recv(min(4*2**23,file_size-recv_file_size))
                    if not data:
                        break
                    file.write(data)
                    recv_file_size += len(data)
                    if self.report:
                        print(f"Получено {recv_file_size/file_size*100*100000//1/100000}%")
            
            if self.report:
                print(f"Файл {filename} загружен с сервера")
            return True
        else:
            if self.report:
                print(f"Ошибка: {response}")
            return False

    def _get_file_hash(self,filepath):
        """Вычисление хэша файла
        Вычисляет хэш файла для проверки его целостности
        
        Аргументы:
            filepath (str): Имя файла
        """
        
        hash_md5 = hashlib.md5()
        with open(filepath,'rb') as file:
            for chunk in iter(lambda: file.read(4096),b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
        
    def disconnect(self):
        """Отключение
        Отключает клиента от сервера
        """
        
        self.connected = False
        self.client.close()
        if self.report:
            print("Вы отключены от сервера")
        


if __name__ != "__main__":
    bg_server = Server()
    bg_client = Client()
else:
    from time import sleep
    text = "HW"
    w = open("BGearLAN/Data/Server/test.txt",'w')
    w.write(text)
    w.close()
    
    serv = Server()
    serv.listen()
    
    cli = Client()
    cli.connect()
    cli.sync_file("test.txt")
    
    sleep(1)
    cli.disconnect()
    serv.stop()