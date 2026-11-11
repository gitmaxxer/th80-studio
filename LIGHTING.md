# TH80 Pro V2 lighting

Control uses the native 48-byte block. On this keyboard, VIA lighting queries just echoed the request back. The GMK87 projects are a useful reference for the native protocol, but that model's features and effect names do not prove support on the TH80.

| Byte, counted from zero | Use | Evidence on the TH80 |
| --- | --- | --- |
| 1 | Effect ID | IDs 1, 3, 13 and 16 captured; changes confirmed |
| 2 | Brightness, 0 to 9 | Captures, writes and visual confirmation |
| 3 | Speed | Levels 2 and 4 captured; changes confirmed |
| 5 | Color mode | 0 for RGB; 255 in one captured rainbow state |
| 6, 7, 8 | Red, green, blue, each 0 to 255 | Change #68FF00 → #35FF00 confirmed visually |
| 9 | Auxiliary color field | Changes along with the shortcuts; meaning not decoded yet |

## Custom color

HEX is a way of writing the three RGB channels: #0066FF means R=0, G=102, B=255. The wheel uses HSV for visual picking and converts the result to RGB. Its lightness control changes the color itself, while the brightness on the main tab controls the keyboard's backlight.

Picking a color on the wheel sends nothing. Click Use color and then Apply lighting. The app reads the current configuration, saves a copy, sets byte 5 to zero and bytes 6–8 to the chosen color. It keeps byte 9 and every other setting, and requires a matching final read. Whether arbitrary RGB looks right still needs a physical test on this TH80; some effects may ignore the chosen color.

## Learned catalog

Earlier captures are imported into lighting-catalog.json when the app opens. Add current state reads the keyboard, without writing to it, and records the effect, speed and color block it sees. To grow the list, change only the effect or the speed with the physical shortcuts and add the state. A capture proves the state was observed; reproducing it still needs visual confirmation.

Captured colors reproduce the original five bytes 5–9. A custom color keeps auxiliary field 9. The current catalog holds four effects, two speed levels and ten color states; three of the color states have been confirmed visually by the user.

## References and limits

- [gmk87-node, protocol code](https://github.com/codedgar/gmk87-node/blob/main/src/lib/device.js): reads the same offsets and edits a copy of the current configuration. Its RGB builder keeps byte 9.
- [Lighting documentation](https://codedgar.github.io/gmk87-node/how-to/configure-lighting/): documents RGB, brightness 0–9, speed 0–9 and 19 effects for the GMK87. On that model speed 0 is fastest and 9 slowest; this has not been confirmed across the whole range on the TH80.
- [GMK87 effect list](https://codedgar.github.io/gmk87-node/how-to/lighting-presets/): IDs 0–18, including static color, breathing, waves and reactive effects. The names are not used as confirmed names on the TH80.
- [GMK87-Tool](https://github.com/pihomeserver/GMK87-Tool): another implementation of RGB and effect control over HID.
- [gmk87-usb-reverse](https://github.com/ikkentim/gmk87-usb-reverse): reverse-engineering reference for the protocol.

There is no evidence that this is a universal keyboard standard. It is a proprietary HID protocol family with similarities across these devices. Auxiliary LEDs, effect direction and the full set of GMK87 IDs are not enabled in this app without validation on the TH80.
