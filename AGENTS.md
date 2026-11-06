## Ruby/Rails Comment Rules

- 在 Ruby/Rails 代码或脚本中新增标准注释块时，`@author` 固定使用 `draven.chen <draven.chen@rccchina.com.cn>`。
- 在 Ruby/Rails 代码或脚本中新增标准注释块时，必须添加 `@jira`，取值使用当前 git 分支名，例如：`@jira [draven/WPL-6089]`。

## Git 提交约定

- 每次完成代码修改并通过相关验证后，默认提交本次任务相关改动，并推送到远程仓库，无需再次确认。
- 只提交当前任务涉及的文件，保留其他未提交改动；不要提交密钥、日志、构建产物或 `.DS_Store`。
- 提交或推送失败时，保留本地改动并说明原因；不要强制推送或覆盖他人的提交。
