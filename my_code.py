# 配置信息
print("\n🤖 欢迎使用 qaminer ！")
print("请依次提供以下配置信息：\n")

def safe_input(prompt: str) -> str:
    """安全输入：确保不为空"""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("❌ 输入不能为空，请重新输入。")

input_path = safe_input("1️⃣ 请输入 PDF 文件路径（如 /home/user/pdf）: ")
output_path = safe_input("2️⃣ 请输入输出目录路径（如 /home/user/output）: ")
model_api = safe_input("3️⃣ 请输入模型服务 API（如 https://dashscope.aliyuncs.com/compatible-mode/v1）: ")
model_name = safe_input("4️⃣ 请输入模型名称（如 qwen3-max）: ")
model_key = safe_input("5️⃣ 请输入模型密钥（如sk-2d7c12272772）: ")

# 库、包、函数
print("正在加载依赖库，请稍候……")
import os
import re
import json
from pathlib import Path
from enum import Enum
from typing import List, Optional
from paddleocr import PaddleOCRVL
from pydantic import BaseModel, Field
from openai import OpenAI
import instructor
import importlib

############################################ pdf转markdown
pipeline = PaddleOCRVL()
print("🖼️ 正在将 PDF 转换为 Markdown 文档（此过程可能需要较长时间）……")
output = pipeline.predict(input_path)
for res in output:
    res.print()
    # res.save_to_json(save_path="output")
    res.save_to_markdown(save_path=output_path+"/md")

############################################ 统一md文件名字
for filename in os.listdir(output_path+"/md"):
    if filename.endswith(".md"):
        # 使用正则匹配 _数字.md 的模式
        match = re.search(r"_(\d+)\.md$", filename)
        if match:
            page_number = match.group(1)  # 提取页码
            new_name = f"{page_number}.md"
            old_path = os.path.join(output_path+"/md", filename)
            new_path = os.path.join(output_path+"/md", new_name)

            # 防止覆盖：如果目标文件已存在，可以选择跳过或报错
            if os.path.exists(new_path):
                print(f"警告: {new_name} 已存在，跳过 {filename}")
                continue

            os.rename(old_path, new_path)
            print(f"重命名: {filename} -> {new_name}")

############################################ 识别目录页在哪几页

client = instructor.from_openai(
    OpenAI(
        api_key=model_key,
        base_url=model_api
    ),
    mode=instructor.Mode.JSON
)

class Catalog(BaseModel):
    catalog: bool=Field(description="此页内容是否属于目录页")
    page: int=Field(description="对应的页码，从0开始")

with open("prompts/prompt1.txt", 'r', encoding='utf-8') as f:
    prompt_template = f.read()

path=Path(output_path+"/md")

md_files = sorted(
    path.glob("*.md"),
    key=lambda p: int(p.stem)  # 按文件名数字排序（0.md, 1.md, ...）
)

all_results: List[Catalog] = []

max_pages = int(input("🔍 为提升效率，仅分析前 N 页以识别目录页。请输入最大分析页数（默认 20）: ") or "20")

for md_file in md_files[0:max_pages]:
    try:
        page_num = int(md_file.stem)
    except ValueError:
        print(f"跳过非数字命名的文件: {md_file.name}")
        continue

    # 读取文件内容
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 构造 prompt
    prompt = prompt_template.format(content=content)

    # 调用模型
    result: Catalog = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        response_model=Catalog
    )

    # 手动设置 page（虽然模型可能没返回，但我们强制加上）
    result.page = page_num

    all_results.append(result)
    print(f"处理完成: page={page_num}, catalog={result.catalog}")

catalog_pages = [item for item in all_results if item.catalog]
for page in catalog_pages:
    print(f"第 {page.page+1} 页是目录页.")

######################################### 人工校正目录页起始和结束
print("\n📋 系统已初步识别目录页，请您人工确认准确范围（包含起止页）：")
catalog_start = int(input("📖 目录起始页码（含）: "))
catalog_end = int(input("📖 目录结束页码（含）: "))

class ChapterCatalog(BaseModel):
    chapter: str=Field(description="章节名称")
    start_page: int=Field(description="章节开始的页码")

with open("prompts/prompt2.txt", "r", encoding="utf-8") as f:
    prompt_template_chapter = f.read()

# path = Path(output_path+"/md")  # ← 替换为你的 .md 文件目录

target_files = []
for page in range(catalog_start, catalog_end + 1):
    file_path = path / f"{page}.md"
    if file_path.exists():
        target_files.append(file_path)
    else:
        print(f"警告: {file_path} 不存在，跳过")

all_chapters: List[ChapterCatalog] = []

for md_file in target_files:
    with open(md_file, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        print(f"跳过空文件: {md_file}")
        continue

    prompt = prompt_template_chapter.format(content=content)

    try:
        result: List[ChapterCatalog] = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_model=List[ChapterCatalog]
        )
        all_chapters.extend(result)
        print(f"✅ 从 {md_file.name} 提取到 {len(result)} 个章节")
    except Exception as e:
        print(f"❌ 处理 {md_file.name} 时出错: {e}")
        # 可选：跳过或记录错误

################################# 根据目录页匹配对应章节的页码数
content_start=int(input("请输入正文开始的页码（包含）: ") or catalog_start+1)

for chapter in all_chapters:
    chapter.start_page += content_start-1

total_page = sum(1 for item in os.listdir(path) if os.path.isfile(os.path.join(path, item)))
print(f"本书总页数: {total_page}")

class ChapterCatalogWithEnd(BaseModel):
    chapter: str = Field(description="章节名称")
    start_page: int = Field(description="章节开始页码")
    end_page: int = Field(description="章节结束页码")
new_chapters: List[ChapterCatalogWithEnd] = []  
for i, chap in enumerate(all_chapters):
    if i == len(all_chapters) - 1:
        end_page = total_page - 1
    else:
        end_page = all_chapters[i + 1].start_page - 1
    
    new_chapters.append(
        ChapterCatalogWithEnd(
            chapter=chap.chapter,
            start_page=chap.start_page,
            end_page=end_page
        )
    )
all_chapters = new_chapters

chapters_dict = [chapter.model_dump() for chapter in all_chapters]
# 将字典列表保存为 JSON 文件
with open(output_path+"/catalog.json", "w", encoding="utf-8") as f:
    json.dump(chapters_dict, f, ensure_ascii=False, indent=2)

print(f"\n✅ 章节目录已生成！请检查并修正页码准确性：{output_path}/catalog.json")
input("🔧 修正完成后，请按回车继续……")

############################################# 判断每一章节包含题目和问题的页码
with open(output_path+"/catalog.json", "r", encoding="utf-8") as f:
    catalog = json.load(f)

# 读取提示词模板（只需读一次，放外面提升效率）
with open("prompts/prompt3.txt", 'r', encoding='utf-8') as f:
    prompt_template = f.read()

# 结果列表
results = []

# 定义响应模型（放在循环外）
class IsQA(BaseModel):
    is_qa: bool = Field(description="此页内容是否包括题目内容")

# Markdown 文件路径
md_path = Path(output_path+"/md")

# 遍历每个章节条目
for entry in catalog:
    chapter = entry["chapter"]
    start_page = entry["start_page"]
    end_page = entry["end_page"]
    print(f"处理章节: {chapter}, 页码范围: {start_page}-{end_page}")

    for page_num in range(start_page, end_page + 1):
        file_path = md_path / f"{page_num}.md"
        
        if not file_path.exists():
            print(f"警告: 文件 {file_path} 不存在，跳过。")
            continue

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 构造 prompt（确保 prompt3.txt 中有 {content} 占位符）
        prompt = prompt_template.format(content=content.strip())

        try:
            # 调用模型
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                response_model=IsQA,
                max_retries=2
            )
            is_qa = response.is_qa
        except Exception as e:
            print(f"页码 {page_num} 处理出错: {e}")
            is_qa = False  # 或设为 None，根据需求

        # 保存结果
        results.append({
            "chapter": chapter,
            "page": page_num,
            "is_qa": is_qa  
        })

        print(f"  → 页 {page_num}: {'是' if is_qa else '否'}")

########################### 每一章节最后一页自动设置成True
# 第一步：记录每个 chapter 最后一次出现的索引
last_index_of = {}
for i, item in enumerate(results):
    chapter = item['chapter']
    last_index_of[chapter] = i  # 不断覆盖，最终保留最后一次出现的索引

# 第二步：遍历 results，对属于“章节最后一次出现”的项，设 is_qa = True
for i, item in enumerate(results):
    if last_index_of[item['chapter']] == i:
        item['is_qa'] = True

############################# 合并qa_start和qa_end
from collections import OrderedDict

# 使用 OrderedDict 保持章节首次出现的顺序
chapter_qa = OrderedDict()

for item in results:
    chapter = item['chapter']
    page = item['page']
    is_qa = item['is_qa']
    
    if is_qa:
        if chapter not in chapter_qa:
            chapter_qa[chapter] = {'start': page, 'end': page}
        else:
            # 更新 end 为当前页（因为按顺序遍历，最后一个是真正的结束）
            chapter_qa[chapter]['end'] = page

# 转换为最终格式列表
results = [
    {
        'chapter': chap,
        'qa_start': info['start'],
        'qa_end': info['end']
    }
    for chap, info in chapter_qa.items()
]

with open(output_path+"/qapage.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n✅ 题目所在页码已推断完成！请检查：{output_path}/qapage.json")
input("🔧 确认无误后，请按回车继续……")

####################################################### 提取章节对应的题目
with open(output_path+"/qapage.json", "r", encoding="utf-8") as f:
    qapage = json.load(f)

# 读取提示词模板
with open("prompts/prompt4.txt", 'r', encoding='utf-8') as f:
    prompt_template = f.read()

class Options(BaseModel):
    # 使用 Optional[str] 并设置默认值为 None，这样非选择题时可以留空
    A: Optional[str] = Field(None, description="选项A的内容")
    B: Optional[str] = Field(None, description="选项B的内容")
    C: Optional[str] = Field(None, description="选项C的内容")
    D: Optional[str] = Field(None, description="选项D的内容")
    E: Optional[str] = Field(None, description="选项E的内容")
    F: Optional[str] = Field(None, description="选项F的内容")
    G: Optional[str] = Field(None, description="选项G的内容")
    H: Optional[str] = Field(None, description="选项H的内容")

class Question(BaseModel):
    question: str = Field(description="题目内容")
    # 如果题目没有选项（如填空题、简答题），AI 会填充 null
    options: Optional[Options] = Field(None, description="选择题的选项，非选择题则为null")

path=Path(output_path+"/md")

print("🧾 正在提取各章节题目内容……")
question=[]
for entry in qapage:
    chapter = entry["chapter"]
    qa_start = entry["qa_start"]
    qa_end = entry["qa_end"]
    print(f"正在处理章节: {chapter}, 合并页码 {qa_start} 到 {qa_end}")
    #############  合并页码内容为一个content
    pages_content = []
    for page_num in range(qa_start, qa_end + 1):
        file_path = path / f"{page_num}.md"
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                page_text = f.read().strip()
                if page_text:  # 忽略空页
                    pages_content.append(page_text)
        else:
            print(f"  ⚠️ 警告: {file_path} 不存在，跳过。")
    # 合并为一个完整 content，用换行分隔各页
    content = "\n\n--- PAGE BREAK (page {start}-{end}) ---\n\n".format(
        start=qa_start, end=qa_end
    ).join(pages_content)

    if not content.strip():
        print(f"  ❌ 章节 {chapter} 无有效内容，跳过。")
        continue
    #################### 构造 prompt
    prompt = prompt_template.format(content=content)
    #################### 提取question
    questions = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        response_model=list[Question],
        max_retries=2
    )
    ##################### 每个问题增加chapter，合并所有结果
    for idx, q in enumerate(questions, start=1):
            q_dict = q.model_dump()
            q_dict["chapter"] = chapter
            q_dict["id"] = idx  # ← 关键：章节内题目编号
            q_dict["qa_start"] = qa_start
            q_dict["qa_end"] = qa_end
            question.append(q_dict)
    print(f"  ✅ 成功提取 {len(questions)} 道题")

def clean_null(obj):
    """
    递归移除字典中值为 None 的键（包括嵌套字典）
    """
    if isinstance(obj, dict):
        return {
            k: clean_null(v)
            for k, v in obj.items()
            if v is not None
        }
    elif isinstance(obj, list):
        return [clean_null(item) for item in obj]
    else:
        return obj

question = clean_null(question)

with open(output_path+"/question.json", "w", encoding="utf-8") as f:
    json.dump(question, f, ensure_ascii=False, indent=2)

######################################################## 爬取question对应的answer
with open(output_path+"/question.json", "r", encoding="utf-8") as f:
    question = json.load(f)

# 读取提示词模板
with open("prompts/prompt5.txt", 'r', encoding='utf-8') as f:
    prompt_template = f.read()

# 定义响应模型（放在循环外）
class QA(BaseModel):
    answer: Optional[str]=Field(None,description="题目所对应的答案")
    
# Markdown 文件路径
# path=Path(output_path+"/md")

qa=[]

print("🔍 正在为每道题匹配答案……")

for entry in question:
    id=entry["id"]
    chapter=entry["chapter"]
    q_text = entry["question"]   
    qa_start = entry["qa_start"]
    qa_end = entry["qa_end"]
    options = entry.get("options", None)
    ################ 合并所有页码的内容成为content
    pages_content = []
    for page_num in range(qa_start, qa_end + 1):
        file_path = path / f"{page_num}.md"
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                page_text = f.read().strip()
                if page_text:  # 忽略空页
                    pages_content.append(page_text)
        else:
            print(f"  ⚠️ 警告: {file_path} 不存在，跳过。")
    # 合并为一个完整 content，用换行分隔各页
    content = "\n\n".join(pages_content)

    if not content.strip():
        print(f"  ❌ 章节 {chapter} 无有效内容，跳过。")
        continue
    #################### 构造 options 字符串（用于提示词）
    if options:
        options_str = "\n".join([f"{k}. {v}" for k, v in options.items() if v is not None])
    else:
        options_str = "（本题无选项，为非选择题）"
    #################### 构造 prompt
    prompt = prompt_template.format(question=q_text, options=options_str, content=content)
    #################### 调用 OpenAI API
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        response_model=QA,
        max_retries=2,
    )
    result = {
            "id": id,
            "chapter": chapter,
            "question": q_text,
            "options": options,
            "answer": response.answer
        }
    qa.append(result)
    print(f"  ✅ 章节 {chapter}, 题号 {id}: 答案 = '{response.answer}'")

########################## 清洗null

qa = clean_null(qa)

with open(output_path+"/qa.json", "w", encoding="utf-8") as f:
    json.dump(qa, f, ensure_ascii=False, indent=2)

########################################################### 题目类型注释
################################# 读取question.json

input("🔧 是否开始题目类型注释？请按回车继续……")

with open(output_path+"/qa.json", "r", encoding="utf-8") as f:
    qa = json.load(f)

# 有的条目没有answer
filtered_data = [
    item for item in qa
    if "answer" in item and item["answer"] is not None and str(item["answer"]).strip()
]
qa=filtered_data

# 读取提示词模板
with open("prompts/prompt6.txt", 'r', encoding='utf-8') as f:
    prompt_template = f.read()

class Type(str,Enum):
    type1="选择题"
    type2="填空题"
    type3="判断题"
    type4="简答题"

class QAType(BaseModel):
    type: Type=Field(None,description="题目类型")
    

qatype=[]
print("🔍 正在为每道题目所属类型……")
for entry in qa:
    id=entry["id"]
    chapter=entry["chapter"]
    question=entry["question"]
    options = entry.get("options", None)
    answer=entry["answer"]
    #################### 构造 options 字符串（用于提示词）
    if options:
        options_str = "\n".join([f"{k}. {v}" for k, v in options.items() if v is not None])
    else:
        options_str = "（本题无选项，为非选择题）"
    #################### 构造 prompt
    prompt = prompt_template.format(question=question, options=options_str, answer=answer)
    #################### 调用 OpenAI API
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        response_model=QAType,
        max_retries=2,
    )
    result = {
            "id": id,
            "chapter": chapter,
            "question": question,
            "options": options,
            "answer": answer,
            "type": response.type.value
        }
    qatype.append(result)
    print(f"  ✅ 章节 {chapter}, 题目 {question}: 类型 = '{response.type.value}'")

########################## 清洗null

qatype = clean_null(qatype)

with open(output_path+"/qatype.json", "w", encoding="utf-8") as f:
    json.dump(qatype, f, ensure_ascii=False, indent=2)

###############################################################题目内容注释
input("🔧 是否开始题目内容注释？请按回车继续……")

with open(output_path+"/qatype.json", "r", encoding="utf-8") as f:
    qatype = json.load(f)

# 读取提示词模板
with open("prompts/prompt7.txt", 'r', encoding='utf-8') as f:
    prompt_template = f.read()

class ContentType(str, Enum):
    ContentType1="病因病理"
    ContentType2="临床表现"
    ContentType3="诊断治疗"
    ContentType4="文献指南"
    ContentType5="其他"

class ContentType(BaseModel):
    content: ContentType=Field(None,description="题目所属的内容")
    
qacontent=[]
print("🔍 正在为每道题目匹配所属内容类型……")
for entry in qatype:
    id=entry["id"]
    chapter=entry["chapter"]
    question=entry["question"]
    options = entry.get("options", None)
    answer=entry["answer"]
    type=entry["type"]
    #################### 构造 options 字符串（用于提示词）
    if options:
        options_str = "\n".join([f"{k}. {v}" for k, v in options.items() if v is not None])
    else:
        options_str = "（本题无选项，为非选择题）"
    #################### 构造 prompt
    prompt = prompt_template.format(question=question, options=options_str, answer=answer)
    #################### 调用 OpenAI API
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        response_model=ContentType,
        max_retries=2,
    )
    result = {
            "id": id,
            "chapter": chapter,
            "question": question,
            "options": options,
            "answer": answer,
            "type": type,
            "content": response.content.value
        }
    qacontent.append(result)
    print(f"  ✅ 章节 {chapter}, 题目 {question}: 内容 = '{response.content.value}'")

########################## 清洗null
qacontent = clean_null(qacontent)

with open(output_path+"/qacontent.json", "w", encoding="utf-8") as f:
    json.dump(qacontent, f, ensure_ascii=False, indent=2)

####################################################### 题目属于哪种人体系统
#################### 读取qacontent.json
input("🔧 是否开始判断题目属于哪种人体系统？请按回车继续……")

with open(output_path+"/qacontent.json", "r", encoding="utf-8") as f:
    qacontent = json.load(f)

##################### 进行相关人体系统注释（第一轮系统注释）

# 读取提示词模板
with open("prompts/prompt8.txt", 'r', encoding='utf-8') as f:
    prompt_template = f.read()

class System(str, Enum):
    System1="呼吸系统"
    System2="心血管系统"
    System3="消化系统"
    System4="泌尿系统"
    System5="血液系统"
    System6="内分泌系统"
    System7="风湿性疾病"
    System8="运动系统"
    System9="传染病、性病"
    System10="产科学"
    System11="妇科学"
    System12="儿科疾病"
    System13="神经内外科疾病"
    System14="精神病"
    System15="其他"

class System(BaseModel):
    system: System=Field(None,description="题目所属的相关人体系统")

qasystem=[]
print("🔍 正在为每道题目匹配所属相关人体系统……")
for entry in qacontent:
    id=entry["id"]
    chapter=entry["chapter"]
    question=entry["question"]
    options = entry.get("options", None)
    answer=entry["answer"]
    type=entry["type"]
    content=entry["content"]
    #################### 构造 options 字符串（用于提示词）
    if options:
        options_str = "\n".join([f"{k}. {v}" for k, v in options.items() if v is not None])
    else:
        options_str = "（本题无选项，为非选择题）"
    #################### 构造 prompt
    prompt = prompt_template.format(chapter=chapter, question=question, options=options_str, answer=answer)
    #################### 调用 OpenAI API
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        response_model=System,
        max_retries=2,
    )
    result = {
            "id": id,
            "chapter": chapter,
            "question": question,
            "options": options,
            "answer": answer,
            "type": type,
            "content": content,
            "system": response.system.value
        }
    qasystem.append(result)
    print(f"  ✅ 章节 {chapter}, 题目 {question}: 系统 = '{response.system.value}'")

########################## 清洗null

qasystem = clean_null(qasystem)

with open(output_path+"/qasystem.json", "w", encoding="utf-8") as f:
    json.dump(qasystem, f, ensure_ascii=False, indent=2)

########################################## 疾病注释
#################### 读取qasystem.json
input("🔧 是否开始判断题目属于哪种疾病？请按回车继续……")

with open(output_path+"/qasystem.json", "r", encoding="utf-8") as f:
    qasystem = json.load(f)

# 读取提示词模板
with open("prompts/prompt9.txt", 'r', encoding='utf-8') as f:
    prompt_template = f.read()

disease_path= "disease"

qadisease=[]
print("🔍 正在为每道题目匹配所属疾病标签……")
for entry in qasystem:
    id=entry["id"]
    chapter=entry["chapter"]
    question=entry["question"]
    options = entry.get("options", None)
    answer=entry["answer"]
    type=entry["type"]
    content=entry["content"]
    system=entry["system"]

    #################################### 动态加载system对应的disease标签
    file_path = os.path.join(disease_path, f"{system}.py")
    # 检查是否存在 
    if not os.path.exists(file_path):
        print(f"⚠️ 警告: 未找到系统 '{system}' 对应的枚举文件: {file_path}")
        entry["disease"] = None
        continue
    # 动态加载模块
    spec = importlib.util.spec_from_file_location(f"{system}_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # 获取 Disease 类
    if not hasattr(module, 'Disease'):
        print(f"❌ 错误: 文件 {file_path} 中未定义 'Disease' 类")
        entry["disease"] = None
        continue
    DiseaseEnum = module.Disease  # 直接拿到 Enum 类

    ######################################### 构造选项字符串
    if options:
        options_str = "\n".join([f"{k}. {v}" for k, v in options.items() if v is not None])
    else:
        options_str = "（本题无选项，为非选择题）"

    ######################################### 疾病列表字符串
    disease_list_str = "\n".join([f"- {item.value}" for item in DiseaseEnum])

    ######################################### 填充提示词
    prompt = prompt_template.format(
        disease_list=disease_list_str,
        question=question,
        options=options_str,
        answer=answer)

    # 动态创建 Pydantic 模型（使用刚加载的 DiseaseEnum）
    class DiseaseAnnotation(BaseModel):
        disease: DiseaseEnum = Field(..., description="题目所属条目")
    
    ######################################### 调用大模型进行注释
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_model=DiseaseAnnotation,
            max_retries=2,
        )
        result = {
            "id": id,
            "chapter": chapter,
            "question": question,
            "options": options,
            "answer": answer,
            "type": type,
            "content": content,
            "system": system,
            "disease": response.disease.value
        }
        qadisease.append(result)
        print(f"✅ ID {id} ({system}) → {response.disease.value}")

    except Exception as e:
        print(f"❌ ID {id} 推理失败: {e}")
        entry["disease"] = None

qadisease = clean_null(qadisease)

with open(output_path+"/qadisease.json", "w", encoding="utf-8") as f:
    json.dump(qadisease, f, ensure_ascii=False, indent=2)

print("\n✨ 处理流程已全部完成！")
print(f"📚 所有结构化结果已保存至：{output_path}")
print("💡 建议：请人工抽查部分章节，确保模型识别准确。")







