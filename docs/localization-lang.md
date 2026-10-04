# localization.lang — the 19-byte locale selector

One of the smallest files in the install, and a tidy little RE exercise:
the game's active-language state in 19 bytes.

## Bytes (measured)

| Offset | Bytes | Meaning |
|---|---|---|
| `0x00` | `4c 41 4e 47` | `"LANG"` magic |
| `0x04` | `0d 00 00 20 02` | record 1 |
| `0x09` | `0d 00 00 20 02` | record 2 — identical to r1 |
| `0x0E` | `00 00 20 02 0d` | record 3 |

## Structure

| Offset | Size | Content |
|---|---|---|
| 0 | 4 | magic `"LANG"` |
| 4 | 5 | record 1: `0D 00 00 20 02` |
| 9 | 5 | record 2: `0D 00 00 20 02` (identical to r1) |
| 14 | 5 | record 3: `00 00 20 02 0D` |

## Observations

- Exactly three 5-byte records — matching the game's three concurrent
  language slots (voice / subtitle / menu, by observation of the settings
  screen), though which record is which has **not** been verified.
- `20 02` recurs in every record at a fixed 5-byte pitch — consistent with a
  small per-slot payload (e.g. a 16-bit value `0x0220` plus flags), not with
  a string.
- Records 1–2 identical, record 3 differs only in byte 0 (`0D` vs `00`) and
  a rotation of the trailing byte — the layout suggests
  `flag:1 + id:2 + spare:2` per record, little-endian.
- Total file size 19 B, no terminator, no checksum.

## Status

| Claim | Evidence |
|---|---|
| magic `LANG`, 3×5 B records, exact bytes above | ✅ measured from the file |
| "three slots = voice/subtitle/menu" | ⚠️ plausible, unverified |
| field split `flag+id+spare` | ⚠️ hypothesis — decode pattern only |

Experiment for anyone with their own copy: flip one byte at a time, boot,
and note which of the three language settings changes — 15 bytes means at
most 15·255 trials to a full map.
