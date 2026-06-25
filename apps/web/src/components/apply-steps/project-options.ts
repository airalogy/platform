import type { CascaderOption } from "naive-ui"

export type ProjectCascaderOption = CascaderOption & { uid: string, id: string }

type ProjectSummary = Pick<Api.Project.MyProjectInfo, "id" | "uid" | "name" | "lab_id" | "lab_uid" | "lab_name">

export function groupProjectsByLabOptions(
  projects: ProjectSummary[],
  excludeProjects: string[] = [],
): ProjectCascaderOption[] {
  const labOptions = new Map<string, ProjectCascaderOption>()

  for (const project of projects) {
    if (!project.lab_id || !project.lab_uid || !project.lab_name || excludeProjects.includes(project.uid)) {
      continue
    }

    let labOption = labOptions.get(project.lab_id)
    if (!labOption) {
      labOption = {
        label: `${project.lab_name} (${project.lab_uid})`,
        value: project.lab_uid,
        depth: 1,
        isLeaf: false,
        id: project.lab_id,
        uid: project.lab_uid,
        children: [],
      }
      labOptions.set(project.lab_id, labOption)
    }

    const children = (labOption.children ||= []) as ProjectCascaderOption[]
    children.push({
      label: `${project.name} (${project.uid})`,
      value: `${project.lab_uid}|${project.uid}`,
      depth: 2,
      isLeaf: true,
      uid: project.uid,
      id: project.id,
    })
  }

  return Array.from(labOptions.values())
}
