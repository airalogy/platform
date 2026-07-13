# Lab 权限管理

本文说明 `LAB_STRUCTURE_MODE=structured` 下的组织单元和研究资源权限。single-Lab profile 默认启用该模式；Community profile 默认为 `flat`，但可显式启用。

## 核心模型

权限模型将“人属于哪个组织”和“人可以操作哪些研究资源”分开：

- **组织结构**：Lab 下是最多三级的组织单元树。组织单元可以是部门、课题组、公共平台、项目团队、委员会或其他组织。
- **资源结构**：Lab 下是最多三级的 Project 树，Project 下包含 Protocol，Protocol 下产生 Record。
- **连接两者**：作用域授权将 User 或组织单元与 Lab、Project 或 Protocol 连接。

组织单元不等于研究权限。组织单元 manager 可维护本单元及其下级单元，但只有获得作用域授权后才能访问研究资源。Project 始终是资源容器，不应用 Project 模拟部门或课题组。

## 组织单元

### 类型

| 类型             | 典型用途                                               |
| ---------------- | ------------------------------------------------------ |
| `department`     | 研究中心、学科部、研发部门等稳定行政分支               |
| `research_group` | PI 课题组、实验组、专业研究组                          |
| `core_facility`  | 质谱、成像、测序、高通量筛选等公共技术平台             |
| `project_team`   | 跨部门项目组、联合攻关组、有明确生命周期的专项团队     |
| `committee`      | 安全、数据治理、仪器、学术委员会                       |
| `other`          | 不属于上述类型的组织单元，也用于承载升级前的历史 Group |

类型用于表达业务语义和界面标签，当前不改变权限算法。同一个通用实体就可以同时承载学术、行政、公共设施和临时项目组织，无需再为 Department 或 Team 建立平行的成员与授权系统。

### 为什么是三级

Lab 本身不计入三级。一个完整结构可以是：一级部门、二级课题组或公共平台、三级项目团队。

三级是当前的明确产品约束，API 在创建或移动组织单元时会校验，不支持无限层级。这不是数据库无法存储更深的树，而是为了控制管理委派、继承解释和界面操作的复杂度。对多数单实验室和中型研究中心，三级已能表达稳定的主干结构，矩阵关系则通过一人加入多个组织单元表达。

如果现实行政树长期需要四级以上，应先判断上级机构是否已经是独立 Lab 或未来的 Organization/Tenant，而不是无限加深单个 Lab。只有在明确的部署需求、委派规则和迁移方案完成后，才应放宽该限制。

### 真实结构示例

**单 PI 实验室**

```text
Lab
└─ 徐天课题组 (research_group)
   ├─ 分子生物学小组 (research_group)
   └─ 蛋白组学项目组 (project_team)
```

规模较小时只创建一个根课题组也可以，不要为了填满三级而制造空层级。

**药物研发中心**

```text
Lab
├─ 小分子研发部 (department)
│  ├─ 药物化学组 (research_group)
│  └─ 先导化合物 A 项目组 (project_team)
├─ 生物学研发部 (department)
│  └─ 细胞功能组 (research_group)
└─ 高通量筛选平台 (core_facility)
```

研发部门的稳定成员关系和项目期限内的协作关系可同时存在。成员可以同时属于药物化学组和先导化合物项目组。

**多 PI 中心与公共设施**

```text
Lab
├─ 神经科学部 (department)
│  ├─ 张教授课题组 (research_group)
│  └─ 李教授课题组 (research_group)
├─ 成像平台 (core_facility)
└─ 数据治理委员会 (committee)
```

一名成员可同时属于自己的 PI 课题组、成像平台和数据治理委员会。这就是矩阵组织，不需要把树改造成图或另建一套“虚线汇报”模型。

## 权限主体

### User

授权可直接指向一个 Lab 成员。成员被移出 Lab 时，其直接授权会自动撤销，相应撤销会记入授权审计日志。

### 组织单元

授权可指向组织单元。用户会获得：

- 直接所属组织单元的授权；
- 该单元所有上级单元的授权；
- 同时所属的其他组织单元及其上级单元的授权。

上级组织单元的授权因此可覆盖整个组织分支。父单元 manager 可创建和管理下级单元；根单元的创建以及已有单元的移动由 Lab owner 或 manager 完成。成员可同时属于多个组织单元，有效授权自动取并集。

## 资源作用域与继承

| 作用域   | 精确对象      | 启用向下继承时                            |
| -------- | ------------- | ----------------------------------------- |
| Lab      | 当前 Lab      | 可向 Project、子 Project 和 Protocol 传播 |
| Project  | 指定 Project  | 可向子 Project 和 Protocol 传播           |
| Protocol | 指定 Protocol | 只作用于该 Protocol                       |

每条授权的 `inherit_to_children` 决定它是否向下传播。Project 和 Protocol 还有各自的 `inherit_permissions` 开关：

- Project 关闭继承时，不再接收父 Project 和 Lab 授权，但自身直接授权仍然有效。
- Protocol 关闭继承时，不再接收 Project 和 Lab 授权，但自身直接授权仍然有效。
- Lab owner 和 manager 的成员身份是 Lab 级管理权，不会被资源继承断点锁在外部。

普通成员访问 Protocol 时的默认查找链为：

```text
Protocol -> Project -> 父 Project -> Lab
```

## 角色与能力

`lab_owner` 和 `lab_admin` 是 Lab 成员身份，必须在 Members 中管理，不能作为普通作用域授权发放。其余角色可在 Access 工作台中授予 User 或组织单元。

| 角色 | 用途 | 主要能力 | 可作用域授予 |
| --- | --- | --- | --- |
| Lab owner | Lab 所有者 | 全部能力，包括 Lab 所有权 | 否 |
| Lab administrator | Lab 管理员 | 除 Lab 所有权外的全部能力 | 否 |
| Project manager | 资源范围管理者 | 管理作用域授权和 Project；编辑 Protocol；创建、读取和删除 Record | 是 |
| Protocol editor | Protocol 编辑者 | 创建、读取、修改和删除 Protocol；执行 Assigner；创建、读取和删除 Record | 是 |
| Contributor | 研究协作者 | 创建和读取 Protocol；执行 Assigner；创建和读取 Record | 是 |
| Recorder | 实验记录者 | 当前能力集与 Contributor 相同，但保留独立角色语义及旧角色映射 | 是 |
| Viewer | 只读用户 | 读取 Protocol 和 Record | 是 |

权限判定使用能力而不是界面上的角色名称。具体能力集可通过 `GET /api/access/roles` 查询。

## 有效权限与委派

用户的最终能力是所有有效来源的并集：Lab owner 或 manager 成员身份、User 直接授权、所属组织单元及其上级单元授权、未被继承断点阻断的资源授权，以及兼容的旧角色。只有未撤销且未过期的授权参与计算。系统不提供显式 `DENY`。

Access 工作台的 **Effective access** 可按 User、Project 和 Protocol 查看有效角色、合并能力和每个授权来源。Lab owner 和 manager 可查看任意成员，普通成员只能查看自己。

授权人必须在目标作用域同时具有 `access.manage`，且自身能力集完整包含待授予角色的能力集。Project manager 可在自己管理的 Project 中授予 Contributor 或 Viewer，但不能授予 Lab administrator。组织单元 manager 不包含 `access.manage`，不能仅凭组织管理权授予研究资源角色。

## 管理流程

### 建立组织

1. 在 **Members** 中邀请成员，只在确有全 Lab 管理需求时设为 manager。
2. 在 **Organization** 中按现实语义创建组织单元，不需要强制填满三级。
3. 将成员加入组织单元，并指定 `manager` 或 `member`。
4. 一个成员需要跨组协作时，将其加入多个组织单元，不要复制人员或树节点。

### 创建授权

1. 进入 **Access > Grants**，选择 **Add grant**。
2. 选择 User 或组织单元。
3. 选择 Lab、Project 或 Protocol 作用域。
4. 选择角色，按需设置向下继承、过期时间和原因。
5. 在 **Effective access** 中选择成员和资源，核对最终能力与来源。

长期稳定的组织权限应优先授予组织单元；个人授权适合例外或临时协作。外部合作者建议设置过期时间。

### 撤销与审计

授权通过 revoke 终止，不会从历史中物理删除。Lab owner 和 manager 可在 **Audit** 中查看授权的创建、修改和撤销，以及移除 Lab 成员时引发的直接授权撤销。它是授权变更审计，不是包含所有登录、数据读取和 Record 修改的全面安全审计系统。

## 常见权限场景

- **整个研究分支只读**：对上级组织单元在 Lab 作用域授予 Viewer，并启用向下继承。
- **临时参与单个 Project**：对用户在指定 Project 授予 Contributor，设置过期时间。
- **敏感 Protocol 隔离**：关闭该 Protocol 的资源继承，再只对需要访问的 User 或组织单元创建直接授权。
- **矩阵协作**：将成员同时加入学科课题组和跨部门项目团队，两个组织分支的有效授权自动取并集。

## API 索引

在默认同源部署中，以下路径使用 `/api` 前缀：

| 用途 | 接口 |
| --- | --- |
| 角色目录 | `GET /api/access/roles` |
| 组织单元树 | `GET /api/access/labs/{lab_id}/organizational-units` |
| 创建组织单元 | `POST /api/access/organizational-units` |
| 更新、删除组织单元 | `PUT` / `DELETE /api/access/organizational-units/{unit_id}` |
| 组织单元成员 | `POST /api/access/organizational-units/{unit_id}/members` / `DELETE /api/access/organizational-units/{unit_id}/members/{user_id}` |
| 授权列表 | `GET /api/access/labs/{lab_id}/grants` |
| 创建、更新、撤销授权 | `POST /api/access/grants` / `PUT /api/access/grants/{grant_id}` / `POST /api/access/grants/{grant_id}/revoke` |
| 可管理作用域 | `GET /api/access/labs/{lab_id}/manageable-scopes` |
| 有效权限解释 | `GET /api/access/labs/{lab_id}/effective` |
| 授权审计 | `GET /api/access/labs/{lab_id}/audit` |
| Project / Protocol 继承开关 | `PUT /api/access/projects/{project_id}/inheritance` / `PUT /api/access/protocols/{protocol_id}/inheritance` |

新授权主体使用 `subject_type=org_unit` 和 `org_unit_id`。为了让已部署客户端平滑升级，API 仍接受历史 `subject_type=team` / `group_id` 和 `/access/teams` 路径，但它们不再出现在 OpenAPI 中，新集成不应继续使用。

API 仍会执行 Lab 成员校验、委派上限、主体与资源归属校验；不应依赖前端隐藏按钮作为安全边界。

## 排错

| 现象 | 检查项 |
| --- | --- |
| 看不到 Organization 或 Access | 确认 `LAB_STRUCTURE_MODE=structured` 并重启 API；single-Lab Web 配置变更后需重建 Web |
| 成员看不到 Project | 确认仍是 Lab 成员；检查授权主体、过期/撤销状态、`inherit_to_children` 和 Project 继承开关 |
| 看得到但不能编辑 | 在 Effective access 中确认是否具有相应 `protocol.*` 或 `record.*` 能力 |
| 无法授予某角色 | 确认授权人在目标作用域具有 `access.manage` 且没有超过委派上限；owner/admin 需在 Members 管理 |
| 组织单元 manager 无法访问资源 | 这是预期行为；请另行授予 User 或组织单元资源角色 |
| 撤销后列表中看不到历史 | 在 Grants 中启用“包含已撤销”，或在 Audit 中查看 |

## 明确边界

当前模型有意保持可解释和可运维，不包含：

- 无限层级组织树；
- 显式拒绝规则和允许/拒绝优先级；
- 任意 ABAC 或策略表达式；
- 字段级、单条 Record 级或数据脱敏策略；
- 全面的安全事件审计、SSO / LDAP 和自动身份生命周期。

这些能力如果成为部署的必须条件，应作为独立的企业身份与合规工程设计，不应通过继续增加组织树深度或临时角色规避。
