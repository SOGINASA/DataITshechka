# CQA demo media assets

## Headset photograph

- File: `headset-editorial.jpg` (768 × 768 pixels, JPEG).
- Created with the built-in `image_gen` tool, generation mode; no reference image and no CLI generation.
- Optimized by technical resize and JPEG conversion after generation.
- Intended use: a small dashboard/import thumbnail.

Exact final prompt:

> Use case: photorealistic-natural. Asset type: a small editorial photograph used as a 120–180 px thumbnail in a professional conversation-quality dashboard and upload dialog. Create one square photograph of a real, modest matte-black customer-support headset with a slim microphone boom, resting naturally beside one closed cream paper notebook on a light neutral desk. A small forest-green fabric detail under the notebook provides a restrained brand accent. Soft daylight from a nearby window, believable gentle shadows, tactile slightly imperfect materials, calm documentary product photography. Close composition with headset clearly readable at thumbnail size, enough breathing room around it. No people, no hands, no text, no letters, no logos, no UI, no watermark. Avoid glossy CGI, 3D clay, floating objects, exaggerated props, dramatic gradients or advertising hero composition.

## Synthetic demonstration audio

- File: `demo-call.m4a`.
- Title: **Демонстрационная запись — синтез речи**.
- Source: the existing seeded `call-ru-024` conversation, containing 12 client/operator messages. This is synthesized demonstration speech, not a recorded customer call.
- Voice: macOS `Milena`, a stock Russian system voice; no voice cloning or impersonation.
- Method: each phrase synthesized locally using `say`, with client rate 190 and operator rate 180; phrase starts aligned to the seeded transcript timestamps; role tracks mixed and encoded with FFmpeg as AAC mono, 22,050 Hz, 64 kbps. No network TTS service was used.
- Duration: **186 seconds (03:06)**, including the original gaps between phrases and a short ending pad.
- Phrase start offsets in seconds: `0, 12, 29, 46, 75, 91, 128, 138, 154, 165, 176, 182`.
- Verification: FFprobe confirmed format/duration; a complete FFmpeg decode completed without errors.

## Role waveforms

- File: `demo-call-waveform.json`.
- Contains the actual audio RMS envelopes of the aligned client and operator tracks: 310 bins per role, 0.6 seconds per bin, normalized per role with a 0.7 power curve. Silent intervals remain zero.
- Includes duration, synthetic-source metadata and each message's offset and synthesized duration.

Ship only this manifest, the JPG, the M4A and the waveform JSON. Audio generation intermediates are not product assets.
