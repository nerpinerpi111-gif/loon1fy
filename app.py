"""
Loonify-клон: плеер с треками из Яндекс Музыки, Spotify, SoundCloud и YouTube Music.

Установка:
    python -m pip install pywebview yt-dlp ytmusicapi yandex-music spotipy

Запуск (файлы app.py и ui.html должны лежать в одной папке):
    python app.py
"""
import json
import os
import random
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from pathlib import Path

import webview
from yt_dlp import YoutubeDL
from ytmusicapi import YTMusic

DIR = Path.home() / ".loonify"
DIR.mkdir(exist_ok=True)
DB = DIR / "data.json"
SESSION = DIR / "session.json"   # очередь, позиция, громкость и т.п.
REDIRECT = "http://127.0.0.1:8888/callback"

# Запросы для случайной подборки, пока у тебя нет своих лайков
RANDOM_QUERIES = [
    "pop hits", "rock classics", "lofi hip hop", "electronic dance", "indie",
    "jazz", "русский рэп", "русский рок", "русский поп", "k-pop", "synthwave",
    "metal", "r&b", "house", "ambient", "old school hip hop", "90s hits",
    "2000s hits", "chill", "acoustic", "phonk", "soul", "punk", "reggae",
    "latin hits", "drum and bass", "blues", "новинки 2026", "top hits 2025",
]

# Настроения для «Моей волны»: ключ -> поисковые запросы
MOODS = {
    "sad": ["sad songs", "грустные песни", "heartbreak songs", "грустный рэп", "sad piano", "melancholy indie"],
    "happy": ["happy songs", "весёлые песни", "feel good hits", "good vibes pop", "summer hits", "позитивные песни"],
    "energy": ["workout hits", "energetic rock", "upbeat pop", "бодрые песни", "high energy dance", "pump up songs"],
    "calm": ["calm music", "спокойная музыка", "chill acoustic", "relaxing lofi", "soft indie", "ambient chill"],
    "love": ["love songs", "романтические песни", "romantic r&b", "песни про любовь", "slow love ballads"],
    "dance": ["dance hits", "club hits", "танцевальные хиты", "house party", "disco hits", "edm hits"],
    "focus": ["focus music", "study lofi", "instrumental focus", "deep work ambient", "минимал электроника"],
    "night": ["night drive", "late night chill", "synthwave night", "ночные песни", "dark r&b", "phonk night"],
    "nostalgia": ["90s hits", "2000s hits", "ностальгия 2000-х", "80s hits", "русские хиты 2000-х", "old school hits"],
}


def _write(path, obj):
    """Атомарная запись: сначала во временный файл, потом замена —
    так данные не повредятся, даже если окно закрыли посреди записи."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), "utf-8")
    os.replace(tmp, path)


def _dur(s):
    try:
        n = 0
        for x in str(s).split(":"):
            n = n * 60 + int(x)
        return n
    except Exception:
        return 0


def _key(t):
    return f'{t["src"]}:{t["id"]}'


class Api:
    # Все внутренние атрибуты начинаются с "_", иначе pywebview попытается
    # выставить их в JavaScript.
    def __init__(self):
        self._lock = threading.Lock()
        self._d = {"likes": [], "history": [], "cfg": {}}
        try:
            self._d.update(json.loads(DB.read_text("utf-8")))
        except Exception:
            pass
        self._session = {}
        try:
            self._session = json.loads(SESSION.read_text("utf-8"))
        except Exception:
            pass
        self._served = set()
        self._ytm = YTMusic()
        self._ym = None
        self._sp = None
        self._cache = {}
        cfg = self._d["cfg"]
        if cfg.get("ym_token"):
            self.connect_ym(cfg["ym_token"])
        if cfg.get("sp_id"):
            try:
                self._sp_init(cfg["sp_id"], cfg["sp_secret"], interactive=False)
            except Exception:
                pass

    # ---------- служебное ----------
    def _save(self):
        with self._lock:
            _write(DB, self._d)

    def save_session(self, sess):
        """Вызывается из интерфейса: запоминает очередь, позицию, громкость и т.д."""
        self._session = sess
        with self._lock:
            _write(SESSION, sess)
        return True

    def _merge_likes(self, tracks):
        have = {_key(t) for t in self._d["likes"]}
        self._d["likes"] += [t for t in tracks if _key(t) not in have]
        self._save()
        return self._d["likes"]

    def open_url(self, url):
        webbrowser.open(url)

    def get_state(self):
        return {
            "likes": self._d["likes"],
            "history": self._d["history"],
            "ym": self._ym is not None,
            "sp": self._sp is not None,
            "session": self._session,
        }

    def toggle_like(self, t):
        likes = self._d["likes"]
        k = _key(t)
        if any(_key(x) == k for x in likes):
            self._d["likes"] = [x for x in likes if _key(x) != k]
        else:
            likes.insert(0, t)
        self._save()
        return self._d["likes"]

    def add_history(self, t):
        h = [x for x in self._d["history"] if _key(x) != _key(t)]
        h.insert(0, t)
        self._d["history"] = h[:50]
        self._save()
        return self._d["history"]

    # ---------- поиск ----------
    def _s_ytm(self, q, limit=10):
        out = []
        for r in self._ytm.search(q, filter="songs", limit=limit):
            if not r.get("videoId"):
                continue
            out.append({
                "src": "ytm", "id": r["videoId"], "title": r["title"],
                "artist": ", ".join(a["name"] for a in r.get("artists") or []),
                "cover": (r.get("thumbnails") or [{}])[-1].get("url", ""),
                "dur": r.get("duration_seconds") or 0,
            })
        return out

    def _s_sc(self, q):
        with YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True}) as y:
            info = y.extract_info(f"scsearch10:{q}", download=False)
        out = []
        for e in info.get("entries") or []:
            out.append({
                "src": "sc", "id": str(e.get("id")),
                "url": e.get("url") or e.get("webpage_url"),
                "title": e.get("title", ""), "artist": e.get("uploader") or "",
                "cover": (e.get("thumbnails") or [{}])[-1].get("url", ""),
                "dur": int(e.get("duration") or 0),
            })
        return out

    def _ym_track(self, t):
        cover = "https://" + t.cover_uri.replace("%%", "200x200") if t.cover_uri else ""
        return {
            "src": "ym", "id": str(t.id), "title": t.title,
            "artist": ", ".join(a.name for a in t.artists), "cover": cover,
            "dur": (t.duration_ms or 0) // 1000,
        }

    def _s_ym(self, q):
        if not self._ym:
            return []
        res = self._ym.search(q, type_="track")
        items = res.tracks.results if res and res.tracks else []
        return [self._ym_track(t) for t in items[:10]]

    def search(self, q):
        def safe(f):
            try:
                return f(q)
            except Exception:
                return []
        with ThreadPoolExecutor(3) as ex:
            parts = list(ex.map(safe, [self._s_ym, self._s_ytm, self._s_sc]))
        mixed = [t for group in zip_longest(*parts) for t in group if t]
        return mixed

    # ---------- случайная подборка / «Моя волна» ----------
    def _random_tracks(self, per_query, queries=2, pool=None):
        out = []
        pool = pool or RANDOM_QUERIES
        for q in random.sample(pool, min(queries, len(pool))):
            try:
                out += self._s_ytm(q, per_query)
            except Exception:
                pass
        return out

    def _radio(self, seed):
        """Похожие треки на один из твоих лайков (радио YouTube Music)."""
        vid = seed["id"] if seed["src"] == "ytm" else self._match_yt(seed)
        res = self._ytm.get_watch_playlist(videoId=vid, radio=True, limit=25)
        out = []
        for r in (res.get("tracks") or [])[1:]:
            if not r.get("videoId"):
                continue
            thumbs = r.get("thumbnail") or r.get("thumbnails") or [{}]
            out.append({
                "src": "ytm", "id": r["videoId"], "title": r.get("title", ""),
                "artist": ", ".join(a["name"] for a in r.get("artists") or []),
                "cover": thumbs[-1].get("url", ""),
                "dur": _dur(r.get("length")),
            })
        return out

    def discover(self, n=20, mood="", _retry=True):
        """Выбрано настроение -> треки под него. Иначе: нет лайков -> случайные,
        есть лайки -> похожие на них + немного случайных."""
        likes = self._d["likes"]
        if mood in MOODS:
            jobs = [lambda: self._random_tracks(12, 3, MOODS[mood])]
        elif likes:
            seeds = random.sample(likes, min(3, len(likes)))
            jobs = [(lambda s=s: self._radio(s)) for s in seeds]
            jobs.append(lambda: self._random_tracks(10, 1))
        else:
            jobs = [lambda: self._random_tracks(15, 3)]

        def run(f):
            try:
                return f()
            except Exception:
                return []
        with ThreadPoolExecutor(4) as ex:
            parts = list(ex.map(run, jobs))

        liked = {_key(t) for t in likes}
        out, seen = [], set()
        for g in zip_longest(*parts):
            for t in g:
                if not t:
                    continue
                k = _key(t)
                if k in liked or k in seen or k in self._served:
                    continue
                seen.add(k)
                out.append(t)
        if not out and self._served and _retry:
            self._served.clear()
            return self.discover(n, mood, _retry=False)
        random.shuffle(out)
        out = out[:n]
        self._served |= {_key(t) for t in out}
        if len(self._served) > 1000:
            self._served.clear()
        return out

    # ---------- получение потока ----------
    def _ydl_url(self, url, fmt):
        opts = {"quiet": True, "noplaylist": True, "format": fmt}
        with YoutubeDL(opts) as y:
            return y.extract_info(url, download=False)["url"]

    def _ym_url(self, tid):
        tr = self._ym.tracks([tid])[0]
        infos = tr.get_download_info(get_direct_links=True)
        mp3 = [i for i in infos if i.codec == "mp3"] or infos
        return max(mp3, key=lambda i: i.bitrate_in_kbps).direct_link

    def _match_yt(self, t):
        k = _key(t)
        if k not in self._cache:
            r = self._ytm.search(f'{t["artist"]} {t["title"]}', filter="songs", limit=1)
            if not r:
                raise RuntimeError("трек не найден на YouTube Music")
            self._cache[k] = r[0]["videoId"]
        return self._cache[k]

    def resolve(self, t):
        try:
            s = t["src"]
            if s == "ym":
                return {"url": self._ym_url(t["id"])}
            if s == "sc":
                return {"url": self._ydl_url(t["url"], "bestaudio[protocol^=http]/bestaudio")}
            vid = t["id"] if s == "ytm" else self._match_yt(t)
            return {"url": self._ydl_url("https://music.youtube.com/watch?v=" + vid,
                                         "bestaudio[ext=m4a]/bestaudio")}
        except Exception as e:
            return {"error": str(e)[:200]}

    # ---------- Яндекс Музыка ----------
    def connect_ym(self, token):
        try:
            from yandex_music import Client
            c = Client(token).init()
            self._ym = c
            self._d["cfg"]["ym_token"] = token
            self._save()
            return {"ok": True, "msg": "Яндекс Музыка подключена"}
        except Exception as e:
            return {"ok": False, "msg": f"Ошибка Яндекса: {str(e)[:120]}"}

    def import_ym(self):
        if not self._ym:
            return self._d["likes"]
        tracks = self._ym.users_likes_tracks().fetch_tracks()
        return self._merge_likes([self._ym_track(t) for t in tracks])

    # ---------- Spotify ----------
    def _sp_init(self, cid, secret, interactive=True):
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        am = SpotifyOAuth(client_id=cid, client_secret=secret, redirect_uri=REDIRECT,
                          scope="user-library-read", cache_path=str(DIR / "sp_cache"))
        if not interactive and not am.get_cached_token():
            return False
        sp = spotipy.Spotify(auth_manager=am)
        sp.current_user()  # при первом входе откроет браузер
        self._sp = sp
        return True

    def connect_sp(self, cid, secret):
        try:
            self._sp_init(cid, secret)
            self._d["cfg"].update({"sp_id": cid, "sp_secret": secret})
            self._save()
            return {"ok": True, "msg": "Spotify подключён"}
        except Exception as e:
            return {"ok": False, "msg": f"Ошибка Spotify: {str(e)[:120]}"}

    def import_sp(self):
        if not self._sp:
            return self._d["likes"]
        out, offset = [], 0
        while True:
            page = self._sp.current_user_saved_tracks(limit=50, offset=offset)
            for it in page["items"]:
                t = it["track"]
                imgs = t["album"]["images"]
                out.append({
                    "src": "sp", "id": t["id"], "title": t["name"],
                    "artist": ", ".join(a["name"] for a in t["artists"]),
                    "cover": imgs[-2]["url"] if len(imgs) > 1 else (imgs[0]["url"] if imgs else ""),
                    "dur": t["duration_ms"] // 1000,
                })
            if not page["next"]:
                break
            offset += 50
        return self._merge_likes(out)


if __name__ == "__main__":
    import sys
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    ui = base / "ui.html"
    if not ui.exists():
        raise SystemExit("ui.html не найден рядом с app.py. Положите его в папку: " + str(ui.parent))
    api = Api()
    webview.create_window(
        "Loonify", html=ui.read_text("utf-8"), js_api=api,
        width=1280, height=780, min_size=(960, 620), background_color="#000000",
    )
    webview.start()
