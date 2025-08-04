FROM python:3.10.5

# Устанавливаем зависимости для вашего проекта
COPY requirements.txt /diwibot/app/
RUN pip install --no-cache-dir -r /diwibot/app/requirements.txt

# Копируем исходный код проекта в Docker-образ
COPY . /diwibot/app

# Задаем рабочую директорию
WORKDIR /diwibot/app

# Указываем порты, которые будут прослушиваться внутри контейнера
EXPOSE 8080

# Команда для запуска main.py
CMD ["python", "main.py"]
#CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

