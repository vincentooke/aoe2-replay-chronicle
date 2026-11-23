; Inno Setup script — AoE2 Review helper, Windows installer.
; One double-click install, no Terminal, no pip, no user install step.
; Bundles: aoe2review-helper.exe (PyInstaller, helper/aoe2review.spec)
;          + ffmpeg.exe (bundled next to the exe; helper.py finds it).
; Registers: aoe2review:// protocol handler (see windows_protocol.reg
;            for the exact keys this writes).
; Signing: NOT included. This produces an UNSIGNED installer for
; testing only. Code signing is an open launch item (BUILD_LOG);
; do not present an unsigned installer as a release, and do not
; invent a certificate.
[Setup]
AppName=AoE2 Review Helper
AppVersion=0.1-dev
DefaultDirName={pf}\AoE2ReviewHelper
DefaultGroupName=AoE2 Review Helper
OutputBaseFilename=AoE2ReviewHelperSetup
Compression=lzma
SolidCompression=yes
; No admin rights are requested for protocol registration in HKCU
; in the production installer; this dev script uses the default
; (HKCR) keys documented in windows_protocol.reg.

[Files]
Source: "aoe2review-helper.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ffmpeg.exe"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
Root: HKCR; Subkey: "aoe2review"; ValueType: string; ValueName: ""; ValueData: "URL:AoE2ReviewHelper Protocol"; Flags: uninsdeletekey
Root: HKCR; Subkey: "aoe2review"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCR; Subkey: "aoe2review\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\aoe2review-helper.exe"" ""%1"""

[Run]
; No post-install launch, no login item, no background service.
; The helper only runs when the user clicks Launch on the website.
