"""
Feishu Markdown adapter for converting standard Markdown to Feishu card markdown format.

飞书卡片 markdown 标签支持的语法:
- **粗体** / *斜体* / ~~删除线~~
- `行内代码`
- ```代码块```（原生支持，含语法高亮）
- [链接](url)
- 引用块 (> )
- 有序/无序列表
- 表格

不支持:
- 标题 (#)（需要转换为粗体）
- 图片 (![alt](url))（需要用 img 元素）
"""

import re


class FeishuMarkdownAdapter:
    """将标准 Markdown 适配为飞书卡片 markdown 标签兼容格式

    飞书卡片的 markdown 标签原生支持代码块和表格，
    只需处理标题转换和段落间距优化。
    """

    @classmethod
    def adapt(cls, text: str) -> str:
        """将 markdown 文本适配为飞书卡片 markdown 格式"""
        if not text:
            return text

        # 1. 保护代码块（避免被标题转换等规则干扰）
        text, code_blocks = cls._protect_code_blocks(text)

        # 2. 转换标题为粗体（飞书 markdown 不支持 # 标题）
        text = cls._convert_headers(text)

        # 3. 优化段落间距
        text = cls._fix_paragraphs(text)

        # 4. 恢复代码块（原样保留，飞书 markdown 标签原生支持）
        text = cls._restore_code_blocks(text, code_blocks)

        return text.strip()

    @classmethod
    def _protect_code_blocks(cls, text: str) -> tuple[str, list[str]]:
        """提取代码块用占位符保护，防止内部内容被其他规则修改"""
        code_blocks: list[str] = []

        def replace_block(match: re.Match) -> str:
            code_blocks.append(match.group(0))
            return f"\x00CODEBLOCK_{len(code_blocks) - 1}\x00"

        # 匹配 ```...``` 代码块（支持有无语言标签）
        text = re.sub(r"```[\s\S]*?```", replace_block, text)
        return text, code_blocks

    @classmethod
    def _convert_headers(cls, text: str) -> str:
        """将 markdown 标题转换为粗体（飞书 markdown 不支持 # 标题语法）"""
        lines = text.split("\n")
        result = []

        for line in lines:
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if header_match:
                content = header_match.group(2)
                result.append(f"**{content}**")
                result.append("")  # 空行分隔
            else:
                result.append(line)

        return "\n".join(result)

    @classmethod
    def _fix_paragraphs(cls, text: str) -> str:
        """优化段落间距，移除多余空行"""
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    @classmethod
    def _restore_code_blocks(cls, text: str, code_blocks: list[str]) -> str:
        """恢复代码块（原样还原，飞书 markdown 标签原生支持 ``` 代码块）"""
        for idx, block in enumerate(code_blocks):
            text = text.replace(f"\x00CODEBLOCK_{idx}\x00", block)
        return text
