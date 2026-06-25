import { computed, ref } from "vue"

export function useAudioPlayer() {
  const audioRef = ref<HTMLAudioElement>()
  const isPlaying = ref(false)
  const duration = ref(0)
  const currentTime = ref(0)
  const progress = ref(0)

  // Computed properties for time formatting
  const currentTimeFormatted = computed(() => formatTime(currentTime.value))
  const durationFormatted = computed(() => formatTime(duration.value))

  function formatTime(seconds: number): string {
    if (!seconds || Number.isNaN(seconds) || !Number.isFinite(seconds))
      return "0:00"

    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = Math.floor(seconds) % 60
    return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`
  }

  function formatTooltip(value: number) {
    if (!duration.value)
      return "0:00"

    const time = (value / 100) * duration.value
    return formatTime(time)
  }

  function togglePlay() {
    if (!audioRef.value)
      return

    if (isPlaying.value) {
      audioRef.value.pause()
    }
    else {
      audioRef.value.play()
    }
    isPlaying.value = !isPlaying.value
  }

  function handleTimeUpdate() {
    if (!audioRef.value || !duration.value)
      return

    currentTime.value = audioRef.value.currentTime
    progress.value = (currentTime.value / duration.value) * 100
  }

  function handleAudioLoad() {
    if (!audioRef.value)
      return

    // For data URLs, we need to load a small portion of the audio first
    if (audioRef.value.src.startsWith("data:")) {
      const loadDuration = () => {
        if (audioRef.value && audioRef.value.duration && audioRef.value.duration !== Infinity) {
          duration.value = audioRef.value.duration
        }
        else {
          // Try again in a short moment
          setTimeout(loadDuration, 100)
        }
      }
      loadDuration()
    }
    else {
      // Regular URL handling
      if (audioRef.value.duration === Infinity || audioRef.value.duration === 0) {
        audioRef.value.currentTime = 1e101
        audioRef.value.currentTime = 0
      }
      duration.value = audioRef.value.duration
    }

    currentTime.value = 0
    progress.value = 0
  }

  function handleEnded() {
    isPlaying.value = false
    currentTime.value = 0
    progress.value = 0
  }

  function handleSeek(value: number) {
    if (!audioRef.value || !duration.value)
      return

    const time = (value / 100) * duration.value
    audioRef.value.currentTime = time
    currentTime.value = time
  }

  function handleDurationChange() {
    if (!audioRef.value)
      return

    duration.value = audioRef.value.duration
  }

  return {
    audioRef,
    isPlaying,
    duration,
    currentTime,
    progress,
    currentTimeFormatted,
    durationFormatted,
    formatTooltip,
    togglePlay,
    handleTimeUpdate,
    handleAudioLoad,
    handleEnded,
    handleSeek,
    handleDurationChange,
  }
}
