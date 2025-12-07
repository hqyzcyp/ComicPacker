# Bug修复和功能改进

## 任务1: 修复转换按钮不发送命令的Bug

### 问题原因
之前使用 `formData.get('convert_to_mobi') === 'on'` 来读取checkbox的值，但当checkbox默认勾选时，FormData可能无法正确获取checked状态。

### 解决方案
直接使用DOM元素的 `.checked` 属性：
```javascript
convert_to_mobi: convertToMobiCheckbox.checked
```

### 额外改进
- 添加了 `console.log` 调试日志，方便查看发送的参数
- 确保错误处理逻辑正确

---

## 任务2: 前缀自动设置输出文件夹

### 功能说明
当用户设置了文件名前缀时，输出文件夹会自动使用该前缀作为子目录名称。

### 实现逻辑
```javascript
const prefix = formData.get('prefix') || '';
let outputFolder = formData.get('output') || './output';

if (prefix) {
    outputFolder = `./output/${prefix}`;
}
```

### 使用示例
- **不设置前缀**: 输出到 `./output/`
- **设置前缀为 "寓言杀手"**: 输出到 `./output/寓言杀手/`
- **设置前缀为 "我的漫画"**: 输出到 `./output/我的漫画/`

### 优势
- 自动组织输出文件，避免混乱
- 不同系列的漫画自动分类存储
- 保持输出目录整洁有序

---

## 测试建议

1. **测试转换功能**:
   - 选择文件夹
   - 点击"开始转换"按钮
   - 检查浏览器控制台是否有 "发送转换请求" 日志
   - 验证转换任务是否正常启动

2. **测试输出文件夹**:
   - 设置前缀为 "test"
   - 启动转换
   - 检查输出文件是否在 `./output/test/` 目录下
