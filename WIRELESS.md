# Wireless testing: 2.4 GHz and Bluetooth

TH80 Studio (and Epomaker's own tools) only configure the keyboard over the USB cable. `wireless_probe.py` tests whether the same private channels are reachable over the 2.4 GHz receiver or Bluetooth. If they are, wireless support can be added to the app.

## What it checks

The app uses two private HID channels. HID is the standard USB protocol keyboards use; these "vendor" channels sit next to the normal keystroke channel.

| Channel | Usage page | Used for | Probe query (read-only) |
| --- | --- | --- | --- |
| Screen | `0xFF1C` | Images, GIFs, clock, lighting | Command 5: read the 48-byte settings block |
| VIA | `0xFF60` | Key remapping | Command 1: get VIA protocol version |

Over each connection, the probe reports whether each channel exists and whether it answers. If the screen channel answers, it also times the round trip and estimates how long an image upload would take.

**Safety.** `list`, `snapshot`, `diff` and `probe` never write settings. They send only the two read queries above, and by default only to Epomaker devices. A receiver with an unknown ID is probed only when you name it with `--device`. The `clock` command is the only write, and it asks you to confirm first.

## Test plan

Run everything from the project folder. `Probe.cmd` runs the probe with the project's Python; adding arguments works the same, e.g. `Probe.cmd list --all`.

### 1. Baseline over USB

Cable connected, mode switch in the middle:

```
Probe.cmd probe
```

Expected: `USB: screen channel ANSWERED, VIA channel ANSWERED`. This proves the probe works on your machine.

### 2. Find the 2.4 GHz receiver

Unplug the cable, then:

```
Probe.cmd snapshot no-receiver
```

Plug in the 2.4 GHz receiver, move the switch to the 2.4 GHz side and press a key so it wakes up. Then:

```
Probe.cmd snapshot receiver
Probe.cmd diff no-receiver receiver
```

The new entries are the receiver. Note its VID:PID, e.g. `320f:5088`, and any lines marked `private channel`, `screen channel` or `VIA channel`.

### 3. Probe over 2.4 GHz

```
Probe.cmd probe --device VID:PID
```

Use the receiver's VID:PID from step 2.

### 4. Bluetooth

Unplug the receiver, move the switch to Bluetooth and pair the keyboard in your OS settings. Then repeat steps 2 and 3, using snapshot names like `no-bt` and `bt`. Over Bluetooth the keyboard may keep the TH80's own ID, so `Probe.cmd probe` without `--device` may already find it.

### 5. Optional write test (only if step 3 or 4 answered)

```
Probe.cmd clock --device VID:PID
```

This sets the keyboard clock over that connection and reads it back. It's the smallest real configuration change.

## Reading the results

| Result | Meaning |
| --- | --- |
| Channel `not found` | The firmware doesn't expose it on this connection. Wireless configuration isn't possible without a firmware change. |
| `no answer` | The channel exists, but the receiver or keyboard doesn't pass the query through. Usually also a firmware limit. The saved report descriptor can still show a different report format worth trying. |
| `ANSWERED` | Wireless configuration is possible. The upload-time estimate shows whether images are practical or only small changes like the clock and lighting. |

Each run saves a JSON report in `probe-results/`. These include report descriptors (the device's description of its own data formats), which are what's needed to dig further if a channel exists but stays silent. Git ignores the folder.

## Platform notes

- **Windows:** Bluetooth keyboards connect as "Bluetooth LE" HID devices. Windows blocks access to the keystroke channel, but private channels stay reachable when the keyboard exposes them.
- **macOS:** the first run may ask for Input Monitoring permission.
- **Linux:** needs a udev rule for `hidraw` access, or run with `sudo`.
