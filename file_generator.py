import os
sizetype = input("Введите, в чём будет измеряться размер файла: ГБ/МБ/КБ/Б ").upper()
sizes = {
    "ГБ": 2**3 * 2**30,
    "МБ": 2**3 * 2**20,
    "КБ": 2**3 * 2**10,
    "Б":  2**3 * 2**0
}
filesize = int(input(f'Введите размер файла в {sizetype} '))

os.makedirs("TestSizeFiles/", exist_ok=True)
file = open(f"TestSizeFiles/Test - {filesize} {sizetype}","wb")

filesize *= sizes[sizetype]

file.write('0'.encode()*(filesize//8))
print('Файл успешно создан')