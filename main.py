import sys
import asyncio
import json
import os
import random
import string
import time
import aiohttp 
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QHBoxLayout, QTextEdit, QProgressBar,
                             QMessageBox, QFileDialog, QCheckBox, QSpinBox,
                             QComboBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from qt_material import apply_stylesheet, list_themes

CHECKED_USERNAMES_FILE = "checked_usernames.json"
AVAILABLE_USERNAMES_FILE = "available.txt"

# --- Вспомогательные функции ---
def generate_username(length=3, use_digits=True, use_underscore=True):
    """Генерирует случайное имя пользователя."""
    try:
        characters = string.ascii_lowercase
        if use_digits:
            characters += string.digits
        if use_underscore:
            characters += "_"
        return ''.join(random.choice(characters) for _ in range(length))
    except Exception as e:
        print(f"Ошибка при генерации имени пользователя: {e}")
        return None

def load_checked_usernames():
    """Загружает список проверенных имен пользователей из JSON файла."""
    try:
        with open(CHECKED_USERNAMES_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Ошибка при загрузке проверенных имен пользователей: {e}")
        return []

def save_checked_usernames(checked_usernames):
    """Сохраняет список проверенных имен пользователей в JSON файл."""
    try:
        with open(CHECKED_USERNAMES_FILE, "w") as f:
            json.dump(checked_usernames, f)
    except Exception as e:
        print(f"Ошибка при сохранении проверенных имен пользователей: {e}")

# --- Класс для проверки имен пользователей в отдельном потоке ---
class CheckerThread(QThread):
    signal_update_taken_log = pyqtSignal(str)
    signal_update_available_log = pyqtSignal(str)
    signal_update_progress = pyqtSignal(int)
    signal_finished = pyqtSignal()

    def __init__(self, mode, usernames_file=None, length=3, use_digits=True,
                 use_underscore=True, delay_ms=0):
        super().__init__()
        self.mode = mode
        self.usernames_file = usernames_file
        self.length = length
        self.use_digits = use_digits
        self.use_underscore = use_underscore
        self.delay_ms = delay_ms / 1000  # Перевод миллисекунд в секунды
        self.checked_usernames = load_checked_usernames()
        self.running = True

    async def check_username(self, session, username):
        """Проверяет доступность имени пользователя Steam."""
        start_time = time.time()
        try:
            async with session.get(f'https://steamcommunity.com/id/{username}') as response:
                text = await response.text()
                elapsed_time = (time.time() - start_time) * 1000  # Время проверки в мс
                if '<div class="error_ctn">' in text:
                    self.signal_update_available_log.emit(f"Доступно: {username} ({elapsed_time:.2f} мс)")
                    with open(AVAILABLE_USERNAMES_FILE, "a") as x:
                        x.write(f"{username}\n")
                else:
                    self.signal_update_taken_log.emit(f"Занято: {username} ({elapsed_time:.2f} мс)")
        except Exception as e:
            self.signal_update_taken_log.emit(f"Ошибка: {username} - {str(e)}")

        await asyncio.sleep(self.delay_ms)

    async def check_usernames_from_file(self, session):
        """Проверяет имена пользователей из файла."""
        try:
            with open(self.usernames_file, 'r', encoding='UTF-8', errors='replace') as u:
                usernames = u.read().splitlines()
                if not usernames:
                    self.signal_update_taken_log.emit("В файле не найдено имен пользователей!")
                    return

                total_usernames = len(usernames)
                for i, username in enumerate(usernames):
                    if not self.running:
                        break
                    await self.check_username(session, username)
                    self.signal_update_progress.emit(int((i + 1) / total_usernames * 100))
        except Exception as e:
            self.signal_update_taken_log.emit(f"Ошибка при чтении файла: {e}")

    async def generate_and_check_usernames(self, session):
        """Бесконечно генерирует и проверяет имена пользователей."""
        while self.running:
            username = generate_username(self.length, self.use_digits, self.use_underscore)
            if username and username not in self.checked_usernames:
                self.checked_usernames.append(username)
                save_checked_usernames(self.checked_usernames)
                await self.check_username(session, username)

    async def run_checks(self):
        """Запускает проверку в зависимости от выбранного режима."""
        async with aiohttp.ClientSession() as session:
            if self.mode == "file":
                await self.check_usernames_from_file(session)
            elif self.mode == "generate":
                await self.generate_and_check_usernames(session)

    def run(self):
        """Запускает асинхронную проверку."""
        try:
            asyncio.run(self.run_checks())
        except Exception as e:
            print(f"Ошибка при запуске проверки: {e}")
        finally:
            self.signal_finished.emit()

    def stop(self):
        """Останавливает проверку."""
        self.running = False

# --- Класс главного окна ---
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Проверка имен пользователей Steam")
        self.setGeometry(100, 100, 800, 600)
        self.threads = []  # Список для хранения запущенных потоков
        self.speed_mapping = {  # Соответствие скорости количеству потоков
            "Медленно": 1,
            "Нормально": 3,
            "Быстро": 5
        }
        self.init_ui()

    def init_ui(self):
        # --- Виджеты ---
        self.mode_label = QLabel("Выберите режим:")
        self.file_button = QPushButton("Проверить из файла")
        self.generate_button = QPushButton("Генерировать и проверять")
        self.file_label = QLabel("Выбранный файл:")
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.browse_button = QPushButton("Обзор")

        self.generator_settings_label = QLabel("Настройки генератора:")
        self.length_label = QLabel("Длина имени пользователя:")
        self.length_spinbox = QSpinBox()
        self.length_spinbox.setMinimum(3)
        self.length_spinbox.setMaximum(10)
        self.length_spinbox.setValue(3)
        self.use_digits_checkbox = QCheckBox("Использовать цифры")
        self.use_digits_checkbox.setChecked(True)
        self.use_underscore_checkbox = QCheckBox("Использовать символ подчеркивания _")
        self.use_underscore_checkbox.setChecked(True)

        self.speed_label = QLabel("Скорость проверки:")
        self.speed_combobox = QComboBox()
        self.speed_combobox.addItems(["Медленно", "Нормально", "Быстро"])

        self.theme_label = QLabel("Тема оформления:")
        self.theme_combobox = QComboBox()
        self.theme_combobox.addItems(list_themes())
        self.theme_combobox.setCurrentText("dark_teal.xml")
        self.theme_combobox.currentIndexChanged.connect(self.change_theme)

        self.log_label = QLabel("Логи:")
        self.taken_log_label = QLabel("Занятые имена:")
        self.taken_log_text = QTextEdit()
        self.taken_log_text.setReadOnly(True)
        self.available_log_label = QLabel("Доступные имена:")
        self.available_log_text = QTextEdit()
        self.available_log_text.setReadOnly(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        self.stop_button = QPushButton("Остановить")
        self.stop_button.setEnabled(False)

        # --- Макеты ---
        main_layout = QVBoxLayout()
        mode_layout = QHBoxLayout()
        file_layout = QHBoxLayout()
        generator_settings_layout = QVBoxLayout()
        speed_layout = QHBoxLayout()
        theme_layout = QHBoxLayout()
        log_layout = QHBoxLayout()
        button_layout = QHBoxLayout()

        mode_layout.addWidget(self.mode_label)
        mode_layout.addWidget(self.file_button)
        mode_layout.addWidget(self.generate_button)

        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.file_path)
        file_layout.addWidget(self.browse_button)

        generator_settings_layout.addWidget(self.generator_settings_label)
        generator_settings_layout.addWidget(self.length_label)
        generator_settings_layout.addWidget(self.length_spinbox)
        generator_settings_layout.addWidget(self.use_digits_checkbox)
        generator_settings_layout.addWidget(self.use_underscore_checkbox)

        speed_layout.addWidget(self.speed_label)
        speed_layout.addWidget(self.speed_combobox)

        theme_layout.addWidget(self.theme_label)
        theme_layout.addWidget(self.theme_combobox)

        log_layout.addWidget(self.taken_log_text)
        log_layout.addWidget(self.available_log_text)

        button_layout.addWidget(self.stop_button)

        main_layout.addLayout(mode_layout)
        main_layout.addLayout(file_layout)
        main_layout.addLayout(generator_settings_layout)
        main_layout.addLayout(speed_layout)
        main_layout.addLayout(theme_layout)
        main_layout.addWidget(self.log_label)
        main_layout.addWidget(self.taken_log_label)
        main_layout.addWidget(self.taken_log_text)
        main_layout.addWidget(self.available_log_label)
        main_layout.addWidget(self.available_log_text)
        main_layout.addWidget(self.progress_bar)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

        # --- Соединения ---
        self.file_button.clicked.connect(self.choose_file)
        self.generate_button.clicked.connect(self.start_generation)
        self.browse_button.clicked.connect(self.browse_file)
        self.stop_button.clicked.connect(self.stop_checking)

    # --- Обработчики событий ---
    def choose_file(self):
        """Выбирает файл с именами пользователей."""
        try:
            filename, _ = QFileDialog.getOpenFileName(self, "Открыть файл", "", "Текстовые файлы (*.txt)")
            if filename:
                self.file_path.setText(filename)
                self.start_checking("file", filename)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при выборе файла: {e}")

    def start_generation(self):
        """Запускает или останавливает генерацию и проверку."""
        try:
            if not self.threads:  # Если нет запущенных потоков
                length = self.length_spinbox.value()
                use_digits = self.use_digits_checkbox.isChecked()
                use_underscore = self.use_underscore_checkbox.isChecked()
                speed = self.speed_combobox.currentText()
                num_threads = self.speed_mapping[speed]
                self.start_checking("generate", length=length, use_digits=use_digits,
                                    use_underscore=use_underscore, num_threads=num_threads)
                self.generate_button.setText("Остановить генерацию")  # Меняем текст кнопки
                self.file_button.setEnabled(False)  # Блокируем кнопку "Проверить из файла"
            else:  # Если потоки уже запущены
                self.stop_checking()
                self.generate_button.setText("Генерировать и проверять")  # Меняем текст кнопки обратно
                self.file_button.setEnabled(True)  # Разблокируем кнопку "Проверить из файла"
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при запуске/остановке генерации: {e}")

    def browse_file(self):
        """Открывает диалог выбора файла."""
        try:
            filename, _ = QFileDialog.getOpenFileName(self, "Открыть файл", "", "Текстовые файлы (*.txt)")
            if filename:
                self.file_path.setText(filename)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при выборе файла: {e}")

    def start_checking(self, mode, usernames_file=None, length=3, use_digits=True, 
                        use_underscore=True, num_threads=1):
        """Запускает проверку в нескольких потоках."""
        try:
            for _ in range(num_threads):
                thread = CheckerThread(mode, usernames_file, length, use_digits,
                                        use_underscore, delay_ms=0)
                thread.signal_update_taken_log.connect(self.update_taken_log)
                thread.signal_update_available_log.connect(self.update_available_log)
                thread.signal_update_progress.connect(self.update_progress)
                # Отключаем signal_finished от checking_finished
                # thread.signal_finished.connect(self.checking_finished)  
                thread.start()
                self.threads.append(thread)  # Добавляем поток в список
            self.stop_button.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при запуске проверки: {e}")

    def update_taken_log(self, message):
        """Обновляет лог занятых имен."""
        self.taken_log_text.append(message)

    def update_available_log(self, message):
        """Обновляет лог доступных имен."""
        self.available_log_text.append(message)

    def update_progress(self, value):
        """Обновляет прогресс бар."""
        self.progress_bar.setValue(value)

    def checking_finished(self):
        """Выводит сообщение о завершении проверки."""
        if self.threads:  # Проверка на пустоту списка
            self.threads.pop()  # Удаляем завершенный поток из списка
        if not self.threads:  # Если все потоки завершены
            QMessageBox.information(self, "Завершено", "Проверка завершена!")
            self.stop_button.setEnabled(False)
            self.file_button.setEnabled(True)  # Разблокируем кнопку "Проверить из файла"
            self.generate_button.setText("Генерировать и проверять")  # Меняем текст кнопки обратно

    def stop_checking(self):
        """Останавливает все запущенные потоки."""
        try:
            for thread in self.threads:
                thread.stop()
                thread.wait()
            self.threads = []  # Очищаем список потоков
            self.stop_button.setEnabled(False)
            self.checking_finished()  # Вызываем checking_finished после остановки потоков
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при остановке проверки: {e}")

    def change_theme(self):
        """Изменяет тему оформления."""
        try:
            theme = self.theme_combobox.currentText()
            apply_stylesheet(app, theme=theme)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при изменении темы: {e}")

# --- Запуск приложения ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme='dark_teal.xml')
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())