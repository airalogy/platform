<template>
  <div class="container mx-auto p-6 color-white md:py-8">
    <div class="flex flex-row flex-wrap lg:flex-nowrap">
      <global-logo monochrome show-title />
      <template v-if="props.showLink">
        <footer-link v-for="item in columns" :key="item.title" :title="item.title" :list="item.list" />
      </template>
    </div>
    <div class="flex flex-wrap items-center justify-center border-t border-white/30 pt-4 sm:justify-between md:pt-6">
      <div class="order-last mr-auto h-fit w-full text-center text-gray-400 md:order-first md:mt-0 sm:w-fit space-x-3 md:text-left">
        <span>&copy; {{ currYear }}</span>
        <span>{{ footerText.copyright }}</span>
        <china-compliance-footer />
      </div>
      <template v-if="props.showIcon">
        <footer-icon v-for="item in sns" :key="item.name" :name="item.name" :to="item.to" />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"
import IconAiraXiv from "@/assets/link-icon/airaxiv.svg"
import ChinaComplianceFooter from "@/components/common/china-compliance-footer.vue"
import { $t } from "@/locales"

defineOptions({ name: "GlobalFooter" })

const props = withDefaults(defineProps<IProps>(), {
  showLink: true,
  showIcon: false,
})

interface IProps {
  showLink?: boolean
  showIcon?: boolean
}
const currYear = new Date().getFullYear()
const footerText = computed(() => ({
  copyright: $t("common.footer.copyright"),
  partners: $t("common.footer.partners"),
}))

const columns = computed((): {
  title: string
  list: {
    name: string
    to: RouteLocationRaw
    external?: boolean
    icon?: string
  }[]
}[] => [
  {
    title: footerText.value.partners,
    list: [
      {
        name: "AiraXiv",
        to: "https://airaxiv.com",
        external: true,
        icon: IconAiraXiv,
      },
    ],
  },
  // {
  //   title: "explore",
  //   list: [
  //     { name: "labs", to: { name: "root" } },
  //     { name: "projects", to: { name: "root" } },
  //     { name: "protocols", to: { name: "root" } },
  //   ],
  // },
  // {
  //   title: "about",
  //   list: [
  //     { name: "Airalogy project", to: { name: "root" } },
  //     { name: "contribute", to: { name: "root" } },
  //     { name: "contact", to: "mailto:contact@airalogy.com", external: true },
  //   ],
  // },
  // {
  //   title: "help",
  //   list: [
  //     { name: "getting started", to: { name: "root" } },
  //     { name: "service status", to: { name: "root" } },
  //     { name: "FAQs", to: { name: "root" } },
  //   ],
  // },
])
// const columns: {
//   title: string;
//   list: {
//     name: string;
//     to: RouteLocationRaw;
//     external?: boolean;
//   }[];
// }[] = [
//     {
//       title: "explore",
//       list: [
//         { name: "research protocol", to: "/research/protocol" },
//         { name: "projects", to: "/projects/all" },
//         { name: "research", to: "/research/all" },
//       ],
//     },
//     {
//       title: "about",
//       list: [
//         { name: "Airalogy project", to: "/about/aira" },
//         { name: "contribute", to: "/about/contribute" },
//         { name: "contact", to: "mailto:contact@airalogy.com", external: true },
//       ],
//     },
//     {
//       title: "help",
//       list: [
//         { name: "getting started", to: "/guide" },
//         { name: "service status", to: "/service-status" },
//         { name: "FAQs", to: "/faq" },
//       ],
//     },
//   ]

const sns = [
  { name: "facebook", to: "https://facebook.com" },
  { name: "github", to: "https://github.com" },
  { name: "wechat", to: "https://wechat.com" },
  { name: "twitter", to: "https://twitter.com" },
] as const
</script>

<style scoped lang="sass">

</style>
