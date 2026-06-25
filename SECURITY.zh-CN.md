# 安全政策

[English](SECURITY.md)

## 支持版本

Community Edition 目前仍处于公开发布准备阶段。除非明确维护 release branch，安全修复应面向最新 `main` 分支。

## 报告漏洞

如发现疑似漏洞，请私下报告给维护者，不要在公开 issue 中包含可利用细节。

不要在公开 issue 或 pull request 中包含真实凭证、私钥、患者数据、未发表科研数据或机构私有数据集。

## 数据处理

Airalogy Platform 可能管理敏感科研记录和大体量科学文件。自托管部署方需要自行配置：

- HTTPS termination
- 数据库备份
- 对象存储访问策略
- 密钥管理
- 认证提供方
- 审计保留
- 本地法规要求
