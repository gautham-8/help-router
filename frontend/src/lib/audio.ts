// Audio decoding for the on-device sound classifier.

export const SAMPLE_RATE = 16_000;

// Decodes a recorded blob (webm/opus, mp4, ogg...) into 16 kHz mono float samples in
// [-1, 1], which is what YAMNet expects. Decoding happens at the browser's native rate,
// then an OfflineAudioContext resamples and mixes down to mono.
export async function decodeTo16kMono(blob: Blob): Promise<Float32Array> {
  const decodeContext = new AudioContext();
  try {
    const decoded = await decodeContext.decodeAudioData(await blob.arrayBuffer());
    const frames = Math.max(1, Math.ceil(decoded.duration * SAMPLE_RATE));
    const offline = new OfflineAudioContext(1, frames, SAMPLE_RATE);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();
    return rendered.getChannelData(0);
  } finally {
    await decodeContext.close();
  }
}
