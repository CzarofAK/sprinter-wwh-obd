# wican_test.ps1 – Befehle an die ELM327-Emulation des WiCAN senden (TCP 23)
#
# Windows-telnet ist ungeeignet: Der WiCAN schliesst Zeilen nur mit CR ab,
# telnet überschreibt dann die Antworten. Dieses Skript wartet pro Befehl auf
# den Prompt '>' und gibt jede Antwort auf einer Zeile aus.
#
# Vorher in HA das Polling pausieren (input_boolean.sprinter_polling aus,
# D+-Automation deaktivieren): Der WiCAN nimmt nur EINE TCP-Verbindung an.
#
# Beispiele:
#   .\wican_test.ps1                                   # Grundtest (unterstützte DIDs)
#   .\wican_test.ps1 -Commands '22F40C','22F442'       # einzelne DIDs (Header bleibt funktional)
#   .\wican_test.ps1 -Dtc                              # Fehlercodes lesen (Gruppe 33)
#   .\wican_test.ps1 -WicanHost 10.10.80.203 -Timeout 8000
#
# Falls die Ausführung blockiert ist: PowerShell als Benutzer öffnen und einmalig
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

param(
    [string]   $WicanHost = '10.10.80.203',   # <- eigene WiCAN-IP
    [int]      $Port      = 23,
    [int]      $Timeout   = 5000,             # ms pro Antwort
    [string[]] $Commands  = @('22F400','22F420','22F440','22F460','22F480'),
    [switch]   $Dtc
)

$init = @('ATZ','ATE0','ATH1','ATSP7','ATCP18','ATSHDB33F1')   # 29 bit, 500k, funktional 18DB33F1

if ($Dtc) {
    # Steuergeräte antworten zuerst mit 7F 19 78 (responsePending):
    # adaptives Timing aus, Timeout auf Maximum, sonst bricht die ELM-Emulation ab
    $init     += @('ATAT0','ATSTFF')
    $Commands  = @('194233FFFF')                  # ReadDTCInformation, WWH-OBD, Gruppe 33
    if ($Timeout -lt 10000) { $Timeout = 10000 }
}

$c = New-Object Net.Sockets.TcpClient($WicanHost, $Port)
$s = $c.GetStream(); $s.ReadTimeout = $Timeout
$w = New-Object IO.StreamWriter($s); $w.AutoFlush = $true

function Send($cmd) {
    $w.Write("$cmd`r")
    $buf = New-Object byte[] 4096; $out = ''
    do {
        try { $n = $s.Read($buf, 0, $buf.Length) } catch { $out += '[TIMEOUT]'; break }
        if ($n -eq 0) { break }
        $out += [Text.Encoding]::ASCII.GetString($buf, 0, $n)
    } until ($out.Contains('>'))
    "{0,-12} => {1}" -f $cmd, (($out -replace "[`r`n]+", " | ").Trim(' |>'))
}

try {
    ($init + $Commands) | ForEach-Object { Send $_ }
} finally {
    $c.Close()
}
