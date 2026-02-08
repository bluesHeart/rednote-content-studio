# （墨滴/公众号粘贴版）把 Markdown 变成 REDnote 卡片，把“最后一公里”交还给人

> 说明：这是一份可直接粘贴到墨滴/公众号编辑器的版本，文内图片已替换为公网 CDN 链接。
>
> GitHub：https://github.com/bluesHeart/rednote-content-studio（欢迎 Star ⭐）

---

你可能也遇到过这个场景：

你有一篇挺完整的技术文稿（Markdown / 笔记 / 研究记录），想发成 REDnote 图文。  
结果不是手动切图切到崩溃，就是让 AI 一键改写后发现——

- 图文顺序不稳定、图片乱飞
- 每页像“新开一条帖”，不连续
- 文风被模型“接管”，你失去编辑权

我们把这个问题当成一个完整工程重新做了一遍，做出了 **rednote-content-studio**：

> 先让 LLM 干重体力活（解析、分页、初稿），  
> 再把最后一公里交给用户自己（块级编辑、锁定、局部重写、拖拽图片）。

---

## 先看成品：图文卡片是“流动的”，不是堆在页顶

![Demo 卡片拼接 A（1-2页）](https://cdn.jsdelivr.net/gh/bluesHeart/rednote-content-studio@main/docs/showcase/article_assets/21_cards_pair_clean_a.png)

![Demo 卡片拼接 B（3-9页）](https://cdn.jsdelivr.net/gh/bluesHeart/rednote-content-studio@main/docs/showcase/article_assets/22_cards_pair_clean_b.png)

关键点只有一个：**图片跟随正文流动**，不会出现“图片顺序对不上 / 位置对不上 / 重复插图”这类翻车体验。

---

## Web App：粘贴 → 一键转换 → 预览 → 最后一公里微调

![Web 流程拼接 A](https://cdn.jsdelivr.net/gh/bluesHeart/rednote-content-studio@main/docs/showcase/article_assets/18_web_flow_pair_clean_a.png)

![Web 流程拼接 B](https://cdn.jsdelivr.net/gh/bluesHeart/rednote-content-studio@main/docs/showcase/article_assets/19_web_flow_pair_clean_b.png)

---

## 最关键的设计：可编辑的“中间层”，而不是一次性生成

我们把内容拆成可编辑的块（例如 `title` / `text` / `image`），每个块都有独立的锁定状态。

这带来三个直接收益：

- 你可以只改某几个文本块，不动其他块
- 你可以锁定满意的块，后续局部重写不许碰
- 你可以调整图片块顺序，让图文重新对齐

![最后一公里编辑与预览弹窗](https://cdn.jsdelivr.net/gh/bluesHeart/rednote-content-studio@main/docs/showcase/article_assets/20_web_edit_pair_clean.png)

---

## 一句话总结

我们不是在做“更会写的 AI”，而是在做：

> 一个把复杂转换流程自动化、但把最终决定权还给人的内容系统。

如果你也在做“AI 生成 + 人工收口”的产品（内容/设计/代码都适用），这套思路会很管用：

- 哪些环节交给模型做“重体力活”
- 哪些环节必须让人“最后拍板”
- 中间层是否足够可编辑、可回退、可审计

---

## 想直接上手？

- GitHub：https://github.com/bluesHeart/rednote-content-studio
- 建议先 Star：后续更新你能第一时间看到

