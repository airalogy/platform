<template>
  <teleport v-for="(file, idx) in files" :key="file.href" :to="`[data-href='${file.href}']`">
    <div
      v-if="file.type === 'image'"
      class="group relative overflow-hidden !max-h-fit"
    >
      <n-image
        width="480"
        :src="fileInfoRecord[file.href]?.data?.url"
        :placeholder="file.href"
        :alt="file.info.alt"
        class="min-h-30"
        @load="handleImageLoad($event, file.href, idx)"
      />
      <!-- <template v-if="imageHeightRecord[`${file.href}_${idx}`] > 1200">
        <div
          v-if="!showMoreRecord[`${file.href}_${idx}`]"
          class="absolute-bl h-fit w-full flex justify-center bg-gradient-from-white bg-gradient-to-transparent bg-gradient-linear bg-gradient-to-t pt-10"
        >
          <n-button
            type="primary"
            quaternary
            icon-placement="right"
            @click="showMoreRecord[`${file.href}_${idx}`] = true"
          >
            More
            <template #icon>
              <icon-local-dropdown-outline />
            </template>
          </n-button>
        </div>
        <div
          v-else
          class="absolute-bl h-fit w-full flex justify-center py-2"
        >
          <n-button
            type="primary"
            quaternary
            icon-placement="right"
            @click="showMoreRecord[`${file.href}_${idx}`] = false"
          >
            Less
            <template #icon>
              <icon-local-dropdown-outline class="rotate-180" />
            </template>
          </n-button>
        </div>
      </template> -->
    </div>

    <asset-box v-else v-model:file-info-record="fileInfoRecord" :uuid="props.uuid" :file="file" />
  </teleport>
</template>

<script setup lang="ts">
import { getFileType, type IFileType } from "@airalogy/shared/utils"
// import { IconLocalDropdownOutline } from "@/components/icons"
import { getStaticResearchAssets } from "@/service/api/project-protocols"

interface IProps {
  uuid: string
}

const props = defineProps<IProps>()

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

const files = ref<IFileItem[]>([])

const fileInfoRecord = ref<
  Record<
    string,
    {
      data?: { id: string, url: string, filename: string }
      status: "pending" | "success" | "error"
    }
  >
>({})
// const imageRefRecord = ref<Record<string, ImageInstance>>({})

const showMoreRecord = ref<Record<string, boolean>>({})
const imageHeightRecord = ref<Record<string, number>>({})

function handleImageLoad(event: Event, href: string, idx: number) {
  const img = event.target as HTMLImageElement
  imageHeightRecord.value[`${href}_${idx}`] = img.height
}

watch(files, (list) => {
  const { uuid: researchUUID } = props

  list.forEach(async (file, idx) => {
    showMoreRecord.value[`${file.href}_${idx}`] = false

    let target = fileInfoRecord.value[file.href]
    if (target && (target.status === "pending" || target.status === "success")) {
      return
    }

    target = reactive({
      status: "pending",
    })

    fileInfoRecord.value[file.href] = target

    try {
      const { data, error } = await getStaticResearchAssets(
        researchUUID,
        file.href,
      )

      if (error) {
        target.status = "error"
        return
      }

      target.data = data
      target.status = "success"
    }
    catch (err) {
      target.status = "error"
    }
  })
})

onMounted(() => {
  const elements = document.querySelectorAll("[data-href][data-ext]")

  files.value = Array.from(elements).map((element) => {
    const { name, href, title, label, ext, ...info } = (element as HTMLElement)
      .dataset as unknown as IFileItemDataset

    const type = getFileType(href)

    return {
      name,
      href,
      label,
      title,
      ext,
      type,
      info,
    }
  })
})
</script>

<style scoped lang="sass">
.absolute-bl
  position: absolute
  bottom: 0
  left: 0
</style>
