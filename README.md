# DLTB Configurator
GUI mod tool to build & install custom PAK tweaks for **Dying Light: The Beast**  
XP • Flashlight • Hunger • Volatiles • Enemies • Vehicles • Keybinds • **Mods (3rd party)**

> **Status:** Beta  
> **Spawns:** Disabled since game v1.5+ (game-side changes)

---

## ✅ Download
Go to **Releases** and download the latest build:
- **DLTB Configurator.exe** (Windows)

---

## 🚀 Quick start (EXE)
### Core workflow
1. Run **DLTB Configurator.exe**
2. Set **Game Folder** (required)
3. (Optional) Set **Save Folder** (for automatic save backups)
4. Click **Apply → Build & Install PAK**
5. Launch the game (Steam button in the tool or start normally)

### 3rd party mods workflow (NEW)
1. Go to the **Mods** tab
2. **Install Archive** (zip/7z/rar) or pick a **Recommended Nexus Mod**
3. Click **Deploy to Game** (copies `.rpack`, `dataN.pak`, `.asi/.dll` to the correct game folders)
4. **Run Super Mod Merger** *(required if you installed 3rd party mods)*
5. Then use **Apply → Build & Install PAK** as usual

> The tool avoids popups — check the **status bar** at the bottom for next steps and results.

---

## ✨ Features
### UI / Quality-of-life (NEW)
- Darker UI theme
- Top toolbar (preset / save-path / game-folder actions)
- Small tab header icons
- Status bar feedback (no “Done!” popups)

### Mods (3rd party) (NEW)
- **Recommended Nexus Mods** list (open Files page + Mod Manager download)
- Install mod archives to `mods/installed/<mod>/raw`
- Deploy supported files to game folders:
  - `assets_?_pc.rpack` → `...\ph_ft\work\data_platform\pc\assets` (slots max 5)
  - `dataN.pak` → `...\ph_ft\source` (slots max 7)
  - `.asi/.dll` → `...\ph_ft\work\bin\x64`
- `.scr` mods are merged into scripts before build (Param() merge logic)
- Super Mod Merger launcher/help for 3rd party mods

### Movement / Player (NEW)
- Jump height tuning
- Movement speed up to **300%**

### XP
- Open World XP multiplier
- Legend XP multipliers (difficulty-based)
- NG+ / Coop multipliers

### Flashlight
- UV levels tuning (drain / max energy / regen delays)
- Post-process flashlight colors (regular + UV)
- Nightmare unlimited toggle

### Hunger
- Tuning buckets + extra modifiers
- One-click restore (if supported by current game build)

### Volatiles
- Perception/profile tuning (pacify / resting / etc.)
- Health multipliers for volatile/hive/apex

### Enemies / Bosses
- Human health multipliers per difficulty
- Advanced: per-tag health multipliers (boss, freak, biter, demolisher, etc.)

### Vehicles
- Vehicle health scaling (pickup / CTB)
- Fuel usage + fuel max sliders
- Vehicle keybind editing (keyboard + mouse tokens)

---

## 🖼 Screenshots
Put images in `/docs/` and link them here.

| Tab | Preview |
|---|---|
| Main / Toolbar | ![Main](docs/main.png) |
| Mods | ![Mods](docs/mods.png) |
| Vehicles | ![Vehicles](docs/vehicles.png) |
| Enemies | ![Enemies](docs/enemies.png) |

---

## ⚠ Notes / Limitations
- **Spawns disabled since v1.5+** (game-side changes break spawn edits)
- Some keybinds depend on the game’s enum tokens:
  - `EKey__...` / `EMouse__...` are defined in `data0.pak/scripts/inputs/inputenums.def`
- In-game keybind settings may override defaults (reset binds in-game if needed)
- If using 3rd party mods: **Deploy → Run Super Mod Merger → Build & Install PAK**

---

## 🛠 Build from source (Developers)
### Requirements
- Python 3.10+
- Dependencies:
  - Pillow
  - numpy
  - psutil
  - (others if you use them)

Install:
```bash
pip install -r requirements.txt
