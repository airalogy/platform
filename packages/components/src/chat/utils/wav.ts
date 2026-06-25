export function writeString(view: DataView, offset: number, string: string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i))
  }
}

export function floatTo16BitPCM(output: DataView, offset: number, input: Float32Array) {
  for (let i = 0; i < input.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, input[i]))
    output.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true)
  }
}

export function audioBufferToWav(buffer: AudioBuffer): Blob {
  const numChannels = 1 // Force mono for STT to save bandwidth
  const sampleRate = buffer.sampleRate
  const format = 1 // PCM
  const bitDepth = 16

  // Downmix to mono if necessary
  let data: Float32Array
  if (buffer.numberOfChannels === 1) {
    data = buffer.getChannelData(0)
  }
  else {
    const left = buffer.getChannelData(0)
    const right = buffer.getChannelData(1)
    data = new Float32Array(left.length)
    for (let i = 0; i < data.length; i++) {
      data[i] = (left[i] + right[i]) / 2
    }
  }

  const bytesPerSample = bitDepth / 8
  const blockAlign = numChannels * bytesPerSample

  const wavDataByteLength = data.length * bytesPerSample
  const headerByteLength = 44
  const totalLength = headerByteLength + wavDataByteLength
  const waveFileData = new Uint8Array(totalLength)

  const view = new DataView(waveFileData.buffer)

  // RIFF chunk descriptor
  writeString(view, 0, "RIFF")
  view.setUint32(4, 36 + wavDataByteLength, true)
  writeString(view, 8, "WAVE")

  // fmt sub-chunk
  writeString(view, 12, "fmt ")
  view.setUint32(16, 16, true) // Subchunk1Size (16 for PCM)
  view.setUint16(20, format, true) // AudioFormat
  view.setUint16(22, numChannels, true) // NumChannels
  view.setUint32(24, sampleRate, true) // SampleRate
  view.setUint32(28, sampleRate * blockAlign, true) // ByteRate
  view.setUint16(32, blockAlign, true) // BlockAlign
  view.setUint16(34, bitDepth, true) // BitsPerSample

  // data sub-chunk
  writeString(view, 36, "data")
  view.setUint32(40, wavDataByteLength, true)

  // Write PCM data
  floatTo16BitPCM(view, 44, data)

  return new Blob([waveFileData], { type: "audio/wav" })
}
