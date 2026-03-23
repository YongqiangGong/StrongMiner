# 🧠 StrongMiner

[**中文**](./README.md) | [**English**](./README_EN.md)

StrongMiner is a structured exercise set extraction framework integrating Large Language Models (LLMs) with human-in-the-loop mechanisms. It efficiently parses catalogs, extracts Q&A pairs, performs label annotation, and outputs structured JSON data from PDF exercise sets.

## 📚 Table of Contents

- [Introduction]
- [✨ Key Features]
- [📁 Project Structure]
- [⚙️ Installation & Usage]
- [⚠️ Precautions]
- [🌍 Application Scenarios]
- [👥 Team & Institution]

## 📖 Introduction 

StrongMiner is designed for the structural extraction of educational exercise sets. Leveraging the semantic understanding of LLMs, it automatically parses PDF structures, identifies chapters, matches questions with answers, and generates standardized JSON outputs.

The framework innovatively incorporates a **human-computer interaction (HCI)** workflow. This addresses the common "context window" limitation of LLMs, allowing the system to process thick documents and long exercise sets with high accuracy through multi-step human-AI collaboration.

## ✨ Key Features

- **📖 Catalog Recognition**: Automatically identifies catalog pages and distinguishes them from body text.
- **📑 Chapter Extraction**: Extracts chapter titles and corresponding page ranges.
- **❓ Question Identification**: Intelligently detects whether content contains questions or answers.
- **✅ Answer Matching**: Pairs answers with their respective questions automatically.
- **🏷️ Label Annotation**: Tags questions based on content (e.g., disease type, system).
- **🧾 Structured Output**: Exports all data into standardized JSON formats.

## 📁 Project Structure

```
StrongMiner/
│
├── disease/                          
│   ├── 产科学.py                     
│   ├── 传染病、性病...py             
│   ├── 儿科疾病.py                     
│   ├── 风湿性疾病.py                   
│   ├── 妇科学.py                       
│   ├── 呼吸系统.py                     
│   ├── 精神病.py                      
│   ├── 泌尿系统.py                     
│   ├── 内分泌系统.py                   
│   ├── 其他.py                        
│   ├── 神经内外科疾病py             
│   ├── 消化系统.py                     
│   ├── 心血管系统.py                  
│   ├── 血液系统.py                     
│   └── 运动系统.py                     
│
├── prompts/                            
│   ├── prompt1.txt                     
│   ├── prompt2.txt                    
│   ├── prompt3.txt                     
│   ├── prompt4.txt                    
│   ├── prompt5.txt                     
│   ├── prompt6.txt                     
│   ├── prompt7.txt                     
│   ├── prompt8.txt                     
│   └── prompt9.txt                     
│
├── langgraph_code.py                   
├── my_code.py                           
├── README.md                            
└── README_EN.md                         
```

## ⚙️ Installation & Usage
### 1. Environment Setup

```Bash
conda create -n StrongMiner python=3.12
conda activate StrongMiner
```

### 2. Dependencies

For PaddleOCR, please refer to the Official Repository. Other dependencies:

```Bash
pip install instructor openai pydantic langgraph
```

### 3. Download & Run
```Bash
git clone [https://github.com/YongqiangGong/StrongMiner.git](https://github.com/YongqiangGong/StrongMiner.git)
cd StrongMiner
python langgraph_code.py
# or run 
# python my_code.py
```

### 5. Workflow & Human-Computer Interaction (Medical Example)
StrongMiner uses a phased execution process with human-in-the-loop verification to ensure data accuracy. Below is the full operation flow for medical exercise sets:

#### 🔧 5.1 Initial Configuration
After running the main script, manually input the following configuration (supports absolute/relative paths and standard API formats):
- 📄 **PDF Source Path** (e.g., `/home/user/pdf`)
- 📂 **Output Directory** (e.g., `/home/user/output`)
- 🌐 **LLM API Endpoint** (e.g., `https://dashscope.aliyuncs.com/compatible-mode/v1`)
- 🤖 **Model Name** (e.g., `qwen-max`)
- 🔑 **API Key** (e.g., `sk-2d7c12272772`)

#### 🔄 5.2 PDF to Markdown Preprocessing
The framework automatically converts PDF files to Markdown:
- This step may take time due to OCR processing.
- To improve efficiency, refer to the PaddleOCR tutorial to adjust OCR parameters.

#### 📑 5.3 Catalog Identification & Correction
1. Set the "Maximum Catalog Page" (Default is 20. **Note: StrongMiner uses 0-indexed page numbers**).
2. The framework scans for the catalog range. You must manually verify and correct the "Start Page" and "End Page" before proceeding.

#### 📘 5.4 Chapter Structure Parsing
1. Input the start page of the main body. The framework identifies chapter titles and their respective page ranges.
2. Manually review and correct these ranges to ensure no questions are missed in the following steps.

#### ❓ 5.5 Question Positioning & Verification
1. The framework analyzes the page distribution of questions within each chapter.
2. Manually verify the accuracy of question pages. Once confirmed, the "Question Extraction + Answer Matching" core engine will start.

#### 🏷️ 5.6 Custom Label Configuration
- By default, StrongMiner adds multi-dimensional labels: Question Type, Stem Content, Human Body System, and Disease Classification.
- To adapt to custom labeling (e.g., difficulty levels, knowledge points), modify the prompt templates and parsing logic in the code.

### 6. Outputs

Upon completion, StrongMiner generates the following files in your output directory:

- `md`: The Markdown version of the source PDF.
- `qa.json`: Complete structured data containing questions and answers.
- `qatype.json`: Questions categorized by type (Multiple choice, Fill-in-the-blank, etc.).
- `qacontent.json`: Questions categorized by content (Etiology, Diagnosis, Clinical manifestations, etc.).
- `qasystem.json`: Questions categorized by human body systems.
- `qadisease.json`: Questions categorized by disease classification.

---

## ⚠️ Precautions

- 🚀 **Model Power**: It is highly recommended to use large-scale parameter models (e.g., Qwen-Max, GPT-4) to ensure extraction quality.
- 🔗 **Matching Scope**: Currently, StrongMiner only matches questions and answers within the same chapter. Cross-chapter matching is not yet supported.
- ⏱️ **OCR Speed**: PDF-to-Markdown conversion can be slow. For acceleration, refer to the PaddleOCR documentation (or use Vllm).
- 🔓 **Customization**: This is an open-source project; users are encouraged to modify the prompts and code to suit specific needs.

## 🌍 Application Scenarios

- 📚 **Question Bank Construction**: Automatically building structured databases from textbooks.
- 💻 **Online Education**: Transforming paper-based materials into digital learning resources.
- 🧠 **Knowledge Management**: Structuring and organizing medical knowledge hierarchies.
- 🤖 **AI Tutoring**: Providing high-quality Q&A data pairs for fine-tuning educational AI.

## 👥 Team Members

- Yongqiang Gong
- Ruixi Li
- Han Dong
- Chenyu Xue
- Ruiqi Ma
- Yijin Liu
- Puhe Gong
- Mingyang Zhang

## 👥 Research Supervisor

- Yi Bai 
- Yin Liu
- Yamin Zhang

## 🏛️ Institution

- School of Medicine, Nankai University
- Department of Hepatobiliary Surgery, Tianjin First Central Hospital
