# Sakura做题集

这是一个本地可运行的 PDF 做题集管理 demo，最新源码包已在本地生成：`Modernized_learning_source.zip`。

## 最新功能

- 上传 PDF 做题本，每页拆成一道题。
- 做题本可按自定义科目管理，例如高数、408、专业课等。
- 题库筛选支持科目、做题本、知识点、章节级联联动。
- 知识点和章节来自导入 PDF 时识别到的内容。
- 每套做题本可单独删除、重扫章节、查看章节正确率。
- 每日练习只从错题、半会题、需复习题中生成。
- 每日练习按“科目 + 做题本”分组，每组最多 5 道。
- 总结与反思按周/月统计实际标记过的题目，不把单纯导入但未做的题计入。
- 总结与反思会按科目拆分统计，例如高数本周做了多少、做对多少、做错多少、需复习多少。
- DeepSeek 只在生成错题分析、举一反三、总结反思时调用；PDF 导入和章节识别在本地完成。

## 启动

```powershell
pip install -r requirements.txt
python app.py
```

然后打开：

```text
http://127.0.0.1:8000
```

## DeepSeek

```powershell
$env:DEEPSEEK_API_KEY="你的 key"
$env:DEEPSEEK_MODEL="deepseek-chat"
python app.py
```
