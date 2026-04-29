# 高数智能错题本 Demo

这是一个本地可运行的高数学习 MVP：

- 上传 PDF 做题本，每页自动拆成一道题。
- 保存每页题图和可提取文字。
- 自动按高数知识点分类。
- 标记做对、做错、半会、需复习。
- 记录错因和备注。
- 生成错题分析。
- 生成每日练习清单。

## 启动

```powershell
python app.py
```

然后打开：

```text
http://127.0.0.1:8000
```

## 使用 AI API

如果设置了 `OPENAI_API_KEY`，系统会优先调用 OpenAI 进行题目分类和错题分析；否则使用本地关键词规则，仍然可以完整体验 demo。

```powershell
$env:OPENAI_API_KEY="你的 key"
python app.py
```

可选设置模型：

```powershell
$env:OPENAI_MODEL="gpt-4o-mini"
python app.py
```
