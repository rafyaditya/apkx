import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from apk_extractor.adb import ADBManager


@dataclass
class AppInfo:
    package_name: str
    app_name: str
    activity_name: Optional[str] = None


# Kamus pemetaan untuk aplikasi populer (Indonesia & Global)
POPULAR_APPS: Dict[str, str] = {
    # Media Sosial & Chat
    "com.whatsapp": "WhatsApp",
    "com.whatsapp.w4b": "WhatsApp Business",
    "com.facebook.katana": "Facebook",
    "com.facebook.orca": "Messenger",
    "com.facebook.lite": "Facebook Lite",
    "com.instagram.android": "Instagram",
    "com.twitter.android": "X (Twitter)",
    "org.telegram.messenger": "Telegram",
    "com.discord": "Discord",
    "com.zhiliaoapp.musically": "TikTok",
    "com.ss.android.ugc.trill": "TikTok",
    "com.snapchat.android": "Snapchat",
    "com.reddit.frontpage": "Reddit",
    "com.linkedin.android": "LinkedIn",
    "com.pinterest": "Pinterest",
    "com.threads.android": "Threads",

    # Musik, Video & Hiburan
    "com.spotify.music": "Spotify",
    "com.google.android.youtube": "YouTube",
    "com.google.android.apps.youtube.music": "YouTube Music",
    "com.netflix.mediaclient": "Netflix",
    "in.startv.hotstar": "Disney+ Hotstar",
    "com.bstar.intl": "Bilibili (Bstar)",
    "com.valvesoftware.android.steam.community": "Steam",

    # AI & Produktivitas
    "com.openai.chatgpt": "ChatGPT",
    "com.anthropic.claud": "Claude",
    "com.google.android.apps.bard": "Gemini",
    "com.notion.id": "Notion",
    "com.microsoft.office.officehubrow": "Microsoft 365",

    # E-Commerce & Finansial (Indonesia)
    "com.shopee.id": "Shopee",
    "com.tokopedia.tkpd": "Tokopedia",
    "com.bukalapak.android": "Bukalapak",
    "com.lazada.android": "Lazada",
    "com.blibli.mobile": "Blibli",
    "id.dana": "DANA",
    "com.telkomsel.telkomselcm": "MyTelkomsel",
    "ovo.id": "OVO",
    "linkaja.linkaja": "LinkAja",
    "com.gojek.app": "Gojek",
    "com.grabtaxi.passenger": "Grab",
    "com.bca": "BCA Mobile",
    "id.co.bri.brimo": "BRImo",
    "id.bmri.livin": "Livin' by Mandiri",
    "id.co.bni.newmobile": "BNI Mobile",
    "com.seabank.mobile": "SeaBank",
    "com.jadens.jago": "Bank Jago",
    "com.btpn.sinaya": "Jenius",

    # Developer & System Tools
    "com.termux": "Termux",
    "moe.shizuku.privileged.api": "Shizuku",
    "flar2.devcheck": "DevCheck",
    "com.cpuid.cpu_z": "CPU-Z",
    "com.finalwire.aida64": "AIDA64",
    "com.catchingnow.icebox": "Ice Box",
    "com.aistra.hail": "Hail",
    "com.koushikdutta.vysor": "Vysor",
    "com.toralabs.apkextractor": "APK Extractor",
    "cloud.blynk": "Blynk IoT",
    "com.gombosdev.ampere": "Ampere",

    # Browser
    "com.brave.browser": "Brave Browser",
    "com.android.chrome": "Google Chrome",
    "org.mozilla.firefox": "Firefox",
    "com.opera.browser": "Opera",
    "com.microsoft.emmx": "Microsoft Edge",
}


def _split_camel_case(s: str) -> str:
    """Memisahkan kata CamelCase menjadi kata-kata terpisah."""
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", s)


def format_fallback_app_name(package_name: str, activity_name: Optional[str] = None) -> str:
    """
    Menghasilkan nama aplikasi yang mudah dibaca berdasarkan launcher activity
    atau segmen nama package.
    """
    # 1. Cek kamus aplikasi populer
    if package_name in POPULAR_APPS:
        return POPULAR_APPS[package_name]

    # 2. Coba ekstrak petunjuk nama dari Activity Launcher
    if activity_name:
        act_parts = activity_name.split(".")
        for part in reversed(act_parts):
            clean = re.sub(r"(Activity|MainActivity|Splash|Revamp|App|_|\$)", "", part, flags=re.IGNORECASE).strip()
            if clean and len(clean) >= 3 and clean.lower() not in {"login", "home", "main", "view", "ui", "act"}:
                words = _split_camel_case(clean)
                return words.title()

    # 3. Ekstrak dari segmen nama package (misal: com.blodhgard.easybudget -> Easybudget)
    pkg_parts = package_name.split(".")
    # Cari bagian nama yang paling spesifik (biasanya segmen terakhir atau kedua dari belakang)
    candidate = pkg_parts[-1]
    if candidate.lower() in {"android", "app", "mobile", "frontend", "twa"} and len(pkg_parts) >= 2:
        candidate = pkg_parts[-2]

    # Bersihkan angka atau karakter aneh
    clean_candidate = re.sub(r"[-_]", " ", candidate)
    words = _split_camel_case(clean_candidate)
    
    # Perbaiki spasi ganda dan buat huruf kapital di awal kata
    formatted = " ".join(w.capitalize() for w in words.split())
    return formatted if formatted else package_name


def fetch_launcher_activities(adb: ADBManager, device_id: Optional[str] = None) -> Dict[str, str]:
    """
    Mengambil mapping package_name -> launcher_activity dari perangkat Android.
    """
    activities_map: Dict[str, str] = {}
    cmd = adb._build_base_cmd(device_id)
    cmd.extend([
        "shell",
        "cmd",
        "package",
        "query-activities",
        "--brief",
        "-a",
        "android.intent.action.MAIN",
        "-c",
        "android.intent.category.LAUNCHER",
    ])

    try:
        res = adb.is_installed()  # pastikan adb aman
        import subprocess
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if "/" in line and not line.startswith("priority="):
                    parts = line.split("/", 1)
                    pkg = parts[0].strip()
                    act = parts[1].strip()
                    if pkg and act:
                        activities_map[pkg] = act
    except Exception:
        pass

    return activities_map


def resolve_apps(
    adb: ADBManager,
    packages: List[str],
    device_id: Optional[str] = None,
) -> List[AppInfo]:
    """
    Meresolusi daftar nama package menjadi objek AppInfo lengkap dengan nama aplikasi ramah.
    """
    launcher_map = fetch_launcher_activities(adb, device_id=device_id)
    app_list: List[AppInfo] = []

    for pkg in packages:
        act = launcher_map.get(pkg)
        friendly_name = format_fallback_app_name(pkg, activity_name=act)
        app_list.append(AppInfo(package_name=pkg, app_name=friendly_name, activity_name=act))

    # Urutkan berdasarkan nama aplikasi agar rapi secara alfabetis
    return sorted(app_list, key=lambda a: a.app_name.lower())
