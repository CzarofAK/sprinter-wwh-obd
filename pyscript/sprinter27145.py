"""
sprinter27145 – pyscript
WiCAN (ELM327-Emulation, TCP) -> ISO 27145 / WWH-OBD -> MQTT-Discovery -> HA
Sprinter VS30: Motor-SG 0x58, SCR/AdBlue-SG 0x5D, 29 bit / 500k
"""
import json
import time

WICAN_HOST   = "10.10.80.203"     # feste IP im Womo-WLAN (DHCP-Reservierung)
WICAN_PORT   = 23
BASE         = "sprinter"
FAST_S       = 5                  # Zyklus wenn wach
SLOW_S       = 60                 # langsame Werte
PROBE_S      = 120                # Weckprobe wenn schlafend
POLL_SWITCH  = "input_boolean.sprinter_polling"
EXPERIMENTAL = True               # DIDs am 08.10.2026 verifiziert (KB FR-A-11)
PROBE        = (0x58, 0x42)       # Bordspannung am Motor-SG

# key, ECU, DID, Name, Einheit, device_class, Gruppe, experimentell
SENSORS = [
    # fast: jeder Zyklus
    ("rpm",         0x58, 0x0C, "Drehzahl",           "rpm",  None,          "fast",   False),
    ("speed",       0x58, 0x0D, "Geschwindigkeit",    "km/h", "speed",       "fast",   False),
    ("load",        0x58, 0x04, "Motorlast",          "%",    None,          "fast",   False),
    ("fuel_rate",   0x58, 0x5E, "Verbrauch",          "L/h",  None,          "fast",   False),
    ("pedal",       0x58, 0x49, "Fahrpedal",          "%",    None,          "fast",   True),
    # engine: nur bei rpm > 0
    ("dpf_dp",      0x58, 0x7A, "DPF Differenzdruck", "kPa",  "pressure",    "engine", False),
    ("adblue_rate", 0x5D, 0x85, "AdBlue Verbrauch",   "L/h",  None,          "engine", False),
    ("torque_act",  0x58, 0x62, "Drehmoment Ist",     "%",    None,          "engine", True),
    ("torque_dem",  0x58, 0x61, "Drehmoment Soll",    "%",    None,          "engine", True),
    ("maf",         0x58, 0x66, "Luftmasse",          "g/s",  None,          "engine", True),
    ("boost",       0x58, 0x70, "Ladedruck",          "kPa",  "pressure",    "engine", True),
    ("rail",        0x58, 0x6D, "Raildruck",          "bar",  "pressure",    "engine", True),
    # F478: S1/S2 = F475 Turbine ein/aus (gleiche Sensoren) -> nur S3; S4 ungueltig (1200 °C)
    ("egt3",        0x58, 0x78, "Abgastemp 3",        "°C",   "temperature", "engine", True),
    ("comp_in",     0x58, 0x75, "Verdichter ein",     "°C",   "temperature", "engine", True),
    ("comp_out",    0x58, 0x75, "Verdichter aus",     "°C",   "temperature", "engine", True),
    ("turb_in",     0x58, 0x75, "Turbine ein",        "°C",   "temperature", "engine", True),
    ("turb_out",    0x58, 0x75, "Turbine aus",        "°C",   "temperature", "engine", True),
    ("exh_press",   0x58, 0x73, "Abgasdruck",         "kPa",  "pressure",    "engine", True),
    ("egr_cmd",     0x58, 0x69, "AGR Soll",           "%",    None,          "engine", True),
    ("egr_act",     0x58, 0x69, "AGR Ist",            "%",    None,          "engine", True),
    ("egr_err",     0x58, 0x69, "AGR Abweichung",     "%",    None,          "engine", True),
    ("turbo_in_p",  0x58, 0x6F, "Turbo Eingangsdruck","kPa",  "pressure",    "engine", True),
    ("inj_timing",  0x58, 0x5D, "Einspritzbeginn",    "°",    None,          "engine", True),
    ("run_time",    0x58, 0x1F, "Laufzeit seit Start","s",    "duration",    "engine", True),
    ("cac_temp",    0x58, 0x77, "Ladeluftkühler",     "°C",   "temperature", "engine", True),
    ("nox1",        0x58, 0x83, "NOx Sensor 1",       "ppm",  None,          "engine", True),
    ("nox2",        0x58, 0x83, "NOx Sensor 2",       "ppm",  None,          "engine", True),
    # slow: alle SLOW_S Sekunden
    ("coolant",     0x58, 0x05, "Kühlmittel",         "°C",   "temperature", "slow",   False),
    ("oil",         0x58, 0x5C, "Öltemperatur",       "°C",   "temperature", "slow",   False),
    ("ambient",     0x58, 0x46, "Aussentemperatur",   "°C",   "temperature", "slow",   False),
    ("tank",        0x58, 0x2F, "Tank",               "%",    None,          "slow",   False),
    ("voltage",     0x58, 0x42, "Spannung ECU",       "V",    "voltage",     "slow",   False),
    ("baro",        0x58, 0x33, "Luftdruck",          "kPa",  "pressure",    "slow",   False),
    ("mil",         0x58, 0x01, "MIL",                None,   None,          "slow",   False),
    ("dtc_count",   0x58, 0x01, "Fehlercodes Anzahl", None,   None,          "slow",   False),
    ("adblue",      0x5D, 0x85, "AdBlue",             "%",    None,          "slow",   False),
    ("iat",         0x58, 0x68, "Ansauglufttemp",     "°C",   "temperature", "slow",   True),
    ("torque_ref",  0x58, 0x63, "Referenzmoment",     "Nm",   None,          "slow",   True),
    ("since_clear", 0x58, 0x4E, "Zeit seit Löschen",  "min",  None,          "slow",   True),
]


# ---------------------------------------------------------------- nativ (asyncio)

@pyscript_compile
async def elm_open(host, port):
    import asyncio
    return await asyncio.wait_for(asyncio.open_connection(host, port), 10)


@pyscript_compile
async def elm_cmd(reader, writer, cmd, timeout=5.0):
    import asyncio
    writer.write((cmd + "\r").encode())
    await writer.drain()
    buf = await asyncio.wait_for(reader.readuntil(b">"), timeout)
    return buf.decode(errors="ignore").replace(">", "")


@pyscript_compile
def elm_close(writer):
    try:
        writer.close()
    except Exception:
        pass


@pyscript_compile
def parse(resp, ecu, did):
    """ISO-TP-Frames (ATH1-Ausgabe) einer ECU zusammensetzen -> Daten nach 62 F4 xx"""
    data, need = [], None
    for line in resp.replace("\n", "\r").split("\r"):
        t = line.split()
        if len(t) < 3 or len(t[0]) != 8 or not t[0].upper().endswith("%02X" % ecu):
            continue
        try:
            b = [int(x, 16) for x in t[1:]]
        except ValueError:
            continue
        typ = b[0] >> 4
        if typ == 0:
            need, data = b[0], b[1:1 + b[0]]
        elif typ == 1:
            need, data = ((b[0] & 0x0F) << 8) | b[1], b[2:8]
        elif typ == 2:
            data += b[1:8]
    if need is None:
        return None
    p = data[:need]
    if len(p) < 4 or p[0] != 0x62 or p[1] != 0xF4 or p[2] != did:
        return None
    return p[3:]


@pyscript_compile
def decode(key, d):
    def u16(x): return x[0] * 256 + x[1]
    def s16(x): return int.from_bytes(bytes(x[0:2]), "big", signed=True)
    def u32(x): return int.from_bytes(bytes(x[0:4]), "big")
    f = {
        "rpm":         lambda: round(u16(d) / 4),
        "speed":       lambda: d[0],
        "load":        lambda: round(d[0] * 100 / 255, 1),
        "fuel_rate":   lambda: round(u16(d) / 20, 2),
        "pedal":       lambda: round(d[0] * 100 / 255, 1),
        "dpf_dp":      lambda: round(s16(d[1:3]) / 100, 2),
        "adblue_rate": lambda: round(u16(d[1:3]) * 0.005, 3),
        "torque_act":  lambda: d[0] - 125,
        "torque_dem":  lambda: d[0] - 125,
        "maf":         lambda: round(u16(d[1:3]) / 32, 1),
        "boost":       lambda: round(u16(d[3:5]) * 0.03125, 1),
        "rail":        lambda: round(u16(d[3:5]) * 0.1),
        "egt3":        lambda: round(u16(d[5:7]) / 10 - 40),
        "comp_in":     lambda: d[1] - 40,
        "comp_out":    lambda: d[2] - 40,
        "turb_in":     lambda: round(u16(d[3:5]) / 10 - 40),
        "turb_out":    lambda: round(u16(d[5:7]) / 10 - 40),
        "exh_press":   lambda: round(u16(d[1:3]) * 0.01, 1),
        "egr_cmd":     lambda: round(d[1] * 100 / 255, 1),
        "egr_act":     lambda: round(d[2] * 100 / 255, 1),
        "egr_err":     lambda: round((d[3] - 128) * 100 / 128, 1),
        "turbo_in_p":  lambda: d[1],
        "inj_timing":  lambda: round(u16(d) / 128 - 210, 1),
        "run_time":    lambda: u16(d),
        "cac_temp":    lambda: d[1] - 40,
        "nox1":        lambda: u16(d[1:3]),
        "nox2":        lambda: u16(d[3:5]),
        "coolant":     lambda: d[0] - 40,
        "oil":         lambda: d[0] - 40,
        "ambient":     lambda: d[0] - 40,
        "tank":        lambda: round(d[0] * 100 / 255, 1),
        "voltage":     lambda: round(u16(d) / 1000, 2),
        "baro":        lambda: d[0],
        "mil":         lambda: "on" if d[0] & 0x80 else "off",
        "dtc_count":   lambda: d[0] & 0x7F,
        "adblue":      lambda: round(d[5] * 100 / 255, 1),
        "iat":         lambda: d[1] - 40,
        "torque_ref":  lambda: u16(d),
        "since_clear": lambda: u16(d),
    }.get(key)
    if f is None:
        return None
    try:
        return f()
    except (IndexError, ValueError):
        return None


# ---------------------------------------------------------------- pyscript

def read_did(conn, ecu, did):
    h = "DA%02XF1" % ecu                     # physikalisch: 18 DA <ecu> F1
    if conn["hdr"] != h:
        elm_cmd(conn["r"], conn["w"], "ATSH" + h)
        conn["hdr"] = h
    return parse(elm_cmd(conn["r"], conn["w"], "22F4%02X" % did), ecu, did)


def polling_enabled():
    try:
        return state.get(POLL_SWITCH) != "off"
    except NameError:
        return True


def discovery():
    dev = {"identifiers": ["sprinter_vs30"], "name": "Sprinter",
           "manufacturer": "Mercedes-Benz", "model": "VS30 via WiCAN (ISO 27145)"}
    for s in SENSORS:
        key, name, unit, dc, exp = s[0], s[3], s[4], s[5], s[7]
        topic = "homeassistant/sensor/sprinter/%s/config" % key
        if exp and not EXPERIMENTAL:
            mqtt.publish(topic=topic, payload="", retain=True)   # Entität entfernen
            continue
        cfg = {"name": name, "unique_id": "sprinter_" + key,
               "state_topic": BASE + "/" + key,
               "availability_topic": BASE + "/status", "device": dev}
        if unit:
            cfg["unit_of_measurement"] = unit
            cfg["state_class"] = "measurement"
        if dc:
            cfg["device_class"] = dc
        mqtt.publish(topic=topic, payload=json.dumps(cfg), retain=True)
    mqtt.publish(topic="homeassistant/binary_sensor/sprinter/awake/config", retain=True,
                 payload=json.dumps({"name": "Fahrzeug wach", "unique_id": "sprinter_awake",
                                     "state_topic": BASE + "/awake",
                                     "availability_topic": BASE + "/status", "device": dev}))


@time_trigger("startup")
def sprinter_poll():
    task.unique("sprinter_poll")
    discovery()

    reqs = {}
    for s in SENSORS:
        if EXPERIMENTAL or not s[7]:
            reqs.setdefault((s[1], s[2]), []).append(s)

    conn = {"r": None, "w": None, "hdr": None}
    awake = None
    engine_on = False
    last_slow = 0

    try:
        while True:
            if not polling_enabled():
                if conn["w"] is not None:
                    elm_close(conn["w"])
                    conn["w"] = None
                    mqtt.publish(topic=BASE + "/status", payload="offline", retain=True)
                    log.info("sprinter27145: pausiert")
                task.sleep(10)
                continue

            try:
                if conn["w"] is None:
                    r, w = elm_open(WICAN_HOST, WICAN_PORT)
                    conn["r"] = r
                    conn["w"] = w
                    conn["hdr"] = None
                    for c in ["ATZ", "ATE0", "ATH1", "ATSP7", "ATCP18"]:
                        elm_cmd(r, w, c)
                    mqtt.publish(topic=BASE + "/status", payload="online", retain=True)
                    log.info("sprinter27145: WiCAN verbunden")

                now = time.time()
                if awake is False:
                    keys = [PROBE]
                    groups = []
                else:
                    groups = ["fast", "engine"]
                    if now - last_slow >= SLOW_S:
                        groups.append("slow")
                    keys = []
                    for k in reqs:
                        for s in reqs[k]:
                            if s[6] in groups:
                                keys.append(k)
                                break

                got = 0
                for k in keys:
                    act = []
                    for s in reqs.get(k, []):
                        if s[6] in groups and (s[6] != "engine" or engine_on):
                            act.append(s)
                    if awake is not False and len(act) == 0:
                        continue
                    d = read_did(conn, k[0], k[1])
                    if d is None:
                        continue
                    got += 1
                    for s in act:
                        val = decode(s[0], d)
                        if val is None:
                            log.warning("sprinter27145: %s nicht dekodierbar" % s[0])
                            continue
                        if s[0] == "rpm":
                            engine_on = val > 0
                        mqtt.publish(topic=BASE + "/" + s[0], payload=str(val), retain=True)

                new_awake = got > 0
                if new_awake != awake:
                    log.info("sprinter27145: Fahrzeug %s" % ("wach" if new_awake else "schlaeft"))
                    mqtt.publish(topic=BASE + "/awake", payload="ON" if new_awake else "OFF", retain=True)
                    if new_awake:
                        last_slow = 0
                    else:
                        engine_on = False
                awake = new_awake
                if awake and "slow" in groups:
                    last_slow = now
                task.sleep(FAST_S if awake else PROBE_S)

            except Exception as e:
                log.warning("sprinter27145: WiCAN-Fehler: %s" % e)
                if conn["w"] is not None:
                    elm_close(conn["w"])
                conn["w"] = None
                awake = None
                mqtt.publish(topic=BASE + "/status", payload="offline", retain=True)
                task.sleep(30)
    finally:
        if conn["w"] is not None:
            elm_close(conn["w"])


# TODO (Todo 7): Fehlercodes via 19 42 33 FF FF an 0x58 / 0x5D –
# Decoder folgt nach dem Test am Fahrzeug (DTC-Format J2012 oder J1939)