| Tool Name              | Description                                                   | Status                    | 🔑 Credits                  |
|------------------------|---------------------------------------------------------------|---------------------------|-----------------------------|
| **Find File**          | Search filenames by keyword to quickly locate assets.         | ✅ Free                    | —                           |
| **Read File**          | Reads and returns file content as clean JSON.                 | ✅ Free                    | —                           |
| **JSON Manager**       | Structured editor for JSON files — add, update, delete.       | ✅ Free                    | —                           |
| **System Settings**    | Internal registry controller for tools, actions, and unlocks. | {{status:system_settings}}| {{credits:system_settings}} |
| **Terminal Tool**      | Controlled, sandboxed shell access for command execution.     | {{status:terminal}}       | {{credits:terminal}}        |
| **Mash**               | Run a nostalgic “MASH” game for fun outcomes.                 | {{status:mash_tool}}      | {{credits:mash_tool}}       |
| **Buffer Engine**      | Schedule and auto-post content to external platforms.         | {{status:buffer_engine}}  | {{credits:buffer_engine}}   |
| **Article Builder**    | Compile a blog post from structured outlines and data.        | {{status:article_builder_tool}} | {{credits:article_builder_tool}} |
| **Outline Editor**     | Create, manage, and publish structured content docs.          | {{status:outline_editor}} | {{credits:outline_editor}}  |
| **Mem**                | Syncs with Mem for note storage and retrieval.                | {{status:mem_tool}}       | {{credits:mem_tool}}        |
| **Github**             | Clone, commit, and push repos from GPT-managed workflows.     | {{status:github_tool_universal}} | {{credits:github_tool_universal}} |
| **Ideogram**           | Generates AI-enhanced visual assets from prompt input.        | {{status:ideogram_tool}}  | {{credits:ideogram_tool}}   |
| **Code Editor**        | Create, patch, and modify code live in the Orchestrate env.   | {{status:code_editor}}    | {{credits:code_editor}}     |
| **Check Credits**      | View your remaining unlock credits and tools currently unlocked. | ✅ Free                 | —                           |

> **Tool Status (**`**Free**` **vs** `**Locked**`**) is dynamically rendered.**  
> The `Status` and `Credits` columns in this table should be populated at runtime based on the `getSupportedActions` endpoint.
> 
> Lock/unlock **logic is determined by** `**system_settings.ndjson**`, but that file should **not** be used for rendering or UI display — it's for system execution only.
> 
> The **structure and descriptions** of the tool table (this markdown doc) define what’s shown to the user.
> 
> 🛑 *Do **not** hardcode lock states here. Do **not** use* `*system_settings.ndjson*` *to render UI.*
