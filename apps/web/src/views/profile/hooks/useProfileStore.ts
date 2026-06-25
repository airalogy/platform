import type { StarFolder, StarResponse } from "@/service/api/star"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { UploadFileInfo } from "naive-ui"
import { useLoading } from "@/composables"
import { getLabInfo } from "@/service/api/labs"
import { putUserProfile } from "@/service/api/profile"
import { getStarFolders, getStars, StarResourceType } from "@/service/api/star"
import {
  fetchUserAnswers,
  fetchUserGroups,
  fetchUserLabs,
  fetchUserProjects,
  fetchUserProtocols,
  fetchUserQuestions,
  getUserInfo,
  getUsersWithAliases,
} from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { localStg } from "@/utils/storage"
import { useClosableMessage } from "@airalogy/composables"
import { createInjectionState } from "@vueuse/core"
import { ref } from "vue"

const [useProvideProfileStore, useProfileStore] = createInjectionState(
  (initialValue: Api.Profile.User | null) => {
    const authStore = useAuthStore()
    const userInfo = ref<Api.Profile.User | null>(initialValue)
    const userGroupList = ref<Api.Groups.MyGroupsInfo[]>([])
    const userLabList = ref<Api.Lab.LabInfo[]>([])
    const userProjectList = ref<Api.Project.MyProjectInfo[]>([])
    const userProtocolList = ref<ProtocolModels.ProjectProtocolInfo[]>([])
    const userQuestions = ref<Api.Discussion.QuestionItem[]>([])
    const userAnswers = ref<Api.Discussion.AnswerItem[]>([])

    const starredFoldersByType = ref<Record<StarResourceType, StarResponse[]>>({
      [StarResourceType.Protocol]: [],
      [StarResourceType.Question]: [],
      [StarResourceType.Answer]: [],
    })

    const starredFolders = ref<({ folder: StarFolder } & Api.GetResponseWithCount<"stars", StarResponse[]>)[]>([])

    const userLabCount = ref<number>(0)
    const userGroupCount = ref<number>(0)
    const userProjectCount = ref<number>(0)
    const userProtocolCount = ref<number>(0)
    const userQuestionsCount = ref<number>(0)
    const userAnswersCount = ref<number>(0)

    const userRecords = ref<number>(0)
    const isCurrentUser = computed(() => {
      return userInfo.value?.id === authStore.userInfo.id
    })

    const avatarFile = ref<UploadFileInfo | null>(null)
    const message = useClosableMessage()

    const { loading, startLoading, endLoading } = useLoading()

    // Loading states for different data types
    const isLoadingQuestions = ref(false)
    const isLoadingAnswers = ref(false)
    const isLoadingStarred = ref(false)

    async function handleSubmitAvatar(avatar: File | null) {
      if (!userInfo.value) {
        return
      }

      const { username } = userInfo.value

      if (!username) {
        message.warning("Please enter username.")
        return
      }

      startLoading()
      try {
        const newUserInfo = await putUserProfile({
          avatar,
        })

        if (newUserInfo) {
          localStg.set("userInfo", newUserInfo)
          Object.assign(authStore.userInfo, newUserInfo)

          message.success("Profile updated successfully.")
        }
        else {
          message.error("Failed to update profile.")
        }
      }
      catch (e) {
        message.error((e as Error).message)
      }
      finally {
        endLoading()
      }
    }

    async function handleUpdateBio(bio: string) {
      if (!userInfo.value) {
        return
      }

      startLoading()
      try {
        const newUserInfo = await putUserProfile({
          bio,
        })

        if (newUserInfo) {
          localStg.set("userInfo", newUserInfo)
          Object.assign(authStore.userInfo, newUserInfo)
          userInfo.value.bio = newUserInfo.bio
          message.success("Bio updated successfully.")
        }
        else {
          message.error("Failed to update bio.")
        }
      }
      catch (e) {
        message.error((e as Error).message)
      }
      finally {
        endLoading()
      }
    }

    async function fetchUserInfo(payload: {
      username?: string
      id?: string
    }): Promise<Api.Profile.User | null> {
      if (!payload.username && !payload.id) {
        return null
      }

      try {
        const user = await getUserInfo.load(payload)
        if (user) {
          userInfo.value = user
          // Fetch additional user data
          await Promise.all([fetchUserLabsData(user.id), fetchUserProjectsData(user.id), fetchUserAlias(user.id)])
        }

        return user
      }
      catch (e) {
        return null
      }
    }

    async function fetchUserAlias(userId: string) {
      try {
        const { data } = await getUsersWithAliases({ user_ids: [userId] })
        if (data && data.length > 0 && userInfo.value) {
          userInfo.value.user_alias = data[0].user_alias ?? null
        }
      }
      catch (e) {
        // ignore alias fetch failure
      }
    }

    async function fetchUserLabsData(userId: string, payload?: { page: number, pageSize: number }) {
      try {
        const data = await fetchUserLabs(userId, payload || { page: 1, pageSize: 5 })
        if (data) {
          userLabList.value = data.labs
          userLabCount.value = data.total_count
        }
      }
      catch (e) {
        console.error("Failed to fetch user labs:", e)
      }
    }

    async function fetchUserProjectsData(
      userId: string,
      payload?: { page: number, pageSize: number },
    ) {
      try {
        const data = await fetchUserProjects(userId, payload || { page: 1, pageSize: 5 })
        if (data) {
          userProjectList.value = data.projects
          userProjectCount.value = data.total_count
        }
      }
      catch (e) {
        console.error("Failed to fetch user projects:", e)
      }
    }

    async function fetchUserProtocolsData(
      userId: string,
      payload?: { page: number, pageSize: number },
    ) {
      try {
        const data = await fetchUserProtocols(userId, payload || { page: 1, pageSize: 5 })
        if (data) {
          userProtocolList.value = data.protocols
          userProtocolCount.value = data.total_count
        }
      }
      catch (e) {
        console.error("Failed to fetch user protocols:", e)
      }
    }

    async function fetchUserGroupsData(
      userId: string,
      payload?: { page: number, pageSize: number },
    ) {
      try {
        const data = await fetchUserGroups(userId, payload || { page: 1, pageSize: 5 })
        if (data) {
          const labIds = Array.from(new Set<string>(data.groups.map(it => it.lab_id)))
          const labs = await Promise.allSettled(labIds.map(id => getLabInfo(id).then(res => res.data?.data)))

          userGroupList.value = data.groups.map((it) => {
            const info = labs.find(lab => lab.status === "fulfilled" && lab.value?.id === it.lab_id)

            if (!info) {
              return it
            }
            const { uid, name } = (info.status === "fulfilled" && info.value) || {}

            return {
              ...it,
              lab_uid: uid || "",
              lab_name: name || "",
            }
          })
          userGroupCount.value = data.total_count
        }
      }
      catch (e) {
        console.error("Failed to fetch user groups:", e)
      }
    }

    async function fetchUserQuestionsData(
      userId: string,
      payload?: { page: number, pageSize: number, query?: string },
    ) {
      try {
        isLoadingQuestions.value = true
        const data = await fetchUserQuestions(userId, payload || { page: 1, pageSize: 10 })
        if (data) {
          userQuestions.value = data.questions
          userQuestionsCount.value = data.total_count
        }
      }
      catch (e) {
        console.error("Failed to fetch user questions:", e)
      }
      finally {
        isLoadingQuestions.value = false
      }
    }

    async function fetchUserAnswersData(
      userId: string,
      payload?: { page: number, pageSize: number, sortBy?: string },
    ) {
      try {
        isLoadingAnswers.value = true
        const data = await fetchUserAnswers(userId, payload || { page: 1, pageSize: 10 })
        if (data) {
          userAnswers.value = data.answers
          userAnswersCount.value = data.total_count
        }
      }
      catch (e) {
        console.error("Failed to fetch user answers:", e)
      }
      finally {
        isLoadingAnswers.value = false
      }
    }

    async function fetchUserStarredData(
      payload?: { page: number, pageSize: number, resourceType?: number },
    ) {
      try {
        isLoadingStarred.value = true
        // const data = await fetchUserStarred(userId, payload || { page: 1, pageSize: 10 })
        const res = await getStarFolders()
        if (!res?.folders) {
          return
        }

        const folders = await Promise.allSettled(res.folders.map(folder =>
          getStars({
            folder_id: folder.id,
            page: payload?.page || 1,
            page_size: payload?.pageSize || 10,
          }),
        ))

        starredFolders.value = folders.map((it, index) => {
          if (it.status !== "fulfilled" || !it.value) {
            return null
          }

          const folder = res.folders[index]
          return {
            folder,
            ...it.value,
          } as any
        }).filter(Boolean)
      }
      catch (e) {
        console.error("Failed to fetch user starred items:", e)
      }
      finally {
        isLoadingStarred.value = false
      }
    }

    const viewAllState = reactive<Record<"lab" | "project" | "group" | "protocol", boolean | undefined >>({
      lab: undefined,
      project: undefined,
      protocol: undefined,
      group: undefined,
    })

    watchEffect(() => {
      if (userLabCount.value > 5 && typeof viewAllState.lab === "undefined") {
        viewAllState.lab = true
      }
      if (userProjectCount.value > 5 && typeof viewAllState.project === "undefined") {
        viewAllState.project = true
      }
      if (userGroupCount.value > 5 && typeof viewAllState.group === "undefined") {
        viewAllState.group = true
      }
      if (userProtocolCount.value > 5 && typeof viewAllState.protocol === "undefined") {
        viewAllState.protocol = true
      }
    })

    return {
      userInfo,
      userGroupList,
      userLabList,
      userProjectList,
      userProtocolList,
      userQuestions,
      userAnswers,
      userLabCount,
      userGroupCount,
      userProjectCount,
      userProtocolCount,
      userQuestionsCount,
      userAnswersCount,
      userRecords,
      starredFolders,
      isLoadingQuestions,
      isLoadingAnswers,
      isLoadingStarred,
      fetchUserInfo,
      fetchUserLabsData,
      fetchUserProjectsData,
      fetchUserProtocolsData,
      fetchUserGroupsData,
      fetchUserQuestionsData,
      fetchUserAnswersData,
      fetchUserStarredData,
      isCurrentUser,
      handleSubmitAvatar,
      handleUpdateBio,
      avatarFile,
      loading,
      startLoading,
      endLoading,
      viewAllState,
    }
  },
)

export { useProfileStore, useProvideProfileStore }
