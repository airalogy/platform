import { useClosableMessage } from "@airalogy/composables"
import { useUserMedia } from "@vueuse/core"

import { ref } from "vue"
import { audioBufferToWav } from "../utils/wav"

export interface AudioRecorderState {
  audioUrl: string | null
  audioBlob: Blob | null
  isPlaying: boolean
  recordingDuration: number
  durationInterval: number | null
}

export function useAudioRecorder() {
  const message = useClosableMessage()
  const isRecording = ref(false)
  const mediaRecorder = ref<MediaRecorder | null>(null)
  const audioChunks = ref<Blob[]>([])

  const audioRecorder = ref<AudioRecorderState>({
    audioUrl: null,
    audioBlob: null,
    isPlaying: false,
    recordingDuration: 0,
    durationInterval: null,
  })

  const {
    stream,
    isSupported,
    start: startStream,
    stop: stopStream,
  } = useUserMedia({
    constraints: {
      audio: {
        deviceId: "default",
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    },
  })

  const audioElement = ref<HTMLAudioElement | null>(null)

  function startDurationCounter() {
    stopDurationCounter()
    audioRecorder.value.recordingDuration = 0
    audioRecorder.value.durationInterval = window.setInterval(() => {
      audioRecorder.value.recordingDuration++
    }, 1000)
  }

  function stopDurationCounter() {
    if (audioRecorder.value.durationInterval) {
      window.clearInterval(audioRecorder.value.durationInterval)
      audioRecorder.value.durationInterval = null
    }
  }

  async function startRecording() {
    if (!isSupported.value || isRecording.value) {
      message.error("Recording not supported or already recording")
      return
    }

    try {
      // First, get available devices to find the correct one
      const devices = await navigator.mediaDevices.enumerateDevices()
      const audioInputs = devices.filter(device => device.kind === "audioinput")

      // Find the default device or built-in microphone
      let preferredDevice = audioInputs.find(d =>
        d.deviceId === "default"
        || d.label.toLowerCase().includes("default"),
      )

      // If no default found, try to find built-in microphone
      if (!preferredDevice) {
        preferredDevice = audioInputs.find(d =>
          d.label.toLowerCase().includes("built-in")
          || d.label.toLowerCase().includes("macbook")
          || d.label.toLowerCase().includes("internal"),
        )
      }

      // Fallback to first non-virtual device
      if (!preferredDevice) {
        preferredDevice = audioInputs.find(d =>
          !d.label.toLowerCase().includes("virtual")
          && !d.label.toLowerCase().includes("ideashare")
          && !d.label.toLowerCase().includes("wemeet"),
        )
      }

      const deviceId = preferredDevice?.deviceId
      const constraints: MediaStreamConstraints = {
        audio: deviceId
          ? {
              deviceId: { exact: deviceId },
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            }
          : {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
        video: false,
      }

      const mediaStream = await navigator.mediaDevices.getUserMedia(constraints)

      if (!mediaStream) {
        console.error("No media stream available")
        return
      }

      // Test which mime types are supported
      const mimeTypes = [
        "audio/webm",
        "audio/webm;codecs=opus",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ]

      let selectedMimeType = ""
      for (const mimeType of mimeTypes) {
        if (MediaRecorder.isTypeSupported(mimeType)) {
          selectedMimeType = mimeType
          break
        }
      }

      mediaRecorder.value = new MediaRecorder(mediaStream, {
        mimeType: selectedMimeType || undefined,
      })
      audioChunks.value = []

      mediaRecorder.value.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.value.push(event.data)
        }
      }

      mediaRecorder.value.onerror = (event: any) => {
        console.error("MediaRecorder error:", event.error)
      }

      mediaRecorder.value.start(100)
      isRecording.value = true
      startDurationCounter()
    }
    catch (error) {
      message.error("Failed to start recording")
      console.error("Recording error:", error)
      isRecording.value = false
    }
  }

  async function convertToBlob(chunks: Blob[]): Promise<Blob> {
    const webmBlob = new Blob(chunks, { type: "audio/webm" })
    try {
      const arrayBuffer = await webmBlob.arrayBuffer()
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer)
      return audioBufferToWav(audioBuffer)
    }
    catch (error) {
      console.error("Error converting to WAV:", error)
      // Fallback to original blob if conversion fails
      return webmBlob
    }
  }

  async function stopRecording(): Promise<void> {
    if (!mediaRecorder.value || mediaRecorder.value.state !== "recording")
      return

    return new Promise((resolve) => {
      if (!mediaRecorder.value)
        return resolve()

      mediaRecorder.value.onstop = async () => {
        const webmBlob = new Blob(audioChunks.value, {
          type: mediaRecorder.value?.mimeType || "audio/webm",
        })

        const wavBlob = await convertToBlob(audioChunks.value)

        audioRecorder.value.audioUrl = URL.createObjectURL(webmBlob)
        audioRecorder.value.audioBlob = wavBlob

        isRecording.value = false
        stopDurationCounter()
        resolve()
      }

      stopDurationCounter()
      mediaRecorder.value.stop()
    })
  }

  function previewAudio() {
    if (!audioRecorder.value.audioUrl)
      return

    if (!audioElement.value) {
      audioElement.value = new Audio(audioRecorder.value.audioUrl)

      audioElement.value.addEventListener("play", () => {
        audioRecorder.value.isPlaying = true
      })

      audioElement.value.addEventListener("pause", () => {
        audioRecorder.value.isPlaying = false
      })

      audioElement.value.addEventListener("ended", () => {
        audioRecorder.value.isPlaying = false
      })
    }

    if (audioRecorder.value.isPlaying) {
      audioElement.value.pause()
      audioElement.value.currentTime = 0
    }
    else {
      audioElement.value.play()
    }
  }

  function stopPreview() {
    if (audioElement.value) {
      audioElement.value.pause()
      audioElement.value.currentTime = 0
      audioRecorder.value.isPlaying = false
    }
  }

  function resetAudioRecorder() {
    if (mediaRecorder.value) {
      if (mediaRecorder.value.state === "recording") {
        mediaRecorder.value.stop()
      }
      mediaRecorder.value = null
    }

    if (audioRecorder.value.audioUrl) {
      URL.revokeObjectURL(audioRecorder.value.audioUrl)
    }

    audioRecorder.value = {
      audioUrl: null,
      audioBlob: null,
      isPlaying: false,
      recordingDuration: 0,
      durationInterval: null,
    }

    isRecording.value = false
    audioChunks.value = []
    stopDurationCounter()

    if (audioElement.value) {
      stopPreview()
      audioElement.value = null
    }
  }

  return {
    audioRecorder,
    isRecording,
    isSupported,
    startRecording,
    stopRecording,
    resetAudioRecorder,
    startDurationCounter,
    stopDurationCounter,
    convertToBlob,
    previewAudio,
    stopPreview,
    audioElement,
  }
}
