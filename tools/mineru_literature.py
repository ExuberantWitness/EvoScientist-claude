"""MinerU 文献子管道: Ingest → Index → Wiki → Retrieve → Deep Read.

Phase G 核心模块. 借鉴 MinerU Document Explorer 的 5 阶段文献管线,
置于 W3 Research 内部.

当前为 stub — 完整实现需要 PDF 解析 + BM25 索引 +
LLM Wiki 生成 + MCP 工具接口.
"""

import json
import time
from pathlib import Path


class LiteraturePipeline:
    """文献知识管线: 5 阶段."""

    def __init__(self, vault_dir: Path):
        self.vault_dir = Path(vault_dir)
        self.literature_dir = self.vault_dir / "Literature"
        self.literature_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.vault_dir / "_index" / "literature_index.json"

    # Stage 1: Ingest — 解析论文 Markdown → 结构化数据
    def ingest(self, paper_id: str, title: str, content: str, *,
               source: str = "", doi: str = "", tags: list[str] | None = None) -> dict:
        """摄入一篇论文."""
        paper_file = self.literature_dir / f"{paper_id}.md"

        # 结构化模板
        paper_md = f"""---
id: {paper_id}
source: {source}
doi: {doi}
tags: {tags or []}
ingested: {time.time()}
---

# {title}

## 摘要
{content[:500]}

## 方法实体
(待 LLM 提取)

## 瓶颈描述
(待 LLM 提取)

## 关系图
(待 LLM 提取)
"""
        paper_file.write_text(paper_md, encoding="utf-8")
        return {"paper_id": paper_id, "file": str(paper_file.relative_to(self.vault_dir))}

    # Stage 2: Index — 构建 keyword 索引
    def build_index(self) -> dict:
        """从文献目录构建关键词索引."""
        index = {}
        for md_file in self.literature_dir.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            # Simple keyword extraction
            keywords = set()
            for line in text.split("\n"):
                if line.startswith("tags:"):
                    for tag in line.replace("tags:", "").strip("[] ").split(","):
                        keywords.add(tag.strip().strip('"'))
            for kw in keywords:
                index.setdefault(kw, []).append(md_file.stem)
        self.index_file.write_text(json.dumps(index, indent=2, ensure_ascii=False))
        return {"keywords": len(index), "papers": len(list(self.literature_dir.glob("*.md")))}

    # Stage 3: Wiki — LLM 从文献提取概念和链接
    def build_wiki(self) -> dict:
        """从文献提取方法实体 + 创建 Obsidian 链接. (需要 LLM)"""
        papers = list(self.literature_dir.glob("*.md"))
        return {"papers_processed": len(papers), "wiki_pages": 0,
                "status": "stub — full implementation requires LLM pipeline"}

    # Stage 4: Retrieve — 搜索文献
    def retrieve(self, query: str) -> list[dict]:
        """搜索文献 (keyword match)."""
        if not self.index_file.exists():
            self.build_index()
        index = json.loads(self.index_file.read_text())
        results = []
        for kw, paper_ids in index.items():
            if query.lower() in kw.lower():
                for pid in paper_ids:
                    paper_file = self.literature_dir / f"{pid}.md"
                    if paper_file.exists():
                        results.append({
                            "paper_id": pid,
                            "title": paper_file.read_text(encoding="utf-8").split("\n")[0].lstrip("# "),
                        })
        return results[:20]

    # Stage 5: Deep Read — 读论文结构化摘要
    def deep_read(self, paper_id: str) -> dict:
        """返回结构化摘要."""
        paper_file = self.literature_dir / f"{paper_id}.md"
        if not paper_file.exists():
            return {"error": f"Paper {paper_id} not found"}
        text = paper_file.read_text(encoding="utf-8")
        return {
            "paper_id": paper_id,
            "content": text[:3000],
            "sections": [line.lstrip("# ").strip() for line in text.split("\n")
                        if line.startswith("## ")],
        }
