import type { ProtocolModels } from "@airalogy/shared/types/models"
import type { MaybeRef } from "vue"
import type { RouteLocationRaw } from "vue-router"

export interface PathSegment {
  uid: string
  name: string
  route: RouteLocationRaw
}

export function useProtocolPath(protocolInfo: MaybeRef<ProtocolModels.ProjectProtocolInfo>, showProtocolName = true) {
  const labRoute = computed<PathSegment>(() => {
    const { lab } = unref(protocolInfo)

    return {
      name: lab.name,
      uid: lab.uid,
      route: {
        name: "lab-projects",
        params: {
          labUid: lab.uid,
        },
      },
    }
  })

  const projectRoute = computed<PathSegment>(() => {
    const { project, lab } = unref(protocolInfo)

    return {
      name: project.name,
      uid: project.uid,
      route: {
        name: "project-protocols",
        params: {
          labUid: lab.uid,
          projectUid: project.uid,
        },
      },
    }
  })

  const protocolRoute = computed<PathSegment>(() => {
    const { uid, name, lab, project } = unref(protocolInfo)

    return {
      name: showProtocolName ? name : "",
      uid,
      route: {
        name: "protocol-info",
        params: {
          labUid: lab.uid,
          projectUid: project.uid,
          protocolUid: uid,
        },
      },
    }
  })

  const pathSegments = computed<PathSegment[]>(() => {
    if (showProtocolName) {
      return [labRoute.value, projectRoute.value, protocolRoute.value]
    }

    return [labRoute.value, projectRoute.value]
  })

  return {
    labRoute,
    projectRoute,
    protocolRoute,
    pathSegments,
  }
}
