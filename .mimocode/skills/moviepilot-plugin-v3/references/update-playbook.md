# 本 skill 的更新与校正流程

目标：让 `moviepilot-plugin-v3` 始终与官方文档同步，「随时可更新、随时可修复」。

## 何时触发更新

- 开发/审核任务开始前，且距 `last_verified` 超过约 30 天。
- 用户明确说「更新插件规范 / 官方文档改了 / 这条规则不对」。
- 实际宿主行为与本 skill 冲突时（以宿主为准，回改 skill）。
- 官方发布新的专题文档或 `manifest.py` 变更。

## 更新步骤

1. **拉取权威文档**（用 webfetch 抓 markdown）：
   - `docs/Plugin_Development.md`（主指南）
   - `docs/V3_Plugin_Adaptation.md`（迁移）
   - `docs/V3_API_Response_Adaptation.md`（API）
   - `docs/Repository_Guide.md`（发布）
   - 必要时对应 FAQ 篇目
   - `MoviePilot` 仓 `app/runtime/compat/manifest.py`（旧导入映射）
2. **对照修订**：
   - 逐节 diff 本 skill 的 SKILL.md 与 references/，改掉过期规则、补新增规则。
   - 只写「结论 + 够用的示例」，细节留在官方文档链接处，避免本 skill 变成文档全文副本（防漂移）。
3. **校验一致性**：
   - 三处版本规则、目录结构、SDK 映射表在 SKILL.md 与 references 之间不互相矛盾。
   - frontmatter `name` 与目录名一致；description 仍含触发词且 < 1024 字符。
4. **更新 `last_verified`** 为当前日期（SKILL.md 第 1 节）。
5. **跑校验脚本**：
   ```bash
   python C:/Users/leo89/.local/share/mimocode/builtin_skills/desktop-1579e7d/skills/skill-creator/scripts/validate_skill.py D:/code/mp-plugins/.mimocode/skills/moviepilot-plugin-v3
   ```
   要求 0 error。
6. **回归**：用一个已知问题（如「命令 event 传字符串会怎样」）确认修订后的条目仍能给出正确诊断。

## 修复单条错误规则

用户指出某条不对时：

1. 定位 SKILL.md 或 references/ 中对应条目。
2. 以官方文档/V3 宿主源码验证正确行为。
3. 改完在该条目旁保持简洁（不要留「曾为 xxx」的考古注释）。
4. 若该错误来自某个真实案例，把它固化进「Troubleshooting」或「审核清单」，这是最高价值的迭代。

## 文件职责

- `SKILL.md`：日常开发/审核所需的全部硬规则 + 清单 + 排错表（保持可独立使用）。
- `references/v2-to-v3-migration.md`：迁移细节与代码对照。
- `references/update-playbook.md`：本文件。
- `locales/*.json`：仅 displayName/brief，不放规则。
