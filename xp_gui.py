# =============================
# DLTB Configurator
# =============================
# 1) Imports & constants
# 2) Helpers (filesystem, detection, utils)
# 3) Patchers (read template -> modify -> write scripts)
# 4) Build/install pipeline
# 5) UI state (tk variables)
# 6) UI builders (create frames/widgets)
# 7) UI callbacks (apply, build, status, refresh)
# 8) main()
# =============================


# -----------------------------
# 1) Imports & constants
# -----------------------------

# --- Standard library ---
import os
import re
import sys
import json
import ctypes
import shutil
import subprocess
import zipfile
import datetime
import time
import webbrowser
from pathlib import Path
from dataclasses import dataclass

# --- Third-party ---
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

# --- Tkinter ---
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser


@dataclass
class FlashlightParams:
    drain_per_second: float
    max_energy: float
    regen_delay: float


APP_NAME = "DLTB Configurator"
OUTPUT_DIR = "output"
PAK_NAME = "data7.pak"
STATUS_REF = [None]
APP_ROOT = Path(__file__).resolve().parent

def status(items):
    cb = STATUS_REF[0]
    if cb:
        cb(items)  
        
SMM_CONFIG_PATH = Path("config") / "tools.json"

# DPI-aware (valfritt men rekommenderat) - måste ligga innan root skapas
def enable_high_dpi_awareness():
    if sys.platform.startswith("win"):
        try:
            # Per-monitor DPI aware (Win 8.1+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

enable_high_dpi_awareness()

# AppUserModelID måste sättas FÖRE något fönster skapas (Windows taskbar/ikon)
if sys.platform.startswith("win"):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DLTB.Configurator")
    except Exception:
        pass

# Skapa root
root = tb.Window(
    themename="darkly",
    title="DLTB Configurator by Robeloto v0.6b",
    size=(1100, 750),
)

try:
    dpi = root.winfo_fpixels("1i")      # 
    scale = dpi / 72.0                  # OBS: 72 brukar kännas bättre i Tk på Windows
    scale = max(1.10, min(2.00, scale)) # clamp
    root.tk.call("tk", "scaling", scale)
except Exception:
    pass

# Sen layout-grejer
root.minsize(1050, 650)

def _load_tools_cfg() -> dict:
    try:
        if SMM_CONFIG_PATH.exists():
            return json.loads(SMM_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_tools_cfg(cfg: dict):
    SMM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SMM_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def find_super_mod_merger_exe() -> Path | None:
    # 1) sparad path
    cfg = _load_tools_cfg()
    p = cfg.get("super_mod_merger_exe")
    if p:
        pp = Path(p)
        if pp.exists():
            return pp

    # 2) om du installerat SMM som en “mod” via din app
    try:
        for mod_root, manifest in list_installed_mods():
            raw_dir = mod_root / "raw"
            exe = raw_dir / "SuperModMerger.exe"
            if exe.exists():
                return exe
    except Exception:
        pass

    # 3) vanliga nedladdningsställen
    candidates = [
        Path.home() / "Downloads" / "SuperModMerger.exe",
        Path.home() / "Desktop" / "SuperModMerger.exe",
    ]
    for c in candidates:
        if c.exists():
            return c

    # 4) sök i senaste Downloads-zip-extract-mappar (lite dyrt men ok)
    dl = Path.home() / "Downloads"
    if dl.exists():
        try:
            for exe in dl.rglob("SuperModMerger.exe"):
                return exe
        except Exception:
            pass

    return None

def pick_super_mod_merger_exe() -> Path | None:
    p = filedialog.askopenfilename(
        title="Select SuperModMerger.exe",
        filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
    )
    if not p:
        return None
    exe = Path(p)
    cfg = _load_tools_cfg()
    cfg["super_mod_merger_exe"] = str(exe)
    _save_tools_cfg(cfg)
    return exe

def run_super_mod_merger(game_root: Path):
    exe = find_super_mod_merger_exe()
    if not exe:
        exe = pick_super_mod_merger_exe()
        if not exe:
            status([(" Super Mod Merger not set. Choose SuperModMerger.exe first.", "warn")])
            return

    game_root = Path(str(game_root).strip())
    phft = game_root / "ph_ft"
    if not phft.exists():
        status([(" Select valid Game Folder (must contain ph_ft).", "warn")])
        return

    # SMM behöver se ./mods (din app) + data0.pak (ph_ft)
    # Lösning: kör i ph_ft och skapa en länk/junction 'mods' -> din app's mods
    app_root = Path(__file__).resolve().parent
    mods_src = app_root / "mods"
    mods_link = phft / "mods"

    try:
        mods_src.mkdir(exist_ok=True)

        if not mods_link.exists():
            # Windows junction: ph_ft/mods -> <app_root>/mods
            subprocess.run(["cmd", "/c", "mklink", "/J", str(mods_link), str(mods_src)], check=True)

        subprocess.Popen([str(exe)], cwd=str(phft))
        status([(" Opened Super Mod Merger ✔  ", "ok"), ("Run merge, then Play Game.", "warn")])
    except Exception as e:
        status([(" Failed to start Super Mod Merger: ", "warn"), (str(e), "warn")])
        
def files_url(mod_id: int, file_id: int | None = None) -> str:
    url = f"https://www.nexusmods.com/dyinglightthebeast/mods/{mod_id}?tab=files"
    if file_id:
        url += f"&file_id={file_id}"
    return url

def nmm_url(mod_id: int, file_id: int) -> str:
    return f"https://www.nexusmods.com/dyinglightthebeast/mods/{mod_id}?tab=files&file_id={file_id}&nmm=1"

RECOMMENDED_MODS = [
    {
        "name": "Apex Volatile Revamp",
        "mod_id": 745,
        "file_id": 2485,
        "affects": ["dlc_ft_zmb_volatile_apex.model"],
    },
    {
        "name": "Arankt's best vehicle enhancements",
        "mod_id": 716,
        "file_id": 2353,
        "affects": ["damagedefinitions.scr", "healthdefinitions.scr", "vehicle_skin_presets.scr", "car.scr"],
        "notes": "+ more",
    },
    {
        "name": "Better Flashlight",
        "mod_id": 81,
        "file_id": 132,
        "affects": ["varlist.scr"],
    },
    {
        "name": "Better Fov",
        "mod_id": 751,
        "file_id": None,
        "affects": ["player_variables.scr", "vehicle_pickup_camera_params.scr", "buggy_wasteland_camera_params.scr", "vehicle_truck_camera_params.scr"],
    },
    {
        "name": "Infinite durability and Stamina",
        "mod_id": 774,
        "file_id": 2591,
        "affects": ["player_variables.scr"],
    },
    {
        "name": "Play as Frank West",
        "mod_id": 772,
        "file_id": 2588,
        "affects": ["player_outfit_slots.scr"],
    },
    {
        "name": "Restore Nightmare Mode Survivor Sense",
        "mod_id": 767,
        "file_id": None,
        "affects": ["NightmareSurvivorSense.asi"],
    },
    {
        "name": "Special Weapons Blueprints",
        "mod_id": 686,
        "file_id": 2212,
        "file_id": 2212,
        "affects": ["collectables_ft.scr", "shop_item_sets.scr"],
    },
        {
        "name": "Super Mod Merger",
        "mod_id": 699,
        "file_id": 2512,
        "affects": [""],
    },
]

def ensure_mod_urls():
    for m in RECOMMENDED_MODS:
        m["url"] = files_url(m["mod_id"], m.get("file_id"))
        file_id = m.get("file_id")
        m["nmm_url"] = nmm_url(m["mod_id"], file_id) if file_id else None

ensure_mod_urls()

def pick_mod_archive():
    path = filedialog.askopenfilename(
        title="Select mod archive",
        filetypes=[
            ("Archives", "*.zip *.7z *.rar"),
            ("ZIP", "*.zip"),
            ("7-Zip", "*.7z"),
            ("RAR", "*.rar"),
            ("All files", "*.*"),
        ],
    )
    return Path(path) if path else None
    
def find_7z_exe() -> Path | None:
    # 1) bundlad (rekommenderat)
    bundled = Path(resource_path("assets/tools/7z.exe"))
    if bundled.exists():
        return bundled

    # 2) system-install (vanliga paths)
    candidates = [
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ]
    for c in candidates:
        if c.exists():
            return c

    # 3) PATH
    p = shutil.which("7z")
    return Path(p) if p else None

def extract_archive(archive_path: Path, dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)

    seven = find_7z_exe()
    if not seven:
        messagebox.showerror(
            "7-Zip not found",
            "To install .rar/.7z mods, include assets/tools/7z.exe (and 7z.dll) "
            "or install 7-Zip to C:\\Program Files\\7-Zip."
        )
        return False

    # 7z x = extract with full paths, -y = yes to all, -o = output dir
    cmd = [str(seven), "x", str(archive_path), f"-o{dest_dir}", "-y"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            messagebox.showerror("Extract failed", (r.stderr or r.stdout or "Unknown error").strip())
            return False
        return True
    except Exception as e:
        messagebox.showerror("Extract failed", str(e))
        return False

import time

def flatten_single_root_folder(dest: Path):
    items = [p for p in dest.iterdir()]
    if len(items) == 1 and items[0].is_dir():
        root = items[0]
        for p in root.iterdir():
            shutil.move(str(p), str(dest / p.name))
        shutil.rmtree(root, ignore_errors=True)



def install_mod_archive_button():
    # Visa direkt att något händer (innan fil-dialogen)
    status([("Opening file dialog…", "warn")])
    root.update_idletasks()

    t0 = time.perf_counter()
    archive = pick_mod_archive()  # Path eller None
    dt_dialog = time.perf_counter() - t0

    if not archive:
        status([("Cancelled.", "warn")])
        return

    status([(f"Selected: {archive.name} (dialog {dt_dialog:.1f}s)", "ok"),
            ("Preparing install…", "warn")])
    root.update_idletasks()

    mod_name = archive.stem
    mod_root = MODS_DIR / mod_name
    raw_dir = mod_root / "raw"

    MODS_DIR.mkdir(parents=True, exist_ok=True)

    # overwrite-fråga (du kan byta bort messagebox senare om du vill)
    if mod_root.exists():
        if not messagebox.askyesno("Overwrite?", f"{mod_name} already exists. Overwrite?"):
            status([("Install aborted (not overwriting).", "warn")])
            return
        shutil.rmtree(mod_root, ignore_errors=True)

    raw_dir.mkdir(parents=True, exist_ok=True)

    status([("Extracting archive…", "warn")])
    root.update_idletasks()

    t1 = time.perf_counter()
    ok = extract_archive(archive, raw_dir)
    dt_extract = time.perf_counter() - t1

    if not ok:
        shutil.rmtree(mod_root, ignore_errors=True)
        status([("Extract failed. Nothing was installed.", "warn")])
        return

    # optional
    flatten_single_root_folder(raw_dir)

    status([(f"Extract OK ({dt_extract:.2f}s). Indexing files…", "ok")])
    root.update_idletasks()

    # indexera filer
    files = [str(p.relative_to(raw_dir)).replace("\\", "/")
             for p in raw_dir.rglob("*") if p.is_file()]
    scr_files = [f for f in files if f.lower().endswith(".scr")]

    manifest = {
        "name": mod_name,
        "installed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "enabled": True,
        "archive_path": str(archive),
        "raw_dir": str(raw_dir),
        "files": files,
        "scr_files": scr_files,
        "priority": {},  # ex: {"player_variables.scr": "mod_wins"}
    }

    status([("Writing manifest…", "warn")])
    root.update_idletasks()

    (mod_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    status([
        ("Mod added to Configurator ✔", "ok"),
        ("Next: Deploy → Apply → Build & Install PAK", "warn"),
    ])

def open_url(url: str):
    url = (url or "").strip()
    print("[OPEN_URL] url =", repr(url))
    if not url:
        messagebox.showwarning("Open link", "Empty URL")
        return

    try:
        # robustare än webbrowser.open i vissa lägen
        webbrowser.open_new_tab(url)
    except Exception as e:
        messagebox.showerror("Open link failed", str(e))

def open_mod_files(mod: dict):
    open_url(files_url(mod["mod_id"], mod.get("file_id")))

def open_mod_manager(mod: dict):
    file_id = mod.get("file_id")
    if not file_id:
        messagebox.showinfo("Not available", "No file_id set for this mod.")
        return
    open_url(nmm_url(mod["mod_id"], file_id))

SCRIPTS_DIR = Path("scripts")  # "DLTB Configurator\\scripts" när du kör från projektroten
MODS_DIR = Path("mods") / "installed"

PARAM_RE = re.compile(r'(?m)^\s*Param\("([^"]+)"\s*,\s*"([^"]*)"\)\s*;\s*$')

def get_enabled_mods() -> list[tuple[Path, dict]]:
    mods = []
    if not MODS_DIR.exists():
        return mods
    for mod_root in sorted(MODS_DIR.iterdir()):
        if not mod_root.is_dir():
            continue
        mf = mod_root / "manifest.json"
        if not mf.exists():
            continue
        try:
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if manifest.get("enabled", False):
            mods.append((mod_root, manifest))
    return mods

def extract_params(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in PARAM_RE.finditer(text)}

def replace_param(text: str, name: str, value: str) -> str:
    pat = re.compile(rf'(?m)^(\s*Param\("{re.escape(name)}"\s*,\s*")([^"]*)("\)\s*;\s*)$')
    if not pat.search(text):
        return text
    return pat.sub(rf'\g<1>{value}\g<3>', text, count=1)

def merge_scr(config_text: str, mod_text: str, mod_wins: bool) -> tuple[str, list[tuple[str,str,str]]]:
    cfg = extract_params(config_text)
    mod = extract_params(mod_text)
    merged = config_text
    conflicts = []

    for k, mod_val in mod.items():
        if k in cfg and cfg[k] != mod_val:
            conflicts.append((k, cfg[k], mod_val))
            if mod_wins:
                merged = replace_param(merged, k, mod_val)

    return merged, conflicts

def find_all_mod_scr_files(mod_root: Path) -> list[Path]:
    raw_dir = mod_root / "raw"
    if not raw_dir.exists():
        return []
    return [p for p in raw_dir.rglob("*.scr") if p.is_file()]

def apply_enabled_mods_to_scripts(scripts_dir: Path, default_policy: str = "config_wins"):
    """
    default_policy: "config_wins" eller "mod_wins"
    """
    scripts_dir = Path(scripts_dir)
    if not scripts_dir.exists():
        raise FileNotFoundError(f"Scripts dir not found: {scripts_dir}")

    enabled = get_enabled_mods()
    if not enabled:
        return

    for mod_root, manifest in enabled:
        mod_name = manifest.get("name", mod_root.name)

        # policy per mod (valfritt senare)
        mod_wins_default = (default_policy == "mod_wins")

        for mod_scr in find_all_mod_scr_files(mod_root):
            target_name = mod_scr.name
            out_scr = scripts_dir / target_name

            mod_text = mod_scr.read_text(encoding="utf-8", errors="ignore")

            # Om config redan har filen → merge Param()
            if out_scr.exists():
                cfg_text = out_scr.read_text(encoding="utf-8", errors="ignore")

                # här kan du senare läsa per-fil policy ur manifest["priority"][target_name]
                mod_wins = mod_wins_default

                merged, conflicts = merge_scr(cfg_text, mod_text, mod_wins)
                out_scr.write_text(merged, encoding="utf-8")

                # (valfritt) logga konflikter för debug
                if conflicts:
                    print(f"[MOD MERGE] {mod_name} conflicts in {target_name}: {len(conflicts)}")
            else:
                # Config har inte filen → kopiera in den
                shutil.copy2(mod_scr, out_scr)
                print(f"[MOD COPY] {mod_name} copied {target_name}")

def find_mod_file(mod_root: Path, filename: str) -> Path | None:
    raw_dir = mod_root / "raw"
    if not raw_dir.exists():
        return None
    hits = list(raw_dir.rglob(filename))
    return hits[0] if hits else None
        
def load_manifest(mod_root: Path) -> dict | None:
    p = mod_root / "manifest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def save_manifest(mod_root: Path, manifest: dict):
    p = mod_root / "manifest.json"
    p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

def build_installed_mods_ui(parent):
    frame = tb.Labelframe(parent, text="Installed Mods", padding=6)
    frame.pack(fill="both", expand=True, pady=(2, 0))

    bottom_container = tb.Frame(frame)
    bottom_container.pack(fill="x", expand=False, side="bottom")
    details = tb.Label(bottom_container, text="", justify="left", anchor="w", wraplength=0)
    details.pack(fill="x", pady=(0, 2))

    btn_row = tb.Frame(bottom_container)
    btn_row.pack(fill="x")
    btn_toggle = tb.Button(btn_row, text="Enable/Disable", bootstyle=SECONDARY)
    btn_toggle.pack(side="left", padx=(0, 8))

    btn_open_folder = tb.Button(btn_row, text="Open Folder", bootstyle=SECONDARY)
    btn_open_folder.pack(side="left")

    btn_remove = tb.Button(btn_row, text="Remove", bootstyle=DANGER)
    btn_remove.pack(side="left", padx=(8, 0))

    top_container = tb.Frame(frame)
    top_container.pack(fill="both", expand=True)
    lb = tk.Listbox(top_container, height=12)
    lb.pack(fill="both", expand=True, pady=(0, 4))
    bind_mousewheel_to_listbox(lb)

    data = {"mods": []}

    def refresh():
        lb.delete(0, "end")
        data["mods"] = list_installed_mods()

        for mod_root, manifest in data["mods"]:
            enabled = manifest.get("enabled", False)
            name = manifest.get("name", mod_root.name)
            prefix = "✅ " if enabled else "⛔ "
            lb.insert("end", prefix + name)

        if data["mods"]:
            lb.selection_set(0)
            update_details()

    def get_selected():
        sel = lb.curselection()
        return data["mods"][sel[0]] if sel else None

    def update_details(_evt=None):
        item = get_selected()
        if not item:
            details.config(text="")
            return
        mod_root, manifest = item
        name = manifest.get("name", mod_root.name)
        enabled = manifest.get("enabled", False)
        scr = manifest.get("scr_files", [])
        files_count = len(manifest.get("files", []))

        details.config(text=f"{name} | Enabled: {enabled} | Files: {files_count} | SCR: {len(scr)}")

    def toggle_enabled():
        item = get_selected()
        if not item:
            return
        mod_root, manifest = item
        manifest["enabled"] = not bool(manifest.get("enabled", False))
        save_manifest(mod_root, manifest)
        refresh()

    def open_folder():
        item = get_selected()
        if not item:
            return
        mod_root, _ = item
        try:
            os.startfile(mod_root)
        except Exception as e:
            messagebox.showerror("Open folder failed", str(e))

    def remove_selected():
        item = get_selected()
        if not item:
            return
        mod_root, manifest = item
        if uninstall_installed_mod(mod_root, manifest):
            refresh()

    btn_toggle.config(command=toggle_enabled)
    btn_open_folder.config(command=open_folder)
    btn_remove.config(command=remove_selected)

    lb.bind("<<ListboxSelect>>", update_details)

    refresh()
    return frame
    
def build_recommended_mods_ui(parent, set_status_cb=None):
    frame = tb.Labelframe(parent, text="Recommended Nexus Mods", padding=6)
    frame.pack(fill="both", expand=True, pady=(0, 2))

    # Grid: row 0 = listbox (guaranteed min height), row 1 = details + buttons + deployed list
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_rowconfigure(0, weight=1, minsize=120)
    frame.grid_rowconfigure(1, weight=0, minsize=140)

    lb = tk.Listbox(frame, height=9, exportselection=False)
    lb.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
    bind_mousewheel_to_listbox(lb)

    bottom_block = tb.Frame(frame)
    bottom_block.grid(row=1, column=0, sticky="ew")

    details = tb.Label(bottom_block, text="", anchor="w", wraplength=0)
    details.pack(fill="x", pady=(0, 2))
    
    btn_row = tb.Frame(bottom_block)
    btn_row.pack(fill="x")
    btn_files = tb.Button(btn_row, text="Open Files (Slow/Fast)", bootstyle=PRIMARY)
    btn_files.pack(side="left", padx=(0, 4))
    
    btn_smm = tb.Button(btn_row, text="Open Super Mod Merger", bootstyle=SECONDARY)
    btn_smm.pack(side="left", padx=(8, 0))
    btn_smm.config(command=lambda: run_super_mod_merger(Path(game_path_var.get().strip())))

    btn_nmm = tb.Button(btn_row, text="Mod Manager Download", bootstyle=SECONDARY)
    btn_nmm.pack(side="left")

    btn_install = tb.Button(btn_row, text="1. Install Archive (.zip/.rar)", bootstyle=INFO)
    btn_install.pack(side="left", padx=(8, 0))
    btn_install.config(command=install_mod_archive_button)
    
    btn_deploy = tb.Button(btn_row, text="2. Deploy Enabled Mods", bootstyle="warning-outline")
    btn_deploy.pack(side="left", padx=(8, 0))

    deployed_lb = tk.Listbox(bottom_block, height=4)
    deployed_lb.pack(fill="x", expand=False, pady=(4, 0))

    for m in RECOMMENDED_MODS:
        lb.insert("end", m["name"])

    def get_selected_mod():
        sel = lb.curselection()
        return RECOMMENDED_MODS[sel[0]] if sel else None

    def update_ui(_evt=None):
        m = get_selected_mod()
        if not m:
            btn_files.config(state="disabled")
            btn_nmm.config(state="disabled")
            details.config(text="")
            return

        btn_files.config(state="normal")
        btn_nmm.config(state=("normal" if m.get("file_id") else "disabled"))

        affects = m.get("affects", [])
        affects_txt = ", ".join(affects) if affects else "—"
        notes = m.get("notes")
        notes_txt = f" | Notes: {notes}" if notes else ""
        url_txt = files_url(m["mod_id"], m.get("file_id"))
        details.config(text=f"{m['name']} | Affects: {affects_txt}{notes_txt} | {url_txt}")

    def on_files():
        m = get_selected_mod()
        if not m:
            messagebox.showinfo("Select a mod", "Select a mod in the list first.")
            return
        open_mod_files(m)

    def on_nmm():
        m = get_selected_mod()
        if not m:
            messagebox.showinfo("Select a mod", "Select a mod in the list first.")
            return
        open_mod_manager(m)

    def do_deploy():
        gp = Path(game_path_var.get().strip())
        _cb = (set_status_cb[0] if isinstance(set_status_cb, list) else set_status_cb) if set_status_cb else None
        if str(gp) in ("", "."):
            if _cb:
                _cb([(" Select Game Folder first.", "warn")])
            return

        deployed = deploy_enabled_mod_files(gp)

        deployed_lb.delete(0, "end")
        for p in deployed:
            deployed_lb.insert("end", p)

        if _cb:
            if deployed:
                _cb([
                    (" Mods deployed ✔  ", "ok"),
                    ("Press Apply / Build & Install PAK.", "ok"),
                ])
            else:
                _cb([(" No deployable files found for enabled mods.", "warn")])
            
    btn_files.config(command=on_files)
    btn_nmm.config(command=on_nmm)
    btn_deploy.config(command=do_deploy)

    lb.bind("<<ListboxSelect>>", update_ui)
    lb.bind("<Double-Button-1>", lambda e: on_files())

    if lb.size() > 0:
        lb.selection_set(0)
    update_ui()

    frame.update_idletasks()
    return frame
  
    # --- Helpers ---
    
# ---- Deploy helpers ----
ASSETS_PC_RE = re.compile(r"^assets_(\d+)_pc$", re.IGNORECASE)   # matchar p.stem
DATA_PAK_RE  = re.compile(r"^data(\d+)$", re.IGNORECASE)         # matchar p.stem ("data5")

def bind_mousewheel_to_listbox(lb: tk.Listbox):
    def _on_mousewheel(event):
        # Windows: event.delta är ±120 per notch
        lb.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"  # stoppa att parent scrollar

    # Windows / Mac
    lb.bind("<MouseWheel>", _on_mousewheel)

    # Linux (om du bryr dig)
    lb.bind("<Button-4>", lambda e: (lb.yview_scroll(-1, "units"), "break"))
    lb.bind("<Button-5>", lambda e: (lb.yview_scroll(1, "units"), "break"))

def find_free_slot(dir_path: Path, stem_re: re.Pattern, max_slots: int) -> int | None:
    used = set()
    if dir_path.exists():
        for p in dir_path.iterdir():
            if p.is_file():
                m = stem_re.match(p.stem)
                if m:
                    used.add(int(m.group(1)))
    for i in range(1, max_slots + 1):
        if i not in used:
            return i
    return None

def deploy_enabled_mod_files(game_root: Path) -> list[str]:
    game_root = Path(str(game_root).strip())
    if str(game_root) in ("", "."):
        return []

    assets_dir = game_root / "ph_ft" / "work" / "data_platform" / "pc" / "assets"
    pak_dir    = game_root / "ph_ft" / "source"
    bin_dir    = game_root / "ph_ft" / "work" / "bin" / "x64"

    # sanity check (tyst) – bara avbryt om fel
    if not (game_root / "ph_ft").exists():
        print(f"[DEPLOY] wrong game folder: {game_root}")
        return []

    assets_dir.mkdir(parents=True, exist_ok=True)
    pak_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    enabled = get_enabled_mods()
    if not enabled:
        return []

    deployed: list[str] = []

    for mod_root, manifest in enabled:
        raw_dir = mod_root / "raw"
        mod_name = manifest.get("name", mod_root.name)

        if not raw_dir.exists():
            print(f"[DEPLOY] missing raw_dir for {mod_name}: {raw_dir}")
            continue

        for src in raw_dir.rglob("*"):
            if not src.is_file():
                continue

            low = src.name.lower()

            try:
                if low.endswith((".asi", ".dll")):
                    dest = bin_dir / src.name
                    shutil.copy2(src, dest)
                    deployed.append(str(dest))
                    continue

                if low.endswith(".rpack") and "_pc" in low:
                    slot = find_free_slot(assets_dir, ASSETS_PC_RE, 5)
                    if slot is None:
                        print(f"[DEPLOY] assets slots full: {assets_dir}")
                        continue
                    dest = assets_dir / f"assets_{slot}_pc.rpack"
                    shutil.copy2(src, dest)
                    deployed.append(str(dest))
                    continue

                if re.match(r"^data\d+\.pak$", src.name, re.IGNORECASE):
                    slot = find_free_slot(pak_dir, DATA_PAK_RE, 7)
                    if slot is None:
                        print(f"[DEPLOY] pak slots full: {pak_dir}")
                        continue
                    dest = pak_dir / f"data{slot}.pak"
                    shutil.copy2(src, dest)
                    deployed.append(str(dest))
                    continue

            except Exception as e:
                print(f"[DEPLOY] ERROR copying {src} ({mod_name}) -> {e}")

    print(f"[DEPLOY] deployed {len(deployed)} files")
    return deployed
    
def uninstall_installed_mod(mod_root: Path, manifest: dict):
    name = manifest.get("name", mod_root.name)

    # Säkerhetsfråga
    if not messagebox.askyesno("Remove mod?", f"Remove '{name}' from Installed Mods?\n\nThis deletes:\n{mod_root}"):
        return False

    try:
        shutil.rmtree(mod_root, ignore_errors=False)
        return True
    except Exception as e:
        messagebox.showerror("Remove failed", str(e))
        return False
    
    def get_selected_mod():
        sel = lb.curselection()
        if not sel:
            messagebox.showinfo("Select a mod", "Select a mod in the list first.")
            return None
        return RECOMMENDED_MODS[sel[0]]
        
       
    def update_buttons(_evt=None):
        sel = lb.curselection()
        if not sel:
            btn_files.config(state="disabled")
            btn_nmm.config(state="disabled")
            details.config(text="")
            return

        m = RECOMMENDED_MODS[sel[0]]

        btn_files.config(state="normal")
        btn_nmm.config(state=("normal" if m.get("file_id") else "disabled"))

        affects = m.get("affects", [])
        affects_txt = ", ".join(affects) if affects else "—"

        notes = m.get("notes")
        notes_txt = f"\nNotes: {notes}" if notes else ""

        # Länkvisning (valfritt)
        url_txt = files_url(m["mod_id"], m.get("file_id"))

        details.config(
            text=f"Affects: {affects_txt}{notes_txt}\nLink: {url_txt}"
        )
        
    def on_files():
        m = get_selected_mod()
        if not m:
            messagebox.showinfo("Select a mod", "Select a mod in the list first.")
            return
        open_mod_files(m)
        
    def on_nmm():
        m = get_selected_mod()
        if not m:
            messagebox.showinfo("Select a mod", "Select a mod in the list first.")
            return
        open_mod_manager(m)
        
    btn_files.config(command=on_files)
    btn_nmm.config(command=on_nmm)

    lb.bind("<<ListboxSelect>>", update_buttons)
    lb.bind("<Double-Button-1>", lambda e: on_files())

    lb.selection_set(0)
    update_buttons()
    
    return frame

def list_installed_mods() -> list[tuple[Path, dict]]:
    mods = []
    if not MODS_DIR.exists():
        return mods
    for mod_root in sorted(MODS_DIR.iterdir()):
        if not mod_root.is_dir():
            continue
        m = load_manifest(mod_root)
        if m:
            mods.append((mod_root, m))
    return mods
    
# Spawn patches have no effect in game v1.5+
SPAWNS_SUPPORTED = False

import math

JUMP_HOLD_DEFAULT = 2.76
JUMP_FURY_DEFAULT = 2.80
JUMP_ONHEIGHT_DEFAULT = 0.5

FALL_LARGE_DEFAULT   = 6.0
FALL_HARMFUL_DEFAULT = 8.0
FALL_LETHAL_DEFAULT  = 12.0

JUMP_SAFE_MAX = 6

MAX_JUMP_MULT = 12.0

JUMP_OVERRIDE_MAX = 90.0  # max 

MAX_JUMP_MULT = 12.0
JUMP_OVERRIDE_MAX = 90.0

def patch_jump_and_fall_direct(content: str, jump_value: float, override_on: bool) -> str:
    # clamp till 0..90
    v = float(jump_value)
    if v < 0.0:
        v = 0.0
    if v > 90.0:
        v = 90.0

    # Jump: skriv direkt
    content = _set_param_value(content, "HoldJumpHeight", f"{v:.4f}")
    content = _set_param_value(content, "FuryHoldJumpHeight", f"{v:.4f}")

    # JumpOnHeight: jump on zombie
    content = _set_param_value(content, "JumpOnHeight", f"{min(v, 10.0):.4f}")

    # Fall
    if override_on:
        content = _set_param_value(content, "LargeFallHeight", "2000.0")
        content = _set_param_value(content, "HarmfulHeight",   "4000.0")
        content = _set_param_value(content, "LethalHeight",    "8000.0")
        content = _set_param_value(content, "FallingHeightToRespawn", "99999")

    return content

# UI colors
COLOR_OK = "#27be0e"
COLOR_WARN = "#9f9f9f"
COLOR_BORDER = "#111111"
# Card border (Volatiles and other tabs) — use same for background and color so all cards match
CARD_HIGHLIGHT = "#8A8A8A"

# -----------------------------
# Game pool constants
# -----------------------------
EXTERIOR_NIGHT_VOLATILE_POOLS = [
    "Night_Exterior_D01",
    "Night_Exterior_D02",
    "Night_Exterior_D03",
    "Night_Exterior_D04",
    "Night_Exterior_D05",
    "Night_Exterior_D06",
    "Night_Exterior_D07",
    "Night_Exterior_D08",
    "Night_Exterior_D09",
    "Night_Exterior_End",
    "Night_Exterior_Hive",
    "Night_Exterior_R01",
    "Night_Exterior_R01_playtest_hard",
    "Night_Exterior_R01_playtest_medium",
    "Night_Exterior_R01_playtest_no_virals",
    "Night_Exterior_CityCenter_Benchmark",
]

# -----------------------------
# 2) Helpers (filesystem, detection, utils)
# -----------------------------


def enable_dark_titlebar(root):
    if sys.platform != "win32":
        return
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Win 11/nyare Win10
        value = ctypes.c_int(1)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        if res != 0:
            # fallback för vissa Win10-builds
            DWMWA_USE_IMMERSIVE_DARK_MODE = 19
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except Exception:
        pass


def make_scrollable(parent):
    outer = tb.Frame(parent)

    # Canvas i dark theme (tk.Canvas kan stylas med bg)
    canvas = tk.Canvas(
        outer,
        highlightthickness=0,
        borderwidth=0,
        bg=outer.winfo_toplevel().cget("background"),  # matcha theme-bg
    )

    # Bootstrap scrollbar (inte tk.Scrollbar)
    vsb = tb.Scrollbar(outer, orient="vertical", command=canvas.yview, bootstyle="dark-round")
    canvas.configure(yscrollcommand=vsb.set)

    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner = tb.Frame(canvas)  # inner får theme
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_configure(_event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event):
        canvas.itemconfigure(window_id, width=event.width)

    inner.bind("<Configure>", _on_inner_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # Windows + Touchpad:
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _bind(_e=None):
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind(_e=None):
        canvas.unbind_all("<MouseWheel>")

    canvas.bind("<Enter>", _bind)
    canvas.bind("<Leave>", _unbind)

    return outer, inner


def create_scrollable_frame(parent):
    """Canvas + vertical Scrollbar + inner Frame; mouse wheel scrolls when cursor over canvas. Returns (outer, inner)."""
    outer = tb.Frame(parent)
    canvas = tk.Canvas(
        outer,
        highlightthickness=0,
        borderwidth=0,
        bg=outer.winfo_toplevel().cget("background"),
    )
    vsb = tb.Scrollbar(outer, orient="vertical", command=canvas.yview, bootstyle="dark-round")
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    inner = tb.Frame(canvas)
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_configure(_event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event):
        canvas.itemconfigure(window_id, width=event.width)

    inner.bind("<Configure>", _on_inner_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind(_e=None):
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind(_e=None):
        canvas.unbind_all("<MouseWheel>")

    canvas.bind("<Enter>", _bind)
    canvas.bind("<Leave>", _unbind)

    return outer, inner


def _fuel_color_bar_row(
    parent,
    label: str,
    var: tk.IntVar,
    vmin: int,
    vmax: int,
    step: int,
    color_func,
    bar_width: int = 220,
    bar_height: int = 18,
):
    """One row: label + clickable/draggable color bar + entry. Updates var; bar color from color_func(value)."""
    row = tk.Frame(parent)
    row.pack(fill="x", anchor="center", pady=(0, 4))
    tk.Label(row, text=label, font=("Arial", 9, "bold"), anchor="center", width=14).pack(side="left", padx=(0, 6))

    def value_to_x(val):
        if vmax == vmin:
            return 0
        return int((val - vmin) / (vmax - vmin) * (bar_width - 2))

    def x_to_value(x):
        x = max(0, min(x, bar_width - 1))
        val = vmin + (x / (bar_width - 1)) * (vmax - vmin)
        val = round(val / step) * step
        return max(vmin, min(vmax, int(val)))

    def set_from_event(ev):
        val = x_to_value(ev.x)
        var.set(val)

    def update_bar(*_):
        val = var.get()
        val = max(vmin, min(vmax, val))
        r, g, b = color_func(val)
        hex_c = f"#{r:02x}{g:02x}{b:02x}"
        canvas.delete("bar")
        canvas.create_rectangle(1, 1, bar_width - 1, bar_height - 1, fill=hex_c, outline="#888", tags="bar")

    canvas = tk.Canvas(row, width=bar_width, height=bar_height, highlightthickness=0, borderwidth=1, relief="solid")
    canvas.pack(side="left", padx=(0, 6))
    canvas.bind("<Button-1>", set_from_event)
    canvas.bind("<B1-Motion>", set_from_event)
    var.trace_add("write", update_bar)
    entry = tk.Entry(row, width=5, textvariable=var)
    entry.pack(side="left")
    update_bar()
    return row
    
def pick_scale(ret):
    if hasattr(ret, "config"):
        return ret
    if isinstance(ret, tuple):
        for item in ret:
            if hasattr(item, "config"):
                return item
    raise TypeError("ui_labeled_slider() did not return a Scale-like widget")
    
def find_scale(obj):
    """Returnerar första tk.Scale/ttk.Scale den hittar i obj (tuple/list/widget)."""
    # Direkt scale?
    if isinstance(obj, (tk.Scale, ttk.Scale)):
        return obj

    # Widget-container? (Frame etc) -> kolla barn
    if isinstance(obj, tk.Widget):
        for child in obj.winfo_children():
            sc = find_scale(child)
            if sc is not None:
                return sc
        return None

    # Tuple/list -> gå igenom
    if isinstance(obj, (tuple, list)):
        for item in obj:
            sc = find_scale(item)
            if sc is not None:
                return sc
        return None

    return None
    
def red_callout(parent, padx=0, pady=0):
    """Returns (box_frame, inner_frame). box_frame has the red border; reconfigure it when path is set."""
    box = tk.Frame(parent, highlightthickness=2, highlightbackground="#d00000")
    box.pack(side="left", padx=0, pady=0)   
    inner = tk.Frame(box)
    inner.pack(padx=padx, pady=pady)        
    return box, inner
  
def resource_path(rel_path: str) -> str:
    # If PyInstaller onefile: sys._MEIPASS points to temp extraction dir
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)   # works for onedir
        mei_dir = getattr(sys, "_MEIPASS", None)     # exists for onefile
        if mei_dir:
            base_dir = mei_dir
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_dir, rel_path)

def config_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    p = base / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p

SAVE_PATH_TXT = config_dir() / "save_path.txt"

def load_save_path_txt() -> str:
    try:
        s = SAVE_PATH_TXT.read_text(encoding="utf-8").strip()
        return s
    except FileNotFoundError:
        return ""
    except Exception as e:
        print("load_save_path_txt ERROR:", e)
        return ""

def save_save_path_txt(path_str: str) -> None:
    try:
        SAVE_PATH_TXT.write_text((path_str or "").strip(), encoding="utf-8")
        print("Saved save_path to:", str(SAVE_PATH_TXT))
    except Exception as e:
        print("save_save_path_txt ERROR:", e)
        raise

def looks_like_dltb_root(path: str) -> bool:
    """Return True if path looks like the games root (where ph_ft/source is located)."""
    return os.path.isdir(os.path.join(path, "ph_ft", "source"))


def find_dltb_candidates_windows():
    """Try to find DLTB in common Steam/Epic folders. Returns list of paths."""
    candidates = []

    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")

    common_roots = [
        os.path.join(program_files_x86, "Steam", "steamapps", "common"),
        os.path.join(program_files, "Steam", "steamapps", "common"),
        r"C:\Steam\steamapps\common",
        r"D:\Steam\steamapps\common",
        r"D:\SteamLibrary\steamapps\common",
        r"E:\Steam\steamapps\common",
        r"E:\SteamLibrary\steamapps\common",
        r"F:\Steam\steamapps\common",
        r"F:\SteamLibrary\steamapps\common",
        r"G:\Steam\steamapps\common",
        r"G:\SteamLibrary\steamapps\common",
        r"H:\Steam\steamapps\common",
        r"H:\SteamLibrary\steamapps\common",
        r"I:\Steam\steamapps\common",
        r"I:\SteamLibrary\steamapps\common",
        r"J:\Steam\steamapps\common",
        r"J:\SteamLibrary\steamapps\common",
    ]

    epic_roots = [
        r"C:\Games",
        r"D:\Games",
        r"E:\Games",
        r"F:\Games",
        r"G:\Games",
        r"H:\Games",
        r"I:\Games",
        r"J:\Games",
        r"K:\Games",
    ]

    possible_folder_names = [
        "Dying Light The Beast",
        "Dying Light: The Beast",
        "DyingLightTheBeast",
    ]

    def probe_root(root_dir):
        if not os.path.isdir(root_dir):
            return
        for name in possible_folder_names:
            p = os.path.join(root_dir, name)
            if looks_like_dltb_root(p):
                candidates.append(p)

        # fallback: scan folders in root_dir
        try:
            for entry in os.listdir(root_dir):
                p = os.path.join(root_dir, entry)
                if os.path.isdir(p) and looks_like_dltb_root(p):
                    candidates.append(p)
        except Exception:
            pass

    for r in common_roots:
        probe_root(r)
    for r in epic_roots:
        probe_root(r)

    # unique
    uniq = []
    seen = set()
    for c in candidates:
        cc = os.path.normpath(c)
        if cc not in seen:
            seen.add(cc)
            uniq.append(cc)
    return uniq
    
def ui_keybind_row(parent, label_text: str, var: tk.StringVar, hint: str = ""):
    row = tk.Frame(parent)
    row.pack(fill="x", pady=2)

    tk.Label(row, text=label_text, width=20, anchor="w").pack(side="left")

    tk.Entry(row, textvariable=var, width=12, bg="white", fg="black").pack(side="left", padx=(6, 6))

    def _bind():
        root_win = parent.winfo_toplevel()  # always a Tk/Toplevel, never a string
        capture_bind(root_win, var, f"Bind: {label_text}")

    tk.Button(row, text="Bind…", command=_bind).pack(side="left", padx=(0, 10))

    if hint:
        tk.Label(row, text=hint, fg="#666666", font=("Arial", 8)).pack(side="left")

    return row

def keysym_to_friendly(keysym: str) -> str:
    k = (keysym or "").strip()

    # normalize common Tk names
    mapping = {
        "space": "Space",
        "Return": "Enter",
        "Escape": "Esc",
        "Tab": "Tab",
        "Caps_Lock": "CapsLock",
        "Shift_L": "LShift",
        "Shift_R": "RShift",
        "Control_L": "LCtrl",
        "Control_R": "RCtrl",
        "Alt_L": "LAlt",
        "Alt_R": "RAlt",
        "Up": "Up",
        "Down": "Down",
        "Left": "Left",
        "Right": "Right",
    }
    if k in mapping:
        return mapping[k]

    # letters
    if len(k) == 1 and k.isalpha():
        return k.upper()

    # numbers
    if len(k) == 1 and k.isdigit():
        return k

    # Function keys like F1..F12
    if k.startswith("F") and k[1:].isdigit():
        return k.upper()

    # fallback: use raw
    return k


def friendly_mouse_button(btn_num: int) -> str:
    # Tk: 1=left, 2=middle, 3=right, 4/5=wheel on some systems
    if btn_num == 2:
        return "Mouse3"   # your game uses BUTTON_3 as “middle” in your snippet
    if btn_num == 3:
        return "MouseRight"
    if btn_num == 1:
        return "MouseLeft"
    return f"Mouse{btn_num}"

def capture_bind(root, target_var: tk.StringVar, title="Press a key"):
    win = tk.Toplevel(root)
    win.title(title)
    win.transient(root)
    win.grab_set()  # modal
    win.resizable(False, False)

    tk.Label(win, text="Press a key or mouse button…", font=("Arial", 10, "bold")).pack(padx=14, pady=(12, 6))
    tk.Label(win, text="(Esc cancels)", fg="#666666", font=("Arial", 9)).pack(padx=14, pady=(0, 12))

    def on_key(e):
        # Esc cancels
        if e.keysym == "Escape":
            win.destroy()
            return
        friendly = keysym_to_friendly(e.keysym)
        target_var.set(friendly)
        win.destroy()

    def on_mouse(e):
        friendly = friendly_mouse_button(e.num)
        target_var.set(friendly)
        win.destroy()

    win.bind("<KeyPress>", on_key)
    win.bind("<ButtonPress>", on_mouse)

    # ensure it receives focus
    win.focus_force()

    
def to_input_token(user_key: str) -> str:
    k = (user_key or "").strip()

    # Normalisera lite
    aliases = {
        " ": "Space",
        "Spacebar": "Space",
        "comma": ",",
        "COMMA": ",",
        "Comma": ",",
        "Esc": "Escape",
        "PgUp": "PageUp",
        "PgDn": "PageDown",
        "Del": "Delete",
        "Ins": "Insert",
        "Caps": "CapsLock",
        "LShift": "LeftShift",
        "RShift": "RightShift",
        "LCtrl": "LeftControl",
        "RCtrl": "RightControl",
        "LAlt": "LeftAlt",
        "RAlt": "RightAlt",
        "UpArrow": "Up",
        "DownArrow": "Down",
        "LeftArrow": "Left",
        "RightArrow": "Right",
    }
    k = aliases.get(k, k)

    # Mouse
    mouse_map = {
        "Mouse1": "EMouse__BUTTON_1",
        "Mouse2": "EMouse__BUTTON_2",
        "Mouse3": "EMouse__BUTTON_3",
        "Mouse4": "EMouse__BUTTON_4",
        "Mouse5": "EMouse__BUTTON_5",
        "WheelUp": "EMouse__WHEEL_UP",
        "WheelDown": "EMouse__WHEEL_DOWN",
    }
    if k in mouse_map:
        return mouse_map[k]

    # Keyboard
    key_map = {
        # arrows
        "Up": "EKey__UP_",
        "Down": "EKey__DOWN",
        "Left": "EKey__LEFT",
        "Right": "EKey__RIGHT",

        # common
        "Space": "EKey__SPACE_",
        "CapsLock": "EKey__CAPITAL",
        "Tab": "EKey__TAB",
        "Enter": "EKey__RETURN",
        "Escape": "EKey__ESCAPE",
        "Backspace": "EKey__BACK",

        # nav/edit (här kommer din Home)
        "Home": "EKey__HOME",
        "End": "EKey__END",
        "PageUp": "EKey__PRIOR",     # ofta PageUp
        "PageDown": "EKey__NEXT",    # ofta PageDown
        "Insert": "EKey__INSERT",
        ",": "EKey__COMMA",
        "Delete": "EKey__DELETE",

        # modifiers
        "LeftShift": "EKey__LSHIFT",
        "RightShift": "EKey__RSHIFT",
        "LeftControl": "EKey__LCONTROL",
        "RightControl": "EKey__RCONTROL",
        "LeftAlt": "EKey__LMENU",
        "RightAlt": "EKey__RMENU",
    }

    # A–Z
    if len(k) == 1 and k.isalpha():
        return f"EKey__{k.upper()}"

    # 0–9
    if len(k) == 1 and k.isdigit():
        return f"EKey__{k}"

    if k in key_map:
        return key_map[k]

    allowed = sorted(list(key_map.keys()) + ["A-Z", "0-9"] + list(mouse_map.keys()))
    raise Exception(f"Unknown key '{user_key}'. Try: " + ", ".join(allowed[:25]) + ("..." if len(allowed) > 25 else ""))
    

def app_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    d = base / "DLTB Configurator"
    d.mkdir(parents=True, exist_ok=True)
    return d

BACKUPS_DIR = app_data_dir() / "player_backup_saves"
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

        
def add_banner(parent, image_path, height=160):
    banner_frame = tk.Frame(parent)
    banner_frame.pack(fill="x", pady=(6, 10))

    # Om man skickar bara "dltb.jpg" → auto-prefixa assets/
    p = Path(image_path)
    if len(p.parts) == 1:
        image_path = str(Path("assets") / image_path)

    img_path = resource_path(image_path)

    # DEBUG: visa exakt vad som händer
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    assets_dir = Path(base) / "assets"
    debug = (
        f"MEIPASS/base:\n{base}\n\n"
        f"Requested:\n{image_path}\n\n"
        f"Resolved img_path:\n{img_path}\n\n"
        f"Exists(img_path): {Path(img_path).exists()}\n"
        f"Exists(assets_dir): {assets_dir.exists()}\n"
    )

    if assets_dir.exists():
        try:
            files = sorted([x.name for x in assets_dir.iterdir()][:50])
            debug += "\nAssets dir files (first 50):\n" + "\n".join(files)
        except Exception as e:
            debug += f"\nCould not list assets dir: {e}"

    try:
        pil_original = Image.open(img_path).convert("RGBA")
    except Exception:
        tk.Label(
            banner_frame,
            text="Banner missing (debug below)",
            fg="red",
            font=("Arial", 9, "bold"),
        ).pack(pady=(0, 6))

        t = tk.Text(banner_frame, height=14, wrap="word")
        t.insert("1.0", debug)
        t.config(state="disabled")
        t.pack(fill="x", padx=6)
        return banner_frame

    lbl = tk.Label(banner_frame, bd=0)
    lbl.pack(fill="x")


    def _redraw(_event=None):
        w = banner_frame.winfo_width()
        if w <= 10:
            return

        scale = height / pil_original.height
        new_w = int(pil_original.width * scale)
        new_h = int(pil_original.height * scale)

        if new_w > w:
            scale = w / pil_original.width
            new_w = int(pil_original.width * scale)
            new_h = int(pil_original.height * scale)

        resized = pil_original.resize((new_w, new_h), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(resized)
        lbl.configure(image=tk_img)
        lbl.image = tk_img

    banner_frame.bind("<Configure>", _redraw)
    _redraw()
    return banner_frame

def fmt_one_decimal(x: float) -> str:

    return f"{x:.1f}"
    
def app_dir() -> Path:
    # Där exe:n ligger när du kör PyInstaller, annars där .py ligger
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent
    
def auto_detect_game_folder():
    cands = find_dltb_candidates_windows()
    if not cands:
        raise Exception("Could not auto-detect game folder. Select manually.")
    return cands[0]


def save_game_path(path):
    with open("game_path.txt", "w", encoding="utf-8") as f:
        f.write(path)


def load_game_path():
    if os.path.exists("game_path.txt"):
        with open("game_path.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


PRESET_SCHEMA_VERSION = 1


def preset_dump(preset_vars):
    data = {"_schema": PRESET_SCHEMA_VERSION}
    for key, var in preset_vars:
        try:
            data[key] = var.get()
        except Exception:
            pass
    return data


def preset_apply(preset_vars, data):
    lookup = {k: v for (k, v) in preset_vars}

    # Migration: old sp_story_limit -> sp_agenda_limit (now shared)
    if "sp_story_limit" in data and "sp_agenda_limit" not in data:
        data["sp_agenda_limit"] = data["sp_story_limit"]
    # Migration: old sp_dynamic_limit -> sp_spawner_limit (now shared)
    if "sp_dynamic_limit" in data and "sp_spawner_limit" not in data:
        data["sp_spawner_limit"] = data["sp_dynamic_limit"]
    # Migration: old sp_challenge_limit -> sp_gameplay_limit (now shared)
    if "sp_challenge_limit" in data and "sp_gameplay_limit" not in data:
        data["sp_gameplay_limit"] = data["sp_challenge_limit"]
    # Migration: old 4 spawn limit sliders -> sp_dynamic_spawner_master (0-100)
    if "sp_dynamic_spawner_master" not in data:
        for old_key in ("sp_agenda_limit", "sp_spawner_limit", "sp_gameplay_limit", "sp_aiproxy_limit"):
            if old_key in data:
                v = data[old_key]
                if old_key == "sp_agenda_limit":
                    t = (v - 60) / 60 if isinstance(v, (int, float)) else 0
                elif old_key == "sp_spawner_limit":
                    t = (v - 120) / 180 if isinstance(v, (int, float)) else 0
                elif old_key == "sp_gameplay_limit":
                    t = (v - 10) / 190 if isinstance(v, (int, float)) else 0
                else:
                    t = (v - 120) / 40 if isinstance(v, (int, float)) else 0
                t = max(0, min(1, t))
                data["sp_dynamic_spawner_master"] = round(t * 100)
                break

    # Migration: old uv12_regen_var -> fl_regen_delay_uv1_var, fl_regen_delay_uv2_var
    if "uv12_regen_var" in data and "fl_regen_delay_uv1_var" not in data:
        v = data["uv12_regen_var"]
        data["fl_regen_delay_uv1_var"] = v
        data["fl_regen_delay_uv2_var"] = v

    for key, value in data.items():
        if isinstance(key, str) and key.startswith("_"):
            continue

        var = lookup.get(key)
        if var is None:
            continue

        try:
            # mild casting
            if isinstance(var, tk.BooleanVar):
                var.set(bool(value))
            elif isinstance(var, tk.IntVar):
                var.set(int(value))
            elif isinstance(var, tk.DoubleVar):
                var.set(float(value))
            else:
                var.set(str(value))
        except Exception:
            pass

def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("scripts", exist_ok=True)


def disable_children(widget: tk.Widget) -> None:
    """Recursively disable all children (ttk: state disabled, tk: state=disabled)."""
    for child in widget.winfo_children():
        try:
            if isinstance(child, ttk.Widget):
                try:
                    child.state(["disabled"])
                except tk.TclError:
                    pass
            else:
                try:
                    child.configure(state="disabled")
                except tk.TclError:
                    pass
        except Exception:
            pass
        disable_children(child)


def clear_scripts():
    # remove generated scripts only
    for folder in ("scripts/player", "scripts/progression",):
        if os.path.exists(folder):
            for f in os.listdir(folder):
                try:
                    os.remove(os.path.join(folder, f))
                except Exception:
                    pass


# -----------------------------
# 3) Patchers (read template -> modify -> write scripts)
# -----------------------------
from typing import Callable, Iterable, Set, List, Tuple

Patcher = Callable[[str], str]


def apply_patchers(content: str, patchers: List[Patcher]) -> str:
    for i, patch in enumerate(patchers):
        if patch is None:
            raise Exception(
                f"Patcher #{i} is None (you appended None to patchers list)"
            )
        content = patch(content)
    return content
    
def patch_disable_layout_keybinding_for_action(action_name: str):
    """
    Comment out LayoutKeybinding(...) { ... } blocks that contain Action(action_name);
    """
    # Match LayoutKeybinding-block
    block_pat = re.compile(r'(?s)(?P<block>LayoutKeybinding\(".*?"\s*,.*?\)\s*\{.*?\})')

    action_pat = re.compile(rf'(?m)^\s*Action\(\s*{re.escape(action_name)}\s*\)\s*;\s*$')

    def _comment_block(block: str) -> str:
        # Comment each line with //
        return "\n".join("//" + line if not line.lstrip().startswith("//") else line
                         for line in block.splitlines())

    def _patch(content: str) -> str:
        changed = False

        def repl(m: re.Match) -> str:
            nonlocal changed
            block = m.group("block")
            if action_pat.search(block):
                changed = True
                return _comment_block(block)
            return block

        out = block_pat.sub(repl, content)
        if not changed:

            return out
        return out

    return _patch


def patch_volatile_weights_scale_for_pools(
    *, pct: int, pools: Iterable[str], min_weight: int = 2
) -> Patcher:
    pct = int(pct)
    pools_set: Set[str] = set(pools)

    pool_pat = re.compile(r'^\s*Pool\(\s*"([^"]+)"\s*\)')
    weighted_pat = re.compile(
        r'^(?P<indent>\s*)PresetWeighted\(\s*"(?P<preset>Character;Volatile[^"]*)"\s*,\s*(?P<num>\d+)\s*\)(?P<tail>.*)$'
    )

    def _patch(content: str) -> str:
        out = []
        current_pool = ""

        for line in content.splitlines(keepends=True):
            # hoppa över kommenterade rader
            if line.lstrip().startswith("//"):
                out.append(line)
                continue

            pm = pool_pat.match(line)
            if pm:
                current_pool = pm.group(1)

            m = weighted_pat.match(line)
            if not m or current_pool not in pools_set:
                out.append(line)
                continue

            old = int(m.group("num"))
            new = int(round(old * (pct / 100.0)))

            if new < min_weight:
                new = min_weight

            if new != old:
                line = f'{m.group("indent")}PresetWeighted("{m.group("preset")}", {new}){m.group("tail")}'

            out.append(line)

        return "".join(out)

    return _patch

def patch_addaction_device_and_key(action_name: str, token: str):
    """
    token: "EKey__F" eller "EMouse__BUTTON_3"
    """
    is_mouse = token.startswith("EMouse__")
    new_device = "Mouse" if is_mouse else "Keyboard"

    pat = re.compile(
        rf'(?m)^(?P<indent>\s*)AddAction\(\s*{re.escape(action_name)}\s*,'
        r'(?P<rest>.*?EInputDevice_)(?P<device>Keyboard|Mouse)(?P<mid>.*?,\s*)'
        r'(?P<key>EKey__\w+_?|EMouse__\w+)(?P<afterkey>.*?\)\s*)'
        r'(?P<tail>;?\s*(\{.*\})?\s*)$'
    )

    def _patch(content: str) -> str:
        if not pat.search(content):
            raise Exception(f"{action_name} not found in inputs_keyboard.scr")

        return pat.sub(
            rf'\g<indent>AddAction({action_name},\g<rest>{new_device}\g<mid>{token}\g<afterkey>\g<tail>',
            content,
            count=1
        )

    return _patch
    
def patch_jump_heights(content: str, boost_slider_value: float) -> str:
    # 0 => 1.0x, 10 => 10.0x
    mult = 1.0 + (6.0 * (boost_slider_value / 10.0))

    hold = JUMP_HOLD_DEFAULT * mult
    fury = JUMP_FURY_DEFAULT * mult

    content = _set_param_value(content, "HoldJumpHeight", f"{hold:.4f}")
    content = _set_param_value(content, "FuryHoldJumpHeight", f"{fury:.4f}")
    return content


def patch_paramfloat_mul(name: str, mul: float) -> Patcher:
    """
    Finds ParamFloat("name", number) and replaces number with number * mul.
    Strict no-op: if mul == 1.0, returns identity patcher (do not patch).
    """
    if abs(mul - 1.0) < 1e-9:
        return lambda c: c
    pat = re.compile(
        rf'(?m)^(\s*ParamFloat\("{re.escape(name)}",\s*)([0-9.]+)(\).*)$'
    )

    def _patch(content: str) -> str:
        m = pat.search(content)
        if not m:
            raise Exception(f'ParamFloat("{name}", ...) not found in template')
        old_val = float(m.group(2))
        new_val = old_val * mul
        new_str = _fmt_num(new_val)
        new_content, n = pat.subn(rf"\g<1>{new_str}\g<3>", content, count=1)
        if n != 1:
            raise Exception(f'ParamFloat("{name}"): expected 1 match, got {n}')
        return new_content

    return _patch


def _extract_sub_block(content: str, sub_name: str) -> tuple[int, int] | None:
    """Find sub SubName() { ... } block. Returns (start_pos, end_pos) or None."""
    pat = re.compile(rf'(?m)^\s*sub\s+{re.escape(sub_name)}\s*\(\s*\)\s*(\r?\n\s*)?\{{')
    m = pat.search(content)
    if not m:
        return None
    brace_start = content.find("{", m.start())
    depth = 1
    i = brace_start + 1
    while i < len(content) and depth > 0:
        c = content[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return (m.start(), i) if depth == 0 else None


def _extract_tag_block(content: str, tag_name: str) -> tuple[int, int] | None:
    """Find Tag("tag_name") { ... } block. Returns (start_pos, end_pos) or None."""
    tag_pat = re.compile(
        rf'(?m)^\s*Tag\s*\(\s*"{re.escape(tag_name)}"\s*\)\s*(\r?\n\s*)?\{{'
    )
    m = tag_pat.search(content)
    if not m:
        return None
    start = m.start()
    brace_start = content.find("{", m.start())
    depth = 1
    i = brace_start + 1
    while i < len(content) and depth > 0:
        c = content[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return (start, i) if depth == 0 else None


def patch_volatile_damage_bonus(
    *,
    bonus_easy_pct: int,
    bonus_normal_pct: int,
    bonus_hard_pct: int,
    bonus_nightmare_pct: int,
) -> Patcher:
    if bonus_easy_pct == 0 and bonus_normal_pct == 0 and bonus_hard_pct == 0 and bonus_nightmare_pct == 0:
        return lambda c: c  # strict no-op

    factors = {
        "Easy": 1.0 + bonus_easy_pct / 100.0,
        "Normal": 1.0 + bonus_normal_pct / 100.0,
        "Hard": 1.0 + bonus_hard_pct / 100.0,
        "Nightmare": 1.0 + bonus_nightmare_pct / 100.0,
    }
    mult_pat = re.compile(
        r'^(\s*)(MeleeDamageMultiplier|RangeDamageMultiplier)\s*\(\s*"(Easy|Normal|Hard|Nightmare)"\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)(\s*;[^\r\n]*[\r\n]?)'
    )

    def _patch(content: str) -> str:
        block = _extract_tag_block(content, "volatile")
        if not block:
            return content
        start, end = block
        before = content[:start]
        block_content = content[start:end]
        after = content[end:]

        lines = block_content.splitlines(keepends=True)
        out = []
        for line in lines:
            m = mult_pat.match(line)
            if not m:
                out.append(line)
                continue
            indent, func, diff, tier, val_str, tail = m.groups()
            factor = factors.get(diff, 1.0)
            if factor == 1.0:
                out.append(line)
                continue
            old_val = float(val_str)
            new_val = round(old_val * factor, 3)
            if abs(new_val - old_val) < 1e-9:
                out.append(line)
                continue
            new_str = f"{new_val:.3f}".rstrip("0").rstrip(".")
            if "." not in new_str:
                new_str += ".0"
            new_line = f'{indent}{func}("{diff}", {tier}, {new_str}){tail}'
            out.append(new_line)

        return before + "".join(out) + after

    return _patch


def patch_human_health_bonus(
    *,
    bonus_easy_pct: int,
    bonus_normal_pct: int,
    bonus_hard_pct: int,
    bonus_nightmare_pct: int,
) -> Patcher:
    # 100% = vanilla (no-op). 10% = 0.1x, 500% = 5.0x (multiplier = pct/100)
    if bonus_easy_pct == 100 and bonus_normal_pct == 100 and bonus_hard_pct == 100 and bonus_nightmare_pct == 100:
        return lambda c: c  # strict no-op

    factors = {
        "Easy": bonus_easy_pct / 100.0,
        "Normal": bonus_normal_pct / 100.0,
        "Hard": bonus_hard_pct / 100.0,
        "Nightmare": bonus_nightmare_pct / 100.0,
    }
    mult_pat = re.compile(
        r'^(\s*)MaxHealthMultiplier\s*\(\s*"(Easy|Normal|Hard|Nightmare)"\s*,\s*(\d+)\s*,\s*(-?[\d.]+)\s*\)(\s*;[^\r\n]*[\r\n]?)'
    )

    def _patch(content: str) -> str:
        block = _extract_tag_block(content, "human")
        if not block:
            return content
        start, end = block
        before = content[:start]
        block_content = content[start:end]
        after = content[end:]

        lines = block_content.splitlines(keepends=True)
        out = []
        for line in lines:
            m = mult_pat.match(line)
            if not m:
                out.append(line)
                continue
            indent, diff, tier, val_str, tail = m.groups()
            factor = factors.get(diff, 1.0)
            if factor == 1.0:
                out.append(line)
                continue
            old_val = float(val_str)
            new_val = round(old_val * factor, 3)
            if abs(new_val - old_val) < 1e-9:
                out.append(line)
                continue
            new_str = f"{new_val:.3f}"

            new_line = f'{indent}MaxHealthMultiplier("{diff}", {tier}, {new_str}){tail}'
            out.append(new_line)

        return before + "".join(out) + after

    return _patch


def _fmt_health_val(x: float) -> str:
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    if s == "":
        s = "0"
    if "." not in s:
        s += ".0"
    return s


def patch_enemy_tag_health_multipliers(
    tag_name: str,
    easy_pct: int,
    normal_pct: int,
    hard_pct: int,
    nm_pct: int,
) -> Patcher:
    """Scale MaxHealthMultiplier(Difficulty, tier, value) inside Tag(tag_name) by pct/100. No-op if all 100."""
    if easy_pct == 100 and normal_pct == 100 and hard_pct == 100 and nm_pct == 100:
        return lambda c: c
    factors = {
        "Easy": easy_pct / 100.0,
        "Normal": normal_pct / 100.0,
        "Hard": hard_pct / 100.0,
        "Nightmare": nm_pct / 100.0,
    }
    mult_pat = re.compile(
        r'^(\s*)MaxHealthMultiplier\s*\(\s*"(Easy|Normal|Hard|Nightmare)"\s*,\s*(\d+)\s*,\s*(-?[\d.]+)\s*\)(\s*;[^\r\n]*[\r\n]?)'
    )

    def _patch(content: str) -> str:
        block = _extract_tag_block(content, tag_name)
        if not block:
            return content
        start, end = block
        before = content[:start]
        block_content = content[start:end]
        after = content[end:]
        lines = block_content.splitlines(keepends=True)
        out = []
        for line in lines:
            m = mult_pat.match(line)
            if not m:
                out.append(line)
                continue
            indent, diff, tier, val_str, tail = m.groups()
            factor = factors.get(diff, 1.0)
            if factor == 1.0:
                out.append(line)
                continue
            old_val = float(val_str)
            new_val = old_val * factor
            if abs(new_val - old_val) < 1e-9:
                out.append(line)
                continue
            new_str = _fmt_health_val(new_val)
            new_line = f'{indent}MaxHealthMultiplier("{diff}", {tier}, {new_str}){tail}'
            out.append(new_line)
        return before + "".join(out) + after

    return _patch


def patch_delete_perception_profiles(
    *,
    names: Iterable[str] = (),
    prefixes: tuple[str, ...] = (),
    exclude_names: Iterable[str] = (),
    exclude_if_contains: Iterable[str] = (),
) -> Patcher:
    names_set: Set[str] = set(names)
    exclude_set: Set[str] = set(exclude_names)
    contains_list = tuple(s.lower() for s in exclude_if_contains)

    # Matcha headern, och tillåt att '{' kan vara på samma rad eller nästa.
    header_pat = re.compile(
        r'(?m)^\s*PerceptionProfile\("(?P<name>[^"]+)"\)\s*(?:\r?\n\s*)?\{'
    )

    def should_delete(name: str) -> bool:
        if name in exclude_set:
            return False

        lname = name.lower()
        for s in contains_list:
            if s and s in lname:
                return False

        if names_set and name in names_set:
            return True
        if prefixes and name.startswith(prefixes):
            return True
        return False

    def delete_block_at(text: str, start: int, brace_index: int) -> tuple[str, bool]:
        """ """
        depth = 0
        i = brace_index
        while i < len(text):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    #
                    return text[:start] + text[i + 1 :], True
            i += 1
        return text, False  #

    def _patch(content: str) -> str:
        out = content
        changed = 0
        pos = 0

        while True:
            m = header_pat.search(out, pos)
            if not m:
                break

            name = m.group("name")

            # find position for '{' (match ends exactly after '{' cause of regex)
            brace_index = m.end() - 1
            block_start = m.start()

            if should_delete(name):
                new_out, removed = delete_block_at(out, block_start, brace_index)
                if removed:
                    out = new_out
                    changed += 1

                    pos = block_start
                    continue

            # not deleted, moving forward
            pos = m.end()

        if changed == 0:
            raise Exception(
                f"No PerceptionProfile blocks deleted. names={tuple(names_set)} prefixes={prefixes}"
            )

        # Verify that the header is not remaining
        if names_set:
            for n in names_set:
                if re.search(rf'(?m)^\s*PerceptionProfile\("{re.escape(n)}"\)', out):
                    raise Exception(
                        f"Delete failed: {n} block still present after patch"
                    )

        return out

    return _patch


def patch_ai_perception_profiles(
    *,
    target_prefixes: tuple[str, ...],
    mode: str,
    exclude_names: Iterable[str] = (),
    resting_profile: str = "volatile_hive_resting",
) -> Patcher:
    exclude_set: Set[str] = set(exclude_names)

    def _patch(content: str) -> str:
        if mode == "vanilla":
            return content

        block_pat = re.compile(
            r'(PerceptionProfile\("(?P<name>[^"]+)"\)\s*\{)(?P<body>.*?)(\n\s*\})',
            re.DOTALL,
        )

        def get_line_value(body: str, key: str) -> str | None:
            m = re.search(
                rf'^\s*{re.escape(key)}\("([^"]+)"\)\s*;\s*$', body, re.MULTILINE
            )
            return m.group(1) if m else None

        def set_line_value(body: str, key: str, new_value: str) -> str:
            line_pat = re.compile(
                rf'^(\s*{re.escape(key)}\(")([^"]+)("\)\s*;\s*)$', re.MULTILINE
            )
            if line_pat.search(body):
                return line_pat.sub(rf"\1{new_value}\3", body, count=1)

            if not body.endswith("\n"):
                body += "\n"
            return body + f'        {key}("{new_value}");\n'

        changed = 0

        def repl(m: re.Match) -> str:
            nonlocal changed
            name = m.group("name")
            body = m.group("body")

            if name in exclude_set:
                return m.group(0)

            if not name.startswith(target_prefixes):
                return m.group(0)

            default_v = get_line_value(body, "DefaultProfile")
            low_v = get_line_value(body, "LowAlertProfile")
            high_v = get_line_value(body, "HighAlertProfile")
            if not default_v or not low_v or not high_v:
                return m.group(0)

            new_body = body

            if mode == "high_to_low":
                new_body = set_line_value(new_body, "LowAlertProfile", default_v)
                new_body = set_line_value(new_body, "HighAlertProfile", low_v)

            elif mode == "high_to_default":
                new_body = set_line_value(new_body, "LowAlertProfile", default_v)
                new_body = set_line_value(new_body, "HighAlertProfile", default_v)

            elif mode == "all_to_resting":
                new_body = set_line_value(new_body, "DefaultProfile", resting_profile)
                new_body = set_line_value(new_body, "LowAlertProfile", resting_profile)
                new_body = set_line_value(new_body, "HighAlertProfile", resting_profile)

            else:
                raise ValueError(f"Unknown mode: {mode}")

            if new_body != body:
                changed += 1

            # m.group(1)=header, m.group(2)=body, m.group(3)=closing brace
            return m.group(1) + new_body + m.group(3)

        out = block_pat.sub(repl, content)

        if changed == 0:
            raise Exception(
                f"No PerceptionProfile blocks changed for prefixes={target_prefixes} (mode={mode})"
            )

        return out

    return _patch


def patch_delete_aipresetpool_pools(names: Tuple[str, ...]) -> Patcher:
    target = set(names)

    pool_pat = re.compile(
        r'^[ \t]*Pool\(\s*"(?P<name>[^"]+)"\s*\)\s*\{', flags=re.MULTILINE
    )

    def find_matching_brace(s: str, open_brace_index: int) -> int:

        depth = 0
        i = open_brace_index
        in_string = False
        escape = False
        in_line_comment = False

        while i < len(s):
            ch = s[i]

            # Handle line comments //
            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
                i += 1
                continue

            # Start on // comment
            if not in_string and ch == "/" and i + 1 < len(s) and s[i + 1] == "/":
                in_line_comment = True
                i += 2
                continue

            # Handling strings
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                i += 1
                continue
            else:
                if ch == '"':
                    in_string = True
                    i += 1
                    continue

            # Count braces
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i  # index  '}'

            i += 1

        raise Exception("Unbalanced braces while removing Pool block")

    def _patch(content: str) -> str:
        removed = 0

        # deleting one block at a time for safety
        while True:
            m = pool_pat.search(content)
            if not m:
                break

            name = m.group("name")
            if name not in target:

                content = content[: m.end()] + content[m.end() :]
                pass

            # finding first match as target
            found = None
            for mm in pool_pat.finditer(content):
                if mm.group("name") in target:
                    found = mm
                    break
            if not found:
                break

            start = found.start()
            open_brace_index = content.find("{", found.start())
            end_brace_index = find_matching_brace(content, open_brace_index)

            #
            end = end_brace_index + 1
            if end < len(content) and content[end : end + 1] == "\n":
                end += 1

            content = content[:start] + content[end:]
            removed += 1

        # Debug
        # print(f"[DBG] Removed {removed} Pool blocks: {sorted(target)}")

        return content

    return _patch


def patch_night_pursuit_caps(pool_to_cap: dict[str, int]) -> Patcher:
    def _patch(content: str) -> str:
        lines = content.splitlines(keepends=True)

        out: list[str] = []
        current_pool: str | None = None
        in_pool = False
        brace_depth = 0
        replaced_in_this_pool = False
        in_old_town = False

        pool_re = re.compile(r'^\s*Pool\(\s*"([^"]+)"\s*\)\s*$')
        cap_re = re.compile(r"^(\s*)MaxNoZombiesInPursuit\(\s*(\d+)\s*\)\s*$")
        allowed_ot_re = re.compile(r'AllowedMaps\s*\(\s*"Old_Town"\s*\)')

        for line in lines:
            # Detect pool start line: Pool("NAME")
            m = pool_re.match(line.strip())
            if m:
                current_pool = m.group(1)
                in_pool = False
                brace_depth = 0
                replaced_in_this_pool = False
                in_old_town = False
                out.append(line)
                continue

            if current_pool is not None:
                # Enter the pool block when we see the first "{"
                if not in_pool and "{" in line:
                    in_pool = True
                    brace_depth += line.count("{") - line.count("}")
                    out.append(line)
                    continue

                if in_pool:
                    if allowed_ot_re.search(line):
                        in_old_town = True
                    brace_depth += line.count("{") - line.count("}")

                    # Resolve key: Old Town pools use "Old_Town::PoolName"
                    lookup_key = (
                        f"Old_Town::{current_pool}"
                        if in_old_town and f"Old_Town::{current_pool}" in pool_to_cap
                        else current_pool
                    )

                    if lookup_key in pool_to_cap:
                        # Try to replace an existing cap line
                        mcap = cap_re.match(line.rstrip("\r\n"))
                        if mcap:
                            indent = mcap.group(1)
                            old_cap = int(mcap.group(2))
                            new_cap = int(pool_to_cap[lookup_key])

                            newline = "\r\n" if line.endswith("\r\n") else "\n"

                            # Skip rewrite when unchanged to avoid whitespace/newline diffs
                            if old_cap == new_cap:
                                out.append(line)
                            else:
                                out.append(f"{indent}MaxNoZombiesInPursuit({new_cap}){newline}")

                            replaced_in_this_pool = True
                            continue

                        # If we are about to close the pool and no cap was present, insert one
                        if brace_depth == 0 and line.strip().startswith("}"):
                            if not replaced_in_this_pool:
                                newline = "\r\n" if line.endswith("\r\n") else "\n"
                                indent = re.match(r"^(\s*)", line).group(1) + "    "
                                new_cap = int(pool_to_cap[lookup_key])
                                out.append(f"{indent}MaxNoZombiesInPursuit({new_cap}){newline}")

                            out.append(line)
                            current_pool = None
                            in_pool = False
                            continue

                    # Leaving pool (even if not patched)
                    if brace_depth == 0 and line.strip().startswith("}"):
                        out.append(line)
                        current_pool = None
                        in_pool = False
                        continue

            out.append(line)

        return "".join(out)

    return _patch



VO_MODES = {"vanilla", "pacify", "high_to_low", "high_to_default"}


def patch_volatiles(*, volatile_mode: str, alpha_mode: str) -> Patcher:
    if volatile_mode not in VO_MODES:
        raise ValueError(f"Unknown volatile_mode: {volatile_mode}")
    if alpha_mode not in VO_MODES:
        raise ValueError(f"Unknown alpha_mode: {alpha_mode}")

    # Match lines like: DefaultProfile("volatile_default");
    re_default = re.compile(r'^(\s*DefaultProfile\(")([^"]+)("\)\s*;?\s*)(.*)$')
    re_low = re.compile(r'^(\s*LowAlertProfile\(")([^"]+)("\)\s*;?\s*)(.*)$')
    re_high = re.compile(r'^(\s*HighAlertProfile\(")([^"]+)("\)\s*;?\s*)(.*)$')

    # Match start of a block: PerceptionProfile("volatile_default")
    re_block_start = re.compile(r'^\s*PerceptionProfile\("([^"]+)"\)\s*$')

    def apply_mode_to_block(block_lines: list[str], mode: str) -> tuple[list[str], int]:
        """
        Returns (new_block_lines, changed_count)
        Assumes re_default, re_low, re_high are compiled regexes that capture:
          group(1)=prefix before value, group(2)=value, group(3)=suffix after value, group(4)=comment/tail (if any)
        """
        if mode == "vanilla":
            return block_lines, 0
        if mode == "pacify":
            raise ValueError(
                "pacify is handled by delete patcher, not apply_mode_to_block"
            )

        default_val = None
        low_val = None

        # First pass: read Default/Low values
        for ln in block_lines:
            m = re_default.match(ln)
            if m:
                default_val = m.group(2)

            m = re_low.match(ln)
            if m:
                low_val = m.group(2)

        changed = 0
        new_lines: list[str] = []

        # Second pass: apply transform
        for ln in block_lines:
            m_high = re_high.match(ln)

            if mode == "high_to_low":
                if m_high and low_val is not None:
                    new_ln = (
                        f"{m_high.group(1)}{low_val}{m_high.group(3)}{m_high.group(4)}"
                    )
                    if new_ln != ln:
                        changed += 1
                    new_lines.append(new_ln)
                    continue

            elif mode == "high_to_default":
                if m_high and default_val is not None:
                    new_ln = f"{m_high.group(1)}{default_val}{m_high.group(3)}{m_high.group(4)}"
                    if new_ln != ln:
                        changed += 1
                    new_lines.append(new_ln)
                    continue

            else:
                raise ValueError(f"Unknown mode: {mode}")

            new_lines.append(ln)

        return new_lines, changed

    def _patch(content: str) -> str:
        lines = content.splitlines(keepends=True)

        out: list[str] = []
        changed_total = 0

        in_block = False
        current_name = ""
        block_buf: list[str] = []

        for ln in lines:
            if not in_block:
                m = re_block_start.match(ln.strip("\r\n"))
                if m:
                    in_block = True
                    current_name = m.group(1)
                    block_buf = [ln]
                else:
                    out.append(ln)
                continue

            # inside PerceptionProfile block
            block_buf.append(ln)

            # End of block: line with only "}"
            if ln.strip() == "}":
                in_block = False

                # Decide which mode to apply based on profile name
                mode = None
                if current_name.startswith("volatile_"):
                    mode = volatile_mode
                elif current_name.startswith("alpha_zombie_"):
                    mode = alpha_mode

                if mode and mode != "vanilla":
                    new_block, ch = apply_mode_to_block(block_buf, mode)
                    changed_total += ch
                    out.extend(new_block)
                else:
                    out.extend(block_buf)

                current_name = ""
                block_buf = []

        if in_block:
            out.extend(block_buf)

        if changed_total == 0 and (
            volatile_mode != "vanilla" or alpha_mode != "vanilla"
        ):
            raise Exception(
                "No PerceptionProfile values changed (pattern not found or already matching)."
            )

        return "".join(out)

    return _patch


def patch_restore_hunger_to_full(max_value: float = 1000.0) -> Patcher:
    """
    Sets HungerRespawnPercent to 1.0 (100%) so player gets full hunger on respawn/rest.
    Uses [ \\t]* for newline-safe Param matching.
    """

    def _patch(content: str) -> str:
        value_str = _fmt_num(1.0)  # 100% = full hunger on respawn
        param_to_set = "HungerRespawnPercent"

        # Newline-safe: use [ \t]* after );
        pat = re.compile(
            rf'(?m)^(\s*Param\("{re.escape(param_to_set)}"\s*,\s*")([^"]*)("\);[ \t]*)([\s\S]*)$'
        )
        m = pat.search(content)
        if not m:
            raise Exception(
                f'Param("{param_to_set}", ...) not found in player_variables template'
            )
        content = pat.sub(rf"\g<1>{value_str}\g<3>\g<4>", content, count=1)
        return content

    return _patch


def patch_player_variables_hunger_extras(
    *,
    decrease_speed: float,
    starving_threshold: float,
    resting_cost: float,
    revived_cost: float,
    mul_dash: float,
    mul_fury: float,
) -> Patcher:
    def _patch(content: str) -> str:
        repl = {
            "HungerPointsDecreaseSpeed": decrease_speed,
            "HungerStateStarvingThreshold": starving_threshold,
            "HungerRestingCost": resting_cost,
            "HungerRevivedCost": revived_cost,
            "HungerPointsDecreaseSpeedMulDash": mul_dash,
            "HungerPointsDecreaseSpeedMulFury": mul_fury,
        }

        for param, value in repl.items():
            # matchar: Param("Name", "123.45");
            pat = rf'Param\("{re.escape(param)}",\s*"[^"]*"\);'
            if not re.search(pat, content):
                raise Exception(f"{param} not found in player_variables template")
            content = re.sub(pat, f'Param("{param}", "{value}");', content)

        return content

    return _patch


def patch_hunger_buckets(
    *,
    cost_05: float,
    cost_10: float,
    cost_20: float,
    cost_30: float,
    cost_40: float,
) -> Patcher:
    mapping = {
        0.5: cost_05,
        1.0: cost_10,
        2.0: cost_20,
        3.0: cost_30,
        4.0: cost_40,
    }

    def _fmt_cost(x: float) -> str:
        s = f"{x:.3f}".rstrip("0").rstrip(".")
        if "." not in s:
            s += ".0"
        return s

    def _patch(content: str) -> str:
        out_lines = []
        changed = 0

        # ActionCost("Name", 3.0);  Use [ \t]* after ); to avoid \s* eating newlines
        pat = re.compile(
            r'^(\s*ActionCost\(\s*"([^"]+)"\s*,\s*)([+-]?\d*\.?\d+)(\);[ \t]*)([\s\S]*)$'
        )

        for line in content.splitlines(keepends=True):
            m = pat.match(line)
            if not m:
                out_lines.append(line)
                continue

            vanilla = float(m.group(3))

            # Leave all 0.0 untouched
            if abs(vanilla) < 1e-12:
                out_lines.append(line)
                continue

            bucket = None
            for k in mapping.keys():
                if abs(vanilla - k) < 1e-9:
                    bucket = k
                    break
            if bucket is None:
                out_lines.append(line)
                continue

            new_val = mapping[bucket]

            eol = (
                "\r\n"
                if line.endswith("\r\n")
                else ("\n" if line.endswith("\n") else "")
            )
            rest = m.group(5).rstrip("\r\n")

            newline = m.group(1) + _fmt_cost(new_val) + m.group(4) + rest + eol
            out_lines.append(newline)

            changed += 1

        if changed == 0:
            raise Exception(
                "No ActionCost(...) lines matched hunger buckets in template"
            )

        return "".join(out_lines)

    return _patch

def write_from_template(template_rel_path: str, out_path: str, patchers):
    template_path = resource_path(template_rel_path)  # <-- VIKTIGT

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    for p in patchers:
        content = p(content)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

def _fmt_num(x: float) -> str:
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    if s == "":
        s = "0"
    if "." not in s:
        s += ".0"
    return s


def patch_openworld_xp(multiplier: int) -> Patcher:
    def _patch(content: str) -> str:
        values = calc_openworld_params(multiplier)
        for param, value in values.items():
            content = _set_param_value(content, param, _fmt_num(float(value)))
        return content

    return _patch


def patch_legend_bonus(easy_normal: int, hard: int, nightmare: int) -> Patcher:
    def _patch(content: str) -> str:
        def replace(text: str, diff: str, value: float) -> str:
            pattern = rf'LegendBonus_Difficulty\("{diff}",\s*[0-9.]+\);'
            if not re.search(pattern, text):
                raise Exception(f"{diff} bonus not found in template")
            return re.sub(pattern, f'LegendBonus_Difficulty("{diff}", {value});', text)

        out = content
        out = replace(out, "Easy", easy_normal * 1.0)
        out = replace(out, "Normal", easy_normal * 1.0)
        out = replace(out, "Hard", hard * 1.05)
        out = replace(out, "Nightmare", nightmare * 1.15)
        return out

    return _patch


def patch_legend_bonus_penalty_game_defaults() -> Patcher:
    def _patch(content: str) -> str:
        mapping = {
            "Easy": 1.05,
            "Normal": 1.10,
            "Hard": 1.20,
            "VeryHard": 1.25,
            "Nightmare": 1.33,
            "Deadly": 0.0,
        }

        out_lines = []
        changed = 0

        for line in content.splitlines(keepends=True):
            m = re.match(
                r'^(\s*LegendBonus_Penalty\(\s*"([^"]+)"\s*,\s*)([^)]*)(\)\s*;\s*)(.*)$',
                line,
            )
            if m:
                diff = m.group(2)
                if diff in mapping:
                    line = (
                        m.group(1) + _fmt_num(mapping[diff]) + m.group(4) + m.group(5)
                    )
                    changed += 1
            out_lines.append(line)

        if changed == 0:
            raise Exception("No LegendBonus_Penalty(...) lines matched in template")
        return "".join(out_lines)

    return _patch


def patch_scale_death_penalty_levels(scale_percent: int) -> Patcher:
    factor = scale_percent / 100.0

    def _fmt(x: float) -> str:
        # matcha typ "0.015" utan massa skräp
        s = f"{x:.6f}".rstrip("0").rstrip(".")
        if "." not in s:
            s += ".0"
        return s

    def _patch(content: str) -> str:
        changed = 0

        for lvl in range(1, 15):
            name = f"DeathPenaltyXpLossPercentageLevel{lvl}"
            pat = rf'(Param\("{re.escape(name)}",\s*")([0-9]*\.?[0-9]+)("\)\s*;)'
            m = re.search(pat, content)
            if not m:
                raise Exception(f"{name} not found in player_variables template")

            base = float(m.group(2))
            new_val = base * factor

            content = re.sub(
                pat,
                lambda mm: mm.group(1) + _fmt(new_val) + mm.group(3),
                content,
                count=1,
            )
            changed += 1

        if changed != 14:
            raise Exception("Not all death penalty level params were scaled")

        return content

    return _patch


def patch_ll_xp_loss_scale(ll_percent: int) -> Patcher:
    def _patch(content: str) -> str:
        scale = ll_percent / 100.0

        vanilla_ll = float(_get_param_value(content, "LLDeathPenaltyXpLossPercentage"))
        new_val = vanilla_ll * scale
        print(
            "[DBG] LL template vanilla =",
            vanilla_ll,
            "scale=",
            ll_percent,
            "new=",
            new_val,
        )

        content = _set_param_value(
            content,
            "LLDeathPenaltyXpLossPercentage",
            _fmt_num(new_val),
        )
        return content

    return _patch


def _get_param_value(content: str, name: str) -> str:
    m = re.search(rf'Param\("{re.escape(name)}",\s*"([^"]+)"\);', content)
    if not m:
        raise Exception(f"{name} not found")
    return m.group(1)


def patch_absolute_xp_loss_split(normal_percent: int, ll_percent: int) -> Patcher:
    def _patch(content: str) -> str:
        return apply_absolute_xp_loss_split(content, normal_percent, ll_percent)

    return _patch


def patch_legend_bonus_penalty_universal(value: float) -> Patcher:
    def _patch(content: str) -> str:
        s = f"{value:.3f}".rstrip("0").rstrip(".") or "0.0"

        changed = 0
        out_lines = []

        for line in content.splitlines(keepends=True):
            m = re.match(
                r'^(\s*LegendBonus_Penalty\("([^"]+)"\s*,\s*)([^)]*)(\)\s*;\s*)(.*)$',
                line,
            )
            if m:
                # m.group(2) is the diff name (Easy/Normal/etc)
                line = m.group(1) + s + m.group(4) + m.group(5)
                changed += 1
            out_lines.append(line)

        if changed == 0:
            raise Exception(
                'No LegendBonus_Penalty("...", ...) lines matched in template'
            )

        return "".join(out_lines)

    return _patch


def patch_coop_multiplier(value: float) -> Patcher:
    def _patch(content: str) -> str:
        s = f"{value:.3f}".rstrip("0").rstrip(".")
        s = s if "." in s else s + ".0"

        changed = 0
        out_lines = []

        for line in content.splitlines(keepends=True):
            m = re.match(
                r"^(\s*LegendBonus_Coop\(\s*(2|3|4)\s*,\s*)([^)]*)(\)\s*;\s*)([\s\S]*)$",
                line,
            )
            if m:
                line = m.group(1) + s + m.group(4) + m.group(5)
                changed += 1
            out_lines.append(line)

        if changed == 0:
            raise Exception("No LegendBonus_Coop(2/3/4, ...) lines matched in template")

        return "".join(out_lines)

    return _patch


def patch_ngplus_multiplier(value: float) -> Patcher:
    def _patch(content: str) -> str:
        s = f"{value:.3f}".rstrip("0").rstrip(".") or "0.0"

        pattern = r"(^\s*LegendBonus_NGPlus\()([0-9]*\.?[0-9]+)(\);\s*)"
        if not re.search(pattern, content, flags=re.MULTILINE):
            raise Exception("LegendBonus_NGPlus(...) not found in template")

        return re.sub(
            pattern, r"\g<1>" + s + r"\g<3>", content, count=1, flags=re.MULTILINE
        )

    return _patch


def _replace_numeric_call(block: str, func: str, value: float) -> str:
    pat = rf"(^\s*{re.escape(func)}\()\s*([+-]?\d*\.?\d+)\s*(\);[ \t]*)([\s\S]*)$"
    if not re.search(pat, block, flags=re.MULTILINE):
        raise Exception(f"{func}(...) not found inside preset block")
    return re.sub(
        pat,
        r"\g<1>" + _fmt_num(value) + r"\g<3>\g<4>",
        block,
        count=1,
        flags=re.MULTILINE,
    )


def patch_uv_preset_3vals(
    preset_name: str,
    *,
    drain: float,
    max_energy: float,
    regen_delay: float,
) -> Patcher:
    def _patch(content: str) -> str:
        header_pat = rf'(^\s*FlashlightPreset\("{re.escape(preset_name)}"\);\s*)'
        block_pat = header_pat + r"(.*?)(?=^\s*FlashlightPreset\(\"|\Z)"

        m = re.search(block_pat, content, flags=re.MULTILINE | re.DOTALL)
        if not m:
            raise Exception(f'FlashlightPreset("{preset_name}") not found')

        header = m.group(1)
        block = m.group(2)

        block = _replace_numeric_call(block, "EnergyDrainPerSecond", drain)
        block = _replace_numeric_call(block, "MaxEnergy", max_energy)
        block = _replace_numeric_call(block, "RegenerationDelay", regen_delay)

        new_chunk = header + block
        return re.sub(
            block_pat, new_chunk, content, count=1, flags=re.MULTILINE | re.DOTALL
        )

    return _patch


def patch_uv_levels_grouped(
    *,
    lvl12_drain: float,
    lvl12_energy: float,
    lvl12_regen: float,
    lvl3_drain: float,
    lvl3_energy: float,
    lvl3_regen: float,
    lvl4_drain: float,
    lvl4_energy: float,
    lvl4_regen: float,
    lvl5_drain: float,
    lvl5_energy: float,
    lvl5_regen: float,
) -> list[Patcher]:
    return [
        patch_uv_preset_3vals(
            "Player Flashlight UV LVL 1",
            drain=lvl12_drain,
            max_energy=lvl12_energy,
            regen_delay=lvl12_regen,
        ),
        patch_uv_preset_3vals(
            "Player Flashlight UV LVL 2",
            drain=lvl12_drain,
            max_energy=lvl12_energy,
            regen_delay=lvl12_regen,
        ),
        patch_uv_preset_3vals(
            "Player Flashlight UV LVL 3",
            drain=lvl3_drain,
            max_energy=lvl3_energy,
            regen_delay=lvl3_regen,
        ),
        patch_uv_preset_3vals(
            "Player Flashlight UV LVL 4",
            drain=lvl4_drain,
            max_energy=lvl4_energy,
            regen_delay=lvl4_regen,
        ),
        patch_uv_preset_3vals(
            "Player Flashlight UV LVL 5",
            drain=lvl5_drain,
            max_energy=lvl5_energy,
            regen_delay=lvl5_regen,
        ),
    ]


def patch_varvec3(var_name: str, r: float, g: float, b: float) -> Patcher:
    def _patch(content: str) -> str:
        s = f"[{r:.3f}, {g:.3f}, {b:.3f}]"
        # match: VarVec3("v_flashlight_pp_uv_color"
        pat = rf'(^\s*VarVec3\(\s*"{re.escape(var_name)}"\s*,\s*)\[[^\]]*\](\s*\).*$)'
        if not re.search(pat, content, flags=re.MULTILINE):
            raise Exception(f'VarVec3("{var_name}", ...) not found in template')
        return re.sub(pat, r"\g<1>" + s + r"\g<2>", content, flags=re.MULTILINE)

    return _patch


def _set_toggle_call(block: str, func: str, enabled: bool) -> str:
    pattern_any = rf"(^\s*)(//\s*)?({re.escape(func)}\(\);\s*)(.*)$"
    m = re.search(pattern_any, block, flags=re.MULTILINE)

    if m:
        indent = m.group(1)
        tail = m.group(4)
        line = f"{func}();" if enabled else f"//{func}();"
        repl = indent + line + tail
        return re.sub(pattern_any, repl, block, count=1, flags=re.MULTILINE)

    insert_after = r"(^\s*)(MaxEnergy\([+-]?\d*\.?\d+\);\s*)(.*)$"
    m2 = re.search(insert_after, block, flags=re.MULTILINE)
    if m2:
        indent = m2.group(1)
        line = f"{func}();" if enabled else f"//{func}();"
        insert_line = indent + line + "\n"
        return re.sub(
            insert_after,
            r"\g<1>\g<2>\g<3>\n" + insert_line,
            block,
            count=1,
            flags=re.MULTILINE,
        )

    # fallback
    line = f"{func}();" if enabled else f"//{func}();"
    return line + "\n" + block


def patch_flashlight_preset(
    preset_name: str,
    *,
    drain_per_second: float,
    max_energy: float,
    regen_delay: float,
    regen_delay_vanilla: float | None = None,
) -> Patcher:
    def _patch(content: str) -> str:
        header_pat = rf'(^\s*FlashlightPreset\("{re.escape(preset_name)}"\);\s*)'
        block_pat = header_pat + r'(.*?)(?=^\s*FlashlightPreset\("|\Z)'

        m = re.search(block_pat, content, flags=re.MULTILINE | re.DOTALL)
        if not m:
            raise Exception(f'FlashlightPreset("{preset_name}") not found')

        header = m.group(1)
        block = m.group(2)

        block = _replace_numeric_call(block, "EnergyDrainPerSecond", drain_per_second)
        block = _replace_numeric_call(block, "MaxEnergy", max_energy)
        if regen_delay_vanilla is None or abs(regen_delay - regen_delay_vanilla) > 1e-9:
            block = _replace_numeric_call(block, "RegenerationDelay", regen_delay)

        new_chunk = header + block
        return re.sub(
            block_pat,
            new_chunk,
            content,
            count=1,
            flags=re.MULTILINE | re.DOTALL,
        )

    return _patch


FLASHLIGHT_PRESET_BY_LEVEL = {
    1: "Player Flashlight UV LVL 1",
    2: "Player Flashlight UV LVL 2",
    3: "Player Flashlight UV LVL 3",
    4: "Player Flashlight UV LVL 4",
    5: "Player Flashlight UV LVL 5",
}


def _replace_numeric_call(block: str, func: str, value: float) -> str:
    """
    Replaces lines like:
        EnergyDrainPerSecond(0.75);  /// comment
    Keeps indentation and trailing comments.
    Uses [ \\t]* after ');' to avoid eating newlines.
    """
    pattern = rf"(^\s*{re.escape(func)}\()\s*([+-]?\d*\.?\d+)\s*(\);[ \t]*)([\s\S]*)$"
    if not re.search(pattern, block, flags=re.MULTILINE):
        raise Exception(f"{func}(...) not found inside preset block")
    return re.sub(
        pattern,
        r"\g<1>" + _fmt_num(value) + r"\g<3>\g<4>",
        block,
        count=1,
        flags=re.MULTILINE,
    )


def _set_toggle_call(block: str, func: str, enabled: bool) -> str:
    pattern_any = rf"(^\s*)(//\s*)?({re.escape(func)}\(\);\s*)(.*)$"
    m = re.search(pattern_any, block, flags=re.MULTILINE)

    if m:
        indent = m.group(1)
        tail = m.group(4)
        line = f"{func}();" if enabled else f"//{func}();"
        repl = indent + line + tail
        return re.sub(pattern_any, repl, block, count=1, flags=re.MULTILINE)

    insert_after = r"(^\s*)(MaxEnergy\([+-]?\d*\.?\d+\);\s*)(.*)$"
    m2 = re.search(insert_after, block, flags=re.MULTILINE)
    if m2:
        indent = m2.group(1)
        line = f"{func}();" if enabled else f"//{func}();"
        insert_line = indent + line + "\n"
        return re.sub(
            insert_after,
            r"\g<1>\g<2>\g<3>\n" + insert_line,
            block,
            count=1,
            flags=re.MULTILINE,
        )

    # fallback
    line = f"{func}();" if enabled else f"//{func}();"
    return line + "\n" + block


# Vanilla RegenerationDelay per UV level
FL_REGEN_VANILLA_UV1 = 3.0
FL_REGEN_VANILLA_UV2 = 2.5


def patch_flashlight_grouped(
    *,
    lvl1: FlashlightParams,
    lvl2: FlashlightParams,
    lvl3: FlashlightParams,
    lvl4: FlashlightParams,
    lvl5: FlashlightParams,
) -> List[Patcher]:
    patchers: List[Patcher] = []

    def add(level: int, p: FlashlightParams, regen_vanilla: float | None = None):
        patchers.append(
            patch_flashlight_preset(
                FLASHLIGHT_PRESET_BY_LEVEL[level],
                drain_per_second=p.drain_per_second,
                max_energy=p.max_energy,
                regen_delay=p.regen_delay,
                regen_delay_vanilla=regen_vanilla,
            )
        )

    add(1, lvl1, regen_vanilla=FL_REGEN_VANILLA_UV1)
    add(2, lvl2, regen_vanilla=FL_REGEN_VANILLA_UV2)

    # separate
    add(3, lvl3)
    add(4, lvl4)
    add(5, lvl5)

    return patchers


def calc_openworld_params(xp_multiplier):
    return {
        "OpenWorldXPModifier": xp_multiplier,
        "OpenWorldNightXPModifier": xp_multiplier,
        "VehicleKillXPMultiplier": round(xp_multiplier * 0.05, 2),
    }

def write_inputs_keyboard(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/inputs_keyboard.scr",
        "scripts/inputs/inputs_keyboard.scr",
        patchers,
    )


def write_fuel_params(template_path: str, out_path: str, patchers: List[Patcher]) -> None:
    write_from_template(template_path, out_path, patchers)


def write_player_variables(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/player_variables.scr",
        "scripts/player/player_variables.scr",
        patchers,
    )
    
def write_player_hunger_config(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/player_hunger_config.scr",
        "scripts/player/player_hunger_config.scr",
        patchers,
    )


def write_player_volatiles_config(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/ai_perception_profiles.scr",
        "scripts/ai/ai_perception_profiles.scr",
        patchers,
    )


def write_aipresetpool_config(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/aipresetpool.scr",
        "scripts/aipresetpool.scr",
        patchers,
    )


def write_player_nightspawn_config(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/night_spawn_pools.scr",
        "scripts/nightaggression/night_spawn_pools.scr",
        patchers,
    )


def write_ai_difficulty_modifiers(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/ai_difficulty_modifiers.scr",
        "scripts//ai/ai_difficulty_modifiers.scr",
        patchers,
    )


def write_ai_spawn_priority_system(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/ai_spawn_priority_system.scr",
        "scripts/ai/ai_spawn_priority_system.scr",
        patchers,
    )


def write_ai_spawn_system_params(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/ai_spawn_system_params.scr",
        "scripts/ai/ai_spawn_system_params.scr",
        patchers,
    )


def write_common_dynamic_spawn_logic(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/common_dynamic_spawn_logic_params.def",
        "scripts/spawn/common_dynamic_spawn_logic_params.def",
        patchers,
    )


def write_progression_actions(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/progressionactions.scr",
        "scripts/progression/progressionactions.scr",
        patchers,
    )


# INVENTORY FLASHLIGHT
def write_inventory_special(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/inventory_special.scr",
        "scripts/inventory/inventory_special.scr",
        patchers,
    )


def write_varlist_game_overlay(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/varlist_game_overlay.scr",
        "scripts/varlist_game_overlay.scr",
        patchers,
    )
    
def _set_value_any_syntax(content: str, name: str, new_val: str) -> str:
    # 1) Param("Name", "123");
    pat_param = re.compile(
        rf'^(\s*Param\(\s*"{re.escape(name)}"\s*,\s*")([0-9.]+)("(\s*\)\s*;?\s*)$)',
        re.M
    )
    out = pat_param.sub(rf'\1{new_val}\3', content)

    # 2) Name("123");  (or without ;)
    pat_call = re.compile(
        rf'^(\s*{re.escape(name)}\(\s*")([0-9.]+)("(\s*\)\s*;?\s*)$)',
        re.M
    )
    out2 = pat_call.sub(rf'\1{new_val}\3', out)
    return out2

def patch_global_densities_scaled_by_aidensity(ai_density: int) -> Patcher:
    """Patch densitiessettings.scr: scale Densities(Day)/Densities(Night) by AIDensityMaxAIsInSpawnArea.
    When ai_density <= AI_DEFAULT (63), strict no-op (0 diffs). At >=600 use max preset."""
    AI_DEFAULT = 63
    AI_MAX = 600

    # Vanilla → Max tables (min, max) per difficulty
    DAY_VAN = {"None": (0, 0), "Easy": (14, 16), "Medium": (14, 16), "VeryHard": (85, 90)}
    DAY_MAX = {"None": (50, 100), "Easy": (100, 200), "Medium": (100, 200), "VeryHard": (125, 250)}
    NIGHT_VAN = {"None": (0, 0), "Easy": (35, 40), "Medium": (50, 55), "Hard": (90, 95), "VeryHard": (100, 110)}
    NIGHT_MAX = {"None": (50, 100), "Easy": (100, 200), "Medium": (100, 200), "Hard": (100, 200), "VeryHard": (125, 250)}

    t = (ai_density - AI_DEFAULT) / (AI_MAX - AI_DEFAULT)
    t = max(0.0, min(1.0, t))

    def _scale(v_min: int, v_max: int, m_min: int, m_max: int) -> tuple[int, int]:
        n_min = round(v_min + t * (m_min - v_min))
        n_max = round(v_max + t * (m_max - v_max))
        if n_max < n_min:
            n_max = n_min
        return (n_min, n_max)

    def _patch(content: str) -> str:
        if t <= 0.0:
            return content  # strict no-op

        # Match the Densities(Day)..Densities(Night) block (commented)
        block_pattern = re.compile(
            r"(/\*)(Densities\(Day\)\s*\{\s*)(.*?)(\}\s*Densities\(Night\)\s*\{\s*)(.*?)(\}\s*)(\*/)",
            re.DOTALL,
        )
        m = block_pattern.search(content)
        if not m:
            raise Exception("Densities(Day)/Densities(Night) block not found in densitiessettings template")

        def _process_block(block: str, van: dict, max_vals: dict) -> str:
            out_lines: list[str] = []
            for line in block.splitlines(keepends=True):
                # Match Difficulty(min, max); or Difficulty(min, max) ; with optional spaces
                dm = re.match(r"^(\s*)(\w+)\((\d+)\s*,\s*(\d+)\)(\s*;?\s*)(.*)$", line)
                if dm and dm.group(2) in van:
                    prefix, diff, cur_min, cur_max, suffix, rest = dm.group(1, 2, 3, 4, 5, 6)
                    v_min, v_max = van[diff]
                    m_min, m_max = max_vals[diff]
                    new_min, new_max = _scale(v_min, v_max, m_min, m_max)
                    if new_min == int(cur_min) and new_max == int(cur_max):
                        out_lines.append(line)  # keep original to avoid diff
                    else:
                        out_lines.append(f"{prefix}{diff}({new_min}, {new_max}){suffix}{rest}")
                else:
                    out_lines.append(line)
            return "".join(out_lines)

        day_block = _process_block(m.group(3), DAY_VAN, DAY_MAX)
        night_block = _process_block(m.group(5), NIGHT_VAN, NIGHT_MAX)

        # Replace comment with uncommented block (no /* and */)
        replacement = m.group(2) + day_block + m.group(4) + night_block + m.group(6)
        return content[: m.start()] + replacement + content[m.end() :]

    return _patch


def write_densitiessettings(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/densitiessettings.scr",
        "scripts/densitiessettings.scr",
        patchers,
    )


def patch_volatile_health_multipliers(
    *,
    volatile_pct: int,
    hive_pct: int,
    apex_pct: int,
) -> Patcher:
    """Patch healthdefinitions.scr: scale Volatile/Hive/Apex health values by percent.
    Strict no-op when all pct == 100."""
    if volatile_pct == 100 and hive_pct == 100 and apex_pct == 100:
        return lambda c: c  # strict no-op

    def _mult_for(name: str) -> float | None:
        if name.startswith("Volatile_Hive_"):
            return hive_pct / 100.0 if hive_pct != 100 else None
        if name.startswith("Volatile_Apex_") or name.startswith("Volatile_Alpha_"):
            return apex_pct / 100.0 if apex_pct != 100 else None
        if name.startswith("Volatile_Tyrant_"):
            return apex_pct / 100.0 if apex_pct != 100 else None
        if name == "Volatile" or name.startswith("Volatile_"):
            return volatile_pct / 100.0 if volatile_pct != 100 else None
        return None

    def _scale_val(val_str: str, factor: float) -> str | None:
        """Parse VALUE, apply factor, return new string or None if not numeric."""
        val_str = val_str.strip()
        if "-" in val_str and not val_str.startswith("-"):
            parts = val_str.split("-", 1)
            try:
                lo, hi = int(parts[0].strip()), int(parts[1].strip())
                if lo > hi:
                    lo, hi = hi, lo
                n_lo = max(1, round(lo * factor))
                n_hi = max(1, round(hi * factor))
                if n_hi < n_lo:
                    n_hi = n_lo
                return f"{n_lo}-{n_hi}"
            except ValueError:
                return None
        try:
            v = int(float(val_str))
            n = max(1, round(v * factor))
            return str(n)
        except ValueError:
            return None

    def _patch(content: str) -> str:
        # Match Health("NAME") { blocks only; exclude inner Health("VALUE");
        block_pat = re.compile(
            r'[ \t]+Health\("([^"]+)"\)(?!\s*;)[^{]*\{', re.MULTILINE
        )
        result = []
        pos = 0
        for m in block_pat.finditer(content):
            name = m.group(1)
            factor = _mult_for(name)
            if factor is None:
                continue
            result.append(content[pos : m.start()])
            brace = content.find("{", m.start())
            depth = 1
            i = brace + 1
            while i < len(content) and depth > 0:
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                i += 1
            block = content[brace + 1 : i - 1]
            inner_pat = re.compile(r'Health\("([^"]*)"\)')
            def repl(mo: re.Match) -> str:
                s = _scale_val(mo.group(1), factor)
                return f'Health("{s}")' if s is not None else mo.group(0)
            new_block = inner_pat.sub(repl, block)
            result.append(content[m.start() : brace + 1])
            result.append(new_block)
            result.append("}")
            pos = i
        result.append(content[pos:])
        return "".join(result)

    return _patch


def patch_vehicle_health(
    *,
    vehicle_pickup_pct: int,
    vehicle_pickup_ctb_pct: int,
) -> Patcher:
    """Patch healthdefinitions.scr: scale Vehicle_Pickup and Vehicle_Pickup_CTB health.
    Defaults: Vehicle_Pickup 1150, Vehicle_Pickup_CTB 2000. 100% = strict no-op."""
    if vehicle_pickup_pct == 100 and vehicle_pickup_ctb_pct == 100:
        return lambda c: c

    VANILLA = {"Vehicle_Pickup": 1150, "Vehicle_Pickup_CTB": 2000}

    def _patch(content: str) -> str:
        block_pat = re.compile(
            r'[ \t]+Health\("([^"]+)"\)(?!\s*;)[^{]*\{', re.MULTILINE
        )
        result = []
        pos = 0
        for m in block_pat.finditer(content):
            name = m.group(1)
            if name not in VANILLA:
                continue
            pct = vehicle_pickup_pct if name == "Vehicle_Pickup" else vehicle_pickup_ctb_pct
            if pct == 100:
                continue
            factor = pct / 100.0
            vanilla = VANILLA[name]
            new_val = max(1, round(vanilla * factor))
            result.append(content[pos : m.start()])
            brace = content.find("{", m.start())
            depth = 1
            i = brace + 1
            while i < len(content) and depth > 0:
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                i += 1
            block = content[brace + 1 : i - 1]
            block = re.sub(
                r'Health\("([^"]*)"\)',
                lambda mo: f'Health("{new_val}")' if mo.group(1).strip().isdigit() else mo.group(0),
                block,
            )
            result.append(content[m.start() : brace + 1])
            result.append(block)
            result.append("}")
            pos = i
        result.append(content[pos:])
        return "".join(result)

    return _patch


def write_healthdefinitions(patchers: List[Patcher]) -> None:
    write_from_template(
        "templates/healthdefinitions.scr",
        "scripts/healthdefinitions.scr",
        patchers,
    )


def _scale_param_value(
    content: str, param_name: str, factor: float, decimals: int = 6
) -> str:
    # matching even if there is spaces
    pattern = rf'(^\s*Param\("{re.escape(param_name)}",\s*")([+-]?\d*\.?\d+)("\);\s*)'
    m = re.search(pattern, content, flags=re.MULTILINE)
    if not m:
        raise Exception(f"{param_name} not found in template")

    vanilla = float(m.group(2))
    new_val = vanilla * factor

    # Important : zero is 0.0
    if abs(new_val) < 1e-12:
        new_str = "0.0"
    else:
        new_str = f"{new_val:.{decimals}f}".rstrip("0").rstrip(".")
        if new_str == "":
            new_str = "0.0"

    return re.sub(
        pattern, r"\g<1>" + new_str + r"\g<3>", content, count=1, flags=re.MULTILINE
    )


def _set_param_value(content: str, name: str, value_str: str) -> str:
    # Matchar exakt en rad av formen:
    # Param("Name", "123.45");
    pat = re.compile(
        rf'(?m)^(\s*Param\("{re.escape(name)}"\s*,\s*")([^"]*)("\)\s*;\s*)$'
    )

    if not pat.search(content):
        raise Exception(f"{name} not found in player_variables template")

    # Byt bara första träffen (ska bara finnas en)
    new_content, n = pat.subn(rf"\g<1>{value_str}\g<3>", content, count=1)
    if n != 1:
        raise Exception(f"{name} replaced {n} times (expected 1)")

    return new_content


def apply_normal_xp_loss_percent(content: str, percent: int) -> str:
    factor = percent / 100.0

    for level in range(1, 15):
        content = _scale_param_value(
            content, f"DeathPenaltyXpLossPercentageLevel{level}", factor
        )

    content = _scale_param_value(content, "DeathPenaltyXpLossMultiplierDay", factor)
    content = _scale_param_value(content, "DeathPenaltyXpLossMultiplierNight", factor)
    return content


def apply_ll_xp_loss_percent(content: str, percent: int) -> str:
    factor = percent / 100.0

    content = _scale_param_value(content, "LLDeathPenaltyXpLossPercentage", factor)
    content = _scale_param_value(content, "LLDeathPenaltyXpLossMultiplierDay", factor)
    content = _scale_param_value(content, "LLDeathPenaltyXpLossMultiplierNight", factor)
    return content


def _scale_param_preserve_line(
    content: str, param_name: str, factor: float, decimals: int = 3
) -> str:
    """
    Scale a Param value by factor, preserve rest of line (comments, newline).
    Returns content unchanged if new value equals old (float tolerance).
    Formats: round to decimals, at least one decimal digit (e.g. 5.0).
    """
    pattern = re.compile(
        rf'(?m)^(\s*Param\("{re.escape(param_name)}",\s*")([+-]?\d*\.?\d+)("\)\s*;)([^\r\n]*[\r\n]?)'
    )
    m = pattern.search(content)
    if not m:
        return content
    prefix, val_str, close, tail = m.groups()
    old_val = float(val_str)
    new_val = round(old_val * factor, decimals)
    if abs(new_val - old_val) < 1e-9:
        return content
    s = f"{new_val:.{decimals}f}".rstrip("0").rstrip(".")
    if not s or "." not in s:
        s = (s or "0") + ".0"
    new_content = content[: m.start()] + prefix + s + close + tail + content[m.end() :]
    return new_content


def patch_player_movement_speed(
    *,
    water_pct: int,
    land_pct: int,
    boost_pct: int,
) -> Patcher:
    """Scale movement Params in player_variables.scr. No-op if all 0."""
    if water_pct == 0 and land_pct == 0 and boost_pct == 0:
        return lambda c: c

    water_factor = 1.0 + water_pct / 100.0
    land_factor = 1.0 + land_pct / 100.0
    boost_factor = 1.0 + boost_pct / 100.0

    water_params = (
        "WaterMovementSpeedMulLevel1",
        "WaterMovementSpeedMulLevel2",
        "WaterMovementSpeedMulLevel3",
    )
    land_params = (
        "MoveForwardMaxSpeed",
        "MoveBackwardMaxSpeed",
        "MoveStrafeMaxSpeed",
        "MoveSprintSpeed",
    )
    boost_params = ("AfterBoostDefaultSpeed", "AfterBoostMaxSpeed")

    def _patch(content: str) -> str:
        for p in water_params:
            content = _scale_param_preserve_line(content, p, water_factor)
        for p in land_params:
            content = _scale_param_preserve_line(content, p, land_factor)
        for p in boost_params:
            content = _scale_param_preserve_line(content, p, boost_factor)
        return content

    return _patch


def _replace_param_in_block(block_content: str, param_name: str, new_val: str) -> str:
    """Replace Param("param_name", "old") with Param("param_name", "new_val") in block. Preserve line."""
    pat = re.compile(
        rf'(^\s*Param\("{re.escape(param_name)}",\s*")([^"]*)("\)\s*;[^\r\n]*[\r\n]?)',
        re.MULTILINE,
    )
    m = pat.search(block_content)
    if not m:
        return block_content
    prefix, _, close_tail = m.groups()
    return block_content[: m.start()] + prefix + new_val + close_tail + block_content[m.end() :]


def _replace_custom_pool_limit(content: str, pool_name: str, new_limit: str) -> str:
    """Replace Limit("N") inside CustomPool("pool_name") block."""
    escaped = re.escape(pool_name)
    pat = re.compile(
        r'(CustomPool\("' + escaped + r'"\)\s*\{[\s\S]*?Limit\(")(\d+)("\)\s*[;\s]*)'
    )
    m = pat.search(content)
    if not m:
        return content
    return content[: m.start(2)] + new_limit + content[m.end(2) :]


def _replace_spawn_source_limit(content: str, source_name: str, new_limit: str) -> str:
    """Replace Limit("N") inside SpawnSourceParams("source_name") block."""
    escaped = re.escape(source_name)
    pat = re.compile(
        r'(SpawnSourceParams\("' + escaped + r'"\)\s*\{[\s\S]*?Limit\(")(\d+)("\)\s*;)'
    )
    m = pat.search(content)
    if not m:
        return content
    return content[: m.start(2)] + new_limit + content[m.end(2) :]


def patch_ai_spawn_system(
    *,
    max_spawned_ai: int,
    auto_cache: bool,
    manual_cache: int,
    dialog_limit: int,
    chase_limit: int,
    advanced_limits: bool = False,
    agenda_limit: int = 60,
    spawner_limit: int = 120,
    dynamic_limit: int = 120,
    challenge_limit: int = 10,
    gameplay_limit: int = 10,
    aiproxy_limit: int = 120,
    story_limit: int = 60,
    boost_darkzones: bool = False,
) -> Patcher:
    """
    Patch ai_spawn_system_params.scr. Strict no-op when all vanilla.
    Vanilla: max_spawned_ai=80, dialog=50, chase=15. When auto, spawn=80->cache=200.
    """
    if (
        max_spawned_ai == 80
        and dialog_limit == 50
        and chase_limit == 15
        and not advanced_limits
        and not boost_darkzones
    ):
        if auto_cache:
            return lambda c: c  # spawn 80 -> cache 200
        if manual_cache == 200:
            return lambda c: c  # don't touch, vanilla
    debug_limit = dialog_limit * 2
    if auto_cache:
        cache = max(200, round(200 + (max_spawned_ai - 80) * 1300 / 720))
    else:
        cache = max(200, min(2400, manual_cache))
    per_frame = 1 if max_spawned_ai <= 80 else min(2, max(1, round(1 + (max_spawned_ai - 80) / 720)))

    def _patch(content: str) -> str:
        block = _extract_sub_block(content, "AISpawnSystemGlobalParams")
        if not block:
            return content
        start, end = block
        before = content[:start]
        block_content = content[start:end]
        after = content[end:]

        block_content = _replace_param_in_block(block_content, "MaxSpawnedAI", str(max_spawned_ai))
        block_content = _replace_param_in_block(block_content, "MaxSpawnedAIImpassableLimit", str(max_spawned_ai))
        block_content = _replace_param_in_block(block_content, "MaxSpawnedAIPerFrame", str(per_frame))
        if cache is not None:
            block_content = _replace_param_in_block(block_content, "MaxSizeOfAICache", str(cache))

        content = before + block_content + after
        content = _replace_spawn_source_limit(content, "Debug", str(debug_limit))
        content = _replace_spawn_source_limit(content, "Dialog", str(dialog_limit))
        content = _replace_spawn_source_limit(content, "Chase", str(min(100, chase_limit)))
        if advanced_limits:
            content = _replace_spawn_source_limit(content, "Agenda", str(agenda_limit))
            content = _replace_spawn_source_limit(content, "Spawner", str(spawner_limit))
            content = _replace_spawn_source_limit(content, "DynamicSpawner", str(dynamic_limit))
            content = _replace_spawn_source_limit(content, "Challenge", str(challenge_limit))
            content = _replace_spawn_source_limit(content, "GameplayForced", str(gameplay_limit))
            content = _replace_spawn_source_limit(content, "AIProxy", str(aiproxy_limit))
            content = _replace_spawn_source_limit(content, "StorySpawner", str(story_limit))
        if boost_darkzones:
            content = _replace_custom_pool_limit(content, "DarkzoneNight", "85")
            content = _replace_custom_pool_limit(content, "DarkzoneDay", "100")
        return content

    return _patch


def patch_player_climb_options(
    *, ladder_climb_slow: bool, fast_climb_enabled: bool
) -> Patcher:
    """Set LadderClimbSlow and FastClimbEnabled in player_variables.scr. No-op when both unchecked (vanilla)."""
    if not ladder_climb_slow and not fast_climb_enabled:
        return lambda c: c

    ladder_val = "false" if ladder_climb_slow else "true"
    fast_val = "true" if fast_climb_enabled else "false"

    def _patch(content: str) -> str:
        out = _set_param_value(content, "LadderClimbSlow", ladder_val)
        out = _set_param_value(out, "FastClimbEnabled", fast_val)
        return out

    return _patch


def patch_legendpoints_quest(value: float) -> Patcher:
    def _patch(content: str) -> str:
        s = f"{value:.3f}".rstrip("0").rstrip(".") or "0.0"
        if "." not in s:
            s = s + ".0"

        # 1) LegendPoints_Quest(1.0);
        pat1 = r"(^\s*LegendPoints_Quest\()([0-9]*\.?[0-9]+)(\);\s*)(.*)$"
        if not re.search(pat1, content, flags=re.MULTILINE):
            raise Exception("LegendPoints_Quest(...) not found in template")

        content = re.sub(
            pat1, r"\g<1>" + s + r"\g<3>\g<4>", content, flags=re.MULTILINE
        )

        # 2) LegendPoint_Quest_Category("ReplayableGREAnomaly", 1.0);
        pat2 = r'(^\s*LegendPoint_Quest_Category\(\s*"ReplayableGREAnomaly"\s*,\s*)([0-9]*\.?[0-9]+)(\);\s*)(.*)$'
        if not re.search(pat2, content, flags=re.MULTILINE):
            raise Exception(
                'LegendPoint_Quest_Category("ReplayableGREAnomaly", ...) not found in template'
            )

        content = re.sub(
            pat2, r"\g<1>" + s + r"\g<3>\g<4>", content, flags=re.MULTILINE
        )

        return content

    return _patch


def patch_param_value_optional(param_name: str, value_str: str) -> Patcher:
    """
    Like patch_param_value, but does NOT raise if param doesn't exist in this file.
    Useful when some params only exist in certain templates.
    """

    def _patch(content: str) -> str:
        pattern = rf'(^\s*Param\("{re.escape(param_name)}",\s*")([^"]*)("\);\s*)(.*)$'
        if not re.search(pattern, content, flags=re.MULTILINE):
            return content

        return re.sub(
            pattern,
            r"\g<1>" + value_str + r"\g<3>\g<4>",
            content,
            count=1,
            flags=re.MULTILINE,
        )

    return _patch


def patch_varvec3(name: str, r: float, g: float, b: float) -> Patcher:
    def _patch(content: str) -> str:
        rr = f"{r:.3f}".rstrip("0").rstrip(".") or "0.0"
        gg = f"{g:.3f}".rstrip("0").rstrip(".") or "0.0"
        bb = f"{b:.3f}".rstrip("0").rstrip(".") or "0.0"

        pattern = rf'(^\s*VarVec3\("{re.escape(name)}",\s*\[)([^\]]+)(\]\)\s*.*$)'
        if not re.search(pattern, content, flags=re.MULTILINE):
            raise Exception(f'VarVec3("{name}", ...) not found in template')

        return re.sub(
            pattern,
            rf"\g<1>{rr}, {gg}, {bb}\g<3>",
            content,
            count=1,
            flags=re.MULTILINE,
        )

    return _patch


def patch_varfloat(name: str, value: float) -> Patcher:
    def _patch(content: str) -> str:
        v = f"{value:.3f}".rstrip("0").rstrip(".") or "0.0"
        pattern = rf'(^\s*VarFloat\("{re.escape(name)}",\s*)([+-]?\d*\.?\d+)(\)\s*.*$)'
        if not re.search(pattern, content, flags=re.MULTILINE):
            raise Exception(f'VarFloat("{name}", ...) not found in template')

        return re.sub(
            pattern,
            rf"\g<1>{v}\g<3>",
            content,
            count=1,
            flags=re.MULTILINE,
        )

    return _patch


def patch_unlimited_nightmare_flashlight(enable: bool) -> Patcher:
    return patch_param_value_optional(
        "BatteryPoweredFlashlightItemName",
        "Player_Flashlight" if enable else "Player_Flashlight_Nightmare",
    )


def _compute_spawn_limits_from_master(master_pct: int) -> tuple[int, int, int, int]:
    """From Dynamic Spawner master 0-100, compute agenda, spawner, gameplay, aiproxy."""
    t = max(0, min(1, master_pct / 100.0))
    agenda = round(60 + t * 60)   # 60 -> 120
    spawner = round(120 + t * 180)  # 120 -> 300
    gameplay = round(10 + t * 190)  # 10 -> 200
    aiproxy = round(120 + t * 40)   # 120 -> 160
    return (agenda, spawner, gameplay, aiproxy)


def _compute_spawn_logic_from_max_ai(max_ai: int) -> tuple[float, float, int, bool]:
    """Compute SpawnRadiusNight, InnerRadiusSpawn, AIDensityMax, AIDensityIgnore from MaxSpawnedAI."""
    t = max(0.0, min(1.0, (max_ai - 80) / (800 - 80)))
    spawn_radius_night = round(60 + t * 25)
    inner_radius = round(19.5 + t * 6.0, 1)
    ai_density_base = round(63 + t * 140)  # 63 at 80, 203 at 800
    if max_ai > 800:
        t2 = min(1.0, (max_ai - 800) / 200)  # 0 at 800, 1 at 1000
        ai_density_max = round(203 + t2 * 200)  # 203 at 800, 403 at 1000
    else:
        ai_density_max = ai_density_base
    ai_density_ignore = max_ai != 80
    return (float(spawn_radius_night), inner_radius, ai_density_max, ai_density_ignore)


def patch_common_dynamic_spawn_logic(
    *,
    spawn_radius_night: float,
    inner_radius_spawn: float,
    ai_density_max: int,
    ai_density_ignore: bool,
    no_op: bool = False,
) -> Patcher:
    """Patch common_dynamic_spawn_logic_params.def with spawn logic params. no_op=True for strict 0-diff."""

    if no_op:
        return lambda c: c

    def _patch(content: str) -> str:
        content = patch_param_value_optional(
            "SpawnRadiusNight", f"{spawn_radius_night:.1f}"
        )(content)
        content = patch_param_value_optional(
            "InnerRadiusSpawnNight", f"{inner_radius_spawn:.1f}"
        )(content)
        content = patch_param_value_optional(
            "InnerRadiusSpawnDay", f"{inner_radius_spawn:.1f}"
        )(content)
        content = patch_param_value_optional(
            "AIDensityMaxAIsInSpawnArea", str(ai_density_max)
        )(content)
        content = patch_param_value_optional(
            "AIDensityIgnoreDefault", "true" if ai_density_ignore else "false"
        )(content)
        return content

    return _patch


# -----------------------------
# 4) Build/install pipeline
# -----------------------------
def apply_enabled_mods_to_scripts(out_scripts_dir: Path):
    enabled = get_enabled_mods()
    if not enabled:
        return

    for mod_root, manifest in enabled:
        # exempel: merge player_variables.scr om den finns
        target_name = "player_variables.scr"
        mod_file = find_mod_file(mod_root, target_name)
        out_file = out_scripts_dir / target_name

        if mod_file and out_file.exists():
            config_text = out_file.read_text(encoding="utf-8", errors="ignore")
            mod_text = mod_file.read_text(encoding="utf-8", errors="ignore")

            # policy: fråga? eller default config_wins?
            # börja enkelt: config wins som default
            mod_wins = False

            merged, conflicts = merge_scr(config_text, mod_text, mod_wins)
            if conflicts:
                # här kan du senare popup + remember choice i manifest["priority"][target_name]
                pass

            out_file.write_text(merged, encoding="utf-8")

def build_pak(pak_name=PAK_NAME):
    ensure_dirs()
    pak_path = os.path.join(OUTPUT_DIR, pak_name)

    with zipfile.ZipFile(pak_path, "w", zipfile.ZIP_STORED) as pak:
        for root_dir, dirs, files in os.walk("scripts"):
            for file in files:
                full_path = os.path.join(root_dir, file)
                pak.write(full_path, full_path)

    return pak_path


def install_pak(game_path: str, pak_name=PAK_NAME):
    if (not game_path) or (not os.path.isdir(game_path)):
        raise Exception("Game folder not set (or invalid)")

    target_dir = os.path.join(game_path, "ph_ft", "source")
    if not os.path.isdir(os.path.join(game_path, "ph_ft")):
        raise Exception("Selected folder doesn't look like the game folder (missing ph_ft).")

    source_pak = os.path.join(OUTPUT_DIR, pak_name)
    target_pak = os.path.join(target_dir, pak_name)

    os.makedirs(target_dir, exist_ok=True)
    shutil.copyfile(source_pak, target_pak)


# -----------------------------
# 5) UI state (tk variables)
# -----------------------------

enable_dark_titlebar(root)

# --- defaults per group ---
DEFAULTS_XP = []
DEFAULTS_FL = []
DEFAULTS_NI = []
DEFAULTS_HU = []
DEFAULTS_VO = []
DEFAULTS_VH = []
DEFAULTS_EN = []
DEFAULTS_PL = []
DEFAULTS_SP = []


def set_default(group_list, var, value):
    
    for i, (v, _) in enumerate(group_list):
        if v is var:
            group_list[i] = (var, value)
            var.set(value)
            return
    group_list.append((var, value))
    var.set(value)


def reset_defaults(group_list):
    for var, value in group_list:
        var.set(value)


# -----------------------------
# OPTIONS (must be global)
# -----------------------------
VO_MODE_OPTIONS = [
    ("Vanilla", "vanilla"),
    ("High → Low + Low → Default", "high_to_low"),
    ("High → Default + Low → Default", "high_to_default"),
    ("Calm (all → volatile_hive_resting)", "all_to_resting"),
    ("Pacify (delete blocks)", "pacify"),
]

ALPHA_MODE_OPTIONS = [
    ("Vanilla (no changes)", "vanilla"),
    ("High → Low", "high_to_low"),
    ("High → Default", "high_to_default"),
    ("Calm (resting)", "all_to_resting"),
    ("Pacify (delete blocks)", "pacify"),
]

# -----------------------------
# Vars (create ONCE)
# -----------------------------
game_path_var = tk.StringVar(root)
mode = tk.StringVar(root)

applied_ok = tk.BooleanVar(root)
advanced_var = tk.BooleanVar(root)

# XP
openworld_var = tk.IntVar(root)

# XP loss override (NEW)
xp_loss_override_var = tk.BooleanVar(root)
xp_loss_scale_var = tk.IntVar(root)

# Legend
legend_easy_var = tk.IntVar(root)
legend_hard_var = tk.IntVar(root)
legend_nightmare_var = tk.IntVar(root)

ll_xp_loss_var = tk.IntVar(root)
legend_penalty_var = tk.DoubleVar(root)
ngplus_var = tk.DoubleVar(root)
coop_var = tk.DoubleVar(root)
quest_lp_var = tk.DoubleVar(root)

# Volatiles UI vars
volatiles_enabled_var = tk.BooleanVar(root)
alpha_enabled_var = tk.BooleanVar(root)
vo_mode_var = tk.StringVar(root)
alpha_mode_var = tk.StringVar(root)
vo_reduce_pct_var = tk.IntVar(root)
vo_reduce_mult_var = tk.StringVar(value="0")  # default
vo_weights_visible_var = tk.BooleanVar(root, False)
vo_dmg_bonus_easy_pct = tk.IntVar(root, 0)
vo_dmg_bonus_normal_pct = tk.IntVar(root, 0)
vo_dmg_bonus_hard_pct = tk.IntVar(root, 0)
vo_dmg_bonus_nightmare_pct = tk.IntVar(root, 0)
vo_hp_volatile_pct = tk.IntVar(root, 100)
vo_hp_hive_pct = tk.IntVar(root, 100)
vo_hp_apex_pct = tk.IntVar(root, 100)
veh_pickup_pct = tk.IntVar(root, 100)
veh_pickup_ctb_pct = tk.IntVar(root, 100)
en_human_hp_bonus_easy_pct = tk.IntVar(root, 100)
en_human_hp_bonus_normal_pct = tk.IntVar(root, 100)
en_human_hp_bonus_hard_pct = tk.IntVar(root, 100)
en_human_hp_bonus_nightmare_pct = tk.IntVar(root, 100)
pl_water_speed_pct = tk.IntVar(root, 0)
pl_land_speed_pct = tk.IntVar(root, 0)
pl_boost_speed_pct = tk.IntVar(root, 0)
pl_ladder_climb_slow_var = tk.BooleanVar(root, False)  # unchecked = vanilla true
pl_fast_climb_enabled_var = tk.BooleanVar(root, False)  # unchecked = vanilla false
en_spawn_priority_var = tk.BooleanVar(root, False)  # EnablePrioritizationOfSpawners
sp_max_spawned_ai = tk.IntVar(root, 80)
sp_auto_cache_var = tk.BooleanVar(root, True)
sp_dialog_limit = tk.IntVar(root, 50)
sp_chase_limit = tk.IntVar(root, 15)  # vanilla 15
sp_cache_manual = tk.IntVar(root, 200)  # manual cache when auto off, 200-2400
sp_advanced_tuning_var = tk.BooleanVar(root, False)  # Advanced Spawning
sp_boost_darkzones_var = tk.BooleanVar(root, False)
sp_dynamic_spawner_master = tk.IntVar(root, 0)  # 0=defaults, 100=max, drives all spawn limits
# common_dynamic_spawn_logic_params.def
sp_spawn_radius_night = tk.DoubleVar(root, 60.0)
sp_inner_radius_spawn = tk.DoubleVar(root, 19.5)
sp_ai_density_max = tk.IntVar(root, 63)
sp_ai_density_ignore_var = tk.BooleanVar(root, False)
# Flashlight
flashlight_enabled_var = tk.BooleanVar(root)
flashlight_advanced_var = tk.BooleanVar(root)
nightmare_unlimited_var = tk.BooleanVar(root)

pp_r = tk.DoubleVar(root)
pp_g = tk.DoubleVar(root)
pp_b = tk.DoubleVar(root)
uv_r = tk.DoubleVar(root)
uv_g = tk.DoubleVar(root)
uv_b = tk.DoubleVar(root)

uv12_drain_var = tk.DoubleVar(root)
uv12_energy_var = tk.DoubleVar(root)
fl_regen_delay_uv1_var = tk.DoubleVar(root, value=3.0)
fl_regen_delay_uv2_var = tk.DoubleVar(root, value=2.5)
uv3_drain_var = tk.DoubleVar(root)
uv3_energy_var = tk.DoubleVar(root)
uv3_regen_var = tk.DoubleVar(root)
uv4_drain_var = tk.DoubleVar(root)
uv4_energy_var = tk.DoubleVar(root)
uv4_regen_var = tk.DoubleVar(root)
uv5_drain_var = tk.DoubleVar(root)
uv5_energy_var = tk.DoubleVar(root)
uv5_regen_var = tk.DoubleVar(root)

# Hunger
hunger_enabled_var = tk.BooleanVar(root)
hu_decrease_speed = tk.DoubleVar(root)
hu_mul_dash = tk.DoubleVar(root)
hu_mul_fury = tk.DoubleVar(root)
hu_resting_cost = tk.DoubleVar(root)
hu_revived_cost = tk.DoubleVar(root)

hu_cost_05 = tk.DoubleVar(root)
hu_cost_10 = tk.DoubleVar(root)
hu_cost_20 = tk.DoubleVar(root)
hu_cost_30 = tk.DoubleVar(root)
hu_cost_40 = tk.DoubleVar(root)
hunger_restore_full_var = tk.BooleanVar(root, value=False)  # one-shot, not in presets

# Night spawns (create ONCE)
night_enabled_var = tk.BooleanVar(root)

ni_begin_l1 = tk.IntVar(root)
ni_begin_l2_slums_l1 = tk.IntVar(root)
ni_begin_l3 = tk.IntVar(root)
ni_begin_l4_slums_l3 = tk.IntVar(root)

ni_slums_l2 = tk.IntVar(root)
ni_slums_l4 = tk.IntVar(root)

ni_ot_l1 = tk.IntVar(root)
ni_ot_l2 = tk.IntVar(root)
ni_ot_l3 = tk.IntVar(root)
ni_ot_l4 = tk.IntVar(root)

# -----------------------------
# Register defaults
# -----------------------------
# Core (game_path_var NOT in DEFAULTS_XP - must not be reset when resetting XP)
set_default(DEFAULTS_XP, mode, "openworld")
set_default(DEFAULTS_XP, applied_ok, False)
set_default(DEFAULTS_XP, advanced_var, False)

# XP
set_default(DEFAULTS_XP, openworld_var, 1)
set_default(DEFAULTS_XP, xp_loss_override_var, False)
set_default(DEFAULTS_XP, xp_loss_scale_var, 100)

# Legend
set_default(DEFAULTS_XP, legend_easy_var, 1.0)
set_default(DEFAULTS_XP, legend_hard_var, 1.05)
set_default(DEFAULTS_XP, legend_nightmare_var, 1.015)
set_default(DEFAULTS_XP, ll_xp_loss_var, 100)
set_default(DEFAULTS_XP, legend_penalty_var, 1.0)
set_default(DEFAULTS_XP, ngplus_var, 1.5)
set_default(DEFAULTS_XP, coop_var, 1.0)
set_default(DEFAULTS_XP, quest_lp_var, 1.0)

# Volatiles
set_default(DEFAULTS_VO, volatiles_enabled_var, True)
set_default(DEFAULTS_VO, alpha_enabled_var, True)
set_default(DEFAULTS_VO, vo_mode_var, "vanilla")
set_default(DEFAULTS_VO, alpha_mode_var, "vanilla")
set_default(DEFAULTS_VO, vo_reduce_pct_var, 100)
set_default(DEFAULTS_VO, vo_reduce_mult_var, "0")
set_default(DEFAULTS_VO, vo_weights_visible_var, False)
set_default(DEFAULTS_VO, vo_dmg_bonus_easy_pct, 0)
set_default(DEFAULTS_VO, vo_dmg_bonus_normal_pct, 0)
set_default(DEFAULTS_VO, vo_dmg_bonus_hard_pct, 0)
set_default(DEFAULTS_VO, vo_dmg_bonus_nightmare_pct, 0)
set_default(DEFAULTS_VO, vo_hp_volatile_pct, 100)
set_default(DEFAULTS_VO, vo_hp_hive_pct, 100)
set_default(DEFAULTS_VO, vo_hp_apex_pct, 100)
set_default(DEFAULTS_VH, veh_pickup_pct, 100)
set_default(DEFAULTS_VH, veh_pickup_ctb_pct, 100)

set_default(DEFAULTS_EN, en_human_hp_bonus_easy_pct, 100)
set_default(DEFAULTS_EN, en_human_hp_bonus_normal_pct, 100)
set_default(DEFAULTS_EN, en_human_hp_bonus_hard_pct, 100)
set_default(DEFAULTS_EN, en_human_hp_bonus_nightmare_pct, 100)
set_default(DEFAULTS_PL, pl_ladder_climb_slow_var, False)
set_default(DEFAULTS_PL, pl_fast_climb_enabled_var, False)
set_default(DEFAULTS_EN, en_spawn_priority_var, False)

set_default(DEFAULTS_PL, pl_water_speed_pct, 0)
set_default(DEFAULTS_PL, pl_land_speed_pct, 0)
set_default(DEFAULTS_PL, pl_boost_speed_pct, 0)

set_default(DEFAULTS_SP, sp_max_spawned_ai, 80)
set_default(DEFAULTS_SP, sp_auto_cache_var, True)
set_default(DEFAULTS_SP, sp_dialog_limit, 50)
set_default(DEFAULTS_SP, sp_chase_limit, 15)
set_default(DEFAULTS_SP, sp_cache_manual, 200)
set_default(DEFAULTS_EN, sp_max_spawned_ai, 80)
set_default(DEFAULTS_EN, sp_auto_cache_var, True)
set_default(DEFAULTS_EN, sp_dialog_limit, 50)
set_default(DEFAULTS_EN, sp_cache_manual, 200)
set_default(DEFAULTS_EN, sp_advanced_tuning_var, False)
set_default(DEFAULTS_EN, sp_boost_darkzones_var, False)
set_default(DEFAULTS_EN, sp_dynamic_spawner_master, 0)
set_default(DEFAULTS_EN, sp_spawn_radius_night, 60.0)
set_default(DEFAULTS_EN, sp_inner_radius_spawn, 19.5)
set_default(DEFAULTS_EN, sp_ai_density_max, 63)
set_default(DEFAULTS_EN, sp_ai_density_ignore_var, False)

# Flashlight
set_default(DEFAULTS_FL, flashlight_enabled_var, True)
set_default(DEFAULTS_FL, flashlight_advanced_var, False)
set_default(DEFAULTS_FL, nightmare_unlimited_var, False)

set_default(DEFAULTS_FL, pp_r, 1.0)
set_default(DEFAULTS_FL, pp_g, 0.95)
set_default(DEFAULTS_FL, pp_b, 0.87)
set_default(DEFAULTS_FL, uv_r, 0.15)
set_default(DEFAULTS_FL, uv_g, 0.5)
set_default(DEFAULTS_FL, uv_b, 1.0)

set_default(DEFAULTS_FL, uv12_drain_var, 0.75)
set_default(DEFAULTS_FL, uv12_energy_var, 5.0)
set_default(DEFAULTS_FL, fl_regen_delay_uv1_var, 3.0)
set_default(DEFAULTS_FL, fl_regen_delay_uv2_var, 2.5)
set_default(DEFAULTS_FL, uv3_drain_var, 0.8)
set_default(DEFAULTS_FL, uv3_energy_var, 6.0)
set_default(DEFAULTS_FL, uv3_regen_var, 2.0)
set_default(DEFAULTS_FL, uv4_drain_var, 1.0)
set_default(DEFAULTS_FL, uv4_energy_var, 15.0)
set_default(DEFAULTS_FL, uv4_regen_var, 1.0)
set_default(DEFAULTS_FL, uv5_drain_var, 1.0)
set_default(DEFAULTS_FL, uv5_energy_var, 18.0)
set_default(DEFAULTS_FL, uv5_regen_var, 1.0)

# Hunger
set_default(DEFAULTS_HU, hunger_enabled_var, True)
set_default(DEFAULTS_HU, hu_decrease_speed, 0.67)
set_default(DEFAULTS_HU, hu_mul_dash, 1.2)
set_default(DEFAULTS_HU, hu_mul_fury, 1.4)
set_default(DEFAULTS_HU, hu_resting_cost, -400.0)
set_default(DEFAULTS_HU, hu_revived_cost, -50.0)

set_default(DEFAULTS_HU, hu_cost_05, 0.5)
set_default(DEFAULTS_HU, hu_cost_10, 1.0)
set_default(DEFAULTS_HU, hu_cost_20, 2.0)
set_default(DEFAULTS_HU, hu_cost_30, 3.0)
set_default(DEFAULTS_HU, hu_cost_40, 4.0)

# Night
set_default(DEFAULTS_NI, night_enabled_var, True)
set_default(DEFAULTS_NI, ni_begin_l1, 2)
set_default(DEFAULTS_NI, ni_begin_l2_slums_l1, 3)
set_default(DEFAULTS_NI, ni_begin_l3, 5)
set_default(DEFAULTS_NI, ni_begin_l4_slums_l3, 8)
set_default(DEFAULTS_NI, ni_slums_l2, 6)
set_default(DEFAULTS_NI, ni_slums_l4, 12)
set_default(DEFAULTS_NI, ni_ot_l1, 4)
set_default(DEFAULTS_NI, ni_ot_l2, 7)
set_default(DEFAULTS_NI, ni_ot_l3, 10)
set_default(DEFAULTS_NI, ni_ot_l4, 14)
set_default(DEFAULTS_NI, sp_chase_limit, 15)


# --- END of defaults --- #

# -----------------------------
# 6) UI builders (create frames/widgets)
# -----------------------------


def ui_labeled_slider(
    parent,
    title,
    var,
    from_,
    to,
    hint=None,
    font_title=("Arial", 10),
    resolution=1,
    tight=True,
    label_width=24,
    entry_width=6,
    invert_negative=False,
    slider_length=420,      # <-- styr hur lång du vill ha den
):
    row_pady = 2 if tight else 4
    row = tk.Frame(parent)
    row.pack(fill="x", pady=(0, row_pady))

    if title:
        tk.Label(row, text=title, font=font_title, width=label_width, anchor="w").pack(side="left")

    scale_var = var
    scale_from, scale_to = from_, to

    if invert_negative and from_ < 0 and to <= 0:
        scale_from = 0
        scale_to = abs(float(from_))
        scale_var = tk.DoubleVar(row, value=-float(var.get()))
        _sync = {"block": False}

        def on_scale_change(*_):
            if _sync["block"]:
                return
            _sync["block"] = True
            try:
                var.set(-scale_var.get())
            finally:
                _sync["block"] = False

        def on_var_change(*_):
            if _sync["block"]:
                return
            _sync["block"] = True
            try:
                v = var.get()
                scale_var.set(-v if v <= 0 else 0)
            finally:
                _sync["block"] = False

        scale_var.trace_add("write", on_scale_change)
        var.trace_add("write", on_var_change)
        scale_var.set(-float(var.get()))

    scale = tk.Scale(
        row,
        from_=scale_from,
        to=scale_to,
        orient="horizontal",
        variable=scale_var,
        showvalue=1,
        resolution=resolution,
        length=slider_length,
    )
    # INTE fill/expand här, annars blir den avlång igen
    scale.pack(side="left", padx=(4, 2))

    entry = tk.Entry(row, width=entry_width, textvariable=var)
    entry.pack(side="left")

    if hint:
        tk.Label(parent, text=hint, fg="#666666", font=("Arial", 8)).pack(fill="x", pady=(0, 1))

    return row, scale, entry



def ui_pick_color_btn(parent, text, r_var, g_var, b_var):
    def _pick():
        rgb, _hex = colorchooser.askcolor(title=text)
        if rgb:
            r, g, b = rgb  # 0-255
            r_var.set(round(r / 255, 3))
            g_var.set(round(g / 255, 3))
            b_var.set(round(b / 255, 3))

    return tk.Button(parent, text=text, command=_pick)


def ui_section_title(parent, text, *, font=("Arial", 10, "bold"), pady=(0, 5)):
    """Centered section title."""
    tk.Label(parent, text=text, font=font).pack(fill="x", pady=pady)


def ui_hint(parent, text, *, fg="#666666", pady=(0, 6)):
    """Small gray helper text."""
    tk.Label(parent, text=text, fg=fg).pack(fill="x", pady=pady)


# Two-column grid layout: use for slider groups to reduce vertical length.
# Caller creates cell = tk.Frame(grid_frame) per item and cell.grid(row=i//2, column=i%2, sticky="ew", padx=..., pady=...).
GRID_COL_PADX = (0, 8)
GRID_ROW_PADY = (0, 2)


def make_two_column_grid(parent):
    """Returns a frame with 2 equal-weight columns. Pack this frame, then grid children at (i//2, i%2)."""
    f = tk.Frame(parent)
    f.columnconfigure(0, weight=1)
    f.columnconfigure(1, weight=1)
    return f


def ui_slider_row(parent, var, *, from_, to, showvalue=0, entry_width=6, pady=(0, 4)):
    """
    A horizontal row: [ Scale expands ] [ Entry ]
    Returns (row_frame, scale_widget, entry_widget)
    """
    row = tk.Frame(parent)
    row.pack(fill="x", pady=pady)

    scale = tk.Scale(
        row, from_=from_, to=to, orient="horizontal", variable=var, showvalue=showvalue
    )
    scale.pack(side="left", fill="x", expand=True)

    entry = tk.Entry(row, width=entry_width, textvariable=var)
    entry.pack(side="left", padx=(8, 0))

    return row, scale, entry


def ui_color_line(parent, label, r_var, g_var, b_var):
    row = tk.Frame(parent)
    row.pack(fill="x", pady=(0, 4))

    tk.Label(row, text=label, width=10, anchor="w").pack(side="left")

    tk.Entry(row, width=6, textvariable=r_var).pack(side="left", padx=(0, 6))
    tk.Entry(row, width=6, textvariable=g_var).pack(side="left", padx=(0, 6))
    tk.Entry(row, width=6, textvariable=b_var).pack(side="left", padx=(0, 6))

    tk.Label(row, text="(0–1)").pack(side="left")
    return row


def _clamp01(x: float) -> float:
    try:
        x = float(x)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, x))


def rgb01_to_hex(r, g, b) -> str:
    r = int(round(_clamp01(r) * 255))
    g = int(round(_clamp01(g) * 255))
    b = int(round(_clamp01(b) * 255))
    return f"#{r:02x}{g:02x}{b:02x}"


def _safe_get(var, fallback=0.0):
    try:
        return float(var.get())
    except Exception:
        return fallback


def ui_color_swatch(parent, r_var, g_var, b_var, size=18):
    sw = tk.Label(parent, width=2, height=1, relief="solid", bd=1)

    def _update(*_):
        r = _safe_get(r_var, 0.0)
        g = _safe_get(g_var, 0.0)
        b = _safe_get(b_var, 0.0)
        sw.configure(bg=rgb01_to_hex(r, g, b))

    # initial
    _update()

    r_var.trace_add("write", _update)
    g_var.trace_add("write", _update)
    b_var.trace_add("write", _update)

    return sw
    
def ui_header(parent, title, subtitle=None, subtitle2=None):
    header = tk.Frame(parent)
    header.pack(fill="x", pady=(10, 8))

    tk.Label(
        header,
        text=title,
        font=("Arial", 18, "bold"),
        anchor="center",
    ).pack(fill="x")

    if subtitle:
        tk.Label(
            header,
            text=subtitle,
            font=("Arial", 10),
            fg="#555555",
            anchor="center",
        ).pack(fill="x", pady=(2, 0))

    if subtitle2:
        tk.Label(
            header,
            text=subtitle2,
            font=("Arial", 9),
            fg="#777777",
            anchor="center",
        ).pack(fill="x", pady=(1, 0))

    # tunn separator-linje (lägg den INUTI header så den också försvinner)
    tk.Frame(header, height=1, bg="#D0D0D0").pack(fill="x", padx=20, pady=(6, 0))

    return header
    
def load_icon(path, size=18):
    img = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    return ImageTk.PhotoImage(img)

# efter root skapats:
icons = {
    "Main": load_icon(resource_path("assets/home.png"), size=30),
    "XP": load_icon(resource_path("assets/xp.png"), size=30),
    "Enemies": load_icon(resource_path("assets/skull.png"), size=30),
    "Flashlight": load_icon(resource_path("assets/uv.png"), size=30),
    "Hunger": load_icon(resource_path("assets/food.png"), size=30),
    "Player": load_icon(resource_path("assets/player.png"), size=30),
    "Vehicles": load_icon(resource_path("assets/car.png"), size=30),
    "Volatiles": load_icon(resource_path("assets/volatile.png"), size=30),
    "Mods": load_icon(resource_path("assets/mods.png"), size=30),
}
root._tab_icons = icons  # keep references (otherwise GC)
    
def set_window_icon(root, icon_path: str):
    icon_path = str(icon_path)

    # Om du har .ico: detta är stabilast på Windows
    if icon_path.lower().endswith(".ico"):
        try:
            root.iconbitmap(icon_path)
            return
        except Exception:
            pass  # fall back till iconphoto nedan

    img = Image.open(icon_path).convert("RGBA")

    sizes = [16, 32, 48, 64, 128]  # räcker
    window_icons = []
    for s in sizes:
        im = img.resize((s, s), Image.LANCZOS)
        window_icons.append(ImageTk.PhotoImage(im, master=root))  # <-- VIKTIGT: master=root

    root.iconphoto(True, *window_icons)
    root._window_icon_refs = window_icons  # <-- VIKTIGT: behåll refs

def build_ui():
    ui = {}  #
    
    # Bottom bar (keep)
    bottom = tk.Frame(root)
    bottom.pack(side="bottom", fill="x", padx=5, pady=(2, 2))

    # TOP toolbar: pure tk, topbar takes focus so button never keeps it; force colors so theme can't override
    TOPBAR_BG = "#2b3038"
    topbar = tk.Frame(root, bg=TOPBAR_BG)
    topbar.configure(takefocus=1)
    topbar.pack(side="top", fill="x", padx=4, pady=4)
    pad_tb = dict(padx=4, pady=4)

    BTN_NORMAL = "#343a44"
    BTN_HOVER = "#363c46"
    FG = "#eaeaea"

    root.option_add("*Button.background", BTN_NORMAL)
    root.option_add("*Button.foreground", FG)
    root.option_add("*Button.activeBackground", BTN_NORMAL)
    root.option_add("*Button.activeForeground", FG)
        
    def make_toolbar_button(parent, text, command=None):
        safe_cmd = command if callable(command) else (lambda: None)
        b = tk.Button(
            parent,
            text=text,
            command=safe_cmd,
            relief="flat",
            bd=0,
            highlightthickness=0,
            takefocus=0,
            bg=BTN_NORMAL,
            fg=FG,
            font=("Segoe UI", 9),
            activebackground=BTN_NORMAL,
            activeforeground=FG,
            highlightbackground=BTN_NORMAL,
            highlightcolor=BTN_NORMAL,
            padx=4,
            pady=2,
            cursor="hand2",
        )

        def set_normal(_=None):
            try:
                b.configure(bg=BTN_NORMAL, activebackground=BTN_NORMAL, fg=FG, activeforeground=FG)
            except tk.TclError:
                pass

        def set_hover(_=None):
            try:
                b.configure(bg=BTN_HOVER, activebackground=BTN_HOVER, fg=FG, activeforeground=FG)
            except tk.TclError:
                pass

        b.bind("<Enter>", set_hover)
        b.bind("<Leave>", set_normal)
        b.bind("<FocusOut>", set_normal)

        def on_release(_=None):
            set_normal()
            try:
                parent.focus_set()
            except tk.TclError:
                pass
            b.after(10, set_normal)
            b.after(50, set_normal)

        b.bind("<ButtonRelease-1>", on_release)
        b.bind("<Map>", lambda e: b.after(1, set_normal))

        for delay in (10, 50, 150, 300):
            b.after(delay, set_normal)

        return b


    # Notebook below topbar
    notebook = tb.Notebook(root, bootstyle="dark")
    # .ico ger rätt ikon i Windows (taskbar, titel, alt-tab); PNG som fallback
    ico_path = resource_path("assets/app.ico")
    if os.path.isfile(ico_path):
        set_window_icon(root, ico_path)
    else:
        set_window_icon(root, resource_path("assets/dltb_icon.png"))
    notebook.pack(fill="both", expand=True)
    
    # ---- Tabs  ----
    main_tab = tk.Frame(notebook)
    xp_tab = tk.Frame(notebook)
    flashlight_tab = tk.Frame(notebook)
    hunger_tab = tk.Frame(notebook)
    player_tab = tk.Frame(notebook)
    vehicles_tab = tk.Frame(notebook)
    volatiles_tab = ttk.Frame(notebook)
    enemies_tab = tk.Frame(notebook)
    mods_tab = tb.Frame(notebook)

    # --- Mods tab ---
    for child in mods_tab.winfo_children():
        child.destroy()
    
    # MÅSTE komma före att du använder en_adv_scroll_inner
    en_adv_scroll_outer, en_adv_scroll_inner = create_scrollable_frame(mods_tab)
    en_adv_scroll_outer.pack(fill="both", expand=True)

    pw = tk.PanedWindow(en_adv_scroll_inner, orient="vertical")
    pw.pack(fill="both", expand=True)

    rec_container = tb.Frame(pw)
    inst_container = tb.Frame(pw)

    pw.add(rec_container, minsize=360)
    pw.add(inst_container, minsize=180)

    # Status bar is created later; pass a ref so mods tab can use it once set
    ui["_set_status_ref"] = [None]
    build_recommended_mods_ui(rec_container, set_status_cb=ui["_set_status_ref"])
    build_installed_mods_ui(inst_container)

    mods_tab.update_idletasks()
    mods_tab.after(0, lambda: pw.sash_place(0, 0, 320))
    
    # --- Volatiles vars ---
    set_default(DEFAULTS_VO, vo_reduce_pct_var, 100)
    
    save_path_var = tk.StringVar(value=load_save_path_txt())
  
    # ---- Save-path helpers (place here: same indentation as apply/build_and_install) ----
    GAME_APPID = "3008130"
    SAVE_SUBPATH = Path(GAME_APPID) / "remote" / "out" / "save"

    def manual_pick_save_path():
        p = filedialog.askdirectory(title="Select your DLTB save folder")
        if not p:
            return
        save_path_var.set(p)
        save_save_path_txt(p)  # <-- viktigt
        messagebox.showinfo("Save path set", f"Save path set to:\n{p}")

    def _guess_steam_roots() -> list[Path]:
        roots = [
            Path(r"C:\Program Files (x86)\Steam"),
            Path(r"C:\Program Files\Steam"),
            Path.home() / "AppData" / "Local" / "Steam",
        ]
        return [p for p in roots if (p / "userdata").exists()]
    
    def auto_find_save_path():
        candidates: list[Path] = []

        for steam_root in _guess_steam_roots():
            userdata = steam_root / "userdata"
            if not userdata.exists():
                continue

            for steamid_dir in userdata.iterdir():
                if not steamid_dir.is_dir():
                    continue
                if not steamid_dir.name.isdigit():
                    continue

                save_dir = steamid_dir / SAVE_SUBPATH
                if save_dir.exists():
                    candidates.append(save_dir)

        # Deduplicate
        uniq: list[Path] = []
        seen = set()
        for p in candidates:
            rp = str(p.resolve())
            if rp not in seen:
                seen.add(rp)
                uniq.append(p)

        if len(uniq) == 0:
            messagebox.showerror(
                "Save path not found",
                "Could not find any saves automatically.\n"
                "Expected: Steam\\userdata\\<steamid>\\3008130\\remote\\out\\save\n\n"
                "Use Manual save path instead."
            )
            return

        if len(uniq) > 1:
            msg = "Multiple account saves found:\n\n" + "\n".join(str(p) for p in uniq[:10])
            if len(uniq) > 10:
                msg += f"\n...and {len(uniq) - 10} more"
            msg += "\n\nManually select path instead."
            messagebox.showerror("Multiple saves found", msg)
            return

        save_path_var.set(str(uniq[0]))
        save_save_path_txt(str(uniq[0]))
        messagebox.showinfo("Save path set", f"Save path set to:\n{uniq[0]}")
        
    DLTB_STEAM_APPID = "3008130"

    def launch_dying_light():
        # 1) 
        try:
            os.startfile(f"steam://rungameid/{DLTB_STEAM_APPID}")
            return
        except Exception:
            pass
            
    veh_throttle_bind = tk.StringVar(value="W")
    veh_brake_bind    = tk.StringVar(value="S")
    veh_left_bind     = tk.StringVar(value="A")
    veh_right_bind    = tk.StringVar(value="D")
    veh_handbrake_bind= tk.StringVar(value="Space")
    veh_leave_bind    = tk.StringVar(value="F")
    veh_camera_bind   = tk.StringVar(value="V")
    veh_lights_bind   = tk.StringVar(value="T")
    veh_lookback_bind = tk.StringVar(value="CapsLock")
    veh_horn_bind     = tk.StringVar(value="H")
    veh_redirect_bind = tk.StringVar(value="R")
    veh_uv_bind       = tk.StringVar(value="Mouse3") 
    
    veh_binds = {
    "throttle": veh_throttle_bind,
    "brake": veh_brake_bind,
    "left": veh_left_bind,
    "right": veh_right_bind,
    "handbrake": veh_handbrake_bind,
    "leave": veh_leave_bind,
    "camera": veh_camera_bind,
    "lights": veh_lights_bind,
    "lookback": veh_lookback_bind,
    "horn": veh_horn_bind,
    "redirect": veh_redirect_bind,
    "uv": veh_uv_bind,
}
    fuel_usage_pct = tk.IntVar(value=100)
    fuel_max_pct = tk.IntVar(value=100)
    notebook.add(main_tab, text="Main", image=icons["Main"], compound="left")
    notebook.add(xp_tab, text="XP", image=icons["XP"], compound="left")
    notebook.add(enemies_tab, text="Enemies", image=icons["Enemies"], compound="left")
    notebook.add(flashlight_tab, text="Flashlight", image=icons["Flashlight"], compound="left")
    notebook.add(hunger_tab, text="Hunger", image=icons["Hunger"], compound="left")
    notebook.add(player_tab, text="Player", image=icons["Player"], compound="left")
    notebook.add(vehicles_tab, text="Vehicles", image=icons["Vehicles"], compound="left")
    notebook.add(volatiles_tab, text="Volatiles", image=icons["Volatiles"], compound="left")
    notebook.add(mods_tab, text="Mods", image=icons["Mods"], compound="left")

    # ---- Top toolbar (real tk.Button, flat, hover never stuck) ----
    pad_tb = dict(padx=4, pady=4)

    btn_load_preset = make_toolbar_button(topbar, "Load preset…", command=None)
    btn_load_preset.pack(side="left", **pad_tb)
    btn_save_preset = make_toolbar_button(topbar, "Save preset…", command=None)
    btn_save_preset.pack(side="left", **pad_tb)
    sep1 = tk.Frame(topbar, width=2, bg="#555555")
    sep1.pack(side="left", fill="y", padx=6, pady=6)

    # Save path group (red border)
    save_path_callout_box = tk.Frame(topbar, highlightthickness=2, highlightbackground="#d00000")
    save_path_callout_box.pack(side="left", **pad_tb)
    save_path_callout_inner = tk.Frame(save_path_callout_box)
    save_path_callout_inner.pack(fill="x", padx=4, pady=2)
    save_path_row = tk.Frame(save_path_callout_inner)
    save_path_row.pack(fill="x")
    save_path_check_label = tk.Label(save_path_row, text="✓", fg="#228b22", font=("Arial", 8, "bold"))
    save_path_check_label.pack(side="left", padx=(0, 8))
    save_path_check_label.pack_forget()
    btn_save_auto = make_toolbar_button(save_path_row, "Auto-find save path", command=auto_find_save_path)
    btn_save_auto.pack(side="left", padx=(0, 6), pady=0)
    btn_manual = make_toolbar_button(save_path_row, "Manual save path...", command=manual_pick_save_path)
    btn_manual.pack(side="left", pady=0)

    sep2 = tk.Frame(topbar, width=2, bg="#555555")
    sep2.pack(side="left", fill="y", padx=6, pady=6)

    # Game folder group (red border)
    callout_box, callout = red_callout(topbar)
    combined_btn_row = tk.Frame(callout)
    combined_btn_row.pack(anchor="w", pady=0)
    btn_auto = make_toolbar_button(combined_btn_row, "Auto-detect Game Folder", command=None)
    btn_auto.pack(side="left", padx=(0, 6))
    btn_select = make_toolbar_button(combined_btn_row, "Select Game Folder", command=None)
    btn_select.pack(side="left", padx=(0, 6))

    root.option_add("*Button.background", "SystemButtonFace")
    root.option_add("*Button.foreground", "SystemButtonText")
    root.option_add("*Button.activeBackground", "SystemButtonHighlight")
    root.option_add("*Button.activeForeground", "SystemButtonText")

    # ---- Bottom bar: Apply / Build / Play + status ----
    btn_row = tk.Frame(bottom)
    btn_row.pack()

    btn_apply = tk.Button(btn_row, text="Apply", state="disabled")
    btn_apply.pack(side="left", padx=8)

    btn_build = tk.Button(btn_row, text="Build & Install PAK", state="disabled")
    btn_build.pack(side="left", padx=8)
    
    btn_launch = tk.Button(
        btn_row,
        text="▶  PLAY GAME",
        command=launch_dying_light,
        bg="#90EE90",           # light green
        fg="black",
        activebackground="#90EE90",
        activeforeground="black",
        bd=0,
        relief="flat",
        font=("Arial", 10, "bold"),
        padx=3,
        pady=3,
        cursor="hand2",
    )
    btn_launch.pack(side="left", padx=6)

    status_frame = tk.Frame(bottom)
    status_frame.pack(fill="x", pady=(8, 0))

    status_text = tk.Text(
        status_frame, height=1, wrap="word", borderwidth=0, highlightthickness=0
    )
    status_text.pack(fill="x")
    status_text.tag_configure("ok", foreground=COLOR_OK)
    status_text.tag_configure("warn", foreground=COLOR_WARN)
    status_text.config(state="disabled", cursor="arrow")
    
    def set_status(items):
        # items: [("text", "ok"), ("text", "warn")] eller bara "text"
        if isinstance(items, str):
            items = [(items, "ok")]

        status_text.config(state="normal")
        status_text.delete("1.0", "end")
        for text, tag in items:
            status_text.insert("end", str(text), tag)
        status_text.config(state="disabled")

    ui["set_status"] = set_status
    ui["status_text"] = status_text  
    if "_set_status_ref" in ui:
        ui["_set_status_ref"][0] = set_status
        
    global STATUS_REF
    STATUS_REF[0] = set_status
    
    btn_reset_fl = None
    
    jump_override_var = tk.BooleanVar(value=False)
    jump_boost_var = tk.DoubleVar(value=0.0)
    
    ui["jump_boost_var"] = jump_boost_var
    ui["jump_override_var"] = jump_override_var
    
    def build_main_tab(parent):
        """Main tab: banner, title, game path + save path only. No XP controls."""
        ui_header(
            parent,
            "Dying Light: The Beast Configurator",
            "by Robeloto • a Mod tool for XP, Flashlight, Hunger, Volatiles and more",
        )

        main_wrapper = tk.Frame(parent)
        main_wrapper.pack(fill="both", expand=True)

        # Banner
        xp_banner_frame = add_banner(main_wrapper, "dltb.jpg", height=160)
        
        hdr = tb.Label(
            main_wrapper,
            text="Workflow: Choose mode → Tune sliders → Build & Install PAK.\n\nWelcome to Version 0.6b",
            font=("Arial", 10),
            bootstyle="info",
            justify="center",
            anchor="center",
        )
        hdr.pack(fill="x", pady=(6, 2))

        lines = [
            "• Changed UI theme to a darker theme",
            "• Added a top toolbar for preset/save-path/game-folder actions",
            "• Added small icons to the tab headers",
            "• Mods tab for loading 3rd party mods",
            "• Separated Main and XP section",
            "• Jumping height added",
            "• Movement speed up to 300%",
        ]

        color_map = {
            1: ("blue", "#66aaff"),
            3: ("pink", "#ff66cc"),

        }

        bullets = tk.Text(
            main_wrapper,
            height=len(lines),
            wrap="none",
            borderwidth=0,
            highlightthickness=0,
            padx=180,   # <-- justera: 120–260 beroende på fönsterbredd
            pady=0,
            font=("Arial", 10),
            fg="#b8b8b8",
            bg=main_wrapper.cget("bg"),
        )
        bullets.pack(fill="x", pady=(0, 8))
        
        smm_note = tk.Label(
            main_wrapper,
            text="Please run Super Mod Merger if you have installed 3rd party mods.",
            font=("Arial", 10, "bold"),
            fg="#ffd54a",  # mild gul
            bg=main_wrapper.cget("bg"),
            justify="center",
        )
        smm_note.pack(fill="x", pady=(0, 10))
        
        def _update_bullets_pad(_evt=None):
            # ungefärlig “blockbredd” du vill ha
            target_width = 300  # test
            w = bullets.winfo_width()
            if w <= 1:
                return
            pad = max(10, (w - target_width) // 2)
            bullets.config(padx=pad)

        bullets.bind("<Configure>", _update_bullets_pad)
        _update_bullets_pad()

        for _, (tag, col) in color_map.items():
            bullets.tag_configure(tag, foreground=col)

        for i, line in enumerate(lines):
            start = bullets.index("end-1c")
            bullets.insert("end", line + ("\n" if i < len(lines)-1 else ""))
            end = bullets.index("end-1c")
            if i in color_map:
                tag, _ = color_map[i]
                bullets.tag_add(tag, start, end)

        bullets.config(state="disabled", cursor="arrow")


        main_content_frame = tk.Frame(main_wrapper)
        main_content_frame.pack(fill="x", pady=(0, 0))

        return {
            "main_content_frame": main_content_frame,
            "xp_banner_frame": xp_banner_frame,
        }


    def build_xp_tab(parent, main_content_frame):
        """XP tab: Choose mode, Open World/Legend sliders, advanced, reset XP."""
        xp_wrapper = tk.Frame(parent)
        xp_wrapper.pack(fill="both", expand=True)
        choose_mode_frame = tk.Frame(xp_wrapper)
        choose_mode_frame.pack(fill="x", pady=(0, 0))
        xp_badge = tk.Frame(
            choose_mode_frame,
            highlightbackground="#8A8A8A",
            highlightthickness=2,
            bd=0,
        )
        xp_badge.pack(pady=(10, 10))
        tk.Label(
            xp_badge,
            text="Choose XP Mode",
            font=("Arial", 11, "bold"),
            padx=13,
            pady=8,
        ).pack()
        xp_card = tk.Frame(choose_mode_frame, highlightthickness=1, highlightbackground="#8A8A8A")
        xp_card.pack(fill="x", padx=50)
        radio_frame = tk.Frame(xp_card)
        radio_frame.pack(pady=(2, 0))
        rb_font = ("Arial", 11)
        rb_ow = tk.Radiobutton(
            radio_frame,
            text="Open World XP (pre-NG+)",
            variable=mode,
            value="openworld",
            font=rb_font,
            pady=0,
        )
        rb_ow.pack(anchor="w")
        rb_leg = tk.Radiobutton(
            radio_frame,
            text="Legend XP Bonus (NG+)",
            variable=mode,
            value="legend",
            font=rb_font,
            pady=2,
        )
        rb_leg.pack(anchor="w")
        openworld_frame = tk.Frame(xp_card)
        legend_frame = tk.Frame(xp_card)
        ow_wrap = tk.Frame(openworld_frame)
        ow_wrap.pack(anchor="center")
        legend_scroll_outer, legend_scroll_inner = make_scrollable(legend_frame)
        legend_scroll_outer.pack(fill="both", expand=True)
        for w in legend_scroll_outer.winfo_children():
            if isinstance(w, tk.Canvas):
                w.configure(height=320)
                break
        tk.Label(
            ow_wrap,
            text="Open World XP Multiplier",
            font=("Arial", 11, "bold"),
        ).pack(anchor="center", pady=(0, 0))
        row, scale, entry = ui_labeled_slider(
            ow_wrap,
            "",
            openworld_var,
            from_=1.0,
            to=100.0,
            hint="(1 = vanilla)",
            font_title=("Arial", 11, "bold"),
            resolution=1.0,
        )
        legend_easy_var.set(1.0)
        legend_hard_var.set(1.05)
        legend_nightmare_var.set(1.15)
        def refresh_advanced():
            pass  # no-op: advanced sliders are always visible now

        TEXT = "#1A1A1A"
        BG = "#D9C06A"
        XP_SLIDER_LEN = 172  # short sliders so two columns fit and align side by side
        XP_COL_PADX = 24     # even spacing between left and right section

        two_col_wrap = tk.Frame(legend_scroll_inner)
        two_col_wrap.pack(fill="x", pady=(8, 0))
        two_col_inner = tk.Frame(two_col_wrap)
        two_col_inner.pack(fill="x", expand=True)
        two_col_inner.grid_columnconfigure(0, weight=1, minsize=320)
        two_col_inner.grid_columnconfigure(1, weight=1, minsize=320)

        # Left column: Legend XP Loss on Death + Legend XP Multipliers (Easy/Normal, Hard, Nightmare)
        left_col = tk.Frame(two_col_inner)
        left_col.grid(row=0, column=0, sticky="n", padx=(0, XP_COL_PADX // 2))
        tk.Label(
            left_col,
            fg="#666666",
            font=("Arial", 8),
        ).pack(anchor="w")
        # Left column 
        ui_labeled_slider(
            left_col,
            "Legend XP Loss(%)",
            ll_xp_loss_var,
            from_=0,
            to=500,
            resolution=1.0,
            tight=True,
            slider_length=XP_SLIDER_LEN,
        )
        legend_header = tk.Frame(
            left_col, bg=BG, highlightbackground=COLOR_BORDER, highlightthickness=1
        )
        legend_header.pack(fill="x", pady=(0, 14))
        ui_labeled_slider(
            left_col,
            "Easy / Normal XP",
            legend_easy_var,
            from_=1.0,
            to=300.0,
            resolution=0.01,
            tight=True,
            slider_length=XP_SLIDER_LEN,
        )
        ui_labeled_slider(
            left_col,
            "Hard XP",
            legend_hard_var,
            from_=1.0,
            to=300.0,
            resolution=0.01,
            tight=True,
            slider_length=XP_SLIDER_LEN,
        )
        ui_labeled_slider(
            left_col,
            "Nightmare XP",
            legend_nightmare_var,
            from_=1.0,
            to=300.0,
            resolution=0.01,
            tight=True,
            slider_length=XP_SLIDER_LEN,
        )

        # Right column: Legend Penalty, NG+ Bonus, Coop Bonus, Quest Legend (always visible)
        right_col = tk.Frame(two_col_inner)
        right_col.grid(row=0, column=1, sticky="n", padx=(XP_COL_PADX // 2, 0))

        _spacer_top = tk.Frame(right_col, height=20)
        _spacer_top.pack(fill="x")
        _spacer_top.pack_propagate(False)

        ui_labeled_slider(
            right_col,
            "Legend Penalty *",
            legend_penalty_var,
            from_=0.0,
            to=5.0,
            resolution=0.05,
            tight=True,
            slider_length=XP_SLIDER_LEN,
        )

        
        _spacer_between = tk.Frame(right_col, height=16)
        _spacer_between.pack(fill="x")
        _spacer_between.pack_propagate(False)

        ui_labeled_slider(
            right_col,
            "NG+ Bonus *",
            ngplus_var,
            from_=0.0,
            to=5.0,
            resolution=0.05,
            tight=True,
            slider_length=XP_SLIDER_LEN,
        )

        ui_labeled_slider(
            right_col,
            "Coop Bonus *",
            coop_var,
            from_=0.0,
            to=5.0,
            resolution=0.05,
            tight=True,
            slider_length=XP_SLIDER_LEN,
        )

        ui_labeled_slider(
            right_col,
            "Quest Legend *",
            quest_lp_var,
            from_=1.0,
            to=10.0,
            resolution=0.05,
            tight=True,
            slider_length=XP_SLIDER_LEN,
        )


        ttk.Separator(legend_scroll_inner, orient="horizontal").pack(fill="x", pady=(8, 8))

        btn_reset_xp = tk.Button(xp_card, text="Reset XP to defaults")
        btn_reset_xp.pack(pady=(10, 14))
        return {
            "openworld_frame": openworld_frame,
            "legend_frame": legend_frame,
            "rb_ow": rb_ow,
            "rb_leg": rb_leg,
            "btn_reset_xp": btn_reset_xp,
            "xp_badge": xp_badge,
            "refresh_advanced": refresh_advanced,
        }

    main_ui = build_main_tab(main_tab)
    xp_ui = build_xp_tab(xp_tab, main_ui["main_content_frame"])

    openworld_frame = xp_ui["openworld_frame"]
    legend_frame = xp_ui["legend_frame"]
    rb_ow = xp_ui["rb_ow"]
    rb_leg = xp_ui["rb_leg"]
    btn_reset_xp = xp_ui["btn_reset_xp"]
    refresh_advanced = xp_ui["refresh_advanced"]

    # =========================
    # Flashlight tab content
    # =========================

    fl_outer, fl_wrap = make_scrollable(flashlight_tab)
    fl_outer.pack(fill="both", expand=True)
    tk.Label(fl_wrap, text="Flashlight", font=("Arial", 12, "bold")).pack(pady=10)

    fl_card = tk.Frame(fl_wrap, highlightthickness=1, highlightbackground="#8A8A8A")
    fl_card.pack(padx=60, pady=12, fill="x")

    # --- Flashlight Colors (postprocess) ---
    colors_box = tk.Frame(fl_card)  # ingen LabelFrame-ram
    colors_box.pack(fill="x", padx=10, pady=(8, 6))

    tk.Label(colors_box, text="Flashlight Colors (postprocess)", font=("Arial", 10, "bold")).pack(anchor="w")

    tk.Label(
        colors_box,
        text="Defaults: Normal = [1.0, 0.95, 0.87]   UV = [0.15, 0.5, 1.0]",
        fg="#666666",
    ).pack(anchor="w", pady=(4, 0))
    
    fl_colors_btn_row = tk.Frame(colors_box)
    fl_colors_btn_row.pack(fill="x", pady=(4, 6))

    ui_pick_color_btn(
        fl_colors_btn_row, "Pick NORMAL flashlight color...", pp_r, pp_g, pp_b
    ).pack(side="left", padx=(0, 8))

    norm_swatch = ui_color_swatch(fl_colors_btn_row, pp_r, pp_g, pp_b)
    norm_swatch.pack(side="left", padx=(0, 16))

    ui_pick_color_btn(
        fl_colors_btn_row, "Pick UV flashlight color...", uv_r, uv_g, uv_b
    ).pack(side="left", padx=(0, 8))

    uv_swatch = ui_color_swatch(fl_colors_btn_row, uv_r, uv_g, uv_b)
    uv_swatch.pack(side="left")
    
    ui_color_line(colors_box, "Normal:", pp_r, pp_g, pp_b)
    ui_color_line(colors_box, "UV:", uv_r, uv_g, uv_b)  

    btn_reset_fl = tk.Button(fl_colors_btn_row, text="Reset everything to defaults")
    btn_reset_fl.pack(side="left", padx=(40, 0))  
    
    tk.Checkbutton(
        fl_card,
        text="Unlimited battery on Nightmare (BatteryPoweredFlashlightItemName -> Player_Flashlight)",
        variable=nightmare_unlimited_var,
    ).pack(anchor="w", pady=(0, 12))

    # Container for tweak controls
    flashlight_controls = tk.Frame(fl_card)
    flashlight_controls.pack(fill="x")

    # LVL 1 & 2 shared
    lf12 = tk.Frame(flashlight_controls)
    lf12.pack(fill="x", pady=(0, 10))

    tk.Label(lf12, text="UV LVL 1 & 2 (shared)", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0,4))


    ui_labeled_slider(
        lf12, "EnergyDrainPerSecond", uv12_drain_var, from_=0.0, to=5.0, resolution=0.05
    )
    ui_labeled_slider(
        lf12, "MaxEnergy", uv12_energy_var, from_=0.0, to=50.0, resolution=0.5
    )
    ui_labeled_slider(
        lf12,
        "UV LVL 1 RegenerationDelay",
        fl_regen_delay_uv1_var,
        from_=0.0,
        to=10.0,
        resolution=0.05,
    )
    ui_labeled_slider(
        lf12,
        "UV LVL 2 RegenerationDelay",
        fl_regen_delay_uv2_var,
        from_=0.0,
        to=10.0,
        resolution=0.05,
    )

    def add_lvl(parent, title, drain_var, energy_var, regen_var):
        lf = tk.Frame(parent)
        lf.pack(fill="x", pady=(0, 10))

        tk.Label(lf, text=title, font=("Arial", 10, "bold")).pack(anchor="w", pady=(0,4))

        ui_labeled_slider(lf, "EnergyDrainPerSecond", drain_var, from_=0.0, to=5.0, resolution=0.05)
        ui_labeled_slider(lf, "MaxEnergy", energy_var, from_=0.0, to=50.0, resolution=0.5)
        ui_labeled_slider(lf, "RegenerationDelay", regen_var, from_=0.0, to=10.0, resolution=0.05)

    add_lvl(
         flashlight_controls, "UV LVL 3", uv3_drain_var, uv3_energy_var, uv3_regen_var
    )
    
    # --- Advanced toggle (LVL 4-5) ---
    adv_row = tk.Frame(flashlight_controls)
    adv_row.pack(fill="x", pady=(4, 8))

    adv_center = tk.Frame(adv_row)
    adv_center.pack()

    advanced_levels_frame = tk.Frame(flashlight_controls)  # created but not packed yet

    def refresh_flashlight_advanced():
        if flashlight_advanced_var.get():
            advanced_levels_frame.pack(fill="x", pady=(0, 10))
        else:
            advanced_levels_frame.pack_forget()

    row = tk.Frame(adv_center)
    row.pack()

    tk.Checkbutton(
        row,
        text="Show advanced UV levels (LVL 4–5)",
        variable=flashlight_advanced_var,
        command=refresh_flashlight_advanced,
    ).pack(side="left")

    tk.Label(
        row,
        text="(Not used by game yet)",
        fg="red",
    ).pack(side="left", padx=(6, 0))

    add_lvl(
        advanced_levels_frame, "UV LVL 4", uv4_drain_var, uv4_energy_var, uv4_regen_var
    )
    add_lvl(
        advanced_levels_frame, "UV LVL 5", uv5_drain_var, uv5_energy_var, uv5_regen_var
    )

    refresh_flashlight_advanced()

    # =========================
    # Hunger tab content (grid centering)
    # =========================

    def show_hunger_actions():
        win = tk.Toplevel(root)
        win.title("Actions affected by hunger sliders")
        win.transient(root)
        win.grab_set()

        txt = tk.Text(win, width=90, height=10, wrap="none")
        txt.pack(fill="both", expand=True, padx=1, pady=1)

        info = (
            "Actions affected by sliders\n\n"
            "0.5 -> FuryAttack\n"
            "1.0 -> Finisher, LightAttack, Slide\n"
            "2.0 -> FuryPowerAttackLvl2, GroundPound, Kick, PowerAttack\n"
            "3.0 -> EnemyJump, KickAir, KickCharged, FuryCharge, FuryGrapplingHookLvl2,\n"
            "      FuryGroundPoundLvl1, FuryJump, FuryScreamLvl2, FurySprint, FuryThrowable,\n"
            "      FuryWindmill, MeleeWeaponThrow, Ram, RopeHookPullEnemy, VaultKick, WeaponThrow\n"
            "4.0 -> CM_Stomp, KickWrestle, Windmill\n"
        )

        txt.insert("1.0", info)
        txt.config(state="disabled")

        btn = tk.Button(win, text="Close", command=win.destroy)
        btn.pack(pady=(0, 10))

    hu_wrapper = tk.Frame(hunger_tab)
    hu_wrapper.pack(fill="both", expand=True)

    # Grid: 0=header, 1=separator, 2=top spacer, 3=card, 4=bottom spacer
    hu_wrapper.grid_columnconfigure(0, weight=1)
    hu_wrapper.grid_rowconfigure(2, weight=1)  # top spacer grows
    hu_wrapper.grid_rowconfigure(4, weight=1)  # bottom spacer grows

    # --- Badge header
    hu_badge = tk.Frame(
        hu_wrapper,
        highlightbackground="#8A8A8A",
        highlightthickness=1,
        bd=0,
    )
    hu_badge.grid(row=0, column=0, pady=(30, 10))

    tk.Label(
        hu_badge,
        text="Nightmare only — Hunger",
        font=("Arial", 15, "bold"),
        padx=12,
        pady=4,
    ).pack()

    # top spacer (empty)
    tk.Frame(hu_wrapper).grid(row=2, column=0, sticky="nsew")

    # --- Card (centered) ---
    hu_card = tk.Frame(hu_wrapper, highlightthickness=1, highlightbackground="#8A8A8A")
    hu_card.grid(row=3, column=0, padx=60, sticky="ew")

    # --- Info button (opens popup) ---
    btn_hu_info = tk.Button(
        hu_card,
        text="Show actions affected by sliders…",
        command=show_hunger_actions,
    )
    btn_hu_info.pack(pady=(0, 0))

    # bottom spacer (empty)
    tk.Frame(hu_wrapper).grid(row=4, column=0, sticky="nsew")

    # =========================
    # INSIDE hu_card (pack + grid
    # =========================

    info_frame = tk.Frame(hu_card)
    info_frame.pack(fill="x", padx=10, pady=(0, 12))

    # grid columns inside info_frame
    info_frame.grid_columnconfigure(0, weight=0)  # numbers
    info_frame.grid_columnconfigure(1, weight=1)  # text expands
    
    tk.Label(hu_card, text="Hunger Action Costs", font=("Arial", 11, "bold")).pack(
        pady=(0, 0)
    )

    ui_labeled_slider(
        hu_card,
        "0.5 values →",
        hu_cost_05,
        from_=0.0,
        to=10.0,
        resolution=0.05,
    )
    ui_labeled_slider(
        hu_card,
        "1.0 values →",
        hu_cost_10,
        from_=0.0,
        to=10.0,
        resolution=0.05,
    )
    ui_labeled_slider(
        hu_card,
        "2.0 values →",
        hu_cost_20,
        from_=0.0,
        to=10.0,
        resolution=0.05,
    )
    ui_labeled_slider(
        hu_card,
        "3.0 values →",
        hu_cost_30,
        from_=0.0,
        to=10.0,
        resolution=0.05,
    )
    ui_labeled_slider(
        hu_card,
        "4.0 values →",
        hu_cost_40,
        from_=0.0,
        to=10.0,
        resolution=0.05,
    )

    ui_labeled_slider(
        hu_card,
        "Hunger drain",
        hu_decrease_speed,
        from_=0.0,
        to=2.0,
        resolution=0.01,
    )

    # advanced:
    ui_labeled_slider(
        hu_card,
        "Dash drain multiplier",
        hu_mul_dash,
        from_=0.0,
        to=3.0,
        resolution=0.01,
    )
    ui_labeled_slider(
        hu_card,
        "Fury drain multiplier",
        hu_mul_fury,
        from_=0.0,
        to=3.0,
        resolution=0.01,
    )

    ui_labeled_slider(
        hu_card,
        "Resting cost",
        hu_resting_cost,
        from_=-400.0,
        to=0.0,
        resolution=1.0,
        invert_negative=True,
    )
    ui_labeled_slider(
        hu_card,
        "Revived cost",
        hu_revived_cost,
        from_=-50.0,
        to=0.0,
        resolution=1.0,
        invert_negative=True,
    )

    hu_btn_row = tk.Frame(hu_card)
    hu_btn_row.pack(fill="x", pady=(6, 10))

    for c in range(3):
        hu_btn_row.grid_columnconfigure(c, weight=1)

    btn_reset_hu = tk.Button(hu_btn_row, text="Reset to defaults")
    btn_reset_hu.grid(row=0, column=0, padx=6, sticky="ew")

    btn_hu_off = tk.Button(hu_btn_row, text="Turn off hunger")
    btn_hu_off.grid(row=0, column=1, padx=6, sticky="ew")
    
    btn_restore_hunger = tk.Button(hu_btn_row, text="Restore Hunger to 100%")
    btn_restore_hunger.grid(row=0, column=2, padx=6, sticky="ew")
    
    tk.Label(
    hu_btn_row,
    text="not working",
    fg="red",
    font=("Arial", 8, "bold"),
).grid(row=1, column=2, padx=6, pady=(2, 0), sticky="ew")

    # =========================
    #   Player tab Content
    # =========================
    pl_wrapper = tk.Frame(player_tab)
    pl_wrapper.pack(fill="both", expand=True)

    pl_card = tk.Frame(
        pl_wrapper, highlightthickness=1, highlightbackground="#8A8A8A"
    )
    pl_card.pack(padx=60, pady=12, fill="x")

    # --- Climb options (player_variables.scr) - 2x2 grid, top center ---
    pl_climb_wrapper = tk.Frame(pl_card)
    pl_climb_wrapper.pack(fill="x", pady=(6, 4))
    climb_grid = tk.Frame(pl_climb_wrapper)
    climb_grid.pack(anchor="center")
    climb_grid.grid_columnconfigure(0, weight=1)
    climb_grid.grid_columnconfigure(1, weight=1)
    # row 0 col 0, row 1 col 0 = left column (west)
    tk.Checkbutton(
        climb_grid,
        text="LadderClimbSlow = false",
        variable=pl_ladder_climb_slow_var,
        font=("Arial", 9),
    ).grid(row=0, column=0, sticky="w", padx=(0, 24), pady=0)
    tk.Checkbutton(
        climb_grid,
        text="FastClimbEnabled = true",
        variable=pl_fast_climb_enabled_var,
        font=("Arial", 9),
    ).grid(row=1, column=0, sticky="w", padx=(0, 24), pady=0)
    # row 0 col 1, row 1 col 1 = right column checkbuttons + warn labels added later

    tk.Label(
        pl_card,
        text="Movement speed (safe sliders)",
        font=("Arial", 12, "bold"),
    ).pack(pady=(10, 4))
    
    pl_hint = "Bonus on top of vanilla. Multiplier = 1.0 + (bonus/100). Ex: 100% = 2.0x, 300% = 4.0x"
    
    tk.Label(pl_card, text=pl_hint, fg="#666666", font=("Arial", 8)).pack(fill="x", pady=(0, 4)
    )

    SAFE_MAX = 100
    OVERRIDE_MAX = 300
    override_var = tk.BooleanVar(value=False)

    pl_speed_grid = make_two_column_grid(pl_card)
    pl_speed_grid.pack(fill="x", pady=(0, 4))
    pl_speed_specs = [
        ("Water speed bonus (%)", pl_water_speed_pct),
        ("Land speed bonus (%)", pl_land_speed_pct),
        ("Boost speed bonus (%)", pl_boost_speed_pct),
    ]
    water_ret = land_ret = boost_ret = None
    for idx, (title, var) in enumerate(pl_speed_specs):
        cell = tk.Frame(pl_speed_grid)
        cell.grid(row=idx // 2, column=idx % 2, sticky="ew", padx=GRID_COL_PADX, pady=GRID_ROW_PADY)
        ret = ui_labeled_slider(cell, title, var, from_=0, to=SAFE_MAX, resolution=5, slider_length=220)
        if idx == 0:
            water_ret = ret
        elif idx == 1:
            land_ret = ret
        else:
            boost_ret = ret

    water_scale = find_scale(water_ret)
    land_scale  = find_scale(land_ret)
    boost_scale = find_scale(boost_ret)

    if not all([water_scale, land_scale, boost_scale]):
        raise RuntimeError("Could not find ttk.Scale returned/created by ui_labeled_slider()")

    cb_override_speed = tk.Checkbutton(
        climb_grid,
        text=f"Override max speed {OVERRIDE_MAX}%",
        variable=override_var,
        font=("Arial", 9),
    )
    cb_override_speed.grid(row=0, column=1, sticky="w", padx=(0, 0), pady=0)

    def apply_override():
        new_max = OVERRIDE_MAX if override_var.get() else SAFE_MAX

        for sc in (water_scale, land_scale, boost_scale):
            sc.config(to=new_max)

        if not override_var.get():
            for var in (pl_water_speed_pct, pl_land_speed_pct, pl_boost_speed_pct):
                if var.get() > SAFE_MAX:
                    var.set(SAFE_MAX)

    cb_override_speed.config(command=apply_override)
    apply_override()

    # Jump
    jump_cell = tk.Frame(pl_speed_grid)
    jump_cell.grid(row=1, column=1, sticky="ew", padx=GRID_COL_PADX, pady=GRID_ROW_PADY)

    jump_ret = ui_labeled_slider(
        jump_cell,  # eller pl_card / jump_cell i grid
        "Jump height boost",
        jump_boost_var,
        from_=0,
        to=JUMP_SAFE_MAX,          # börjar safe
        resolution=1,
        tight=True,
        slider_length=220,
    )
    jump_scale = jump_ret[1]
    jump_entry = jump_ret[2]
    jump_entry.config(width=3)

    cb_override_jump = tk.Checkbutton(
        climb_grid,
        text=f"Override jump max {JUMP_OVERRIDE_MAX:g}",
        variable=jump_override_var,
        font=("Arial", 9),
    )
    cb_override_jump.grid(row=1, column=1, sticky="w", padx=(0, 0), pady=0)

    def apply_jump_override():
        new_max = JUMP_OVERRIDE_MAX if jump_override_var.get() else JUMP_SAFE_MAX
        jump_scale.config(to=new_max)

        if not jump_override_var.get() and jump_boost_var.get() > JUMP_SAFE_MAX:
            jump_boost_var.set(JUMP_SAFE_MAX)

    cb_override_jump.config(command=apply_jump_override)
    apply_jump_override()

    btn_reset_pl = tk.Button(pl_card, text="Reset Player tab to defaults")
    btn_reset_pl.pack(pady=(10, 14))

    # =========================
    #   Vehicles tab Content (scrollable, compact)
    # =========================
    vh_outer, vh_wrap = make_scrollable(vehicles_tab)
    vh_outer.pack(fill="both", expand=True)
    vh_wrapper = vh_wrap

    pad_vh, pady_vh = 36, 8
    vh_card = tk.Frame(
        vh_wrapper, highlightthickness=1, highlightbackground="#8A8A8A"
    )
    vh_card.pack(padx=pad_vh, pady=pady_vh, fill="x")

    controls_card = tk.Frame(vh_wrapper, highlightthickness=1, highlightbackground="#8A8A8A")
    controls_card.pack(padx=pad_vh, pady=(0, pady_vh), fill="x")

    # -------------------------
    # Fuel section (always visible) — 2 columns
    # -------------------------
    fuel_frame = tk.Frame(controls_card, highlightthickness=1, highlightbackground="#DDD")
    fuel_frame.pack(fill="x", padx=0, pady=(3, 5))

    tk.Label(
        fuel_frame,
        text="Fuel",
        font=("Arial", 10, "bold"),
    ).pack(fill="x", anchor="center", padx=4, pady=(2, 2))

    def fuel_usage_color(val):
        # clamp 0..100
        v = max(0.0, min(100.0, float(val)))
        t = v / 100.0  # 0..1

        # 0%  -> nästan grå men lite röd tint (svagast möjligt utan att bli osynlig)
        r0, g0, b0 = 135, 125, 125
        # 100% -> neutral grå (vanilla)
        r1, g1, b1 = 145, 145, 145

        r = int(r0 + (r1 - r0) * t)
        g = int(g0 + (g1 - g0) * t)
        b = int(b0 + (b1 - b0) * t)
        return (r, g, b)

    def fuel_max_color(val):
        t = (val - 100) / 900.0 if val > 100 else 0.0
        t = max(0, min(1, t))
        if t < 0.4:
            u = t / 0.4
            r = int(128 * (1 - u))
            g = int(128 * (1 - u))
            b = int(128 + (255 - 128) * u)
        else:
            u = (t - 0.4) / 0.6
            r = int(160 * u)
            g = 0
            b = 255
        return (min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)))

    fuel_grid = make_two_column_grid(fuel_frame)
    fuel_grid.pack(fill="x", padx=4, pady=(0, 2))
    fuel_left = tk.Frame(fuel_grid)
    fuel_left.grid(row=0, column=0, sticky="ew", padx=GRID_COL_PADX, pady=GRID_ROW_PADY)
    fuel_right = tk.Frame(fuel_grid)
    fuel_right.grid(row=0, column=1, sticky="ew", padx=GRID_COL_PADX, pady=GRID_ROW_PADY)
    _fuel_color_bar_row(
        fuel_left, "Fuel usage (%)", fuel_usage_pct, 0, 100, 1, fuel_usage_color
    )
    _fuel_color_bar_row(
        fuel_right, "Fuel max (%)", fuel_max_pct, 100, 1000, 10, fuel_max_color
    )

    tk.Label(
        fuel_frame,
        text="100% = vanilla. Usage 0% = no drain. Max 1000% = 10× tank.",
        fg="#666666",
        font=("Arial", 8),
    ).pack(anchor="w", padx=8, pady=(2, 8))


    # --- Vehicle keybinds (2 columns) ---
    tk.Label(
        controls_card,
        text="Vehicle keybinds",
        font=("Arial", 10, "bold"),
    ).pack(anchor="w", pady=(6, 4))

    # Wrapper som håller två kolumner
    kb_wrap = tk.Frame(controls_card)
    kb_wrap.pack(fill="x", pady=(0, 2))

    kb_left = tk.Frame(kb_wrap)
    kb_left.pack(side="left", fill="both", expand=True)

    kb_right = tk.Frame(kb_wrap)
    kb_right.pack(side="left", fill="both", expand=True, padx=(9, 0))  # space mellan kolumner

    # Vänster kolumn
    ui_keybind_row(kb_left, "Throttle",        veh_throttle_bind,   "")
    ui_keybind_row(kb_left, "Brake",           veh_brake_bind,      "")
    ui_keybind_row(kb_left, "Turn left",       veh_left_bind,       "")
    ui_keybind_row(kb_left, "Turn right",      veh_right_bind,      "")
    ui_keybind_row(kb_left, "Handbrake",       veh_handbrake_bind,  "")
    ui_keybind_row(kb_left, "Leave vehicle",   veh_leave_bind,      "")

    # Höger kolumn
    ui_keybind_row(kb_right, "Change camera",      veh_camera_bind,   "")
    ui_keybind_row(kb_right, "Lights toggle",      veh_lights_bind,   "")
    ui_keybind_row(kb_right, "Look back",          veh_lookback_bind, "")
    ui_keybind_row(kb_right, "Horn",               veh_horn_bind,     "")
    ui_keybind_row(kb_right, "Redir safeh",        veh_redirect_bind, "")
    ui_keybind_row(kb_right, "UV lights",          veh_uv_bind,       "")

    tk.Label(
        controls_card,
        text="Note: In-game keybind settings may override these defaults. Reset binds in-game if needed.",
        fg="#666666",
        font=("Arial", 8),
        wraplength=560,
        justify="left",
    ).pack(anchor="w", pady=(4, 6))


    vh_hint = "100% = vanilla (no change). Max 1000%. Edits scripts/healthdefinitions.scr."
    tk.Label(
        vh_card,
        text="Vehicle health",
        font=("Arial", 11, "bold"),
    ).pack(pady=(6, 2))
    tk.Label(vh_card, text=vh_hint, fg="#666666", font=("Arial", 8)).pack(
        fill="x", pady=(0, 6)
    )

    def _centered_slider(parent, title, var, from_, to, resolution=1):
        outer = tk.Frame(parent)
        outer.pack(fill="x", pady=(0, 4))

        tk.Label(
            outer,
            text=title,
            font=("Arial", 9, "bold"),
            anchor="center",
            justify="center",
        ).pack(fill="x")

        # wrapper som centrerar hela slider+entry-blocket
        row_wrap = tk.Frame(outer)
        row_wrap.pack(fill="x", pady=1)

        row = tk.Frame(row_wrap)
        row.pack(anchor="center")   # <-- detta är nyckeln

        scale = tk.Scale(
            row,
            from_=from_,
            to=to,
            orient="horizontal",
            variable=var,
            showvalue=0,
            resolution=resolution,
            length=280,
        )
        scale.pack(side="left", padx=(0, 6))
        tk.Entry(row, width=5, textvariable=var, justify="right").pack(side="left")

        return outer


    vh_slider_grid = make_two_column_grid(vh_card)
    vh_slider_grid.pack(fill="x", pady=(0, 4))
    vh_cell0 = tk.Frame(vh_slider_grid)
    vh_cell0.grid(row=0, column=0, sticky="ew", padx=GRID_COL_PADX, pady=GRID_ROW_PADY)
    vh_cell1 = tk.Frame(vh_slider_grid)
    vh_cell1.grid(row=0, column=1, sticky="ew", padx=GRID_COL_PADX, pady=GRID_ROW_PADY)
    _centered_slider(
        vh_cell0, "Vehicle_Pickup (%) — default 1150 HP",
        veh_pickup_pct, 100, 1000, 10
    )
    _centered_slider(
        vh_cell1, "Vehicle_Pickup_CTB (%) — default 2000 HP",
        veh_pickup_ctb_pct, 100, 1000, 10
    )
    btn_reset_vh = tk.Button(vh_card, text="Reset Vehicles tab to defaults")
    btn_reset_vh.pack(pady=(6, 10))

    # =========================
    #   Volatiles tab Content (scrollable)
    # =========================
    vo_outer, vo_wrap = make_scrollable(volatiles_tab)
    vo_outer.pack(fill="both", expand=True)

    vo_card = tk.Frame(
        vo_wrap, highlightthickness=1, highlightbackground=CARD_HIGHLIGHT, highlightcolor=CARD_HIGHLIGHT
    )
    vo_card.pack(padx=60, pady=12, fill="x")

    tk.Label(
        vo_card,
        text="Volatile perception",
        font=("Arial", 12, "bold"),
    ).pack(pady=(10, 4))

    info_text = (
        "Vanilla = no change\n"
        "High→Low = High becomes Low, Low becomes Default\n"
        "High→Default = High becomes Default, Low becomes Default\n"
        "Calm = all profiles set to volatile_hive_resting\n"
        "Pacify = deletes selected Perception blocks (no attacks)"
    )

    tk.Label(
        vo_card,
        text=info_text,
        font=("Arial", 9),
        wraplength=470,
        justify="center",  # centers multi-line text
        anchor="center",
    ).pack(pady=(0, 10), padx=10)

    # --- Dropdown for volatiles ---
    vo_labels = [label for (label, value) in VO_MODE_OPTIONS]
    vo_values = [value for (label, value) in VO_MODE_OPTIONS]
    vo_label_to_value = {label: value for (label, value) in VO_MODE_OPTIONS}
    vo_value_to_label = {value: label for (label, value) in VO_MODE_OPTIONS}

    row = tk.Frame(vo_card)
    row.pack(pady=(6, 10))

    tk.Label(row, text="Volatile behavior:", font=("Arial", 10, "bold")).pack(
        side="left", padx=(0, 10)
    )

    vo_combo = ttk.Combobox(
        row,
        values=vo_labels,
        state="readonly",
        width=34,
    )

    vo_combo.set(vo_value_to_label.get(vo_mode_var.get(), vo_labels[0]))
    vo_combo.pack(side="left")

    def _on_vo_combo_change(_evt=None):
        label = vo_combo.get()
        vo_mode_var.set(vo_label_to_value[label])

    vo_combo.bind("<<ComboboxSelected>>", _on_vo_combo_change)

    # --- Alpha card section (Nightmare only) ---
    alpha_card = tk.Frame(
        vo_wrap, highlightthickness=1, highlightbackground=CARD_HIGHLIGHT, highlightcolor=CARD_HIGHLIGHT
    )
    alpha_card.pack(padx=60, pady=(0, 12), fill="x")

    # “badge” / Nightmare-only
    alpha_badge = tk.Frame(
        alpha_card, highlightbackground="#8A8A8A", highlightthickness=1, bd=0
    )
    alpha_badge.pack(pady=(10, 6))
    tk.Label(
        alpha_badge,
        text="Nightmare only — Alpha volatile",
        font=("Arial", 9),
        padx=12,
        pady=4,
    ).pack()

    alpha_radio_wrap = tk.Frame(alpha_card)
    alpha_radio_wrap.pack(fill="x", pady=(6, 12))

    alpha_radio_frame = tk.Frame(alpha_radio_wrap)
    alpha_radio_frame.pack()

    # --- Dropdown for ALPHA ---
    alpha_labels = [label for (label, value) in ALPHA_MODE_OPTIONS]
    alpha_label_to_value = {label: value for (label, value) in ALPHA_MODE_OPTIONS}
    alpha_value_to_label = {value: label for (label, value) in ALPHA_MODE_OPTIONS}

    alpha_row = tk.Frame(alpha_card)
    alpha_row.pack(pady=(6, 12))

    tk.Label(alpha_row, text="Alpha behavior:", font=("Arial", 10, "bold")).pack(
        side="left", padx=(0, 10)
    )

    alpha_combo = ttk.Combobox(
        alpha_row, values=alpha_labels, state="readonly", width=34
    )
    alpha_combo.set(alpha_value_to_label.get(alpha_mode_var.get(), alpha_labels[0]))
    alpha_combo.pack(side="left")

    def _on_alpha_combo_change(_evt=None):
        alpha_mode_var.set(alpha_label_to_value[alpha_combo.get()])

    alpha_combo.bind("<<ComboboxSelected>>", _on_alpha_combo_change)

    # --- Spawn scaling section (AIPresetPool) ---
    spawn_card = tk.Frame(
        vo_wrap, highlightthickness=1, highlightbackground=CARD_HIGHLIGHT, highlightcolor=CARD_HIGHLIGHT
    )
    spawn_card.pack(padx=60, pady=(0, 12), fill="x")

    # Volatile Weights checkbox (centered) — toggles visibility of weights section
    vo_weights_cb_frame = tk.Frame(spawn_card)
    vo_weights_cb_frame.pack(pady=(10, 4), fill="x")
    vo_weights_cb = tk.Checkbutton(
        vo_weights_cb_frame,
        text="Volatile Weights",
        variable=vo_weights_visible_var,
        font=("Arial", 9),
    )
    vo_weights_cb.pack(anchor="center")

    vo_weights_frame = tk.Frame(spawn_card)

    tk.Label(
        vo_weights_frame,
        text="Volatile weights (AIPresetPool)",
        font=("Arial", 11, "bold"),
    ).pack(pady=(10, 4))

    tk.Label(
        vo_weights_frame,
        text="100% = vanilla/off. Lower scales volatile weights in night pools.\n Experimental: actual spawn changes may be hard to notice without long playtesting;other systems may override pool weights.",
        font=("Arial", 9),
        wraplength=460,
        justify="center",
    ).pack(pady=(0, 8), padx=10)

    val_lbl = tk.Label(
        vo_weights_frame, text=f"{vo_reduce_pct_var.get()}%", font=("Arial", 10, "bold")
    )
    val_lbl.pack(pady=(0, 2))

    def _on_spawn_slider(_=None):
        val_lbl.config(text=f"{vo_reduce_pct_var.get()}%")

    spawn_slider = tk.Scale(
        vo_weights_frame,
        from_=2,
        to=100,  # percent
        orient="horizontal",
        resolution=1,
        variable=vo_reduce_pct_var,
        command=_on_spawn_slider,
        length=420,
    )
    spawn_slider.pack(pady=(0, 10))

    _on_spawn_slider()

    def _vo_weights_toggle(*_):
        if vo_weights_visible_var.get():
            vo_weights_frame.pack(fill="x", pady=(0, 4), after=vo_weights_cb_frame)
        else:
            vo_weights_frame.pack_forget()

    vo_weights_visible_var.trace_add("write", _vo_weights_toggle)
    _vo_weights_toggle()

    # --- Radio buttons: Volatile amount (Hive pools removal) ---
    tk.Label(
        spawn_card,
        text="Amount of volatiles",
        font=("Arial", 10, "bold"),
    ).pack(pady=(4, 2), anchor="center")
    VO_AMOUNT_OPTIONS = [
        ("x0 (vanilla)", "0"),
        ("x2 (less)", "x2"),
        ("x3 (less)", "x3"),
        ("x4 (less)", "x4"),
    ]
    rb_frame = tk.Frame(spawn_card)
    rb_frame.pack(pady=(0, 12), anchor="center")
    for label, value in VO_AMOUNT_OPTIONS:
        tk.Radiobutton(
            rb_frame,
            text=label,
            variable=vo_reduce_mult_var,
            value=value,
            font=("Arial", 9),
        ).pack(side="left", padx=10)

    # --- Volatile HP multipliers (healthdefinitions.scr) ---
    vo_hp_hint = "100% = vanilla. 20–300% range. Affects Volatile, Hive, Apex/Tyrant health."
    tk.Label(
        spawn_card,
        text="Volatile health multipliers",
        font=("Arial", 10, "bold"),
    ).pack(pady=(10, 2), fill="x")

    ui_labeled_slider(
        spawn_card,
        "Volatiles HP %",
        vo_hp_volatile_pct,
        from_=20,
        to=300,
        resolution=5,
    )
    ui_labeled_slider(
        spawn_card,
        "Hive Volatiles HP %",
        vo_hp_hive_pct,
        from_=20,
        to=300,
        resolution=5,
    )
    ui_labeled_slider(
        spawn_card,
        "Alpha & Tyrant HP %",
        vo_hp_apex_pct,
        from_=20,
        to=300,
        resolution=5,
    )
    tk.Label(spawn_card, text=vo_hp_hint, fg="#666666", font=("Arial", 8)).pack(
        fill="x", pady=(0, 6)
    )

    # --- Damage vs volatiles (per difficulty) ---
    vo_dmg_hint = "0 = vanilla, 100 = +100% (2.0x), 500 = +500% (6.0x)"
    tk.Label(
        spawn_card,
        text="Damage on volatiles multiplier ",
        font=("Arial", 10, "bold"),
    ).pack(pady=(10, 2), fill="x")
    ui_labeled_slider(
        spawn_card,
        "Easy",
        vo_dmg_bonus_easy_pct,
        from_=0,
        to=500,
        resolution=10,
    )
    ui_labeled_slider(spawn_card, "Normal", vo_dmg_bonus_normal_pct, from_=0, to=500, resolution=10)
    ui_labeled_slider(spawn_card, "Hard", vo_dmg_bonus_hard_pct, from_=0, to=500, resolution=10)
    ui_labeled_slider(spawn_card, "Nightmare", vo_dmg_bonus_nightmare_pct, from_=0, to=500, resolution=10)
    # show hint only once
    tk.Label(spawn_card, text=vo_dmg_hint, fg="#666666", font=("Arial", 8)).pack(
        fill="x", pady=(0, 8)
    )

    btn_reset_vo = tk.Button(spawn_card, text="Reset Volatiles tab to defaults")
    btn_reset_vo.pack(pady=(10, 14))

    # =========================
    # Enemies tab Content (scrollable, compact)
    # =========================
    en_outer, en_wrap = make_scrollable(enemies_tab)
    en_outer.pack(fill="both", expand=True)
    
    en_card = tk.Frame(
        en_wrap, highlightthickness=1, highlightbackground="#8A8A8A"
    )
    en_card.pack(padx=40, pady=8, fill="x")
    
    ENEMY_TAG_OPTIONS = [
        "Boss", "Freak", "Biter", "Biter_boss", "Spitter_boss", "Viral", "Demolisher",
        "Goon", "Slasher", "Defect", "Karen", "Behemoth", "Nemo", "Matriarch", "Daughter",
        "Hologram", "Superman", "Aiden", "Baron", "Beast",
    ]
    en_tag_hp_vars = []  # list of (tag_name, easy_var, normal_var, hard_var, nm_var)
    for tag in ENEMY_TAG_OPTIONS:
        en_tag_hp_vars.append((
            tag,
            tk.IntVar(value=100),
            tk.IntVar(value=100),
            tk.IntVar(value=100),
            tk.IntVar(value=100),
        ))

    en_header = tk.Frame(en_card)
    en_header.pack(fill="x", pady=(6, 2))
    tk.Label(
        en_header,
        text="Human Health Multiplier",
        font=("Arial", 12, "bold"),
    ).pack(pady=(10, 2), fill="x")
    en_reset_frame = tk.Frame(en_card)
    en_reset_frame.pack(fill="x", pady=(8, 4))
    btn_reset_en = tk.Button(en_reset_frame, text="Reset to defaults")
    btn_reset_en.pack(anchor="center")

    en_hp_hint = "100% = vanilla. 10% = 0.1× health, 500% = 5× health."
    en_hp_grid = make_two_column_grid(en_card)
    en_hp_grid.pack(fill="x", pady=(0, 4))
    for i, (label, var) in enumerate([
        ("Easy", en_human_hp_bonus_easy_pct),
        ("Normal", en_human_hp_bonus_normal_pct),
        ("Hard", en_human_hp_bonus_hard_pct),
        ("Nightmare", en_human_hp_bonus_nightmare_pct),
    ]):
        cell = tk.Frame(en_hp_grid)
        cell.grid(row=i // 2, column=i % 2, sticky="ew", padx=GRID_COL_PADX, pady=GRID_ROW_PADY)
        ui_labeled_slider(
            cell, label, var,
            from_=10, to=500, resolution=10,
            slider_length=220,
            label_width=9,      # <-- gör labeln smalare
            entry_width=5,      # valfritt
        )

    tk.Label(en_card, text=en_hp_hint, fg="#666666", font=("Arial", 8)).pack(
        fill="x", pady=(0, 6)
    )

    # --- Enemy tag health (per-tag multipliers, 20 tags × 4 sliders) ---
    tk.Label(
        en_card,
        text="Enemy Health Multiplier (per tag)",
        font=("Arial", 11, "bold"),
    ).pack(fill="x", anchor="center", pady=(10, 4))
    en_advanced_visible = [False]
    en_advanced_frame = tk.Frame(en_card)
    en_adv_scroll_outer, en_adv_scroll_inner = make_scrollable(en_advanced_frame)
    en_adv_scroll_outer.pack(fill="both", expand=True)
    for w in en_adv_scroll_outer.winfo_children():
        if isinstance(w, tk.Canvas):
            w.configure(height=380)
            break
    tk.Label(en_adv_scroll_inner, text="100% = vanilla. Set Easy/Normal/Hard/Nightmare % per tag.", fg="#666666", font=("Arial", 8)).pack(anchor="w", pady=(0, 6))
    for tag, easy_var, normal_var, hard_var, nm_var in en_tag_hp_vars:
        block = tk.Frame(en_adv_scroll_inner, highlightthickness=1, highlightbackground="#ddd")
        block.pack(fill="x", pady=(0, 6))
        tk.Label(block, text=tag, font=("Arial", 10, "bold"), anchor="center").pack(fill="x", padx=6, pady=(4, 2))
        tag_grid = make_two_column_grid(block)
        tag_grid.pack(fill="x", padx=4, pady=(0, 4))
        for j, (lbl, var) in enumerate([
            ("Easy %", easy_var), ("Normal %", normal_var), ("Hard %", hard_var), ("Nightmare %", nm_var),
        ]):
            cell = tk.Frame(tag_grid)
            cell.grid(row=j // 2, column=j % 2, sticky="ew", padx=GRID_COL_PADX, pady=GRID_ROW_PADY)
            ui_labeled_slider(cell, lbl, var, from_=10, to=500, resolution=5, label_width=10, font_title=("Arial", 9), slider_length=200)
        
    en_advanced_visible = [False]

    adv_wrap = tk.Frame(en_card)
    adv_wrap.pack(fill="x", pady=(4, 6))

    btn_en_advanced = tk.Button(
        adv_wrap,
        text="Show all sliders for enemies and bosses",
        font=("Arial", 10, "bold"),
    )
    btn_en_advanced.pack()  # centrerad i wrappern

    def toggle_en_advanced():
        if en_advanced_visible[0]:
            en_advanced_frame.pack_forget()
            btn_en_advanced.config(text="Show all sliders for enemies and bosses")
            en_advanced_visible[0] = False
        else:
            # visa advanced direkt under knappen (wrappern), snyggt & stabilt
            en_advanced_frame.pack(fill="both", expand=False, pady=(6, 8), after=adv_wrap)
            btn_en_advanced.config(text="Hide advanced enemy sliders")
            en_advanced_visible[0] = True

    btn_en_advanced.config(command=toggle_en_advanced)

    # --- Chase limit (moved from former Chase limit tab) ---
    chase_limit_visible = [False]
    chase_limit_btn_row = tk.Frame(en_card)
    chase_limit_btn_row.pack(fill="x", pady=(8, 4), after=adv_wrap)

    btn_chase_limit = tk.Button(
        chase_limit_btn_row,
        text="Show chase limit sliders",
        font=("Arial", 10, "bold"),
    )
    btn_chase_limit.pack()

    chase_limit_frame = tk.Frame(en_card, highlightthickness=1, highlightbackground="#8A8A8A")
    # chase_limit_frame not packed initially (hidden)

    tk.Label(
        chase_limit_frame,
        text="Chase limit — max zombies that can actively chase you (day and night).",
        font=("Arial", 9),
        fg="#666666",
        wraplength=500,
    ).pack(fill="x", padx=8, pady=(8, 4))

    ni_slider_specs = [
        ("Easy_Level1", ni_begin_l1, 0, 20),
        ("Slums_Level2", ni_begin_l2_slums_l1, 0, 20),
        ("Easy_Level3", ni_begin_l3, 0, 25),
        ("Easy_Slums_Lvl4", ni_begin_l4_slums_l3, 0, 30),
        ("Slums_Level2", ni_slums_l2, 0, 30),
        ("Slums_Level4", ni_slums_l4, 0, 40),
        ("OLDTOWN_Lvl1", ni_ot_l1, 0, 30),
        ("OLDTOWN_Lvl2", ni_ot_l2, 0, 30),
        ("OLDTOWN_Lvl3", ni_ot_l3, 0, 40),
        ("OLDTOWN_Lvl4", ni_ot_l4, 0, 50),
        ("Chase limit", sp_chase_limit, 0, 100),
    ]
    chase_grid = make_two_column_grid(chase_limit_frame)
    chase_grid.pack(fill="x", padx=8, pady=(0, 4))
    for i, (title, var, from_, to) in enumerate(ni_slider_specs):
        cell = tk.Frame(chase_grid)
        cell.grid(row=i // 2, column=i % 2, sticky="ew", padx=GRID_COL_PADX, pady=GRID_ROW_PADY)
        res = 5 if "Chase limit" in title else 1
        ui_labeled_slider(cell, title, var, from_=from_, to=to, resolution=res, slider_length=220)
    tk.Label(chase_limit_frame, text="Hard cap 100. Vanilla 15.", fg="#666666", font=("Arial", 8)).pack(fill="x", pady=(0, 2), padx=8)

    btn_reset_ni = tk.Button(chase_limit_frame, text="Reset Chase limit to defaults")
    btn_reset_ni.pack(pady=(10, 14))

    def toggle_chase_limit():
        if chase_limit_visible[0]:
            chase_limit_frame.pack_forget()
            btn_chase_limit.config(text="Show chase limit sliders")
            chase_limit_visible[0] = False
        else:
            chase_limit_frame.pack(fill="x", pady=(6, 8), after=chase_limit_btn_row)
            btn_chase_limit.config(text="Hide chase limit sliders")
            chase_limit_visible[0] = True

    btn_chase_limit.config(command=toggle_chase_limit)

    # --- Spawns section (DISABLED - no effect in game v1.5+) ---
    spawn_banner_frame = tk.Frame(
        en_card,
        bg="#fff1f1",
        highlightthickness=1,
        highlightbackground="#f2b8b8",
    )
    spawn_banner_frame.pack(fill="x", pady=(12, 6))

    # vänster accent-linje
    tk.Frame(spawn_banner_frame, bg="#d00000", width=6).pack(side="left", fill="y")

    spawn_banner_body = tk.Frame(spawn_banner_frame, bg="#fff1f1")
    spawn_banner_body.pack(side="left", fill="both", expand=True, padx=12, pady=10)

    tk.Label(
        spawn_banner_body,
        text="Spawns disabled (game v1.5+)",
        font=("Arial", 12, "bold"),
        fg="#2b2b2b",
        bg="#fff1f1",
        anchor="w",
    ).pack(fill="x")

    tk.Label(
        spawn_banner_body,
        text="Spawn-related tweaks currently have no effect due to game changes in v1.5+.\n"
             "I’ll re-enable this section if/when a reliable method becomes available.",
        font=("Arial", 9),
        fg="#444444",
        bg="#fff1f1",
        wraplength=650,
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(3, 0))


    preset_vars = [
        # --- XP ---
        ("mode", mode),
        ("openworld_var", openworld_var),
        ("legend_easy_var", legend_easy_var),
        ("legend_hard_var", legend_hard_var),
        ("legend_nightmare_var", legend_nightmare_var),
        ("xp_loss_scale_var", xp_loss_scale_var),
        ("ll_xp_loss_var", ll_xp_loss_var),
        ("advanced_var", advanced_var),
        ("legend_penalty_var", legend_penalty_var),
        ("ngplus_var", ngplus_var),
        ("coop_var", coop_var),
        ("quest_lp_var", quest_lp_var),
        # --- Flashlight ---
        ("flashlight_enabled_var", flashlight_enabled_var),
        ("nightmare_unlimited_var", nightmare_unlimited_var),
        ("flashlight_advanced_var", flashlight_advanced_var),
        ("pp_r", pp_r),
        ("pp_g", pp_g),
        ("pp_b", pp_b),
        ("uv_r", uv_r),
        ("uv_g", uv_g),
        ("uv_b", uv_b),
        ("uv12_drain_var", uv12_drain_var),
        ("uv12_energy_var", uv12_energy_var),
        ("fl_regen_delay_uv1_var", fl_regen_delay_uv1_var),
        ("fl_regen_delay_uv2_var", fl_regen_delay_uv2_var),
        ("uv3_drain_var", uv3_drain_var),
        ("uv3_energy_var", uv3_energy_var),
        ("uv3_regen_var", uv3_regen_var),
        ("uv4_drain_var", uv4_drain_var),
        ("uv4_energy_var", uv4_energy_var),
        ("uv4_regen_var", uv4_regen_var),
        ("uv5_drain_var", uv5_drain_var),
        ("uv5_energy_var", uv5_energy_var),
        ("uv5_regen_var", uv5_regen_var),
        # --- Hunger ---
        ("hunger_enabled_var", hunger_enabled_var),
        ("hu_cost_05", hu_cost_05),
        ("hu_cost_10", hu_cost_10),
        ("hu_cost_20", hu_cost_20),
        ("hu_cost_30", hu_cost_30),
        ("hu_cost_40", hu_cost_40),
        # --- Night ---
        ("night_enabled_var", night_enabled_var),
        ("ni_begin_l1", ni_begin_l1),
        ("ni_begin_l2_slums_l1", ni_begin_l2_slums_l1),
        ("ni_begin_l3", ni_begin_l3),
        ("ni_begin_l4_slums_l3", ni_begin_l4_slums_l3),
        ("ni_slums_l2", ni_slums_l2),
        ("ni_slums_l4", ni_slums_l4),
        ("ni_ot_l1", ni_ot_l1),
        ("ni_ot_l2", ni_ot_l2),
        ("ni_ot_l3", ni_ot_l3),
        ("ni_ot_l4", ni_ot_l4),
        ("volatiles_enabled_var", volatiles_enabled_var),
        ("alpha_enabled_var", alpha_enabled_var),
        ("alpha_mode_var", alpha_mode_var),
        ("vo_mode_var", vo_mode_var),
        ("vo_reduce_pct", vo_reduce_pct_var),
        ("vo_reduce_mult", vo_reduce_mult_var),
        ("vo_weights_visible", vo_weights_visible_var),
        ("vo_dmg_bonus_easy_pct", vo_dmg_bonus_easy_pct),
        ("vo_dmg_bonus_normal_pct", vo_dmg_bonus_normal_pct),
        ("vo_dmg_bonus_hard_pct", vo_dmg_bonus_hard_pct),
        ("vo_dmg_bonus_nightmare_pct", vo_dmg_bonus_nightmare_pct),
        ("vo_hp_volatile_pct", vo_hp_volatile_pct),
        ("vo_hp_hive_pct", vo_hp_hive_pct),
        ("vo_hp_apex_pct", vo_hp_apex_pct),
        ("veh_pickup_pct", veh_pickup_pct),
        ("veh_pickup_ctb_pct", veh_pickup_ctb_pct),
        ("en_human_hp_bonus_easy_pct", en_human_hp_bonus_easy_pct),
        ("en_human_hp_bonus_normal_pct", en_human_hp_bonus_normal_pct),
        ("en_human_hp_bonus_hard_pct", en_human_hp_bonus_hard_pct),
        ("en_human_hp_bonus_nightmare_pct", en_human_hp_bonus_nightmare_pct),
    ]
    for tag, easy_var, normal_var, hard_var, nm_var in en_tag_hp_vars:
        preset_vars.extend([
            (f"en_tag_hp_{tag}_easy_pct", easy_var),
            (f"en_tag_hp_{tag}_normal_pct", normal_var),
            (f"en_tag_hp_{tag}_hard_pct", hard_var),
            (f"en_tag_hp_{tag}_nm_pct", nm_var),
        ])
    preset_vars += [
        ("pl_water_speed_pct", pl_water_speed_pct),
        ("pl_land_speed_pct", pl_land_speed_pct),
        ("pl_boost_speed_pct", pl_boost_speed_pct),
        ("pl_ladder_climb_slow_var", pl_ladder_climb_slow_var),
        ("pl_fast_climb_enabled_var", pl_fast_climb_enabled_var),
        ("jump_boost_var", jump_boost_var),
        ("jump_override_var", jump_override_var),
        ("sp_dialog_limit", sp_dialog_limit),
        ("sp_chase_limit", sp_chase_limit),
    ]

    return {
        "notebook": notebook,
        "main_tab": main_tab,
        "xp_tab": xp_tab,
        "flashlight_tab": flashlight_tab,
        "btn_auto": btn_auto,
        "btn_select": btn_select,
        "callout_box": callout_box,
        "rb_ow": rb_ow,
        "rb_leg": rb_leg,
        "openworld_frame": openworld_frame,  # openworldXP
        "legend_frame": legend_frame,  # legend xp, penalties, bonus etc
        "btn_apply": btn_apply,
        "btn_build": btn_build,
        "status_frame": status_frame,
        "status_text": status_text,  # XP and Legend status
        "btn_row": btn_row,
        "btn_reset_xp": btn_reset_xp,  # reset xp values
        "btn_reset_fl": btn_reset_fl,  # reset flashlight values
        "btn_reset_hu": btn_reset_hu,  # reset hunger values
        "btn_reset_ni": btn_reset_ni,  # reset night values
        "btn_reset_pl": btn_reset_pl,  # reset player values
        "btn_reset_vo": btn_reset_vo,  # reset volatiles values
        "btn_reset_vh": btn_reset_vh,
        "btn_reset_en": btn_reset_en,
        "btn_hu_off": btn_hu_off,  # Hunger off
        "btn_restore_hunger": btn_restore_hunger,
        "btn_load_preset": btn_load_preset,
        "btn_save_preset": btn_save_preset,
        "preset_vars": preset_vars,
        "refresh_advanced": refresh_advanced,
        "refresh_flashlight_advanced": refresh_flashlight_advanced,
        "vo_reduce_pct_var": vo_reduce_pct_var,
        "save_path_var": save_path_var,
        "save_path_callout_box": save_path_callout_box,
        "veh_binds": veh_binds,
        "fuel_usage_pct": fuel_usage_pct,
        "fuel_max_pct": fuel_max_pct,
        "en_tag_hp_vars": en_tag_hp_vars,
        "jump_boost_var": jump_boost_var,
        "jump_override_var": jump_override_var,
    }
    



# -----------------------------
# 7) UI callbacks (apply, build, status, refresh)
# -----------------------------
def main():
    import shutil, os

    shutil.rmtree("scripts", ignore_errors=True)
    os.makedirs("scripts", exist_ok=True)

    ui = build_ui()

    openworld_frame = ui["openworld_frame"]
    legend_frame = ui["legend_frame"]
    status_text = ui["status_text"]
    btn_apply = ui["btn_apply"]
    btn_build = ui["btn_build"]
    btn_auto = ui["btn_auto"]
    btn_select = ui["btn_select"]
    callout_box = ui["callout_box"]
    btn_load_preset = ui.get("btn_load_preset")
    btn_save_preset = ui.get("btn_save_preset")
    preset_vars = ui.get("preset_vars", [])
    btn_reset_xp = ui["btn_reset_xp"]
    btn_reset_fl = ui["btn_reset_fl"]
    btn_reset_hu = ui["btn_reset_hu"]
    btn_reset_ni = ui["btn_reset_ni"]
    btn_reset_pl = ui["btn_reset_pl"]
    btn_reset_vo = ui["btn_reset_vo"]
    btn_reset_vh = ui["btn_reset_vh"]
    btn_reset_en = ui["btn_reset_en"]
    btn_hu_off = ui["btn_hu_off"]
    vo_reduce_pct_var = ui["vo_reduce_pct_var"]
    save_path_var = ui["save_path_var"]
    save_path_callout_box = ui["save_path_callout_box"]
    veh_binds = ui["veh_binds"]
    fuel_usage_pct = ui["fuel_usage_pct"]
    fuel_max_pct = ui["fuel_max_pct"]
    en_tag_hp_vars = ui["en_tag_hp_vars"]
    jump_boost_var = ui["jump_boost_var"]
    jump_override_var = ui["jump_override_var"]

    refresh_advanced = ui.get("refresh_advanced")
    refresh_flashlight_advanced = ui.get("refresh_flashlight_advanced")
    alpha_mode = alpha_mode_var.get()

    def get_patchers_for_build(veh_binds):
    
        player_patchers: List[Patcher] = []
        prog_patchers: List[Patcher] = []
        inv_patchers: List[Patcher] = []
        overlay_patchers: List[Patcher] = []
        hunger_patchers: List[Patcher] = []
        volatiles_patchers: List[Patcher] = []  # volatiles patchers
        night_patchers: List[Patcher] = []  # night chasers
        aipresetpool_patchers: List[Patcher] = []  # volatile reduce amount
        ai_difficulty_patchers: List[Patcher] = []  # ai_difficulty_modifiers.scr
        ai_spawn_priority_patchers: List[Patcher] = []  # ai_spawn_priority_system.scr
        ai_spawn_system_patchers: List[Patcher] = []  # ai_spawn_system_params.scr
        spawn_logic_patchers: List[Patcher] = []  # common_dynamic_spawn_logic_params.def
        densitiessettings_patchers: List[Patcher] = []  # densitiessettings.scr
        healthdefinitions_patchers: List[Patcher] = []  # healthdefinitions.scr
        fuel_patchers: List[Patcher] = []  # fuel params (usage/max) for all 3 buggy scripts

        inputs_keyboard_patchers: List[Patcher] = []  # inputs_keyboard.scr

        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_THROTTLE", to_input_token(veh_binds["throttle"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_BRAKE", to_input_token(veh_binds["brake"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_TURN_VEHICLE_LEFT", to_input_token(veh_binds["left"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_TURN_VEHICLE_RIGHT", to_input_token(veh_binds["right"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_HANDBRAKE", to_input_token(veh_binds["handbrake"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_VEHICLE_LEAVE", to_input_token(veh_binds["leave"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_VEHICLE_CHANGE_CAMERA", to_input_token(veh_binds["camera"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_CAR_LIGHTS_TOGGLE", to_input_token(veh_binds["lights"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_VEHICLE_LOOKBACK", to_input_token(veh_binds["lookback"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_HORN", to_input_token(veh_binds["horn"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_VEHICLE_REDIRECT_TO_SAFE_HOUSE", to_input_token(veh_binds["redirect"].get())))
        inputs_keyboard_patchers.append(patch_addaction_device_and_key("_ACTION_CAR_LIGHTS_UV", to_input_token(veh_binds["uv"].get())))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("ACTION_THROTTLE"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_BRAKE"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_TURN_VEHICLE_LEFT"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_TURN_VEHICLE_RIGHT"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_HANDBRAKE"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_VEHICLE_LEAVE"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_VEHICLE_CHANGE_CAMERA"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_CAR_LIGHTS_TOGGLE"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_VEHICLE_LOOKBACK"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_HORN"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_VEHICLE_REDIRECT_TO_SAFE_HOUSE"))
        inputs_keyboard_patchers.append(patch_disable_layout_keybinding_for_action("_ACTION_CAR_LIGHTS_UV"))


        # --- Hunger patches ---
        if hunger_enabled_var.get():
            hunger_patchers.append(
                patch_hunger_buckets(
                    cost_05=hu_cost_05.get(),
                    cost_10=hu_cost_10.get(),
                    cost_20=hu_cost_20.get(),
                    cost_30=hu_cost_30.get(),
                    cost_40=hu_cost_40.get(),
                )
            )

            is_off = (
                hu_decrease_speed.get() == 0.0
                and hu_mul_dash.get() == 0.0
                and hu_mul_fury.get() == 0.0
                and hu_resting_cost.get() == 0.0
                and hu_revived_cost.get() == 0.0
                and hu_cost_05.get() == 0.0
                and hu_cost_10.get() == 0.0
                and hu_cost_20.get() == 0.0
                and hu_cost_30.get() == 0.0
                and hu_cost_40.get() == 0.0
            )

        if is_off:
            player_patchers.append(
                patch_player_variables_hunger_extras(
                    decrease_speed=0.0,
                    starving_threshold=0.0,
                    resting_cost=0.0,
                    revived_cost=0.0,
                    mul_dash=0.0,
                    mul_fury=0.0,
                )
            )

            player_patchers.append(
                patch_player_variables_hunger_extras(
                    decrease_speed=hu_decrease_speed.get(),
                    starving_threshold=0.0,  #
                    resting_cost=hu_resting_cost.get(),
                    revived_cost=hu_revived_cost.get(),
                    mul_dash=hu_mul_dash.get(),
                    mul_fury=hu_mul_fury.get(),
                )
            )

            # player_variables.scr (Nightmare unlimited toggle)
            player_patchers.append(
                patch_unlimited_nightmare_flashlight(nightmare_unlimited_var.get())
            )

        if hunger_restore_full_var.get():
            player_patchers.append(patch_restore_hunger_to_full(1000.0))
            
        # Jump + fall
        player_patchers.append(
            lambda c, ui=ui: patch_jump_and_fall_direct(
                c,
                ui["jump_boost_var"].get(),
                ui["jump_override_var"].get()
            )
        )
        # -----------------
        # Alpha volatile (apex)
        # -----------------
        if alpha_enabled_var.get():
            alpha_mode = alpha_mode_var.get()

            if alpha_mode in ("vanilla", "none"):
                pass
            elif alpha_mode == "pacify":
                volatiles_patchers.append(
                    patch_delete_perception_profiles(
                        names=("volatile_apex", "volatile_apex_nightmare"),
                        exclude_names=("volatile_aiden",),
                    )
                )
            else:
                volatiles_patchers.append(
                    patch_ai_perception_profiles(
                        target_prefixes=("volatile_apex",),
                        mode=alpha_mode,
                        resting_profile="volatile_hive_resting",
                        exclude_names=("volatile_aiden",),
                    )
                )

        # -----------------
        # XP mode
        # -----------------
        if mode.get() == "openworld":
            player_patchers.append(patch_openworld_xp(openworld_var.get()))
        else:
            if ll_xp_loss_var.get() != 100:
                player_patchers.append(patch_ll_xp_loss_scale(ll_xp_loss_var.get()))

            prog_patchers.append(
                patch_legend_bonus(
                    legend_easy_var.get(),
                    legend_hard_var.get(),
                    legend_nightmare_var.get(),
                )
            )
            penalty_val = legend_penalty_var.get()
            if penalty_val == 1.0:
                prog_patchers.append(patch_legend_bonus_penalty_game_defaults())
            else:
                prog_patchers.append(patch_legend_bonus_penalty_universal(penalty_val))
            prog_patchers.append(patch_ngplus_multiplier(ngplus_var.get()))
            prog_patchers.append(patch_coop_multiplier(coop_var.get()))
            prog_patchers.append(patch_legendpoints_quest(quest_lp_var.get()))

        # XP loss override (death penalty levels)
        if xp_loss_override_var.get():
            player_patchers.append(
                patch_scale_death_penalty_levels(xp_loss_scale_var.get())
            )

        # -----------------
        # Player movement speed (player_variables.scr)
        # -----------------
        player_patchers.append(
            patch_player_movement_speed(
                water_pct=int(pl_water_speed_pct.get()),
                land_pct=int(pl_land_speed_pct.get()),
                boost_pct=int(pl_boost_speed_pct.get()),
            )
        )
        player_patchers.append(
            patch_player_climb_options(
                ladder_climb_slow=pl_ladder_climb_slow_var.get(),
                fast_climb_enabled=pl_fast_climb_enabled_var.get(),
            )
        )

        # -----------------
        # ai_difficulty_modifiers.scr (volatile damage + human HP)
        # -----------------
        ai_difficulty_patchers.append(
            patch_volatile_damage_bonus(
                bonus_easy_pct=int(vo_dmg_bonus_easy_pct.get()),
                bonus_normal_pct=int(vo_dmg_bonus_normal_pct.get()),
                bonus_hard_pct=int(vo_dmg_bonus_hard_pct.get()),
                bonus_nightmare_pct=int(vo_dmg_bonus_nightmare_pct.get()),
            )
        )
        ai_difficulty_patchers.append(
            patch_human_health_bonus(
                bonus_easy_pct=int(en_human_hp_bonus_easy_pct.get()),
                bonus_normal_pct=int(en_human_hp_bonus_normal_pct.get()),
                bonus_hard_pct=int(en_human_hp_bonus_hard_pct.get()),
                bonus_nightmare_pct=int(en_human_hp_bonus_nightmare_pct.get()),
            )
        )
        # Enemy tag health: one patcher per tag when not all 100%
        for tag, easy_var, normal_var, hard_var, nm_var in en_tag_hp_vars:
            e, n, h, nm = int(easy_var.get()), int(normal_var.get()), int(hard_var.get()), int(nm_var.get())
            if (e, n, h, nm) != (100, 100, 100, 100):
                ai_difficulty_patchers.append(
                    patch_enemy_tag_health_multipliers(
                        tag_name=tag,
                        easy_pct=e,
                        normal_pct=n,
                        hard_pct=h,
                        nm_pct=nm,
                    )
                )

        # -----------------
        # Spawn patchers (disabled when SPAWNS_SUPPORTED=False - no effect in game v1.5+)
        # -----------------
        if SPAWNS_SUPPORTED:
            if sp_advanced_tuning_var.get() and en_spawn_priority_var.get():
                ai_spawn_priority_patchers.append(
                    patch_param_value_optional("EnablePrioritizationOfSpawners", "true")
                )
            _adv = sp_advanced_tuning_var.get()
            _max_ai = int(sp_max_spawned_ai.get())
            _ag, _sp, _gp, _ap = _compute_spawn_limits_from_master(int(sp_dynamic_spawner_master.get()))
            ai_spawn_system_patchers.append(
                patch_ai_spawn_system(
                    max_spawned_ai=_max_ai,
                    auto_cache=True if not _adv else sp_auto_cache_var.get(),
                    manual_cache=int(sp_cache_manual.get()),
                    dialog_limit=50 if not _adv else int(sp_dialog_limit.get()),
                    chase_limit=min(100, int(sp_chase_limit.get())),
                    advanced_limits=_adv,
                    agenda_limit=_ag,
                    spawner_limit=_sp,
                    dynamic_limit=_sp,
                    challenge_limit=_gp,
                    gameplay_limit=_gp,
                    aiproxy_limit=_ap,
                    story_limit=_ag,
                    boost_darkzones=sp_boost_darkzones_var.get() if _adv else False,
                )
            )
            if _adv:
                _ai_density = int(sp_ai_density_max.get())
                spawn_logic_patchers.append(
                    patch_common_dynamic_spawn_logic(
                        spawn_radius_night=float(sp_spawn_radius_night.get()),
                        inner_radius_spawn=float(sp_inner_radius_spawn.get()),
                        ai_density_max=_ai_density,
                        ai_density_ignore=sp_ai_density_ignore_var.get(),
                    )
                )
            else:
                _sr, _ir, _adm, _adi = _compute_spawn_logic_from_max_ai(_max_ai)
                _ai_density = _adm
                spawn_logic_patchers.append(
                    patch_common_dynamic_spawn_logic(
                        spawn_radius_night=_sr,
                        inner_radius_spawn=_ir,
                        ai_density_max=_adm,
                        ai_density_ignore=_adi,
                        no_op=(_max_ai == 80),
                    )
                )
            densitiessettings_patchers.append(
                patch_global_densities_scaled_by_aidensity(_ai_density)
            )

        # -----------------
        # Volatile spawn scaling (aipresetpool)
        # -----------------
        pct = int(vo_reduce_pct_var.get())
        if pct != 100:
            aipresetpool_patchers.append(
                patch_volatile_weights_scale_for_pools(
                    pct=pct,
                    pools=EXTERIOR_NIGHT_VOLATILE_POOLS,
                    min_weight=2,
                )
            )

        # -----------------
        # Volatile dropdown perception
        # -----------------
        if volatiles_enabled_var.get():
            vo_mode = vo_mode_var.get()

            if vo_mode in ("vanilla", "none"):
                pass
            elif vo_mode == "pacify":
                volatiles_patchers.append(
                    patch_delete_perception_profiles(
                        names=(
                            "volatile_default",
                            "volatile_patrol_nightmare",
                            "volatile_patrol",
                            "volatile_nightmare",
                            "volatile_chase",
                            "volatile_chase_nightmare",
                            "volatile_sun_immune",
                        ),
                        exclude_names=(
                            "volatile_aiden",
                            "volatile_stinger",
                            "volatile_hive_default",
                            "volatile_hive_mq06",
                            "volatile_hive_nightmare",
                            "volatile_summoner_default",
                            "volatile_summoner_nightmare",
                            "alpha_zombie_default",
                        ),
                    )
                )
            else:
                volatiles_patchers.append(
                    patch_ai_perception_profiles(
                        target_prefixes=("volatile_",),
                        mode=vo_mode,
                        resting_profile="volatile_hive_resting",
                        exclude_names=(
                            "volatile_aiden",
                            "volatile_stinger",
                            "volatile_hive_default",
                        ),
                    )
                )

        # -----------------
        # Volatile HP multipliers (healthdefinitions.scr)
        # -----------------
        healthdefinitions_patchers.append(
            patch_volatile_health_multipliers(
                volatile_pct=int(vo_hp_volatile_pct.get()),
                hive_pct=int(vo_hp_hive_pct.get()),
                apex_pct=int(vo_hp_apex_pct.get()),
            )
        )
        healthdefinitions_patchers.append(
            patch_vehicle_health(
                vehicle_pickup_pct=int(veh_pickup_pct.get()),
                vehicle_pickup_ctb_pct=int(veh_pickup_ctb_pct.get()),
            )
        )

        # -----------------
        # Night patches
        # -----------------
        if night_enabled_var.get():
            night_patchers.append(
                patch_night_pursuit_caps(
                    pool_to_cap={
                        "Night_Aggresion_Level_1_Easy": ni_begin_l1.get(),
                        "Night_Aggresion_Level_2_Easy": ni_begin_l2_slums_l1.get(),
                        "Night_Aggresion_Level_3_Easy": ni_begin_l3.get(),
                        "Night_Aggresion_Level_4_Easy": ni_begin_l4_slums_l3.get(),
                        "Night_Aggresion_Level_1": ni_begin_l2_slums_l1.get(),
                        "Night_Aggresion_Level_2": ni_slums_l2.get(),
                        "Night_Aggresion_Level_3": ni_begin_l4_slums_l3.get(),
                        "Night_Aggresion_Level_4": ni_slums_l4.get(),
                        "Old_Town::Night_Aggresion_Level_1": ni_ot_l1.get(),
                        "Old_Town::Night_Aggresion_Level_2": ni_ot_l2.get(),
                        "Old_Town::Night_Aggresion_Level_3": ni_ot_l3.get(),
                        "Old_Town::Night_Aggresion_Level_4": ni_ot_l4.get(),
                    }
                )
            )

        # -----------------
        # Flashlight patches
        # -----------------
        if flashlight_enabled_var.get():
            overlay_patchers.append(
                patch_varvec3(
                    "v_flashlight_pp_color", pp_r.get(), pp_g.get(), pp_b.get()
                )
            )
            overlay_patchers.append(
                patch_varvec3(
                    "v_flashlight_pp_uv_color", uv_r.get(), uv_g.get(), uv_b.get()
                )
            )
            player_patchers.append(
                patch_unlimited_nightmare_flashlight(nightmare_unlimited_var.get())
            )
            inv_patchers.extend(
                patch_flashlight_grouped(
                    lvl1=FlashlightParams(
                        uv12_drain_var.get(),
                        uv12_energy_var.get(),
                        fl_regen_delay_uv1_var.get(),
                    ),
                    lvl2=FlashlightParams(
                        uv12_drain_var.get(),
                        uv12_energy_var.get(),
                        fl_regen_delay_uv2_var.get(),
                    ),
                    lvl3=FlashlightParams(
                        uv3_drain_var.get(), uv3_energy_var.get(), uv3_regen_var.get()
                    ),
                    lvl4=FlashlightParams(
                        uv4_drain_var.get(), uv4_energy_var.get(), uv4_regen_var.get()
                    ),
                    lvl5=FlashlightParams(
                        uv5_drain_var.get(), uv5_energy_var.get(), uv5_regen_var.get()
                    ),
                )
            )

        # inventory_special.scr (UV LVL 1–5)
        inv_patchers.extend(
            patch_flashlight_grouped(
                lvl1=FlashlightParams(
                    drain_per_second=uv12_drain_var.get(),
                    max_energy=uv12_energy_var.get(),
                    regen_delay=fl_regen_delay_uv1_var.get(),
                ),
                lvl2=FlashlightParams(
                    drain_per_second=uv12_drain_var.get(),
                    max_energy=uv12_energy_var.get(),
                    regen_delay=fl_regen_delay_uv2_var.get(),
                ),
                lvl3=FlashlightParams(
                    drain_per_second=uv3_drain_var.get(),
                    max_energy=uv3_energy_var.get(),
                    regen_delay=uv3_regen_var.get(),
                ),
                lvl4=FlashlightParams(
                    drain_per_second=uv4_drain_var.get(),
                    max_energy=uv4_energy_var.get(),
                    regen_delay=uv4_regen_var.get(),
                ),
                lvl5=FlashlightParams(
                    drain_per_second=uv5_drain_var.get(),
                    max_energy=uv5_energy_var.get(),
                    regen_delay=uv5_regen_var.get(),
                ),
            )
        )

        if fuel_usage_pct.get() != 100:
            fuel_patchers.append(patch_paramfloat_mul("fuel_usage_base", fuel_usage_pct.get() / 100.0))
        if fuel_max_pct.get() != 100:
            fuel_patchers.append(patch_paramfloat_mul("fuel_max_amount", fuel_max_pct.get() / 100.0))

        return (
            player_patchers,
            prog_patchers,
            inv_patchers,
            overlay_patchers,
            hunger_patchers,
            night_patchers,
            volatiles_patchers,
            aipresetpool_patchers,
            ai_difficulty_patchers,
            ai_spawn_priority_patchers,
            ai_spawn_system_patchers,
            spawn_logic_patchers,
            densitiessettings_patchers,
            healthdefinitions_patchers,
            inputs_keyboard_patchers,
            fuel_patchers,
    )    
        

    def do_reset_xp():
        cur_mode = mode.get()
        reset_defaults(DEFAULTS_XP)
        mode.set(cur_mode)

        applied_ok.set(False)
        if callable(refresh_advanced):
            refresh_advanced()
        refresh_buttons()
        update_mode()
        set_status([(" Reset XP tab to defaults.", "warn")])

    def do_reset_fl():
        reset_defaults(DEFAULTS_FL)
        applied_ok.set(False)
        if callable(refresh_flashlight_advanced):
            refresh_flashlight_advanced()
        refresh_buttons()
        set_status([(" Reset Flashlight tab to defaults.", "warn")])

    def do_reset_hu():
        reset_defaults(DEFAULTS_HU)
        applied_ok.set(False)
        refresh_buttons()
        set_status([(" Reset Hunger tab to defaults.", "warn")])

    def do_reset_ni():
        reset_defaults(DEFAULTS_NI)
        applied_ok.set(False)
        refresh_buttons()
        set_status([(" Reset Nightspawn tab to defaults.", "warn")])

    def do_reset_pl():
        reset_defaults(DEFAULTS_PL)
        applied_ok.set(False)
        refresh_buttons()
        set_status([(" Reset Player tab to defaults.", "warn")])

    def do_reset_vo():
        reset_defaults(DEFAULTS_VO)
        applied_ok.set(False)
        refresh_buttons()
        set_status([(" Reset Volatiles tab to defaults.", "warn")])

    def do_reset_vh():
        reset_defaults(DEFAULTS_VH)
        # Keybinds
        veh_binds["throttle"].set("W")
        veh_binds["brake"].set("S")
        veh_binds["left"].set("A")
        veh_binds["right"].set("D")
        veh_binds["handbrake"].set("Space")
        veh_binds["leave"].set("F")
        veh_binds["camera"].set("V")
        veh_binds["lights"].set("T")
        veh_binds["lookback"].set("CapsLock")
        veh_binds["horn"].set("H")
        veh_binds["redirect"].set("R")
        veh_binds["uv"].set("Mouse3")
        # Fuel
        fuel_usage_pct.set(100)
        fuel_max_pct.set(100)
        applied_ok.set(False)
        refresh_buttons()
        set_status([(" Reset Vehicles tab to defaults.", "warn")])

    def do_reset_en():
        reset_defaults(DEFAULTS_EN)
        for _tag, easy_var, normal_var, hard_var, nm_var in en_tag_hp_vars:
            easy_var.set(100)
            normal_var.set(100)
            hard_var.set(100)
            nm_var.set(100)
        applied_ok.set(False)
        refresh_buttons()
        refresh_enemies_spawn = ui.get("refresh_enemies_spawn_ui")
        if callable(refresh_enemies_spawn):
            refresh_enemies_spawn()
        set_status([(" Reset Enemies tab to defaults.", "warn")])

    btn_reset_xp.config(command=do_reset_xp)
    btn_reset_fl.config(command=do_reset_fl)
    btn_reset_hu.config(command=do_reset_hu)
    btn_reset_ni.config(command=do_reset_ni)
    btn_reset_pl.config(command=do_reset_pl)
    btn_reset_vo.config(command=do_reset_vo)
    btn_reset_vh.config(command=do_reset_vh)
    btn_reset_en.config(command=do_reset_en)

    def _write_status(widget, parts):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        for text, tag in parts:
            widget.insert("end", text, tag)
        widget.config(state="disabled")

    def set_status(parts):
        _write_status(status_text, parts)

    def do_load_preset():
        path = filedialog.askopenfilename(
            title="Load preset",
            filetypes=[("JSON preset", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            preset_apply(preset_vars, data)
            applied_ok.set(False)

            if callable(refresh_advanced):
                refresh_advanced()
            if callable(refresh_flashlight_advanced):
                refresh_flashlight_advanced()

            update_mode()
            refresh_buttons()
            set_status([(" Preset loaded — press Apply", "warn")])

        except Exception as e:
            messagebox.showerror("Load preset failed", str(e))

    def do_save_preset():
        path = filedialog.asksaveasfilename(
            title="Save preset",
            defaultextension=".json",
            filetypes=[("JSON preset", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            data = preset_dump(preset_vars)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            set_status([(" Preset saved ✔", "ok")])

        except Exception as e:
            messagebox.showerror("Save preset failed", str(e))

    # wire preset✅
    if btn_load_preset:
        btn_load_preset.config(command=do_load_preset)
    if btn_save_preset:
        btn_save_preset.config(command=do_save_preset)

    def on_spawn_scale_change(*_):
        applied_ok.set(False)
        refresh_buttons()
        set_status(
            [(f" Volatile spawns: {vo_reduce_pct_var.get()}% — press Apply", "warn")]
        )

        vo_reduce_pct_var.trace_add("write", on_spawn_scale_change)

    def refresh_buttons(*_):
        path = game_path_var.get()
        path_ok = bool(path) and os.path.isdir(os.path.join(path, "ph_ft", "source"))

        btn_apply.config(state=("normal" if path_ok else "disabled"))
        btn_build.config(
            state=("normal" if (path_ok and applied_ok.get()) else "disabled")
        )
        if path_ok:
            callout_box.config(highlightthickness=0)
        else:
            callout_box.config(highlightthickness=2, highlightbackground="#d00000")

        if not path_ok:
            set_status(
                [
                    (
                        " No game folder set (or invalid). Please select the game folder.",
                        "warn",
                    )
                ]
            )

    def on_vo_mode_change(*_):
        applied_ok.set(False)
        refresh_buttons()
        set_status(
            [(" Volatile perception: " + vo_mode_var.get() + " — press Apply", "warn")]
        )

    vo_mode_var.trace_add("write", on_vo_mode_change)

    def on_alpha_mode_change(*_):
        applied_ok.set(False)
        refresh_buttons()
        set_status(
            [(" Alpha volatile: " + alpha_mode_var.get() + " — press Apply", "warn")]
        )

    alpha_mode_var.trace_add("write", on_alpha_mode_change)

    def do_hunger_off():
        try:
            #
            hunger_enabled_var.set(True)

            #
            for v in (hu_cost_05, hu_cost_10, hu_cost_20, hu_cost_30, hu_cost_40):
                v.set(0.0)

            hu_decrease_speed.set(0.0)  # HungerPointsDecreaseSpeed
            hu_mul_dash.set(0.0)  # HungerPointsDecreaseSpeedMulDash
            hu_mul_fury.set(0.0)  # HungerPointsDecreaseSpeedMulFury
            hu_resting_cost.set(0.0)  # HungerRestingCost
            hu_revived_cost.set(0.0)  # HungerRevivedCost

            applied_ok.set(False)
            refresh_buttons()
            set_status(
                [(" Hunger disabled (all costs set to 0) — press Apply", "warn")]
            )

        except Exception as e:
            messagebox.showerror("Hunger off failed", str(e))

    btn_hu_off.config(command=do_hunger_off)

    def do_restore_hunger():
        hunger_restore_full_var.set(True)
        set_status(
            [
                (
                    " Restore hunger to full: enabled — press Apply, then Build & Install",
                    "ok",
                )
            ]
        )

    btn_restore_hunger = ui.get("btn_restore_hunger")
    if btn_restore_hunger:
        btn_restore_hunger.config(command=do_restore_hunger)

    def mark_dirty(*_):
        if applied_ok.get():
            set_status([(" Settings changed — press Apply", "warn")])
        applied_ok.set(False)
        refresh_buttons()


    def update_mode(*_):
        openworld_frame.pack_forget()
        legend_frame.pack_forget()
        if mode.get() == "openworld":
            advanced_var.set(False)
            if callable(refresh_advanced):
                refresh_advanced()
            openworld_frame.pack(fill="x", padx=20, pady=4)
        else:
            legend_frame.pack(fill="both", expand=True, padx=16, pady=2)
        mark_dirty()

    def apply():
        try:
            if mode.get() == "openworld":
                set_status(
                    [
                        ("  Open World settings ready ", "ok"),
                        (
                            f"({openworld_var.get()}x, XP loss {xp_loss_scale_var.get()}%) ",
                            "ok",
                        ),
                        (" | Press Build & Install", "warn"),
                    ]
                )
            else:
                set_status(
                    [
                        (" Legend settings ready ", "ok"),
                        (f"| E/N:{legend_easy_var.get()}x, ", "ok"),
                        (f"H:{legend_hard_var.get()}x, ", "ok"),
                        (f"N:{legend_nightmare_var.get()}x, ", "ok"),
                        (f"LL XP loss {ll_xp_loss_var.get()}% ", "ok"),
                        (" | Press Build & Install", "warn"),
                    ]
                )

            applied_ok.set(True)
            refresh_buttons()

        except Exception as e:
            applied_ok.set(False)
            refresh_buttons()
            set_status([("Error: ", "warn"), (str(e), "warn")])
            
 
    def build_and_install(_veh_binds=veh_binds):
        try:
            clear_scripts()
            # HARD RESET: se till att inga gamla skript följer med i paken
            shutil.rmtree("scripts", ignore_errors=True)
            os.makedirs("scripts", exist_ok=True)

            # delete generated overlay file (optional)
            overlay_out = "scripts/varlist_game_overlay.scr"
            if os.path.exists(overlay_out):
                os.remove(overlay_out)

            (
                player_patchers,
                prog_patchers,
                inv_patchers,
                overlay_patchers,
                hunger_patchers,
                night_patchers,
                volatiles_patchers,
                aipresetpool_patchers,
                ai_difficulty_patchers,
                ai_spawn_priority_patchers,
                ai_spawn_system_patchers,
                spawn_logic_patchers,
                densitiessettings_patchers,
                healthdefinitions_patchers,
                inputs_keyboard_patchers,
                fuel_patchers,
            ) = get_patchers_for_build(_veh_binds)

            write_player_variables(player_patchers)
            deploy_enabled_mod_files(Path(game_path_var.get().strip()))
            if prog_patchers:
                write_progression_actions(prog_patchers)
            if inv_patchers:
                write_inventory_special(inv_patchers)
            if overlay_patchers:
                write_varlist_game_overlay(overlay_patchers)
            if hunger_patchers:
                write_player_hunger_config(hunger_patchers)
            if night_patchers:
                write_player_nightspawn_config(night_patchers)
            if volatiles_patchers:
                write_player_volatiles_config(volatiles_patchers)
            if aipresetpool_patchers:
                write_aipresetpool_config(aipresetpool_patchers)
            write_ai_difficulty_modifiers(ai_difficulty_patchers)
            if SPAWNS_SUPPORTED:
                write_ai_spawn_priority_system(ai_spawn_priority_patchers)
                write_ai_spawn_system_params(ai_spawn_system_patchers)
                if spawn_logic_patchers:
                    write_common_dynamic_spawn_logic(spawn_logic_patchers)
                write_densitiessettings(densitiessettings_patchers)

            write_healthdefinitions(healthdefinitions_patchers)
            write_inputs_keyboard(inputs_keyboard_patchers)
            write_fuel_params(
                "templates/buggy_defender_fuel_params.scr",
                "scripts/vehicles/buggy_defender_fuel_params.scr",
                fuel_patchers,
            )
            write_fuel_params(
                "templates/buggy_madriders_fuel_params.scr",
                "scripts/vehicles/buggy_madriders_fuel_params.scr",
                fuel_patchers,
            )
            write_fuel_params(
                "templates/buggy_wasteland_fuel_params.scr",
                "scripts/vehicles/buggy_wasteland_fuel_params.scr",
                fuel_patchers,
            )

            build_pak()
            install_pak(game_path_var.get())
            backup_player_save(save_path_var.get())
            hunger_restore_full_var.set(False)
            if SPAWNS_SUPPORTED:
                set_status([(" PAK built & installed successfully ✔", "ok")])
            else:
                set_status([
                    (" PAK built & installed successfully ✔ ", "ok"),
                    (" + Save backup created.", "ok"),
                ])

        except Exception as e:
            set_status([(" Error: ", "warn"), (str(e), "warn")])
            
    def autodetect_and_set():
        try:
            path = auto_detect_game_folder()
            game_path_var.set(path)
            save_game_path(path)
            set_status([(" Game folder auto-detected: ", "ok"), (path, "ok")])
            refresh_buttons()
        except Exception as e:
            set_status([(" Auto-detect failed: ", "warn"), (str(e), "warn")])

    def choose_game_folder():
        path = filedialog.askdirectory(title="Select Dying Light The Beast folder")
        if path:
            game_path_var.set(path)
            save_game_path(path)
            refresh_buttons()
                        
    def backup_player_save(src_str: str):
        src_str = (src_str or "").strip()
        if not src_str:
            return

        src = Path(src_str)
        if not src.exists():
            messagebox.showerror("Invalid save path", f"Selected save path does not exist:\n{src}")
            return

        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dst = BACKUPS_DIR / f"save_backup_{stamp}"

        try:
            shutil.copytree(src, dst)
        except Exception as e:
            messagebox.showerror("Backup failed", f"Could not backup saves:\n{e}")



    # wire buttons
    btn_auto.config(command=autodetect_and_set)
    btn_select.config(command=choose_game_folder)
    btn_apply.config(command=apply)
    btn_build.config(command=build_and_install)

    if btn_load_preset:
        btn_load_preset.config(command=do_load_preset)
    if btn_save_preset:
        btn_save_preset.config(command=do_save_preset)

    def update_save_path_callout(*_):
        path_set = bool((save_path_var.get() or "").strip())
        if path_set:
            save_path_callout_box.config(highlightthickness=0)
        else:
            save_path_callout_box.config(highlightthickness=2, highlightbackground="#d00000")
    update_save_path_callout()
    save_path_var.trace_add("write", update_save_path_callout)

    # traces
    game_path_var.trace_add("write", lambda *_: refresh_buttons())

    mode.trace_add("write", update_mode)

    openworld_var.trace_add("write", mark_dirty)

    legend_easy_var.trace_add("write", mark_dirty)
    legend_hard_var.trace_add("write", mark_dirty)
    legend_nightmare_var.trace_add("write", mark_dirty)
    xp_loss_scale_var.trace_add("write", mark_dirty)
    ll_xp_loss_var.trace_add("write", mark_dirty)
    legend_penalty_var.trace_add("write", mark_dirty)
    ngplus_var.trace_add("write", mark_dirty)
    coop_var.trace_add("write", mark_dirty)
    quest_lp_var.trace_add("write", mark_dirty)

    flashlight_enabled_var.trace_add("write", mark_dirty)
    nightmare_unlimited_var.trace_add("write", mark_dirty)
    flashlight_advanced_var.trace_add("write", mark_dirty)

    pp_r.trace_add("write", mark_dirty)
    pp_g.trace_add("write", mark_dirty)
    pp_b.trace_add("write", mark_dirty)
    uv_r.trace_add("write", mark_dirty)
    uv_g.trace_add("write", mark_dirty)
    uv_b.trace_add("write", mark_dirty)

    uv12_drain_var.trace_add("write", mark_dirty)
    uv12_energy_var.trace_add("write", mark_dirty)
    fl_regen_delay_uv1_var.trace_add("write", mark_dirty)
    fl_regen_delay_uv2_var.trace_add("write", mark_dirty)

    uv3_drain_var.trace_add("write", mark_dirty)
    uv3_energy_var.trace_add("write", mark_dirty)
    uv3_regen_var.trace_add("write", mark_dirty)

    uv4_drain_var.trace_add("write", mark_dirty)
    uv4_energy_var.trace_add("write", mark_dirty)
    uv4_regen_var.trace_add("write", mark_dirty)

    uv5_drain_var.trace_add("write", mark_dirty)
    uv5_energy_var.trace_add("write", mark_dirty)
    uv5_regen_var.trace_add("write", mark_dirty)

    hunger_enabled_var.trace_add("write", mark_dirty)
    hu_cost_05.trace_add("write", mark_dirty)
    hu_cost_10.trace_add("write", mark_dirty)
    hu_cost_20.trace_add("write", mark_dirty)
    hu_cost_30.trace_add("write", mark_dirty)
    hu_cost_40.trace_add("write", mark_dirty)
    night_enabled_var.trace_add("write", mark_dirty)
    hu_decrease_speed.trace_add("write", mark_dirty)
    hu_mul_dash.trace_add("write", mark_dirty)
    hu_mul_fury.trace_add("write", mark_dirty)
    hu_resting_cost.trace_add("write", mark_dirty)
    hu_revived_cost.trace_add("write", mark_dirty)
    vo_mode_var.trace_add("write", mark_dirty)
    vo_weights_visible_var.trace_add("write", mark_dirty)
    vo_hp_volatile_pct.trace_add("write", mark_dirty)
    vo_hp_hive_pct.trace_add("write", mark_dirty)
    vo_hp_apex_pct.trace_add("write", mark_dirty)
    veh_pickup_pct.trace_add("write", mark_dirty)
    veh_pickup_ctb_pct.trace_add("write", mark_dirty)
    pl_ladder_climb_slow_var.trace_add("write", mark_dirty)
    pl_fast_climb_enabled_var.trace_add("write", mark_dirty)
    pl_land_speed_pct.trace_add("write", mark_dirty)
    pl_water_speed_pct.trace_add("write", mark_dirty)
    pl_boost_speed_pct.trace_add("write", mark_dirty)
    en_spawn_priority_var.trace_add("write", mark_dirty)
    en_human_hp_bonus_easy_pct.trace_add("write", mark_dirty)
    en_human_hp_bonus_normal_pct.trace_add("write", mark_dirty)
    en_human_hp_bonus_hard_pct.trace_add("write", mark_dirty)
    en_human_hp_bonus_nightmare_pct.trace_add("write", mark_dirty)
    sp_max_spawned_ai.trace_add("write", mark_dirty)
    sp_auto_cache_var.trace_add("write", mark_dirty)
    sp_dialog_limit.trace_add("write", mark_dirty)
    sp_chase_limit.trace_add("write", mark_dirty)
    sp_cache_manual.trace_add("write", mark_dirty)
    sp_advanced_tuning_var.trace_add("write", mark_dirty)
    sp_boost_darkzones_var.trace_add("write", mark_dirty)
    sp_dynamic_spawner_master.trace_add("write", mark_dirty)
    sp_spawn_radius_night.trace_add("write", mark_dirty)
    sp_inner_radius_spawn.trace_add("write", mark_dirty)
    sp_ai_density_max.trace_add("write", mark_dirty)
    sp_ai_density_ignore_var.trace_add("write", mark_dirty)

    # init
    ensure_dirs()
    game_path_var.set(load_game_path())
    update_mode()
    refresh_buttons()

    root.mainloop()


# -----------------------------
# 8) main()
# -----------------------------
if __name__ == "__main__":
    main()
