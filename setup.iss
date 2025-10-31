; Skrip Inno Setup untuk LabelDefectDetection (Electron + Python)

; --- Definisi Variabel Global ---
#define MyAppName "LabelDefectDetection"
; MyAppVersion diambil dari GitHub Actions (/DMyAppVersion=...)
#ifndef MyAppVersion
  ; Versi default jika kompilasi manual
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppPublisher "JST Indonesia"
; Launcher utama sekarang adalah Electron EXE
#define MyAppExeName "Label Defect Detection.exe" 

[Setup]
; Informasi dasar aplikasi
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppVerName={#MyAppName}
UninstallDisplayName={#MyAppName}

; Lokasi instalasi (di dalam Program Files)
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}

; Ikon untuk installer (diambil dari variabel GitHub Actions)
; Pastikan path ini sesuai dengan /DSetupIconAbsPath di YML
#ifndef SetupIconAbsPath
  #define SetupIconAbsPath "assets\logo.ico"
#endif
SetupIconFile={#SetupIconAbsPath}
; Ikon untuk Uninstaller di Control Panel
UninstallDisplayIcon={app}\icon.ico
; Nama file output installer
OutputBaseFilename=Output\{#MyAppName}-Setup-v{#MyAppVersion}

; Pengaturan kompresi
Compression=lzma
SolidCompression=yes
WizardStyle=modern

; Meminta hak Admin
PrivilegesRequired=admin

[Languages]
Name: "indonesian"; MessagesFile: "compiler:Languages\Indonesian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Dirs]
; Direktori kustom untuk backend Python
Name: "{app}\py_backend"
Name: "{app}\py_backend\python"
Name: "{app}\py_backend\models"
Name: "{app}\py_backend\wheels"

[Files]
; 1. Menyalin aplikasi Electron (dari staging/app)
Source: "staging\app\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

; 2. Menyalin lingkungan Python (dari staging/py_backend)
Source: "staging\py_backend\python\*"; DestDir: "{app}\py_backend\python"; Flags: recursesubdirs createallsubdirs
Source: "staging\py_backend\models\*"; DestDir: "{app}\py_backend\models"; Flags: recursesubdirs createallsubdirs
Source: "staging\py_backend\wheels\*"; DestDir: "{app}\py_backend\wheels"; Flags: recursesubdirs createallsubdirs
Source: "staging\py_backend\detector.py"; DestDir: "{app}\py_backend"
Source: "staging\py_backend\requirements.txt"; DestDir: "{app}\py_backend"
Source: "staging\py_backend\install_libs.bat"; DestDir: "{app}\py_backend"
Source: "staging\py_backend\get-pip.py"; DestDir: "{app}\py_backend"

; 3. Menyalin file pendukung
Source: "staging\vc_redist.x64.exe"; DestDir: "{app}"; Flags: deleteafterinstall
Source: "staging\icon.ico"; DestDir: "{app}"

[Run]
; 1. Memasang Microsoft Visual C++ Redistributable
Filename: "{app}\vc_redist.x64.exe"; \
  Parameters: "/install /passive /norestart"; \
  WorkingDir: "{app}"; \
  StatusMsg: "Memasang komponen sistem Microsoft Visual C++..."; \
  Flags: runhidden skipifdoesntexist waituntilterminated

; 2. Memasang Pip ke Python Embed
Filename: "{app}\py_backend\python\python.exe"; \
  Parameters: """{app}\py_backend\get-pip.py"" --no-index --find-links=""{app}\py_backend\wheels"""; \
  WorkingDir: "{app}\py_backend"; \
  StatusMsg: "Memasang Pip..."; \
  Flags: runhidden

; 3. Menjalankan batch script untuk menginstal library dari folder 'wheels'
Filename: "{app}\py_backend\install_libs.bat"; \
  WorkingDir: "{app}\py_backend"; \
  StatusMsg: "Memasang library Python (YOLO, OpenCV, OCR)... Ini mungkin perlu beberapa saat."; \
  Flags: runhidden

; 4. Menjalankan aplikasi Electron setelah instalasi selesai
Filename: "{app}\{#MyAppExeName}"; \
  WorkingDir: "{app}"; \
  Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

[Icons]
; Membuat shortcut di Start Menu untuk Electron EXE
Name: "{group}\{#MyAppName}"; \
  Filename: "{app}\{#MyAppExeName}"; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\icon.ico"

; Membuat shortcut Uninstaller di Start Menu
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[UninstallDelete]
; Membersihkan seluruh folder aplikasi saat uninstall
Type: filesandordirs; Name: "{app}"