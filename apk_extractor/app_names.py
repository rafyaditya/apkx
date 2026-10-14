import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from apk_extractor.adb import ADBManager


@dataclass
class AppInfo:
    package_name: str
    app_name: str
    activity_name: Optional[str] = None


APP_CACHE_FILE = Path.home() / ".apkx" / "app_cache.json"


def load_app_cache() -> Dict[str, str]:
    """Memuat cache pemetaan package_name -> app_name dari disk."""
    if APP_CACHE_FILE.is_file():
        try:
            with open(APP_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_to_app_cache(package_name: str, app_name: str) -> None:
    """Menyimpan atau memperbarui nama aplikasi ke cache disk ~/.apkx/app_cache.json."""
    try:
        APP_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cache = load_app_cache()
        cache[package_name] = app_name
        with open(APP_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# Kamus pemetaan untuk aplikasi & game populer (termasuk kasus package codename)
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

    # Game Populer & Kasus Codename
    "com.pixio.google.mtd": "Summoner's Greed",
    "com.fluffyfairygames.idleminertycoon": "Idle Miner Tycoon",
    "com.supercell.magic": "Clash of Clans",
    "com.supercell.laser": "Brawl Stars",
    "com.supercell.scroll": "Clash Royale",
    "com.supercell.clashofclans": "Clash of Clans",
    "com.dts.freefireth": "Free Fire",
    "com.dts.freefiremax": "Free Fire MAX",
    "com.kiloo.subwaysurf": "Subway Surfers",
    "com.miHoYo.GenshinImpact": "Genshin Impact",
    "com.activision.callofduty.shooter": "Call of Duty: Mobile",
    "com.riotgames.league.wildrift": "League of Legends: Wild Rift",
    "com.mobile.legends": "Mobile Legends: Bang Bang",
    "com.roblox.client": "Roblox",
    "com.mojang.minecraftpe": "Minecraft",
    "com.ea.gp.fifamobile": "EA Sports FC Mobile",
    "com.epicgames.portal": "Epic Games",
    "com.innersloth.spacemafia": "Among Us",
    "com.king.candycrushsaga": "Candy Crush Saga",

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

# Prefix namespace engine dan wrapper pihak ketiga yang bukan identitas produk
KNOWN_ENGINE_PREFIXES = (
    "com.unity3d.",
    "io.flutter.",
    "com.facebook.react.",
    "org.godotengine.",
    "com.epicgames.",
    "org.apache.cordova.",
    "com.getcapacitor.",
    "mono.android.",
    "crc64.",
    "com.ansca.",
    "org.cocos2dx.",
)

# Kata-kata peran komponen/layar teknis yang tidak merepresentasikan nama aplikasi
GENERIC_SCREEN_WORDS = {
    "activity",
    "mainactivity",
    "splash",
    "splashscreen",
    "screen",
    "revamp",
    "app",
    "view",
    "ui",
    "act",
    "login",
    "home",
    "main",
    "start",
    "loading",
    "intro",
    "welcome",
    "gate",
    "auth",
    "player",
    "unityplayer",
    "flutter",
    "react",
    "wrapper",
    "container",
    "host",
    "proxy",
    "delegate",
    "bridge",
    "dummy",
    "root",
    "game",
    "base",
}

# Kosakata kata majemuk umum aplikasi & game untuk pemisahan cerdas
COMMON_APP_WORDS = {
    "idle", "miner", "tycoon", "easy", "budget", "pdf", "editor", "reader", "viewer",
    "super", "vpn", "free", "screen", "recorder", "photo", "video", "music", "player",
    "scan", "scanner", "game", "pro", "lite", "plus", "fast", "cleaner", "booster",
    "battery", "saver", "notes", "calendar", "tracker", "wallet", "pay", "chat",
    "social", "smart", "tool", "tools", "file", "manager", "camera", "live", "news",
    "weather", "shop", "store", "mall", "auto", "car", "drive", "taxi", "food",
    "fitness", "workout", "health", "sleep", "meditation", "learn", "study",
    "dictionary", "translator", "puzzle", "runner", "racing", "war", "battle",
    "hero", "quest", "craft", "crafting", "tower", "defense", "merge", "match",
    "farm", "city", "build", "block", "card", "board", "rpg", "mmo", "fps",
    "arcade", "simulator", "space", "galaxy", "star", "dark", "light", "cloud",
    "net", "web", "hub", "box", "lab", "labs", "studio", "studios", "app", "apps",
    "tech", "soft", "dev", "code", "rush", "saga", "clash", "strike", "force",
    "combat", "world", "land", "island", "zone", "pocket", "mini", "micro",
    "macro", "mega", "ultra", "hyper", "master", "expert", "ninja", "zombie",
    "monster", "dragon", "pet", "cat", "dog", "bird", "fish",
}


def _split_camel_case(s: str) -> str:
    """Memisahkan kata CamelCase menjadi kata-kata terpisah."""
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", s)


def _split_compound_words(s: str) -> str:
    """
    Memecah kata gabungan huruf kecil (misal: idleminertycoon -> Idle Miner Tycoon)
    berdasarkan kosakata kata aplikasi/game yang umum.
    """
    s_lower = s.lower()

    def helper(sub: str) -> Optional[List[str]]:
        if not sub:
            return []
        for length in range(len(sub), 2, -1):
            chunk = sub[:length]
            if chunk in COMMON_APP_WORDS:
                rest = helper(sub[length:])
                if rest is not None:
                    return [chunk] + rest
        return None

    chunks = helper(s_lower)
    if chunks:
        formatted_chunks = [
            chunk.upper() if chunk == "vpn" else chunk.capitalize()
            for chunk in chunks
        ]
        return " ".join(formatted_chunks)

    return s


def is_framework_or_wrapper_activity(package_name: str, activity_name: str) -> bool:
    """
    Mengecek apakah sebuah activity adalah wrapper generic dari engine/framework
    atau komponen layar generik yang bukan identitas asli aplikasi.
    """
    if not activity_name:
        return True

    act_lower = activity_name.lower()

    # 1. Cek prefix engine pihak ketiga yang dikenal
    if any(act_lower.startswith(prefix) for prefix in KNOWN_ENGINE_PREFIXES):
        return True

    # 2. Cek apakah activity berada di luar domain root aplikasi
    # Misalnya: package com.fluffyfairygames.* tapi activity com.unity3d.*
    pkg_parts = package_name.split(".")
    act_parts = activity_name.split(".")
    if len(pkg_parts) >= 2 and len(act_parts) >= 2:
        # Jika bukan relative activity (seperti .MainActivity) dan root domain berbeda
        if not activity_name.startswith(".") and act_parts[0] != pkg_parts[0]:
            return True

    # 3. Cek apakah bagian nama class hanya berupa kata komponen layar generik
    class_simple_name = act_parts[-1]
    clean = re.sub(r"(Activity|MainActivity|Splash|Revamp|App|_|\$)", "", class_simple_name, flags=re.IGNORECASE).strip()
    if not clean or clean.lower() in GENERIC_SCREEN_WORDS or len(clean) < 3:
        return True

    return False


def find_aapt_binary() -> Optional[str]:
    """Mencari executable aapt2 atau aapt di sistem (PATH atau Android SDK)."""
    for bin_name in ["aapt2", "aapt"]:
        found = shutil.which(bin_name)
        if found:
            return found
        if sys.platform == "win32":
            found = shutil.which(f"{bin_name}.exe")
            if found:
                return found

    candidates: List[Path] = []
    for env_var in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
        val = os.environ.get(env_var)
        if val:
            candidates.append(Path(val))

    home = Path.home()
    if sys.platform == "win32":
        candidates.append(home / "AppData" / "Local" / "Android" / "Sdk")
    elif sys.platform == "darwin":
        candidates.append(home / "Library" / "Android" / "sdk")
    else:
        candidates.append(home / "Android" / "Sdk")

    candidates.append(home / ".apkx" / "platform-tools")
    candidates.append(home / ".apkx" / "build-tools")

    exe_names = ["aapt2.exe", "aapt.exe"] if sys.platform == "win32" else ["aapt2", "aapt"]
    for base in candidates:
        if not base.exists():
            continue
        build_tools = base / "build-tools"
        if build_tools.is_dir():
            for version_dir in sorted(build_tools.iterdir(), reverse=True):
                if version_dir.is_dir():
                    for exe in exe_names:
                        target = version_dir / exe
                        if target.is_file():
                            return str(target)
        for exe in exe_names:
            target = base / exe
            if target.is_file():
                return str(target)

    return None


def extract_apk_label(apk_path: Path) -> Optional[str]:
    """
    Mengekstrak label aplikasi resmi dari file APK lokal menggunakan aapt2 dump badging.
    """
    aapt_bin = find_aapt_binary()
    if not aapt_bin or not apk_path.is_file():
        return None

    try:
        proc = subprocess.run(
            [aapt_bin, "dump", "badging", str(apk_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=4,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if line.startswith("application-label:"):
                    m = re.search(r"application-label(?:-[a-zA-Z]+)?:'([^']*)'", line)
                    if m and m.group(1).strip():
                        return m.group(1).replace(r"\'", "'").strip()
                if line.startswith("launchable-activity:") and "label='" in line:
                    m = re.search(r"label='([^']*)'", line)
                    if m and m.group(1).strip():
                        return m.group(1).replace(r"\'", "'").strip()
    except Exception:
        pass

    return None


def format_fallback_app_name(
    package_name: str,
    activity_name: Optional[str] = None,
    cache: Optional[Dict[str, str]] = None,
) -> str:
    """
    Menghasilkan nama aplikasi yang mudah dibaca secara universal:
    1. Cek cache disk (~/.apkx/app_cache.json).
    2. Cek kamus POPULAR_APPS (termasuk kasus codename game/aplikasi).
    3. Evaluasi launcher activity hanya jika BUKAN engine/komponen generic.
    4. Ekstrak identitas produk dari Package ID dengan pemisahan kata majemuk & CamelCase.
    """
    # 1. Cek cache lokal
    if cache is not None and package_name in cache:
        return cache[package_name]

    # 2. Cek kamus aplikasi populer & codename
    if package_name in POPULAR_APPS:
        return POPULAR_APPS[package_name]

    # 3. Coba ekstrak dari Activity Launcher HANYA jika bukan framework/wrapper/screen
    if activity_name and not is_framework_or_wrapper_activity(package_name, activity_name):
        act_parts = activity_name.split(".")
        for part in reversed(act_parts):
            clean = re.sub(r"(Activity|MainActivity|Splash|Revamp|App|_|\$)", "", part, flags=re.IGNORECASE).strip()
            if clean and len(clean) >= 3 and clean.lower() not in GENERIC_SCREEN_WORDS:
                words = _split_camel_case(clean)
                return words.title()

    # 4. Ekstrak identitas produk dari Package ID (misal: com.project.aplikasi.Geoabsen -> Geoabsen)
    pkg_parts = package_name.split(".")
    candidate = pkg_parts[-1]
    if candidate.lower() in {"android", "app", "mobile", "frontend", "twa"} and len(pkg_parts) >= 2:
        candidate = pkg_parts[-2]

    # Bersihkan karakter pemisah seperti strip dan underscore
    clean_candidate = re.sub(r"[-_]", " ", candidate)

    # Coba pecah kata majemuk umum jika candidate berhuruf kecil semua
    if clean_candidate.islower():
        compound_result = _split_compound_words(clean_candidate)
        if compound_result != clean_candidate:
            return compound_result

    # Format pemisahan CamelCase
    words = _split_camel_case(clean_candidate)
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
    cache = load_app_cache()
    app_list: List[AppInfo] = []

    for pkg in packages:
        act = launcher_map.get(pkg)
        friendly_name = format_fallback_app_name(pkg, activity_name=act, cache=cache)
        app_list.append(AppInfo(package_name=pkg, app_name=friendly_name, activity_name=act))

    # Urutkan berdasarkan nama aplikasi agar rapi secara alfabetis
    return sorted(app_list, key=lambda a: a.app_name.lower())

