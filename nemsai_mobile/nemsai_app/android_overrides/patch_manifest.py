"""Run after `flutter create`: add the permissions the app needs and name the app.
(The default template only declares INTERNET for debug builds, so a release APK could not reach the server.)"""
import re
p = "android/app/src/main/AndroidManifest.xml"
s = open(p, encoding="utf-8").read()
perms = (
    '    <uses-permission android:name="android.permission.INTERNET"/>\n'
    '    <uses-permission android:name="android.permission.CAMERA"/>\n'
    '    <uses-feature android:name="android.hardware.camera" android:required="false"/>\n'
    '    <uses-feature android:name="android.hardware.camera.autofocus" android:required="false"/>\n'
)
if "android.permission.CAMERA" not in s:
    s = s.replace("<application", perms + "    <application", 1)
s = re.sub(r'android:label="[^"]*"', 'android:label="NEMSAI"', s, count=1)
open(p, "w", encoding="utf-8").write(s)
print("manifest patched")
