# Lab 权限管理

本文说明 `LAB_STRUCTURE_MODE=structured` 下的团队和研究资源权限。single-Lab profile 默认启用该模式；Community profile 默认为 `flat`，但可显式启用。

## 设计目标

权限模型将“人属于哪个组织”和“人可以操作哪些研究资源”分开：

- **组织结构**：Lab 下是最多三级的 Team 树。成员可同时属于多个 Team，因此也可表达矩阵组织。
- **资源结构**：Lab 下是最多三级的 Project 树，Project 下包含 Protocol，Protocol 下产生 Record。
- **连接两者**：作用域授权将 User 或 Team 与 Lab、Project 或 Protocol 连接。

Team 本身不代表研究权限。Team manager 可维护本 Team 及下级 Team，但只有获得作用域授权后才能访问研究资源。

## 权限主体

### User

授权可直接指向一个 Lab 成员。成员被移出 Lab 时，其直接授权会自动撤销，相应撤销会记入授权审计日志。

### Team

授权可指向 Team。用户获得：

- 直接所属 Team 的授权；
- 该 Team 所有上级 Team 的授权；
- 同时所属的其他 Team 及其上级 Team 的授权。

上级 Team 的授权因此可覆盖整个组织分支。父 Team manager 可创建和管理下级 Team；根 Team 的创建以及 Team 的移动由 Lab owner 或 manager 完成。

## 资源作用域与继承

授权有三种作用域：

| 作用域   | 精确对象      | 启用向下继承时                            |
| -------- | ------------- | ----------------------------------------- |
| Lab      | 当前 Lab      | 可向 Project、子 Project 和 Protocol 传播 |
| Project  | 指定 Project  | 可向子 Project 和 Protocol 传播           |
| Protocol | 指定 Protocol | 只作用于该 Protocol                       |

每条授权的 `inherit_to_children` 决定它是否向下传播。Project 和 Protocol 还有各自的 `inherit_permissions` 开关：

- Project 关闭继承时，不再接收父 Project 和 Lab 授权，但它自身的直接授权仍然有效。
- Protocol 关闭继承时，不再接收 Project 和 Lab 授权，但它自身的直接授权仍然有效。
- Lab owner 和 manager 的成员身份是 Lab 级管理权，不会被资源继承断点锁在外部。

对一个 Protocol，普通成员的计算链默认为：

```text
Protocol -> Project -> 父 Project -> Lab
```

遇到资源继承断点时停止向上查找；遇到未启用向下继承的上级授权时，该授权不会传播到当前资源。

## 角色与能力

`lab_owner` 和 `lab_admin` 是 Lab 成员身份，必须在 Members 中管理，不能作为普通作用域授权发放。其余角色可在 Access 工作台中授予 User 或 Team。

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

## 有效权限计算

用户的最终能力是所有有效来源的**并集**：

1. Lab owner 或 manager 成员身份；
2. 当前 User 的直接授权；
3. User 所属 Team 和上级 Team 的授权；
4. 当前资源和未被继承断点阻断的上级资源授权；
5. 兼容的旧 Project、Lab Group、Protocol 和 Project Group 角色。

只有未撤销且未过期的授权参与计算。系统不提供显式 `DENY`；如果一个来源给予 Viewer，另一个来源给予 Contributor，最终用户拥有 Contributor 增加的能力。

Access 工作台的 **Effective access** 可按 User、Project 和 Protocol 查看：

- 有效角色集；
- 合并后的能力集；
- 每个来源的主体、作用域、授权 ID 及是否继承。

Lab owner 和 manager 可查看任意成员的有效权限；普通成员只能查看自己。

## 授权委派

授权人必须在目标作用域同时满足：

1. 具有 `access.manage`；
2. 自身能力集完整包含待授予角色的能力集。

这是委派上限。例如 Project manager 可在自己管理的 Project 中授予 Contributor 或 Viewer，但不能授予 Lab administrator。Team manager 身份不包含 `access.manage`，不能仅凭团队管理权授予资源角色。

## 管理操作

### 建立组织

1. 在 **Members** 中邀请成员，并只在确有全 Lab 管理需求时设为 manager。
2. 在 **Teams** 中创建根 Team 和下级 Team。
3. 将成员加入 Team，并指定 `manager` 或 `member`。
4. 一个成员需要跨组协作时，将其加入多个 Team，不需要复制 Team。

### 创建授权

1. 进入 **Access > Grants**，选择 **Add grant**。
2. 选择 User 或 Team。
3. 选择 Lab、Project 或 Protocol 作用域。
4. 选择角色，按需设置向下继承、过期时间和原因。
5. 在 **Effective access** 中选择成员和资源，核对最终能力与来源。

长期稳定的组织权限应优先授予 Team；个人授权适合例外或临时协作。外部合作者建议设置过期时间。

### 撤销与审计

授权通过 revoke 终止，不会从历史中物理删除。Lab owner 和 manager 可在 **Audit** 中查看授权的创建、修改和撤销，以及移除 Lab 成员时引发的直接授权撤销。它是授权变更审计，不是包含所有登录、数据读取和 Record 修改的全面安全审计系统。

## 常见场景

### 整个研究分支只读

对上级 Team 在 Lab 作用域授予 Viewer，并启用向下继承。所有下级 Team 成员都可读取未关闭资源继承的 Project 和 Protocol。

### 临时参与单个 Project

对用户在指定 Project 授予 Contributor，设置过期时间，并根据是否允许访问子 Project 决定向下继承。

### 敏感 Protocol 隔离

在敏感 Protocol 上关闭资源继承，然后只对需要访问的 User 或 Team 创建 Protocol 直接授权。由于没有显式 `DENY`，关闭继承是阻止上级授权传入的必要步骤。

### 矩阵协作

将成员同时加入学科 Team 和项目 Team。两个 Team 的有效授权自动取并集，不需要创建一套独立的“矩阵角色”。

## API 索引

在默认同源部署中，以下路径使用 `/api` 前缀：

| 用途 | 接口 |
| --- | --- |
| 角色目录 | `GET /api/access/roles` |
| Team 树 | `GET /api/access/labs/{lab_id}/teams` |
| 创建、更新、删除 Team | `POST /api/access/teams` / `PUT` / `DELETE /api/access/teams/{team_id}` |
| Team 成员 | `POST /api/access/teams/{team_id}/members` / `DELETE /api/access/teams/{team_id}/members/{user_id}` |
| 授权列表 | `GET /api/access/labs/{lab_id}/grants` |
| 创建、更新、撤销授权 | `POST /api/access/grants` / `PUT /api/access/grants/{grant_id}` / `POST /api/access/grants/{grant_id}/revoke` |
| 可管理作用域 | `GET /api/access/labs/{lab_id}/manageable-scopes` |
| 有效权限解释 | `GET /api/access/labs/{lab_id}/effective` |
| 授权审计 | `GET /api/access/labs/{lab_id}/audit` |
| Project / Protocol 继承开关 | `PUT /api/access/projects/{project_id}/inheritance` / `PUT /api/access/protocols/{protocol_id}/inheritance` |

API 仍会执行 Lab 成员校验、委派上限、主体与资源归属校验；不应依赖前端隐藏按钮作为安全边界。

## 排错

| 现象 | 检查项 |
| --- | --- |
| 看不到 Teams 或 Access | 确认 `LAB_STRUCTURE_MODE=structured` 并重启 API；single-Lab Web 配置变更后需重建 Web |
| 成员看不到 Project | 确认仍是 Lab 成员；检查授权主体、过期/撤销状态、`inherit_to_children` 和 Project 继承开关 |
| 看得到但不能编辑 | 在 Effective access 中确认是否具有相应 `protocol.*` 或 `record.*` 能力 |
| 无法授予某角色 | 确认授权人在目标作用域具有 `access.manage` 且没有超过委派上限；owner/admin 需在 Members 管理 |
| Team manager 无法访问资源 | 这是预期行为；请另行授予 User 或 Team 资源角色 |
| 撤销后列表中看不到历史 | 在 Grants 中启用“包含已撤销”，或在 Audit 中查看 |

## 明确边界

当前模型有意保持可解释和可运维，不包含：

- 无限层级组织树；
- 显式拒绝规则和允许/拒绝优先级；
- 任意 ABAC 或策略表达式；
- 字段级、单条 Record 级或数据脱敏策略；
- 全面的安全事件审计、SSO / LDAP 和自动身份生命周期。

这些能力如果成为部署的必须条件，应作为独立的企业身份与合规工程设计，不应通过继续增加 Team 层级或临时角色规避。
