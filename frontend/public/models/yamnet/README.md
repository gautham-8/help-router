# YAMNet (vendored)

On-device sound-event classifier used by the caller page. Committed to the repo on purpose
so the app works offline and from a clean clone.

| File | What it is | Source |
|---|---|---|
| `model.json`, `group1-shard*.bin` | YAMNet as a TensorFlow.js graph model (about 15 MB) | TF Hub `google/tfjs-model/yamnet/tfjs/1` (https://tfhub.dev/google/tfjs-model/yamnet/tfjs/1) |
| `yamnet_class_map.csv` | Class number to name (521 classes) | https://github.com/tensorflow/models/tree/master/research/audioset/yamnet |

## Licenses and attribution

- YAMNet source code (tensorflow/models): Apache License 2.0.
- The 521 class names come from Google's **AudioSet ontology**, licensed
  **CC BY-SA 4.0** (https://research.google.com/audioset/download.html). Attribution:
  "AudioSet ontology, Google LLC, CC BY-SA 4.0".
- The model weights were trained on the AudioSet corpus. The TF Hub model page does not state
  a separate license for the weight files; confirm the terms on the model's page before
  relying on this for anything beyond the hackathon.

## Notes for developers

- Input: mono 16 kHz float32 in [-1, 1]. Output: three tensors (spectrogram, embeddings,
  scores) in an order the TF.js export does not promise. Find the scores by their last
  dimension (521), as `src/lib/sounds.ts` does.
- Scores are **not calibrated probabilities** (per the model card). The app's cut-off
  (`EVENT_MIN_CONFIDENCE` in `src/lib/sounds.ts`) is a rough choice checked only on
  synthetic tones, not tuned on real emergency recordings.
- Do not edit these files. If you replace the model, re-run `npm run test`: the tests check
  that every class name the app depends on still exists.
