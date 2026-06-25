<template>
  <div class="tracebacks-container">
    <div v-if="!simple" class="traceback-exception">
      <strong>{{ terms.error_traceback }}</strong>
    </div>
    <div
      v-for="(traceback, tracebackIndex) in data"
      :key="tracebackIndex"
      class="traceback"
    >
      <template v-if="!simple">
        <template v-for="(frame, frameIndex) in traceback.frames" :key="frameIndex">
          <frame v-if="frame.type === 'frame'" :frame="frame" />
          <repeated-frames v-else :frames="frame.frames" />
        </template>
      </template>
      <div>
        <span class="traceback-exception">
          <strong>{{ traceback.exception.type }}: </strong>
          {{ traceback.exception.message }}
        </span>
        <friendly-message :friendly="traceback.friendly" />
      </div>
      <div v-if="traceback.didyoumean?.length > 0" class="traceback-didyoumean">
        <i>{{ terms.did_you_mean }}</i>
        <ul>
          <li v-for="(suggestion, suggestionIndex) in traceback.didyoumean" :key="suggestionIndex">
            {{ suggestion }}?
          </li>
        </ul>
      </div>
      <div v-if="traceback.tail" class="traceback-tail">
        {{ traceback.tail }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { terms } from "../constants"
import Frame from "./Frame.vue"
import FriendlyMessage from "./FriendlyMessage.vue"
import RepeatedFrames from "./RepeatedFrames.vue"

import "./pygments.css"

const props = defineProps<{
  data: any[]
  codeSource?: string
}>()

const simple = computed(
  () =>
    props.codeSource === "shell"
    && props.data.length === 1
    && props.data[0].frames.length === 1,
)
</script>

<style lang="scss">
.output-prediction {
  opacity: 0;
  cursor: pointer;
  height: 0;
  transition: all 1s linear;
  overflow: hidden;

  // Between firefox and chrome, one seems to only use padding,
  // while the other only uses margin
  padding-bottom: 6em;
  margin-bottom: 6em;

  &.show {
    opacity: 1;
  }

  &.fading {
    opacity: 0;
  }

  .prediction-choice {
    // Center radio button vertically against multiline text
    display: flex;
    align-items: center;

    margin: 5px;
    padding: 8px 5px 8px 15px;
    border-radius: 4px;
    border: 2px #464f52 solid;

    .prediction-label {
      white-space: pre;
      display: inline-block;
      margin-left: 15px;
    }

    &.prediction-correct {
      border: 2px #56ff94 solid;
      background: #004200;
    }

    &.prediction-wrong {
      border: 2px #ff0000 solid;
      background: #660000;
    }

    &.prediction-selected {
      border: 2px #0090ff solid;
      background: #003866;
    }
  }

  .submit-prediction {
    position: fixed;
    bottom: 2vh;
    background:rgb(33, 33, 33);;
    padding: 0.5em 0 0.5em 1em;
    border: 2px #464f52 solid;
    border-radius: 4px;
    width: 40vw;

    button {
      margin-top: 0.5em;

      &:disabled {
        opacity: 1;
        background: #1c58b1;
        border-color: #1c58b1;
      }
    }
  }
}

.tracebacks-container {

  .traceback {
    .traceback-frame {
      background: #272822;
      border: 1px solid grey;
      border-radius: 8px;
      padding: 0.5em;
      margin-top: 3px;

      .traceback-frame-name {
        font-weight: bold;
        color: white;
      }

      table {
        margin-top: 0.25em;
      }

      .traceback-variables-table {
        td {
          border: 1px solid grey;
          padding: 4px;
          white-space: pre;
        }

        td.traceback-variable-name {
          padding-right: 2em;
        }

      }

      .traceback-line-content {
        padding-left: 8px;
        white-space: pre;
      }

      .traceback-lineno {
        color: #8F908A;
        min-width: 32px;
        padding-right: 11px;
        text-align: right;
      }

    }

    .traceback-repeated-frames {
      margin: 1.5em;
    }
  }
  .traceback-exception {
    font-size: 120%;
    color: red;
    padding: 0 0.5em;
  }

  .traceback-tail {
    margin: 1em;
  }
}
</style>
