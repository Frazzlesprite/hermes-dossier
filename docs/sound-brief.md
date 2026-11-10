# Sound brief: Dossier demo, 66 seconds

Built to `sound-design-film` (Walter Murch) with the beat sheet from `video/references/edit-anatomy.md`.

## Emotional journey

| Time | Beat | What the viewer should feel |
|---|---|---|
| 0:00-0:05 | You have a meeting in 45 minutes | Mild alarm, recognition |
| 0:05-0:18 | Command, sources land | Momentum, competence |
| 0:18-0:31 | The brief | Trust: this is a real document |
| 0:31-0:43 | Same evidence, different questions | The idea lands |
| 0:43-0:52 | Zero changes | Relief, honesty |
| 0:52-0:59 | The PDF | Something to hold |
| 0:59-1:06 | Install line | Confidence |

## Sound hierarchy for this piece

Murch's order, applied:

1. **Dialogue.** Seven voiceover lines. Nothing is allowed to cover a consonant.
2. **Key story sounds.** The six source rows landing, the command keystrokes, the zero on the diff. These mark the moments the picture depends on.
3. **Music.** Trance bed at 140 BPM. Supports pace, never competes.
4. **Effects.** Scene-change whooshes, riser into the drop, final hit.
5. **Foley and ambience.** Room tone under everything, so the mix has a floor instead of starting from digital silence.

## Layer count by section (Law of Two and a Half)

| Section | Layers | Count | Why |
|---|---|---|---|
| Hook | voice, ambience, pad | 3 | Clarity, the line has to land |
| Command | voice, music, keystrokes, ambience | 4 | Momentum |
| Sources | voice, music, ticks, ambience | 4 | Story sounds on each row |
| Brief | voice, music, ambience | 3 | Dialogue-heavy, keep it clear |
| Split | voice, music, ticks, ambience | 4 | Emotional peak |
| Diff | voice, music, thud, ambience | 4 then 2 | The thud, then space |
| PDF | voice, music, ambience | 3 | Clarity |
| Close | voice, music, hit, ambience | 4 | Intentional threshold crossing |

Nothing runs at five layers except the last three seconds.

## Worldizing

There is no real room to record in, so the space is synthesised: a 1.6 second impulse response of decaying noise with early reflections, convolved over the music bus at 18 percent and the voice at 8 percent. Ambience is a low band of brown noise with a slow amplitude wander, at about -34 dBFS, so it reads as a room rather than a hiss.

## Technical

- 44.1 kHz, 16-bit, stereo.
- Voice ducks the music by 86 percent and the ambience by 50 percent.
- Master: DC removal, soft limit, peak at or under 0.85, then measured and reported rather than assumed.
- Stems: music, voice, effects, ambience. Levels printed at build time.
