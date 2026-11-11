# TH80 Studio 🎹

**Your keyboard, your photo, your keys, your colors.**

Open-source desktop configurator for the **EPOMAKER TH80 Pro V2**, using a USB connection and an English interface in graphite and blue. Upload images and GIFs, set the clock, remap keys and control the lighting without Epomaker's Image Custom Tool.

> English translation of [Clouddios/th80-studio](https://github.com/Clouddios/th80-studio), which is in Portuguese. The USB protocol and app logic are unchanged; only the interface text, messages, docs and local log/file names were translated.

![Sample GIF for the keyboard screen](assets/clawd-typing.gif)

> Independent project, not affiliated with EPOMAKER. Validated on a TH80 Pro V2 on Windows. macOS and Linux have not been validated on the hardware yet.

## What it does

| Tab | Features |
| --- | --- |
| Screen & GIF | Preview, fit to 240 × 135 and upload images or animations |
| Clock | Sync the computer's date and time; return to the saved image |
| Keys | Read four layers, edit any of the 79 keys and undo the last change |
| Lighting | Brightness 0–9, observed effects and speeds, color states, color wheel and HEX |
| Manual | English guide, physical shortcuts and a link to the official manual |

## Installing on Windows

You need **Python 3.12 with Tcl/Tk**, installed from the [official Python site](https://www.python.org/downloads/windows/), and the keyboard connected over USB.

1. Download the project with **Code → Download ZIP**, or clone it:

   ```powershell
   git clone https://github.com/gitmaxxer/th80-studio.git
   cd th80-studio
   ```

2. Double-click **Install.cmd**. It creates a `.venv` environment and installs Pillow and hidapi.
3. Run **Open.cmd**.
4. Put the keyboard's mode switch in the middle, connect the USB cable and close other configurators, including VIA.
5. Click **Connect keyboard**.

You can also install manually, without activating the environment in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

The project uses no machine-specific paths. This version runs through Python; there is no signed `.exe` installer yet.

## Photo and GIF

Open **Screen & GIF**, choose a file, check the preview and send it. The sample [clawd-typing.gif](assets/clawd-typing.gif) is already in the screen's format.

- Resolution: **240 × 135 pixels**.
- Images are center-cropped; transparency is composited over black.
- GIFs are fitted to **at most 18 frames per slot**, with one uniform frame time of at least 60 ms. This is a conservative app limit, not the device's proven maximum.
- Uploading replaces **both image slots**. The app saves the previous configuration but **does not copy the old images**.
- Keep the cable connected until it finishes.

## Clock and keys

In **Clock**, send the computer's local time. The clock preview in the app shows the computer's clock; it does not continuously read the keyboard's time.

In **Keys**, read the layer before editing. Click a key, choose the function and apply. The app checks the current value, saves the previous one and verifies the write by reading it back. **Undo last change** restores only the last key, and only if it still has the value the app applied.

Letters, numbers, F1–F12, navigation keys and modifiers are available. Macros and key combinations have no editor yet.

## Lighting and HEX colors

1. Click **Check lighting**.
2. Set the brightness and choose an effect, speed or color. **Keep current** leaves that setting unchanged.
3. For any RGB color, open **Color wheel / HEX** and pick on the wheel or type a code such as `#0066FF`.
4. Click **Use color** and then **Apply lighting**. Picking on the wheel does not send anything by itself.

The color can depend on the active effect. Brightness, effect and speed changes, and three color states, were confirmed on the physical keyboard. Arbitrary RGB has automated tests and read-back verification; how it looks still needs physical confirmation.

The catalog starts with the known states. To grow it, change the effect or speed with the physical shortcuts and click **Add current state**. That button **only reads** the keyboard. Local captures are imported when the app opens.

See [LIGHTING.md](LIGHTING.md) for the protocol offsets and for what was observed on the TH80 versus what comes from other keyboards.

## Keyboard shortcuts

| Shortcut | Default action per the TH80 Pro V2 manual |
| --- | --- |
| Fn + Backspace | Lighting on/off |
| Fn + `\` | Cycle RGB effects |
| Fn + ↑ / ↓ | Adjust brightness |
| Fn + → / ← | Adjust hue |
| Fn + = / - | Adjust speed |
| Fn + [ / ] | Adjust saturation |
| Fn + Enter | Switch screen content |
| Fn + X | Screen on/off |
| Fn + A / S | Windows / Mac mode |

Source: [EPOMAKER's official manual](https://epomaker.com/blogs/manuals/th80-pro-v2-manual). Remapping keys can change how the shortcuts behave.

## Compatibility and troubleshooting

The app selects the product **EPOMAKER TH80 Pro V2**, VID `320F`, PID `5055`, on specific HID interfaces. Similar IDs on another model don't guarantee compatibility. Connect only one keyboard of this model at a time.

If the keyboard isn't found, check the cable and the switch position, and close other configurators. Bluetooth and the 2.4 GHz receiver are not supported in this version. The code avoids reset, bootloader and firmware commands; it doesn't require disabling Windows protections or removing drivers.

Results and configuration backups are written locally to `result-*.json`, `*-before-*.json` and the `logs-*` folders. Git ignores them. The app does not send them to any telemetry service. Review the logs before attaching them to an issue.

## Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py"
.\.venv\Scripts\python.exe app.py --check-ui
```

The tests exercise USB packets, transfers, animations, the clock, the VIA keymap, settings preservation, the catalog and color conversion, replacing the USB boundary with simulated devices. They are not a substitute for confirmation on the physical keyboard.

| File | Responsibility |
| --- | --- |
| `app.py`, `ui.py` | Operations and Tkinter interface |
| `protocol.py`, `transfer.py` | Native packets, acknowledgement and transfers |
| `via.py`, `keyboard_layout.py` | VIA and key layout |
| `media.py` | Image and GIF preparation |
| `color_wheel.py`, `lighting_catalog.py` | RGB selection and observed catalog |
| `manual.py` | Built-in guide |

Contributions are welcome: tests on more units, effect mapping, Windows packaging and validated macOS/Linux support. Include the exact model, OS, steps and expected result when opening an issue.

## Credits and license

Project code under the [MIT license](LICENSE). Original project by [Clouddios](https://github.com/Clouddios/th80-studio). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for protocol references and dependencies.

Thanks to [gmk87-node](https://github.com/codedgar/gmk87-node), [gmk87-usb-reverse](https://github.com/ikkentim/gmk87-usb-reverse), [GMK87-Tool](https://github.com/pihomeserver/GMK87-Tool) and [QMK](https://github.com/qmk/qmk_firmware). Features from other models are references, not confirmed support on the TH80.
