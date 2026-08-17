import { defineConfig } from "vitepress"

function normalizeBase(value: string | undefined) {
  const trimmed = value?.trim()
  if (!trimmed) return "/docs/"

  return `/${trimmed.replace(/^\/+|\/+$/g, "")}/`
}

const base = normalizeBase(process.env.DOCS_BASE)
const outDir = process.env.DOCS_OUT_DIR?.trim() || undefined

const englishSidebar = [
  {
    text: "User guide",
    items: [
      { text: "Get started", link: "/en/user-guide/" },
      { text: "Protocols", link: "/en/user-guide/protocols" },
      { text: "Records", link: "/en/user-guide/records" },
      { text: "Collaboration", link: "/en/user-guide/collaboration" },
      { text: "Search", link: "/en/user-guide/search" },
      { text: "Import and export", link: "/en/user-guide/import-export" },
    ],
  },
  {
    text: "Lab administration",
    items: [
      { text: "Administration guide", link: "/en/lab-admin/" },
      { text: "Access control reference", link: "/en/access-control" },
    ],
  },
  {
    text: "Self-hosting",
    items: [
      { text: "Operations guide", link: "/en/self-hosting/" },
      { text: "Community Edition", link: "/en/community-edition" },
      { text: "Single-Lab deployment", link: "/en/single-lab-deployment" },
      { text: "Release and deployment identity", link: "/en/release-and-deployment-identity" },
      { text: "Self-hosted architecture", link: "/en/architecture/self-hosted-architecture" },
    ],
  },
  {
    text: "Development",
    items: [
      { text: "Development overview", link: "/en/developer/" },
      { text: "Frontend development", link: "/en/development/frontend" },
      { text: "File Storage Bridge", link: "/en/architecture/file-storage-bridge" },
    ],
  },
]

const chineseSidebar = [
  {
    text: "使用手册",
    items: [
      { text: "快速开始", link: "/zh/user-guide/" },
      { text: "Protocol", link: "/zh/user-guide/protocols" },
      { text: "Record", link: "/zh/user-guide/records" },
      { text: "协作", link: "/zh/user-guide/collaboration" },
      { text: "搜索", link: "/zh/user-guide/search" },
      { text: "导入与导出", link: "/zh/user-guide/import-export" },
    ],
  },
  {
    text: "实验室管理",
    items: [
      { text: "实验室管理指南", link: "/zh/lab-admin/" },
      { text: "访问控制参考", link: "/zh/access-control" },
    ],
  },
  {
    text: "自托管运维",
    items: [
      { text: "运维指南", link: "/zh/self-hosting/" },
      { text: "Community Edition", link: "/zh/community-edition" },
      { text: "单实验室部署", link: "/zh/single-lab-deployment" },
      { text: "发布与部署身份", link: "/zh/release-and-deployment-identity" },
      { text: "自托管架构", link: "/zh/architecture/self-hosted-architecture" },
    ],
  },
  {
    text: "开发文档",
    items: [
      { text: "开发概览", link: "/zh/developer/" },
      { text: "前端开发", link: "/zh/development/frontend" },
      { text: "文件存储桥接", link: "/zh/architecture/file-storage-bridge" },
    ],
  },
]

export default defineConfig({
  base,
  cleanUrls: true,
  description:
    "Documentation for Airalogy Platform users, Lab administrators, operators, and developers.",
  head: [
    ["meta", { name: "theme-color", content: "#2563eb" }],
    ["link", { rel: "icon", type: "image/svg+xml", href: `${base}favicon.svg?v=airalogy-1` }],
  ],
  outDir,
  locales: {
    root: {
      label: "English",
      lang: "en-US",
      link: "/en/",
    },
    zh: {
      label: "简体中文",
      lang: "zh-CN",
      link: "/zh/",
    },
  },
  title: "Airalogy Platform",
  themeConfig: {
    logo: { src: "/favicon.svg", alt: "Airalogy" },
    search: { provider: "local" },
    socialLinks: [{ icon: "github", link: "https://github.com/airalogy/platform" }],
    locales: {
      root: {
        docFooter: { prev: "Previous", next: "Next" },
        lastUpdated: { text: "Last updated" },
        nav: [
          { text: "User guide", link: "/en/user-guide/" },
          { text: "Lab administration", link: "/en/lab-admin/" },
          { text: "Self-hosting", link: "/en/self-hosting/" },
          { text: "Development", link: "/en/developer/" },
        ],
        outline: { label: "On this page", level: [2, 3] },
        sidebar: { "/en/": englishSidebar },
      },
      zh: {
        docFooter: { prev: "上一页", next: "下一页" },
        lastUpdated: { text: "最后更新" },
        nav: [
          { text: "使用手册", link: "/zh/user-guide/" },
          { text: "实验室管理", link: "/zh/lab-admin/" },
          { text: "自托管运维", link: "/zh/self-hosting/" },
          { text: "开发文档", link: "/zh/developer/" },
        ],
        outline: { label: "本页内容", level: [2, 3] },
        sidebar: { "/zh/": chineseSidebar },
      },
    },
  },
})
