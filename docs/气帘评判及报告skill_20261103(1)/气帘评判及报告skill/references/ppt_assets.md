# 从云图到 PPT 素材：拼版、动画 GIF、落位与校验

上一篇 `hyperview_postprocess.md` 产出的是**原始截图**（1200×900、四周大片白底、
带 HyperView 图例与 `Frame N` 角标）。本篇把这些变成能直接进报告的素材。

---

## 1. 三种素材，三种用途

| 素材 | 尺寸（本 skill 默认） | 体积 | 用在哪 |
| --- | --- | --- | --- |
| `fourview_animation.gif` | 1280×960（4 格 640×480） | 21 帧 ≈ 3.4 MB | 「展开过程」页主体，模仿客户参考报告第 4 页 |
| `fourview_last.png` | 1280×960 | ≈ 330 KB | 同一页的静态兜底（打印、动画不播、审阅者截图） |
| 单视角 `front_s82.png` | 1200×900 | 100–180 KB | 证据页单图；需要精确读数时用 |

原则：**动画页只放动画 + 一句判读原则**，不要把数值表塞进去——动画在放映时数值看不清，
审阅者会来回翻页。

---

## 2. 拼版规则（`hv_render.py gif` 已实现）

```bash
python scripts/hv_render.py gif --shots out/shots.json \
    --gif  assets/fourview_animation.gif \
    --png  assets/fourview_last.png \
    --cell 640x480 --duration 90
```

四步处理，每一步都有原因：

1. **裁白边**（`_crop_white`，阈值 246、pad 14）
   HyperView 截图的有效内容常只占中间 60%。不裁，四格拼起来每格都是"小图 + 大留白"，
   投到会议室屏幕上根本看不清气帘形态。阈值 246 是为了不把浅灰图例底纹当内容。
2. **等比缩放 + 居中**（`_fit_cell`）
   用 `min(cw/iw, ch/ih)`，**绝不拉伸**。气帘长条形，一旦按格拉伸，厚度与角度全失真，
   报告里就变成错误证据。
3. **画视角角标**（左上角深蓝块 + 白字 `FRONT/BACK/LEFT/RIGHT`）
   参考报告的做法。没有角标，读者分不清哪格是前视还是侧视。
4. **GIF 参数**：`duration=90ms`、`loop=0`（无限循环）、`disposal=2`（每帧清空，避免残影）、
   `optimize=True`。

> 帧数与体积的取舍：21 帧 / 3.4 MB 是甜点（放映流畅、邮件能发）。
> 想要更顺滑可 30–40 帧，但 PPT 会到 5–6 MB，注意客户邮箱与内网限制。
> 参考报告那张是 152 帧 / 8.7 MB——**不必对齐它的帧数**。

---

## 3. 落进 slide DSL

模板工程结构：

```
IC_Coverage_G143/
├─ IC_Coverage_G143.pptx
├─ DESIGN.md              # 颜色/字号/版式约定
├─ assets/                # 图片素材（DSL 里写相对路径）
│   ├─ fourview_animation.gif
│   └─ fourview_last.png
└─ slides/01.slide … 12.slide
```

动画页的关键片段：

```jsx
<Box style={{ flex: 1, justifyContent: 'center', alignItems: 'center',
              backgroundColor: '#F7F9FC', borderRadius: 10 }}>
  <Image src="assets/fourview_animation.gif"
         style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
</Box>
```

三条硬规则：

1. **`width` 和 `height` 必须同时写**。只写 width 时 slidep 不按真实比例取高 → 图被压扁。
2. 用 `objectFit: 'contain'`。截图是 4:3，页面是 16:9，`cover` 会切掉图例或气帘两端。
3. 图片放 `assets/`，DSL 写相对路径。**换图后必须重新 upsert**，因为 pptx 内嵌的是副本。

标题行建议带上判读所需的三要素，省一页说明：

> 前视 / 后视 / 左视 / 右视 四视角同步展开（位移幅值 Mag，Frame 1→82，T = 200 ms）

---

## 4. 构建与校验

```bash
cd <project>
SLIDEP=~/.workbuddy/binaries/node/versions/22.22.2-6/slidep
"$SLIDEP" create deck.pptx
for n in 01 02 … 12; do
  "$SLIDEP" upsert-dsl deck.pptx --dsl-file "slides/$n.slide" --page-index -1
done
```

- `upsert-dsl` 返回 `{"ok":true,"failures":[]}` 才算过；**出现 failures 必须逐条看**。
- 新增页后**页脚总数要同步改**（`x / 11` → `x / 12`），否则最后一页写 12/11。
- `slidep screenshot` 需要 Vulkan/GPU 合成，**无头环境一定失败**（不要以为是版式问题）。

### 无截图时怎么确认真的嵌进去了

```bash
python - <<'PY'
import zipfile, hashlib
z = zipfile.ZipFile("deck.pptx")
print("slides:", len([n for n in z.namelist()
                     if n.startswith("ppt/slides/slide") and n.endswith(".xml")]))
for m in [n for n in z.namelist() if "media" in n and n.endswith((".gif",".png"))]:
    print(m, len(z.read(m))//1024, "KB", hashlib.md5(z.read(m)).hexdigest()[:12])
PY
# 再和 assets/ 下本地文件的 md5 对比：一致 = 内嵌的就是你刚生成的那份
```

这一步很值得做：曾经出现过"upsert 成功但嵌入的仍是旧 GIF"的错觉，
直到比对 md5 才发现 pptx 里还是上一版素材。

---

## 5. 素材页自检清单

- [ ] 四格视角确实不同（`hv_render.py check` 的 unique md5 == 总数）
- [ ] 图例量程与所选结果类型一致（`Displacement Mag` 的 Max/Min 合理，不是 0）
- [ ] 角标 FRONT/BACK/LEFT/RIGHT 与画面一致（侧视应看到上边梁 + B 柱）
- [ ] `<Image>` 写了 width + height + `objectFit: contain`
- [ ] pptx 内嵌素材 md5 == 本地文件 md5
- [ ] 页脚分母 = 总页数
- [ ] 判读原则那一句在页面上（动画异常则结果不可采信，G.14.3.2）
