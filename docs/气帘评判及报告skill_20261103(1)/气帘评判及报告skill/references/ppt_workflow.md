# PPT 工作流（workbuddy-pptx / slidep）

> 中文报告走 `workbuddy-pptx` skill（office-routing 门控）。本文件是该 skill 的
> DSL 速记 + 本评估专有的设计系统与实测坑位。完整 DSL 见 workbuddy-pptx 的
> `references/dsl/{slide,box,text,image,table,svg}.md`。

## 命令流
```bash
slidep create report.pptx                                   # 建空 deck
slidep upsert-dsl report.pptx --dsl-file slides/01.slide     # 追加一页
slidep upsert-dsl report.pptx --dsl-file slides/08.slide --page-index 7   # 覆盖第 8 页
slidep lint report.pptx --dsl-file slides/01.slide --page-index 0         # 单页校验
slidep inspect report.pptx --out inspect/                    # 结构核对（生成 slides.md）
```
> 每条命令冷启动 Node，数秒级；批量时给足 timeout。`upsert-dsl` 不带 `--page-index`
> 就是追加；带索引是覆盖该页（不改变总页数）。

## DSL 要点（实测）
- 根元素 `<Slide style={{...}}>`，内部 `<Box>`（flex）与 `<Text>`。
- 表格 `<Table cells={[[...]]} defaultTextStyle={...} defaultCellStyle={...} />`；
  单元格可写 `{text:'...', textStyle:{...}, cellStyle:{...}}`；**单元格内不支持 `\n`**。
- 内联矢量图直接写 `<svg viewBox=...>...</svg>`。
- 字符串里的中文引号用普通直引号即可，不需要转义。

## ⚠️ 图片必须写死宽高
```jsx
<Image src="assets/fig.png" style={{ width: 880, height: 352 }} />
```
只给 `width` 时，转换器**不会按图片真实比例取高**，会把图压扁（曾把 1531×861 的图压成
640×100）。每次加图先算 `height = width * 像素高 / 像素宽`，两者一起写。

已知图的像素比：
| 图 | 像素 | h/w |
| --- | --- | --- |
| `fig_G3_eval_region.png` | 见 assets/figures | 按文件算 |
| `fig_G4_head_cog.png` | 见 assets/figures | 按文件算 |
| 厚度场（`fig_thk_field.png`） | 1950×780 | 0.400 |
| 厚度时程（`fig_thk_curves.png`） | 1440×690 | 0.479 |

## 设计系统（两种风格，按客户模板选）

### A. 通用蓝白学术风
- 画布 **1280×720**；内容页 = 顶部深蓝标题条(72) + 内容区(padding 48) + 页脚(36)。
- 配色：主 `#1E4FA8`；警示 `#D9534F`；通过 `#2E7D32`；正文 `#1A2230`；辅助 `#8B97A8`；
  浅底 `#E8EFF8` / `#F7F9FC`；分隔线 `#E5E7EB`。
- 字号：页标题 30–32(bold)；卡片标 22；正文 18–20；表 16–18；注释 13–14。

### B. 客户模板（Autoliv 类，优先）
- 从 `ppt/theme/theme1.xml` 取 `clrScheme`：本例 主 `#005496`、强调 `#009FE3`、
  正文 `#474C4F`、正文浅灰 `#8A9096`、分隔页巨号数字 `#E3EEF8`。
- 字号：封面主标 46–58；页标题 40–46；分隔页数字 200；表头/正文 18–22。
- 母题：左上标题 + 右上页码 + 底部细线；分隔页"巨号浅色数字 + 章节名"。

## 排版自检（交付前必做）

```bash
# 边界：所有元素右下 y 必须 <= 720
D=$(mktemp -d) && slidep inspect report.pptx --out "$D" >/dev/null
python - "$D" <<'PY'
import re,sys,pathlib
txt=(pathlib.Path(sys.argv[1])/'slides.md').read_text(encoding='utf-8')
for k,v in re.findall(r'^## 第 (\d+) 页\n([\s\S]*?)(?=^## 第 |\Z)', txt, re.M):
    ys=[float(m) for m in re.findall(r'右下\s*[\d.]+,\s*([\d.]+)', v)]
    if ys and max(ys) > 720: print('OVERFLOW page', k, max(ys))
PY

# 图片比例：解压后看每个 <p:pic> 的 a:ext
unzip -o -q report.pptx -d /tmp/chk && python - <<'PY'
import re,glob,os
for f in sorted(glob.glob('/tmp/chk/ppt/slides/slide*.xml')):
    s=open(f,encoding='utf-8').read()
    for pic in re.findall(r'<p:pic>.*?</p:pic>', s, re.S):
        off=re.search(r'<a:off x="(\d+)" y="(\d+)"/>',pic); ext=re.search(r'<a:ext cx="(\d+)" cy="(\d+)"/>',pic)
        if off and ext:
            x,y,w,h=[int(v)/9525 for v in (*off.groups(),*ext.groups())]
            print(os.path.basename(f), f'({x:.0f},{y:.0f}) {w:.0f}x{h:.0f} bottom={y+h:.0f}')
PY
```

## 本环境限制
- `slidep screenshot` 在本机因缺 Vulkan 组件不可用（`Failed to resolve Vulkan proc
  vkEnumerateInstanceVersion`）→ 无法逐页出图核对，只能靠 lint + 坐标计算。
- PDF 转 PNG 同样不可用；需要规程插图时，用工具抽 `pdfimages` 内嵌图（`--image-dir`），
  不要依赖页面渲染。

## 页面清单模板
见 `references/report_structure.md` 的四段式骨架；`assets/ppt_template/` 下有
封面 / 评分卡 / 云图页 / 区域示意图 / 证据图 的 `.slide` 起手模板。
