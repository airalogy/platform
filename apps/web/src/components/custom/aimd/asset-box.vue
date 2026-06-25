<template>
  <div class="group download-box">
    <n-icon :component="getFileIcon(file.ext)" size="24" class="mr-3" />
    <div>
      <div class="font-bold">
        {{ file.label }}
      </div>
      <a
        :href="props.directURL || fileInfoRecord[file.href]?.data?.url"
        target="_blank"
        rel="noreferrer"
        class="group/anchor relative"
      >
        <n-icon
          class="absolute-y-center left-full ml-1 opacity-0 transition-opacity group-hover/anchor:opacity-100"
        >
          <open-outline />
        </n-icon>
        <span>
          {{ `${file.name}.${file.ext}` }}
        </span>
      </a>
    </div>
    <n-button quaternary type="primary" class="ml-2" title="Download" @click="handleDownload(file)">
      <n-icon size="20">
        <download-icon />
      </n-icon>
    </n-button>
  </div>
</template>

<script setup lang="ts">
import type { IFileType } from "@airalogy/shared/utils"
import { getStaticResearchAssets } from "@/service/api/project-protocols"
import { useClosableMessage } from "@airalogy/composables"
import FileTrayFullOutline from "~icons/ion/file-tray-full-outline"
import OpenOutline from "~icons/ion/open-outline"

interface IProps {
  uuid?: string
  file: {
    name: string
    href: string
    title: string
    label: string
    ext: string
    type: IFileType
    info: Record<string, any>
  }
  fileInfoRecord: Record<
    string,
    {
      data?: { id: string, url: string, filename: string }
      status: "pending" | "success" | "error"
    }
  >
  directURL?: string
}

const props = defineProps<IProps>()

const emit = defineEmits<IEmits>()

interface IEmits {
  (
    e: "update:fileInfoRecord",
    value: Record<
      string,
      {
        data?: { id: string, url: string, filename: string }
        status: "pending" | "success" | "error"
      }
    >,
  ): void
}

const fileInfoRecord = useVModel(props, "fileInfoRecord", emit)

function getFileIcon(ext: string) {
  switch (ext) {
    case "pdf":
      return FileTrayFullOutline
    case "doc":
    case "docx":
      return FileTrayFullOutline
    case "xls":
    case "xlsx":
      return FileTrayFullOutline
    default:
      return FileTrayFullOutline
  }
}

interface IFileItemDataset {
  name: string
  href: string
  title: string
  label: string
  ext: string
  type: IFileType
  info: Record<string, any>
}

interface IFileItem extends IFileItemDataset {}

const message = useClosableMessage()

async function handleDownload(file: IFileItem) {
  const { uuid: researchUUID } = props
  const tempLink = document.createElement("a")

  try {
    if (props.directURL) {
      tempLink.href = props.directURL
      tempLink.style.display = "none"
      tempLink.setAttribute("download", props.file.name)
      if (typeof tempLink.download === "undefined")
        tempLink.setAttribute("target", "_blank")

      document.body.appendChild(tempLink)
      tempLink.click()
      document.body.removeChild(tempLink)

      return
    }

    let assetInfo = fileInfoRecord.value[file.href]

    if (!researchUUID) {
      message.error("Research ID is required")
      return
    }

    if (!assetInfo || !assetInfo.data) {
      const { data, error } = await getStaticResearchAssets(
        researchUUID,
        file.href.split("/").slice(1).join("/"),
      )

      if (error) {
        return
      }

      assetInfo = { data, status: "success" }

      fileInfoRecord.value[file.href] = assetInfo
    }

    if (!assetInfo.data) {
      return
    }

    tempLink.href = assetInfo.data.url
    tempLink.style.display = "none"
    tempLink.setAttribute("download", assetInfo.data.filename)
    if (typeof tempLink.download === "undefined")
      tempLink.setAttribute("target", "_blank")

    document.body.appendChild(tempLink)
    tempLink.click()
    document.body.removeChild(tempLink)
  }
  catch (err) {
    message.error((err as Error).message)
  }
}
</script>

<style scoped lang="sass">
.download-box
  border: 1px solid #ddd
  padding: 10px
  margin: 10px 0
  background-color: #f9f9f9
  display: flex
  align-items: center
  border-radius: 5px
  transition: background-color 0.3s

.file-name
  font-size: 16px
  font-weight: bold
  flex-grow: 1

.download-box:hover
  background-color: #f1f1f1
</style>
