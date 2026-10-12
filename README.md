# sprinter-wwh-obd

Fahrzeugdaten eines Mercedes Sprinter VS30 (Euro VI) per **WWH-OBD / ISO 27145** lokal in Home Assistant – mit einem WiCAN als ELM327-Server, einem pyscript und MQTT-Discovery. Kein Cloud-Dienst, kein WAN-Verkehr.

> [!WARNING]
> **Sicherheit & Haftung / Safety & liability** – Privates Hobbyprojekt, bereitgestellt «wie besehen», Nutzung **auf eigene Gefahr**.
> Das Skript sendet Diagnose-Anfragen auf den **Fahrzeug-CAN-Bus** über die OBD-Buchse. Auch rein lesende Anfragen können Steuergeräte wachhalten (Starterbatterie leer), Fehlerspeichereinträge erzeugen oder bei Fehlern im Adapter den Bus stören.
> Nicht während der Fahrt testen oder ändern. Keine Fahrzeug- oder Sicherheitsfunktion von diesen Werten abhängig machen. Eingriffe in die Fahrzeugelektronik können Garantie und Betriebserlaubnis berühren.
> Details: [DISCLAIMER.md](DISCLAIMER.md) (DE/EN).

> **WWH-OBD** = World-Wide Harmonized On-Board Diagnostics (UNECE GTR Nr. 5), technisch ISO 27145. Nachfolger von OBD-II/EOBD: UDS-Service `22 F4xx` statt Mode `01 xx`.

## Warum

Der EU-Sprinter VS30 antwortet **nicht** auf klassisches OBD-II (`0100` auf 11 bit). Er spricht nur WWH-OBD auf **29-bit-CAN, 500 kbit/s**. Übliche OBD-Apps und die Standard-PIDs des WiCAN sehen deshalb nichts. Die `F4xx`-DIDs entsprechen aber 1:1 den SAE-J1979-PIDs mit gleicher Skalierung.

## Architektur

```
OBD-Buchse ── WiCAN (ELM327-Emulation, TCP 23) ── pyscript in HA ── MQTT-Discovery ── Gerät «Sprinter»
                                                      ▲
                                    input_boolean.sprinter_polling (Pause)
                                                      ▲
                                       Automation D+ (Motor läuft)
```

* **Wach:** schnelle Werte alle 5 s, langsame alle 60 s, Motorwerte nur bei Drehzahl > 0
* **Schlafend:** Weckprobe (F442 an 0x58) alle 120 s
* **Pausiert:** TCP-Verbindung getrennt, `sprinter/awake = OFF`; die Entitäten bleiben verfügbar und zeigen die letzten Werte (z.B. Tank/AdBlue beim Abstellen)
* **WiCAN nicht erreichbar:** `sprinter/status = offline`, Entitäten «nicht verfügbar»

Der WiCAN nimmt nur **eine** TCP-Verbindung an. Für Tests am PC das Polling pausieren.

**Empfohlene Steuerung:** Polling über D+ (Motor läuft). Das Motor-SG antwortet nur bei Kl. 15 und verstummt mit dem Startknopf sofort; Diagnose-Anfragen wecken es nicht. Die Weckprobe ist deshalb nur ein Rückfall. Der WiCAN selbst hängt an Dauerplus und sollte über seinen Sleep Mode schlafen, solange die Lichtmaschine nicht lädt.

## Hardware

* WiCAN-USB (non-Pro), Firmware 4.21 (WiCAN-OBD sollte gleich funktionieren)
* Anschluss an der OBD-Buchse:

| OBD-Pin | Funktion | WiCAN-Klemme |
| --- | --- | --- |
| 6 | CAN-H | CH |
| 14 | CAN-L | CL |
| 5 | Signal-GND | GND |
| 16 | +12 V Dauerplus | VIN |
| – | Terminierung | **TR frei lassen** (Bus im Fahrzeug abgeschlossen) |

Prüfwerte: Pin 16–5 = Batteriespannung; Pin 6 und 14 gegen GND je ≈ 2.5 V bei Zündung ein; Pin 6–14 ≈ 60 Ω bei Zündung aus.

## WiCAN-Einstellungen (Webinterface)

| Einstellung | Wert |
| --- | --- |
| IP | feste Adresse (DHCP-Reservierung) |
| CAN Bitrate / Mode | 500K / Normal |
| Port Type / Port / Protocol | TCP / 23 / elm327 |
| MQTT | Disable |
| Webhook | Disable |
| Automate: Standard PIDs | Disable |
| Sleep Mode | Enable, Schwelle zwischen Ruhespannung und Ladespannung (Lichtmaschine ≈ 14.7 V) |

AutoPID/Webhook und pyscript teilen sich sonst die ELM-Emulation und verstellen sich gegenseitig die Header.

## Installation in Home Assistant

1. **pyscript** über HACS installieren und in `configuration.yaml` aktivieren:
   ```yaml
   pyscript:
     allow_all_imports: true    # für asyncio
   ```
2. **MQTT**-Integration mit Broker (z.B. Mosquitto-Add-on) einrichten.
3. `pyscript/sprinter27145.py` nach `/config/pyscript/` kopieren und oben anpassen: `WICAN_HOST`, ggf. `FAST_S` / `SLOW_S` / `PROBE_S`.
4. Pause-Schalter anlegen: `examples/package_polling_switch.yaml` als Package oder als Helfer in der UI.
5. Optional Automation mit D+: `examples/automation_polling_d_plus.yaml`, D+-Entität anpassen.
6. HA neu starten bzw. **Entwicklerwerkzeuge → Aktionen → `pyscript.reload`**.

Danach erscheint unter **Einstellungen → Geräte & Dienste → MQTT** das Gerät **Sprinter**.

## Werte (DIDs)

A, B, … = Datenbytes nach `62 F4 xx`. «Motor» = nur bei laufendem Motor abgefragt. Verifiziert am Fahrzeug (Leerlauf und ≈ 1500 rpm).

| DID | SG | Wert | Formel | Motor |
| --- | --- | --- | --- | --- |
| F40C | 58 | Drehzahl | (256A+B)/4 rpm | |
| F40D | 58 | Geschwindigkeit | A km/h | |
| F404 | 58 | Motorlast | A×100/255 % | |
| F45E | 58 | Verbrauch | (256A+B)/20 L/h | |
| F449 | 58 | Fahrpedal | A×100/255 % | |
| F47A | 58 | DPF-Differenzdruck | (256B+C)/100 kPa, signed | ja |
| F485 | 5D | AdBlue-Verbrauch | (256B+C)×0.005 L/h | ja |
| F462 / F461 | 58 | Drehmoment Ist / Soll | A−125 % | ja |
| F466 | 58 | Luftmasse | (256B+C)/32 g/s | ja |
| F470 | 58 | Ladedruck (abs.) | (256D+E)×0.03125 kPa | ja |
| F46D | 58 | Raildruck | (256D+E)×0.1 bar | ja |
| F475 | 58 | Verdichter ein / aus | B−40 / C−40 °C | ja |
| F475 | 58 | Turbine ein / aus | (256D+E)/10−40 / (256F+G)/10−40 °C | ja |
| F478 | 58 | Abgastemperatur 3 | (256F+G)/10−40 °C | ja |
| F473 | 58 | Abgasdruck | (256B+C)×0.01 kPa | ja |
| F469 | 58 | AGR Soll / Ist / Abweichung | B×100/255, C×100/255, (D−128)×100/128 % | ja |
| F46F | 58 | Turbo-Eingangsdruck | B kPa | ja |
| F45D | 58 | Einspritzbeginn | (256A+B)/128−210 ° | ja |
| F41F | 58 | Laufzeit seit Start | 256A+B s | ja |
| F477 | 58 | Ladeluftkühler | B−40 °C | ja |
| F483 | 58 | NOx Sensor 1 / 2 | 256B+C / 256D+E ppm | ja |
| F405 | 58 | Kühlmittel | A−40 °C | |
| F45C | 58 | Öltemperatur | A−40 °C | |
| F446 | 58 | Aussentemperatur | A−40 °C | |
| F468 | 58 | Ansauglufttemperatur | B−40 °C | |
| F42F | 58 | Tank | A×100/255 % | |
| F485 | 5D | AdBlue-Füllstand | F×100/255 % | |
| F442 | 58 | Bordspannung | (256A+B)/1000 V | |
| F433 | 58 | Luftdruck | A kPa | |
| F401 | 58 | MIL / Anzahl Fehler | A bit 7 / A & 0x7F | |
| F463 | 58 | Referenzmoment | 256A+B Nm | |
| F44E | 58 | Zeit seit Fehler löschen | 256A+B min | |

**Hinweise**

* F478 Sensor 1/2 sind dieselben Sensoren wie F475 Turbine ein/aus und werden nur einmal verwendet; Sensor 4 liefert konstant 1200 °C (ungültig).
* F47F (Betriebs-/Leerlaufstunden) liefert nur Nullen.
* Kein Kilometerstand: F4A0/F4C0 werden nicht unterstützt.
* NOx-Sensoren liefern erst bei warmem Abgasstrang Werte.

## MQTT-Topics

| Topic | Inhalt |
| --- | --- |
| `sprinter/status` | `online` / `offline` (Verfügbarkeit aller Entitäten) |
| `sprinter/awake` | `ON` / `OFF` |
| `sprinter/<key>` | Werte, retained |
| `homeassistant/sensor/sprinter/<key>/config` | Discovery |

## Protokoll

* Funktional: `18DB33F1`, physikalisch: `18DA<SG>F1`, Antworten von `18DAF1<SG>`
* Steuergeräte: **0x58** Motor, **0x5D** SCR/AdBlue, 0x59 / 0x5A nur Basis-DIDs
* ELM-Initialisierung: `ATZ`, `ATE0`, `ATH1`, `ATSP7` (29 bit, 500k), `ATCP18`
* Multi-Frame (ISO-TP) erledigt die ELM-Emulation selbst; das pyscript setzt die Frames aus der `ATH1`-Ausgabe zusammen.

### Fehlercodes

`19 42 33 FF FF` (ReadDTCInformation, WWH-OBD, Gruppe 33 Emissionen), physikalisch an 0x58, 0x59 und 0x5D – nach dem Aufwachen sofort, danach alle `DTC_S` (300 s). Die SGs antworten zuerst mit `7F 19 78` (responsePending) → das Skript setzt dafür kurz `ATAT0` + `ATSTFF` und danach wieder `ATST32` + `ATAT1`. DTC-Format `04` = SAE J2012-DA (P-Codes). 0x5D unterstützt Gruppe 33 nicht (`7F 19 31`) und liefert eine leere Liste.

Antwort: `59 42` · Gruppe · Status-Maske · Severity-Maske · Format · je Eintrag 5 Byte (Severity, DTC High, DTC Mid, Failure-Type, Status). DTC High: Bit 7–6 Buchstabe (P/C/B/U), Bit 5–4 erste Ziffer.

**Sensor «Fehlercodes gespeichert»** (`sprinter/dtc`): Anzahl aller Codes; Attribute `codes` (z.B. `P13E7 (gespeichert)`), `details` (SG, Status-Bits, Severity, FTB) und `gelesen` (Zeitpunkt). Status-Bits: `aktiv` = testFailed (0x01), `ausstehend` = pending (0x04), `gespeichert` = confirmed (0x08), `MIL` (0x80). Der bestehende Sensor «Fehlercodes Anzahl» (F401) zählt nur MIL-relevante Codes.

Löschen (`14 FF FF 33`) wird mit `54` quittiert, wirkt am Motor-SG aber nicht – nicht implementiert.

## Stolpersteine

* **Windows-telnet** ist ungeeignet (WiCAN schliesst Zeilen nur mit CR). Stattdessen `examples/wican_test.ps1` verwenden (`-Dtc` für Fehlercodes).
* **Linux `nc`** sendet nur LF, der ELM wartet dann ewig → `socat …,crlf`.
* **Nur Emissionsdaten:** WWH-OBD sieht keine Fehler in Airbag, ESP, Komfort oder Aufbau.
* **Kein Nachlauf:** Mit dem Startknopf verstummt das Motor-SG sofort; Anfragen wecken es nicht.

## Referenzen

* [wican-fw Issue #298](https://github.com/meatpiHQ/wican-fw/issues/298) – EU-Sprinter und ISO 27145
* Normen: ISO 27145 (WWH-OBD), ISO 15765-4 (CAN-Diagnose), ISO 14229 (UDS), SAE J1979 (PID-Formeln), SAE J2012-DA (DTC)

## Lizenz

MIT, siehe [LICENSE](LICENSE). Nutzung auf eigene Gefahr – siehe [DISCLAIMER.md](DISCLAIMER.md).
