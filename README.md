# UE-Style Viewport Navigation for Blender

Fly through the Blender viewport the way you do in Unreal Engine: hold the right mouse button to look around, move with WASD, rise and sink with E and Q, and change the camera speed with the mouse wheel. A sidebar tab gives you UE-style camera speed, mouse settings and an editable viewport transform.

Single-file add-on, no dependencies. Tested on Blender 5.1 (macOS); requires Blender 4.2 or newer.

## Controls

| Input | Action |
|---|---|
| Hold **RMB** + move mouse | Look around |
| Hold **RMB** + **W / A / S / D** | Move forward / left / back / right |
| Hold **RMB** + **Q / E** | Move down / up |
| Hold **RMB** + **mouse wheel** | Camera speed 1–8 |
| **Shift / Ctrl** while flying | 3× faster / 0.3× slower |
| Short **RMB** click (no drag) | Blender's normal context menu |
| **Alt + LMB** | Orbit * |
| **Alt + RMB** | Dolly * |
| **MMB** | Pan * |
| **F** (Object Mode) | Focus selected * |
| **G** | Game View: hide/show grid, axes, outlines, light/camera lines and gizmos ** |

\*\* G replaces Blender's Grab shortcut (use the Move tool, or pick *Shift + `* / *None* under **Game View Key** in the sidebar or add-on preferences).

\* Optional UE mouse mapping, on by default. It changes Blender defaults (MMB pans instead of orbiting), so it can be switched off in the sidebar or in the add-on preferences.

Flying works in Object, Edit (mesh, curve, armature, lattice, metaball), Pose and Particle modes. Sculpt and paint modes are left untouched because RMB opens brush panels there.

## Sidebar: N › UE Nav

- **Camera Speed & Mouse** – Game View on/off button, camera speed slider (1–8, from 0.25 to 32 m/s), speed multiplier, mouse sensitivity, invert mouse Y, UE mouse mapping on/off, Game View key.
- **Viewport Transform** – the eye position (X/Y/Z), yaw and pitch of the viewport, all editable, plus the viewport lens and a *Level View* button.
- **Scene Camera** – align the active camera to the current view, or look through it.
- **Shortcuts** – a short reminder of the controls.

## Installation

1. Download [`ue_style_navigation.py`](ue_style_navigation.py).
2. In Blender: **Edit › Preferences › Add-ons**, open the drop-down at the top right, choose **Install from Disk…** and select the file.
3. Enable **UE-Style Viewport Navigation**.

To update, install the new file the same way; Blender replaces the old one.

## Notes

- If you fly while looking through the scene camera, the viewport switches to a free perspective view first; the camera itself does not move. Use *Align Active Camera to View* to place it.
- When you release RMB, the orbit pivot is put back in front of you, so Alt+LMB / MMB orbiting continues naturally from where you stopped.
- Settings are stored in the add-on preferences and persist when Blender saves its preferences.

## License

GPL-3.0-or-later, as required for Blender add-ons. See [LICENSE](LICENSE).
