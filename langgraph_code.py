import os
import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Any, Union
from enum import Enum
from pydantic import BaseModel, Field
from paddleocr import PaddleOCRVL
from openai import OpenAI
import instructor
from langgraph.graph import StateGraph, END
import importlib.util
 
# ==============================
# 🔧 全局配置 & 工具
# ==============================

ocr_pipeline = PaddleOCRVL()

def get_client(model_api: str, model_key: str):
    return instructor.from_openai(
        OpenAI(api_key=model_key, base_url=model_api),
        mode=instructor.Mode.JSON
    )

def safe_input(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("❌ 输入不能为空，请重新输入。")

def clean_null(obj):
    if isinstance(obj, dict):
        return {k: clean_null(v) for k, v in obj.items() if v is not None}
    elif isinstance(obj, list):
        return [clean_null(item) for item in obj]
    else:
        return obj

# ==============================
# 🧠 State 定义
# ==============================

class CatalogPage(BaseModel):
    catalog: bool
    page: int

class ChapterEntry(BaseModel):
    chapter: str
    start_page: int
    end_page: int

class QuestionItem(BaseModel):
    id: int
    chapter: str
    question: str
    options: Optional[Dict[str, str]] = None
    answer: Optional[str] = None
    type: Optional[str] = None
    content: Optional[str] = None
    system: Optional[str] = None
    disease: Optional[str] = None
    qa_start: Optional[int] = None
    qa_end: Optional[int] = None

class AppState(BaseModel):
    # 配置
    input_path: str = ""
    output_path: str = ""
    model_api: str = ""
    model_name: str = ""
    model_key: str = ""

    # 中间状态
    md_dir: str = ""
    total_pages: int = 0
    catalog_pages_raw: List[CatalogPage] = Field(default_factory=list)
    catalog_start: Optional[int] = None
    catalog_end: Optional[int] = None
    content_start: Optional[int] = None
    chapters: List[ChapterEntry] = Field(default_factory=list)
    qa_pages: List[Dict[str, int]] = Field(default_factory=list)  # [{chapter, qa_start, qa_end}]
    questions: List[QuestionItem] = Field(default_factory=list)

    # 控制标志（用于人工确认）
    user_confirmed_catalog: bool = False
    user_confirmed_qa: bool = False

# ==============================
# 🔄 节点函数（Nodes）
# ==============================

def pdf_to_markdown(state: AppState) -> dict:
    print("🖼️ 正在将 PDF 转换为 Markdown 文档……")
    output = ocr_pipeline.predict(state.input_path)
    md_dir = os.path.join(state.output_path, "md")
    os.makedirs(md_dir, exist_ok=True)

    for res in output:
        res.save_to_markdown(save_path=md_dir)

    # 重命名文件：xxx_123.md → 123.md
    for filename in os.listdir(md_dir):
        if filename.endswith(".md"):
            match = re.search(r"_(\d+)\.md$", filename)
            if match:
                page_num = match.group(1)
                old_path = os.path.join(md_dir, filename)
                new_path = os.path.join(md_dir, f"{page_num}.md")
                if not os.path.exists(new_path):
                    os.rename(old_path, new_path)
                else:
                    print(f"⚠️ 跳过重命名（已存在）: {new_path}")
    return {"md_dir": md_dir}

def detect_catalog_pages(state: AppState) -> dict:
    client = get_client(state.model_api, state.model_key)
    path = Path(state.md_dir)
    md_files = sorted(path.glob("*.md"), key=lambda p: int(p.stem))
    max_pages = int(input("🔍 仅分析前 N 页以识别目录页（默认 20）: ") or "20")

    with open("prompts/prompt1.txt", 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    results = []
    for md_file in md_files[:max_pages]:
        try:
            page_num = int(md_file.stem)
        except ValueError:
            continue
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        prompt = prompt_template.format(content=content)
        result: CatalogPage = client.chat.completions.create(
            model=state.model_name,
            messages=[{"role": "user", "content": prompt}],
            response_model=CatalogPage
        )
        result.page = page_num
        results.append(result)
        print(f"处理完成: page={page_num}, catalog={result.catalog}")

    return {"catalog_pages_raw": results}

def request_catalog_confirmation(state: AppState) -> dict:
    print("\n📋 系统已初步识别目录页，请您人工确认准确范围（包含起止页）：")
    start = int(input("📖 目录起始页码（含）: "))
    end = int(input("📖 目录结束页码（含）: "))
    return {
        "catalog_start": start,
        "catalog_end": end,
        "user_confirmed_catalog": True
    }

def extract_chapters(state: AppState) -> dict:
    client = get_client(state.model_api, state.model_key)
    path = Path(state.md_dir)

    with open("prompts/prompt2.txt", "r", encoding="utf-8") as f:
        prompt_template = f.read()

    class ChapterCatalog(BaseModel):
        chapter: str
        start_page: int

    all_chapters_raw = []
    for page in range(state.catalog_start, state.catalog_end + 1):
        file_path = path / f"{page}.md"
        if not file_path.exists():
            print(f"警告: {file_path} 不存在，跳过")
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            continue
        prompt = prompt_template.format(content=content)
        try:
            results: List[ChapterCatalog] = client.chat.completions.create(
                model=state.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_model=List[ChapterCatalog]
            )
            all_chapters_raw.extend(results)
        except Exception as e:
            print(f"❌ 处理 {file_path.name} 时出错: {e}")

    content_start = int(input("请输入正文开始的页码（包含）: ") or (state.catalog_end + 1))
    for chap in all_chapters_raw:
        chap.start_page += content_start - 1

    total_page = len([f for f in path.iterdir() if f.is_file() and f.suffix == ".md"])
    new_chapters = []
    for i, chap in enumerate(all_chapters_raw):
        end_page = total_page - 1 if i == len(all_chapters_raw) - 1 else all_chapters_raw[i + 1].start_page - 1
        new_chapters.append(ChapterEntry(
            chapter=chap.chapter,
            start_page=chap.start_page,
            end_page=end_page
        ))

    with open(os.path.join(state.output_path, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump([c.model_dump() for c in new_chapters], f, ensure_ascii=False, indent=2)

    return {
        "chapters": new_chapters,
        "total_pages": total_page,
        "content_start": content_start
    }

def detect_qa_pages(state: AppState) -> dict:
    client = get_client(state.model_api, state.model_key)
    md_path = Path(state.md_dir)

    with open("prompts/prompt3.txt", 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    class IsQA(BaseModel):
        is_qa: bool

    results = []
    for entry in state.chapters:
        for page in range(entry.start_page, entry.end_page + 1):
            file_path = md_path / f"{page}.md"
            if not file_path.exists():
                continue
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            prompt = prompt_template.format(content=content.strip())
            try:
                resp = client.chat.completions.create(
                    model=state.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=IsQA
                )
                results.append({"chapter": entry.chapter, "page": page, "is_qa": resp.is_qa})
            except Exception as e:
                print(f"页码 {page} 处理出错: {e}")
                results.append({"chapter": entry.chapter, "page": page, "is_qa": False})

    # 强制每章最后一页为 QA
    last_index_of = {}
    for i, item in enumerate(results):
        last_index_of[item['chapter']] = i
    for i, item in enumerate(results):
        if last_index_of[item['chapter']] == i:
            item['is_qa'] = True

    # 合并连续 QA 页
    from collections import OrderedDict
    chapter_qa = OrderedDict()
    for item in results:
        if item["is_qa"]:
            ch = item["chapter"]
            if ch not in chapter_qa:
                chapter_qa[ch] = {'start': item["page"], 'end': item["page"]}
            else:
                chapter_qa[ch]['end'] = item["page"]

    qa_list = [{"chapter": ch, "qa_start": v["start"], "qa_end": v["end"]} for ch, v in chapter_qa.items()]

    with open(os.path.join(state.output_path, "qapage.json"), "w", encoding="utf-8") as f:
        json.dump(qa_list, f, ensure_ascii=False, indent=2)

    return {"qa_pages": qa_list}

def request_qa_confirmation(state: AppState) -> dict:
    print(f"\n✅ 题目所在页码已推断完成！请检查：{state.output_path}/qapage.json")
    input("🔧 确认无误后，请按回车继续……")
    return {"user_confirmed_qa": True}

def extract_questions(state: AppState) -> dict:
    client = get_client(state.model_api, state.model_key)
    md_path = Path(state.md_dir)

    with open("prompts/prompt4.txt", 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    class Options(BaseModel):
        A: str; B: str
        C: Optional[str] = None; D: Optional[str] = None
        E: Optional[str] = None; F: Optional[str] = None
        G: Optional[str] = None; H: Optional[str] = None

    class Question(BaseModel):
        question: str
        options: Optional[Options] = None

    all_questions = []
    for entry in state.qa_pages:
        pages_content = []
        for p in range(entry["qa_start"], entry["qa_end"] + 1):
            fpath = md_path / f"{p}.md"
            if fpath.exists():
                with open(fpath, 'r', encoding='utf-8') as f:
                    txt = f.read().strip()
                    if txt:
                        pages_content.append(txt)
        if not pages_content:
            continue
        content = "\n\n".join(pages_content)
        prompt = prompt_template.format(content=content)
        try:
            qs: List[Question] = client.chat.completions.create(
                model=state.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_model=list[Question],
                max_retries=2
            )
            for idx, q in enumerate(qs, 1):
                q_dict = q.model_dump()
                q_dict.update({
                    "id": idx,
                    "chapter": entry["chapter"],
                    "qa_start": entry["qa_start"],
                    "qa_end": entry["qa_end"]
                })
                all_questions.append(QuestionItem(**clean_null(q_dict)))
        except Exception as e:
            print(f"提取题目失败: {e}")

    with open(os.path.join(state.output_path, "question.json"), "w", encoding="utf-8") as f:
        json.dump([q.model_dump() for q in all_questions], f, ensure_ascii=False, indent=2)

    return {"questions": all_questions}

def extract_answers(state: AppState) -> dict:
    client = get_client(state.model_api, state.model_key)
    md_path = Path(state.md_dir)

    with open("prompts/prompt5.txt", 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    class QA(BaseModel):
        answer: Optional[str] = None

    updated_questions = []
    for q in state.questions:
        pages_content = []
        for p in range(q.qa_start, q.qa_end + 1):
            fpath = md_path / f"{p}.md"
            if fpath.exists():
                with open(fpath, 'r', encoding='utf-8') as f:
                    txt = f.read().strip()
                    if txt:
                        pages_content.append(txt)
        content = "\n\n".join(pages_content)
        if not content.strip():
            q.answer = None
            updated_questions.append(q)
            continue

        options_str = "（本题无选项，为非选择题）"
        if q.options:
            options_str = "\n".join([f"{k}. {v}" for k, v in q.options.items() if v])

        prompt = prompt_template.format(question=q.question, options=options_str, content=content)
        try:
            resp: QA = client.chat.completions.create(
                model=state.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_model=QA,
                max_retries=2
            )
            q.answer = resp.answer
        except Exception as e:
            print(f"答案提取失败 (ID={q.id}): {e}")
            q.answer = None
        updated_questions.append(q)

    with open(os.path.join(state.output_path, "qa.json"), "w", encoding="utf-8") as f:
        json.dump([q.model_dump() for q in updated_questions], f, ensure_ascii=False, indent=2)

    return {"questions": updated_questions}

def classify_question_type(state: AppState) -> dict:
    client = get_client(state.model_api, state.model_key)

    with open("prompts/prompt6.txt", 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    class QType(str, Enum):
        type1 = "选择题"
        type2 = "填空题"
        type3 = "判断题"
        type4 = "简答题"

    class QAType(BaseModel):
        type: QType

    updated = []
    for q in state.questions:
        options_str = "（本题无选项，为非选择题）"
        if q.options:
            options_str = "\n".join([f"{k}. {v}" for k, v in q.options.items() if v])
        prompt = prompt_template.format(question=q.question, options=options_str, answer=q.answer or "")
        try:
            resp = client.chat.completions.create(
                model=state.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_model=QAType,
                max_retries=2
            )
            q.type = resp.type.value
        except Exception as e:
            print(f"类型分类失败 (ID={q.id}): {e}")
            q.type = "未知"
        updated.append(q)

    with open(os.path.join(state.output_path, "qatype.json"), "w", encoding="utf-8") as f:
        json.dump([q.model_dump() for q in updated], f, ensure_ascii=False, indent=2)

    return {"questions": updated}

def classify_content_type(state: AppState) -> dict:
    client = get_client(state.model_api, state.model_key)

    with open("prompts/prompt7.txt", 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    class ContentTypeEnum(str, Enum):
        ContentType1 = "病因病理"
        ContentType2 = "临床表现"
        ContentType3 = "诊断治疗"
        ContentType4 = "文献指南"
        ContentType5 = "其他"

    class ContentType(BaseModel):
        content: ContentTypeEnum

    updated = []
    for q in state.questions:
        options_str = "（本题无选项，为非选择题）"
        if q.options:
            options_str = "\n".join([f"{k}. {v}" for k, v in q.options.items() if v])
        prompt = prompt_template.format(question=q.question, options=options_str, answer=q.answer or "")
        try:
            resp = client.chat.completions.create(
                model=state.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_model=ContentType,
                max_retries=2
            )
            q.content = resp.content.value
        except Exception as e:
            print(f"内容分类失败 (ID={q.id}): {e}")
            q.content = "其他"
        updated.append(q)

    with open(os.path.join(state.output_path, "qacontent.json"), "w", encoding="utf-8") as f:
        json.dump([q.model_dump() for q in updated], f, ensure_ascii=False, indent=2)

    return {"questions": updated}

def classify_system(state: AppState) -> dict:
    client = get_client(state.model_api, state.model_key)

    with open("prompts/prompt8.txt", 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    class SystemEnum(str, Enum):
        System1 = "呼吸系统"
        System2 = "心血管系统"
        System3 = "消化系统"
        System4 = "泌尿系统"
        System5 = "血液系统"
        System6 = "内分泌系统"
        System7 = "风湿性疾病"
        System8 = "运动系统"
        System9 = "传染病、性病"
        System10 = "产科学"
        System11 = "妇科学"
        System12 = "儿科疾病"
        System13 = "神经内外科疾病"
        System14 = "精神病"
        System15 = "其他"

    class System(BaseModel):
        system: SystemEnum

    updated = []
    for q in state.questions:
        options_str = "（本题无选项，为非选择题）"
        if q.options:
            options_str = "\n".join([f"{k}. {v}" for k, v in q.options.items() if v])
        prompt = prompt_template.format(chapter=q.chapter, question=q.question, options=options_str, answer=q.answer or "")
        try:
            resp = client.chat.completions.create(
                model=state.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_model=System,
                max_retries=2
            )
            q.system = resp.system.value
        except Exception as e:
            print(f"系统分类失败 (ID={q.id}): {e}")
            q.system = "其他"
        updated.append(q)

    with open(os.path.join(state.output_path, "qasystem.json"), "w", encoding="utf-8") as f:
        json.dump([q.model_dump() for q in updated], f, ensure_ascii=False, indent=2)

    return {"questions": updated}

def classify_disease(state: AppState) -> dict:
    client = get_client(state.model_api, state.model_key)
    disease_path = "disease"

    with open("prompts/prompt9.txt", 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    updated = []
    for q in state.questions:
        system = q.system
        file_path = os.path.join(disease_path, f"{system}.py")
        if not os.path.exists(file_path):
            q.disease = None
            updated.append(q)
            continue

        spec = importlib.util.spec_from_file_location(f"{system}_module", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, 'Disease'):
            q.disease = None
            updated.append(q)
            continue

        DiseaseEnum = module.Disease

        options_str = "（本题无选项，为非选择题）"
        if q.options:
            options_str = "\n".join([f"{k}. {v}" for k, v in q.options.items() if v])
        disease_list_str = "\n".join([f"- {item.value}" for item in DiseaseEnum])

        prompt = prompt_template.format(
            disease_list=disease_list_str,
            question=q.question,
            options=options_str,
            answer=q.answer or ""
        )

        class DiseaseAnnotation(BaseModel):
            disease: DiseaseEnum

        try:
            resp = client.chat.completions.create(
                model=state.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_model=DiseaseAnnotation,
                max_retries=2
            )
            q.disease = resp.disease.value
        except Exception as e:
            print(f"疾病标注失败 (ID={q.id}, 系统={system}): {e}")
            q.disease = None
        updated.append(q)

    with open(os.path.join(state.output_path, "qadisease.json"), "w", encoding="utf-8") as f:
        json.dump([q.model_dump() for q in updated], f, ensure_ascii=False, indent=2)

    return {"questions": updated}

# ==============================
# 🌐 构建 Graph
# ==============================

def build_graph() -> StateGraph:
    graph = StateGraph(AppState)

    # 添加所有节点
    graph.add_node("pdf_to_md", pdf_to_markdown)
    graph.add_node("detect_catalog", detect_catalog_pages)
    graph.add_node("confirm_catalog", request_catalog_confirmation)
    graph.add_node("extract_chapters", extract_chapters)
    graph.add_node("detect_qa", detect_qa_pages)
    graph.add_node("confirm_qa", request_qa_confirmation)
    graph.add_node("extract_questions", extract_questions)
    graph.add_node("extract_answers", extract_answers)
    graph.add_node("classify_type", classify_question_type)
    graph.add_node("classify_content", classify_content_type)
    graph.add_node("classify_system", classify_system)
    graph.add_node("classify_disease", classify_disease)

    # 设置入口
    graph.set_entry_point("pdf_to_md")

    # 连接流程
    graph.add_edge("pdf_to_md", "detect_catalog")
    graph.add_edge("detect_catalog", "confirm_catalog")
    graph.add_edge("confirm_catalog", "extract_chapters")
    graph.add_edge("extract_chapters", "detect_qa")
    graph.add_edge("detect_qa", "confirm_qa")
    graph.add_edge("confirm_qa", "extract_questions")
    graph.add_edge("extract_questions", "extract_answers")
    graph.add_edge("extract_answers", "classify_type")
    graph.add_edge("classify_type", "classify_content")
    graph.add_edge("classify_content", "classify_system")
    graph.add_edge("classify_system", "classify_disease")
    graph.add_edge("classify_disease", END)

    return graph.compile()

# ==============================
# ▶️ 主程序入口
# ==============================

if __name__ == "__main__":
    print("\n🤖 欢迎使用 qaminer (LangGraph 版)！")
    print("请依次提供以下配置信息：\n")

    initial_state = AppState(
        input_path=safe_input("1️⃣ 请输入 PDF 文件路径（如 /home/user/pdf）: "),
        output_path=safe_input("2️⃣ 请输入输出目录路径（如 /home/user/output）: "),
        model_api=safe_input("3️⃣ 请输入模型服务 API（如 https://.../v1）: "),
        model_name=safe_input("4️⃣ 请输入模型名称（如 qwen3-max）: "),
        model_key=safe_input("5️⃣ 请输入模型密钥（如 sk-xxxx）: ")
    )

    app = build_graph()
    final_state = app.invoke(initial_state)

    print("\n✨ 处理流程已全部完成！")
    print(f"📚 所有结构化结果已保存至：{final_state.output_path}")
    print("💡 建议：请人工抽查部分章节，确保模型识别准确。")