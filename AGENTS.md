# Codex 项目全局规则

本文件是本仓库内所有 Codex/AI 代码代理必须遵守的项目级工作规则。

## 中文与编码

1. 在 Windows PowerShell 中读取含中文文件时，不能信任默认控制台输出。
2. 读取、验证、迁移中文文本必须显式使用 UTF-8：
   - 优先使用 `node -e "fs.readFileSync(path, 'utf8')"` 检查真实内容。
   - 或使用 `Get-Content -Encoding UTF8`，必要时先设置 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`。
3. 如果终端出现 `闃挎牴寤?`、`棰勬祴` 之类 mojibake，必须立刻停止基于该输出做判断，并用 UTF-8 方式重新读取文件。
4. 不能把乱码复制进代码、测试、文档或 JSON 产物。
5. 修改中文 UI、报告、文档后，必须至少用一次 UTF-8 读取方式确认文件内容正常。

## 缓存与产物

1. 修改报告结构、artifact schema、预测发布逻辑或用户可见文案后，必须同步处理 `outputs/predictions` 下的旧产物。
2. 旧预测报告缓存不能继续被前端或 API 当作当前报告展示。
3. 清理旧产物时必须先归档，再迁移或失效化：
   - 归档目录建议为 `outputs/predictions/legacy-archive/YYYYMMDD-说明/`。
   - 当前 API 会读取的 `candidate-*.json`、`published-*.json`、`history/*.json`、`candidates/*.json` 必须检查并迁移。
   - `outputs/predictions/reports/*.json` 中的旧报告缓存必须归档或重建。
4. 普通用户可见报告不得出现以下内部词：
   - `artifact`
   - `candidate`
   - `seed`
   - `model_config_hash`
   - `透明试算`
   - `结构化概率`
   - `发布门禁`
   - `发布门槛`
5. 每次涉及报告展示的改动，都要用脚本扫描当前产物，确认上述词不会从当前 API 读取路径流出。

## 端到端验收

1. 只改生成器不算完成；必须确认现有页面实际读取到的产物也被迁移、重建或前端兼容。
2. 如果页面展示来自旧缓存，代码必须自动识别并降级处理，不能要求用户理解内部缓存机制。
3. 面向用户的验收至少包含：
   - 当前页面不再显示旧报告文案。
   - 模型与数据页解释数据未接入的真实原因。
   - 开发者详情默认折叠。
   - 前端测试和构建通过。
