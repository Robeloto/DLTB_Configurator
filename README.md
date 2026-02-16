

# DLTB Configurator
GUI mod tool to build & install custom PAK tweaks for **Dying Light: The Beast**  
XP • Flashlight • Hunger • Volatiles • Enemies • Vehicles • Keybinds

> **Status:** Beta  
> **Spawns:** Disabled since game v1.5+ (game-side changes)

---

## ✅ Download
Go to **Releases** and download the latest build:
- **DLTB Configurator.exe** (Windows)

---

## 🚀 Quick start (EXE)
1. Run **DLTB Configurator.exe**
2. Set **Game Folder** (required)
3. (Optional) Set **Save Folder** (for automatic save backups)
4. Click **Apply → Build & Install PAK**
5. Launch the game (Steam button in the tool or start normally)

---

## ✨ Features
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

### Quality-of-life
- Auto-detect game folder
- Auto-detect save folder + optional backups
- One-click Build & Install PAK
- Launch game via Steam

---

## 🖼 Screenshots
> Tip: Put images in `/docs/` or `/screenshots/` and link them here.

| Tab | Preview |
|---|---|
| Vehicles | ![Vehicles](docs/vehicles.png) |
| Enemies | ![Enemies](docs/enemies.png) |

---

## ⚠ Notes / Limitations
- **Spawns disabled since v1.5+** (game-side changes break spawn edits)
- Some keybinds depend on the game’s enum tokens:
  - `EKey__...` / `EMouse__...` are defined in `data0.pak/scripts/inputs/inputenums.def`
- In-game keybind settings may override defaults (reset binds in-game if needed)

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
