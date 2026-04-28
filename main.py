import network
import time
from machine import Pin, I2C
from umqtt.simple import MQTTClient
from neopixel import NeoPixel
import ahtx0
import bmp280
import ssd1306

# --- НАСТРОЙКИ СЕТИ И MQTT ---
SSID = "home"
PASS = "jiger1324"
MQTT_BROKER = "192.168.1.148" 
CLIENT_ID = "Sara_Neural_Key"
TOPIC = "sara/sensors"

# ПИНЫ И ПАРАМЕТРЫ
# I2C: 1MHz как ты и выжал (предел стабильности)
i2c = I2C(0, scl=Pin(9), sda=Pin(8), freq=1000000) 
NP_PIN = 48 # NeoPixel на борту S3
NP_NUM = 1

time.sleep(0.5)

# ГЛОБАЛЬНЫЕ ОБЪЕКТЫ
oled = None
sensor_aht = None
sensor_bmp = None
np = None

# --- ИНИЦИАЛИЗАЦИЯ ЖЕЛЕЗА ---
try:
    oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3c)
    print("OLED: OK")
except: print("OLED Fail")

try:
    sensor_aht = ahtx0.AHT20(i2c)
    print("AHT20: OK")
except: print("AHT Fail")

try:
    sensor_bmp = bmp280.BMP280(i2c, addr=0x77)
    print("BMP280: OK")
except: print("BMP Fail")

try:
    np = NeoPixel(Pin(NP_PIN), NP_NUM)
    print("NeoPixel: OK")
except: print("NP Fail")

# --- ФУНКЦИИ СИСТЕМЫ ---

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, PASS)
        for _ in range(20):
            if wlan.isconnected(): break
            time.sleep(0.5)
    print('WiFi Status:', wlan.isconnected())

def update_rgb(t, h, delta_p, mqtt_ok):
    if not np: return
    # Логика светодиода:
    if not mqtt_ok:
        np[0] = (15, 5, 0) # Оранжевый - нет связи
    elif t >= 28.0:
        np[0] = (20, 0, 0) # Красный - жарко
    elif t <= 18.0:
        np[0] = (0, 0, 20) # Синий - холодно
    elif h <= 30.0:
        np[0] = (15, 15, 0) # Желтый - сухо (глаза сохнут!)
    elif abs(delta_p) > 2.0:
        np[0] = (10, 0, 15) # Фиолетовый - скачок давления
    else:
        np[0] = (0, 0, 0) # Всё норм - не светим
    np.write()

def update_oled(t, h, p, mqtt_ok, frame):
    if not oled: return
    oled.fill(0)
    
    # ЛОГИКА АНИМЕ-ИНТЕРФЕЙСА (V3)
    if not mqtt_ok:
        faces = [" (T_T) ", " (;_;) "]
        mood = " Baka.. "
        action = " *weep*"
    elif t >= 28.0:
        faces = ["(x_x;) ", "(+_+)  "]
        mood = " Atsui! "
        action = " *melt*"
    elif t <= 18.0:
        faces = ["(>_< ) ", "( >_<) "]
        mood = " Samui~ "
        action = " *brrr*"
    else:
        faces = ["(=^w^=)", "(=-w-=)"] 
        mood = " Senpai"
        actions = [" *purr*", " *meow*"]
        action = actions[frame]

    # ЛЕВАЯ ПАНЕЛЬ (Анимация и статус)
    oled.text(faces[frame], 0, 10, 1)
    oled.text(mood, 0, 28, 1)
    oled.text(action, 0, 46, 1)

    # РАЗДЕЛИТЕЛЬ (На 58px, чтобы не наслаивалось)
    oled.vline(58, 0, 64, 1)
    
    # ПРАВАЯ ПАНЕЛЬ (Телеметрия)
    oled.fill_rect(60, 0, 68, 12, 1) # Инверсный хедер
    oled.text("S.A.R.A.", 62, 2, 0)
    
    oled.text("T:{:.1f}".format(t), 62, 16, 1)
    oled.text("H:{:.0f}%".format(h), 62, 28, 1)
    oled.text("P:{:.0f}".format(p), 62, 40, 1) # В гектопаскалях
    
    oled.hline(60, 52, 68, 1)
    if mqtt_ok:
        wifi_icons = ["WIFI:V", "WIFI:v"]
        oled.text(wifi_icons[frame], 62, 56, 1)
    else:
        oled.text("WIFI:X", 62, 56, 1)
        
    oled.show()

# --- ГЛАВНЫЙ ЦИКЛ ---
def main_loop():
    connect_wifi()
    mqtt_ok = False
    client = MQTTClient(CLIENT_ID, MQTT_BROKER)
    try:
        client.connect()
        mqtt_ok = True
    except: pass
        
    t, h, p_hpa = 0, 0, 0
    p_history = []
    last_sensor_update = 0
    frame = 0
    
    while True:
        try:
            current_ms = time.ticks_ms()
            
            # Обновление данных раз в 10 секунд
            if time.ticks_diff(current_ms, last_sensor_update) > 10000 or last_sensor_update == 0:
                if sensor_aht:
                    t = sensor_aht.temperature
                    h = sensor_aht.relative_humidity
                if sensor_bmp:
                    p_hpa = sensor_bmp.pressure / 100.0 # Перевод в hPa
                
                # Считаем дельту давления за 5 циклов (чуть меньше минуты)
                p_history.append(p_hpa)
                if len(p_history) > 5: p_history.pop(0)
                delta_p = p_hpa - p_history[0] if len(p_history) > 1 else 0
                
                if mqtt_ok:
                    msg = '{"t":%.1f,"h":%.1f,"p":%.1f,"dp":%.1f}' % (t, h, p_hpa, delta_p)
                    try: client.publish(TOPIC, msg)
                    except: mqtt_ok = False
                
                update_rgb(t, h, delta_p, mqtt_ok)
                last_sensor_update = current_ms

            # Обновление анимации раз в секунду
            frame = (frame + 1) % 2
            update_oled(t, h, p_hpa, mqtt_ok, frame)
            
        except Exception as e:
            print("Error:", e)
            
        time.sleep(1)

# СТАРТ
main_loop()